"""报销单预审规则——从 L0.1 的 budget.py 迁入包内（一字未改规则本体）。

模块 = 文件：这个文件的名字 rules 就是模块名，全名是「包名.模块名」= expense.rules。
对照 Java：一个文件必须与公共类同名；Python 无此约束，文件名本身就取了个模块名。

金额一律整数「分」；返回码沿用明线约定 "PASS" / "REJECT:<原因>"。
"""

# 单笔报销上限：5000 分（50 元）
DAILY_MEAL_LIMIT_CENTS = 5000
# 单张报销单合计上限：500000 分（5000 元）
TRIP_TOTAL_LIMIT_CENTS = 500000


def preapprove(items_cents: list[int]) -> str:
    """对一张报销单的明细金额做预审，返回放行或拒绝原因。

    规则（按优先级）：
    1. 任意金额 <= 0                        -> "REJECT:INVALID_AMOUNT"   脏数据最先挡
    2. 任意单笔 > DAILY_MEAL_LIMIT_CENTS     -> "REJECT:ITEM_OVER_LIMIT"
    3. 合计 > TRIP_TOTAL_LIMIT_CENTS         -> "REJECT:TOTAL_OVER_LIMIT"
    4. 以上都未命中                          -> "PASS"
    """
    if any(c <= 0 for c in items_cents):
        return "REJECT:INVALID_AMOUNT"
    if any(c > DAILY_MEAL_LIMIT_CENTS for c in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    if sum(items_cents) > TRIP_TOTAL_LIMIT_CENTS:
        return "REJECT:TOTAL_OVER_LIMIT"
    return "PASS"
