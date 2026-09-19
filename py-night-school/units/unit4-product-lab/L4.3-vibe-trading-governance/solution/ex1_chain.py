# 参考答案：ex1_chain（练习文件的完整解法——完成前别看）
"""补全检查链：0/1/2/3 查已给，4（当日累计）/ 5（日次数）/ 6（授权过期）见 TODO 原位。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mandate import PayMandate

BREACH_KIND_STRUCTURAL = "structural"
BREACH_KIND_QUANTITATIVE = "quantitative"


@dataclass(frozen=True)
class PaymentIntent:
    """一笔付款意图（金额整数分；与讲义 code/enforcement.py 同构）。"""

    payee: str
    category: str
    amount_cents: int


@dataclass(frozen=True)
class TodaySnapshot:
    """注入的「现在 + 当日已付清单」——检查链绝不自己取时钟。"""

    now: datetime
    paid: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class Breach:
    """一条违规：kind 决定门的三态路由（structural→DENY、quantitative→PAUSE）。"""

    kind: str
    limit: str
    attempted_cents: int
    detail: str = ""


def _parse_paid_amount(entry: Mapping[str, Any]) -> int | None:
    """已给：读单条已付记录的金额；不可解析返回 None（fail-closed 的判定点）。"""
    amount = entry.get("amount_cents")
    if type(amount) is not int or amount <= 0:
        return None
    payee = entry.get("payee")
    category = entry.get("category")
    if not isinstance(payee, str) or not payee.strip():
        return None
    if not isinstance(category, str) or not category.strip():
        return None
    return amount


def check_payment(mandate: PayMandate, intent: PaymentIntent, today: TodaySnapshot) -> Breach | None:
    """七查（固定顺序，首查命中即返回，fail-closed）。"""
    caps = mandate.hard_caps
    universe = mandate.universe

    # 0. 意图可解析（已给）。
    payee = intent.payee.strip().lower() if isinstance(intent.payee, str) else ""
    category = intent.category.strip().lower() if isinstance(intent.category, str) else ""
    if not payee or not category or type(intent.amount_cents) is not int or intent.amount_cents <= 0:
        return Breach(BREACH_KIND_STRUCTURAL, "payment_intent", 0, "payment intent unparseable")

    # 1. 收款方黑名单（已给）——优先于其他一切规则。
    if payee in universe.excluded_vendors:
        return Breach(
            BREACH_KIND_STRUCTURAL, "excluded_vendors", intent.amount_cents, f"{payee} is on the mandate exclude list"
        )

    # 2. 科目白名单（已给）——空 = 全拒。
    if category not in universe.allowed_categories:
        return Breach(
            BREACH_KIND_STRUCTURAL,
            "allowed_categories",
            intent.amount_cents,
            f"category '{category}' not in allowed_categories",
        )

    # 3. 单笔上限（已给）。
    if intent.amount_cents > caps.max_single_payment_cents:
        return Breach(BREACH_KIND_QUANTITATIVE, "max_single_payment_cents", intent.amount_cents)

    # 4. 当日累计：任一条不可解析 = breach（fail-closed）；可解析才合计。
    paid_total = 0
    for entry in today.paid:
        amount = _parse_paid_amount(entry)
        if amount is None:
            return Breach(
                BREACH_KIND_QUANTITATIVE,
                "max_daily_total_cents",
                0,
                "today's paid list could not be read (fail-closed)",
            )
        paid_total += amount
    if paid_total + intent.amount_cents > caps.max_daily_total_cents:
        return Breach(BREACH_KIND_QUANTITATIVE, "max_daily_total_cents", paid_total + intent.amount_cents)

    # 5. 日次数：只数确认已付的条目，本笔 +1。
    attempted_count = len(today.paid) + 1
    if attempted_count > caps.max_payments_per_day:
        return Breach(
            BREACH_KIND_QUANTITATIVE,
            "max_payments_per_day",
            intent.amount_cents,
            f"attempted {attempted_count} payments today (cap {caps.max_payments_per_day})",
        )

    # 6. 授权过期：结构性——到点即拒，修数字救不了。
    expires_at = mandate.consent.expires_at
    assert expires_at is not None  # ConsentMeta.__post_init__ 保证
    if today.now >= expires_at:
        return Breach(
            BREACH_KIND_STRUCTURAL,
            "mandate_expiry",
            intent.amount_cents,
            f"mandate expired at {expires_at.isoformat()} — re-authorize",
        )

    return None  # 全查通过：ALLOW
