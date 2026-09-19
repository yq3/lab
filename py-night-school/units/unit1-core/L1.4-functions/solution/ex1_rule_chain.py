"""参考答案（ex1）——先完成练习再看；不追求与你的写法一致，追求通过验收且读得舒服。

要点：规则函数统一「命中返回 str / 未命中返回 None」的形状；
preapprove 只消费 RULES 列表，不认识任何具体规则——注入测试正是为此。
"""

from collections.abc import Callable

DAILY_MEAL_LIMIT_CENTS = 5000
TRIP_TOTAL_LIMIT_CENTS = 500000

Rule = Callable[[list[int]], str | None]


def check_invalid(items_cents: list[int]) -> str | None:
    if any(c <= 0 for c in items_cents):
        return "REJECT:INVALID_AMOUNT"
    return None


def check_item_limit(items_cents: list[int]) -> str | None:
    if any(c > DAILY_MEAL_LIMIT_CENTS for c in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    return None


def check_total_limit(items_cents: list[int]) -> str | None:
    if sum(items_cents) > TRIP_TOTAL_LIMIT_CENTS:
        return "REJECT:TOTAL_OVER_LIMIT"
    return None


RULES: list[Rule] = [check_invalid, check_item_limit, check_total_limit]


def preapprove(items_cents: list[int]) -> str:
    for rule in RULES:
        verdict = rule(items_cents)
        if verdict is not None:
            return verdict
    return "PASS"
