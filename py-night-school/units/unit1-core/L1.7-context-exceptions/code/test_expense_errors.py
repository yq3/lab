"""讲义示例测试：报销领域异常分层。"""

import pytest

from expense_errors import (
    DAILY_MEAL_LIMIT_CENTS,
    ExpenseError,
    InvalidAmountError,
    LimitExceededError,
    audit_amount,
    parse_and_audit,
)


def test_pass_path() -> None:
    assert audit_amount("CLM-2026-0001", 1200) == "PASS"


def test_invalid_amount_carries_claim_id() -> None:
    with pytest.raises(InvalidAmountError) as exc_info:
        audit_amount("CLM-2026-0003", -500)
    assert exc_info.value.claim_id == "CLM-2026-0003"
    assert isinstance(exc_info.value, ExpenseError)  # 子类：一个 except 接住全家


def test_limit_exceeded_carries_limit() -> None:
    with pytest.raises(LimitExceededError) as exc_info:
        audit_amount("CLM-2026-0002", 8800)
    assert exc_info.value.limit_cents == DAILY_MEAL_LIMIT_CENTS
    assert exc_info.value.claim_id == "CLM-2026-0002"


def test_parse_and_audit_chains_cause() -> None:
    with pytest.raises(InvalidAmountError, match="行格式错误") as exc_info:
        parse_and_audit("CLM-2026-0001,12abc")
    assert isinstance(exc_info.value.__cause__, ValueError)  # 原始异常在链上
    assert parse_and_audit("CLM-2026-0001,1200") == "PASS"
