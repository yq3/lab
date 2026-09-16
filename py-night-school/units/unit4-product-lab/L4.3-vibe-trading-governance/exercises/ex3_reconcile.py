# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""对账不重发：骨架给了标记文件原语与结果类型，你来写 pay_with_safety / reconcile_pending。

对版改造题：HKUDS/Vibe-Trading@f84b2977#agent/src/live/pending_action.py + sdk_order_gate.py#_allow
（讲义 code/pending.py 是完整版，可对照读）。两条命：
  先标记后提交——标记落盘失败时绝不能碰 broker（零 pay 调用）；反过来（先提交后标记）
    会留下「款已付出、本地无记录」的崩溃窗口；
  对账不重发——恢复只按 ref_id 精确身份取证（get_payment_by_ref），有证据关窗、无证据
    留标记等人；两个方法里都**绝不**出现第二次 broker.pay。

完成判据：uv run pytest exercises/test_ex3.py 全绿——五个测试：正常流恰好一次 broker.pay、
门拒绝零 broker 调用、崩溃后有证据关窗（pay 恰好一次）、无证据标记保留且新付款被拒、
标记后崩溃 pay 零次（重发零次断言）。
TODO 所需的顶部 import：uuid。
"""

from __future__ import annotations

import json
import os
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
    """先标记后提交 + 对账不重发（对版产品 pending_action 的教学单通道版）。

    Args:
        state_dir: 标记文件目录。
        crash_after_marker: True 时在标记成功落盘之后、broker.pay 之前抛 SimulatedCrash。
    """

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
        """安全付款：门裁决 → 先落盘标记 → 再提交；任何异常都**不自动重试**。

        TODO(ex3-a)：顺序是本题的题眼，逐个问自己——
          开工前先看什么（has_pending）？有未决窗口时该返回什么 status？
          门裁决不为 ALLOW 时返回什么（附上哪个字段给审计）？此时 broker 被碰了吗？
          ref_id 何时生成、标记何时落盘（形状参考文件头部的「两条命」）？落盘失败呢？
          crash_after_marker 置 True 时，在哪个点抛 SimulatedCrash 才对得起它的名字？
          broker.pay 之后、返回 PAID 之前，未决窗口该怎么收场？
        """
        # TODO(ex3-a): 按上面的顺序问一遍再写；本方法里 broker.pay 至多出现一次。
        raise NotImplementedError("TODO(ex3-a): 补全 pay_with_safety")

    def reconcile_pending(self, broker: Broker) -> ReconcileResult:
        """崩溃恢复：按 ref_id 精确身份对账——**绝不重发**。

        TODO(ex3-b)：两分支拿什么区分（get_payment_by_ref 的返回值长什么样）？
          无标记时返回哪个 status？标记在但读不出（_read_marker 为 None）呢——
          状态不可信时往「关窗」还是「人工」那边倒？
          查到证据时窗口怎么关（标记文件动不动）？查不到时标记呢？
          本方法里可以调用 broker 的哪个方法、绝不能调用哪个？
        """
        # TODO(ex3-b): 恢复=取证+决断，不是重试；这里的 broker 永远不该收到 pay。
        raise NotImplementedError("TODO(ex3-b): 补全 reconcile_pending")

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
