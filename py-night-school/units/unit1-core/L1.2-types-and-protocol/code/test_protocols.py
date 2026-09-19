"""讲义测试：结构化类型——isinstance 通过、无继承关系、规则链可用。"""

from protocols import DirtyDataRule, ItemLimitRule, Rule, run_rules


def test_structural_isinstance() -> None:
    """runtime_checkable 协议的 isinstance 只查「方法在不在」，不查签名与实现。"""
    for rule in (ItemLimitRule(5000), DirtyDataRule()):
        assert isinstance(rule, Rule)


def test_no_inheritance() -> None:
    """两个实现的 __bases__ 都是 (object,)——与 Rule 没有继承关系，纯长得像。"""
    for cls in (ItemLimitRule, DirtyDataRule):
        assert cls.__bases__ == (object,)


def test_run_rules_priority() -> None:
    # 显式标注 list[Rule]：list 是不变的（invariant），让 pyright 按协议类型理解元素
    rules: list[Rule] = [DirtyDataRule(), ItemLimitRule(5000)]
    assert run_rules(rules, [1200, 3500]) == "PASS"
    assert run_rules(rules, [8800]) == "REJECT:ITEM_OVER_LIMIT"
    assert run_rules(rules, [-1]) == "REJECT:INVALID_AMOUNT"
    assert run_rules(rules, [8800, -1]) == "REJECT:INVALID_AMOUNT"  # 顺序即优先级
