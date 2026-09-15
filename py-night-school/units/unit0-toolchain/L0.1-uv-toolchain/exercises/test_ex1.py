"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import pytest

from ex1_preapprove import preapprove


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([1200, 3500, 2400], "PASS"),
        ([5000], "PASS"),
        ([5000] * 100, "PASS"),
        ([5001], "REJECT:ITEM_OVER_LIMIT"),
        ([8800], "REJECT:ITEM_OVER_LIMIT"),
        ([0], "REJECT:INVALID_AMOUNT"),
        ([-100, 200], "REJECT:INVALID_AMOUNT"),
        ([4000] * 126, "REJECT:TOTAL_OVER_LIMIT"),
        ([4999] * 101, "REJECT:TOTAL_OVER_LIMIT"),  # 合计 504899 分，单笔均合法
        # 冲突用例：规则顺序即返回优先级
        ([8800, -1], "REJECT:INVALID_AMOUNT"),  # 脏数据优先于单笔超限
        ([5001] + [4999] * 100, "REJECT:ITEM_OVER_LIMIT"),  # 单笔超限优先于合计超限
    ],
)
def test_ex1_rules(items: list[int], expected: str) -> None:
    assert preapprove(items) == expected
