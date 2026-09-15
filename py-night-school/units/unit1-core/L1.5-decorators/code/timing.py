"""timing 装饰器——增强型装饰器的最小完整样本（含 functools.wraps）。

运行本文件看两条路线的等价演示：
    uv run python code/timing.py
"""

from collections.abc import Callable
from functools import wraps
from time import perf_counter, sleep
from typing import ParamSpec, TypeVar

P = ParamSpec("P")  # 参数部分的形状（见讲义 §2.7）
R = TypeVar("R")  # 返回值部分的形状


def timing(func: Callable[P, R]) -> Callable[P, R]:
    """包装 func：调用前后计时，把耗时打到日志，返回值原样透传。"""

    @wraps(func)  # 把 func 的 __name__/__doc__ 等元数据复制到 wrapper 上
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = perf_counter()
        result = func(*args, **kwargs)  # 真正的调用发生在这里
        elapsed = perf_counter() - start
        print(f"[timing] {func.__name__} 耗时 {elapsed:.4f}s")
        return result

    return wrapper  # 返回的是「新函数」，不是调用结果


def preapprove(items_cents: list[int]) -> str:
    """报销单预审（明线老朋友）：单笔 > 5000 分拒绝。"""
    if any(c > 5000 for c in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    return "PASS"


if __name__ == "__main__":
    # 路线一：不用 @ 语法糖——装饰器就是「收函数、返回函数」的普通函数
    audited = timing(preapprove)
    print(audited([1200, 3500]))  # 打印耗时日志，然后 "PASS"
    print(audited.__name__)  # preapprove（wraps 的功劳；注释掉 @wraps 再跑，这里会变成 wrapper）

    # 路线二：@ 语法糖——完全等价于「slow_check = timing(原函数)」
    @timing
    def slow_check(items_cents: list[int]) -> str:
        sleep(0.05)  # 模拟一次慢调用
        return preapprove(items_cents)

    print(slow_check([8800]))  # 打印约 0.05s 的耗时日志，然后 "REJECT:ITEM_OVER_LIMIT"
