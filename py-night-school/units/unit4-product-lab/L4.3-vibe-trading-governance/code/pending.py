"""对账不重发（crash-safe 副作用标记 + 精确身份对账）——对版
HKUDS/Vibe-Trading@f84b2977#agent/src/live/pending_action.py 与 sdk_order_gate.py#_allow。

产品在下单前的顺序（sdk_order_gate._allow）：**先落盘 crash-safe 的 pending 标记**
（new_pending_order + save_pending_action；落盘失败 → DENY，**零券商调用**），然后才
place_order（带 client_order_id 幂等键）。崩溃重启后拿券商证据对账——产品 runner.py
原话：「reconciliation, not re-send, closes the cross-restart double-trade hole」；
pending_action 的恢复纪律是 "Resolve ... by exact identity, never by resubmission"：
get_order_by_client_order_id 查得到 → 审计后关闭窗口；查不到 → 标记保留、人工介入；
**mutation 调用永不自动重试**（repeatable=False）。

为什么是「先标记后提交」而不是反过来：标记写失败时你还没碰外部世界（安全地拒）；
顺序反过来，崩溃窗口里就存在「款已付出、本地毫无记录」的区间——对账连 ref_id 都
不知道，双倍付款的大门就开了。

付款域映射：client_order_id → ref_id；「已有未决标记时拒绝新付款」对版产品的
pending 窗口语义；「日计数只在确认执行后消耗」对版 increment_daily_count 只在
broker 返回非 error 时执行（本课日次数从通道已付清单推导，天然只含确认执行的单）。
"""

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

_MARKER_FILENAME = "pending_payment.json"


class SimulatedCrash(RuntimeError):
    """教学用的「进程死亡」：标记落盘后、broker.pay 前的确定性故障点（ex3 用它练对账）。"""


@dataclass(frozen=True)
class PayOutcome:
    """pay_with_safety 的返回（只在「有礼貌地结束」时返回；崩溃以异常上抛）。

    Attributes:
        status: ``"PAID"``（已执行并确认）/ ``"REFUSED"``（任何一步拒绝）。
        detail: 人类可读说明。
        ref_id: 本次幂等键（REFUSED 时可能为 None——还没走到生成那步）。
        verdict: 被门拒绝时附带的裁决（审计取证）。
        receipt: PAID 时的通道回执。
    """

    status: str
    detail: str
    ref_id: str | None = None
    verdict: Verdict | None = None
    receipt: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ReconcileResult:
    """reconcile_pending 的返回（对版产品恢复路径的三分支）。

    Attributes:
        status: ``"NO_PENDING"``（无窗口）/ ``"RESOLVED_BY_EVIDENCE"``（有证据，已关窗）/
            ``"NEEDS_MANUAL_REVIEW"``（无证据，标记保留——绝不重发）。
        ref_id: 未决标记的幂等键。
        detail: 说明（落审计）。
        evidence: 关窗依据的通道回执（RESOLVED_BY_EVIDENCE 时）。
    """

    status: str
    ref_id: str | None
    detail: str
    evidence: Mapping[str, Any] | None = None


class PendingPaymentManager:
    """先标记后提交 + 对账不重发（对版产品 pending_action 的教学单通道版）。

    Args:
        state_dir: 标记文件目录（一般与 HALT 哨兵同层）。
        crash_after_marker: True 时在标记成功落盘之后、broker.pay 之前抛
            :class:`SimulatedCrash`——模拟「进程死在最有意思的窗口里」（ex3 的故障注入）。
    """

    def __init__(self, state_dir: Path, *, crash_after_marker: bool = False) -> None:
        self._state_dir = state_dir
        self._crash_after_marker = crash_after_marker

    @property
    def marker_path(self) -> Path:
        return self._state_dir / _MARKER_FILENAME

    def has_pending(self) -> bool:
        """是否处于未决窗口（有标记 = 有未对账的副作用）。"""
        return self.marker_path.exists()

    def pay_with_safety(self, gate: PaymentGate, broker: Broker, intent: PaymentIntent) -> PayOutcome:
        """安全付款：门裁决 → 先落盘标记 → 再提交；任何异常都**不自动重试**。

        - 已有未决标记：直接 REFUSED（未决窗口里绝不发新付款）；
        - 门拒绝：REFUSED（附裁决），零 broker 写调用；
        - 标记落盘失败：REFUSED，**零 broker.pay 调用**（对版产品 persist 失败 → DENY）；
        - crash_after_marker：落盘成功后抛 SimulatedCrash（进程死亡，标记留在盘上）；
        - broker.pay 抛异常：异常上抛、标记保留——恢复只走 reconcile_pending，
          本方法**永不重试**（对版 mutation repeatable=False）。
        """
        if self.has_pending():
            return PayOutcome(status="REFUSED", detail="pending window open — reconcile first")

        verdict = gate.decide(intent)
        if verdict.decision != "ALLOW":
            return PayOutcome(
                status="REFUSED",
                detail=f"gate refused: {verdict.reason}",
                verdict=verdict,
            )

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

        receipt = broker.pay(intent, ref_id)  # 异常上抛：恢复只走 reconcile，绝不在此重试
        self._clear_marker()
        return PayOutcome(status="PAID", detail="payment executed and confirmed", ref_id=ref_id, receipt=receipt)

    def reconcile_pending(self, broker: Broker) -> ReconcileResult:
        """崩溃恢复：按 ref_id 精确身份对账——**绝不重发**（本方法零 broker.pay 调用）。

        有证据（get_payment_by_ref 查到）→ 审计后关闭窗口（删标记）；
        无证据（含取证本身失败）→ 标记保留，NEEDS_MANUAL_REVIEW 等人——
        「Resolve by exact identity, never by resubmission」。
        """
        if not self.has_pending():
            return ReconcileResult("NO_PENDING", None, "no pending marker on disk")
        marker = self._read_marker()
        if marker is None:
            # 标记在但读不出：状态不可信——按无证据处理，走人工，标记保留。
            return ReconcileResult("NEEDS_MANUAL_REVIEW", None, "marker unreadable — manual review required")
        ref_id = str(marker["ref_id"])

        try:
            evidence = broker.get_payment_by_ref(ref_id)
        except Exception:  # noqa: BLE001 - 取证失败 = 无证据，fail-closed 走人工（不重发）
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
            "NEEDS_MANUAL_REVIEW",
            ref_id,
            "no broker evidence — manual review required; never resubmit",
        )

    # ---- 标记文件原语（crash-safe 写：tmp + os.replace，对版产品 save_pending_action）----

    def _write_marker_atomic(self, ref_id: str, intent: PaymentIntent) -> None:
        """原子落盘标记：tmp 写满再 os.replace——读者要么看不到、要么看到完整标记。"""
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
        """读标记；不存在/损坏 → None（损坏等价于「状态不可信」，恢复走人工）。"""
        try:
            data = json.loads(self.marker_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) and "ref_id" in data else None

    def _clear_marker(self) -> None:
        try:
            self.marker_path.unlink()
        except FileNotFoundError:
            pass
