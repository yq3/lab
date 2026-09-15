"""报销单预审——夜校明线「报销单审查」的核心规则（纯函数，好测试）。

金额一律用整数「分」表示：Java 里用 long 存分的习惯，在 Python 同样成立，
且天然避开浮点误差（0.1 + 0.2 != 0.3 的问题与财务代码无缘）。

本函数在后续课程的归宿：Unit 2 成为 mini-agent 的第一个工具，
Unit 5 毕业设计中并入 fail-closed 执行门的检查链。
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
