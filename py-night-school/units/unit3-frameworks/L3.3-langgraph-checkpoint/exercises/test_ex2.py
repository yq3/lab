"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio
from typing import Literal

import demo
import ex2_gate as ex2


async def _snapshot_of(db_path: str, thread_id: str):
    """用一张不跑模型的图读快照（aget_state 不调模型——URL 永远不会被请求）。"""
    async with demo.open_saver(db_path) as saver:
        graph = ex2.build_gate(demo.model_for_url("http://127.0.0.1:1"), saver)
        return await graph.aget_state(demo.thread_config(thread_id))


def test_escalate_pauses_at_human_gate_with_payload(tmp_path) -> None:  # noqa: ANN001
    db = str(tmp_path / "gate.sqlite3")
    result, thread_id = asyncio.run(ex2.start_side(db, "CLM-2026-0003"))
    assert "advice" not in result  # 图没跑完：finalize 没执行
    snapshot = asyncio.run(_snapshot_of(db, thread_id))
    assert snapshot.next == ("human_gate",)
    assert [i.value for i in snapshot.interrupts] == [{"claim_id": "CLM-2026-0003", "reason": "REJECT:INVALID_AMOUNT"}]


def test_approve_and_deny_produce_different_outcomes(tmp_path) -> None:  # noqa: ANN001
    cases: list[tuple[Literal["approve", "deny"], tuple[str, str, str]]] = [
        ("approve", ("APPROVE", "PASS", "approve")),
        ("deny", ("REJECT", "REJECT:HUMAN_DENIED", "deny")),
    ]
    for decision, expect in cases:
        db = str(tmp_path / f"gate-{decision}.sqlite3")
        _result, thread_id = asyncio.run(ex2.start_side(db, "CLM-2026-0003"))
        resumed = asyncio.run(ex2.resume_side(db, thread_id, decision))
        outcome = resumed["advice"]
        assert (outcome.decision, outcome.reason, outcome.human) == expect, decision
        assert outcome.remaining_cents == 40000
        assert resumed["events"] == ["reviewer", "tools", "reviewer", "human_gate", "reviewer", "finalize"]
        final = asyncio.run(_snapshot_of(db, thread_id))
        assert final.next == ()  # 恢复后跑完：无暂停点


def test_non_escalate_claim_never_pauses(tmp_path) -> None:  # noqa: ANN001
    db = str(tmp_path / "skip.sqlite3")
    result, thread_id = asyncio.run(ex2.start_side(db, "CLM-2026-0001"))
    snapshot = asyncio.run(_snapshot_of(db, thread_id))
    assert snapshot.next == () and not snapshot.interrupts  # 零暂停
    outcome = result["advice"]
    assert (outcome.decision, outcome.reason, outcome.human) == ("APPROVE", "PASS", "skipped")
