"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

import ex2_replay as ex2


async def _take(log: ex2.EventLog, last_id: int, count: int, timeout: float = 2.0) -> list[dict]:
    """从订阅读恰好 count 条（读够就断开）；超时即失败——顺序与到达都在这里面。"""
    collected: list[dict] = []

    async def collect() -> list[dict]:
        async for record in log.subscribe(last_id):
            collected.append(record)
            if len(collected) >= count:
                break
        return collected

    return await asyncio.wait_for(collect(), timeout)


def _append_run(log: ex2.EventLog, names: list[str]) -> None:
    for name in names:
        log.append(name, {"seq": name})


def test_new_subscriber_replays_full_history() -> None:
    """A2：无人订阅期间发生的事件，新订阅者一条不丢（重订阅即重放）。"""
    log = ex2.EventLog()
    _append_run(log, ["run.started", "approval.requested", "approval.replied"])  # 没有任何订阅者在场
    records = asyncio.run(_take(log, last_id=0, count=3))
    assert [record["event"] for record in records] == ["run.started", "approval.requested", "approval.replied"]
    assert [record["id"] for record in records] == [1, 2, 3]  # id 从 1 单调自增
    assert records[1]["data"] == {"seq": "approval.requested"}  # data 原样重放


def test_last_event_id_truncates_replay() -> None:
    """断线续传：带 Last-Event-ID 重订阅只重放其后——之前收过的不再重发。"""
    log = ex2.EventLog()
    _append_run(log, ["e1", "e2", "e3", "e4"])
    records = asyncio.run(_take(log, last_id=2, count=2))
    assert [record["id"] for record in records] == [3, 4]
    assert [record["event"] for record in records] == ["e3", "e4"]


async def test_replay_then_live_without_gap_or_duplicate() -> None:
    """重放→实时无缝：每条恰好一次、顺序与事件表一致；断开后订阅注销。"""
    log = ex2.EventLog()
    _append_run(log, ["e1", "e2"])  # 订阅前的历史
    task = asyncio.create_task(_take(log, last_id=0, count=4))
    await asyncio.sleep(0)  # 让订阅注册发生（生成器体的同步段跑完）
    _append_run(log, ["e3", "e4"])  # 订阅后的实时事件
    records = await task
    assert [record["id"] for record in records] == [1, 2, 3, 4]  # 重放在前、实时在后，无缝无重
    assert [record["event"] for record in records] == ["e1", "e2", "e3", "e4"]
    await asyncio.sleep(0)
    assert log._subscribers == []  # 断开（读够 count 后不再迭代）即注销


async def test_two_concurrent_subscribers_same_order() -> None:
    """两个并发订阅者（重连的老工作台 + 新工作台）：同序收到同一条流。"""
    log = ex2.EventLog()
    _append_run(log, ["e1", "e2"])
    alice = asyncio.create_task(_take(log, last_id=0, count=5))
    bob = asyncio.create_task(_take(log, last_id=0, count=5))
    await asyncio.sleep(0)  # 两个订阅都注册完
    _append_run(log, ["e3", "e4", "e5"])  # 一次广播，两个队列各得一份
    alice_records, bob_records = await asyncio.gather(alice, bob)
    assert [record["event"] for record in alice_records] == ["e1", "e2", "e3", "e4", "e5"]
    assert [record["id"] for record in bob_records] == [1, 2, 3, 4, 5]
    assert alice_records == bob_records  # 同序同内容：广播给所有在线者
