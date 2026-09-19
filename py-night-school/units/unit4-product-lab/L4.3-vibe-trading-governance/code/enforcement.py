"""fail-closed 检查链——对版 HKUDS/Vibe-Trading@f84b2977#agent/src/live/enforcement.py#check_mandate。

产品是纯决策函数 ``(mandate, intent, positions, balance, *, broker, remote_tool, daily_count)
-> BreachEvent | None``，固定顺序**八查**（意图可解析 → 黑名单 → 工具白名单 → 资产类别 →
单笔名义额 → 交易后总敞口 → 杠杆 → 日次数 → 资金防线 → universe 地板），任何不可解析
输入 = breach，绝不放行。

本课裁剪为**七查**（付款域用不上资产类别/杠杆/资金镜像/universe 地板），顺序同样固定：

  0 意图可解析（金额 > 0 的 int、科目/收款方非空）      → structural
  1 收款方黑名单（excluded_vendors）                    → structural
  2 科目白名单（allowed_categories，空 = 全拒）          → structural
  3 单笔上限（max_single_payment_cents）                 → quantitative
  4 当日累计（max_daily_total_cents；清单任一条目不可解析 → breach，fail-closed）→ quantitative
  5 日次数（max_payments_per_day）                       → quantitative
  6 授权未过期（expires_at）                             → structural

kind 两值对版产品：structural（结构性违规）→ 门 DENY——不修改合同就永远不可能放行，
而 agent 永远改不了合同；quantitative（定量违规）→ 门 PAUSE_FOR_REAUTH——暂停等用户
重新授权。返回 None = 全查通过（ALLOW）。

时钟纪律：**本函数绝不自己取系统时钟**（对版产品 manifest 模块的「绝不自己取时钟」纪律）。
「现在几点」与「今天已付了什么」都装进 TodaySnapshot 由调用方注入——纯函数因此可测试：
同一个 (mandate, intent, today) 永远同一个结论，测试不随墙钟漂移。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mandate import PayMandate

#: breach kind 两值（对版产品 universe/instrument=结构性、quantitative=定量）。
BREACH_KIND_STRUCTURAL = "structural"
BREACH_KIND_QUANTITATIVE = "quantitative"


@dataclass(frozen=True)
class PaymentIntent:
    """一笔付款意图（对版产品 OrderIntent 的付款域极简版）。

    Attributes:
        payee: 收款方标识（比较前小写归一）。
        category: 报销科目（比较前小写归一）。
        amount_cents: 金额，整数「分」。float / bool / 字符串数字都算**不可解析**。
    """

    payee: str
    category: str
    amount_cents: int


@dataclass(frozen=True)
class TodaySnapshot:
    """检查链唯一的「世界状态」输入（对版产品的持仓/余额快照 + daily_count 合体）。

    Attributes:
        now: 「现在」——aware UTC，由调用方注入（时钟纪律见模块 docstring）。
        paid: 当日已付清单（从付款通道读来的快照）。每条目是带 payee/category/
            amount_cents 键的映射；**任何一条不可解析 → 整个检查链 breach（fail-closed）**，
            对版产品「持仓任一行解析失败 → breach」分支。
    """

    now: datetime
    paid: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class Breach:
    """一条违规（对版产品 BreachEvent 的教学裁剪版：去掉 broker/远程工具戳记）。

    Attributes:
        kind: ``"structural"``（门 DENY）或 ``"quantitative"``（门 PAUSE_FOR_REAUTH）。
        limit: 命中的限制名（如 ``"excluded_vendors"``、``"max_single_payment_cents"``）。
        attempted_cents: 违规时点的金额/累计（结构性违规里数字不承载语义，detail 才是）。
        detail: 人类可读说明。
    """

    kind: str
    limit: str
    attempted_cents: int
    detail: str = ""


def _parse_paid_amount(entry: Mapping[str, Any]) -> int | None:
    """读单条已付记录的金额；不可解析返回 None（调用方必须当 breach 处理）。

    金额必须是正整数分：``type(x) is not int`` 连 float 和 bool 一起拒
    （bool 是 int 子类——这是 Python 著名的坑，此处宁可误杀不可放过）。
    """
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
    """对一笔付款意图跑七查（固定顺序，首查命中即返回，fail-closed）。

    Args:
        mandate: 当前有效合同（门在调用前已完成加载/过期检查）。
        intent: 待裁决的付款意图。
        today: 注入的「现在 + 当日已付清单」。

    Returns:
        ``None`` 表示全查通过（ALLOW）；否则返回第一条违规的 :class:`Breach`。
    """
    caps = mandate.hard_caps
    universe = mandate.universe

    # 0. 意图可解析——类型/形状不对直接拒（structural，对版 check 0）。
    payee = intent.payee.strip().lower() if isinstance(intent.payee, str) else ""
    category = intent.category.strip().lower() if isinstance(intent.category, str) else ""
    if not payee or not category or type(intent.amount_cents) is not int or intent.amount_cents <= 0:
        return Breach(
            kind=BREACH_KIND_STRUCTURAL,
            limit="payment_intent",
            attempted_cents=0,
            detail="payment intent unparseable (payee/category/amount_cents)",
        )

    # 1. 收款方黑名单——优先于其他一切规则（对版 exclude-list）。
    if payee in universe.excluded_vendors:
        return Breach(
            kind=BREACH_KIND_STRUCTURAL,
            limit="excluded_vendors",
            attempted_cents=intent.amount_cents,
            detail=f"{payee} is on the mandate exclude list",
        )

    # 2. 科目白名单——空 = 全拒（fail-closed，对版 allowed_instruments 空 == deny all）。
    if category not in universe.allowed_categories:
        return Breach(
            kind=BREACH_KIND_STRUCTURAL,
            limit="allowed_categories",
            attempted_cents=intent.amount_cents,
            detail=f"category '{category}' not in allowed_categories"
            + (" (empty == deny all)" if not universe.allowed_categories else ""),
        )

    # 3. 单笔上限。
    if intent.amount_cents > caps.max_single_payment_cents:
        return Breach(
            kind=BREACH_KIND_QUANTITATIVE,
            limit="max_single_payment_cents",
            attempted_cents=intent.amount_cents,
        )

    # 4. 当日累计：先逐条解析已付清单——任一条不可解析 = breach（fail-closed，
    #    对版产品「current positions could not be read (fail-closed)」分支）。
    paid_total = 0
    for entry in today.paid:
        amount = _parse_paid_amount(entry)
        if amount is None:
            return Breach(
                kind=BREACH_KIND_QUANTITATIVE,
                limit="max_daily_total_cents",
                attempted_cents=0,
                detail="today's paid list could not be read (fail-closed)",
            )
        paid_total += amount
    if paid_total + intent.amount_cents > caps.max_daily_total_cents:
        return Breach(
            kind=BREACH_KIND_QUANTITATIVE,
            limit="max_daily_total_cents",
            attempted_cents=paid_total + intent.amount_cents,
        )

    # 5. 日次数：只数「确认已付」的条目（对版产品「日计数只在确认执行后消耗」）。
    attempted_count = len(today.paid) + 1
    if attempted_count > caps.max_payments_per_day:
        return Breach(
            kind=BREACH_KIND_QUANTITATIVE,
            limit="max_payments_per_day",
            attempted_cents=intent.amount_cents,
            detail=f"attempted {attempted_count} payments today (cap {caps.max_payments_per_day})",
        )

    # 6. 授权未过期：到期即拒（结构性——修数字救不了，只能重新授权）。
    expires_at = mandate.consent.expires_at
    assert expires_at is not None  # __post_init__ 保证；窄化给 pyright
    if today.now >= expires_at:
        return Breach(
            kind=BREACH_KIND_STRUCTURAL,
            limit="mandate_expiry",
            attempted_cents=intent.amount_cents,
            detail=f"mandate expired at {expires_at.isoformat()} — re-authorize",
        )

    return None  # 全查通过：ALLOW
