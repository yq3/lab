"""讲义示例测试：规则链与 L0.1 的 preapprove 行为一致，且「规则是数据」可动态增删。"""

import pytest

import preapprove_rules as m
from preapprove_rules import describe_rules, preapprove


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([1200, 3500, 2400], "PASS"),
        ([5000], "PASS"),  # 边界：恰好等于单笔上限
        ([5000] * 100, "PASS"),  # 边界：合计恰好 500000
        ([5001], "REJECT:ITEM_OVER_LIMIT"),
        ([0], "REJECT:INVALID_AMOUNT"),
        ([-100, 200], "REJECT:INVALID_AMOUNT"),
        ([4000] * 126, "REJECT:TOTAL_OVER_LIMIT"),
        # 冲突用例：规则顺序即返回优先级（与 L0.1 完全同口径）
        ([8800, -1], "REJECT:INVALID_AMOUNT"),
        ([5001] + [4999] * 100, "REJECT:ITEM_OVER_LIMIT"),
    ],
)
def test_preapprove_matches_l01_behavior(items: list[int], expected: str) -> None:
    assert preapprove(items) == expected


def test_rules_carry_their_own_names() -> None:
    # __name__：函数对象的元数据，日志与追踪不用注解就有名字
    assert describe_rules() == ["check_invalid", "check_item_limit", "check_total_limit"]


def test_chain_is_data_not_control_flow() -> None:
    """架构判据：往 RULES 头部插一条规则，行为必须立刻变——证明 preapprove 真的在消费这个列表。"""
    original = m.RULES[:]
    try:
        m.RULES.insert(0, lambda items: "REJECT:BLACKLISTED" if sum(items) > 100000 else None)
        assert m.preapprove([50000, 60000]) == "REJECT:BLACKLISTED"
        assert m.preapprove([1200]) == "PASS"  # 未命中的注入规则放行，后续规则照常工作
        assert m.describe_rules()[0] == "<lambda>"  # lambda 的 __name__ 固定叫 <lambda>——名字即文档的理由
    finally:
        m.RULES[:] = original  # 测试不留痕：还原现场
    assert m.preapprove([4000] * 126) == "REJECT:TOTAL_OVER_LIMIT"  # 还原后回到原行为
