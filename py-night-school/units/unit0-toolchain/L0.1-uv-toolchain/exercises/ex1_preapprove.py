# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""报销单预审——轮到你写。规则与 code/budget.py 相同，测试见 test_ex1.py。

考察点：for/any/sum 的组合、提前返回的分支顺序（三条规则的优先级就是返回优先级）。
完成后：uv run pytest exercises/test_ex1.py 全绿。
"""

DAILY_MEAL_LIMIT_CENTS = 5000
TRIP_TOTAL_LIMIT_CENTS = 500000


def preapprove(items_cents: list[int]) -> str:
    """按优先级实现三条规则，全部未命中返回 "PASS"。

    1. 任意金额 <= 0                        -> "REJECT:INVALID_AMOUNT"
    2. 任意单笔 > DAILY_MEAL_LIMIT_CENTS     -> "REJECT:ITEM_OVER_LIMIT"
    3. 合计 > TRIP_TOTAL_LIMIT_CENTS         -> "REJECT:TOTAL_OVER_LIMIT"
    """
    raise NotImplementedError("TODO(ex1): 按 docstring 实现三条规则后删除本行")
