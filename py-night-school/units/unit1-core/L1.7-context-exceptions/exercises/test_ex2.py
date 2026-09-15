"""练习 2 验收（不要改本文件——它就是你的判卷老师）。

pytest.raises 正式用法：作上下文管理器包住「会炸的调用」，
as exc_info 拿到异常对象；match= 按正则检查消息。
"""

import pytest

from ex2_custom_error import AmountParseError, ExpenseError, parse_amount


def test_ex2_success_path() -> None:
    assert parse_amount("1200") == 1200


def test_ex2_type_message_cause() -> None:
    # 三重断言：类型（含分层）+ 消息 + 因果链
    with pytest.raises(AmountParseError, match="金额字段不是整数") as exc_info:
        parse_amount("12abc")

    exc = exc_info.value
    assert isinstance(exc, ExpenseError)  # 子类关系：调用方一个 except 接住全家
    assert exc.context == "parse_amount"  # 出错环节随异常走
    assert "12abc" in str(exc)  # 消息里带着肇事数据

    cause = exc.__cause__
    assert isinstance(cause, ValueError)  # from 的功劳：原始异常在链上
    assert "12abc" in str(cause)


def test_ex2_cause_is_not_implicit_context() -> None:
    # raise X from e 设的是 __cause__（显式），不是 __context__（隐式）——两个通道要分清
    with pytest.raises(AmountParseError) as exc_info:
        parse_amount("abc")
    assert exc_info.value.__cause__ is not None
