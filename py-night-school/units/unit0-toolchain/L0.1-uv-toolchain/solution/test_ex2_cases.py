"""参考答案（ex2）——5 组用例，含边界（恰好等于上限应 PASS）。"""

import pytest

from ex1_preapprove import preapprove


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([1200, 3500, 2400], "PASS"),
        ([5000], "PASS"),  # 边界：恰好等于单笔上限
        ([5000] * 100, "PASS"),  # 边界：合计恰好 500000
        ([-100], "REJECT:INVALID_AMOUNT"),
        ([4000] * 126, "REJECT:TOTAL_OVER_LIMIT"),
    ],
)
def test_ex2_rules(items: list[int], expected: str) -> None:
    assert preapprove(items) == expected
