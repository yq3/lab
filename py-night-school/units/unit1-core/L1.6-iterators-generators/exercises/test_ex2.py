"""练习 2 验收（不要改本文件——它就是你的判卷老师）。

关键设计：用 counting_source 的 pulled 计数器证明短路——只消费前 N 项时，
底层源恰好只被拉了必要的行数，而不是全部。
"""

from ex2_pipeline import LINES, counting_source, over_limit_meals, parse_lines, total_over_limit


def test_ex2_parse_lines() -> None:
    records = list(parse_lines(iter(LINES)))
    assert records[0] == ("CLM-0001", "meal", 1200)
    assert records[2] == ("CLM-0003", "transport", 400)


def test_ex2_filter_keeps_only_oversized_meals() -> None:
    records = list(over_limit_meals(parse_lines(iter(LINES))))
    assert records == [("CLM-0002", "meal", 8800), ("CLM-0004", "meal", 5200)]


def test_ex2_total_over_limit() -> None:
    assert total_over_limit(iter(LINES)) == 14000  # 8800 + 5200


def test_ex2_lazy_short_circuit() -> None:
    # 只消费前 2 条超标记录：第 1 条在第 2 行、第 2 条在第 4 行——底层恰好被拉 4 次
    pulled: list[str] = []
    pipeline = over_limit_meals(parse_lines(counting_source(LINES, pulled)))

    assert next(pipeline) == ("CLM-0002", "meal", 8800)
    assert len(pulled) == 2  # 第一条超标在第 2 行：拉了 2 行就拿到了
    assert next(pipeline) == ("CLM-0004", "meal", 5200)
    assert len(pulled) == 4  # 两条超标到手，底层只拉了 4 行
    assert len(LINES) == 5  # 全量明明有 5 行——短路就是少干活


def test_ex2_full_consumption_pulls_everything() -> None:
    pulled: list[str] = []
    assert total_over_limit(counting_source(LINES, pulled)) == 14000
    assert len(pulled) == 5  # sum 消费到底：这次 5 行全被拉了
