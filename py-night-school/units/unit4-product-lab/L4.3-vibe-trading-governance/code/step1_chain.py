"""Step1：零状态跑检查链——三态各一幕 + fail-closed 一幕（零文件、零 broker）。

用法：uv run python code/step1_chain.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from enforcement import (
    BREACH_KIND_STRUCTURAL,
    PaymentIntent,
    TodaySnapshot,
    check_payment,
)
from mandate import ConsentMeta, HardCaps, PayMandate, PayUniverse

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
CREATED_AT = NOW - timedelta(days=3)

MANDATE = PayMandate(
    schema_version=1,
    hard_caps=HardCaps(
        max_single_payment_cents=200_000,  # 单笔 ≤ 2000.00 元
        max_daily_total_cents=500_000,  # 当日累计 ≤ 5000.00 元
        max_payments_per_day=3,
    ),
    universe=PayUniverse(
        allowed_categories=("travel", "office_supplies", "training"),
        excluded_vendors=("sketchy-mall",),
    ),
    consent=ConsentMeta(consent_token_sha256="sha256:consent-demo", created_at=CREATED_AT),
)


def verdict_of(breach) -> str:
    """kind → 三态（对版产品的 kind 路由：structural→DENY、quantitative→PAUSE）。"""
    if breach is None:
        return "ALLOW"
    return "DENY" if breach.kind == BREACH_KIND_STRUCTURAL else "PAUSE_FOR_REAUTH"


def main() -> None:
    print("== Step1 检查链七查：固定顺序、首查命中即停（零状态纯函数） ==")
    print(
        f"mandate: 单笔≤{MANDATE.hard_caps.max_single_payment_cents} 分, "
        f"日累计≤{MANDATE.hard_caps.max_daily_total_cents} 分, "
        f"日次数≤{MANDATE.hard_caps.max_payments_per_day}, "
        f"科目={list(MANDATE.universe.allowed_categories)}, "
        f"黑名单={list(MANDATE.universe.excluded_vendors)}"
    )

    today = TodaySnapshot(
        now=NOW,
        paid=(
            {"payee": "airline-co", "category": "travel", "amount_cents": 180_000, "ref_id": "pay-earlier1"},
            {"payee": "stationery-co", "category": "office_supplies", "amount_cents": 60_000, "ref_id": "pay-earlier2"},
        ),
    )
    print(f"today: now={NOW.isoformat()}, 已付 2 笔共 240000 分\n")

    cases = [
        ("幕1 ALLOW   | 合规小额", PaymentIntent(payee="airline-co", category="travel", amount_cents=90_000), today),
        (
            "幕2 DENY    | 黑名单收款方",
            PaymentIntent(payee="Sketchy-Mall", category="office_supplies", amount_cents=50_000),
            today,
        ),
        (
            "幕3 PAUSE   | 单笔超上限（定量）",
            PaymentIntent(payee="airline-co", category="travel", amount_cents=250_000),
            today,
        ),
        (
            "幕4 PAUSE   | 已付清单脏数据（fail-closed）",
            PaymentIntent(payee="airline-co", category="travel", amount_cents=10_000),
            TodaySnapshot(now=NOW, paid=({"payee": "airline-co", "category": "travel"},)),
        ),  # 缺 amount_cents
    ]
    for title, intent, snap in cases:
        breach = check_payment(MANDATE, intent, snap)
        kind = breach.kind if breach else "-"
        print(f"{title}")
        print(f"  -> {verdict_of(breach):6} kind={kind:12} limit={breach.limit if breach else '-'}")
        if breach:
            print(f"     detail: {breach.detail or f'attempted {breach.attempted_cents} 分'}")
    print(
        "\n读法：幕2 优先命中黑名单（第 1 查先于单笔第 3 查）；幕4 是本课的魂——"
        "已付清单缺 amount_cents，定量检查算不下去就 breach：宁可不放行，绝不带着脏数据放行"
        "（DENY 与 PAUSE 都是「不放」，差别只在恢复路径：结构性没救、定量可重新授权）。"
    )


if __name__ == "__main__":
    main()
