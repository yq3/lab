"""带参 retry 装饰器——三层函数：外收参数、中收函数、内做包装。

`@retry(max_attempts=3, retry_on=(ConnectionError,))` 的执行顺序：
    1. 先调用 retry(max_attempts=3, ...) 得到 decorator（最外层生效）
    2. 再用 decorator 包装函数（@ 语法糖自动完成）
对照 Java：这是「带属性的动态代理工厂」的函数版。

运行本文件（mock 一个三次里挂两次的不稳定函数）：
    uv run python code/retry.py
"""

from collections.abc import Callable
from functools import wraps
from time import perf_counter, sleep
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def retry(
    max_attempts: int = 3,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    delay_seconds: float = 0.0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """带参装饰器工厂：返回一个「无参装饰器」，重试到 max_attempts 次耗尽为止。"""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)  # wraps 永远贴在「最内层真正包函数」的那层
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            attempt = 0
            while True:
                attempt += 1
                try:
                    return func(*args, **kwargs)
                except retry_on as exc:  # 只重试名单内的异常
                    print(f"[retry] {func.__name__} 第 {attempt}/{max_attempts} 次失败: {exc}")
                    if attempt >= max_attempts:
                        raise  # 次数耗尽：裸 raise 抛最后一次异常（保现场，L1.7 详讲）
                    if delay_seconds:
                        sleep(delay_seconds)

        return wrapper

    return decorator


# ---- mock：一个「三次里挂两次」的不稳定函数，用模块级计数器控制 ----
_calls = 0


@retry(max_attempts=3, retry_on=(ConnectionError,))
def fetch_exchange_rate() -> int:
    """mock 拉汇率：第 1、2 次抛 ConnectionError，第 3 次成功返回 719。"""
    global _calls
    _calls += 1
    if _calls < 3:
        raise ConnectionError(f"上游抖动（第 {_calls} 次）")
    return 719


if __name__ == "__main__":
    start = perf_counter()
    rate = fetch_exchange_rate()  # 三次中两次失败，最终仍成功
    print(f"拿到汇率 {rate}，共尝试 {_calls} 次，耗时 {perf_counter() - start:.3f}s")
