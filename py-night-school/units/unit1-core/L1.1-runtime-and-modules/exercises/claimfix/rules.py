"""claimfix 的规则模块（与 expense.rules 同一套预审规则的简化版）。"""

DAILY_MEAL_LIMIT_CENTS = 5000


def preapprove(items_cents: list[int]) -> str:
    """两条规则的简化预审：脏数据最先挡，其次单笔超限。"""
    if any(c <= 0 for c in items_cents):
        return "REJECT:INVALID_AMOUNT"
    if any(c > DAILY_MEAL_LIMIT_CENTS for c in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    return "PASS"
