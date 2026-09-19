"""一次性消费实验——生成器的「静默排空」现场（§5 陷阱的先行演示）。

运行本文件：
    uv run python code/oneshot.py
"""

from collections.abc import Iterator

CLAIMS = [1200, 3500, 2400]  # 三笔金额（整数分）


def read_amounts() -> Iterator[int]:
    """生成器函数：每次 next 吐一笔（yield from：逐个转发 CLAIMS 的每个元素）。"""
    yield from CLAIMS


if __name__ == "__main__":
    # 现场：第一次消费有数据，第二次静默空——没有任何异常！
    gen = read_amounts()
    first_pass = list(gen)
    second_pass = list(gen)  # 生成器已耗尽：不报错，只是空
    print(f"第一次: {first_pass}")  # [1200, 3500, 2400]
    print(f"第二次: {second_pass}")  # []  <- 静默空，这就是生成器的一次性

    # 修复一：物化成 list（要复用就 list()）
    materialized = list(read_amounts())
    print("物化后两遍:", sum(materialized), sum(materialized))  # 7100 7100

    # 修复二：每次重建生成器（每次要新鲜的就重新造）
    print("重建后两遍:", sum(read_amounts()), sum(read_amounts()))  # 7100 7100
