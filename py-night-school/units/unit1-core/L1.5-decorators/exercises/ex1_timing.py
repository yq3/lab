# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体；为完成 TODO 需要的 import 也算合法改动）
"""补全 timing 装饰器——最经典的「两层函数」无参装饰器。

考察点：wrapper 里「调真函数 -> 记录 -> 透传返回值」三步，以及 functools.wraps 的位置。
你会用到 functools.wraps 与 time.perf_counter（import 自己加）。
验收（test_ex1.py 机器判定，三方对齐）：
  1. 被装饰函数的返回值原样透传；
  2. 每次调用把耗时（秒，float）append 进模块级 TIMINGS，一次调用一条；
  3. __name__ / __doc__ 元数据保留（wraps 的功劳）。
完成后：uv run pytest exercises/test_ex1.py 全绿。
"""

from collections.abc import Callable
from typing import TypeVar

R = TypeVar("R")

# 每次被装饰函数调用结束，把耗时（perf_counter 差值，单位秒）append 进来
TIMINGS: list[float] = []


def timing(func: Callable[[], R]) -> Callable[[], R]:
    """包装 func：把每次调用的耗时记进 TIMINGS，返回值透传，元数据用 wraps 保住。"""
    # TODO(ex1): 在这里写 wrapper 函数并返回它；结构参考讲义 §3 Step 1
    raise NotImplementedError("TODO(ex1): 实现 timing 装饰器（记得 @wraps(func)）")
