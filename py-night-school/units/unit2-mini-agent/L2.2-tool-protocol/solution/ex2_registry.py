# 参考答案：ex2_registry（练习文件的完整解法——完成前别看）
"""@tool 带参装饰器：函数一登记进注册表。"""

from __future__ import annotations

import functools
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
    registry: dict[str, ToolSpec] = REGISTRY

    def decorator(func: Callable[..., str | int]) -> Callable[..., str | int]:
        doc = (func.__doc__ or "").strip()
        registry[func.__name__] = ToolSpec(
            name=func.__name__,
            description=doc.splitlines()[0] if doc else "",
            args_model=args_model,
            func=func,
        )

        @functools.wraps(func)
        def wrapper(*args: object, **kwargs: object) -> str | int:
            return func(*args, **kwargs)

        return wrapper

    return decorator
