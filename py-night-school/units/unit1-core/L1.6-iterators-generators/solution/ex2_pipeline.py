"""参考答案（ex2）——三段都是生成器函数，组合时不做任何物化，惰性才能保留到底。"""

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
    for line in lines:
        claim_id, category, amount = line.split(",")
        yield claim_id, category, int(amount)


def over_limit_meals(records: Iterator[Record], limit_cents: int = 5000) -> Iterator[Record]:
    """第 2 段：只保留超标的「工作餐」（类别 meal 且金额 > limit_cents）。"""
    for record in records:
        _, category, amount = record
        if category == "meal" and amount > limit_cents:
            yield record


def total_over_limit(lines: Iterator[str]) -> int:
    """第 3 段：组合两段并求和（sum 会驱动整条管线流动）。"""
    return sum(record[2] for record in over_limit_meals(parse_lines(lines)))
