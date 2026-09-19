"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

from pathlib import Path

from httpx import ASGITransport, AsyncClient

import ex1_ticket as ex1


def _texts(messages: list) -> list[str]:
    """消息史里的 user 侧文本（驳回留言回喂的取证——留言只出现在 user 侧）。"""
    texts: list[str] = []
    for m in messages:
        if isinstance(m, dict):
            if m.get("role") == "user":
                texts.append(str(m.get("content", "")))
        elif getattr(m, "type", "") == "human":
            texts.append(str(m.content))
    return texts


async def test_reply_once_completes_run(tmp_path: Path) -> None:
    async with ex1.open_db(str(tmp_path / "once.db")) as saver:
        service = ex1.ApprovalService(saver)
        ticket_id = await service.start()
        assert service.pending[ticket_id]["draft_version"] == 1  # 首版建议单已登记
        outcome = await service.reply(ticket_id, "once")
        assert outcome == {"ticket_id": ticket_id, "decision": "once", "rule_id": None}
        assert service.pending == {}  # 总表清空
        requested = {
            "ticket_id": ticket_id,
            "claim_id": "CLM-2026-0001",
            "dept": "SALES",
            "total_cents": 7100,
            "draft_version": 1,
        }
        assert [(e["event"], e["data"]) for e in service.events] == [
            ("approval.requested", requested),
            ("approval.replied", {"ticket_id": ticket_id, "decision": "once", "rule_id": None}),
            ("run.completed", {"run_id": "ex1-run-1", "sent": True}),
        ]
        snapshot = await service.state()
        assert snapshot.next == ()  # 跑到 END
        assert snapshot.values["sent"] is True
        assert snapshot.values["drafts"] == [1]  # once 不回环：drafter 恰好一轮


async def test_reply_reject_feeds_message_and_loops(tmp_path: Path) -> None:
    async with ex1.open_db(str(tmp_path / "reject.db")) as saver:
        service = ex1.ApprovalService(saver)
        first = await service.start()
        await service.reply(first, "reject", message="餐费需附客户名单")
        assert first not in service.pending
        (second,) = service.pending  # 回环重生成后：恰好一张新单在场
        assert service.pending[second]["draft_version"] == 2  # 新单是新版本内容
        assert service.events[1] == {
            "event": "approval.replied",
            "data": {"ticket_id": first, "decision": "reject", "message": "餐费需附客户名单"},
        }
        snapshot = await service.state()
        assert snapshot.next == ("submit",)  # 回到 drafter 重起草后再次停在送审门
        assert snapshot.values["drafts"] == [1, 2]  # 回环取证：drafter 恰好两轮
        assert any("餐费需附客户名单" in text for text in _texts(snapshot.values["messages"]))  # 留言回喂进 messages
        await service.reply(second, "once")  # 第二单批准收尾
        assert service.events[-1] == {"event": "run.completed", "data": {"run_id": "ex1-run-1", "sent": True}}


async def test_reject_without_message_uses_default_feedback(tmp_path: Path) -> None:
    async with ex1.open_db(str(tmp_path / "default.db")) as saver:
        service = ex1.ApprovalService(saver)
        ticket_id = await service.start()
        await service.reply(ticket_id, "reject")
        snapshot = await service.state()
        assert any(ex1.DEFAULT_FEEDBACK in text for text in _texts(snapshot.values["messages"]))
        assert service.events[1]["data"]["message"] == ex1.DEFAULT_FEEDBACK


async def test_reply_always_grants_rule_and_reuses_on_hit(tmp_path: Path) -> None:
    async with ex1.open_db(str(tmp_path / "always.db")) as saver:
        service = ex1.ApprovalService(saver)
        first = await service.start()
        outcome = await service.reply(first, "always")
        assert outcome == {"ticket_id": first, "decision": "always", "rule_id": "rule-001"}
        assert service.rules.count() == 1  # 规则入库
        assert service.events[1]["data"]["rule_id"] == "rule-001"
        snapshot = await service.state()
        assert snapshot.values["sent"] is True  # always 也批准本单

        second = await service.start()  # 同部门同额的第二单（新 run）
        outcome2 = await service.reply(second, "always")
        assert outcome2["rule_id"] == "rule-001"  # 命中查询：复用已有规则
        assert service.rules.count() == 1  # 不重复建规则
        assert service.events[-1]["event"] == "run.completed"


async def test_unknown_ticket_maps_to_404(tmp_path: Path) -> None:
    async with ex1.open_db(str(tmp_path / "http.db")) as saver:
        service = ex1.ApprovalService(saver)
        transport = ASGITransport(app=ex1.create_app(service))
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            response = await client.post("/approvals/tkt-999/reply", json={"decision": "once"})
            assert response.status_code == 404
            assert response.json()["detail"] == "unknown_ticket: tkt-999"
            ticket_id = await service.start()  # 合法单同端点照常 200
            response = await client.post(f"/approvals/{ticket_id}/reply", json={"decision": "once"})
            assert response.status_code == 200
            assert response.json()["decision"] == "once"
