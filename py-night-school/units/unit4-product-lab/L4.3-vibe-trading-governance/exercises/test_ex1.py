"""练习 1 验收（不要改本文件——它就是你的判卷老师）。

用例表逐查覆盖（对版产品 test_mandate_enforcement 的 per-limit 思想：每查一个「只破
这一项」的用例）+ 覆盖型 meta（三态/两 kind/七限制逐维断言）+ 顺序断言（黑名单先于单笔）。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

import ex1_chain as ex1
from mandate import ConsentMeta, HardCaps, PayMandate, PayUniverse

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)

BASE_MANDATE = PayMandate(
    schema_version=1,
    hard_caps=HardCaps(max_single_payment_cents=200_000, max_daily_total_cents=500_000, max_payments_per_day=3),
    universe=PayUniverse(
        allowed_categories=("travel", "office_supplies", "training"), excluded_vendors=("sketchy-mall",)
    ),
    consent=ConsentMeta(consent_token_sha256="sha256:test", created_at=NOW - timedelta(days=3)),
)
EXPIRED_MANDATE = replace(
    BASE_MANDATE, consent=replace(BASE_MANDATE.consent, created_at=NOW - timedelta(days=31), expires_at=None)
)


def intent(payee: str = "airline-co", category: str = "travel", amount: int = 90_000) -> ex1.PaymentIntent:
    return ex1.PaymentIntent(payee=payee, category=category, amount_cents=amount)


def paid(*entries: dict[str, Any]) -> ex1.TodaySnapshot:
    return ex1.TodaySnapshot(now=NOW, paid=entries)


CLEAN = paid()  # 空的当日清单

#: 用例表：(名字, mandate, intent, today, 期望)——期望为 None=ALLOW，否则 (kind, limit)。
CASES: list[tuple[str, PayMandate, ex1.PaymentIntent, ex1.TodaySnapshot, Any]] = [
    ("check0 意图不可解析", BASE_MANDATE, intent(amount=0), CLEAN, ("structural", "payment_intent")),
    (
        "check1 黑名单",
        BASE_MANDATE,
        intent(payee="sketchy-mall", amount=50_000),
        CLEAN,
        ("structural", "excluded_vendors"),
    ),
    ("check2 科目不在白名单", BASE_MANDATE, intent(category="groceries"), CLEAN, ("structural", "allowed_categories")),
    ("check3 单笔超上限", BASE_MANDATE, intent(amount=200_001), CLEAN, ("quantitative", "max_single_payment_cents")),
    (
        "check4 当日累计超上限",
        BASE_MANDATE,
        intent(amount=90_000),
        paid({"payee": "v1", "category": "travel", "amount_cents": 420_000}),
        ("quantitative", "max_daily_total_cents"),
    ),
    (
        "check4 已付清单脏数据 fail-closed",
        BASE_MANDATE,
        intent(amount=100),
        paid({"payee": "v1", "category": "travel"}),  # 缺 amount_cents
        ("quantitative", "max_daily_total_cents"),
    ),
    (
        "check5 日次数超上限",
        BASE_MANDATE,
        intent(amount=100),
        paid(*[{"payee": f"v{i}", "category": "travel", "amount_cents": 100} for i in range(3)]),
        ("quantitative", "max_payments_per_day"),
    ),
    ("check6 授权过期", EXPIRED_MANDATE, intent(), CLEAN, ("structural", "mandate_expiry")),
    ("allow 全查通过", BASE_MANDATE, intent(), CLEAN, None),
]

DECISION_OF = {None: "ALLOW", "structural": "DENY", "quantitative": "PAUSE_FOR_REAUTH"}


def run_one(m: PayMandate, i: ex1.PaymentIntent, t: ex1.TodaySnapshot) -> Any:
    breach = ex1.check_payment(m, i, t)
    return None if breach is None else (breach.kind, breach.limit)


@pytest.mark.parametrize("name, m, i, t, expected", CASES, ids=[c[0] for c in CASES])
def test_case_table(name: str, m: PayMandate, i: ex1.PaymentIntent, t: ex1.TodaySnapshot, expected: Any) -> None:
    assert run_one(m, i, t) == expected


def test_blacklist_short_circuits_before_single_cap() -> None:
    # 同时违反黑名单（第 1 查）与单笔上限（第 3 查）：首查命中即停——固定顺序是合同的一部分。
    breach = ex1.check_payment(BASE_MANDATE, intent(payee="sketchy-mall", amount=999_999), CLEAN)
    assert breach is not None and breach.limit == "excluded_vendors"


def test_meta_table_covers_seven_checks_three_states_two_kinds() -> None:
    outcomes = [run_one(m, i, t) for _, m, i, t, _ in CASES]
    limits = {o[1] for o in outcomes if o is not None}
    assert limits == {  # 七查每一查都被某个用例命中（对版 per-limit 覆盖）
        "payment_intent",
        "excluded_vendors",
        "allowed_categories",
        "max_single_payment_cents",
        "max_daily_total_cents",
        "max_payments_per_day",
        "mandate_expiry",
    }
    decisions = {DECISION_OF[None] if o is None else DECISION_OF[o[0]] for o in outcomes}
    assert decisions == {"ALLOW", "DENY", "PAUSE_FOR_REAUTH"}  # 三态各有用例
    kinds = {o[0] for o in outcomes if o is not None}
    assert kinds == {"structural", "quantitative"}  # 两种 kind 各有用例
    assert len(CASES) >= 9  # 用例表规模下限（数量词兑现：9 条）


def test_pure_function_same_inputs_same_verdict() -> None:
    # 时钟注入 + 纯函数：同一组输入跑两遍，结论逐字段相等（测试不随墙钟漂移）。
    first = ex1.check_payment(BASE_MANDATE, intent(amount=250_000), CLEAN)
    second = ex1.check_payment(BASE_MANDATE, intent(amount=250_000), CLEAN)
    assert first == second and first is not None and first.limit == "max_single_payment_cents"
