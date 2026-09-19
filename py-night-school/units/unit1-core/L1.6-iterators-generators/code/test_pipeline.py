"""讲义示例测试：报销流水惰性管线（对照手工算出的期望值）。"""

from collections.abc import Iterator

from pipeline import FLOW_FILE, amounts, oversized_meals, parse_records, read_lines, total_oversized_meals


def test_flow_file_shape() -> None:
    lines = list(read_lines(FLOW_FILE))
    assert len(lines) == 300
    date, claim_id, category, amount = lines[0].split(",")
    assert date == "2026-09-01"
    assert claim_id == "CLM-2026-0001"
    assert (category, amount) == ("meal", "1213")


def test_oversized_meals_count_and_total() -> None:
    over = list(oversized_meals(parse_records(read_lines(FLOW_FILE))))
    assert len(over) == 30  # 数据规则：每 10 行的第 3 行是超标餐
    assert over[0] == ("CLM-2026-0003", "meal", 6000)  # 第一笔超标在第 3 行
    assert sum(amounts(iter(over))) == 236550  # 手工算出的期望合计（分）


def test_pipeline_total() -> None:
    assert total_oversized_meals() == 236550


def test_pipeline_is_lazy() -> None:
    # 短路证明：只取第一笔超标，底层只应被拉 3 行（超标单在第 3 行）
    pulled: list[str] = []

    def counting_lines() -> Iterator[str]:
        for line in read_lines(FLOW_FILE):
            pulled.append(line)
            yield line

    first_over = next(oversized_meals(parse_records(counting_lines())))
    assert first_over == ("CLM-2026-0003", "meal", 6000)
    assert len(pulled) == 3  # 300 行的文件，只读了 3 行——惰性的价值
