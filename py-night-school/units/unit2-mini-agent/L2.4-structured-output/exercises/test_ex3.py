"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import pytest
from pydantic import ValidationError

import ex3_verdict_model as ex3


def test_decision_happy_path_and_schema() -> None:
    decision = ex3.Decision(claim_id="CLM-2026-0001", verdict="PASS", reason="明细合规")
    assert decision.reviewer == "night-school-agent"  # 默认值兜底
    schema = ex3.Decision.model_json_schema()
    assert "enum" in schema["properties"]["verdict"]  # Literal → enum：值域广告给模型
    assert len(schema["properties"]["verdict"]["enum"]) == 4
    assert "reviewer" not in schema["required"]  # 有默认 → 不进 required
    assert sorted(schema["required"]) == ["claim_id", "reason", "verdict"]


def test_decision_rejects_bad_values() -> None:
    with pytest.raises(ValidationError):
        ex3.Decision(claim_id="bad-id", verdict="PASS", reason="x")  # 单号格式：pattern 的工作
    with pytest.raises(ValidationError):
        ex3.Decision(claim_id="CLM-2026-0001", verdict="PASS", reason="")  # 空理由：min_length 的工作
    with pytest.raises(ValidationError):
        # 值域越界走 dict 路径喂（pyright 会在字面量调用处就把 Literal 违规拦下——静态层已经证明了这件事）
        ex3.Decision.model_validate({"claim_id": "CLM-2026-0001", "verdict": "REJECT:NEW_RULE", "reason": "x"})


def test_normalize_tolerant_but_closed() -> None:
    assert ex3.normalize_verdict(" pass ") == "PASS"
    assert ex3.normalize_verdict("reject:item_over_limit") == "REJECT:ITEM_OVER_LIMIT"
    assert ex3.normalize_verdict("REJECT: ITEM_OVER_LIMIT") == "REJECT:ITEM_OVER_LIMIT"
    assert ex3.normalize_verdict("Pass") == "PASS"


def test_normalize_never_invents() -> None:
    with pytest.raises(ValueError, match="未知"):
        ex3.normalize_verdict("REJECT:NEW_RULE")  # fail-closed：未知原因必须抛，不许猜
