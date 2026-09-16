# 练习 2 参考答案（solution/ 覆盖 exercises/ 后跑验收全绿；与骨架的差异只在 TODO 区）
"""门入图：execute 节点的三出口接线与事件发射（讲义 graph.py 的同构迷你版）。

迷你图 drafter→submit(interrupt)→execute——drafter 是纯代码替身（第 n 轮产第 n 版
建议单，指纹 hash-v<n>），submit 换芯与审批回执（given），门本体直接复用讲义区的
gate.check_intent（真件，不是替身）。TODO 只在最该练的一处——三出口接线：

- ALLOW：账本记账（ledger.record）+ paid_cents + 事件流「gate.allowed」「payment.executed」；
- DENY：不付款，写 gate_reject（action/reason_code）+ 事件流「gate.denied:<码>」→ escalate 哨兵；
- PAUSE_FOR_REAUTH：同样不付款——取舍（讲义 §2.6）：升额改的是 Policy（合同），
  人升额后重开新 run，不是图内回环；事件流「gate.paused:<码>」；
- route_after_execute：付了 → END；没付 → escalate。

完成判据：uv run pytest exercises/test_ex2.py 全绿——6 个测试：
  链路①过门付款（paid_cents + payment.executed 事件 + 账本在账）；
  链路③紧合同超限（gate.paused 事件在账、未付款、终态 ESCALATE/升额码、账本零记录）；
  审批 hash 不匹配整单 DENY（approval_content_mismatch + GATE_DENIED 码）；
  clamp 合同裁剪放行（paid_cents 是裁剪值）；
  RECURSION_LIMIT 足够（驳回回环烧满的最坏链不炸）；
  meta：三出口的状态键形状（paid_cents / gate_reject 的键各在什么时候出现）。
"""

from __future__ import annotations

import operator
from typing import Annotated, NotRequired, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from gate import ApprovalRecord, LedgerView, PaymentIntent, Policy, check_intent

VENDOR = "王工"  # 收款方=提单人（讲义同款建模）
DEPT = "SALES"
MAX_APPROVAL_LOOPS = 2  # 审批回环封顶（讲义同款：第 3 次驳回烧满 → escalate）


class MiniState(TypedDict):
    """迷你图状态：起草轮数（回环取证）+ 送审标志 + 审批回执 + 门的账。"""

    drafts: Annotated[list[int], operator.add]
    events: Annotated[list[str], operator.add]
    sent: NotRequired[bool]
    approval: NotRequired[dict]
    gate_reject: NotRequired[dict]
    paid_cents: NotRequired[int]


class MemoryLedger:
    """（given）进程内账本：record 记付款、payments_for 读当日已付——讲义 VolatileLedger 同款。"""

    def __init__(self) -> None:
        self._rows: list[dict] = []

    def payments_for(self) -> tuple[dict, ...]:
        return tuple(self._rows)

    def record(self, payment: dict) -> None:
        self._rows.append(dict(payment))


async def drafter(state: MiniState) -> dict:
    """（given）起草员替身：第 n 轮产第 n 版建议单（内容指纹 hash-v<n>——A6 的替身口径）。"""
    version = len(state.get("drafts") or []) + 1
    return {"drafts": [version], "events": [f"drafter:v{version}"]}


def _content_hash(state: MiniState) -> str:
    """（given）当前草稿的内容指纹：hash-v<最新轮次>——submit 与 execute 各自调，口径同源。"""
    drafts = state.get("drafts") or []
    return f"hash-v{drafts[-1]}"


async def submit(state: MiniState) -> dict:
    """（given）送审门：interrupt 摁停；approve 写审批回执（A7 的输入），reject 回喂回环。

    恢复载荷可带 content_hash（审批服务侧的单据指纹——中间层记错版本时与执行侧
    重算不符，门当场 DENY）；缺省回落本单自算值（自洽）。
    """
    payload = {"run_id": "mini", "total_cents": 8_800, "content_hash": _content_hash(state)}
    decision = interrupt(payload)
    if decision.get("action") == "reject":
        message = decision.get("message") or "驳回：请复核后重新起草"
        return {"events": [f"submit.rejected:{message[:12]}"]}
    return {
        "sent": True,
        "approval": {
            "decision": "CONFIRMED",
            "content_hash": str(decision.get("content_hash") or payload["content_hash"]),
        },
        "events": ["submit.approved"],
    }


def route_after_submit(state: MiniState) -> str:
    """（given）送审门后三分支：批准→execute；驳回未烧满→drafter；烧满→escalate。"""
    if state.get("sent"):
        return "execute"
    rejections = [e for e in state.get("events") or [] if e.startswith("submit.rejected")]
    if len(rejections) <= MAX_APPROVAL_LOOPS:
        return "drafter"
    return "escalate"


def make_execute(policy: Policy, ledger: MemoryLedger, amount_cents: int):
    """execute 节点工厂：装配意图 → 复用讲义的 gate.check_intent →（你的 TODO）三出口。"""

    async def execute(state: MiniState) -> dict:
        approval_raw = state.get("approval")
        assert approval_raw is not None  # 路由保证：submit 批准后才会到本节点
        intent = PaymentIntent(
            claim_id="CLM-MINI-0001",
            vendor=VENDOR,
            dept=DEPT,
            category="迷你演示",
            amount_cents=amount_cents,
            content_hash=_content_hash(state),  # A6：执行侧重算指纹，不信在途状态
        )
        verdict = check_intent(
            policy,
            intent,
            _record_of(approval_raw),
            LedgerView(today="2026-09-16", payments=ledger.payments_for()),
        )
        if verdict.action == "ALLOW":
            paid = verdict.clamp_cents if verdict.clamp_cents is not None else amount_cents
            ledger.record(
                {
                    "claim_id": "CLM-MINI-0001",
                    "vendor": VENDOR,
                    "dept": DEPT,
                    "amount_cents": amount_cents,
                    "paid_cents": paid,
                }
            )
            return {"paid_cents": paid, "events": ["gate.allowed", "payment.executed"]}
        gate_reject = {"action": verdict.action, "reason_code": verdict.reason_code}
        stream = "gate.denied" if verdict.action == "DENY" else "gate.paused"
        return {"gate_reject": gate_reject, "events": [f"{stream}:{verdict.reason_code}"]}

    return execute


def _record_of(approval_raw: dict) -> ApprovalRecord:
    """（given）state 里的审批回执 → gate.ApprovalRecord（A7 二次校验的输入）。"""
    return ApprovalRecord(
        ticket_id="tkt-mini",
        decision=str(approval_raw.get("decision", "")),
        content_hash=str(approval_raw.get("content_hash", "")),
        approved_at="t0",
    )


def route_after_execute(state: MiniState) -> str:
    """执行门后的两分支（参考答案）：付了 → END；没付 → escalate。"""
    if state.get("paid_cents") is not None:
        return END
    return "escalate"


async def escalate(state: MiniState) -> dict:
    """（given）哨兵：门拦下 → ESCALATE，DENY 与 PAUSE 分码（讲义第三哨兵的同构迷你版）。"""
    gate_reject = state.get("gate_reject") or {"action": "DENY", "reason_code": "unknown"}
    reason = "REJECT:GATE_DENIED" if gate_reject["action"] == "DENY" else "REJECT:GATE_REAUTH_REQUIRED"
    return {"events": [f"escalate:{reason}"]}


def build(
    checkpointer: BaseCheckpointSaver[str],
    policy: Policy,
    ledger: MemoryLedger | None = None,
    amount_cents: int = 8_800,
) -> CompiledStateGraph:
    """装配（given）：drafter → submit ─(approve)→ execute ─(付/没付)→ END / escalate。"""
    builder = StateGraph(MiniState)
    builder.add_node("drafter", drafter)
    builder.add_node("submit", submit)
    builder.add_node("execute", make_execute(policy, ledger or MemoryLedger(), amount_cents))
    builder.add_node("escalate", escalate)
    builder.add_edge(START, "drafter")
    builder.add_edge("drafter", "submit")
    builder.add_conditional_edges("submit", route_after_submit)
    builder.add_conditional_edges("execute", route_after_execute)
    builder.add_edge("escalate", END)
    return builder.compile(checkpointer=checkpointer)
