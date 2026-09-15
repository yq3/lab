"""报销领域异常分层——基类带属性，子类带细节，坏数据链上原始异常。

这棵小树是毕业设计 fail-closed 执行门里 REJECT 语义的基础：
「可分类的失败」用异常类型表达，「失败的证据」用异常属性携带。
"""

DAILY_MEAL_LIMIT_CENTS = 5000


class ExpenseError(Exception):
    """报销领域异常基类：所有报销异常的父类，claim_id 随行。"""

    def __init__(self, claim_id: str, message: str) -> None:
        super().__init__(message)  # 消息走 Exception 原生通道（str(e) 就是它）
        self.claim_id = claim_id  # 领域属性：哪张单出的事


class InvalidAmountError(ExpenseError):
    """脏数据：金额非正数。"""


class LimitExceededError(ExpenseError):
    """业务越界：单笔超限。limit_cents 记录「超的是哪条线」。"""

    def __init__(self, claim_id: str, message: str, limit_cents: int) -> None:
        super().__init__(claim_id, message)
        self.limit_cents = limit_cents


def audit_amount(claim_id: str, amount_cents: int) -> str:
    """单笔审计：返回 "PASS"，或抛出带证据的领域异常。"""
    if amount_cents <= 0:
        raise InvalidAmountError(claim_id, f"金额必须为正数: {amount_cents}")
    if amount_cents > DAILY_MEAL_LIMIT_CENTS:
        raise LimitExceededError(claim_id, f"单笔 {amount_cents} 分超过限额", DAILY_MEAL_LIMIT_CENTS)
    return "PASS"


def parse_and_audit(line: str) -> str:
    """'CLM-0001,1200' -> audit 结果；解析失败包成领域异常并链上原始异常。

    调用方只需 except ExpenseError 就能接住本函数的一切失败——分层的意义。
    """
    try:
        claim_id, raw_amount = line.split(",")
        amount = int(raw_amount)
    except ValueError as exc:
        raise InvalidAmountError("UNKNOWN", f"行格式错误: {line!r}") from exc
    return audit_amount(claim_id, amount)
