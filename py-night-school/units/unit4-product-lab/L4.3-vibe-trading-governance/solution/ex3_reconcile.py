# 参考答案：ex3_reconcile（练习文件的完整解法——完成前别看）
"""对账不重发：pay_with_safety / reconcile_pending 见 TODO 原位。"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from broker import Broker
from enforcement import PaymentIntent
from gate import PaymentGate, Verdict

MARKER_FILENAME = "pending_payment.json"


class SimulatedCrash(RuntimeError):
    """教学用的「进程死亡」：标记落盘后、broker.pay 前的确定性故障点。"""


@dataclass(frozen=True)
class PayOutcome:
    """pay_with_safety 的返回（只在「有礼貌地结束」时返回；崩溃以异常上抛）。

    status: "PAID"（已执行并确认）/ "REFUSED"（任何一步拒绝）。
    """

    status: str
    detail: str
    ref_id: str | None = None
    verdict: Verdict | None = None
    receipt: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ReconcileResult:
    """reconcile_pending 的返回。

    status: "NO_PENDING"（无窗口）/ "RESOLVED_BY_EVIDENCE"（有证据，已关窗）/
        "NEEDS_MANUAL_REVIEW"（无证据，标记保留——绝不重发）。
    """

    status: str
    ref_id: str | None
    detail: str
    evidence: Mapping[str, Any] | None = None


class PendingPaymentManager:
    """先标记后提交 + 对账不重发（对版产品 pending_action 的教学单通道版）。"""

    def __init__(self, state_dir: Path, *, crash_after_marker: bool = False) -> None:
        self._state_dir = state_dir
        self._crash_after_marker = crash_after_marker

    @property
    def marker_path(self) -> Path:
        """已给：标记文件路径。"""
        return self._state_dir / MARKER_FILENAME

    def has_pending(self) -> bool:
        """已给：是否处于未决窗口（有标记 = 有未对账的副作用）。"""
        return self.marker_path.exists()

    def pay_with_safety(self, gate: PaymentGate, broker: Broker, intent: PaymentIntent) -> PayOutcome:
        """安全付款：门裁决 → 先落盘标记 → 再提交；任何异常都**不自动重试**。"""
        if self.has_pending():
            return PayOutcome(status="REFUSED", detail="pending window open — reconcile first")

        verdict = gate.decide(intent)
        if verdict.decision != "ALLOW":
            return PayOutcome(status="REFUSED", detail=f"gate refused: {verdict.reason}", verdict=verdict)

        ref_id = f"pay-{uuid.uuid4().hex}"
        try:
            self._write_marker_atomic(ref_id, intent)
        except OSError:
            return PayOutcome(
                status="REFUSED",
                detail="pending marker could not be persisted (zero broker calls)",
                ref_id=ref_id,
                verdict=verdict,
            )
        if self._crash_after_marker:
            raise SimulatedCrash(f"process died after marker persisted, before broker.pay (ref={ref_id})")

        receipt = broker.pay(intent, ref_id)  # 异常上抛：标记保留，恢复只走 reconcile
        self._clear_marker()
        return PayOutcome(status="PAID", detail="payment executed and confirmed", ref_id=ref_id, receipt=receipt)

    def reconcile_pending(self, broker: Broker) -> ReconcileResult:
        """崩溃恢复：按 ref_id 精确身份对账——**绝不重发**（零 broker.pay 调用）。"""
        if not self.has_pending():
            return ReconcileResult("NO_PENDING", None, "no pending marker on disk")
        marker = self._read_marker()
        if marker is None:
            return ReconcileResult("NEEDS_MANUAL_REVIEW", None, "marker unreadable — manual review required")
        ref_id = str(marker["ref_id"])

        try:
            evidence = broker.get_payment_by_ref(ref_id)
        except Exception:  # noqa: BLE001 - 取证失败 = 无证据，走人工（不重发）
            return ReconcileResult("NEEDS_MANUAL_REVIEW", ref_id, "evidence lookup failed — manual review required")

        if evidence is not None:
            self._clear_marker()
            return ReconcileResult(
                "RESOLVED_BY_EVIDENCE",
                ref_id,
                "window closed by exact identity (never resubmitted)",
                evidence=evidence,
            )
        return ReconcileResult(
            "NEEDS_MANUAL_REVIEW", ref_id, "no broker evidence — manual review required; never resubmit"
        )

    # ---- 标记文件原语（已给：crash-safe 写 = tmp 写满 + os.replace）----

    def _write_marker_atomic(self, ref_id: str, intent: PaymentIntent) -> None:
        """已给：原子落盘标记——读者要么看不到、要么看到完整标记。失败抛 OSError。"""
        payload = {
            "ref_id": ref_id,
            "intent": {"payee": intent.payee, "category": intent.category, "amount_cents": intent.amount_cents},
            "written_at": datetime.now(UTC).isoformat(),
        }
        self._state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.marker_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.marker_path)

    def _read_marker(self) -> dict[str, Any] | None:
        """已给：读标记；不存在/损坏/缺 ref_id → None。"""
        try:
            data = json.loads(self.marker_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) and "ref_id" in data else None

    def _clear_marker(self) -> None:
        """已给：删标记（关窗动作）。"""
        try:
            self.marker_path.unlink()
        except FileNotFoundError:
            pass
