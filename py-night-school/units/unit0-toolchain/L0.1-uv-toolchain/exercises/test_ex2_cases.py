# 练习 2（单变量编辑约束：只补 TODO 标注的 CASES 列表内容）
"""为参数化测试补全用例表——学会「测试也是要维护的代码资产」。

要求（验收的验收 test_ex2_cases_cover_all_outcomes 会机器判定）：
  1. 至少 5 组 (items, expected)；
  2. 四种返回结果各至少一组：PASS / REJECT:INVALID_AMOUNT / REJECT:ITEM_OVER_LIMIT / REJECT:TOTAL_OVER_LIMIT；
  3. 至少一个边界用例：单笔或合计恰好等于上限、且期望为 PASS。
加分项（不强制）：加一组冲突用例，例如同时含脏数据与单笔超限，验证「规则顺序即优先级」。

注意：本测试依赖练习 1 的 preapprove 已完成（先做 ex1）。
完成后：uv run pytest exercises/test_ex2_cases.py 全绿。
"""

import pytest

from ex1_preapprove import DAILY_MEAL_LIMIT_CENTS, TRIP_TOTAL_LIMIT_CENTS, preapprove

# TODO(ex2): 在此补全用例表，每行形如 ([1200, 3500], "PASS"),
CASES: list[tuple[list[int], str]] = []


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
