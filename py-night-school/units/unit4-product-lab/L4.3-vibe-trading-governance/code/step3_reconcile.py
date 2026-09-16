"""Step3：对账不重发三幕——正常付款 / 崩溃恢复（证据关窗）/ 无证据阻断。

用法：uv run python code/step3_reconcile.py
（写进系统临时目录，跑完即弃。）
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from broker import BrokerUnavailable, MockBroker
from enforcement import PaymentIntent
from gate import PaymentGate
from halt import HaltSentinel
from pending import PendingPaymentManager

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    """固定钟：脚本的「现在」焊死，输出可复现（测试同款，见 test_demo.py）。"""
    return NOW


def build_workspace(root: Path) -> tuple[Path, HaltSentinel]:
    """用户侧写合同（授权写入在受信面——agent 侧模块没有 save_mandate）。"""
    mandate_path = root / "mandate.json"
    mandate_path.write_text(
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
                    "consent_token_sha256": "sha256:consent-demo",
                    "created_at": (NOW - timedelta(days=3)).isoformat(),
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return mandate_path, HaltSentinel(root)


def make_gate(mandate_path: Path, broker: MockBroker) -> PaymentGate:
    return PaymentGate(mandate_path, HaltSentinel(mandate_path.parent), broker, clock=fixed_clock)


def main() -> None:
    print("== Step3 对账不重发：先标记后提交，按 ref_id 精确身份对账，绝不重发 ==\n")
    intent = PaymentIntent(payee="airline-co", category="travel", amount_cents=90_000)

    with tempfile.TemporaryDirectory(prefix="l43-pending-") as tmp:
        print("[幕1 正常付款：门 ALLOW → 标记落盘 → broker.pay → 删标记]")
        mandate_path, _ = build_workspace(Path(tmp))
        broker = MockBroker()
        manager = PendingPaymentManager(Path(tmp))
        outcome = manager.pay_with_safety(make_gate(mandate_path, broker), broker, intent)
        print(f"  status={outcome.status} ref_id={outcome.ref_id}")
        print(f"  broker.pay 调用 {len(broker.pay_calls)} 次；未决标记残留={manager.has_pending()}\n")

    with tempfile.TemporaryDirectory(prefix="l43-pending-") as tmp:
        print("[幕2 崩溃恢复：款项已到达但确认丢失 → 证据关窗]")
        mandate_path, _ = build_workspace(Path(tmp))
        broker = MockBroker(failure="arrived_unconfirmed")
        manager = PendingPaymentManager(Path(tmp))
        try:
            manager.pay_with_safety(make_gate(mandate_path, broker), broker, intent)
        except BrokerUnavailable as exc:
            print(f"  崩溃现场: {exc}")
        print(f"  重启前: 标记在盘={manager.has_pending()} broker.pay 调用 {len(broker.pay_calls)} 次")
        result = manager.reconcile_pending(broker)
        print(f"  reconcile: status={result.status}")
        print(f"    evidence.ref_id={result.evidence['ref_id'] if result.evidence else None}")
        print(f"  重启后: 标记在盘={manager.has_pending()} broker.pay 仍 {len(broker.pay_calls)} 次（零重发）\n")

    with tempfile.TemporaryDirectory(prefix="l43-pending-") as tmp:
        print("[幕3 无证据阻断：broker 全程不可达 → 标记保留 + 拒绝新付款]")
        mandate_path, _ = build_workspace(Path(tmp))
        broker = MockBroker(failure="unreachable")
        manager = PendingPaymentManager(Path(tmp))
        try:
            manager.pay_with_safety(make_gate(mandate_path, broker), broker, intent)
        except BrokerUnavailable as exc:
            print(f"  崩溃现场: {exc}")
        result = manager.reconcile_pending(broker)
        print(f"  reconcile: status={result.status} detail='{result.detail}'")
        fresh_broker = MockBroker()
        blocked = manager.pay_with_safety(make_gate(mandate_path, fresh_broker), fresh_broker, intent)
        print(f"  未决窗口内新付款: status={blocked.status} detail='{blocked.detail}'")
        print(f"  全程 broker.pay 调用 {len(broker.pay_calls)} 次（零重发）——要不要补付，人说了算")


if __name__ == "__main__":
    main()
