# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""检查链补全：check_intent 的统一入口 + 定量三查（讲义 code/gate.py 的同构迷你版）。

given：全部值对象（Policy / PaymentIntent / ApprovalRecord / LedgerView / GateVerdict）、
两个解析器（_parse_intent / _parse_paid——fail-closed 的底层件）、前两查
（_approval_issue 审批单二次校验 A7+A6、_blocklist_issue 黑名单）。
TODO 只在最该练的一处——check_intent 的链体：

- ⑥ 统一入口：先问「意图可解析吗」——_parse_intent 的返回值什么时候意味着不可解析？
  不可解析的答案是 DENY（reason_code 用 unparseable_intent），不是崩溃；
- ③ 单笔上限：超了怎么办由 Policy.clamp_overruns 决定——False 时 PAUSE（single_over_limit），
  True 时把金额裁到上限**继续往下查**（裁剪值要记着，最后进 verdict）；
- ④ 当日累计：先逐条过 _parse_paid（任一条读不了即 DENY：ledger_unreadable——fail-closed），
  累计加上本笔超上限时同样二选一（PAUSE 或裁到当日剩余额度；剩余 ≤ 0 裁不动，PAUSE）；
- ⑤ 当日频次：已付条数 + 1 超上限即 PAUSE（frequency_over_limit）——笔数不可裁，clamp 也救不了；
- 全查通过：ALLOW（reason_code=allow）；有过裁剪：ALLOW（reason_code=clamped，clamp_cents=裁剪值）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——13 个测试（8 个函数，
fail-closed 参数化 6 例）：
  三态各一幕（ALLOW/PAUSE/DENY）；③④⑤ 各一个「只破这项」用例（含 clamp 两态）；
  覆盖型 meta（用例表 11 种 reason_code 齐、三态齐、表 11 行）；短路顺序（黑名单先于单笔）；
  fail-closed 参数化（None 意图/负数/字符串金额/bool 金额/缺字段/脏账本/None 账本）。
"""

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
    """（given）意图统一解析：六字段齐全、金额正整数分 → 归一五元组；任何畸形 → None。

    bool / float / 带单位字符串的金额都算畸形；vendor 小写归一（黑名单比较口径）。
    """
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
    """七查链体（你的 TODO）：统一入口 + 定量三查——题干 docstring 有完整契约。

    问：_parse_intent 返回什么的时候该 DENY？③ 超限且 clamp 开启时，「继续查」用的
    金额是原值还是裁剪值？④ 的账本逐条解析发生在累计比较之前还是之后？⑤ 为什么
    clamp 救不了频次？全查通过时 clamp_cents 给什么？
    """
    # TODO(ex1): ⑥ 统一入口——不可解析即 DENY（unparseable_intent），然后跑 given 的 ①②
    # TODO(ex1): ③ 单笔上限（PAUSE 或裁到上限继续）
    # TODO(ex1): ④ 当日累计（账本先逐条解析——读不了即 DENY；超限 PAUSE 或裁到剩余额度）
    # TODO(ex1): ⑤ 当日频次（笔数不可裁——超次一律 PAUSE）
    # TODO(ex1): 收口——无裁剪 ALLOW(allow)；有裁剪 ALLOW(clamped, clamp_cents=裁剪值)
    raise NotImplementedError("TODO(ex1): check_intent 链体")
