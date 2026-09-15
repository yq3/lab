"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import pytest

from ex1_paginate import paginate


def test_ex1_uneven_last_page() -> None:
    assert list(paginate(list(range(10)), 3)) == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]


def test_ex1_exact_multiple_no_empty_tail() -> None:
    assert list(paginate([1, 2, 3, 4], 2)) == [[1, 2], [3, 4]]  # 整除：没有空尾页


def test_ex1_page_larger_than_input() -> None:
    assert list(paginate([1, 2], 5)) == [[1, 2]]


def test_ex1_empty_input_yields_nothing() -> None:
    assert list(paginate([], 3)) == []


def test_ex1_preserves_element_type() -> None:
    pages = list(paginate(["PASS", "REJECT:OVER_LIMIT", "PASS"], 2))
    assert pages == [["PASS", "REJECT:OVER_LIMIT"], ["PASS"]]


def test_ex1_invalid_size_raises() -> None:
    with pytest.raises(ValueError):
        list(paginate([1, 2, 3], 0))  # size 非法：消费时抛 ValueError
