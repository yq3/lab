# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体）
"""@contextmanager 实现临时限额覆盖——yield 前后就是 __enter__/__exit__。

考察点：生成器写上下文管理器的「保存 -> 修改 -> yield -> 恢复」四步；finally 保证异常也恢复。
语义约定（与 test_ex3.py 三方对齐）：
  - with override_limit(8000): 期间，check_item(6000) == "PASS"（限额被临时抬高）；
  - with 结束后限额恢复 5000，check_item(6000) 回到 "REJECT:ITEM_OVER_LIMIT"；
  - with 体内抛异常：异常正常向外传播，且限额照样恢复（finally 的功劳）。
完成后：uv run pytest exercises/test_ex3.py 全绿。
"""

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
    # TODO(ex3): 声明 global DAILY_MEAL_LIMIT_CENTS；保存旧值；改成新值；yield；finally 里恢复
    raise NotImplementedError("TODO(ex3): 实现 override_limit（保存->修改->yield->finally 恢复）")
