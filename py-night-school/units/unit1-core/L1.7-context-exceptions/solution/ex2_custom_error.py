"""参考答案（ex2）——基类带 context 属性；raise ... from exc 保住因果链。"""


class ExpenseError(Exception):
    """报销领域异常基类：所有报销异常的父类，context 属性标记出错环节。"""

    context: str  # 属性声明（__init__ 负责赋值）

    def __init__(self, message: str, *, context: str) -> None:
        super().__init__(message)  # 消息走原生通道，str(e) 直接可用
        self.context = context  # 出错环节随异常走


class AmountParseError(ExpenseError):
    """金额解析失败：坏数据进管线时的标准出口。"""


def parse_amount(raw: str) -> int:
    """把文本金额解析成整数分；失败时抛 AmountParseError（from 原始 ValueError）。"""
    try:
        return int(raw)
    except ValueError as exc:
        raise AmountParseError(f"金额字段不是整数: {raw!r}", context="parse_amount") from exc
