"""付款门全 ceremony 端到端：合同加载 → HALT → 快照 → 检查链 → 三态 → 安全付款 → 哈希链审计。

用法：uv run python code/demo.py
（写进系统临时目录，跑完即弃。）

对照产品的一条完整实盘链路（sdk_order_gate.execute_live_order + live/audit.py 双写）：
每笔付款意图先过门拿三态裁决，裁决与执行事件全部进哈希链账本——「每一笔动钱的动作
都被记录、且记录改不了」。合同由 build_workspace 的「用户侧」写入（对版产品
commit_mandate 的受信面）；agent 侧模块（mandate.py）刻意没有 save_mandate。
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from broker import MockBroker
from enforcement import PaymentIntent
from gate import PaymentGate
from halt import HaltSentinel
from ledger import HashLedger
from mandate import load_mandate
from pending import PendingPaymentManager

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    return NOW


def build_workspace(root: Path) -> tuple[Path, HaltSentinel, Path]:
    """搭一个最小世界：用户侧合同 + HALT 哨兵 + 审计账本（都还没有事件）。"""
    root.mkdir(parents=True, exist_ok=True)
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
    return mandate_path, HaltSentinel(root), root / "audit_chain.jsonl"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="l43-demo-") as tmp:
        mandate_path, halt, ledger_path = build_workspace(Path(tmp))
        broker = MockBroker(
            opening_paid=[
                {
                    "ref_id": "pay-earlier1",
                    "payee": "stationery-co",
                    "category": "office_supplies",
                    "amount_cents": 60_000,
                },
            ]
        )
        gate = PaymentGate(mandate_path, halt, broker, clock=fixed_clock)
        ledger = HashLedger(ledger_path)
        manager = PendingPaymentManager(Path(tmp))

        print("== L4.3 付款门全 ceremony（报销付款域，整数分） ==")
        mandate = load_mandate(mandate_path)
        assert mandate is not None
        print(
            f"mandate 加载: 单笔≤{mandate.hard_caps.max_single_payment_cents} 分 "
            f"日累计≤{mandate.hard_caps.max_daily_total_cents} 分 "
            f"日次数≤{mandate.hard_caps.max_payments_per_day} "
            f"过期={mandate.consent.effective_expiry.isoformat()}"
        )
        print(f"today: 已付 1 笔 60000 分；now={NOW.isoformat()}\n")

        intents = [
            PaymentIntent(payee="airline-co", category="travel", amount_cents=90_000),
            PaymentIntent(payee="Sketchy-Mall", category="office_supplies", amount_cents=50_000),
            PaymentIntent(payee="training-co", category="training", amount_cents=480_000),
        ]
        print("[六步裁决 ×3]")
        allowed = None
        for intent in intents:
            verdict = gate.decide(intent)
            ledger.append(
                {
                    "event": "verdict",
                    "decision": verdict.decision,
                    "reason": verdict.reason,
                    "amount_cents": intent.amount_cents,
                    "payee": intent.payee,
                }
            )
            print(f"  {intent.payee:14} {intent.amount_cents:>7} 分 -> {verdict.decision:16} {verdict.reason}")
            if verdict.decision == "ALLOW":
                allowed = intent

        print("\n[ALLOW 者走安全付款（先标记后提交）]")
        assert allowed is not None
        outcome = manager.pay_with_safety(gate, broker, allowed)
        print(f"  status={outcome.status} ref_id={outcome.ref_id} 回执={dict(outcome.receipt or {})}")
        ledger.append(
            {
                "event": "payment",
                "ref_id": outcome.ref_id,
                "payee": allowed.payee,
                "amount_cents": allowed.amount_cents,
            }
        )

        print("\n[拉闸后再裁决一笔]")
        halt.trip(by="user", reason="财务例会：暂停自动付款")
        verdict = gate.decide(allowed)
        print(f"  HALT 存在 -> {verdict.decision}: {verdict.reason}")
        ledger.append({"event": "verdict", "decision": verdict.decision, "reason": verdict.reason})
        halt.clear()

        print("\n[审计账本]")
        for record in ledger.records():
            print(f"  seq={record['seq']} {record.get('event'):8} {record.get('decision', record.get('ref_id'))}")
        result = ledger.verify()
        print(f"  verify: ok={result.ok} record_count={result.record_count} —— 改任何一条，其后整条链都会断")


if __name__ == "__main__":
    main()
