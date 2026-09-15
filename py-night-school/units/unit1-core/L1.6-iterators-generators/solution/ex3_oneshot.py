"""参考答案（ex3）——物化修复：要复用就 list()，一次性是生成器的天性不是 bug。"""

from collections.abc import Iterator

LINES = [
    "CLM-1001,meal,1200",
    "CLM-1002,meal,3500",
    "CLM-1003,transport,480",
    "CLM-1004,hotel,18600",
    "CLM-1005,meal,2400",
]


def read_amounts(lines: list[str]) -> Iterator[int]:
    """文本行 -> 金额（生成器表达式，已写好，不要改）。"""
    return (int(line.rsplit(",", 1)[1]) for line in lines)


# 修复：物化成 list——两个 total_pass_* 现在各自完整消费一份数据
AMOUNTS: list[int] = list(read_amounts(LINES))


def total_pass_1() -> int:
    return sum(AMOUNTS)


def total_pass_2() -> int:
    return sum(AMOUNTS)
