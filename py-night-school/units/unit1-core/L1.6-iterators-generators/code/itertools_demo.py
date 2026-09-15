"""itertools 四件套 + 短路证明——对照 Java Stream 的 limit / takeWhile / concat / iterate。

运行本文件：
    uv run python code/itertools_demo.py
"""

from collections.abc import Iterator
from itertools import chain, count, islice, takewhile

MEAL_LIMIT_CENTS = 5000


def counting_source(items: list[int], pulled: list[int]) -> Iterator[int]:
    """带计数的源：每被拉取一次，就往 pulled 里记一笔——惰性的「测速仪」。"""
    for item in items:
        pulled.append(item)
        yield item


def first_n(source: Iterator[int], n: int) -> Iterator[int]:
    """islice：只取前 n 个。对照 Java Stream.limit(n)。"""
    return islice(source, n)


def amounts_under_limit(source: Iterator[int]) -> Iterator[int]:
    """takewhile：条件成立就一直取，遇到第一个不成立的立刻停。
    对照 Java Stream.takeWhile(predicate)。
    """
    return takewhile(lambda amount: amount <= MEAL_LIMIT_CENTS, source)


def concat(first: Iterator[int], second: Iterator[int]) -> Iterator[int]:
    """chain：把两段迭代器接成一段。对照 Java Stream.concat(s1, s2)。"""
    return chain(first, second)


def natural_numbers() -> Iterator[int]:
    """count：从 1 开始的无限自然数。对照 Java Stream.iterate(1, i -> i + 1)。

    无限流之所以能用，靠的是消费端短路（islice/takewhile）：没人拉，它就不算。
    """
    return count(start=1, step=1)


if __name__ == "__main__":
    # 短路证明一：islice(source, 3) 之后，底层只被拉了 3 次
    pulled: list[int] = []
    head = list(first_n(counting_source(list(range(100)), pulled), 3))
    print(f"islice 取 {len(head)} 个，底层实际被拉了 {len(pulled)} 次")  # 3 3——没多拉一次

    # 短路证明二：takewhile 遇到第一个超标单就停
    pulled2: list[int] = []
    kept = list(amounts_under_limit(counting_source([1200, 3500, 8800, 2400, 900], pulled2)))
    print(f"takewhile 保留 {kept}，底层被拉了 {len(pulled2)} 次")  # 3 次：8800 处即停

    # chain 与 count
    merged = list(concat(iter([1200, 3500]), iter([2400, 400])))
    print("chain 结果:", merged)  # [1200, 3500, 2400, 400]
    print("count+islice 前 5 个:", list(first_n(natural_numbers(), 5)))  # [1, 2, 3, 4, 5]
