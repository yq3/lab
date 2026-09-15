# 练习 3（单变量编辑约束：只改 TODO 标注的区域；其余代码不要动）
"""修复一次性消费 bug——第一次有值、第二次静默 0 的现场在你手里。

考察点：识别「模块级生成器被复用」的坏味道；物化 / 重建两种修复。
验收（test_ex3.py 三方对齐）：
  - total_pass_1() 与 total_pass_2() 返回同一个、正确的总额（当前必有一个是 0）；
  - 只允许改 TODO 标注区（物化成 list 是最直接的修法；「每次重建生成器」的修法
    需要改函数，本题为守住单变量约束只收物化版——重建版见讲义 code/oneshot.py）。
完成后：uv run pytest exercises/test_ex3.py 全绿。
"""

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


# TODO(ex3): 坏代码就在下一行——AMOUNTS 是一次性生成器，total_pass_1 消费完它，
# TODO(ex3): total_pass_2 只能得到静默的 0。把它改成可重复消费的形态（提示：list(...) 物化）。
AMOUNTS: Iterator[int] = read_amounts(LINES)


def total_pass_1() -> int:
    return sum(AMOUNTS)


def total_pass_2() -> int:
    return sum(AMOUNTS)
