"""讲义示例测试：体验 pytest 三种最常用形态。

对照 Java：函数名 test_ 开头即测试（无需 @Test 注解）；
assert 是语言关键字（无需 Assertions.assertEquals）；
@pytest.mark.parametrize 对应 JUnit 5 的 @ParameterizedTest。
"""

import pytest

from budget import preapprove


def test_normal_claim_passes() -> None:
    assert preapprove([1200, 3500, 2400]) == "PASS"


def test_single_oversized_item_rejected() -> None:
    assert preapprove([1200, 8800]) == "REJECT:ITEM_OVER_LIMIT"


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([100], "PASS"),
        # 边界：恰好等于上限不是「超过」，应放行
        ([5000], "PASS"),
        ([5000] * 100, "PASS"),  # 合计恰好 500000 分
        ([5001], "REJECT:ITEM_OVER_LIMIT"),
        ([0], "REJECT:INVALID_AMOUNT"),
        ([-100, 200], "REJECT:INVALID_AMOUNT"),
        ([4000] * 126, "REJECT:TOTAL_OVER_LIMIT"),  # 合计 504000 分
        # 冲突用例：三条规则的判定顺序就是返回优先级（脏数据 > 单笔 > 合计）
        ([8800, -1], "REJECT:INVALID_AMOUNT"),
        ([5001] + [4999] * 100, "REJECT:ITEM_OVER_LIMIT"),
    ],
)
def test_rules(items: list[int], expected: str) -> None:
    assert preapprove(items) == expected
