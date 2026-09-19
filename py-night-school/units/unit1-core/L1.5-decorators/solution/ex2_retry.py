"""参考答案（ex2）——三层函数逐层读：retry 收参数、decorator 收函数、wrapper 做包装。"""

from collections.abc import Callable
from functools import wraps
from typing import TypeVar

R = TypeVar("R")


def retry(
    max_attempts: int = 3,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[[], R]], Callable[[], R]]:
    """带参装饰器：函数抛出名单内异常时重试，直到成功或次数耗尽。"""

    def decorator(func: Callable[[], R]) -> Callable[[], R]:
        @wraps(func)
        def wrapper() -> R:
            for attempt in range(1, max_attempts + 1):
                try:
                    return func()  # 成功：立刻返回，绝不重试
                except retry_on:
                    if attempt == max_attempts:
                        raise  # 耗尽：裸 raise 抛最后一次异常，保住原始 traceback
            raise AssertionError("unreachable")  # 仅让类型检查器安心

        return wrapper

    return decorator
