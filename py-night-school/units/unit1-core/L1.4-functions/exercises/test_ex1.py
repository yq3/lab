"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import pytest

import ex1_rule_chain as m
from ex1_rule_chain import preapprove

# 与 L0.1 同口径的用例表：四种结果 + 边界 + 冲突优先级
CASES: list[tuple[list[int], str]] = [
    ([1200, 3500, 2400], "PASS"),
    ([5000], "PASS"),
    ([5000] * 100, "PASS"),
    ([5001], "REJECT:ITEM_OVER_LIMIT"),
    ([8800], "REJECT:ITEM_OVER_LIMIT"),
    ([0], "REJECT:INVALID_AMOUNT"),
    ([-100, 200], "REJECT:INVALID_AMOUNT"),
    ([4000] * 126, "REJECT:TOTAL_OVER_LIMIT"),
    ([4999] * 101, "REJECT:TOTAL_OVER_LIMIT"),
    # 冲突用例：规则顺序即返回优先级
    ([8800, -1], "REJECT:INVALID_AMOUNT"),  # 脏数据优先于单笔超限
    ([5001] + [4999] * 100, "REJECT:ITEM_OVER_LIMIT"),  # 单笔超限优先于合计超限
]


@pytest.mark.parametrize(("items", "expected"), CASES)
def test_ex1_rules(items: list[int], expected: str) -> None:
    assert preapprove(items) == expected


def test_ex1_cases_cover_all_outcomes() -> None:
    """验收的验收：用例表本身必须覆盖全部结果种类、含边界与冲突（延续 L0.1 ex2 的 meta 风格）。"""
    outcomes = {expected for _, expected in CASES}
    assert outcomes == {"PASS", "REJECT:INVALID_AMOUNT", "REJECT:ITEM_OVER_LIMIT", "REJECT:TOTAL_OVER_LIMIT"}
    assert any(expected == "PASS" and items in ([5000], [5000] * 100) for items, expected in CASES), (
        "边界用例：恰好等于上限应 PASS"
    )
    conflicts = [items for items, _ in CASES if len([x for x in items if x <= 0]) > 0 and any(x > 5000 for x in items)]
    assert conflicts, "冲突用例：脏数据与单笔超限同现，验证优先级"


def test_ex1_chain_is_data_not_hardcoded_ifs() -> None:
    """架构判据：往 RULES 注入一条规则，preapprove 的行为必须随之改变。

    如果你在 preapprove 里硬编码了 if 链（不消费 RULES），本测试会失败——
    「规则是数据」正是框架 guardrail / 中间件能动态装配的原因。
    """
    original = m.RULES[:]
    try:
        m.RULES.insert(0, lambda items: "REJECT:BLACKLISTED" if sum(items) > 100000 else None)
        assert m.preapprove([50000, 60000]) == "REJECT:BLACKLISTED"
        assert m.preapprove([1200]) == "PASS"
    finally:
        m.RULES[:] = original
    assert m.preapprove([4000] * 126) == "REJECT:TOTAL_OVER_LIMIT"
