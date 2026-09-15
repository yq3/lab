"""Rule 协议与两个「无继承实现」——结构化类型的完整示例（本课高潮）。

对照 Java：这里没有任何 implements。ItemLimitRule / DirtyDataRule 与 Rule
的关系不是「继承来的」，而是「长得像」——pyright 认这个，这就是 Protocol。
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Rule(Protocol):
    """预审规则协议：任何带 apply(items) -> 判定字符串 的对象都是 Rule。

    方法体写 ...（Ellipsis）：协议只声明形状，不提供实现——
    对照 Java interface 方法没有方法体。
    """

    def apply(self, items: list[int]) -> str: ...


class ItemLimitRule:
    """单笔限额规则——注意：没有继承 Rule，形状对上就算数。"""

    def __init__(self, limit_cents: int) -> None:
        self.limit_cents = limit_cents

    def apply(self, items: list[int]) -> str:
        if any(c > self.limit_cents for c in items):
            return "REJECT:ITEM_OVER_LIMIT"
        return "PASS"


class DirtyDataRule:
    """脏数据规则——同样没有继承。"""

    def apply(self, items: list[int]) -> str:
        if any(c <= 0 for c in items):
            return "REJECT:INVALID_AMOUNT"
        return "PASS"


def run_rules(rules: list[Rule], items: list[int]) -> str:
    """按顺序跑规则链，第一条 REJECT 即返回（规则顺序 = 优先级）。

    参数类型 list[Rule]：任何「长得像 Rule」的对象都能传进来——
    pyright 会在调用处做结构化检查（编译期版的鸭子类型）。
    """
    for rule in rules:
        verdict = rule.apply(items)
        if verdict != "PASS":
            return verdict
    return "PASS"
