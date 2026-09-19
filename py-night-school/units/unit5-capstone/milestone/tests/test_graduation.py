"""毕业测试①：三条主链路的 pytest 集成测试（不要改本文件——它就是判卷老师）。

CURRICULUM「Unit 5 里程碑」的机器判据：链路①审批暂停→恢复 / 链路②拒绝回环 / 链路③
fail-closed 拒绝（定量 PAUSE 与黑名单 DENY 两个变体）。前身是 L5.4 code/test_final.py
的五张测试（三链路 + 图签名 + 统一审计出口）——本文件把它扩成正式毕业件：判据写进
docstring（毕业判据清单），meta 测试钉住「清单与断言逐条对齐」。

每条链路最关键的一处取证在 graduation_checks.py（你的三个 TODO(g1)/(g2)/(g3)）：
未填时三/四张链路测试是**设计内的红**（NotImplementedError），其余测试发货态就必须绿。
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

import approvals
import audit_cache
import demo
import eventstore
import gate
import graduation_checks as checks
import graph
import versioning

TODAY = graph.DEFAULT_TODAY
TIGHT_POLICY = gate.Policy(  # 链路③定量变体：单笔上限 5000 分（0002 总额 8800 分必超）
    max_single_cents=5_000,
    max_daily_total_cents=1_000_000,
    max_payments_per_day=50,
    vendor_blocklist=(),
)
BLOCKLIST_POLICY = gate.Policy(  # 链路③结构变体：收款方硬黑名单（0001 提单人 王工 在列）
    max_single_cents=1_000_000,
    max_daily_total_cents=10_000_000,
    max_payments_per_day=50,
    vendor_blocklist=("王工",),
)
CLOCK = "t"


async def _ticket_of(service: approvals.ApprovalService, run_id: str) -> dict:
    """取 run 当前唯一待审单（轮询待审总表，5s 上限）——工作台视角。"""
    for _ in range(500):
        rows = await service.pending_approvals()
        for row in rows:
            if row["run_id"] == run_id:
                return row
        await asyncio.sleep(0.01)
    raise AssertionError(f"ticket for {run_id} never appeared")


# ---- 链路①：审批暂停→恢复（interrupt → once → 门 ALLOW → payment.executed）----


async def test_link_one_pause_resume_pays_and_audits(tmp_path: Path) -> None:
    """链路① 审批暂停→恢复（毕业判据清单，逐条有断言对齐）：
    1. interrupt 暂停在 submit：待审单挂在 ["submit"]——等人的是 checkpoint，不是线程；
    2. once 批准后过门付款：paid_cents == 7100 分，终态 APPROVE/PASS（L5.1 出口契约存活）；
    3. 事件顺序：submitted → gate.checked → payment.executed 收尾（A7：批准只是授权，门查过才付款）；
    4. seq 连续：整条事件流水从 0 无空洞（append-only 审计账）；
    5. 双落账：payment.executed 在 run 聚合（审计面）与 ledger:<today> 日历聚合（账本面）各在案。
    """
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
            assert ticket["graph_next"] == ["submit"]  # 判据1：暂停点在送审门
            assert ticket["content_hash"] and ticket["advice"]["decision"] == "APPROVE"
            await service.reply(ticket["ticket_id"], "once")
            report = await service.run_report(run_id)
            assert report["next"] == []
            assert (report["decision"], report["reason"]) == ("APPROVE", "PASS")  # 判据2：终态
            assert report["paid_cents"] == 7100  # 判据2：过门实付（整数分）
            checks.assert_stream_tail(  # 判据3 事件顺序 + 判据4 seq 连续（你的取证工装）
                store, report["run_key"], ("submitted", "gate.checked", "payment.executed")
            )
            payment = store.events_for(report["run_key"], type="payment.executed")[0]["payload"]
            assert (payment["paid_cents"], payment["vendor"], payment["dept"]) == (7100, "王工", "SALES")
            day = store.events_for(graph.PaymentLedger.day_aggregate(TODAY), type="payment.executed")
            assert len(day) == 1 and day[0]["payload"]["claim_id"] == "CLM-2026-0001"  # 判据5：账本面在案
            assert day[0]["seq"] == 0  # 账本聚合自己也从 0 连续
            cache.close()


# ---- 链路②：拒绝回环（reject+留言 → drafter 重生成 → 新 hash → 批准 → 过门）----


async def test_link_two_reject_loop_regenerates_new_hash_then_pays(tmp_path: Path) -> None:
    """链路② 拒绝回环（毕业判据清单，逐条有断言对齐）：
    1. reject+留言回喂：图回 drafter 重生成，新审批单 ticket_id 变（旧单消费掉、新单登记）；
    2. content_hash 变化：批的是新一版内容（A6）——同一单据重生成，指纹必须换；
    3. 修订版建议单 decision == ESCALATE（按留言转人工），事件表两条 advice.drafted（改稿审计证据）；
    4. 权威在审批面（A1）：审批人否决 ESCALATE 建议仍批准付款，终态 paid_cents == 7100 且
       事件流以 payment.executed 收尾。
    """
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
            assert second["ticket_id"] != first["ticket_id"]  # 判据1：新的一单
            assert second["advice"]["decision"] == "ESCALATE"  # 判据3：修订版按留言转人工
            checks.assert_hash_rotated(first, second)  # 判据2：A6 指纹轮换（你的取证工装）
            await service.reply(second["ticket_id"], "once")
            report = await service.run_report(run_id)
            assert (report["decision"], report["reason"]) == ("ESCALATE", "REJECT:APPROVAL_FEEDBACK")
            assert report["paid_cents"] == 7100  # 判据4：审批人否决建议、批准付款
            rows = store.events_for(report["run_key"])
            types = [row["type"] for row in rows]
            assert types.count("advice.drafted") == 2  # 判据3：两版建议单的审计证据
            assert "submitted" in types
            assert types[-1] == "payment.executed"  # 判据4：收尾是实付
            day = store.events_for(graph.PaymentLedger.day_aggregate(TODAY), type="payment.executed")
            assert len(day) == 1
            cache.close()


# ---- 链路③：fail-closed 拒绝（定量 PAUSE / 黑名单 DENY 两个变体）----


async def test_link_three_tight_policy_pauses_without_payment(tmp_path: Path) -> None:
    """链路③ fail-closed 拒绝·定量超限（毕业判据清单，逐条有断言对齐）：
    1. 紧合同下单笔超限提案照常走到审批（8800 > 5000）——审批面不管定量，门管；
    2. 批准后门 PAUSE_FOR_REAUTH/single_over_limit：paid_cents 为 None、sent 为 False；
    3. 终态 ESCALATE / REJECT:GATE_REAUTH_REQUIRED——升额改的是 Policy（合同），重开新 run；
    4. 事件顺序：gate.checked → gate.denied → advice.drafted 收尾（批了、没付、转人审的审计叙事）；
    5. 账本零记录：当日账本聚合上 payment.executed 一条都没有——「没付」的铁证。
    """
    db = tmp_path / "three.db"
    async with graph.open_saver(str(tmp_path / "three.ckpt")) as saver:
        with eventstore.connect(db, clock=lambda: CLOCK) as store:
            service = approvals.ApprovalService(
                saver, store=store, policy=TIGHT_POLICY, ledger=graph.PaymentLedger(store), today=TODAY
            )
            run_id = service.start_run("CLM-2026-0002")
            await service.wait_run(run_id)
            ticket = await _ticket_of(service, run_id)
            assert ticket["total_cents"] > TIGHT_POLICY.max_single_cents  # 判据1：8800 > 5000，注定过不了门
            await service.reply(ticket["ticket_id"], "once")
            report = await service.run_report(run_id)
            assert report["decision"] == "ESCALATE"
            assert report["reason"] == graph.ESCALATE_REAUTH_REASON  # 判据3：定量超限的升级码
            assert report["paid_cents"] is None and report["sent"] is False  # 判据2：未付款、不送审
            assert report["gate"]["reason_code"] == "single_over_limit"
            denied = store.events_for(report["run_key"], type="gate.denied")[0]["payload"]
            assert (denied["action"], denied["reason_code"]) == ("PAUSE_FOR_REAUTH", "single_over_limit")
            checks.assert_stream_tail(  # 判据4：批了、没付、转人审（顺序取证）
                store, report["run_key"], ("gate.checked", "gate.denied", "advice.drafted")
            )
            checks.assert_zero_payments(  # 判据5：账本零记录（你的取证工装）
                store, graph.PaymentLedger.day_aggregate(TODAY)
            )
            completed = service.log.snapshot()[-1]
            assert completed["event"] == "run.completed" and completed["data"]["paid_cents"] is None


async def test_link_three_blocklist_denies_without_payment(tmp_path: Path) -> None:
    """链路③ fail-closed 拒绝·黑名单（毕业判据清单，逐条有断言对齐）：
    1. 收款方在 vendor_blocklist：结构性违规走 DENY——改数字救不了，与定量态分码；
    2. 批准后门 DENY/vendor_blocklisted：gate.denied 事件在账，payload.action == "DENY"；
    3. 终态 ESCALATE / REJECT:GATE_DENIED——审计看码知道下一步（结构性拒绝没有恢复路径）；
    4. 账本零记录：当日账本 payment.executed 零条（复用链路③的取证工装）。
    """
    db = tmp_path / "block.db"
    async with graph.open_saver(str(tmp_path / "block.ckpt")) as saver:
        with eventstore.connect(db, clock=lambda: CLOCK) as store:
            service = approvals.ApprovalService(
                saver, store=store, policy=BLOCKLIST_POLICY, ledger=graph.PaymentLedger(store), today=TODAY
            )
            run_id = service.start_run("CLM-2026-0001")
            await service.wait_run(run_id)
            ticket = await _ticket_of(service, run_id)
            assert ticket["total_cents"] == 7100
            await service.reply(ticket["ticket_id"], "once")
            report = await service.run_report(run_id)
            assert report["decision"] == "ESCALATE"
            assert report["reason"] == graph.ESCALATE_GATE_REASON  # 判据3：结构性拒绝的分码
            assert report["paid_cents"] is None and report["sent"] is False
            assert report["gate"]["reason_code"] == "vendor_blocklisted"
            denied = store.events_for(report["run_key"], type="gate.denied")[0]["payload"]
            assert (denied["action"], denied["reason_code"]) == ("DENY", "vendor_blocklisted")  # 判据2
            checks.assert_stream_tail(store, report["run_key"], ("gate.checked", "gate.denied", "advice.drafted"))
            checks.assert_zero_payments(store, graph.PaymentLedger.day_aggregate(TODAY))  # 判据4
            completed = service.log.snapshot()[-1]
            assert completed["event"] == "run.completed" and completed["data"]["paid_cents"] is None


# ---- 支撑测试：四层合体的两个横向证据（L5.4 test_final 原样迁入）----


def test_gate_node_changes_signature_and_run_key(tmp_path) -> None:
    """图签名变化→run_key 变化（L5.3 图版本绑定在毕业件里的存活证据）：
    加一个节点（extra_stamp）签名必变，同一单据换图即换 run_key、旧聚合不可续。"""
    with_default = versioning.topology_signature(graph.build_graph(demo.model_for_url("http://x/v1")))
    with_stamp = versioning.topology_signature(graph.build_graph(demo.model_for_url("http://x/v1"), extra_stamp=True))
    assert with_default != with_stamp  # +1 节点：签名必变
    assert versioning.run_key("CLM-2026-0001", with_default) != versioning.run_key("CLM-2026-0001", with_stamp)
    assert versioning.run_key("CLM-2026-0001", with_default).startswith("CLM-2026-0001@")
    with pytest.raises(versioning.GraphVersionMismatch):
        versioning.assert_compatible(with_default, with_stamp)  # 旧 key 续新图：拒绝


async def test_reaudited_run_appends_gate_events_and_cache_hits(tmp_path: Path) -> None:
    """统一审计出口（demo.run_audited）：门事件进事件流、第二遍缓存全命中（零请求）且事件照常追加。"""
    db = tmp_path / "audited.db"
    first = await demo.run_audited("CLM-2026-0001", db, clock=lambda: CLOCK)
    assert first["requests"] == 2  # planner + drafter 各一次真实调用
    with eventstore.connect(db, clock=lambda: CLOCK) as store:
        types = [row["type"] for row in store.events_for(first["run_key"])]
        assert types[-3:] == ["submitted", "gate.checked", "payment.executed"]
        assert store.events_for(graph.PaymentLedger.day_aggregate(TODAY), type="payment.executed")
    second = await demo.run_audited("CLM-2026-0001", db, clock=lambda: CLOCK)
    assert second["requests"] == 0  # 缓存全命中——第二遍想花钱都没门
    assert second["run_key"] == first["run_key"]  # 同图同单：run_key 稳定
    with eventstore.connect(db, clock=lambda: CLOCK) as store:
        rows = store.events_for(first["run_key"])
        assert [row["type"] for row in rows].count("payment.executed") == 2  # 自动批准又付了一遍
        assert len(store.events_for(first["run_key"], type="run.started")) == 2  # 两次出生证明


# ---- meta：毕业判据清单与断言逐条对齐（清单不是文案，是合同）----

# 每条判据 = (关键词, 取证探针)：关键词必须在对应测试的 docstring 里，探针（断言表达式
# 片段）必须出现在本文件源码里——删断言不删判据、或删判据不删断言，meta 当场红。
GRADUATION_CRITERIA: dict[str, list[tuple[str, str]]] = {
    "test_link_one_pause_resume_pays_and_audits": [
        ("interrupt 暂停在 submit", 'ticket["graph_next"] == ["submit"]'),
        ("过门付款", 'report["paid_cents"] == 7100'),
        ("事件顺序", '("submitted", "gate.checked", "payment.executed")'),
        ("seq 连续", "checks.assert_stream_tail"),
        ("双落账", "graph.PaymentLedger.day_aggregate"),
    ],
    "test_link_two_reject_loop_regenerates_new_hash_then_pays": [
        ("ticket_id 变", 'second["ticket_id"] != first["ticket_id"]'),
        ("content_hash 变化", "checks.assert_hash_rotated"),
        ("两条 advice.drafted", 'types.count("advice.drafted") == 2'),
        ("权威在审批面", 'types[-1] == "payment.executed"'),
    ],
    "test_link_three_tight_policy_pauses_without_payment": [
        ("8800 > 5000", "TIGHT_POLICY.max_single_cents"),
        ("PAUSE_FOR_REAUTH", 'report["gate"]["reason_code"] == "single_over_limit"'),
        ("REJECT:GATE_REAUTH_REQUIRED", "graph.ESCALATE_REAUTH_REASON"),
        ("gate.checked → gate.denied → advice.drafted", '("gate.checked", "gate.denied", "advice.drafted")'),
        ("账本零记录", "checks.assert_zero_payments"),
    ],
    "test_link_three_blocklist_denies_without_payment": [
        ("vendor_blocklist", "BLOCKLIST_POLICY"),
        ("DENY/vendor_blocklisted", '("DENY", "vendor_blocklisted")'),
        ("REJECT:GATE_DENIED", "graph.ESCALATE_GATE_REASON"),
        ("账本零记录", "checks.assert_zero_payments"),
    ],
}


def test_criteria_docstrings_aligned_with_assertions() -> None:
    """meta：三链路四张测试的「毕业判据清单」docstring 与断言逐条对齐（L0.1 ex2 覆盖型先例）。

    覆盖维度逐维断言：链路齐（四张测试都在 GRADUATION_CRITERIA 里）、每链路的判据逐条
    有关键词（docstring 承诺兑现）、逐条有取证探针（断言真实存在）——数量词与断言同口径
    （宪法 §4「三方对齐」的毕业版）。
    """
    source = Path(__file__).read_text(encoding="utf-8")
    link_tests = [name for name in globals() if name.startswith("test_link_")]
    assert set(link_tests) == set(GRADUATION_CRITERIA)  # 链路测试与判据清单一一对应，不多不少
    for name, criteria in GRADUATION_CRITERIA.items():
        doc = inspect.getdoc(globals()[name]) or ""
        assert doc, f"{name} 缺毕业判据清单 docstring"
        for keyword, probe in criteria:
            assert keyword in doc, f"{name}：判据「{keyword}」没写进 docstring"
            assert probe in source, f"{name}：判据「{keyword}」缺取证断言（找不到 {probe}）"
