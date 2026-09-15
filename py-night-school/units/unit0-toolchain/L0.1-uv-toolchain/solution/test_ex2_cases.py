"""参考答案（ex2）——用例表本身也要过「验收的验收」（meta-test）。

要点：四种结果各一组 + 两个边界（恰好等于上限应 PASS）+ 两组冲突（验证规则顺序即优先级）。
"""

import pytest

from ex1_preapprove import DAILY_MEAL_LIMIT_CENTS, TRIP_TOTAL_LIMIT_CENTS, preapprove

CASES: list[tuple[list[int], str]] = [
    ([1200, 3500, 2400], "PASS"),
    ([5000], "PASS"),  # 边界：单笔恰好等于上限
    ([5000] * 100, "PASS"),  # 边界：合计恰好 500000
    ([-100], "REJECT:INVALID_AMOUNT"),
    ([8800, -1], "REJECT:INVALID_AMOUNT"),  # 冲突：脏数据优先于单笔超限
    ([5001], "REJECT:ITEM_OVER_LIMIT"),
    ([5001] + [4999] * 100, "REJECT:ITEM_OVER_LIMIT"),  # 冲突：单笔超限优先于合计超限
    ([4000] * 126, "REJECT:TOTAL_OVER_LIMIT"),
]


@pytest.mark.parametrize(("items", "expected"), CASES)
def test_ex2_rules(items: list[int], expected: str) -> None:
    assert preapprove(items) == expected


def test_ex2_cases_cover_all_outcomes() -> None:
    """验收的验收：题目对用例表的覆盖要求，由它机器判定（不要改本函数）。"""
    outcomes = {expected for _, expected in CASES}
    required = {
        "PASS",
        "REJECT:INVALID_AMOUNT",
        "REJECT:ITEM_OVER_LIMIT",
        "REJECT:TOTAL_OVER_LIMIT",
    }
    missing = required - outcomes
    assert not missing, f"用例表缺少结果种类：{sorted(missing)}"
    assert len(CASES) >= 5, "至少 5 组用例"
    has_boundary = any(
        expected == "PASS" and (max(items) == DAILY_MEAL_LIMIT_CENTS or sum(items) == TRIP_TOTAL_LIMIT_CENTS)
        for items, expected in CASES
    )
    assert has_boundary, "至少一个边界用例：单笔或合计恰好等于上限且 PASS"
