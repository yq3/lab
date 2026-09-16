"""L5.2 API 侧验收的 L5.4 副本：REST 建单 / 待审总表 / 三元回复 / SSE 重放——全部内存直连（零端口）。

对版纪律：与 L5.2 的 test_api 逐字相同，只有一处断言差异——once 完成的图内审计流水
尾部从 submit.approved 变为 payment.executed（批准后自动过门付款，L5.4 的接痕）。

离线确定性：httpx.AsyncClient(transport=ASGITransport(app=...)) 不起网络服务；
SSE 断言双取证——读 event stream（帧）+ 读事件表（approvals.EventLog）。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import api
import approvals
import demo
import graph


@pytest.fixture
async def harness(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, approvals.ApprovalService]]:
    """服务 + 内存直连 client（生命周期随测试；默认离线剧本）。"""
    async with graph.open_saver(str(tmp_path / "api.sqlite3")) as saver:
        service = approvals.ApprovalService(saver)
        transport = ASGITransport(app=api.build_app(service))
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            yield client, service


async def _wait_ticket(client: AsyncClient, run_id: str) -> dict:
    """等 run 的审批单出现在待审总表（工作台轮询视角，5s 上限）。"""
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        rows = (await client.get("/approvals")).json()["pending"]
        for row in rows:
            if row["run_id"] == run_id:
                return row
        await asyncio.sleep(0.01)
    raise AssertionError(f"ticket for {run_id} never appeared")


def _events(service: approvals.ApprovalService, run_id: str) -> list[tuple[str, dict]]:
    """事件表切片（SSE 双取证的另一半）。"""
    return [(r["event"], r["data"]) for r in service.log.snapshot() if r["data"].get("run_id") == run_id]


async def _read_frames(
    client: AsyncClient, count: int, last_event_id: str | None = None
) -> list[tuple[int, str, dict]]:
    """从 SSE 流读恰好 count 帧（id / event / data 三元组）。

    mode=replay：只重放历史即关流——ASGITransport 会等 app 跑完，常开的 live 流在
    内存直连下永远读不到（讲义 §3 的实测坑）；live 推送的顺序断言走事件生成器直测。
    """
    params = {"mode": "replay"}
    headers = {"Last-Event-ID": last_event_id} if last_event_id is not None else {}
    frames: list[tuple[int, str, dict]] = []
    frame_id, event_name = 0, ""
    async with client.stream("GET", "/approvals/stream", params=params, headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        async for line in response.aiter_lines():
            if line.startswith("id: "):
                frame_id = int(line.removeprefix("id: "))
            elif line.startswith("event: "):
                event_name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                frames.append((frame_id, event_name, json.loads(line.removeprefix("data: "))))
                if len(frames) >= count:
                    break
    return frames


async def test_post_run_registers_ticket_and_lists_pending(harness) -> None:
    client, service = harness
    response = await client.post("/runs", json={"claim_id": "CLM-2026-0001"})
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    row = await _wait_ticket(client, run_id)
    assert row["claim_id"] == "CLM-2026-0001"
    assert row["dept"] == "SALES"
    assert row["total_cents"] == 7100
    assert row["advice"]["decision"] == "APPROVE"
    assert row["status"] == "pending"
    assert row["graph_next"] == ["submit"]  # 待审总表带图快照：单挂在哪个节点上一目了然
    assert [event for event, _ in _events(service, run_id)] == ["run.started", "approval.requested"]


async def test_reply_once_completes_run(harness) -> None:
    client, service = harness
    run_id = (await client.post("/runs", json={"claim_id": "CLM-2026-0004"})).json()["run_id"]
    ticket_id = (await _wait_ticket(client, run_id))["ticket_id"]
    response = await client.post(f"/approvals/{ticket_id}/reply", json={"decision": "once"})
    assert response.status_code == 200
    assert response.json() == {"ticket_id": ticket_id, "run_id": run_id, "decision": "once", "rule_id": None}
    names = [event for event, _ in _events(service, run_id)]
    assert names == ["run.started", "approval.requested", "approval.replied", "run.completed"]
    completed = dict(_events(service, run_id)[-1][1])
    assert completed["sent"] is True
    assert completed["reason"] == "REJECT:INVOICE_INVALID"
    assert (await client.get("/approvals")).json()["pending"] == []  # 总表清空
    report = await service.run_report(run_id)
    assert report["events"][-1] == "payment.executed"  # L5.4：批准后过门付款才收口
    assert report["paid_cents"] == 5000


async def test_reply_reject_loops_back_with_new_ticket_and_hash(harness) -> None:
    client, service = harness
    run_id = (await client.post("/runs", json={"claim_id": "CLM-2026-0001"})).json()["run_id"]
    first = await _wait_ticket(client, run_id)
    await client.post(
        f"/approvals/{first['ticket_id']}/reply", json={"decision": "reject", "message": "餐费需附客户名单"}
    )
    second = await _wait_ticket(client, run_id)  # 回环重生成后：同一 run 的新审批单
    assert second["ticket_id"] != first["ticket_id"]
    assert second["content_hash"] != first["content_hash"]  # A6：新内容新指纹
    assert second["advice"]["decision"] == "ESCALATE"  # 修订版按留言转人工
    replied = dict(_events(service, run_id)[2][1])
    assert replied == {
        "ticket_id": first["ticket_id"],
        "run_id": run_id,
        "decision": "reject",
        "message": "餐费需附客户名单",
    }
    await client.post(f"/approvals/{second['ticket_id']}/reply", json={"decision": "once"})
    names = [event for event, _ in _events(service, run_id)]
    assert names == [
        "run.started",
        "approval.requested",
        "approval.replied",
        "approval.requested",
        "approval.replied",
        "run.completed",
    ]


async def test_reply_always_saves_rule_then_next_auto_applies(harness) -> None:
    client, service = harness
    run_1 = (await client.post("/runs", json={"claim_id": "CLM-2026-0002"})).json()["run_id"]
    ticket = await _wait_ticket(client, run_1)
    response = await client.post(
        f"/approvals/{ticket['ticket_id']}/reply", json={"decision": "always", "approver": "审批人-老王"}
    )
    rule_id = response.json()["rule_id"]
    (rule,) = service.rules.all()
    assert rule.rule_id == rule_id
    assert rule.dept == "SALES" and rule.max_total_cents == 8800  # cap=被批单总额
    assert rule.approved_by == "审批人-老王" and rule.approved_at  # A6 审计字段
    assert rule.content_hash == ticket["content_hash"]  # 绑的是批准时那版内容

    run_2 = (await client.post("/runs", json={"claim_id": "CLM-2026-0001"})).json()["run_id"]
    await service.wait_run(run_2)  # 起跑段收工（自动批准在段内完成）
    names = [event for event, _ in _events(service, run_2)]
    assert names == ["run.started", "approval.auto_applied", "run.completed"]  # 零人审
    auto = dict(_events(service, run_2)[1][1])
    assert auto["rule_id"] == rule_id
    assert (await client.get("/approvals")).json()["pending"] == []  # 没有单留给工作台
    report = await service.run_report(run_2)
    assert report["sent"] is True


async def test_reject_three_times_escalates_via_api(tmp_path) -> None:
    """HTTP 面的封顶：连驳三次 → 双哨兵收口（不送审），run.completed 带 sent=False。"""

    def generous_scripts(claim_id: str) -> list[str]:
        revised = demo.revised_advice_after_feedback
        return [*demo.offline_run_scripts(claim_id), revised(claim_id), revised(claim_id)]

    async with graph.open_saver(str(tmp_path / "cap.sqlite3")) as saver:
        service = approvals.ApprovalService(saver, scripts_for_run=generous_scripts)
        transport = ASGITransport(app=api.build_app(service))
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            run_id = (await client.post("/runs", json={"claim_id": "CLM-2026-0001"})).json()["run_id"]
            for _ in range(graph.MAX_APPROVAL_LOOPS + 1):
                ticket_id = (await _wait_ticket(client, run_id))["ticket_id"]
                await client.post(f"/approvals/{ticket_id}/reply", json={"decision": "reject"})
            completed = dict(_events(service, run_id)[-1][1])
            assert completed["decision"] == "ESCALATE"
            assert completed["reason"] == graph.ESCALATE_APPROVAL_REASON
            assert completed["sent"] is False


async def test_unknown_ticket_and_unknown_claim(harness) -> None:
    client, _service = harness
    response = await client.post("/approvals/tkt-9999/reply", json={"decision": "once"})
    assert response.status_code == 404
    assert response.json()["detail"] == "unknown_ticket: tkt-9999"
    response = await client.post("/runs", json={"claim_id": "CLM-9999"})
    assert response.status_code == 404
    assert response.json()["detail"] == "claim_not_found: CLM-9999"


async def test_sse_replays_history_and_last_event_id_truncates(harness) -> None:
    """SSE 双取证：断线重连全量重放（A2），Last-Event-ID 只重放其后（续传）。"""
    client, service = harness
    run_id = (await client.post("/runs", json={"claim_id": "CLM-2026-0003"})).json()["run_id"]
    ticket_id = (await _wait_ticket(client, run_id))["ticket_id"]
    await client.post(f"/approvals/{ticket_id}/reply", json={"decision": "once"})
    total = len(service.log.snapshot())
    assert total == 4  # started / requested / replied / completed

    full = await _read_frames(client, total)
    names = [name for _, name, _ in full]
    assert names == ["run.started", "approval.requested", "approval.replied", "run.completed"]
    assert [frame_id for frame_id, _, _ in full] == [1, 2, 3, 4]  # id 单调自增
    assert full[1][2]["ticket_id"] == ticket_id  # 帧内容与事件表一致

    partial = await _read_frames(client, total - 2, last_event_id="2")
    assert [frame_id for frame_id, _, _ in partial] == [3, 4]  # 断线点之后才开始重放


async def test_bad_last_event_id_and_empty_log(harness) -> None:
    client, service = harness
    response = await client.get("/approvals/stream", params={"mode": "replay"}, headers={"Last-Event-ID": "abc"})
    assert response.status_code == 400
    empty = await _read_frames(client, 0)
    assert empty == []
    assert service.log.snapshot() == []  # 空表读空（不丢单的前提：事件表是真相之源）


async def test_live_generator_replay_then_push_in_order(harness) -> None:
    """live 流的顺序断言（事件生成器直测——spec 双取证的另一半）：

    订阅先重放历史、再无缝接实时推送：每条恰好一次、顺序与事件表一致（A2）。
    """
    _client, service = harness
    service.log.append("approval.requested", {"ticket_id": "tkt-0001"})  # 订阅前的历史
    collected: list[dict] = []
    stream = service.log.subscribe()
    first = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)  # 让订阅注册发生（生成器体的同步段跑完）
    service.log.append("approval.replied", {"ticket_id": "tkt-0001", "decision": "once"})  # 订阅后的实时
    collected.append(await first)
    collected.append(await stream.__anext__())
    await stream.aclose()  # 断开：订阅注销
    assert [record["event"] for record in collected] == ["approval.requested", "approval.replied"]  # 重放在前、实时在后
    assert [record["id"] for record in collected] == [1, 2]
    assert service.log._subscribers == []  # 断开后订阅注销（不泄漏）


def test_sse_frame_shape() -> None:
    """SSE 帧格式：id 行 + event 行 + data 行 + 空行收尾（协议规定）。"""
    frame = api._sse_frame({"id": 7, "event": "approval.requested", "data": {"ticket_id": "tkt-0001"}})
    assert frame == 'id: 7\nevent: approval.requested\ndata: {"ticket_id": "tkt-0001"}\n\n'
