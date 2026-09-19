"""讲义区测试：检查链逐查单测 + 三态、门六步、账本篡改三连、对账生命周期、授权不可达不变量。

（对版思想来源：HKUDS/Vibe-Trading@f84b2977#agent/tests/test_mandate_enforcement.py 的
per-limit 用例、#agent/tests/test_governance.py 的篡改三连、#agent/tests/test_sdk_order_gate.py
的重启不重发。）
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import mandate as mandate_module
import pending as pending_module
from broker import BrokerUnavailable, MockBroker
from enforcement import (
    BREACH_KIND_QUANTITATIVE,
    BREACH_KIND_STRUCTURAL,
    PaymentIntent,
    TodaySnapshot,
    check_payment,
)
from gate import PaymentGate
from halt import HaltSentinel
from ledger import GENESIS_PREV_HASH, HashLedger, LedgerCorruptionError, canonical_json, compute_record_hash
from mandate import ConsentMeta, HardCaps, PayMandate, PayUniverse, load_mandate
from pending import PendingPaymentManager

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    return NOW


BASE_MANDATE = PayMandate(
    schema_version=1,
    hard_caps=HardCaps(max_single_payment_cents=200_000, max_daily_total_cents=500_000, max_payments_per_day=3),
    universe=PayUniverse(
        allowed_categories=("travel", "office_supplies", "training"), excluded_vendors=("sketchy-mall",)
    ),
    consent=ConsentMeta(consent_token_sha256="sha256:test", created_at=NOW - timedelta(days=3)),
)

GOOD_INTENT = PaymentIntent(payee="airline-co", category="travel", amount_cents=90_000)
EMPTY_TODAY = TodaySnapshot(now=NOW, paid=())


def write_mandate_json(path: Path, mandate: PayMandate) -> Path:
    """用户侧写合同（对版 commit_mandate 的受信面；agent 侧模块没有 save_mandate）。"""
    path.write_text(
        json.dumps(
            {
                "schema_version": mandate.schema_version,
                "hard_caps": {
                    "max_single_payment_cents": mandate.hard_caps.max_single_payment_cents,
                    "max_daily_total_cents": mandate.hard_caps.max_daily_total_cents,
                    "max_payments_per_day": mandate.hard_caps.max_payments_per_day,
                },
                "universe": {
                    "allowed_categories": list(mandate.universe.allowed_categories),
                    "excluded_vendors": list(mandate.universe.excluded_vendors),
                },
                "consent": {
                    "consent_token_sha256": mandate.consent.consent_token_sha256,
                    "created_at": mandate.consent.created_at.isoformat(),
                    "expires_at": mandate.consent.effective_expiry.isoformat(),
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def make_gate(tmp_path: Path, broker: MockBroker, mandate: PayMandate = BASE_MANDATE) -> PaymentGate:
    return PaymentGate(
        write_mandate_json(tmp_path / "mandate.json", mandate),
        HaltSentinel(tmp_path),
        broker,
        clock=fixed_clock,
    )


# ---------- mandate：加载与「授权不可达」 ----------


def test_mandate_roundtrip_and_default_expiry_30_days(tmp_path: Path) -> None:
    path = write_mandate_json(tmp_path / "mandate.json", BASE_MANDATE)
    loaded = load_mandate(path)
    assert loaded is not None
    assert loaded == BASE_MANDATE
    assert loaded.consent.effective_expiry == BASE_MANDATE.consent.created_at + timedelta(days=30)  # 不许永生


def test_mandate_load_fail_closed(tmp_path: Path) -> None:
    assert load_mandate(tmp_path / "absent.json") is None  # 文件缺失
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_mandate(broken) is None  # JSON 损坏
    missing_field = tmp_path / "missing.json"
    missing_field.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    assert load_mandate(missing_field) is None  # 字段缺失
    future = tmp_path / "future.json"
    future.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    assert load_mandate(future) is None  # 未知未来版本


def test_no_save_mandate_authorization_unreachable() -> None:
    # 授权不可达（产品的「命门不变量」）：agent 侧模块只有 load，没有写路径可调。
    assert not hasattr(mandate_module, "save_mandate")
    assert not hasattr(mandate_module, "write_mandate")
    assert [n for n in dir(mandate_module) if n.startswith("save")] == []


# ---------- enforcement：七查逐查单测（只破这一项） ----------


def test_check0_intent_shapes_are_structural_breach() -> None:
    for bad in (
        PaymentIntent(payee="", category="travel", amount_cents=100),  # 收款方空
        PaymentIntent(payee="airline-co", category=" ", amount_cents=100),  # 科目空白
        PaymentIntent(payee="airline-co", category="travel", amount_cents=0),  # 金额非正
        PaymentIntent(payee="airline-co", category="travel", amount_cents=-5),
    ):
        breach = check_payment(BASE_MANDATE, bad, EMPTY_TODAY)
        assert breach is not None and breach.kind == BREACH_KIND_STRUCTURAL and breach.limit == "payment_intent"


def test_check0_float_and_bool_amounts_are_unparseable() -> None:
    for bad_amount in (99.0, "90000", True):
        intent = PaymentIntent(payee="a", category="travel", amount_cents=bad_amount)  # type: ignore[arg-type]
        breach = check_payment(BASE_MANDATE, intent, EMPTY_TODAY)
        assert breach is not None and breach.limit == "payment_intent"  # 宁拒不放（bool 是 int 子类也不行）


def test_check1_excluded_vendor_is_structural() -> None:
    intent = PaymentIntent(payee="Sketchy-Mall", category="travel", amount_cents=100)
    breach = check_payment(BASE_MANDATE, intent, EMPTY_TODAY)
    assert breach is not None
    assert (breach.kind, breach.limit) == (BREACH_KIND_STRUCTURAL, "excluded_vendors")


def test_check2_category_whitelist_empty_denies_all() -> None:
    deny_all = replace(BASE_MANDATE, universe=PayUniverse(allowed_categories=(), excluded_vendors=("sketchy-mall",)))
    breach = check_payment(deny_all, PaymentIntent(payee="a", category="travel", amount_cents=100), EMPTY_TODAY)
    assert breach is not None and breach.limit == "allowed_categories"
    good = check_payment(BASE_MANDATE, PaymentIntent(payee="a", category="Training", amount_cents=100), EMPTY_TODAY)
    assert good is None  # 白名单大小写归一后放行


def test_check3_single_payment_cap_is_quantitative() -> None:
    breach = check_payment(BASE_MANDATE, PaymentIntent(payee="a", category="travel", amount_cents=200_001), EMPTY_TODAY)
    assert breach is not None
    assert (breach.kind, breach.limit, breach.attempted_cents) == (
        BREACH_KIND_QUANTITATIVE,
        "max_single_payment_cents",
        200_001,
    )


def test_check4_daily_total_counts_paid_plus_attempt() -> None:
    paid = tuple({"payee": "a", "category": "travel", "amount_cents": 420_000} for _ in range(1))
    today = TodaySnapshot(now=NOW, paid=paid)
    breach = check_payment(BASE_MANDATE, PaymentIntent(payee="b", category="travel", amount_cents=90_000), today)
    assert breach is not None
    assert (breach.kind, breach.limit, breach.attempted_cents) == (
        BREACH_KIND_QUANTITATIVE,
        "max_daily_total_cents",
        510_000,
    )


def test_check4_dirty_paid_list_fails_closed() -> None:
    dirty = TodaySnapshot(now=NOW, paid=({"payee": "a", "category": "travel"},))  # 缺 amount_cents
    breach = check_payment(BASE_MANDATE, PaymentIntent(payee="b", category="travel", amount_cents=100), dirty)
    assert breach is not None and breach.limit == "max_daily_total_cents"
    assert "fail-closed" in breach.detail


def test_check5_daily_count_only_counts_confirmed() -> None:
    paid = tuple({"payee": f"v{i}", "category": "travel", "amount_cents": 100} for i in range(3))
    today = TodaySnapshot(now=NOW, paid=paid)  # 已确认 3 笔 = 到达次数上限
    breach = check_payment(BASE_MANDATE, PaymentIntent(payee="b", category="travel", amount_cents=100), today)
    assert breach is not None and breach.limit == "max_payments_per_day"
    two = TodaySnapshot(now=NOW, paid=paid[:2])
    assert check_payment(BASE_MANDATE, PaymentIntent(payee="b", category="travel", amount_cents=100), two) is None


def test_check6_mandate_expiry_is_structural() -> None:
    # replace 会重走 __post_init__：expires_at 显式置 None 才会按新 created_at 重取 30 天默认。
    expired = replace(
        BASE_MANDATE, consent=replace(BASE_MANDATE.consent, created_at=NOW - timedelta(days=31), expires_at=None)
    )
    breach = check_payment(expired, GOOD_INTENT, EMPTY_TODAY)
    assert breach is not None and breach.limit == "mandate_expiry"
    assert breach.kind == BREACH_KIND_STRUCTURAL
    fresh = replace(BASE_MANDATE, consent=replace(BASE_MANDATE.consent, created_at=NOW, expires_at=None))
    assert check_payment(fresh, GOOD_INTENT, EMPTY_TODAY) is None  # created 今天：未过期


def test_all_clear_returns_none_allow() -> None:
    assert check_payment(BASE_MANDATE, GOOD_INTENT, EMPTY_TODAY) is None


def test_blacklist_short_circuits_before_single_cap() -> None:
    # 同时违反黑名单（第 1 查）与单笔上限（第 3 查）：首查命中即停——固定顺序是合同的一部分。
    breach = check_payment(
        BASE_MANDATE, PaymentIntent(payee="sketchy-mall", category="travel", amount_cents=999_999), EMPTY_TODAY
    )
    assert breach is not None and breach.limit == "excluded_vendors"


# ---------- gate：六步 ceremony ----------


def test_gate_allow_end_to_end(tmp_path: Path) -> None:
    gate = make_gate(tmp_path, MockBroker())
    verdict = gate.decide(GOOD_INTENT)
    assert (verdict.decision, verdict.breach, verdict.reason) == ("ALLOW", None, "payment in mandate")


def test_gate_deny_when_no_valid_mandate(tmp_path: Path) -> None:
    gate = PaymentGate(tmp_path / "absent.json", HaltSentinel(tmp_path), MockBroker(), clock=fixed_clock)
    verdict = gate.decide(GOOD_INTENT)
    assert verdict.decision == "DENY" and verdict.reason == "no valid mandate on file"


def test_gate_deny_expired_mandate(tmp_path: Path) -> None:
    expired = replace(
        BASE_MANDATE, consent=replace(BASE_MANDATE.consent, created_at=NOW - timedelta(days=40), expires_at=None)
    )
    verdict = make_gate(tmp_path, MockBroker(), expired).decide(GOOD_INTENT)
    assert verdict.decision == "DENY" and "expired" in verdict.reason


def test_gate_deny_when_halt_tripped_even_with_corrupt_payload(tmp_path: Path) -> None:
    halt = HaltSentinel(tmp_path)
    gate = PaymentGate(write_mandate_json(tmp_path / "m.json", BASE_MANDATE), halt, MockBroker(), clock=fixed_clock)
    halt.trip(by="user", reason="test")
    assert gate.decide(GOOD_INTENT).reason == "payments halted (kill switch tripped)"
    halt.clear()
    halt.path.write_text("not json at all", encoding="utf-8")  # 损坏 payload
    assert halt.tripped() is True  # 存在性即停机（fail-closed）
    assert gate.decide(GOOD_INTENT).decision == "DENY"


def test_gate_deny_when_broker_snapshot_unreadable(tmp_path: Path) -> None:
    class UnreadableBroker(MockBroker):
        def today_payments(self) -> list[dict]:
            raise BrokerUnavailable("read tool down")

    verdict = make_gate(tmp_path, UnreadableBroker()).decide(GOOD_INTENT)
    assert verdict.decision == "DENY" and "fail-closed" in verdict.reason


def test_gate_three_states_route_by_breach_kind(tmp_path: Path) -> None:
    gate = make_gate(tmp_path, MockBroker())
    assert gate.decide(GOOD_INTENT).decision == "ALLOW"
    structural = gate.decide(PaymentIntent(payee="sketchy-mall", category="travel", amount_cents=100))
    assert structural.decision == "DENY" and structural.breach is not None
    assert structural.breach.kind == BREACH_KIND_STRUCTURAL
    quantitative = gate.decide(PaymentIntent(payee="a", category="travel", amount_cents=250_000))
    assert quantitative.decision == "PAUSE_FOR_REAUTH" and quantitative.breach is not None
    assert quantitative.breach.kind == BREACH_KIND_QUANTITATIVE


# ---------- ledger：篡改三连 + canonical json ----------


def test_ledger_append_grows_and_verifies(tmp_path: Path) -> None:
    ledger = HashLedger(tmp_path / "chain.jsonl")
    first = ledger.append({"event": "payment", "amount_cents": 100})
    assert (first["seq"], first["prev_record_hash"]) == (1, GENESIS_PREV_HASH)
    second = ledger.append({"event": "payment", "amount_cents": 200})
    assert second["prev_record_hash"] == first["record_hash"]
    result = ledger.verify()
    assert result.ok and result.record_count == 2


def test_ledger_tamper_edit_is_pinpointed(tmp_path: Path) -> None:
    ledger = HashLedger(tmp_path / "chain.jsonl")
    for amount in (100, 200, 300):
        ledger.append({"event": "payment", "amount_cents": amount})
    path = tmp_path / "chain.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["amount_cents"] = 1  # 审计记录被事后改小
    lines[1] = json.dumps(record, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = ledger.verify()
    assert not result.ok and result.first_break is not None
    assert (result.first_break.index, result.first_break.reason) == (1, "hash mismatch")


def test_ledger_tamper_delete_middle_is_detected(tmp_path: Path) -> None:
    ledger = HashLedger(tmp_path / "chain.jsonl")
    for amount in (100, 200, 300):
        ledger.append({"event": "payment", "amount_cents": amount})
    path = tmp_path / "chain.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]  # 删中间条
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = ledger.verify()
    assert not result.ok
    assert result.first_break is not None and result.first_break.reason in ("seq gap", "prev mismatch")


def test_ledger_self_fixing_tamper_caught_downstream(tmp_path: Path) -> None:
    ledger = HashLedger(tmp_path / "chain.jsonl")
    for amount in (100, 200, 300):
        ledger.append({"event": "payment", "amount_cents": amount})
    path = tmp_path / "chain.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["amount_cents"] = 1
    payload = {k: v for k, v in record.items() if k not in ("seq", "prev_record_hash", "record_hash")}
    record["record_hash"] = compute_record_hash(record["seq"], record["prev_record_hash"], payload)
    lines[1] = json.dumps(record, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = ledger.verify()
    assert not result.ok and result.first_break is not None
    assert (result.first_break.index, result.first_break.reason) == (2, "prev mismatch")  # 下一条出卖它


def test_ledger_refuses_to_extend_broken_chain(tmp_path: Path) -> None:
    ledger = HashLedger(tmp_path / "chain.jsonl")
    ledger.append({"event": "payment", "amount_cents": 100})
    path = tmp_path / "chain.jsonl"
    path.write_text("garbage\n", encoding="utf-8")  # 断链
    with pytest.raises(LedgerCorruptionError):
        ledger.append({"event": "payment", "amount_cents": 200})
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1  # 拒写：一个字节没多


def test_canonical_json_makes_key_order_irrelevant() -> None:
    # L4.1「相等不等哈希」的正解：先规范化再哈希——键序不同不影响结果。
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert compute_record_hash(1, GENESIS_PREV_HASH, {"b": 1, "a": 2}) == compute_record_hash(
        1, GENESIS_PREV_HASH, {"a": 2, "b": 1}
    )


# ---------- pending：先标记后提交 + 对账不重发 ----------


def test_pending_normal_flow_pays_exactly_once(tmp_path: Path) -> None:
    broker = MockBroker()
    manager = PendingPaymentManager(tmp_path)
    outcome = manager.pay_with_safety(make_gate(tmp_path, broker), broker, GOOD_INTENT)
    assert outcome.status == "PAID" and outcome.receipt is not None
    assert len(broker.pay_calls) == 1  # 恰好一次
    assert not manager.has_pending()  # 窗口关闭


def test_pending_gate_refusal_never_touches_broker(tmp_path: Path) -> None:
    broker = MockBroker()
    manager = PendingPaymentManager(tmp_path)
    outcome = manager.pay_with_safety(
        make_gate(tmp_path, broker), broker, PaymentIntent(payee="sketchy-mall", category="travel", amount_cents=100)
    )
    assert outcome.status == "REFUSED" and outcome.verdict is not None
    assert outcome.verdict.decision == "DENY"
    assert broker.pay_calls == []  # 零写调用
    assert not manager.has_pending()


def test_pending_marker_write_failure_blocks_payment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    broker = MockBroker()
    manager = PendingPaymentManager(tmp_path)

    def boom(self: PendingPaymentManager, ref_id: str, intent: PaymentIntent) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(PendingPaymentManager, "_write_marker_atomic", boom)
    outcome = manager.pay_with_safety(make_gate(tmp_path, broker), broker, GOOD_INTENT)
    assert outcome.status == "REFUSED" and "zero broker calls" in outcome.detail
    assert broker.pay_calls == []  # 标记落盘失败 → 零 broker 调用（对版 persist 失败 → DENY）


def test_pending_recovery_with_evidence_closes_window(tmp_path: Path) -> None:
    broker = MockBroker(failure="arrived_unconfirmed")
    manager = PendingPaymentManager(tmp_path)
    with pytest.raises(BrokerUnavailable):
        manager.pay_with_safety(make_gate(tmp_path, broker), broker, GOOD_INTENT)
    assert manager.has_pending()  # 崩溃现场：标记在盘
    result = manager.reconcile_pending(broker)
    assert result.status == "RESOLVED_BY_EVIDENCE"
    assert result.evidence is not None and result.evidence["ref_id"] == result.ref_id
    assert not manager.has_pending() and len(broker.pay_calls) == 1  # 证据关窗、零重发


def test_pending_without_evidence_keeps_marker_and_blocks_new(tmp_path: Path) -> None:
    broker = MockBroker(failure="unreachable")
    manager = PendingPaymentManager(tmp_path)
    with pytest.raises(BrokerUnavailable):
        manager.pay_with_safety(make_gate(tmp_path, broker), broker, GOOD_INTENT)
    result = manager.reconcile_pending(broker)
    assert result.status == "NEEDS_MANUAL_REVIEW" and result.evidence is None
    assert manager.has_pending()  # 标记保留
    fresh = MockBroker()
    blocked = manager.pay_with_safety(make_gate(tmp_path, fresh), fresh, GOOD_INTENT)
    assert blocked.status == "REFUSED" and fresh.pay_calls == []  # 窗口内拒绝新付款
    assert len(broker.pay_calls) == 1  # 全程恰好一次（崩溃前那次）


def test_pending_crash_after_marker_never_reaches_broker(tmp_path: Path) -> None:
    broker = MockBroker()
    manager = PendingPaymentManager(tmp_path, crash_after_marker=True)
    with pytest.raises(pending_module.SimulatedCrash):
        manager.pay_with_safety(make_gate(tmp_path, broker), broker, GOOD_INTENT)
    assert manager.has_pending() and broker.pay_calls == []  # pay 根本没发生
    result = manager.reconcile_pending(broker)
    assert result.status == "NEEDS_MANUAL_REVIEW"  # 无证据：等人，不重发
    assert broker.pay_calls == []  # 重发零次——要不要补付，人说了算
