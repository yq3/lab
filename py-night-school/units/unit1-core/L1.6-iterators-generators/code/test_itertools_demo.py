"""讲义示例测试：itertools 四件套与短路。"""

from itertools import count

from itertools_demo import amounts_under_limit, concat, counting_source, first_n, natural_numbers


def test_islice_short_circuits() -> None:
    pulled: list[int] = []
    head = list(first_n(counting_source(list(range(100)), pulled), 3))
    assert head == [0, 1, 2]
    assert len(pulled) == 3  # 没多拉一次


def test_takewhile_stops_at_first_failure() -> None:
    pulled: list[int] = []
    kept = list(amounts_under_limit(counting_source([1200, 3500, 8800, 2400, 900], pulled)))
    assert kept == [1200, 3500]
    assert len(pulled) == 3  # 8800 判负即停，后面的 2400 根本没被拉


def test_chain_concatenates() -> None:
    assert list(concat(iter([1200, 3500]), iter([2400, 400]))) == [1200, 3500, 2400, 400]


def test_count_is_infinite_but_sliceeable() -> None:
    assert list(first_n(natural_numbers(), 5)) == [1, 2, 3, 4, 5]
    assert next(count(start=7)) == 7
