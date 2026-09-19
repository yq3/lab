# 练习 2（单变量编辑约束：只改本文件 TODO 标注的区域；为完成 TODO 需要的 import 也算合法改动）
"""自定义异常分层 + raise from——pytest.raises 在这一题正式教给你。

考察点：领域异常基类带属性、子类化、raise NewError(...) from exc 的因果链。
验收口径（test_ex2.py 三方对齐，也是 pytest.raises 的标准姿势）：
  - parse_amount("12abc") 抛 AmountParseError，且 isinstance(exc, ExpenseError)；
  - 消息 match "金额字段不是整数"；
  - exc.context == "parse_amount"（出错环节随异常走）；
  - exc.__cause__ 是原始 ValueError（int() 抛的那个）——from 的功劳。
完成后：uv run pytest exercises/test_ex2.py 全绿。
"""


class ExpenseError(Exception):
    """报销领域异常基类：所有报销异常的父类，context 属性标记出错环节。"""

    context: str  # 属性声明（你的 __init__ 负责给它赋值）

    def __init__(self, message: str, *, context: str) -> None:
        # TODO(ex2): super().__init__(message)，再把 context 存成实例属性 self.context
        raise NotImplementedError("TODO(ex2): 补全 ExpenseError.__init__")


class AmountParseError(ExpenseError):
    """金额解析失败：坏数据进管线时的标准出口。"""


def parse_amount(raw: str) -> int:
    """把文本金额解析成整数分；失败时抛 AmountParseError（from 原始 ValueError）。

    消息格式：f"金额字段不是整数: {raw!r}"；context 传 "parse_amount"。
    """
    # TODO(ex2): try int(raw)；except ValueError as exc: raise AmountParseError(...) from exc
    raise NotImplementedError("TODO(ex2): 实现 parse_amount（记得 raise ... from exc）")
