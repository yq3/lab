"""L5.2 图本体：L5.1 副本 + submit 审批换芯（本课核心）。

L5.2 副本声明（对版纪律「合理差异就地注释」）：拓扑六节点、重规划环、超限哨兵、
全部状态键与 L5.1 相同；差异集中在「送审半边」——
- submit 换芯：L5.1 的桩（置 sent=True 完事）换成 interrupt(payload) 真审批：
  L3.3 的抛-捕-落盘语义原样上产（payload 随状态落盘，恢复是重放）；
- 新增拒绝回环：submit --(reject)--> drafter（驳回留言作为 user 消息回喂重生成，
  A1「reject 的 message 回喂做纠错」+ A24 human 节点回环），MAX_APPROVAL_LOOPS=2 封顶；
- route_after_submit 三分支 + escalate 双哨兵（重规划烧完 / 审批回环烧完各一个枚举码）；
- compile(checkpointer=...)：interrupt 必须配 checkpointer（L3.3 铁律②），
  open_saver/run_config 是 AsyncSqliteSaver 的接线（L3.3 demo.open_saver 同款）。

固定拓扑（StateGraph，静态可审计）：

    START → intake → planner → plan_gate ─(valid)→ executor → drafter → submit → END
                        ↑ └─(invalid 未超限：原因回喂重规划)┘                ├─(approve)→ END
                        └──────────(超限)──────→ escalate → END              └─(reject 未超限)→ drafter（回环）
                                                                       └─(reject 超限)→ escalate

thread_id 即 run_id（审批单的归属凭证）：submit 从 config 里读它写进审批 payload——
L3.3 说「thread_id 丢了暂停点就无人认领」，本课把它产品化为 REST 建单的关联键。
"""

from __future__ import annotations

import hashlib
import json
import operator
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal, NotRequired, TypedDict

import aiosqlite
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

import mock_tools
import prompts
from advice import Advice
from executor import execute_plan
from plan import FetchBudgetStep, FetchClaimStep, Plan, PlanRejection, VerifyInvoiceStep, validate_plan

MAX_REPLANS = 2  # 重规划封顶：planner 最多被叫 1+2 次，第 3 次拒绝即超限转 escalate（L5.1 原样）
MAX_APPROVAL_LOOPS = 2  # 审批回环封顶：驳回留言最多回喂 2 次，第 3 次驳回即超限转 escalate（A24 max 思想）
ESCALATE_REASON = "REJECT:PLAN_REPLANS_EXCEEDED"  # 重规划烧完的枚举风格结论码（L5.1 原样）
ESCALATE_APPROVAL_REASON = "REJECT:APPROVAL_LOOPS_EXCEEDED"  # 审批回环烧完的枚举风格结论码（L5.2 新增）
DEFAULT_REJECT_FEEDBACK = "审批人驳回且未留留言：请复核建议单后重新起草。"
# superstep 预算：最坏链（脏计划 3 轮 + 审批回环 3 轮）约 15 步，L5.1 的 12 不够用——L5.2 副本差异
RECURSION_LIMIT = 20


def merge_results(old: dict, new: dict) -> dict:
    """results 键的合并 reducer：dict 版的 Annotated[list, operator.add]（L5.1 原样）。"""

    return {**old, **new}


class ExpenseState(TypedDict):
    """图状态：节点间唯一的通信媒介（L5.1 全部键 + L5.2 新增 approval_rejects）。

    - messages：会话史（本课新增一类内容：审批驳回留言——作为任务数据回喂 drafter）；
    - plan / plan_rejections / results / advice / events / sent：L5.1 原样；
    - approval_rejects：审批驳回逐次累积（每条带留言），回环封顶的计数依据、审计的账。
    """

    claim_id: str
    messages: Annotated[list, add_messages]
    plan: NotRequired[Plan]
    plan_rejections: Annotated[list[PlanRejection], operator.add]
    results: Annotated[dict[str, dict], merge_results]
    advice: NotRequired[Advice]
    events: Annotated[list[str], operator.add]
    sent: NotRequired[bool]
    approval_rejects: Annotated[list[dict], operator.add]  # 审批驳回账本：[{message: 驳回留言}] 逐次累积


# ---- 节点：纯「读状态 → 返回更新」的函数 ----


async def intake(state: ExpenseState) -> dict:
    """载单：读 mock 表组装单据摘要，planner 的岗位书（system）与事实来源（user）进场。"""
    view = mock_tools.claim_view(state["claim_id"])
    return {
        "messages": [
            {"role": "system", "content": prompts.PLANNER_SYSTEM},
            {"role": "user", "content": prompts.planner_brief(view)},
        ],
        "events": ["intake"],
    }


def make_planner(model: Runnable):
    """planner 节点工厂：产计划 JSON（LLM 合法位置①，L5.1 原样）。"""

    async def planner(state: ExpenseState) -> dict:
        rejections = state.get("plan_rejections") or []
        extra: list[dict] = []
        if rejections:
            previous_plan = state["messages"][-1].content  # 最新一条 AI 消息 = 上一版计划原文
            extra.append({"role": "user", "content": prompts.replan_instruction(previous_plan, rejections[-1])})
        response = await model.ainvoke(state["messages"] + extra)
        return {"messages": extra + [response], "events": ["planner"]}

    return planner


async def plan_gate(state: ExpenseState) -> dict:
    """校验门（纯代码，非 LLM，L5.1 原样）。"""
    outcome = validate_plan(state["messages"][-1].content)
    if isinstance(outcome, PlanRejection):
        return {"plan_rejections": [outcome], "events": [f"plan.rejected:{outcome.reason_code}"]}
    return {"plan": outcome, "events": ["plan.approved"]}


def route_after_gate(state: ExpenseState) -> Literal["executor", "planner", "escalate"]:
    """条件边三分支（L5.1 原样）：valid→executor / invalid 未超限→planner / 超限→escalate。"""
    if state.get("plan") is not None:
        return "executor"
    if len(state.get("plan_rejections") or []) <= MAX_REPLANS:
        return "planner"
    return "escalate"


async def executor_node(state: ExpenseState) -> dict:
    """执行器节点：确定性步进的薄包装（L5.1 原样）。"""
    candidate = state.get("plan")
    assert candidate is not None
    return {"results": execute_plan(candidate), "events": ["executor"]}


def make_drafter(model: Runnable):
    """drafter 节点工厂：依取数结果产建议单（LLM 合法位置②，L5.1 原样——回环再入时
    messages 里多了驳回留言，它读到的是全量历史：无状态协议没变，变的是历史更长）。"""

    async def drafter(state: ExpenseState) -> dict:
        user = {"role": "user", "content": prompts.drafter_instruction(state["results"])}
        response = await model.ainvoke(state["messages"] + [user])
        advice = Advice.model_validate_json(response.content.strip())
        return {"messages": [user, response], "advice": advice, "events": ["drafter"]}

    return drafter


def content_hash(advice: Advice, total_cents: int) -> str:
    """被审内容的指纹（A6「审批与被审内容版本绑定」）：建议单 + 总额的规范序列化 sha256。

    同一单据重生成出不同建议单（decision/reason/remaining 任一变）→ hash 变 → 新审批单；
    内容不变 hash 不变——「批的是哪一版」由它锁定，不是靠单据号。
    """
    payload = json.dumps(
        {"advice": advice.model_dump(), "total_cents": total_cents}, ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


async def submit(state: ExpenseState, config: RunnableConfig) -> dict:
    """送审门（L5.2 换芯）：interrupt() 在这里把图摁停，等一个审批决策。

    第一次执行：interrupt(payload) 抛 GraphInterrupt → pregel 捕获 → 图暂停、审批单
    payload 随状态落盘（L3.3 的抛-捕-落盘）→ 下面的 return 一行没跑到。
    恢复重执行：本节点从头重跑（重放），interrupt() 返回 Command(resume=) 带来的决策：
    - approve → sent=True 收口 END（once/always/规则自动批准都走这里）；
    - reject  → 驳回留言作为 user 消息回喂 drafter 重生成（A1/A24），新建议单回到本门——
      内容变了 content_hash 变，是新一单（A6）。

    重放幂等性（L3.3 铁律①）：interrupt 之前的 payload 组装全是纯函数（claim_view 纯读取
    不记 CALL_LOG、content_hash 确定性）——重放一遍代价是重算一次指纹，安全。
    """
    advice = state.get("advice")
    assert advice is not None  # 路由保证：drafter 之后才会到本节点（NotRequired 键的守门读法）
    candidate = state.get("plan")
    assert candidate is not None  # 路由保证：只有过门的合法计划才会走到本节点（NotRequired 键的守门读法）
    view = mock_tools.claim_view(state["claim_id"])  # 纯读取：部门是审批规则的匹配维度
    run_id = (config.get("configurable") or {}).get("thread_id", "")  # thread_id 即 run_id：审批单的归属凭证
    payload = {
        "run_id": run_id,
        "claim_id": advice.claim_id,
        "dept": view["dept"],
        "total_cents": candidate.claim_total_cents,
        "advice": {"decision": advice.decision, "reason": advice.reason, "remaining_cents": advice.remaining_cents},
        "content_hash": content_hash(advice, candidate.claim_total_cents),
    }
    decision = interrupt(payload)
    if decision.get("action") == "reject":
        message = decision.get("message") or DEFAULT_REJECT_FEEDBACK
        return {
            "messages": [{"role": "user", "content": prompts.approval_feedback_instruction(advice, message)}],
            "approval_rejects": [{"message": message}],
            "events": ["submit.rejected"],
        }
    return {"sent": True, "events": ["submit.approved"]}


def route_after_submit(state: ExpenseState) -> str:
    """送审门后的三分支：approve→END / reject 未超限→drafter 回环 / reject 超限→escalate。

    返回值里混着 langgraph 的 END 常量（LiteralString，非字面量），返回注解只能放宽到 str。

    驳回次数含当前这次（状态已含 submit 的写入）：第 1/2 次驳回回环重生成，
    第 3 次驳回时已用满 2 次回环 → 哨兵收口，不送审。
    """
    if state.get("sent"):
        return END
    if len(state.get("approval_rejects") or []) <= MAX_APPROVAL_LOOPS:
        return "drafter"
    return "escalate"


async def escalate(state: ExpenseState) -> dict:
    """双哨兵收尾（L5.1 扩展）：哪条环烧完，用哪个枚举码——审计看到码就知道烧在哪。

    remaining_cents=0 表示「未取到」；sent=False（不送审，转人工）——两种收口同型
    （Advice），下游审批 API 只有一个出口类型（L5.1 的契约原样）。
    """
    if len(state.get("approval_rejects") or []) > MAX_APPROVAL_LOOPS:
        reason = ESCALATE_APPROVAL_REASON
    else:
        reason = ESCALATE_REASON
    advice = Advice(
        claim_id=state["claim_id"],
        decision="ESCALATE",
        reason=reason,
        remaining_cents=0,
    )
    return {"advice": advice, "sent": False, "events": ["escalate"]}


def build_graph(model: Runnable, checkpointer: BaseCheckpointSaver[str] | None = None) -> CompiledStateGraph:
    """装配固定拓扑：七节点 + 两个三分支条件边（L5.1 的形状 + submit 出口换分支）。

    checkpointer 是 L5.2 的必接项：interrupt 的暂停点要落盘，不接就 RuntimeError
    （L3.3 铁律②）。
    """
    builder = StateGraph(ExpenseState)
    builder.add_node("intake", intake)
    builder.add_node("planner", make_planner(model))
    builder.add_node("plan_gate", plan_gate)
    builder.add_node("executor", executor_node)
    builder.add_node("drafter", make_drafter(model))
    builder.add_node("submit", submit)
    builder.add_node("escalate", escalate)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", "planner")
    builder.add_edge("planner", "plan_gate")
    builder.add_conditional_edges("plan_gate", route_after_gate)  # 三分支：executor | planner | escalate
    builder.add_edge("executor", "drafter")
    builder.add_edge("drafter", "submit")
    builder.add_conditional_edges("submit", route_after_submit)  # 三分支：END | drafter（回环）| escalate
    builder.add_edge("escalate", END)
    return builder.compile(checkpointer=checkpointer)


def initial_state(claim_id: str) -> dict:
    """入口状态：claim_id 进场，消息史从空开始（L5.1 原样 + approval_rejects 空账本）。"""
    return {
        "claim_id": claim_id,
        "messages": [],
        "plan_rejections": [],
        "results": {},
        "events": [],
        "approval_rejects": [],
    }


def run_config(run_id: str) -> RunnableConfig:
    """审批挂起/恢复的取货凭证：thread_id=run_id（L3.3 thread_config 的产品化改名）。"""
    return {"configurable": {"thread_id": run_id}, "recursion_limit": RECURSION_LIMIT}


# ---- checkpointer 接线（L3.3 demo.open_saver 的同款，serde 白名单换成 L5.2 的状态类型）----


@asynccontextmanager
async def open_saver(db_path: str) -> AsyncIterator[AsyncSqliteSaver]:
    """打开（或创建）checkpoint 数据库——@asynccontextmanager 是 L1.7 的 with 语义复课。

    aiosqlite 连接不关进程会挂住（AsyncSqliteSaver 文档原文警告，L3.3 踩过）；serde 白名单：
    状态里的 plan / advice 是 Pydantic 对象（连带三个步型子类），整只序列化进 db、恢复时
    import 回来——跨 invoke 读回的类型要锁死（对照 Java 反序列化白名单）。
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[Advice, Plan, PlanRejection, FetchClaimStep, FetchBudgetStep, VerifyInvoiceStep]
    )
    async with aiosqlite.connect(db_path) as conn:
        yield AsyncSqliteSaver(conn, serde=serde)
