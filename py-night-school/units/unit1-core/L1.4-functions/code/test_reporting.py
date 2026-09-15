"""讲义示例测试：多级排序、三种推导式、带累加的分组循环。"""

from reporting import ClaimSummary, big_claims, rank_by_total, submitters, totals_by_submitter

CLAIMS = [
    ClaimSummary("CLM-2026-0001", "王工", 7100),
    ClaimSummary("CLM-2026-0002", "李工", 7100),
    ClaimSummary("CLM-2026-0003", "王工", 8800),
    ClaimSummary("CLM-2026-0004", "赵工", 1200),
]


def test_rank_by_total_then_submitter() -> None:
    ranked = rank_by_total(CLAIMS)
    # 金额降序；王工/李工同为 7100 分，按提交人升序。注意字符串默认按 Unicode 码点比较：
    # 李(U+674E) < 王(U+738B)——中文「字典序」并不保证，生产要按 locale 或专门键排序
    assert [c.claim_id for c in ranked] == ["CLM-2026-0003", "CLM-2026-0002", "CLM-2026-0001", "CLM-2026-0004"]


def test_ranking_does_not_mutate_input() -> None:
    snapshot = list(CLAIMS)
    rank_by_total(CLAIMS)
    assert CLAIMS == snapshot  # sorted 返回新列表（list.sort 才是原地版）


def test_big_claims_filters_and_keeps_order() -> None:
    assert [c.claim_id for c in big_claims(CLAIMS, 5000)] == ["CLM-2026-0001", "CLM-2026-0002", "CLM-2026-0003"]


def test_submitters_deduplicates() -> None:
    assert submitters(CLAIMS) == {"王工", "李工", "赵工"}


def test_totals_by_submitter() -> None:
    assert totals_by_submitter(CLAIMS) == {"王工": 15900, "李工": 7100, "赵工": 1200}
