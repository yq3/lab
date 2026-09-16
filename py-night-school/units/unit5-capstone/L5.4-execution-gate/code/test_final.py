"""讲义区验收（七）：三主链路端到端——里程碑集成测试的雏形（demo_final 三幕的断言版）。

- 链路① 审批暂停→恢复：interrupt 暂停 → reply once → 门 ALLOW → payment.executed 在账；
- 链路② 拒绝回环：reject+留言 → 回 drafter 重生成 → 新审批单（content_hash 变）→ 批准 → 过门；
- 链路③ fail-closed 拒绝：紧合同下单笔超限 → 未付款 → gate.denied 在账 + ESCALATE 终态；
- 事件流水断言：payment.executed / gate.denied 分别在 run 聚合与日历账本聚合上；
- 图签名变化 → run_key 变化（L5.3 图版本绑定在 L5.4 的复用：加门节点 = 换世界）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import approvals
import audit_cache
import demo
import eventstore
import gate
import graph
import versioning

TODAY = graph.DEFAULT_TODAY
TIGHT_POLICY = gate.Policy(
    max_single_cents=5_000,
    max_daily_total_cents=1_000_000,
    max_payments_per_day=50,
    vendor_blocklist=(),
)
CLOCK = "t"


async def _ticket_of(service: approvals.ApprovalService, run_id: str) -> dict:
    """取 run 当前唯一待审单（轮询待审总表，5s 上限）。"""
    for _ in range(500):
        rows = await service.pending_approvals()
        for row in rows:
            if row["run_id"] == run_id:
                return row
        await asyncio.sleep(0.01)
    raise AssertionError(f"ticket for {run_id} never appeared")


async def test_link_one_pause_resume_pays_and_audits(tmp_path: Path) -> None:
    """链路①：暂停在 submit、once 恢复、门 ALLOW、付款在账（run 聚合 + 日历账本双取证）。"""
    db = tmp_path / "one.db"
    async with graph.open_saver(str(tmp_path / "one.ckpt")) as saver:
        with eventstore.connect(db, clock=lambda: CLOCK) as store:
            cache = audit_cache.DecisionCache(db, clock=lambda: CLOCK)
            service = approvals.ApprovalService(
                saver, store=store, cache=cache, ledger=graph.PaymentLedger(store), today=TODAY
            )
            run_id = service.start_run("CLM-2026-0001")
            await service.wait_run(run_id)
            ticket = await _ticket_of(service, run_id)
            assert ticket["graph_next"] == ["submit"]  # 暂停点：单挂在送审门
            assert ticket["content_hash"] and ticket["advice"]["decision"] == "APPROVE"
            await service.reply(ticket["ticket_id"], "once")
            report = await service.run_report(run_id)
            assert report["next"] == []
            assert (report["decision"], report["reason"]) == ("APPROVE", "PASS")
            assert report["paid_cents"] == 7100
            assert report["events"][-2:] == ["gate.allowed", "payment.executed"]
            rows = store.events_for(report["run_key"])
            types = [r["type"] for r in rows]
            assert types[-3:] == ["submitted", "gate.checked", "payment.executed"]  # A7：批准之后门先查再付
            payment = store.events_for(report["run_key"], type="payment.executed")[0]["payload"]
            assert (payment["paid_cents"], payment["vendor"]) == (7100, "王工")
            day = store.events_for(graph.PaymentLedger.day_aggregate(TODAY), type="payment.executed")
            assert len(day) == 1 and day[0]["payload"]["claim_id"] == "CLM-2026-0001"  # 当日账本在账
            cache.close()


async def test_link_two_reject_loop_regenerates_new_hash_then_pays(tmp_path: Path) -> None:
    """链路②：驳回留言回喂重生成 → 新审批单（新 hash）→ 批准 → 过门付款（人审权威在 A1）。"""
    db = tmp_path / "two.db"
    async with graph.open_saver(str(tmp_path / "two.ckpt")) as saver:
        with eventstore.connect(db, clock=lambda: CLOCK) as store:
            cache = audit_cache.DecisionCache(db, clock=lambda: CLOCK)
            service = approvals.ApprovalService(
                saver, store=store, cache=cache, ledger=graph.PaymentLedger(store), today=TODAY
            )
            run_id = service.start_run("CLM-2026-0001")
            await service.wait_run(run_id)
            first = await _ticket_of(service, run_id)
            await service.reply(first["ticket_id"], "reject", message="补充三级审批单")
            second = await _ticket_of(service, run_id)
            assert second["ticket_id"] != first["ticket_id"]
            assert second["content_hash"] != first["content_hash"]  # A6：内容一变指纹变——新的一单
            assert second["advice"]["decision"] == "ESCALATE"  # 修订版按留言转人工
            await service.reply(second["ticket_id"], "once")
            report = await service.run_report(run_id)
            assert (report["decision"], report["reason"]) == ("ESCALATE", "REJECT:APPROVAL_FEEDBACK")
            assert report["paid_cents"] == 7100  # 审批人否决了 ESCALATE 建议——权威在审批面（A1）
            rows = store.events_for(report["run_key"])
            types = [r["type"] for r in rows]
            assert types.count("advice.drafted") == 2  # 改稿的审计证据：两版建议单
            assert "submit" in types or "submitted" in types
            assert types[-1] == "payment.executed"
            cache.close()


async def test_link_three_tight_policy_denies_without_payment(tmp_path: Path) -> None:
    """链路③：紧合同超限 → 未付款 → gate.denied 在账 + 终态 ESCALATE/REAUTH 码。"""
    db = tmp_path / "three.db"
    async with graph.open_saver(str(tmp_path / "three.ckpt")) as saver:
        with eventstore.connect(db, clock=lambda: CLOCK) as store:
            service = approvals.ApprovalService(
                saver, store=store, policy=TIGHT_POLICY, ledger=graph.PaymentLedger(store), today=TODAY
            )
            run_id = service.start_run("CLM-2026-0002")
            await service.wait_run(run_id)
            ticket = await _ticket_of(service, run_id)
            assert ticket["total_cents"] > TIGHT_POLICY.max_single_cents  # 8800 > 5000：注定过不了门
            await service.reply(ticket["ticket_id"], "once")
            report = await service.run_report(run_id)
            assert report["decision"] == "ESCALATE"
            assert report["reason"] == graph.ESCALATE_REAUTH_REASON  # 定量超限：升额后重开新 run
            assert report["paid_cents"] is None
            assert report["gate"]["reason_code"] == "single_over_limit"
            assert report["sent"] is False
            rows = store.events_for(report["run_key"])
            types = [r["type"] for r in rows]
            assert types[-3:] == ["gate.checked", "gate.denied", "advice.drafted"]
            denied = store.events_for(report["run_key"], type="gate.denied")[0]["payload"]
            assert (denied["action"], denied["reason_code"]) == ("PAUSE_FOR_REAUTH", "single_over_limit")
            assert store.events_for(graph.PaymentLedger.day_aggregate(TODAY), type="payment.executed") == []
            completed = service.log.snapshot()[-1]
            assert completed["event"] == "run.completed" and completed["data"]["paid_cents"] is None


def test_gate_node_changes_signature_and_run_key(tmp_path) -> None:
    """图签名变化→run_key 变化（L5.3 复用）：L5.4 图（含 execute）与 extra_stamp 变体签名互异；
    同一单据换图即换 run_key——旧聚合不可续（版本绑定是「续跑权」的作废，不是历史的作废）。"""
    with_default = versioning.topology_signature(graph.build_graph(demo.model_for_url("http://x/v1")))
    with_stamp = versioning.topology_signature(graph.build_graph(demo.model_for_url("http://x/v1"), extra_stamp=True))
    assert with_default != with_stamp  # +1 节点：签名必变
    assert versioning.run_key("CLM-2026-0001", with_default) != versioning.run_key("CLM-2026-0001", with_stamp)
    assert versioning.run_key("CLM-2026-0001", with_default).startswith("CLM-2026-0001@")
    with pytest.raises(versioning.GraphVersionMismatch):
        versioning.assert_compatible(with_default, with_stamp)  # 旧 key 续新图：拒绝


async def test_reaudited_run_appends_gate_events_and_cache_hits(tmp_path: Path) -> None:
    """统一审计出口（run_audited）：门事件进事件流、第二遍缓存全命中（零请求）且事件照常追加。"""
    db = tmp_path / "audited.db"
    first = await demo.run_audited("CLM-2026-0001", db, clock=lambda: CLOCK)
    assert first["requests"] == 2  # planner + drafter 各一次真实调用
    with eventstore.connect(db, clock=lambda: CLOCK) as store:
        types = [r["type"] for r in store.events_for(first["run_key"])]
        assert types[-3:] == ["submitted", "gate.checked", "payment.executed"]
        assert store.events_for(graph.PaymentLedger.day_aggregate(TODAY), type="payment.executed")
    second = await demo.run_audited("CLM-2026-0001", db, clock=lambda: CLOCK)
    assert second["requests"] == 0  # 缓存全命中——第二遍想花钱都没门
    assert second["run_key"] == first["run_key"]  # 同图同单：run_key 稳定
    with eventstore.connect(db, clock=lambda: CLOCK) as store:
        rows = store.events_for(first["run_key"])
        assert [r["type"] for r in rows].count("payment.executed") == 2  # 自动批准又付了一遍（账本继续记账）
        assert len(store.events_for(first["run_key"], type="run.started")) == 2  # 两次出生证明
