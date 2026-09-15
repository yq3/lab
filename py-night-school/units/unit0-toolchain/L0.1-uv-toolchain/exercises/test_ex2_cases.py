# 练习 2（单变量编辑约束：只补 TODO 标注的列表内容）
"""为参数化测试补全用例表——学会「测试也是代码要维护的资产」。

要求补 5 组 (items, expected)，必须覆盖：
  PASS、REJECT:INVALID_AMOUNT、REJECT:ITEM_OVER_LIMIT、REJECT:TOTAL_OVER_LIMIT，
以及至少一个边界用例（恰好等于上限时应当 PASS）。

注意：本测试依赖练习 1 的 preapprove 已完成（先做 ex1）。
完成后：uv run pytest exercises/test_ex2_cases.py 全绿。
"""

import pytest

from ex1_preapprove import preapprove


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        # TODO(ex2): 在此补全 5 组用例，形如 ([1200, 3500], "PASS"),
    ],
)
def test_ex2_rules(items: list[int], expected: str) -> None:
    assert preapprove(items) == expected
