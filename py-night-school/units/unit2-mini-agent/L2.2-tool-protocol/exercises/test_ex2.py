"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from pydantic import BaseModel

import ex2_registry as ex2


class AddArgs(BaseModel):
    a: int
    b: int


def test_tool_registers_and_wraps() -> None:
    @ex2.tool(AddArgs)
    def add_cents(a: int, b: int) -> int:
        """把两笔金额相加。"""
        return a + b

    assert "add_cents" in ex2.REGISTRY
    spec = ex2.REGISTRY["add_cents"]
    assert spec.description == "把两笔金额相加。"  # docstring 第一行
    assert spec.args_model is AddArgs
    assert spec.func(2, 3) == 5
    assert add_cents(2, 3) == 5  # wrapper 仍可直接调用
    assert add_cents.__name__ == "add_cents"  # functools.wraps 保住身份


def test_tool_without_docstring_gets_empty_description() -> None:
    @ex2.tool(AddArgs)
    def no_doc(a: int, b: int) -> int:
        return a - b

    assert ex2.REGISTRY["no_doc"].description == ""


def test_registry_keyed_by_dunder_name() -> None:
    @ex2.tool(AddArgs)
    def scale_cents(a: int, b: int) -> int:
        """按倍数放大金额。"""
        return a * b

    spec = ex2.REGISTRY["scale_cents"]
    assert spec.func(3, 2) == 6  # 注册表里存的是原函数，测试里可直调验证
