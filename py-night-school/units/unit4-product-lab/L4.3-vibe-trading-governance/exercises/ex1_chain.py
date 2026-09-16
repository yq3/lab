# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""补全检查链：0/1/2/3 查已给，你来补 4（当日累计）/ 5（日次数）/ 6（授权过期）。

对版改造题：HKUDS/Vibe-Trading@f84b2977#agent/src/live/enforcement.py#check_mandate 的
八查在付款域裁成七查（讲义 code/enforcement.py 是同构完整版，可对照读，但请先自己写）。
三条纪律：
  fail-closed——today.paid 里**任何一条**不可解析（金额非正 int / 缺 payee 或 category）
    就是 breach，绝不带着脏数据继续算；
  日次数只数「确认已付」的条目，本笔是 attempted = 已付 + 1；
  授权过期是结构性违规（kind=structural，到点即拒，修数字救不了）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——用例表逐查覆盖（每查一个「只破
这一项」的用例）、覆盖型 meta（三态 ALLOW/DENY/PAUSE 各至少一例、两种 kind 各有）、
顺序断言（黑名单先于单笔）。
"""

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
    """七查（固定顺序，首查命中即返回，fail-closed）。0–3 查已给。"""
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

    # TODO(ex1-4) 当日累计（max_daily_total_cents，quantitative）：
    #   逐条遍历 today.paid 问「这一条可解析吗」（用上面给定的 _parse_paid_amount）；
    #   任一条不可解析时这一查该返回什么 kind/limit/detail，才叫 fail-closed？
    #   全部可解析时，拿「已付合计 + 本笔」与哪个上限比、超了返回什么？
    # TODO(ex1-5) 日次数（max_payments_per_day，quantitative）：
    #   「今日已确认付款笔数」从哪个数出来？本笔算进去之后 attempted 是多少？与谁比？
    # TODO(ex1-6) 授权过期（mandate_expiry，structural）：
    #   拿 today.now 与 mandate.consent.expires_at 比——哪个比较符能让「到期那一刻」算过期？
    #   （expires_at 由 ConsentMeta 的 __post_init__ 保证非 None，可直接断言窄化。）

    return None  # 全查通过：ALLOW
