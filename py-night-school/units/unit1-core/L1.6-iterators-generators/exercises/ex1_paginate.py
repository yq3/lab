# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体）
"""分页生成器 paginate——最基础的生成器函数：逐页 yield。

考察点：生成器函数的「边产边消费」；切页的边界（最后一页不满、整除、空输入、size 非法）。
语义约定（与 test_ex1.py 三方对齐）：
  - 每页是一个 list，最多 size 个元素，按原顺序；
  - 最后一页可以不满；整除时没有空尾页；空输入产出零页；
  - size <= 0 时抛 ValueError（消费时抛出即可，生成器函数体内检查就行）。
完成后：uv run pytest exercises/test_ex1.py 全绿。
"""

from collections.abc import Iterator, Sequence


def paginate[T](items: Sequence[T], size: int) -> Iterator[list[T]]:
    """逐页 yield：每页最多 size 个元素。"""
    # TODO(ex1): 用 while/for 推进下标，每次 yield items[i:i+size]
    raise NotImplementedError("TODO(ex1): 实现分页生成器")
