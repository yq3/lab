# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体）
"""try / except / else / finally 四个子句完整补全——用 trace 列表验证执行顺序。

考察点：else 的语义（只在「无异常」时执行——别把它和「try 尾部」混为一谈）；
finally 的语义（无论如何都执行，return / 异常都拦不住它收尾）。
语义约定（与 test_ex1.py 三方对齐）：
  - record_transfer 依次把执行到的子句名 append 进 trace，顺序即真相；
  - 正常路径：trace == ["try", "else", "finally"]，返回 "OK"；
  - 异常路径（amount_cents <= 0）：trace == ["try", "except", "finally"]，返回 "FAILED"；
  - 异常类型 InvalidAmountError（已给出，不要改）。
完成后：uv run pytest exercises/test_ex1.py 全绿。
"""


class InvalidAmountError(Exception):
    """金额非法（零或负数）。"""


def record_transfer(claim_id: str, amount_cents: int, trace: list[str]) -> str:
    """模拟记账：四个子句各 append 自己的名字；金额 <= 0 抛 InvalidAmountError 并在 except 收住。"""
    # TODO(ex1): try 里 append "try"，金额 <= 0 时 raise InvalidAmountError；
    # TODO(ex1): except 捕获它 append "except"；else（无异常才走）append "else"；finally append "finally"
    # TODO(ex1): 返回值：正常 "OK"、异常 "FAILED"（想想 return 分别放哪才不会提前跳出 finally 语义）
    raise NotImplementedError("TODO(ex1): 实现 try/except/else/finally 完整结构")
