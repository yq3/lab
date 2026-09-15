"""讲义测试：泛型函数——同一实现服务多种类型，空入参抛错。"""

import pytest

from generics import first, pluck


def test_first_int() -> None:
    assert first([3, 1, 2]) == 3


def test_first_str() -> None:
    assert first(["REJECT", "PASS"]) == "REJECT"


def test_first_empty_raises() -> None:
    with pytest.raises(ValueError, match="空列表"):
        first([])


def test_pluck_int_values() -> None:
    rows: list[dict[str, int]] = [
        {"amount": 1200, "fee": 30},
        {"amount": 3500, "fee": 45},
    ]
    assert pluck(rows, "amount") == [1200, 3500]


def test_pluck_str_values() -> None:
    rows: list[dict[str, str]] = [{"id": "CLM-2026-0001"}, {"id": "CLM-2026-0002"}]
    assert pluck(rows, "id") == ["CLM-2026-0001", "CLM-2026-0002"]
