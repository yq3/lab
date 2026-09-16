# 练习 1 参考答案（solution/ 覆盖 exercises/ 后跑验收全绿；与骨架的差异只在 TODO 区）
"""检查链补全：check_intent 的统一入口 + 定量三查（讲义 code/gate.py 的同构迷你版）。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

GateAction = Literal["ALLOW", "DENY", "PAUSE_FOR_REAUTH"]
GateReason = Literal[
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
]

_APPROVAL_CONFIRMED = "CONFIRMED"


@dataclass(frozen=True)
class Policy:
    """限额合同（对版讲义版）：clamp_overruns 决定定量超限是 PAUSE 还是裁剪后放行。"""

    max_single_cents: int
    max_daily_total_cents: int
    max_payments_per_day: int
    vendor_blocklist: tuple[str, ...]
    clamp_overruns: bool = False


@dataclass(frozen=True)
class PaymentIntent:
    """付款意图六字段（金额正整数分；畸形值一律算不可解析）。"""

    claim_id: str
    vendor: str
    dept: str
    category: str
    amount_cents: int
    content_hash: str


@dataclass(frozen=True)
class ApprovalRecord:
    """审批回执（A7：只认 CONFIRMED；A6：content_hash 锁定批的是哪一版）。"""

    ticket_id: str
    decision: str
    content_hash: str
    approved_at: str


@dataclass(frozen=True)
class LedgerView:
    """当日账本视图（注入的世界状态——不取系统时钟）。"""

    today: str
    payments: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class GateVerdict:
    """三态裁决（连 ALLOW 也是带原因码的一等值）。"""

    action: GateAction
    reason_code: GateReason
    detail: str
    clamp_cents: int | None = None


def _text(value: Any) -> str:
    """读一个「必须是非空字符串」的字段；读不到返回空串（按不可解析处理）。"""
    return value.strip() if isinstance(value, str) else ""


def _parse_intent(intent: PaymentIntent | None) -> tuple[str, str, str, int, str] | None:
    """（given）意图统一解析：六字段齐全、金额正整数分 → 归一五元组；任何畸形 → None。"""
    if intent is None:
        return None
    claim_id = _text(getattr(intent, "claim_id", None))
    vendor = _text(getattr(intent, "vendor", None)).lower()
    dept = _text(getattr(intent, "dept", None))
    category = _text(getattr(intent, "category", None))
    content_hash = _text(getattr(intent, "content_hash", None))
    amount = getattr(intent, "amount_cents", None)
    if type(amount) is not int or amount <= 0:
        return None
    if not claim_id or not vendor or not dept or not category or not content_hash:
        return None
    return claim_id, vendor, dept, amount, content_hash


def _parse_paid(entry: Mapping[str, Any]) -> int | None:
    """（given）读单条已付记录的金额；不可解析返回 None（调用方必须当 DENY 处理）。"""
    amount = entry.get("amount_cents")
    if type(amount) is not int or amount <= 0:
        return None
    if not _text(entry.get("vendor")) or not _text(entry.get("dept")) or not _text(entry.get("category")):
        return None
    return amount


def _approval_issue(policy: Policy, parsed: tuple[str, str, str, int, str], approval: ApprovalRecord | None):
    """（given）① 审批单二次校验（A7+A6）：不在场 / 非 CONFIRMED / 指纹不符 → DENY。"""
    _claim_id, _vendor, _dept, _amount, content_hash = parsed
    if approval is None:
        return GateVerdict("DENY", "approval_missing", "no approval record on file (fail-closed)")
    decision = getattr(approval, "decision", None)
    approved_hash = getattr(approval, "content_hash", None)
    if decision != _APPROVAL_CONFIRMED:
        return GateVerdict("DENY", "approval_not_confirmed", f"approval decision is {decision!r}, not CONFIRMED")
    if not isinstance(approved_hash, str) or not approved_hash.strip() or approved_hash != content_hash:
        return GateVerdict(
            "DENY", "approval_content_mismatch", f"approved {approved_hash!r} != intent {content_hash!r}"
        )
    return None


def _blocklist_issue(policy: Policy, parsed: tuple[str, str, str, int, str]):
    """（given）② 供应商黑名单：结构性 DENY，优先于定量检查。"""
    _claim_id, vendor, *_rest = parsed
    if vendor in {v.strip().lower() for v in policy.vendor_blocklist}:
        return GateVerdict("DENY", "vendor_blocklisted", f"{vendor} is on the vendor blocklist")
    return None


def check_intent(
    policy: Policy,
    intent: PaymentIntent | None,
    approval: ApprovalRecord | None,
    ledger: LedgerView | None,
) -> GateVerdict:
    """七查链体（参考答案）：统一入口 + 前两查 + 定量三查 + 收口。"""
    # ⑥ 统一入口：不可解析即 DENY——后面每一查都要解引用意图字段，先拦住 None/畸形。
    parsed = _parse_intent(intent)
    if parsed is None:
        return GateVerdict("DENY", "unparseable_intent", "payment intent unparseable (fields/amount_cents)")
    # ①② given 的前两查：审批单二次校验（A7+A6）与黑名单——首查命中即返回。
    issue = _approval_issue(policy, parsed, approval)
    if issue is not None:
        return issue
    issue = _blocklist_issue(policy, parsed)
    if issue is not None:
        return issue
    _claim_id, _vendor, _dept, effective, _content_hash = parsed
    clamp: int | None = None
    # ③ 单笔上限：clamp 开则裁到上限继续查（只缩不放）。
    if effective > policy.max_single_cents:
        if not policy.clamp_overruns:
            return GateVerdict(
                "PAUSE_FOR_REAUTH", "single_over_limit", f"单笔 {effective} 分 > 上限 {policy.max_single_cents} 分"
            )
        clamp = policy.max_single_cents
        effective = clamp
    # ④ 当日累计：账本先逐条解析（fail-closed），再累计比较；clamp 开则裁到剩余额度。
    if ledger is None:
        return GateVerdict("DENY", "ledger_unreadable", "ledger view missing (fail-closed)")
    paid_total = 0
    for entry in ledger.payments:
        paid = _parse_paid(entry)
        if paid is None:
            return GateVerdict("DENY", "ledger_unreadable", f"ledger entry unparseable: {dict(entry)!r}")
        paid_total += paid
    if paid_total + effective > policy.max_daily_total_cents:
        if not policy.clamp_overruns:
            return GateVerdict(
                "PAUSE_FOR_REAUTH",
                "daily_over_limit",
                f"当日累计 {paid_total + effective} 分 > 上限 {policy.max_daily_total_cents} 分",
            )
        remaining = policy.max_daily_total_cents - paid_total
        if remaining <= 0:
            return GateVerdict("PAUSE_FOR_REAUTH", "daily_over_limit", "当日额度已耗尽——裁不动")
        clamp = remaining
        effective = remaining
    # ⑤ 当日频次：笔数不可裁——clamp 也救不了，超次一律 PAUSE。
    if len(ledger.payments) + 1 > policy.max_payments_per_day:
        return GateVerdict("PAUSE_FOR_REAUTH", "frequency_over_limit", f"当日已付 {len(ledger.payments)} 笔，超次")
    # 收口：有过裁剪 → clamped + clamp_cents；否则原样放行。
    if clamp is not None:
        return GateVerdict("ALLOW", "clamped", f"超限裁剪至 {clamp} 分（clamp 只缩不放）", clamp)
    return GateVerdict("ALLOW", "allow", f"七查通过：{effective} 分原样放行")
