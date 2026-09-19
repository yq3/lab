"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

import ex3_audit as ex3


def test_trajectory_at_pause(tmp_path) -> None:  # noqa: ANN001 -- pytest fixture
    db = str(tmp_path / "audit.sqlite3")
    thread_id = asyncio.run(ex3.pause_claim(db))

    async def scene() -> ex3.Trajectory:
        return ex3.rebuild(await ex3.fetch_history(db, thread_id))

    traj = asyncio.run(scene())
    assert traj.nodes_ran == ("reviewer", "tools", "reviewer")  # human_gate 还没跑成
    assert traj.paused_at == ("human_gate",)
    assert traj.supersteps == 3
    assert traj.interrupt_payload == {"claim_id": "CLM-2026-0003", "reason": "REJECT:INVALID_AMOUNT"}


def test_trajectory_after_resume(tmp_path) -> None:  # noqa: ANN001
    db = str(tmp_path / "audit.sqlite3")
    thread_id = asyncio.run(ex3.pause_claim(db))
    asyncio.run(ex3.resume_claim(db, thread_id, "deny"))

    async def scene() -> tuple[ex3.Trajectory, list[str]]:
        snaps = await ex3.fetch_history(db, thread_id)
        return ex3.rebuild(snaps), snaps[0].values["events"]  # snaps[0] 是最新快照

    traj, events = asyncio.run(scene())
    assert traj.nodes_ran == ("reviewer", "tools", "reviewer", "human_gate", "reviewer", "finalize")
    assert traj.paused_at == ()
    assert traj.supersteps == 6
    assert traj.interrupt_payload is None


def test_events_stream_agrees_with_rebuilt_nodes(tmp_path) -> None:  # noqa: ANN001
    """交叉验证：events 审计流水（reducer 口径）与 next 重建（快照口径）必须一致。"""
    db = str(tmp_path / "cross.sqlite3")
    thread_id = asyncio.run(ex3.pause_claim(db))

    async def at_pause() -> tuple[ex3.Trajectory, list[str]]:
        snaps = await ex3.fetch_history(db, thread_id)
        return ex3.rebuild(snaps), snaps[0].values["events"]

    traj, events = asyncio.run(at_pause())
    assert list(traj.nodes_ran) == events

    asyncio.run(ex3.resume_claim(db, thread_id, "approve"))

    async def after_resume() -> tuple[ex3.Trajectory, list[str]]:
        snaps = await ex3.fetch_history(db, thread_id)
        return ex3.rebuild(snaps), snaps[0].values["events"]

    traj, events = asyncio.run(after_resume())
    assert list(traj.nodes_ran) == events
    assert events == ["reviewer", "tools", "reviewer", "human_gate", "reviewer", "finalize"]
