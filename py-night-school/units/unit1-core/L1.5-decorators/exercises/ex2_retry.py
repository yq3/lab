# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体；为完成 TODO 需要的 import 也算合法改动）
"""带参 retry 装饰器——三层函数：外收参数、中收函数、内做包装。

考察点：三层嵌套的正确连通（参数跨层捕获 = 闭包）、重试次数语义、异常名单、裸 raise。
你会用到 functools.wraps（import 自己加）。
语义约定（与 test_ex2.py 三方对齐）：
  - max_attempts 是「总尝试次数上限」：max_attempts=3 表示最多调 3 次；
  - 只重试 retry_on 名单内的异常类型；名单外异常一次都不重试、立刻上抛；
  - 次数耗尽：抛「最后一次」的异常（裸 raise 即可）；
  - 成功后立刻返回，绝不重试。
完成后：uv run pytest exercises/test_ex2.py 全绿。
"""

from collections.abc import Callable
from typing import TypeVar

R = TypeVar("R")


def retry(
    max_attempts: int = 3,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[[], R]], Callable[[], R]]:
    """带参装饰器：函数抛出名单内异常时重试，直到成功或次数耗尽。"""
    # TODO(ex2): 外层收参数 -> 返回 decorator；decorator 收函数 -> 返回 wrapper；
    # TODO(ex2): wrapper 里循环尝试、except retry_on、耗尽时裸 raise、记得 @wraps(func)
    raise NotImplementedError("TODO(ex2): 实现带参 retry 装饰器（三层函数）")
