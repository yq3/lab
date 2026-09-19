"""讲义示例测试：expense 包的行为 + 包身份（模块名）双验证。"""

import pytest

import expense
from expense import rules
from expense.rules import preapprove


def test_package_identity() -> None:
    """包内模块的 __name__ 带「包名.」前缀——被导入时它不是 "__main__"。"""
    assert expense.__name__ == "expense"
    assert rules.__name__ == "expense.rules"


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([1200, 3500, 2400], "PASS"),
        ([5000], "PASS"),  # 边界：恰好等于上限不是「超过」
        ([5000] * 100, "PASS"),  # 边界：合计恰好 500000 分
        ([5001], "REJECT:ITEM_OVER_LIMIT"),
        ([0], "REJECT:INVALID_AMOUNT"),
        ([-100, 200], "REJECT:INVALID_AMOUNT"),
        ([4000] * 126, "REJECT:TOTAL_OVER_LIMIT"),  # 合计 504000 分
        ([8800, -1], "REJECT:INVALID_AMOUNT"),  # 规则顺序即返回优先级
    ],
)
def test_preapprove_rules(items: list[int], expected: str) -> None:
    assert preapprove(items) == expected
