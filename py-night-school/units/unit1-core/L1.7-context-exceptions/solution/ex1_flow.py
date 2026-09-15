"""参考答案（ex1）——四个子句各就各位；返回值放在各自的自然路径上。"""


class InvalidAmountError(Exception):
    """金额非法（零或负数）。"""


def record_transfer(claim_id: str, amount_cents: int, trace: list[str]) -> str:
    """模拟记账：四个子句各 append 自己的名字；金额 <= 0 抛 InvalidAmountError 并在 except 收住。"""
    try:
        trace.append("try")
        if amount_cents <= 0:
            raise InvalidAmountError(f"{claim_id} 金额非法: {amount_cents}")
    except InvalidAmountError:
        trace.append("except")
        return "FAILED"  # return 也不会跳过 finally
    else:
        trace.append("else")  # 只在「无异常」时走
        return "OK"
    finally:
        trace.append("finally")  # 无论如何都收尾
