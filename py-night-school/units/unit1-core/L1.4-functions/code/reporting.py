"""多级排序与推导式——把 Java Stream 的 map / filter / collect 翻译成 Python 日常写法。

Python 的日常主力不是 map/filter 函数，而是三种推导式（comprehension）：
  [expr for x in xs if cond]        列表推导式  ≈ stream().filter().map().collect(toList())
  {k_expr: v_expr for x in xs}      字典推导式  ≈ collect(toMap(...))
  {expr for x in xs}                集合推导式  ≈ collect(toSet())
纪律：嵌套不超过两层；带累加的分组逻辑用普通循环（别硬凹推导式）。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimSummary:
    """报销单摘要（L1.3 的 frozen dataclass 复用：不可变值对象，排序时不怕被改）。"""

    claim_id: str
    submitter: str
    total_cents: int


def rank_by_total(claims: list[ClaimSummary]) -> list[ClaimSummary]:
    """多级排序：合计降序，同金额按提交人升序。

    key 是「函数当参数」的标准现场：sorted 对每个元素调用 key 函数，按返回值排序。
    多级排序的惯用法：key 返回元组（-total_cents, submitter），元组按字典序逐项比较——
    负号把「金额越大越靠前」翻译成「数值越小越靠前」。Java 对照：
    Comparator.comparingLong(ClaimSummary::totalCents).reversed().thenComparing(ClaimSummary::submitter)
    """
    return sorted(claims, key=lambda c: (-c.total_cents, c.submitter))


def big_claims(claims: list[ClaimSummary], limit_cents: int) -> list[ClaimSummary]:
    """列表推导式 = filter + map + collect 一行：筛出合计超限的单子，按入参顺序保持稳定。"""
    return [c for c in claims if c.total_cents > limit_cents]


def submitters(claims: list[ClaimSummary]) -> set[str]:
    """集合推导式：去重的提交人名单。"""
    return {c.submitter for c in claims}


def totals_by_submitter(claims: list[ClaimSummary]) -> dict[str, int]:
    """分组求和：提交人 -> 合计分。

    带累加状态的分组用普通 for 循环最直白（dict.get(k, 0) 是「没有就当 0」的地道写法）。
    Java 的 Collectors.groupingBy + summingInt 在 Python 的对应物是 collections.defaultdict，
    L1.6 迭代器课再升级——本课先记住：推导式不是万能，别硬凹。
    """
    totals: dict[str, int] = {}
    for claim in claims:
        totals[claim.submitter] = totals.get(claim.submitter, 0) + claim.total_cents
    return totals
