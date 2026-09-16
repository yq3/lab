"""讲义区验收（六）：执行门纯函数——逐查单测、三态覆盖 meta、fail-closed 参数化。

覆盖表（meta 测试钉住它——每个 reason_code 至少一个用例、三态各有、数量先数后写）：
  ALLOW：allow / clamped（2 种）
  PAUSE：single_over_limit / daily_over_limit / frequency_over_limit（3 种）
  DENY：unparseable_intent / approval_missing / approval_not_confirmed /
        approval_content_mismatch / vendor_blocklisted / ledger_unreadable（6 种）
  合计 11 种 reason_code、用例表 11 行（数量词口径：len(CASES)）。
"""

from __future__ import annotations

from typing import Any

import pytest

from gate import (
    DEFAULT_POLICY,
    ApprovalRecord,
    GateVerdict,
    LedgerView,
    PaymentIntent,
    Policy,
    check_intent,
)

TODAY = "2026-09-16"


def policy(**overrides: Any) -> Policy:
    """默认合同的快捷覆盖（kwargs 覆盖字段）。"""
    base: dict[str, Any] = dict(
        max_single_cents=200_000,
        max_daily_total_cents=500_000,
        max_payments_per_day=3,
        vendor_blocklist=("sketchy-mall",),
        clamp_overruns=False,
    )
    base.update(overrides)
    return Policy(**base)


def intent(**overrides: Any) -> PaymentIntent:
    """六字段齐全的合规意图（kwargs 覆盖字段）。"""
    base: dict[str, Any] = dict(
        claim_id="CLM-2026-0001",
        vendor="airline-co",
        dept="SALES",
        category="差旅",
        amount_cents=90_000,
        content_hash="sha256:v1",
    )
    base.update(overrides)
    return PaymentIntent(**base)


def approval(**overrides: Any) -> ApprovalRecord:
    """与 intent 自洽的 CONFIRMED 审批回执（A6 指纹一致）。"""
    base: dict[str, Any] = dict(ticket_id="tkt-0001", decision="CONFIRMED", content_hash="sha256:v1", approved_at="t0")
    base.update(overrides)
    return ApprovalRecord(**base)


def ledger(*payments: dict, today: str = TODAY) -> LedgerView:
    """当日账本视图（缺省两笔已付：180000 + 60000 = 240000 分、2 笔）。"""
    rows = list(payments) or [
        {"claim_id": "C91", "vendor": "airline-co", "dept": "SALES", "category": "差旅", "amount_cents": 180_000},
        {"claim_id": "C92", "vendor": "stationery-co", "dept": "DEV", "category": "办公", "amount_cents": 60_000},
    ]
    return LedgerView(today=today, payments=tuple(rows))


def verdict_of(**kw) -> GateVerdict:
    """check_intent 的默认实参快捷调用。"""
    return check_intent(
        kw.pop("policy", policy()),
        kw.pop("intent", intent()),
        kw.pop("approval", approval()),
        kw.pop("ledger", ledger()),
    )


# ---- 逐查单测：每查一测（只破这一项） ----


def test_check0_unparseable_intent_denies() -> None:
    """⑥′ 意图不可解析即 DENY——金额非正、类型不对、字段缺失都算（统一入口）。"""
    assert verdict_of(intent=intent(amount_cents=-500)).reason_code == "unparseable_intent"
    assert verdict_of(intent=intent(amount_cents=0)).reason_code == "unparseable_intent"
    assert verdict_of(intent=intent(amount_cents="8800元")).reason_code == "unparseable_intent"  # type: ignore[arg-type]
    assert verdict_of(intent=intent(vendor=" ")).reason_code == "unparseable_intent"
    assert verdict_of(intent=intent(claim_id=None)).reason_code == "unparseable_intent"  # type: ignore[arg-type]


def test_check1_approval_missing_or_not_confirmed_denies() -> None:
    """① 审批单二次校验（A7）：不在场 / 不是 CONFIRMED 都 DENY——决策层批了不算数。"""
    assert verdict_of(approval=None).reason_code == "approval_missing"
    assert verdict_of(approval=approval(decision="PENDING")).reason_code == "approval_not_confirmed"
    assert verdict_of(approval=approval(decision="REJECTED")).reason_code == "approval_not_confirmed"


def test_check2_approval_hash_mismatch_denies() -> None:
    """② 审批指纹绑定（A6）：批的是旧版内容 → DENY——执行侧重算指纹逐字比对。"""
    verdict = verdict_of(approval=approval(content_hash="sha256:old"))
    assert verdict.action == "DENY"
    assert verdict.reason_code == "approval_content_mismatch"


def test_check3_vendor_blocklist_denies() -> None:
    """② 供应商黑名单：结构性 DENY（大小写不敏感——比较前小写归一）。"""
    verdict = verdict_of(intent=intent(vendor="Sketchy-Mall"))
    assert verdict.action == "DENY"
    assert verdict.reason_code == "vendor_blocklisted"


def test_check4_single_over_limit_pauses_or_clamps() -> None:
    """③ 单笔上限：clamp 关 → PAUSE；clamp 开 → 裁到上限 ALLOW（clamp 只缩不放）。"""
    verdict = verdict_of(intent=intent(amount_cents=250_000))
    assert verdict.action == "PAUSE_FOR_REAUTH"
    assert verdict.reason_code == "single_over_limit"
    clamped = verdict_of(policy=policy(clamp_overruns=True), intent=intent(amount_cents=250_000))
    assert (clamped.action, clamped.reason_code) == ("ALLOW", "clamped")
    assert clamped.clamp_cents == 200_000  # 250000 → 200000：只缩不放


def test_check5_daily_total_over_limit_pauses_or_clamps() -> None:
    """④ 当日累计：已付 450000 + 本笔 90000 > 500000（单笔未超）→ PAUSE；clamp 开 → 裁到剩余额度。"""
    heavy = ledger(
        {"claim_id": "C91", "vendor": "a", "dept": "SALES", "category": "x", "amount_cents": 400_000},
        {"claim_id": "C92", "vendor": "b", "dept": "DEV", "category": "x", "amount_cents": 50_000},
    )
    verdict = verdict_of(ledger=heavy)  # 90000 分单笔合规，累计 540000 超日上限
    assert (verdict.action, verdict.reason_code) == ("PAUSE_FOR_REAUTH", "daily_over_limit")
    clamped = verdict_of(policy=policy(clamp_overruns=True), ledger=heavy)
    assert (clamped.action, clamped.reason_code) == ("ALLOW", "clamped")
    assert clamped.clamp_cents == 50_000  # 裁到当日剩余额度 500000-450000——clamp 只缩不放


def test_check5_daily_exhausted_cannot_clamp() -> None:
    """④ 当日额度耗尽：裁不出正数金额 → 仍 PAUSE（clamp 不是万能出口）。"""
    spent = ledger({"claim_id": "C93", "vendor": "a", "dept": "SALES", "category": "x", "amount_cents": 500_000})
    verdict = verdict_of(policy=policy(clamp_overruns=True), ledger=spent)
    assert (verdict.action, verdict.reason_code) == ("PAUSE_FOR_REAUTH", "daily_over_limit")


def test_check6_frequency_over_limit_never_clamps() -> None:
    """⑤ 当日频次：已付 2 笔 + 本笔 = 3 恰好打满；3 笔已付 + 本笔 = 4 超次——clamp 开也不放（笔数不可裁）。"""
    full = verdict_of(intent=intent(amount_cents=90_000))
    assert full.action == "ALLOW"  # 2 已付 + 1 = 3，未超
    spent = ledger(
        {"claim_id": "C91", "vendor": "a", "dept": "SALES", "category": "x", "amount_cents": 10},
        {"claim_id": "C92", "vendor": "b", "dept": "SALES", "category": "x", "amount_cents": 10},
        {"claim_id": "C93", "vendor": "c", "dept": "SALES", "category": "x", "amount_cents": 10},
    )
    verdict = verdict_of(policy=policy(clamp_overruns=True), ledger=spent)
    assert (verdict.action, verdict.reason_code) == ("PAUSE_FOR_REAUTH", "frequency_over_limit")
    assert verdict.clamp_cents is None  # 一笔就是一笔，裁不出 0.7 笔


def test_ledger_unparseable_entry_denies() -> None:
    """④ 的 fail-closed 内核：已付清单任一条不可解析 → DENY（宁可不付，不带脏账放行）。"""
    dirty = ledger({"vendor": "airline-co", "dept": "SALES", "category": "差旅"})  # 缺 amount_cents
    verdict = verdict_of(ledger=dirty)
    assert (verdict.action, verdict.reason_code) == ("DENY", "ledger_unreadable")
    dirty_amount = ledger({"vendor": "a", "dept": "SALES", "category": "x", "amount_cents": 12.5})
    assert verdict_of(ledger=dirty_amount).reason_code == "ledger_unreadable"  # float 金额也不行


def test_allow_passes_with_no_clamp() -> None:
    """全查通过：ALLOW/allow、clamp 为 None——「通过」也是带原因码的一等裁决。"""
    verdict = verdict_of()
    assert verdict == GateVerdict("ALLOW", "allow", verdict.detail)
    assert verdict.clamp_cents is None


# ---- 短路顺序：黑名单先于限额（构造双违单） ----


def test_blocklist_short_circuits_before_limits() -> None:
    """双违单（黑名单 + 超单笔上限）：裁决停在黑名单——结构性先于定量（顺序是审计契约）。"""
    verdict = verdict_of(intent=intent(vendor="sketchy-mall", amount_cents=999_999))
    assert verdict.reason_code == "vendor_blocklisted"  # 不是 single_over_limit
    # 同理：指纹不符先于黑名单（改 hash 也救不了黑名单单）
    mismatch = verdict_of(intent=intent(vendor="sketchy-mall"), approval=approval(content_hash="sha256:x"))
    assert mismatch.reason_code == "approval_content_mismatch"


# ---- fail-closed 参数化：None / 畸形输入 ----


@pytest.mark.parametrize(
    "make_kwargs",
    [
        {"intent": None},
        {"approval": None},
        {"ledger": None},
        {"policy": None},
    ],
    ids=["intent-none", "approval-none", "ledger-none", "policy-none"],
)
def test_fail_closed_none_inputs_deny(make_kwargs) -> None:
    """None 输入一律 DENY（fail-closed）：意图/审批/账本/合同缺哪个都不放行、不崩溃。"""
    verdict = verdict_of(**make_kwargs)
    assert verdict.action == "DENY"


@pytest.mark.parametrize(
    "bad_intent",
    [
        intent(amount_cents=True),  # type: ignore[arg-type]  # bool 是 int 子类——必须拒
        intent(amount_cents=1.5),  # type: ignore[arg-type]  # float
        intent(content_hash=""),  # 指纹缺失：A6 无从比对
        intent(dept=""),
    ],
    ids=["amount-bool", "amount-float", "hash-empty", "dept-empty"],
)
def test_fail_closed_malformed_intents_deny(bad_intent) -> None:
    """畸形意图参数化：答案永远是 DENY，不是 TypeError（统一入口拦在解引用之前）。"""
    verdict = verdict_of(intent=bad_intent)
    assert verdict.action == "DENY"
    assert verdict.reason_code == "unparseable_intent"


# ---- 覆盖型 meta：三态各有、每种 reason_code 齐、数量先数后写 ----

# 用例表：(改哪个输入, kwargs, 期望 reason_code)——「只破这项」的最小变更集合。
CASES: list[tuple[str, dict, str]] = [
    ("allow", {}, "allow"),
    ("clamped", {"policy": policy(clamp_overruns=True), "intent": intent(amount_cents=250_000)}, "clamped"),
    ("single", {"intent": intent(amount_cents=250_000)}, "single_over_limit"),
    (
        "daily",
        {
            "ledger": ledger(
                {"claim_id": "C91", "vendor": "a", "dept": "SALES", "category": "x", "amount_cents": 400_000},
                {"claim_id": "C92", "vendor": "b", "dept": "DEV", "category": "x", "amount_cents": 50_000},
            )
        },
        "daily_over_limit",
    ),
    (
        "frequency",
        {
            "ledger": ledger(
                {"claim_id": "C1", "vendor": "a", "dept": "SALES", "category": "x", "amount_cents": 10},
                {"claim_id": "C2", "vendor": "b", "dept": "SALES", "category": "x", "amount_cents": 10},
                {"claim_id": "C3", "vendor": "c", "dept": "SALES", "category": "x", "amount_cents": 10},
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


def test_case_table_covers_every_reason_code_and_action() -> None:
    """meta：覆盖表逐维断言——11 种 reason_code 每种至少一个用例、三态各有、表 11 行。"""
    assert len(CASES) == 11  # 数量词：表 11 行（先数再写）
    codes = {expected for _name, _kw, expected in CASES}
    assert codes == {
        "allow",
        "clamped",
        "single_over_limit",
        "daily_over_limit",
        "frequency_over_limit",
        "unparseable_intent",
        "approval_missing",
        "approval_not_confirmed",
        "approval_content_mismatch",
        "vendor_blocklisted",
        "ledger_unreadable",
    }  # reason 种类集单独断言（不留单维缺口）
    actions = {verdict_of(**kw).action for _name, kw, _expected in CASES}
    assert actions == {"ALLOW", "DENY", "PAUSE_FOR_REAUTH"}  # 三态各有
    for name, kw, expected in CASES:  # 每行期望兑现
        assert verdict_of(**kw).reason_code == expected, name


def test_default_policy_is_permissive_for_mock_claims() -> None:
    """教学缺省合同：四单素材的金额（最大 8800 分）全部原样放行（宽门——真实部署显式注入 Policy）。"""
    for amount in (7100, 8800, 5000):
        verdict = check_intent(DEFAULT_POLICY, intent(amount_cents=amount), approval(), ledger())
        assert verdict.action == "ALLOW"
        assert verdict.reason_code == "allow"
