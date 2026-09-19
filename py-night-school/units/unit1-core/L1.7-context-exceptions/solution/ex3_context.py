"""参考答案（ex3）——保存 -> 修改 -> yield -> finally 恢复：@contextmanager 的标准四步。"""

from collections.abc import Iterator
from contextlib import contextmanager

DAILY_MEAL_LIMIT_CENTS = 5000


def check_item(amount_cents: int) -> str:
    """单笔检查（已写好，不要改）：读全局限额。"""
    if amount_cents > DAILY_MEAL_LIMIT_CENTS:
        return "REJECT:ITEM_OVER_LIMIT"
    return "PASS"


@contextmanager
def override_limit(limit_cents: int) -> Iterator[None]:
    """临时把单笔限额改成 limit_cents，with 结束（含异常退出）后恢复原值。"""
    global DAILY_MEAL_LIMIT_CENTS
    old = DAILY_MEAL_LIMIT_CENTS
    DAILY_MEAL_LIMIT_CENTS = limit_cents
    try:
        yield  # with 体在这里执行
    finally:
        DAILY_MEAL_LIMIT_CENTS = old  # 清理必达：正常与异常都恢复
