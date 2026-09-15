"""参考答案（ex1）——先完成练习再看；不追求与你的写法一致，追求通过验收且读得舒服。"""

from collections.abc import Callable
from functools import wraps
from time import perf_counter
from typing import TypeVar

R = TypeVar("R")

TIMINGS: list[float] = []


def timing(func: Callable[[], R]) -> Callable[[], R]:
    """包装 func：把每次调用的耗时记进 TIMINGS，返回值透传，元数据用 wraps 保住。"""

    @wraps(func)
    def wrapper() -> R:
        start = perf_counter()
        result = func()
        TIMINGS.append(perf_counter() - start)
        return result

    return wrapper
