"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import operator
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import ex2_wire as ex2
from gate import Policy

CFG = RunnableConfig(configurable={"thread_id": "ex2"}, recursion_limit=12)


def generous() -> Policy:
    return Policy(
        max_single_cents=1_000_000, max_daily_total_cents=10_000_000, max_payments_per_day=50, vendor_blocklist=()
    )


def tight() -> Policy:
    return Policy(max_single_cents=5_000, max_daily_total_cents=1_000_000, max_payments_per_day=50, vendor_blocklist=())


async def _start(policy: Policy, ledger: ex2.MemoryLedger | None = None):
    """起跑到 submit 暂停；返回 (图实例, cfg, 审批 payload)。"""
    compiled = ex2.build(InMemorySaver(), policy, ledger)
    await compiled.ainvoke({"drafts": [], "events": []}, CFG)
    snapshot = await compiled.aget_state(CFG)
    assert snapshot.next == ("submit",), "clean 起跑应停在送审门"
    return compiled, dict(snapshot.interrupts[0].value)


async def _resume(compiled, decision: dict):
    await compiled.ainvoke(Command(resume=decision), CFG)
    return await compiled.aget_state(CFG)


async def test_link_one_allows_and_pays_on_ledger(tmp_path: Path) -> None:
    """链路①：批准 → 门 ALLOW → payment.executed 事件在账 + paid_cents + 账本落一笔。"""
    ledger = ex2.MemoryLedger()
    compiled, _payload = await _start(generous(), ledger)
    snapshot = await _resume(compiled, {"action": "approve"})
    values = snapshot.values
    assert snapshot.next == ()  # 跑到 END
    assert values["paid_cents"] == 8_800
    assert "payment.executed" in values["events"]
    assert "gate.allowed" in values["events"]
    assert len(ledger.payments_for()) == 1  # 账本在账
    (payment,) = ledger.payments_for()
    assert payment["paid_cents"] == 8_800 and payment["vendor"] == ex2.VENDOR


async def test_link_three_tight_policy_denies_without_payment(tmp_path: Path) -> None:
    """链路③：紧合同（单笔 5000）下 8800 的提案 → gate.paused 事件、终态 ESCALATE/升额码、零付款。"""
    ledger = ex2.MemoryLedger()
    compiled, _payload = await _start(tight(), ledger)
    snapshot = await _resume(compiled, {"action": "approve"})
    values = snapshot.values
    assert snapshot.next == ()  # 哨兵收口（经 escalate → END）
    assert "paid_cents" not in values  # 没付款
    assert "payment.executed" not in values["events"]
    assert any(e.startswith("gate.paused:single_over_limit") for e in values["events"]), values["events"]
    assert any(e.startswith("escalate:REJECT:GATE_REAUTH_REQUIRED") for e in values["events"])
    assert ledger.payments_for() == ()  # 账本零记录


async def test_wrong_approval_hash_denies_whole_payment(tmp_path: Path) -> None:
    """A6/A7 接线级：恢复载荷声称的指纹与执行侧重算不符 → 整单 DENY（GATE_DENIED 码）。"""
    ledger = ex2.MemoryLedger()
    compiled, _payload = await _start(generous(), ledger)
    snapshot = await _resume(compiled, {"action": "approve", "content_hash": "hash-v999"})
    values = snapshot.values
    assert "paid_cents" not in values
    assert any(e.startswith("gate.denied:approval_content_mismatch") for e in values["events"]), values["events"]
    assert any(e.startswith("escalate:REJECT:GATE_DENIED") for e in values["events"])
    assert ledger.payments_for() == ()


async def test_clamp_policy_pays_clamped_amount(tmp_path: Path) -> None:
    """clamp 合同：8800 裁到 5000 放行——paid_cents 是裁剪值（clamp 只缩不放）。"""
    ledger = ex2.MemoryLedger()
    clamped = Policy(
        max_single_cents=5_000,
        max_daily_total_cents=1_000_000,
        max_payments_per_day=50,
        vendor_blocklist=(),
        clamp_overruns=True,
    )
    compiled, _payload = await _start(clamped, ledger)
    snapshot = await _resume(compiled, {"action": "approve"})
    values = snapshot.values
    assert values["paid_cents"] == 5_000  # 裁剪后实付
    assert snapshot.next == ()
    (payment,) = ledger.payments_for()
    assert payment["paid_cents"] == 5_000


async def test_recursion_budget_survives_worst_chain(tmp_path: Path) -> None:
    """RECURSION_LIMIT 足够：驳回烧满（3 次驳回 = MAX_APPROVAL_LOOPS+1）的最坏链不炸。"""
    ledger = ex2.MemoryLedger()
    compiled, _payload = await _start(generous(), ledger)
    for _ in range(ex2.MAX_APPROVAL_LOOPS + 1):
        snapshot = await _resume(compiled, {"action": "reject"})
    assert snapshot.next == ()  # 哨兵收口而不是 GraphRecursionError
    rejected = [e for e in snapshot.values["events"] if e.startswith("submit.rejected")]
    assert len(rejected) == ex2.MAX_APPROVAL_LOOPS + 1  # 3 次驳回全部在账
    assert any(e.startswith("escalate:") for e in snapshot.values["events"])
    assert "paid_cents" not in snapshot.values  # 从未过门


async def test_state_key_shape_meta() -> None:
    """meta：三出口的状态键形状——MiniState 声明了 approval/gate_reject/paid_cents 三个键
    （漏声明的键会被图静默丢弃——讲义踩过才补的课）。"""
    from typing import get_type_hints

    hints = get_type_hints(ex2.MiniState, include_extras=True)
    assert {"approval", "gate_reject", "paid_cents"} <= set(hints)
    assert hints["events"].__metadata__ == (operator.add,)  # 事件流是合并语义
