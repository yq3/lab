"""Step1：零图跑检查链——三态各一幕 + A6/A7 幕 + fail-closed 幕（零文件、零模型、零图）。

用法：uv run python code/step1_gate.py
（对照 L4.3 的 step1_chain：同一形态——门是纯函数，不需要图就能验。）
"""

from __future__ import annotations

from gate import (
    ApprovalRecord,
    LedgerView,
    PaymentIntent,
    Policy,
    check_intent,
)

TODAY = "2026-09-16"  # 注入的「今天」（ISO 日期）——门不取系统时钟（§5 陷阱）

POLICY = Policy(
    max_single_cents=200_000,  # 单笔 ≤ 2000.00 元
    max_daily_total_cents=500_000,  # 当日累计 ≤ 5000.00 元
    max_payments_per_day=3,
    vendor_blocklist=("sketchy-mall",),
    clamp_overruns=False,
)

DIRTY = {"vendor": "airline-co", "dept": "SALES", "category": "差旅"}  # 缺 amount_cents 的脏账目

CLAMP_POLICY = Policy(
    max_single_cents=200_000,
    max_daily_total_cents=500_000,
    max_payments_per_day=3,
    vendor_blocklist=("sketchy-mall",),
    clamp_overruns=True,  # 第二组对照：定量超限不 PAUSE，裁到限额放行（clamp 只缩不放）
)

PAID_AIR = {
    "claim_id": "CLM-2026-0091",
    "vendor": "airline-co",
    "dept": "SALES",
    "category": "差旅",
    "amount_cents": 180_000,
}
PAID_STA = {
    "claim_id": "CLM-2026-0092",
    "vendor": "stationery-co",
    "dept": "DEV",
    "category": "办公用品",
    "amount_cents": 60_000,
}
LEDGER = LedgerView(today=TODAY, payments=(PAID_AIR, PAID_STA))


def intent_of(vendor: str, amount: int) -> PaymentIntent:
    """造一笔意图的捷径（六字段齐全——content_hash 与审批单同源）。"""
    return PaymentIntent(
        claim_id="CLM-2026-0001",
        vendor=vendor,
        dept="SALES",
        category="客户拜访",
        amount_cents=amount,
        content_hash="sha256:demo-v1",
    )


APPROVAL = ApprovalRecord(
    ticket_id="tkt-0001",
    decision="CONFIRMED",
    content_hash="sha256:demo-v1",
    approved_at="2026-09-16T20:00:00+00:00",
)


def show(title: str, verdict, policy: Policy) -> None:
    clamp = f" clamp={verdict.clamp_cents} 分" if verdict.clamp_cents is not None else ""
    print(f"{title}")
    print(f"  -> {verdict.action:<16} reason={verdict.reason_code}{clamp}")
    print(f"     detail: {verdict.detail}")


def main() -> None:
    print("== Step1 检查链七查：固定顺序、首查命中即停（零图纯函数） ==")
    print(
        f"policy: 单笔≤{POLICY.max_single_cents} 分, 日累计≤{POLICY.max_daily_total_cents} 分, "
        f"日次数≤{POLICY.max_payments_per_day}, 黑名单={list(POLICY.vendor_blocklist)}, "
        f"clamp={'开' if POLICY.clamp_overruns else '关'}"
    )
    print(f"ledger: today={LEDGER.today}, 已付 {len(LEDGER.payments)} 笔共 240000 分\n")

    cases = [
        (
            "幕1 ALLOW | 合规小额（审批单 CONFIRMED 且指纹一致）",
            check_intent(POLICY, intent_of("airline-co", 90_000), APPROVAL, LEDGER),
            POLICY,
        ),
        (
            "幕2 DENY  | 黑名单收款方（双违单：同时超单笔上限——黑名单先查，短路）",
            check_intent(POLICY, intent_of("Sketchy-Mall", 250_000), APPROVAL, LEDGER),
            POLICY,
        ),
        (
            "幕3 PAUSE | 单笔超上限（定量——clamp 关：暂停等重新授权）",
            check_intent(POLICY, intent_of("airline-co", 250_000), APPROVAL, LEDGER),
            POLICY,
        ),
        (
            "幕4 DENY  | 审批指纹不符（A6+A7：批的不是这版——执行出口的二次校验）",
            check_intent(
                POLICY,
                intent_of("airline-co", 90_000),
                ApprovalRecord("tkt-0002", "CONFIRMED", "sha256:old-version", "2026-09-15T09:00:00+00:00"),
                LEDGER,
            ),
            POLICY,
        ),
        (
            "幕5 DENY  | 已付清单脏数据（fail-closed——宁可整单拒绝，不带脏账放行）",
            check_intent(POLICY, intent_of("airline-co", 10_000), APPROVAL, LedgerView(today=TODAY, payments=(DIRTY,))),
            POLICY,
        ),
        (
            "幕6 ALLOW+clamp | 同一笔超限单在 clamp 开启的合同下：裁到上限放行",
            check_intent(CLAMP_POLICY, intent_of("airline-co", 250_000), APPROVAL, LEDGER),
            CLAMP_POLICY,
        ),
    ]
    for title, verdict, policy in cases:
        show(title, verdict, policy)

    print(
        "\n读法：幕2 是短路顺序的证据——同一笔单既进黑名单又超单笔上限，裁决停在黑名单\n"
        "（结构性先于定量：改数字救不了黑名单，先说没救的事）；幕4 是本课的新查——\n"
        "决策层「批了」不算数，执行出口把审批指纹与重算指纹逐字比对（A7 纵深防御）；\n"
        "幕5 是魂——账本读不了，答案不是崩，是 DENY（fail-closed 拒绝的是带脏数据放行）。"
    )


if __name__ == "__main__":
    main()
