"""L5.2 三幕 demo：REST 建单 + 三元回复 + 事件流重放，一屏看全「审批外化」（讲义 §3 主线）。

全部走 httpx 内存直连（ASGITransport，零端口）。事件流读 ?mode=replay 的拉取面——
每幕动作后拉一次「重放即关」的流，打印该 run 的 SSE 帧时序；live 常开流是 uvicorn
加餐的形态（curl -N，讲义 §3 末尾），顺序语义与重放同一张事件表保证。

三幕：
- 第一幕 once：建单 → 审批人 once 批准 → run completed（sent=True）；
- 第二幕 reject 回环：建单 → 驳回+留言 → 图回 drafter 重生成 → 新审批单（content_hash 变）
  → 再批准 → completed——A1「reject 的 message 回喂模型做纠错」+ A6 内容绑定；
- 第三幕 always + 自动批准：建单 → always（存规则）→ completed；再建同部门小额单 →
  零人审自动过（approval.auto_applied，A1「批准并记住」的完整闭环）。

压轴两拍（A2「审批是可重放事件」）：断线重连的第二个工作台不带 Last-Event-ID 重订阅
→ 全量重放；带 Last-Event-ID → 只重放其后（断线续传）。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path

from httpx import ASGITransport, AsyncClient

import api
import approvals
import graph


async def _frames(client: AsyncClient, last_event_id: str | None = None) -> list[tuple[int, str, dict]]:
    """拉一帧重放流（mode=replay 重放即关）：[(id, event, data), ...]。"""
    params = {"mode": "replay"}
    headers = {"Last-Event-ID": last_event_id} if last_event_id is not None else {}
    frames: list[tuple[int, str, dict]] = []
    frame_id, event_name = 0, ""
    async with client.stream("GET", "/approvals/stream", params=params, headers=headers) as response:
        async for line in response.aiter_lines():
            if line.startswith("id: "):
                frame_id = int(line.removeprefix("id: "))
            elif line.startswith("event: "):
                event_name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                frames.append((frame_id, event_name, json.loads(line.removeprefix("data: "))))
    return frames


async def _events_for(client: AsyncClient, run_id: str) -> list[tuple[str, dict]]:
    return [(event, data) for _id, event, data in await _frames(client) if data.get("run_id") == run_id]


def _print_stream(events: list[tuple[str, dict]]) -> None:
    for event, data in events:
        extra = {k: v for k, v in data.items() if k not in {"run_id", "claim_id"}}
        print(f"    {event:<22} {extra}")


async def _wait_ticket(client: AsyncClient, run_id: str) -> dict:
    """等 run 的审批单出现在待审总表（工作台轮询视角，5s 上限）。"""
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        for row in (await client.get("/approvals")).json()["pending"]:
            if row["run_id"] == run_id:
                return row
        await asyncio.sleep(0.01)
    raise AssertionError(f"ticket for {run_id} never appeared")


async def _wait_completed(client: AsyncClient, run_id: str) -> None:
    """等 run.completed（自动批准路径：完成在起跑段内，不经过工作台）。"""
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if any(event == "run.completed" for event, data in await _events_for(client, run_id)):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} never completed")


def _print_report(report: dict) -> None:
    print(f"    图内审计流水: {report['events']}")
    print(f"    收口: {report['decision']} / {report['reason']} / sent={report['sent']}")


async def act_once(client: AsyncClient, service: approvals.ApprovalService) -> None:
    print("== 第一幕 once：建单 → 批准本单 → 完成 ==")
    run_id = (await client.post("/runs", json={"claim_id": "CLM-2026-0004"})).json()["run_id"]
    ticket = await _wait_ticket(client, run_id)
    print(f"  [POST /runs 0004 → {run_id}] 待审单 {ticket['ticket_id']} 已登记")
    print(f"    总表行: dept={ticket['dept']}  total={ticket['total_cents']}分  advice={ticket['advice']}")
    print(f"    graph_next={ticket['graph_next']}（单挂在 submit——无人订阅也不丢，单在 pending 表里）")
    print('  [POST /approvals/{ticket}/reply {"decision": "once"}] 事件流时序：')
    await client.post(f"/approvals/{ticket['ticket_id']}/reply", json={"decision": "once"})
    _print_stream(await _events_for(client, run_id))
    _print_report(await service.run_report(run_id))


async def act_reject(client: AsyncClient, service: approvals.ApprovalService) -> None:
    print("== 第二幕 reject：驳回+留言 → 回环重生成 → 新单（hash 变）→ 再批准 ==")
    run_id = (await client.post("/runs", json={"claim_id": "CLM-2026-0001"})).json()["run_id"]
    first = await _wait_ticket(client, run_id)
    print(f"  [POST /runs 0001 → {run_id}] 首版建议单 {first['ticket_id']}（content_hash={first['content_hash']}）")
    await client.post(
        f"/approvals/{first['ticket_id']}/reply",
        json={"decision": "reject", "message": "客户拜访餐费需补充三级审批单，补齐前先转人工复核"},
    )
    second = await _wait_ticket(client, run_id)
    print(f"  [reply reject+留言] 图回 drafter 重生成 → 新单 {second['ticket_id']}")
    print(f"    （content_hash={second['content_hash']}）")
    print(f"    hash 变了：{first['content_hash']} != {second['content_hash']} ——批的是新一版内容，不是单据号（A6）")
    await client.post(f"/approvals/{second['ticket_id']}/reply", json={"decision": "once"})
    print("  [reply once] 事件流时序：")
    _print_stream(await _events_for(client, run_id))
    report = await service.run_report(run_id)
    _print_report(report)


async def act_always(client: AsyncClient, service: approvals.ApprovalService) -> None:
    print("== 第三幕 always：批准并记住 → 同部门小额单零人审自动过 ==")
    run_1 = (await client.post("/runs", json={"claim_id": "CLM-2026-0002"})).json()["run_id"]
    ticket = await _wait_ticket(client, run_1)
    await client.post(f"/approvals/{ticket['ticket_id']}/reply", json={"decision": "always", "approver": "审批人-老王"})
    (rule,) = service.rules.all()
    print(f"  [reply always] 规则已存：{rule.rule_id} = dept {rule.dept} 且总额 ≤ {rule.max_total_cents} 分")
    print(f"    审计四问：谁 {rule.approved_by} / 何时 {rule.approved_at}")
    print(f"    pattern ({rule.dept}≤{rule.max_total_cents}) / 绑定 {rule.content_hash}")

    run_2 = (await client.post("/runs", json={"claim_id": "CLM-2026-0001"})).json()["run_id"]
    await _wait_completed(client, run_2)
    print(f"  [POST /runs 0001 → {run_2}] 零人审——事件流时序：")
    _print_stream(await _events_for(client, run_2))
    _print_report(await service.run_report(run_2))


async def finale(client: AsyncClient, service: approvals.ApprovalService) -> None:
    print("== 压轴 A2：审批是可重放事件——断线重连的工作台 ==")
    total = len(service.log.snapshot())
    full = await _frames(client)
    print(f"  [不带 Last-Event-ID 重订阅] 全量重放 {len(full)} 条（先发生的事件一条不丢）：")
    print(f"    {[event for _, event, _ in full]}")
    partial = await _frames(client, last_event_id="3")
    print(f"  [带 Last-Event-ID: 3] 只重放其后 {len(partial)} 条：{[event for _, event, _ in partial]}")
    print("    <- 断线期间不丢单也不隐式作答：重订阅即重放（无人在线时单都在 pending 表里）")
    assert len(full) == total and len(partial) == total - 3


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "approval.sqlite3")
        async with graph.open_saver(db) as saver:
            service = approvals.ApprovalService(saver)
            transport = ASGITransport(app=api.build_app(service))
            async with AsyncClient(transport=transport, base_url="http://l52") as client:
                await act_once(client, service)
                print()
                await act_reject(client, service)
                print()
                await act_always(client, service)
                print()
                await finale(client, service)
                print()
                print(f"checkpoint 库（图状态活过每一段 invoke）: {db}")


if __name__ == "__main__":
    asyncio.run(main())
