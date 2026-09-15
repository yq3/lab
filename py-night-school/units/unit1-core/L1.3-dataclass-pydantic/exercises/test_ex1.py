"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from dataclasses import is_dataclass

from ex1_dataclass import ExpenseLine, ExpenseLineData


def test_ex1_fields_constructible() -> None:
    line = ExpenseLineData("餐饮", 3500)
    assert line.description == "餐饮"
    assert line.amount_cents == 3500
    assert line.tags == []
    kw = ExpenseLineData(description="交通", amount_cents=1200, tags=["打车"])
    assert kw.tags == ["打车"]


def test_ex1_default_tags_not_shared() -> None:
    a = ExpenseLineData("餐饮", 3500)
    b = ExpenseLineData("餐饮", 3500)
    assert a.tags is not b.tags  # 各拿各的空列表：可变默认值的纪律判据
    a.tags.append("加班餐")
    assert b.tags == []


def test_ex1_equality() -> None:
    assert ExpenseLineData("餐饮", 3500, ["加班餐"]) == ExpenseLineData("餐饮", 3500, ["加班餐"])
    assert ExpenseLineData("餐饮", 3500) != ExpenseLineData("餐饮", 3600)
    # 与其他类型比较判不等（dataclass 生成的 __eq__ 先比类再比字段）
    assert ExpenseLineData("餐饮", 3500, []) != ExpenseLine("餐饮", 3500, [])


def test_ex1_repr() -> None:
    line = ExpenseLineData("餐饮", 3500, ["加班餐"])
    assert repr(line) == "ExpenseLineData(description='餐饮', amount_cents=3500, tags=['加班餐'])"


def test_ex1_really_is_a_dataclass() -> None:
    # 防作弊：不许把上面的手写类换个名字糊弄——验收的是 @dataclass 改写
    assert is_dataclass(ExpenseLineData)
    assert not is_dataclass(ExpenseLine)
