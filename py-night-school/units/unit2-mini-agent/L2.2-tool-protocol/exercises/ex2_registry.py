# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体与所需的顶部 import，其余不要动）
"""@tool 带参装饰器：函数一登记进注册表。

考察点：L1.5 带参装饰器的三层结构在真实场景的落地；
从函数对象提取元数据（__name__ / __doc__）——「文档即数据」；
functools.wraps 保住原函数身份。

完成判据：uv run pytest exercises/test_ex2.py 全绿——
  注册生效、描述取 docstring 第一行、wrapper 可调用且身份保留、注册表键来自 __name__。
提示：docstring 可能为 None 或前后有空白——先 strip 再取第一行。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolSpec:
    """一个工具的全部元数据（讲义 code/tools.py 的同款）。"""

    name: str
    description: str
    args_model: type[BaseModel]
    func: Callable[..., str | int]


REGISTRY: dict[str, ToolSpec] = {}


def tool(
    args_model: type[BaseModel],
) -> Callable[[Callable[..., str | int]], Callable[..., str | int]]:
    """@tool(SomeArgs) 装饰器：把函数登记进 REGISTRY，返回包装后的函数。"""
    # TODO(ex2): 三层结构——外层收 args_model；内层造 ToolSpec（名字=函数名，描述=docstring 首行）
    # TODO(ex2): 存入 REGISTRY；functools.wraps 后返回 wrapper
    raise NotImplementedError("TODO(ex2): 补全 tool 装饰器")
