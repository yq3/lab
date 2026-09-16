"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

from typing import Any

import pytest

import ex1_gate as ex1

TODAY = "2026-09-16"


def policy(**overrides: Any) -> ex1.Policy:
    base: dict[str, Any] = dict(
        max_single_cents=200_000,
        max_daily_total_cents=500_000,
        max_payments_per_day=3,
        vendor_blocklist=("sketchy-mall",),
        clamp_overruns=False,
    )
    base.update(overrides)
    return ex1.Policy(**base)


def intent(**overrides: Any) -> ex1.PaymentIntent:
    base: dict[str, Any] = dict(
        claim_id="CLM-2026-0001",
        vendor="airline-co",
        dept="SALES",
        category="差旅",
        amount_cents=90_000,
        content_hash="sha256:v1",
    )
    base.update(overrides)
    return ex1.PaymentIntent(**base)


def approval(**overrides) -> ex1.ApprovalRecord:
    base = dict(ticket_id="tkt-0001", decision="CONFIRMED", content_hash="sha256:v1", approved_at="t0")
    base.update(overrides)
    return ex1.ApprovalRecord(**base)


def ledger(*payments: dict) -> ex1.LedgerView:
    rows = list(payments) or [
        {"vendor": "airline-co", "dept": "SALES", "category": "差旅", "amount_cents": 180_000},
        {"vendor": "stationery-co", "dept": "DEV", "category": "办公", "amount_cents": 60_000},
    ]
    return ex1.LedgerView(today=TODAY, payments=tuple(rows))


def check(**kw) -> ex1.GateVerdict:
    return ex1.check_intent(
        kw.pop("policy", policy()),
        kw.pop("intent", intent()),
        kw.pop("approval", approval()),
        kw.pop("ledger", ledger()),
    )


def test_allow_clean_intent() -> None:
    """三态之 ALLOW：全查通过原样放行（clamp_cents 为 None）。"""
    verdict = check()
    assert verdict.action == "ALLOW"
    assert verdict.reason_code == "allow"
    assert verdict.clamp_cents is None


def test_single_over_limit_pauses_and_clamps() -> None:
    """③「只破这项」：单笔 250000 > 200000——clamp 关 PAUSE / clamp 开裁到上限。"""
    verdict = check(intent=intent(amount_cents=250_000))
    assert (verdict.action, verdict.reason_code) == ("PAUSE_FOR_REAUTH", "single_over_limit")
    clamped = check(policy=policy(clamp_overruns=True), intent=intent(amount_cents=250_000))
    assert (clamped.action, clamped.reason_code) == ("ALLOW", "clamped")
    assert clamped.clamp_cents == 200_000


def test_daily_over_limit_only_when_single_passes() -> None:
    """④「只破这项」：单笔 90000 合规，累计 450000+90000 > 500000——PAUSE / 裁到剩余。"""
    heavy = ledger(
        {"vendor": "a", "dept": "SALES", "category": "x", "amount_cents": 400_000},
        {"vendor": "b", "dept": "DEV", "category": "x", "amount_cents": 50_000},
    )
    verdict = check(ledger=heavy)
    assert (verdict.action, verdict.reason_code) == ("PAUSE_FOR_REAUTH", "daily_over_limit")
    clamped = check(policy=policy(clamp_overruns=True), ledger=heavy)
    assert (clamped.action, clamped.reason_code) == ("ALLOW", "clamped")
    assert clamped.clamp_cents == 50_000


def test_frequency_over_limit_never_clamps() -> None:
    """⑤「只破这项」：已付 3 笔 + 本笔 > 3——clamp 开也不放（笔数不可裁）。"""
    spent = ledger(
        {"vendor": "a", "dept": "SALES", "category": "x", "amount_cents": 10},
        {"vendor": "b", "dept": "SALES", "category": "x", "amount_cents": 10},
        {"vendor": "c", "dept": "SALES", "category": "x", "amount_cents": 10},
    )
    verdict = check(policy=policy(clamp_overruns=True), ledger=spent)
    assert (verdict.action, verdict.reason_code) == ("PAUSE_FOR_REAUTH", "frequency_over_limit")
    assert verdict.clamp_cents is None


def test_unparseable_entry_in_ledger_denies() -> None:
    """④ 的 fail-closed 内核：账本任一条不可解析 → DENY（ledger_unreadable），不是 TypeError。"""
    dirty = ledger({"vendor": "airline-co", "dept": "SALES", "category": "差旅"})  # 缺 amount_cents
    assert check(ledger=dirty).reason_code == "ledger_unreadable"
    assert check(ledger=None).reason_code == "ledger_unreadable"  # 账本视图缺失同样 fail-closed


def test_blocklist_short_circuits_before_single_limit() -> None:
    """短路顺序：双违单（黑名单 + 超单笔）裁决停在黑名单——结构性先于定量。"""
    verdict = check(intent=intent(vendor="Sketchy-Mall", amount_cents=999_999))
    assert verdict.reason_code == "vendor_blocklisted"


@pytest.mark.parametrize(
    "bad_intent",
    [
        None,
        intent(amount_cents=-500),
        intent(amount_cents="8800元"),
        intent(amount_cents=True),
        intent(vendor=" "),
        intent(content_hash=""),
    ],
    ids=["none", "negative", "string-amount", "bool-amount", "blank-vendor", "empty-hash"],
)
def test_fail_closed_malformed_intents_deny(bad_intent) -> None:
    """fail-closed 参数化：畸形/None 意图的答案永远是 DENY（unparseable_intent）。"""
    verdict = check(intent=bad_intent)
    assert verdict.action == "DENY"
    assert verdict.reason_code == "unparseable_intent"


# ---- 覆盖型 meta：用例表逐维断言（不留单维缺口） ----

CASES: list[tuple[str, dict, str]] = [
    ("allow", {}, "allow"),
    ("clamped", {"policy": policy(clamp_overruns=True), "intent": intent(amount_cents=250_000)}, "clamped"),
    ("single", {"intent": intent(amount_cents=250_000)}, "single_over_limit"),
    (
        "daily",
        {
            "ledger": ledger(
                {"vendor": "a", "dept": "SALES", "category": "x", "amount_cents": 400_000},
                {"vendor": "b", "dept": "DEV", "category": "x", "amount_cents": 50_000},
            )
        },
        "daily_over_limit",
    ),
    (
        "frequency",
        {
            "ledger": ledger(
                {"vendor": "a", "dept": "SALES", "category": "x", "amount_cents": 10},
                {"vendor": "b", "dept": "SALES", "category": "x", "amount_cents": 10},
                {"vendor": "c", "dept": "SALES", "category": "x", "amount_cents": 10},
            )
        },
        "frequency_over_limit",
    ),
    ("unparseable", {"intent": intent(amount_cents=-500)}, "unparseable_intent"),
    ("approval-missing", {"approval": None}, "approval_missing"),
    ("approval-state", {"approval": approval(decision="PENDING")}, "approval_not_confirmed"),
    ("approval-hash", {"approval": approval(content_hash="sha256:old")}, "approval_content_mismatch"),
    ("blocklist", {"intent": intent(vendor="sketchy-mall")}, "vendor_blocklisted"),
    ("ledger-dirty", {"ledger": ledger({"vendor": "a", "dept": "SALES", "category": "x"})}, "ledger_unreadable"),
]


def test_case_table_covers_all_codes_actions_and_count() -> None:
    """meta：表 11 行、11 种 reason_code 每种恰有、三态齐、每行期望兑现（数量先数再写）。"""
    assert len(CASES) == 11
    assert len({expected for _n, _kw, expected in CASES}) == 11  # 种类恰好齐——无重复无缺
    actions = {check(**kw).action for _name, kw, _expected in CASES}
    assert actions == {"ALLOW", "DENY", "PAUSE_FOR_REAUTH"}
    for name, kw, expected in CASES:
        assert check(**kw).reason_code == expected, name
