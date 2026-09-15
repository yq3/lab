"""讲义示例测试：异常链（cause / 裸 raise / from None）。"""

import pytest

from chains import DomainError, parse_amount, parse_and_report


def test_normal_path() -> None:
    assert parse_amount("1200") == 1200


def test_raise_from_sets_cause() -> None:
    with pytest.raises(DomainError, match="金额字段不是整数") as exc_info:
        parse_amount("12abc")
    cause = exc_info.value.__cause__
    assert isinstance(cause, ValueError)  # from exc 记下的直接原因
    assert "12abc" in str(cause)


def test_bare_raise_preserves_object_and_traceback() -> None:
    caught: list[DomainError] = []
    try:
        parse_and_report("xyz")  # 内部裸 raise 原样上抛
    except DomainError as exc:
        caught.append(exc)
        assert exc.__traceback__ is not None  # 原始 traceback 没丢
        assert isinstance(exc.__cause__, ValueError)  # 包装时设的 cause 链还在
    assert len(caught) == 1  # 只炸一次：except 收住了
