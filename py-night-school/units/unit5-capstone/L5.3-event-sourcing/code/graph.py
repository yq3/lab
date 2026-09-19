"""L5.1 副本 + L5.3 事件层（对版纪律「合理差异就地注释」）。

图本体零拓扑改动：七节点 + 三分支条件边 + escalate 终态与 L5.1 完全一致——
本课对 L5.1 的 graph.py 只做了两类加法，节点函数体一行未动：
1) 节点旁挂事件发射（_with_events）：recorder 进场时，把每个节点的
   (输入状态, 输出更新) 翻译成 append-only 事件（eventstore.EVENT_TYPES 的一等类型）；
   recorder=None（默认）时节点原样返回——L5.1 的行为与签名一字不差，
   L5.1 复制来的 test_demo / demo_trace 原样全绿就是回归证据。
2) extra_stamp 装配变体：drafter 与 submit 之间可加一个 audit_stamp 节点
   （讲义 §3 第三幕「改图→签名变→旧账作废」的道具；默认 False，拓扑与 L5.1 相同）。

固定拓扑（静态可审计——图形状能 diff、能签名，L5.1 的 step2_signature 原样适用）：

    START → intake → planner → plan_gate ─(valid)→ executor → drafter → submit → END
                        ↑ └─(invalid 且未超限：原因回喂重规划，MAX_REPLANS=2 封顶)
                        └─────────────────(超限)──────→ escalate → END（收尾哨兵，不送审）

状态键的合并/覆盖语义（L3.2 §2.3 的延续）：messages/events/plan_rejections 合并
（append-only 审计），results 用自定义 reducer 合并 dict（Annotated[list] 的 dict 版），
plan/advice/sent 覆盖（全图只有一个写者）。events（内存审计流水）与事件表
（eventstore 的持久审计流水）是同一事实的两种读法：前者随 state 生死，后者 append-only。
"""

from __future__ import annotations

import functools
import operator
from collections.abc import Callable
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

import mock_tools
import prompts
from advice import Advice
from audit_cache import AuditedModel, DecisionCache
from eventstore import RunRecorder
from executor import execute_plan
from plan import Plan, PlanRejection, validate_plan

MAX_REPLANS = 2  # 重规划封顶：planner 最多被叫 1+2 次，第 3 次拒绝即超限转 escalate
RECURSION_LIMIT = 12  # superstep 预算：最坏链 intake+3×(planner+gate)+escalate=8，余量充足
ESCALATE_REASON = "REJECT:PLAN_REPLANS_EXCEEDED"  # 超限哨兵的枚举风格结论码


def merge_results(old: dict, new: dict) -> dict:
    """results 键的合并 reducer：dict 版的 Annotated[list, operator.add]。

    本课 executor 仍是唯一写者、一次写全；合并语义的契约留给事件回放/审批回写
    ——「覆盖」语义会静默吞数据（§5 陷阱）。
    """

    return {**old, **new}


class ExpenseState(TypedDict):
    """图状态：节点间唯一的通信媒介。

    - messages：会话史（intake 的 system+brief、planner 的计划与重规划指令、drafter 的指令与建议单）；
    - plan / plan_rejections：计划半边的两个状态键——合法计划与拒绝原因（A29 显式状态键）；
    - results：executor 的取数产物（produces 键 → 工具返回），合并语义；
    - advice / sent：出口半边——建议单与送审标志，覆盖语义、单写者。
    """

    claim_id: str
    messages: Annotated[list, add_messages]
    plan: NotRequired[Plan]
    plan_rejections: Annotated[list[PlanRejection], operator.add]  # 拒绝原因逐次累积（回喂+审计）
    results: Annotated[dict[str, dict], merge_results]
    advice: NotRequired[Advice]
    events: Annotated[list[str], operator.add]  # 审计流水：节点名 + plan.approved/plan.rejected:<码>
    sent: NotRequired[bool]


# ---- 节点：纯「读状态 → 返回更新」的函数（以下七个节点与 L5.1 逐字相同）----


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
    """planner 节点工厂：产计划 JSON（LLM 合法位置①）。

    重规划轮：把最新拒绝原因与上一版计划作为 user 消息回喂（A29）——
    planner 不 bind_tools，工具选择在计划数据里，不在 function calling 协议里。
    """

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
    """校验门（纯代码，非 LLM）：判别联合分派 + 白名单 + 必填/金额校验。

    拒绝原因入 state（plan_rejections）而不是抛异常——它是回喂 planner 的任务数据；
    events 落 plan.rejected:<码>，审计流水与状态键同一口径。
    """
    outcome = validate_plan(state["messages"][-1].content)
    if isinstance(outcome, PlanRejection):
        return {"plan_rejections": [outcome], "events": [f"plan.rejected:{outcome.reason_code}"]}
    return {"plan": outcome, "events": ["plan.approved"]}


def route_after_gate(state: ExpenseState) -> Literal["executor", "planner", "escalate"]:
    """条件边三分支：路由决策是确定性代码（LLM 在这里零发言权）。

    valid → executor；invalid 且拒绝次数未超 MAX_REPLANS → 回 planner（原因已入 state）；
    超限 → escalate 收尾哨兵。拒绝次数含当前这次：第 1/2 次拒绝回去重规划，
    第 3 次拒绝时已用满 2 次重规划（replans = 拒绝次数 - 1 == MAX_REPLANS）→ 超限。
    """
    if state.get("plan") is not None:
        return "executor"
    if len(state.get("plan_rejections") or []) <= MAX_REPLANS:
        return "planner"
    return "escalate"


async def executor_node(state: ExpenseState) -> dict:
    """执行器节点：确定性步进的薄包装——本体在 executor.execute_plan（纯函数）。"""
    candidate = state.get("plan")
    assert candidate is not None  # 路由保证：只有过门的合法计划才会走到本节点（NotRequired 键的守门读法）
    return {"results": execute_plan(candidate), "events": ["executor"]}


def make_drafter(model: Runnable):
    """drafter 节点工厂：依取数结果产建议单（LLM 合法位置②）。

    出口纪律（L2.4/L3.2 延续）：LLM 只产 JSON 文本，Advice 的 schema 把守在边界上。
    """

    async def drafter(state: ExpenseState) -> dict:
        user = {"role": "user", "content": prompts.drafter_instruction(state["results"])}
        response = await model.ainvoke(state["messages"] + [user])
        advice = Advice.model_validate_json(response.content.strip())
        return {"messages": [user, response], "advice": advice, "events": ["drafter"]}

    return drafter


async def submit(state: ExpenseState) -> dict:
    """送审桩（stub）：只落「已送审」事件并置 sent=True。

    L5.2 把这里换成 interrupt()（L3.3 的抛-捕-落盘）+ 审批 API（REST 建单 + SSE 推送）——
    图形状不变、换芯不换壳，这就是静态拓扑给后续课留的稳定接口。
    """
    return {"sent": True, "events": ["submit"]}


async def escalate(state: ExpenseState) -> dict:
    """超限收尾哨兵：重规划烧完仍非法——不送审、转人工（拒绝静默降级，A16）。

    remaining_cents=0 表示「未取到」（取数从未发生），哨兵建议单与正常建议单同型
    （Advice），下游审批 API 只有一个出口类型。
    """
    advice = Advice(
        claim_id=state["claim_id"],
        decision="ESCALATE",
        reason=ESCALATE_REASON,
        remaining_cents=0,
    )
    return {"advice": advice, "sent": False, "events": ["escalate"]}


async def audit_stamp(state: ExpenseState) -> dict:
    """L5.3 道具节点（extra_stamp=True 时进场）：纯拓扑占位——只往状态审计流水记一笔。

    它不产新事件类型（EVENT_TYPES 是封闭词汇表）：存在的意义就是让图形状 +1 节点，
    演示「改图→签名变→旧执行态作废」（讲义 §3 第三幕）。
    """
    return {"events": ["audit_stamp"]}


# ---- L5.3 事件层：节点旁挂事件发射（AOP 审计切面的显式版）----
#
# 取舍（讲义 §2 展开）：另一条路是节点内直接 store.append——那会让每个节点都
# import eventstore、都重复 (store, aggregate_id) 样板，节点从「纯函数」退化为
# 「带隐藏写副作用的函数」。选旁挂：节点本体零改动（L5.1 行为与测试原样保留），
# 事件从节点的 (输入状态, 输出更新) 派生——审计层是可拆卸的旁路，不是改写。


EventPairs = list[tuple[str, dict]]
EventsOf = Callable[[ExpenseState, dict], EventPairs]


def _with_events(node, events_of: EventsOf, recorder: RunRecorder | None):
    """装饰节点：先跑本体，再把 (state, update) 翻译成事件逐条 emit。

    recorder=None 时原样返回节点——审计层可拆卸（默认不装，L5.1 语义一字不差）。
    """
    if recorder is None:
        return node

    @functools.wraps(node)
    async def wrapped(state: ExpenseState) -> dict:
        update = await node(state)
        for event_type, payload in events_of(state, update):
            recorder.emit(event_type, payload)
        return update

    return wrapped


def _intake_events(state: ExpenseState, update: dict) -> EventPairs:
    """intake.loaded：复述单据摘要（纯读取重取视图——claim_view 不记 CALL_LOG）。"""
    view = mock_tools.claim_view(state["claim_id"])
    return [
        (
            "intake.loaded",
            {
                "claim_id": view["id"],
                "dept": view["dept"],
                "total_cents": view["total_cents"],
                "invoice_ids": view["invoice_ids"],
            },
        )
    ]


def _gate_events(state: ExpenseState, update: dict) -> EventPairs:
    """plan.approved（计划全文进 payload，审计能看全）或 plan.rejected（原因码+细节）。"""
    if "plan" in update:
        plan: Plan = update["plan"]
        return [
            (
                "plan.approved",
                {
                    "claim_total_cents": plan.claim_total_cents,
                    "steps": [step.model_dump() for step in plan.steps],
                    "note": plan.note,
                },
            )
        ]
    rejection: PlanRejection = update["plan_rejections"][-1]
    return [("plan.rejected", {"reason_code": rejection.reason_code, "detail": rejection.detail})]


def _executor_events(state: ExpenseState, update: dict) -> EventPairs:
    """tool.called×N：按计划顺序每步一条——produces→result 进 payload，fold 靠它重建 results。"""
    plan = state.get("plan")
    assert plan is not None  # 与 executor_node 同款守门断言（路由保证可达前已置 plan）
    return [
        (
            "tool.called",
            {
                "step_id": step.step_id,
                "tool": step.tool,
                "produces": step.produces,
                "result": update["results"][step.produces],
            },
        )
        for step in plan.steps
    ]


def _drafter_events(state: ExpenseState, update: dict) -> EventPairs:
    """advice.drafted：建议单全文（escalate 哨兵路径同用本类型——ESCALATE 也是建议单）。"""
    return [("advice.drafted", update["advice"].model_dump())]


def _submit_events(state: ExpenseState, update: dict) -> EventPairs:
    return [("submitted", {"sent": True})]


_escalate_events = _drafter_events  # 哨兵建议单同样落 advice.drafted（decision=ESCALATE 自证路径）


def build_graph(
    model: Runnable,
    recorder: RunRecorder | None = None,
    cache: DecisionCache | None = None,
    *,
    extra_stamp: bool = False,
) -> CompiledStateGraph:
    """装配固定拓扑：七节点 + 条件边三分支 + escalate 终态（装配即部署，对照 L3.2）。

    L5.3 加的两个可选件（默认全关，L5.1 装配一字不差）：
    - recorder：进场则节点旁挂事件发射（intake/gate/executor/drafter/submit/escalate）；
    - cache：进场则 planner/drafter 的模型调用过审计层（AuditedModel——命中零请求，
      未命中落缓存+成本事件；llm.decision/cost.recorded 事件由审计层发，不经节点）。
    """
    audited = cache is not None
    planner_model = AuditedModel(model, cache, recorder, node="planner") if audited else model
    drafter_model = AuditedModel(model, cache, recorder, node="drafter") if audited else model
    builder = StateGraph(ExpenseState)
    builder.add_node("intake", _with_events(intake, _intake_events, recorder))
    builder.add_node("planner", make_planner(planner_model))
    builder.add_node("plan_gate", _with_events(plan_gate, _gate_events, recorder))
    builder.add_node("executor", _with_events(executor_node, _executor_events, recorder))
    builder.add_node("drafter", _with_events(make_drafter(drafter_model), _drafter_events, recorder))
    builder.add_node("submit", _with_events(submit, _submit_events, recorder))
    builder.add_node("escalate", _with_events(escalate, _escalate_events, recorder))
    if extra_stamp:
        builder.add_node("audit_stamp", audit_stamp)  # 第三幕道具：+1 节点，签名必变
    builder.add_edge(START, "intake")
    builder.add_edge("intake", "planner")
    builder.add_edge("planner", "plan_gate")
    builder.add_conditional_edges("plan_gate", route_after_gate)  # 三分支：executor | planner | escalate
    builder.add_edge("executor", "drafter")
    if extra_stamp:
        builder.add_edge("drafter", "audit_stamp")
        builder.add_edge("audit_stamp", "submit")
    else:
        builder.add_edge("drafter", "submit")
    builder.add_edge("submit", END)
    builder.add_edge("escalate", END)
    return builder.compile()


def initial_state(claim_id: str) -> dict:
    """入口状态：claim_id 进场，消息史从空开始（intake 写头两条）。

    合并语义的键显式给空初值（reducer 从空累积），覆盖语义的键（plan/advice/sent）
    是 NotRequired——第一个写它们的节点才让它们出现。
    """
    return {"claim_id": claim_id, "messages": [], "plan_rejections": [], "results": {}, "events": []}
