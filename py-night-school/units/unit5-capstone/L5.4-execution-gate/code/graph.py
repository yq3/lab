"""L5.4 图本体：四层合体——L5.1 图 + L5.2 审批换芯 + L5.3 事件层 + 本课执行门。

合并声明（对版纪律「合理差异就地注释」）：本文件以 **L5.2 的图**为骨架（submit 换芯与
拒绝回环是拓扑主体），并入 **L5.3 的事件层**（_with_events 旁挂 + AuditedModel），再加
**本课的执行门**（submit 批准后不再直接 END，改道 execute 节点过门）。逐课差异：
- L5.1 部分：intake / planner / plan_gate / route_after_gate / executor_node / drafter
  六个节点函数体与 L5.1（=L5.2=L5.3）逐字相同；
- L5.2 部分：submit 的 interrupt 换芯 + 拒绝回环 + 双哨兵 + open_saver/run_config——
  差异只有「批准后写审批回执进 state」与「approve 出口从 END 改道 execute」；
- L5.3 部分：_with_events 旁挂事件发射 + AuditedModel 装配 + extra_stamp 道具——
  除新增 _execute_events 外与 L5.3 相同；
- L5.4 部分：make_execute（门节点工厂）+ route_after_execute + 第三哨兵分码 +
  PaymentLedger（当日账本 = 事件表的日历聚合投影）。

拓扑签名必变（L5.3 图版本绑定的活教材）：比 L5.3 多了 execute 节点与两条出边——
同一单据在 L5.4 图下的 run_key 与 L5.3 不同，旧 checkpoint 不可续（讲义 §3 第三链路）。

固定拓扑（StateGraph，静态可审计）：

    START → intake → planner → plan_gate ─(valid)→ executor → drafter → submit → execute ─(ALLOW)→ END
                        ↑ └─(invalid 未超限)┘                                        ├─(DENY/PAUSE)→ escalate → END
                        └──(超限)──→ escalate → END    submit ─(reject 未超限)→ drafter（回环）
                                                            └─(reject 超限)→ escalate

「LLM 影响力终止于建议」的最终形态：planner/drafter 两个 LLM 节点之外全是确定性代码——
plan_gate 校验、executor 步进、submit 审批、**execute 执行门**、escalate 哨兵。
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import operator
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal, NotRequired, TypedDict

import aiosqlite
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

import eventstore
import gate
import mock_tools
import prompts
from advice import Advice
from audit_cache import AuditedModel, DecisionCache
from eventstore import RunRecorder
from executor import execute_plan
from plan import FetchBudgetStep, FetchClaimStep, Plan, PlanRejection, VerifyInvoiceStep, validate_plan

MAX_REPLANS = 2  # 重规划封顶：planner 最多被叫 1+2 次，第 3 次拒绝即超限转 escalate（L5.1 原样）
MAX_APPROVAL_LOOPS = 2  # 审批回环封顶：驳回留言最多回喂 2 次，第 3 次驳回即超限转 escalate（L5.2 原样）
ESCALATE_REASON = "REJECT:PLAN_REPLANS_EXCEEDED"  # 重规划烧完的枚举风格结论码（L5.1 原样）
ESCALATE_APPROVAL_REASON = "REJECT:APPROVAL_LOOPS_EXCEEDED"  # 审批回环烧完（L5.2 原样）
ESCALATE_GATE_REASON = "REJECT:GATE_DENIED"  # L5.4：门结构性拒绝（DENY）——不可解析/审批缺位/指纹不符/黑名单
ESCALATE_REAUTH_REASON = "REJECT:GATE_REAUTH_REQUIRED"  # L5.4：门定量暂停（PAUSE）——升额后重开新 run
DEFAULT_REJECT_FEEDBACK = "审批人驳回且未留留言：请复核建议单后重新起草。"  # L5.2 原样
# 「今天」的注入缺省（ISO 日期）——门与账本的日历窗口都从装配参数来，不取系统时钟（§5 陷阱）。
DEFAULT_TODAY = "2026-09-16"
# superstep 预算：最坏链 intake + 3×(planner+gate) + executor + 3×(drafter+submit) + execute + escalate
# = 16 步；L5.2 的 20 在加门后只剩 4 步余量，顺手放大到 24（留 8 步——docstring 声明的放大理由）。
RECURSION_LIMIT = 24


def merge_results(old: dict, new: dict) -> dict:
    """results 键的合并 reducer：dict 版的 Annotated[list, operator.add]（L5.1 原样）。"""

    return {**old, **new}


class ExpenseState(TypedDict):
    """图状态：节点间唯一的通信媒介（L5.2 全部键 + L5.4 新增三个执行半边的键）。

    - messages / plan / plan_rejections / results / advice / events / sent /
      approval_rejects：L5.2 原样；
    - approval：审批回执（submit 批准后写；execute 的 A7 二次校验读它——decision 必须是
      CONFIRMED、content_hash 必须与执行时重算的指纹一致）；
    - gate_result：门裁决摘要（execute 写：action/reason_code/detail/clamp_cents/amount_cents）；
    - gate_reject：门未放行标记（execute 写：DENY/PAUSE 的 action+reason_code——escalate
      第三哨兵的分码依据。注意：TypedDict 漏声明的键会被图**静默丢弃**，这个键就是因此
      踩过坑后补的——schema 是合同，不是文档）；
    - paid_cents：实付金额（ALLOW 后才有；clamp 时是裁剪值——paid ≤ amount 只缩不放）。
    """

    claim_id: str
    messages: Annotated[list, add_messages]
    plan: NotRequired[Plan]
    plan_rejections: Annotated[list[PlanRejection], operator.add]
    results: Annotated[dict[str, dict], merge_results]
    advice: NotRequired[Advice]
    events: Annotated[list[str], operator.add]
    sent: NotRequired[bool]
    approval_rejects: Annotated[list[dict], operator.add]
    approval: NotRequired[dict]
    gate_result: NotRequired[dict]
    gate_reject: NotRequired[dict]
    paid_cents: NotRequired[int]


# ---- 节点：纯「读状态 → 返回更新」的函数（以下与 L5.1/L5.2 逐字相同）----


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
    """drafter 节点工厂：依取数结果产建议单（LLM 合法位置②，L5.1/L5.2 原样）。"""

    async def drafter(state: ExpenseState) -> dict:
        user = {"role": "user", "content": prompts.drafter_instruction(state["results"])}
        response = await model.ainvoke(state["messages"] + [user])
        advice = Advice.model_validate_json(response.content.strip())
        return {"messages": [user, response], "advice": advice, "events": ["drafter"]}

    return drafter


def content_hash(advice: Advice, total_cents: int) -> str:
    """被审内容的指纹（A6「审批与被审内容版本绑定」，L5.2 原样）：建议单 + 总额的规范序列化 sha256。

    同一单据重生成出不同建议单（decision/reason/remaining 任一变）→ hash 变 → 新审批单；
    内容不变 hash 不变——「批的是哪一版」由它锁定，不是靠单据号。
    L5.4 的执行门在 execute 节点**重算**它（不信在途状态）——审批单上的指纹与重算值
    逐字比对，就是 A6+A7 的二次校验。
    """
    payload = json.dumps(
        {"advice": advice.model_dump(), "total_cents": total_cents}, ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


async def submit(state: ExpenseState, config: RunnableConfig) -> dict:
    """送审门（L5.2 换芯 + L5.4 回执）：interrupt() 把图摁停，等一个审批决策。

    第一次执行：interrupt(payload) 抛 GraphInterrupt → 图暂停、审批单 payload 随状态
    落盘（L3.3 的抛-捕-落盘）。恢复重执行：本节点从头重跑（重放），interrupt() 返回
    Command(resume=) 带来的决策：
    - approve → 写**审批回执**进 state（decision=CONFIRMED + content_hash + approved_at，
      L5.4 新增——execute 的 A7 二次校验读它）→ 改道 execute 过门；
    - reject  → 驳回留言作为 user 消息回喂 drafter 重生成（A1/A24），新建议单回到本门。

    回执的 content_hash：优先取回复载荷里的（审批服务侧的单据指纹——中间层被绕过/记错
    版本时与执行侧重算值不符，门当场 DENY，A7 的威胁模型）；缺省回落本单自算值
    （L5.2 形态的回复不带指纹，自洽）。
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
    return {
        "sent": True,
        "approval": {
            "ticket_id": str(decision.get("ticket_id", "")),
            "decision": "CONFIRMED",
            "content_hash": str(decision.get("content_hash") or payload["content_hash"]),
            "approved_at": str(decision.get("approved_at", "")),
        },
        "events": ["submit.approved"],
    }


def route_after_submit(state: ExpenseState) -> str:
    """送审门后的三分支（L5.4 改道）：approve→**execute** / reject 未超限→drafter / 超限→escalate。

    L5.2 的 approve 出口是 END——批了就完了；L5.4 在 END 前面装了执行门：批准是授权，
    付款还得过门（A7 纵深防御——决策层批了不算数，执行出口再查一次）。
    """
    if state.get("sent"):
        return "execute"
    if len(state.get("approval_rejects") or []) <= MAX_APPROVAL_LOOPS:
        return "drafter"
    return "escalate"


# ---- L5.4 执行门：批准之后、付款之前，纯函数检查链接管 ----


class PaymentLedger:
    """当日账本（事件表即账本）：payment.executed 事件的日历聚合投影。

    聚合键 ``ledger:<yyyy-mm-dd>``——「今天已付了什么」跨 run 共享（限额/频次是跨单的
    合同，不是单 run 的私事）；读 = 该聚合的 payment.executed 投影，写 = append 一条
    （append-only：账本没有改法，付款事实发生了就只能追加）。
    """

    def __init__(self, store: eventstore.EventStore) -> None:
        self._store = store

    @staticmethod
    def day_aggregate(today: str) -> str:
        """日历聚合键：ledger:<yyyy-mm-dd>（today 由装配方注入——门不取系统时钟）。"""
        return f"ledger:{today}"

    def payments_for(self, today: str) -> tuple[dict, ...]:
        """当日已付清单（按 seq 升序——账本的读法就是事件的投影）。"""
        rows = self._store.events_for(self.day_aggregate(today), type="payment.executed")
        return tuple(row["payload"] for row in rows)

    def record(self, today: str, payment: dict) -> None:
        """append 一笔已付（不可改、不可删——想「撤销」只能再记一笔冲销事件）。"""
        self._store.append(self.day_aggregate(today), "payment.executed", payment)


class VolatileLedger(PaymentLedger):
    """进程内挥发性账本（未注入事件表时的缺省）：付款事实只活在本段执行里。

    L5.2 形态（不挂审计层）的兼容缺省——限额/频次在段内成立、不跨段记账；
    要跨 run 的账本，注入 EventStore 背书的 PaymentLedger（demo_final / 里程碑形态）。
    """

    def __init__(self) -> None:
        self._by_day: dict[str, list[dict]] = {}

    def payments_for(self, today: str) -> tuple[dict, ...]:
        return tuple(self._by_day.get(today, ()))

    def record(self, today: str, payment: dict) -> None:
        self._by_day.setdefault(today, []).append(dict(payment))


def make_execute(policy: gate.Policy, ledger: PaymentLedger, today: str):
    """execute 节点工厂（本课核心②的接线处）：装配意图 → 过门 → 三出口。

    - 意图装配全在节点内重算（claim_view 纯读取、content_hash 重算）——不信任在途
      state 的任何「应该是」；
    - ALLOW：付款落账本（paid_cents 记实付，clamp 时为裁剪值）→ 终态保持送审结论；
    - DENY / PAUSE：不付款，写 gate_reject 交 escalate 第三哨兵分码收口
      （取舍见讲义 §2：PAUSE 的「重新授权」在产品里是人升额后**重开新 run**——
      升额改的是 Policy（合同），不是图内回环能解决的事）。
    """

    async def execute(state: ExpenseState) -> dict:
        advice = state.get("advice")
        candidate = state.get("plan")
        approval_raw = state.get("approval")
        assert advice is not None and candidate is not None and approval_raw is not None  # 路由保证（守门读法）
        record = gate.ApprovalRecord(
            ticket_id=str(approval_raw.get("ticket_id", "")),
            decision=str(approval_raw.get("decision", "")),
            content_hash=str(approval_raw.get("content_hash", "")),
            approved_at=str(approval_raw.get("approved_at", "")),
        )
        view = mock_tools.claim_view(state["claim_id"])  # 纯读取（vendor=提单人：报销款收款方）
        intent = gate.PaymentIntent(
            claim_id=state["claim_id"],
            vendor=view["submitter"],
            dept=view["dept"],
            category=view["purpose"],  # 素材无科目字段：用途文本代位——门只校验非空齐全
            amount_cents=candidate.claim_total_cents,
            content_hash=content_hash(advice, candidate.claim_total_cents),  # A6：执行侧重算
        )
        ledger_view = gate.LedgerView(today=today, payments=ledger.payments_for(today))
        verdict = gate.check_intent(policy, intent, record, ledger_view)
        result = {
            "action": verdict.action,
            "reason_code": verdict.reason_code,
            "detail": verdict.detail,
            "clamp_cents": verdict.clamp_cents,
            "amount_cents": intent.amount_cents,
        }
        if verdict.action == "ALLOW":
            paid = verdict.clamp_cents if verdict.clamp_cents is not None else intent.amount_cents
            ledger.record(
                today,
                {
                    "claim_id": intent.claim_id,
                    "vendor": intent.vendor,
                    "dept": intent.dept,
                    "category": intent.category,
                    "amount_cents": intent.amount_cents,
                    "paid_cents": paid,
                },
            )
            return {"paid_cents": paid, "gate_result": result, "events": ["gate.allowed", "payment.executed"]}
        gate_reject = {"action": verdict.action, "reason_code": verdict.reason_code}  # escalate 分码依据
        stream = "gate.denied" if verdict.action == "DENY" else "gate.paused"
        return {"gate_result": result, "gate_reject": gate_reject, "events": [f"{stream}:{verdict.reason_code}"]}

    return execute


def route_after_execute(state: ExpenseState) -> str:
    """执行门后的两分支：付了→END；没付（DENY/PAUSE）→escalate 哨兵分码收口。"""
    if state.get("paid_cents") is not None:
        return END
    return "escalate"


async def escalate(state: ExpenseState) -> dict:
    """三哨兵收尾（L5.2 双哨兵 + L5.4 门哨兵）：哪条防线烧完/拦下，用哪个枚举码。

    分码顺序：门拦下（gate_reject 在场——最近的防线最先问）> 审批回环烧完 > 重规划烧完。
    remaining_cents=0 表示「未取到」；sent=False（不送审，转人工）——三种收口同型
    （Advice），下游审批 API 只有一个出口类型（L5.1 的契约原样）。
    """
    gate_reject = state.get("gate_reject")
    if gate_reject is not None:
        reason = ESCALATE_GATE_REASON if gate_reject["action"] == "DENY" else ESCALATE_REAUTH_REASON
    elif len(state.get("approval_rejects") or []) > MAX_APPROVAL_LOOPS:
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


async def audit_stamp(state: ExpenseState) -> dict:
    """L5.3 道具节点（extra_stamp=True 时进场）：纯拓扑占位——只往状态审计流水记一笔。

    它不产新事件类型（EVENT_TYPES 是封闭词汇表）：存在的意义就是让图形状 +1 节点，
    演示「改图→签名变→旧执行态作废」（L5.3 第三幕，L5.4 复用作签名变化的对照组）。
    """
    return {"events": ["audit_stamp"]}


# ---- L5.3 事件层：节点旁挂事件发射（AOP 审计切面的显式版）----
#
# 取舍（L5.3 §2.4 原样）：另一条路是节点内直接 store.append——那会让每个节点都
# import eventstore、都重复 (store, aggregate_id) 样板，节点从「纯函数」退化为
# 「带隐藏写副作用的函数」。选旁挂：节点本体零改动，事件从 (输入状态, 输出更新)
# 派生——审计层是可拆卸的旁路，不是改写。


EventPairs = list[tuple[str, dict]]
EventsOf = Callable[[ExpenseState, dict], EventPairs]


def _with_events(node, events_of: EventsOf, recorder: RunRecorder | None):
    """装饰节点：先跑本体，再把 (state, update) 翻译成事件逐条 emit。

    recorder=None 时原样返回节点——审计层可拆卸（默认不装，L5.2 语义一字不差）。
    config 透传：声明了 config 形参的节点（submit 读 thread_id）原样收到 config，
    单参节点（L5.1 系）不受影响——按本体的签名分派，包装层零假设。
    """

    if recorder is None:
        return node
    takes_config = "config" in inspect.signature(node).parameters

    @functools.wraps(node)
    async def wrapped(state: ExpenseState, config: RunnableConfig | None = None) -> dict:
        update = await (node(state, config) if takes_config else node(state))
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
    """submitted：送审完成（approve 路径；reject 回环不落——它还没「完成送审」）。"""
    if "sent" in update:
        return [("submitted", {"sent": True})]
    return []  # 驳回回环：submitted 未发生，事件表不记（审计只记事实，不记意图）


def _execute_events(state: ExpenseState, update: dict) -> EventPairs:
    """L5.4 门事件：gate.checked（每次过门一条裁决）+ payment.executed / gate.denied。

    - payment.executed 进 run 聚合（审计面）与日历聚合（账本面，节点内 ledger.record
      已写）——同一事实两种读法；
    - gate.denied 记**未放行**（DENY 与 PAUSE 都不付款——审计第一问是「付了没」，
      payload.action 再答「哪一态」；讲义 §2.6 讲这个事件语义的取舍）。
    """
    result: dict = dict(update["gate_result"])
    checked = ("gate.checked", {**result, "claim_id": state["claim_id"]})
    if "paid_cents" in update:
        view = mock_tools.claim_view(state["claim_id"])  # 纯读取（payload 带 vendor/dept 便于对账）
        payment = (
            "payment.executed",
            {
                "claim_id": state["claim_id"],
                "vendor": view["submitter"],
                "dept": view["dept"],
                "amount_cents": result["amount_cents"],
                "paid_cents": update["paid_cents"],
                "clamp_cents": result["clamp_cents"],
            },
        )
        return [checked, payment]
    denied = (
        "gate.denied",
        {
            "claim_id": state["claim_id"],
            "action": result["action"],
            "reason_code": result["reason_code"],
            "detail": result["detail"],
        },
    )
    return [checked, denied]


_escalate_events = _drafter_events  # 哨兵建议单同样落 advice.drafted（decision=ESCALATE 自证路径）


def build_graph(
    model: Runnable,
    recorder: RunRecorder | None = None,
    cache: DecisionCache | None = None,
    *,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    policy: gate.Policy | None = None,
    ledger: PaymentLedger | None = None,
    today: str = DEFAULT_TODAY,
    extra_stamp: bool = False,
) -> CompiledStateGraph:
    """装配固定拓扑：八节点 + 三个三分支条件边（L5.1 形状 + L5.2 送审分支 + L5.4 执行门）。

    签名是四课合流（讲义 §3 溯源表）：
    - L5.3 协议兼容：位置参数 (model, recorder, cache)——run_audited 的 GraphBuilder 原样可调；
    - L5.2 协议兼容：关键字 checkpointer=——审批服务的两段式 invoke 原样可调；
    - L5.4 新增：policy / ledger / today——执行门三件（缺省 = gate.DEFAULT_POLICY +
      挥发性账本 + 注入日期，L5.2/L5.3 行为在这个缺省下语义不变、只多过一道宽门）。
    """
    audited = cache is not None
    planner_model = AuditedModel(model, cache, recorder, node="planner") if audited else model
    drafter_model = AuditedModel(model, cache, recorder, node="drafter") if audited else model
    execute_node = make_execute(policy or gate.DEFAULT_POLICY, ledger or VolatileLedger(), today)
    builder = StateGraph(ExpenseState)
    builder.add_node("intake", _with_events(intake, _intake_events, recorder))
    builder.add_node("planner", make_planner(planner_model))
    builder.add_node("plan_gate", _with_events(plan_gate, _gate_events, recorder))
    builder.add_node("executor", _with_events(executor_node, _executor_events, recorder))
    builder.add_node("drafter", _with_events(make_drafter(drafter_model), _drafter_events, recorder))
    builder.add_node("submit", _with_events(submit, _submit_events, recorder))
    builder.add_node("execute", _with_events(execute_node, _execute_events, recorder))
    builder.add_node("escalate", _with_events(escalate, _escalate_events, recorder))
    if extra_stamp:
        builder.add_node("audit_stamp", audit_stamp)  # L5.3 道具：+1 节点，签名必变
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
    builder.add_conditional_edges("submit", route_after_submit)  # 三分支：execute | drafter（回环）| escalate
    builder.add_conditional_edges("execute", route_after_execute)  # 两分支：END | escalate（门哨兵）
    builder.add_edge("escalate", END)
    return builder.compile(checkpointer=checkpointer)


def initial_state(claim_id: str) -> dict:
    """入口状态：claim_id 进场，消息史从空开始（L5.2 原样——approval/gate_result/paid_cents
    是 NotRequired 覆盖键，第一个写它们的节点才让它们出现）。"""
    return {
        "claim_id": claim_id,
        "messages": [],
        "plan_rejections": [],
        "results": {},
        "events": [],
        "approval_rejects": [],
    }


def run_config(run_id: str) -> RunnableConfig:
    """审批挂起/恢复的取货凭证：thread_id=run_id（L5.2 原样，recursion_limit 换 L5.4 值）。"""
    return {"configurable": {"thread_id": run_id}, "recursion_limit": RECURSION_LIMIT}


# ---- checkpointer 接线（L3.3 demo.open_saver 的同款，serde 白名单与 L5.2 相同）----


def memory_saver() -> InMemorySaver:
    """进程内 checkpoint（demo 驱动器用）：serde 白名单与 open_saver 同款。

    缺省序列化器对 Pydantic 对象只**警告**不阻止——把白名单显式给齐，跨 invoke 读回的
    类型锁死（对照 Java 反序列化白名单），告警也一并消失。
    """
    return InMemorySaver(serde=_state_serializer())


def _state_serializer() -> JsonPlusSerializer:
    """状态序列化器（open_saver 与 memory_saver 共用白名单）。"""
    return JsonPlusSerializer(
        allowed_msgpack_modules=[Advice, Plan, PlanRejection, FetchClaimStep, FetchBudgetStep, VerifyInvoiceStep]
    )


@asynccontextmanager
async def open_saver(db_path: str) -> AsyncIterator[AsyncSqliteSaver]:
    """打开（或创建）checkpoint 数据库——@asynccontextmanager 是 L1.7 的 with 语义复课。

    aiosqlite 连接不关进程会挂住（AsyncSqliteSaver 文档原文警告，L3.3 踩过）；serde 白名单：
    状态里的 plan / advice 是 Pydantic 对象（连带三个步型子类），整只序列化进 db、恢复时
    import 回来——跨 invoke 读回的类型要锁死（对照 Java 反序列化白名单）。L5.4 新增的
    approval / gate_result / paid_cents 全是原生 dict/str/int，不需要进白名单。
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        yield AsyncSqliteSaver(conn, serde=_state_serializer())
