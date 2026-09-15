"""报销流水惰性管线：读「大文件」-> 过滤超标餐 -> 取金额 -> 汇总，全程内存恒定。

数据文件 expense_flow.txt（300 行）由确定性规则生成：
    日期,单号,类别,金额分     如 2026-09-01,CLM-2026-0003,meal,6000
规则要点：每 10 行的第 3 行是一笔超标工作餐（> 5000 分）；住宿单价高不受单餐限制。

运行本文件（含 lazy vs eager 的内存对比，放大 200 倍看得更清楚）：
    uv run python code/pipeline.py
"""

import tracemalloc
from collections.abc import Iterator
from itertools import chain
from pathlib import Path

FLOW_FILE = Path(__file__).parent / "expense_flow.txt"
MEAL_LIMIT_CENTS = 5000

Record = tuple[str, str, int]  # (单号, 类别, 金额分)


def read_lines(path: Path) -> Iterator[str]:
    """第 1 段：惰性读文件——每次 next 才读一行，不把整个文件装进内存。"""
    with path.open(encoding="utf-8") as f:
        for line in f:
            yield line.rstrip("\n")


def parse_records(lines: Iterator[str]) -> Iterator[Record]:
    """第 2 段：文本行 -> 结构化记录（日期被丢弃，后面用不到）。"""
    for line in lines:
        _, claim_id, category, amount = line.split(",")
        yield claim_id, category, int(amount)


def oversized_meals(records: Iterator[Record], limit_cents: int = MEAL_LIMIT_CENTS) -> Iterator[Record]:
    """第 3 段：只保留超标的「工作餐」（类别 meal 且金额 > 上限）。"""
    for record in records:
        _, category, amount = record
        if category == "meal" and amount > limit_cents:
            yield record


def amounts(records: Iterator[Record]) -> Iterator[int]:
    """第 4 段：记录 -> 金额。"""
    for record in records:
        yield record[2]


def total_oversized_meals(path: Path = FLOW_FILE) -> int:
    """组合四段管线：像接水管一样把迭代器串起来，sum 驱动整条管线流动。"""
    return sum(
        amounts(
            oversized_meals(
                parse_records(
                    read_lines(path),
                ),
            ),
        ),
    )


if __name__ == "__main__":
    count = sum(1 for _ in oversized_meals(parse_records(read_lines(FLOW_FILE))))
    print(f"超标餐笔数: {count}，合计: {total_oversized_meals()} 分")

    # 内存对比（各用一次干净的 tracemalloc 会话，先测 lazy——eager 的 list 会留在内存里抬高后续基线）
    PASSES = 200  # 把同一份流水放大 200 倍（60000 行），量级差异才看得见

    tracemalloc.start()
    seen = sum(1 for _ in chain.from_iterable(read_lines(FLOW_FILE) for _ in range(PASSES)))
    _, peak_lazy = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    tracemalloc.start()
    base_lines = FLOW_FILE.read_text(encoding="utf-8").splitlines()
    eager_all = base_lines * PASSES  # eager：60000 行全部同时驻留内存
    _, peak_eager = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert seen == len(eager_all) == PASSES * 300
    print(f"处理 {seen} 行（300 行流水 x {PASSES} 遍）:")
    print(f"  lazy  峰值内存: {peak_lazy / 1024:.0f} KiB（任意时刻只握着 1 行——行数翻倍它也几乎不变）")
    print(f"  eager 峰值内存: {peak_eager / 1024 / 1024:.1f} MiB（60000 行全在内存——近似线性上涨）")
