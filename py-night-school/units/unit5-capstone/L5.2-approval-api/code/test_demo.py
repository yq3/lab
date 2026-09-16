"""L5.2 demo 验收：剧本形态 + 三幕全链路（服务面直跑，零 HTTP）。"""

from __future__ import annotations

import approvals
import demo
import graph
from advice import Advice
from plan import Plan, validate_plan


def test_offline_run_scripts_shape() -> None:
    """一次 run 的剧本清单：[planner 合法计划, drafter 首版, drafter 修订版（回环才消费）]。"""
    scripts = demo.offline_run_scripts("CLM-2026-0001")
    assert len(scripts) == 3
    assert isinstance(validate_plan(scripts[0]), Plan)  # 首条是合法计划
    first = Advice.model_validate_json(scripts[1])
    assert (first.decision, first.reason) == ("APPROVE", "PASS")  # 首版=规则表结论
    revised = Advice.model_validate_json(scripts[2])
    assert revised.decision == "ESCALATE" and revised.reason == "REJECT:APPROVAL_FEEDBACK"  # 回环修订版


async def test_three_acts_service_level(tmp_path) -> None:
    """三幕集成：once / reject 回环 / always+自动批准——事件表与图收口双取证。"""
    async with graph.open_saver(str(tmp_path / "demo.sqlite3")) as saver:
        service = approvals.ApprovalService(saver)

        # 第一幕 once：建单 → 批准 → 完成
        run_1 = service.start_run("CLM-2026-0004")
        await service.wait_run(run_1)
        (ticket_1,) = [t for t in service._pending.values()]
        assert ticket_1.claim_id == "CLM-2026-0004"
        await service.reply(ticket_1.ticket_id, "once")
        report_1 = await service.run_report(run_1)
        assert report_1["sent"] is True and report_1["events"][-1] == "submit.approved"

        # 第二幕 reject：驳回+留言 → 回环重生成（新 hash）→ 再批准
        run_2 = service.start_run("CLM-2026-0001")
        await service.wait_run(run_2)
        (ticket_2,) = [t for t in service._pending.values()]
        hash_1 = ticket_2.content_hash
        await service.reply(ticket_2.ticket_id, "reject", message="餐费需附客户名单")
        (ticket_3,) = [t for t in service._pending.values()]
        assert ticket_3.content_hash != hash_1
        assert ticket_3.advice["decision"] == "ESCALATE"
        await service.reply(ticket_3.ticket_id, "once")
        report_2 = await service.run_report(run_2)
        assert report_2["sent"] is True
        assert "submit.rejected" in report_2["events"] and report_2["events"].count("drafter") == 2

        # 第三幕 always + 自动批准：第二张同部门小额单零人审
        run_3 = service.start_run("CLM-2026-0002")
        await service.wait_run(run_3)
        (ticket_4,) = [t for t in service._pending.values()]
        await service.reply(ticket_4.ticket_id, "always", approver="审批人-老王")
        run_4 = service.start_run("CLM-2026-0001")
        await service.wait_run(run_4)
        assert not service._pending  # 没有单留给工作台
        names = [record["event"] for record in service.log.snapshot() if record["data"].get("run_id") == run_4]
        assert names == ["run.started", "approval.auto_applied", "run.completed"]
        report_4 = await service.run_report(run_4)
        assert report_4["sent"] is True

        # 全局事件账（四类事件齐、id 连续）
        all_records = service.log.snapshot()
        kinds = {record["event"] for record in all_records}
        assert kinds == {
            "run.started",
            "approval.requested",
            "approval.replied",
            "run.completed",
            "approval.auto_applied",
        }
        assert [record["id"] for record in all_records] == list(range(1, len(all_records) + 1))
