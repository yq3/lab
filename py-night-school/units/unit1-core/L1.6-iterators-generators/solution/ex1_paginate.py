"""参考答案（ex1）——先完成练习再看；不追求与你的写法一致，追求通过验收且读得舒服。"""

from collections.abc import Iterator, Sequence


def paginate[T](items: Sequence[T], size: int) -> Iterator[list[T]]:
    """逐页 yield：每页最多 size 个元素。"""
    if size <= 0:
        raise ValueError(f"size 必须为正数: {size}")
    i = 0
    while i < len(items):
        yield list(items[i : i + size])  # 切片天然处理最后一页不满；list() 对齐声明类型
        i += size
