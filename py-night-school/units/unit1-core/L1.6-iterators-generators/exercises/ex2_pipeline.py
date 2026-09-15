# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体）
"""三段管线组合 + 短路证明——惰性的价值要靠「计数器」才能看见。

考察点：生成器函数串联（parse -> filter -> sum）；理解「只有被拉取才工作」。
下面 counting_source 是给测试用的「测速仪」：底层每被拉一行就记一笔（已写好，不要改）。
语义约定（与 test_ex2.py 三方对齐）：
  - 行格式 "单号,类别,金额分"，如 "CLM-0002,meal,8800"；日期不在本练习的数据里；
  - over_limit_meals 保留「类别为 meal 且金额 > limit_cents」的记录；
  - total_over_limit 组合三段，返回超标总额（整数分）。
完成后：uv run pytest exercises/test_ex2.py 全绿。
"""

from collections.abc import Iterator

Record = tuple[str, str, int]  # (单号, 类别, 金额分)

LINES = [
    "CLM-0001,meal,1200",
    "CLM-0002,meal,8800",
    "CLM-0003,transport,400",
    "CLM-0004,meal,5200",
    "CLM-0005,hotel,18000",
]


def counting_source(lines: list[str], pulled: list[str]) -> Iterator[str]:
    """测速仪：每被拉取一行就 append 进 pulled（已写好，不要改）。"""
    for line in lines:
        pulled.append(line)
        yield line


def parse_lines(lines: Iterator[str]) -> Iterator[Record]:
    """第 1 段：文本行 -> (单号, 类别, 金额) 记录。"""
    # TODO(ex2): split(",") 拆字段，int() 转金额，yield 记录
    raise NotImplementedError("TODO(ex2): 实现 parse_lines")


def over_limit_meals(records: Iterator[Record], limit_cents: int = 5000) -> Iterator[Record]:
    """第 2 段：只保留超标的「工作餐」（类别 meal 且金额 > limit_cents）。"""
    # TODO(ex2): 条件命中才 yield——注意：不命中的记录也要「拉过」，但别吐出去
    raise NotImplementedError("TODO(ex2): 实现 over_limit_meals")


def total_over_limit(lines: Iterator[str]) -> int:
    """第 3 段：组合两段并求和（sum 会驱动整条管线流动）。"""
    # TODO(ex2): 组合 parse_lines 与 over_limit_meals，对金额求和
    raise NotImplementedError("TODO(ex2): 实现 total_over_limit")
