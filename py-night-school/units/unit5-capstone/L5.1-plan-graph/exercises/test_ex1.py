"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

import demo
from ex1_plan import (
    FetchBudgetStep,
    FetchClaimStep,
    Plan,
    PlanRejection,
    VerifyInvoiceStep,
    validate_plan,
)

CLAIM = "CLM-2026-0002"  # 干净正数单（8800 分）


def test_legal_plan_dispatches_step_types_precisely() -> None:
    outcome = validate_plan(demo.legal_plan_text(CLAIM))
    assert isinstance(outcome, Plan)
    assert isinstance(outcome.steps[0], FetchClaimStep)
    assert isinstance(outcome.steps[1], FetchBudgetStep)
    assert isinstance(outcome.steps[2], VerifyInvoiceStep)
    assert outcome.steps[1].dept == "SALES"
    assert outcome.claim_total_cents == 8800


def test_dirty_data_restate_is_legal() -> None:
    """0003 总额 -500：忠实重述必须合法——校验门管格式，脏数据在建议单层处置。"""
    outcome = validate_plan(demo.legal_plan_text("CLM-2026-0003"))
    assert isinstance(outcome, Plan)
    assert outcome.claim_total_cents == -500


@pytest.mark.parametrize(
    ("name", "sample", "expected_code"),
    [
        ("不是 JSON", "抱歉，我先需要更多信息……", "not_json"),
        ("未知工具", lambda: demo.dirty_plan_unknown_tool(CLAIM), "unknown_tool"),
        ("缺必填参数", lambda: demo.dirty_plan_missing_field(CLAIM), "missing_field"),
        ("金额带单位字符串", lambda: demo.dirty_plan_bad_amount(CLAIM), "bad_amount"),
    ],
)
def test_rejects_each_dimension(name: str, sample: str | Callable[[], str], expected_code: str) -> None:
    text = sample() if callable(sample) else sample
    outcome = validate_plan(text)
    assert isinstance(outcome, PlanRejection), name
    assert outcome.reason_code == expected_code, (name, outcome.reason_code, outcome.detail)
    assert outcome.detail


def test_empty_plan_and_extra_field_dimensions() -> None:
    base = json.loads(demo.legal_plan_text(CLAIM))
    empty = validate_plan(json.dumps({**base, "steps": []}, ensure_ascii=False))
    assert isinstance(empty, PlanRejection) and empty.reason_code == "empty_plan"
    base["steps"][0]["urgency"] = "high"
    extra = validate_plan(json.dumps(base, ensure_ascii=False))
    assert isinstance(extra, PlanRejection) and extra.reason_code == "bad_plan_shape"


def test_rejection_codes_cover_all_six_dimensions() -> None:
    """覆盖型 meta：六维种类集逐维断言——某维样本被改成与另一维同码，这里当场红。"""
    base = json.loads(demo.legal_plan_text(CLAIM))
    samples = [
        "不是 JSON 的自由文本",
        demo.dirty_plan_unknown_tool(CLAIM),
        demo.dirty_plan_missing_field(CLAIM),
        demo.dirty_plan_bad_amount(CLAIM),
        json.dumps({**base, "steps": []}, ensure_ascii=False),
        json.dumps({**base, "unexpected": 1}, ensure_ascii=False),
    ]
    codes = set()
    for sample in samples:
        outcome = validate_plan(sample)
        assert isinstance(outcome, PlanRejection), sample[:40]
        codes.add(outcome.reason_code)
    assert codes == {"not_json", "unknown_tool", "missing_field", "bad_amount", "empty_plan", "bad_plan_shape"}
