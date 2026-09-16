"""练习 3 验收（不要改本文件——它就是你的判卷老师）。

对账生命周期 + 重发零次断言（对版产品 test_sdk_order_gate 的「重启不重发」思想：
MockBroker 注入故障，数 pay 调用次数）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import ex3_reconcile as ex3
from broker import BrokerUnavailable, MockBroker
from enforcement import PaymentIntent
from gate import PaymentGate
from halt import HaltSentinel

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
GOOD_INTENT = PaymentIntent(payee="airline-co", category="travel", amount_cents=90_000)
BAD_INTENT = PaymentIntent(payee="sketchy-mall", category="travel", amount_cents=50_000)


def fixed_clock() -> datetime:
    return NOW


def write_mandate(path: Path) -> Path:
    """用户侧写合同（授权写入在受信面——mandate 模块没有 save_mandate）。"""
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "hard_caps": {
                    "max_single_payment_cents": 200_000,
                    "max_daily_total_cents": 500_000,
                    "max_payments_per_day": 3,
                },
                "universe": {
                    "allowed_categories": ["travel", "office_supplies", "training"],
                    "excluded_vendors": ["sketchy-mall"],
                },
                "consent": {
                    "consent_token_sha256": "sha256:test",
                    "created_at": (NOW - timedelta(days=3)).isoformat(),
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def gate_of(tmp_path: Path, broker: MockBroker) -> PaymentGate:
    return PaymentGate(write_mandate(tmp_path / "mandate.json"), HaltSentinel(tmp_path), broker, clock=fixed_clock)


def make_world(tmp_path: Path, broker: MockBroker, *, crash_after_marker: bool = False) -> ex3.PendingPaymentManager:
    return ex3.PendingPaymentManager(tmp_path, crash_after_marker=crash_after_marker)


def test_normal_flow_pays_exactly_once_and_closes_window(tmp_path: Path) -> None:
    broker = MockBroker()
    manager = make_world(tmp_path, broker)
    outcome = manager.pay_with_safety(gate_of(tmp_path, broker), broker, GOOD_INTENT)
    assert outcome.status == "PAID" and outcome.receipt is not None
    assert outcome.ref_id is not None and outcome.ref_id.startswith("pay-")
    assert broker.pay_calls == [outcome.ref_id]  # 恰好一次
    assert not manager.has_pending()  # 窗口关闭


def test_gate_refusal_never_touches_broker(tmp_path: Path) -> None:
    broker = MockBroker()
    manager = make_world(tmp_path, broker)
    outcome = manager.pay_with_safety(gate_of(tmp_path, broker), broker, BAD_INTENT)  # 黑名单
    assert outcome.status == "REFUSED" and outcome.verdict is not None
    assert outcome.verdict.decision == "DENY"
    assert broker.pay_calls == []  # 零写调用
    assert not manager.has_pending()  # 没留下未决标记


def test_recovery_with_evidence_closes_window_without_resend(tmp_path: Path) -> None:
    broker = MockBroker(failure="arrived_unconfirmed")  # 款到、确认丢
    manager = make_world(tmp_path, broker)
    with pytest.raises(BrokerUnavailable):
        manager.pay_with_safety(gate_of(tmp_path, broker), broker, GOOD_INTENT)
    assert manager.has_pending()  # 崩溃现场：标记在盘
    result = manager.reconcile_pending(broker)
    assert result.status == "RESOLVED_BY_EVIDENCE"
    assert result.evidence is not None and result.evidence["ref_id"] == result.ref_id
    assert not manager.has_pending()  # 证据关窗
    assert len(broker.pay_calls) == 1  # 全程恰好一次——零重发


def test_no_evidence_retains_marker_and_blocks_new_payment(tmp_path: Path) -> None:
    broker = MockBroker(failure="unreachable")  # 款根本没到
    manager = make_world(tmp_path, broker)
    with pytest.raises(BrokerUnavailable):
        manager.pay_with_safety(gate_of(tmp_path, broker), broker, GOOD_INTENT)
    result = manager.reconcile_pending(broker)
    assert result.status == "NEEDS_MANUAL_REVIEW" and result.evidence is None
    assert manager.has_pending()  # 标记保留
    fresh = MockBroker()
    blocked = manager.pay_with_safety(gate_of(tmp_path, fresh), fresh, GOOD_INTENT)
    assert blocked.status == "REFUSED" and fresh.pay_calls == []  # 窗口内拒绝新付款
    assert len(broker.pay_calls) == 1  # 重发零次断言


def test_crash_after_marker_never_reaches_broker(tmp_path: Path) -> None:
    broker = MockBroker()
    manager = make_world(tmp_path, broker, crash_after_marker=True)
    with pytest.raises(ex3.SimulatedCrash):
        manager.pay_with_safety(gate_of(tmp_path, broker), broker, GOOD_INTENT)
    assert manager.has_pending() and broker.pay_calls == []  # pay 根本没发生
    result = manager.reconcile_pending(broker)
    assert result.status == "NEEDS_MANUAL_REVIEW"  # 无证据：等人，不重发
    assert broker.pay_calls == []  # 重发零次——要不要补付，人说了算
