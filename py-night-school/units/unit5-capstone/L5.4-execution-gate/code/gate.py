"""fail-closed 执行门——纯函数检查链（本课核心①，A7/A8 在毕业设计自己域里的落地）。

对版关系：L4.3 在付款域写过 check_payment 七查（Vibe-Trading check_mandate 八查的教学
裁剪）；今晚把它移植进**自己的 PoC**，并新增毕业设计自己的第一查——审批单二次校验
（A7 执行侧二次校验 + A6 内容版本绑定：决策层批了不算数，执行出口再查一次
「真批了吗、批的是这版吗」——纵深防御，防中间层缺位/被绕过）。

固定顺序七查（首查命中即停——顺序本身是审计契约，改序 = 改语义）：

  ⑥′ 意图可解析（金额正整数分、六字段齐全）      → DENY unparseable_intent
  ①  审批单在场且 CONFIRMED（A7：只执行 CONFIRMED）→ DENY approval_missing / approval_not_confirmed
  ②′ 审批指纹匹配（A6：批的是这版内容吗）         → DENY approval_content_mismatch
  ②  供应商黑名单                                → DENY vendor_blocklisted
  ③  单笔上限                                    → PAUSE single_over_limit（或 clamp 后放行）
  ④  当日累计（账本逐条解析，读不了即 DENY）        → PAUSE daily_over_limit（或 clamp 后放行）
  ⑤  当日频次                                    → PAUSE frequency_over_limit（笔数不可裁）

「意图可解析」放最前是短路顺序的必然：后面每一查都要解引用意图字段，先拦住 None/
畸形，检查链才永远对一个「形状完整」的对象说话——任何不可解析输入的答案是 DENY，
不是 TypeError（fail-closed 拒绝的是「带着脏数据放行」，不是「程序崩溃」）。

三态裁决（对版 L4.3）：结构性违规（不可解析 / 审批缺位 / 指纹不符 / 黑名单 / 账本不可读）
→ DENY——不修改合同就永远不可能放行；定量违规（单笔 / 累计 / 频次超限）→
PAUSE_FOR_REAUTH，或按 Policy.clamp_overruns 裁到限额后放行（clamp 只缩不放，
GateVerdict.clamp_cents 带裁剪后金额）；频次是唯一不可 clamp 的定量维度——一笔就是
一笔，裁不出 0.7 笔，超次一律 PAUSE。

时钟纪律（对版 L4.3 TodaySnapshot / L5.3 事件钟）：本模块零 IO、绝不取系统时钟——
「今天几号、今天已付了什么」装进 LedgerView 由调用方注入（today 是注入的 ISO 日期
字符串；已付清单是 payment.executed 事件的投影）。同一个 (policy, intent, approval,
ledger) 永远同一个裁决，测试不随墙钟漂移——门才 fail-closed 得起来（讲义 §5 坑位）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

#: 三态裁决（对版 L4.3 的 DENY / PAUSE_FOR_REAUTH / ALLOW）。
GateAction = Literal["ALLOW", "DENY", "PAUSE_FOR_REAUTH"]

#: 拒绝/暂停原因枚举（11 种：2 放行 + 3 定量暂停 + 6 结构拒绝——枚举风格纪律）。
GateReason = Literal[
    "allow",  # 全查通过，原样放行
    "clamped",  # 定量超限被裁到限额后放行（clamp_cents 带裁剪值）
    "single_over_limit",  # PAUSE：单笔超上限
    "daily_over_limit",  # PAUSE：当日累计超上限
    "frequency_over_limit",  # PAUSE：当日笔数超上限（不可 clamp）
    "unparseable_intent",  # DENY：付款意图不可解析（fail-closed 第一查）
    "approval_missing",  # DENY：审批单不在场（A7）
    "approval_not_confirmed",  # DENY：审批单不是 CONFIRMED（A7：只执行 CONFIRMED）
    "approval_content_mismatch",  # DENY：审批绑定的内容指纹与执行意图不符（A6）
    "vendor_blocklisted",  # DENY：收款方在黑名单
    "ledger_unreadable",  # DENY：当日账本读不了（fail-closed——宁可不付，不带脏账放行）
]

_APPROVAL_CONFIRMED = "CONFIRMED"  # A7 的执行侧状态词（决策层「批了」在执行侧的学名）


@dataclass(frozen=True)
class Policy:
    """执行门的限额合同（对版 L4.3 HardCaps + PayUniverse 的合并裁剪）。

    Attributes:
        max_single_cents: 单笔付款上限（整数分）。
        max_daily_total_cents: 当日累计付款上限（含当日已付，整数分）。
        max_payments_per_day: 当日付款笔数上限。
        vendor_blocklist: 收款方硬黑名单（比较前小写归一），优先于定量检查。
        clamp_overruns: 定量超限的处置——False（缺省）超限即 PAUSE_FOR_REAUTH；
            True 时裁到限额后放行（clamp 只缩不放；频次维度不可裁，仍 PAUSE）。
    """

    max_single_cents: int
    max_daily_total_cents: int
    max_payments_per_day: int
    vendor_blocklist: tuple[str, ...]
    clamp_overruns: bool = False


#: 教学缺省合同：宽到四单 mock 素材全部原样放行——真实部署应显式注入 Policy
#: （缺省是「便利」不是「安全默认」：fail-closed 的对象是检查链的输入，不是装配参数）。
DEFAULT_POLICY = Policy(
    max_single_cents=1_000_000,
    max_daily_total_cents=10_000_000,
    max_payments_per_day=50,
    vendor_blocklist=(),
)


@dataclass(frozen=True)
class PaymentIntent:
    """一笔付款意图（L4.3 PaymentIntent 的毕业设计版：域字段 + A6 内容指纹）。

    Attributes:
        claim_id: 报销单号。
        vendor: 收款方标识（报销款收款方 = 提单人；比较前小写归一）。
        dept: 部门码（账本对账维度）。
        category: 科目描述（素材无科目字段，以用途文本代位——门只校验非空齐全）。
        amount_cents: 金额，整数「分」。None / 负数 / 零 / float / bool / 字符串都算**不可解析**。
        content_hash: 被审内容的指纹——与审批单上的指纹逐字比对（A6）。
    """

    claim_id: str
    vendor: str
    dept: str
    category: str
    amount_cents: int
    content_hash: str


@dataclass(frozen=True)
class ApprovalRecord:
    """审批面的回执（L5.2 审批单在执行侧的读法——A7 二次校验的对象）。

    Attributes:
        ticket_id: 审批单号（审计溯源用）。
        decision: 审批决定；执行门只认 ``CONFIRMED``（once / always / 规则自动批准都归它）。
        content_hash: 审批发生时绑定的内容指纹——「批的是哪一版」由它锁定（A6）。
        approved_at: 批准时刻（ISO 字符串，注入时钟产物；留档用，本门不校验有效期）。
    """

    ticket_id: str
    decision: str
    content_hash: str
    approved_at: str


@dataclass(frozen=True)
class LedgerView:
    """当日账本视图（检查链唯一的「世界状态」输入，对版 L4.3 TodaySnapshot）。

    Attributes:
        today: 「今天」——注入的 ISO 日期字符串（yyyy-mm-dd），门不取系统时钟。
        payments: 当日已付清单（日历聚合上 payment.executed 事件的投影）。每条是带
            vendor/dept/category/amount_cents 键的映射；**任何一条不可解析 → 整链 DENY**
            （fail-closed：宁可不付，不带脏账放行）。
    """

    today: str
    payments: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class GateVerdict:
    """门的一次裁决（对版 L4.3 Breach 的「正面陈述」版：连 ALLOW 也显式返回）。

    Attributes:
        action: 三态之一（GateAction）。
        reason_code: 枚举原因码（GateReason）——审计与终态 advice 分码的依据。
        detail: 人类可读说明（含命中的限额与数字）。
        clamp_cents: 裁剪后的实付金额——仅 ``clamp_overruns`` 生效且确有裁剪时非 None。
    """

    action: GateAction
    reason_code: GateReason
    detail: str
    clamp_cents: int | None = None


def _text(value: Any) -> str:
    """读一个「必须是非空字符串」的字段；读不到返回空串（调用方按不可解析处理）。"""
    return value.strip() if isinstance(value, str) else ""


def _parse_intent(intent: PaymentIntent | None) -> tuple[str, str, str, int, str] | None:
    """意图统一解析：六字段齐全、金额正整数分 → 归一五元组；任何畸形 → None。

    ``type(amount_cents) is not int`` 连 float 和 bool 一起拒（bool 是 int 子类——
    L4.3 的老坑，宁可误杀不可放过）。vendor 小写归一（黑名单比较口径）。
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
    """读单条已付记录的金额；不可解析返回 None（调用方必须当 DENY 处理——fail-closed）。

    与 _parse_intent 同款纪律：金额正整数分（bool/float/字符串一律拒），
    vendor/dept/category 非空字符串（账本要能对账，不能只有数字）。
    """
    amount = entry.get("amount_cents")
    if type(amount) is not int or amount <= 0:
        return None
    if not _text(entry.get("vendor")) or not _text(entry.get("dept")) or not _text(entry.get("category")):
        return None
    return amount


def check_intent(
    policy: Policy | None,
    intent: PaymentIntent | None,
    approval: ApprovalRecord | None,
    ledger: LedgerView | None,
) -> GateVerdict:
    """对一笔付款意图跑七查（固定顺序，首查命中即返回，fail-closed）。

    Args:
        policy: 限额合同；None 视为不可解析 → DENY（门没有合同就不开门）。
        intent: 待裁决的付款意图；None / 畸形 → DENY unparseable_intent。
        approval: 审批面回执；None / 非 CONFIRMED / 指纹不符 → DENY（A7/A6）。
        ledger: 注入的当日账本视图；None 或任一条目不可解析 → DENY（fail-closed）。

    Returns:
        三态裁决 :class:`GateVerdict`——连 ALLOW 也显式返回（对照 L4.3 返回
        ``Breach | None``：这里把「通过」也做成带原因码的一等值，审计口径统一）。
    """
    # ⑥′ 意图可解析——统一入口：任何 None/畸形在这里变成 DENY，而不是 TypeError。
    parsed = _parse_intent(intent)
    if parsed is None:
        return GateVerdict("DENY", "unparseable_intent", "payment intent unparseable (fields/amount_cents)")
    _claim_id, vendor, _dept, amount, content_hash = parsed
    if policy is None:
        return GateVerdict("DENY", "unparseable_intent", "policy missing (gate has no contract)")

    # ① 审批单二次校验（A7：只执行 CONFIRMED）——决策层批了不算数，执行出口再查一次。
    if approval is None:
        return GateVerdict("DENY", "approval_missing", "no approval record on file (fail-closed)")
    approved_decision = getattr(approval, "decision", None)
    approved_hash = getattr(approval, "content_hash", None)
    if approved_decision != _APPROVAL_CONFIRMED:
        return GateVerdict(
            "DENY", "approval_not_confirmed", f"approval decision is {approved_decision!r}, not CONFIRMED"
        )
    if not isinstance(approved_hash, str) or not approved_hash.strip() or approved_hash != content_hash:
        return GateVerdict(
            "DENY",
            "approval_content_mismatch",
            f"approved content_hash {approved_hash!r} != intent {content_hash!r}（批的不是这版）",
        )

    # ② 供应商黑名单——结构性违规，优先于一切定量检查（对版 L4.3 exclude-list）。
    if vendor in {v.strip().lower() for v in policy.vendor_blocklist}:
        return GateVerdict("DENY", "vendor_blocklisted", f"{vendor} is on the vendor blocklist")

    # ③④⑤ 定量三查：clamp_overruns=False 时超限即 PAUSE；True 时裁到限额继续查。
    effective = amount
    clamp: int | None = None

    # ③ 单笔上限。
    if effective > policy.max_single_cents:
        if not policy.clamp_overruns:
            return GateVerdict(
                "PAUSE_FOR_REAUTH",
                "single_over_limit",
                f"单笔 {effective} 分 > 上限 {policy.max_single_cents} 分（重新授权或拆单人审）",
            )
        if policy.max_single_cents <= 0:
            return GateVerdict("PAUSE_FOR_REAUTH", "single_over_limit", "上限非正——裁不动，转重新授权")
        clamp = policy.max_single_cents
        effective = clamp

    # ④ 当日累计：先逐条解析账本——任一条不可解析 = DENY（fail-closed）。
    if ledger is None:
        return GateVerdict("DENY", "ledger_unreadable", "ledger view missing (fail-closed)")
    paid_total = 0
    for entry in ledger.payments:
        paid = _parse_paid(entry)
        if paid is None:
            return GateVerdict(
                "DENY", "ledger_unreadable", f"today's ledger entry unparseable: {dict(entry)!r}（fail-closed）"
            )
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
            return GateVerdict("PAUSE_FOR_REAUTH", "daily_over_limit", "当日额度已耗尽——裁不动，转重新授权")
        clamp = remaining
        effective = remaining

    # ⑤ 当日频次：笔数不可 clamp——一笔就是一笔，超次一律 PAUSE（取舍：宁可整笔暂停）。
    if len(ledger.payments) + 1 > policy.max_payments_per_day:
        return GateVerdict(
            "PAUSE_FOR_REAUTH",
            "frequency_over_limit",
            f"当日已付 {len(ledger.payments)} 笔，上限 {policy.max_payments_per_day} 笔（笔数不可裁）",
        )

    if clamp is not None:
        return GateVerdict("ALLOW", "clamped", f"超限裁剪：{amount} 分 → {clamp} 分（clamp 只缩不放）", clamp)
    return GateVerdict("ALLOW", "allow", f"七查通过：{amount} 分原样放行")
