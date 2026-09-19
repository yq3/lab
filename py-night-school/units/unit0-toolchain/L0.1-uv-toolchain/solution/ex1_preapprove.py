"""参考答案（ex1）——先完成练习再看；不追求与你的写法一致，追求通过验收且读得舒服。"""

DAILY_MEAL_LIMIT_CENTS = 5000
TRIP_TOTAL_LIMIT_CENTS = 500000


def preapprove(items_cents: list[int]) -> str:
    if any(c <= 0 for c in items_cents):
        return "REJECT:INVALID_AMOUNT"
    if any(c > DAILY_MEAL_LIMIT_CENTS for c in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    if sum(items_cents) > TRIP_TOTAL_LIMIT_CENTS:
        return "REJECT:TOTAL_OVER_LIMIT"
    return "PASS"
