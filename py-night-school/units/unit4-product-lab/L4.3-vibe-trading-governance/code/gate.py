"""付款门六步 ceremony——对版 HKUDS/Vibe-Trading@f84b2977#agent/src/live/sdk_order_gate.py#execute_live_order。

产品的下单门在**任何券商调用之前**走固定顺序：load_mandate（解析失败→DENY）→ 过期检查
（→DENY+reauth）→ halt 哨兵（→DENY）→ 意图提取/定价（不可定价→DENY）→ 读持仓/余额快照
（读失败→DENY）→ check_mandate → ALLOW / DENY / PAUSE_FOR_REAUTH 三态裁决。

本课 PaymentGate.decide 同构六步（金额是意图自带的，裁掉「实时报价定价」一步）：

  1 load_mandate：合同缺失/损坏 → DENY「no valid mandate on file」
  2 过期：expires_at 已到 → DENY「mandate expired — re-authorize」
  3 HALT 哨兵：存在（payload 损坏也算）→ DENY「payments halted」
  4 意图归一：字段类型/形状不对 → DENY「fail-closed」
  5 今日已付快照：向 Broker 读；读失败 → DENY「fail-closed」
  6 check_payment：None → ALLOW；structural → DENY；quantitative → PAUSE_FOR_REAUTH

注意第 5 步的 ``except Exception → DENY``：这不是 §5 陷阱里的 fail-open 兜底——方向
相反，异常被翻译成**拒绝**并带 reason 落账。fail-closed 的语义责任在「异常路径的
出口是 DENY 而不是继续」。

时钟：构造时注入 ``clock``（默认取系统钟）。检查链本身不取时钟（enforcement 模块
docstring 的纪律），门是运行时组件负责供钟，测试注入固定钟换确定性。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import broker as broker_module
import enforcement
import mandate as mandate_module
from broker import Broker
from enforcement import Breach, PaymentIntent, TodaySnapshot
from halt import HaltSentinel

DECISION_ALLOW = "ALLOW"
DECISION_DENY = "DENY"
DECISION_PAUSE_FOR_REAUTH = "PAUSE_FOR_REAUTH"

#: structural → DENY；quantitative → PAUSE_FOR_REAUTH（对版产品 kind→裁决路由）。
KIND_TO_DECISION = {
    enforcement.BREACH_KIND_STRUCTURAL: DECISION_DENY,
    enforcement.BREACH_KIND_QUANTITATIVE: DECISION_PAUSE_FOR_REAUTH,
}


@dataclass(frozen=True)
class Verdict:
    """三态裁决（对版产品 ALLOW / blocked-envelope / PAUSE_FOR_REAUTH）。

    Attributes:
        decision: ``ALLOW`` / ``DENY`` / ``PAUSE_FOR_REAUTH``。
        breach: 命中的违规（ALLOW / 前置步骤拒绝时为 None——那些步骤没有 breach 语义）。
        reason: 人类可读理由（落审计账本的字段，测试断言的口径）。
    """

    decision: str
    breach: Breach | None
    reason: str


def _normalize_intent(intent: PaymentIntent) -> PaymentIntent | None:
    """意图归一（对版产品「意图提取」步骤）：strip + 小写；形状不对返回 None。

    返回 None 的口径与检查链第 0 查一致：非 str 收款方/科目、非 int 金额（float、
    bool、字符串数字都算不可解析）。
    """
    if not isinstance(intent.payee, str) or not isinstance(intent.category, str):
        return None
    if type(intent.amount_cents) is not int:
        return None
    return PaymentIntent(
        payee=intent.payee.strip().lower(),
        category=intent.category.strip().lower(),
        amount_cents=intent.amount_cents,
    )


class PaymentGate:
    """报销付款门：唯一的付款裁决出口（对版产品 execute_live_order 的类化教学版）。

    Args:
        mandate_path: 合同文件路径（只读；写入在用户侧受信面，见 mandate.py docstring）。
        halt: kill switch 哨兵。
        broker: 付款通道（读当日已付快照用）。
        clock: 时钟注入点（测试给固定钟；默认系统 UTC 钟——aware，见讲义 §2.6）。
    """

    def __init__(
        self,
        mandate_path: Path,
        halt: HaltSentinel,
        broker: Broker,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._mandate_path = mandate_path
        self._halt = halt
        self._broker = broker
        self._clock = clock or (lambda: datetime.now(UTC))

    def decide(self, intent: PaymentIntent) -> Verdict:
        """六步 ceremony：任何一步不过都是 DENY，只是 reason 不同。"""
        # 1. 合同在且可解析（授权层第一问：这份授权存在吗）。
        mandate = mandate_module.load_mandate(self._mandate_path)
        if mandate is None:
            return Verdict(DECISION_DENY, None, "no valid mandate on file")

        # 2. 授权未过期（「live mandate 不许永生」）。
        now = self._clock()
        expires_at = mandate.consent.expires_at
        assert expires_at is not None  # ConsentMeta.__post_init__ 保证
        if now >= expires_at:
            return Verdict(DECISION_DENY, None, "mandate expired — re-authorize")

        # 3. kill switch：文件存在即停（在任何 broker 调用之前）。
        if self._halt.tripped():
            return Verdict(DECISION_DENY, None, "payments halted (kill switch tripped)")

        # 4. 意图可解析（fail-closed）。
        normalized = _normalize_intent(intent)
        if normalized is None:
            return Verdict(DECISION_DENY, None, "payment intent could not be parsed (fail-closed)")

        # 5. 今日已付快照：读不到就拒——绝不「先放行再补数据」。
        try:
            paid = tuple(self._broker.today_payments())
        except broker_module.BrokerUnavailable:
            return Verdict(DECISION_DENY, None, "today's payments could not be read (fail-closed)")

        # 6. 检查链裁决（日次数从已付清单推导——只数确认已付的）。
        breach = enforcement.check_payment(mandate, normalized, TodaySnapshot(now=now, paid=paid))
        if breach is None:
            return Verdict(DECISION_ALLOW, None, "payment in mandate")
        decision = KIND_TO_DECISION[breach.kind]
        return Verdict(decision, breach, f"breach: {breach.limit} ({breach.kind})")
