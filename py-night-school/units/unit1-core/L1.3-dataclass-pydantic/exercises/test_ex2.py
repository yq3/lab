"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

import pytest
from pydantic import ValidationError

from ex2_schema import INVALID_CASES, ReceiptSubmission

# 合法样本：模型语义的正确侧（含边界——恰好 5000 分必须放行）
VALID_SAMPLES: list[dict[str, object]] = [
    {"receipt_no": "RCP-2026-000123", "amount_cents": 3500, "payer": "美团"},
    {"receipt_no": "RCP-2025-999999", "amount_cents": 1, "payer": "便利店"},  # 下边界：1 分也合法
    {"receipt_no": "RCP-2026-000001", "amount_cents": 5000, "payer": "滴滴"},  # 上边界：恰好 5000 合法
]


@pytest.mark.parametrize("payload", VALID_SAMPLES, ids=lambda p: str(p["receipt_no"]))
def test_ex2_valid_samples_pass(payload: dict[str, object]) -> None:
    receipt = ReceiptSubmission.model_validate(payload)
    assert receipt.amount_cents > 0


@pytest.mark.parametrize(("kind", "payload"), INVALID_CASES)
def test_ex2_invalid_cases_rejected(kind: str, payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReceiptSubmission.model_validate(payload)


def test_ex2_invalid_cases_cover_all_fields() -> None:
    """验收的验收：样本表必须覆盖三个字段各自的违规、至少 4 组（防止「全挑软柿子」）。"""
    kinds = {kind for kind, _ in INVALID_CASES}
    missing = {"receipt_no", "amount_cents", "payer"} - kinds
    assert not missing, f"样本表缺少对字段 {sorted(missing)} 的违规样本"
    assert len(INVALID_CASES) >= 4, "至少 4 组非法样本"
    assert len({repr(payload) for _, payload in INVALID_CASES}) == len(INVALID_CASES), "样本不得重复"
