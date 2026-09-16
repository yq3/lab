"""讲义区验收（一）：validate_plan 的分派精确性与各拒绝维度——计划校验门的单元视角。

样本全部复用 demo 的剧本生成器（legal_plan_text / dirty_plan_*）——同一份脏样本
既演 demo 又进测试，讲义与验收同一口径（三方对齐纪律）。
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

import demo
import executor
from plan import (
    TOOL_ALLOWLIST,
    FetchBudgetStep,
    FetchClaimStep,
    Plan,
    PlanRejection,
    VerifyInvoiceStep,
    validate_plan,
)

CLAIM = "CLM-2026-0002"  # 干净正数单（8800 分）——金额维度的样本在它身上最无歧义


def test_legal_plan_dispatches_step_types_precisely() -> None:
    """判别联合精确分派：三个 tool tag 各自落到具体步型（对照 Jackson 多态反序列化）。"""
    outcome = validate_plan(demo.legal_plan_text(CLAIM))
    assert isinstance(outcome, Plan)
    assert isinstance(outcome.steps[0], FetchClaimStep)
    assert isinstance(outcome.steps[1], FetchBudgetStep)
    assert isinstance(outcome.steps[2], VerifyInvoiceStep)
    assert outcome.steps[1].dept == "SALES"
    assert outcome.claim_total_cents == 8800


def test_dirty_data_claim_restate_is_legal() -> None:
    """设计决策的钉子：脏数据单（0003 总额 -500）的忠实重述是合法计划——
    校验门只管格式（整数分），负总额要在建议单层被规则 1 处置（ESCALATE），不在计划层拦。"""
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
def test_validate_plan_rejects_each_dimension(name: str, sample: str | Callable[[], str], expected_code: str) -> None:
    """各拒绝维度逐维断言：每个脏样本命中自己的 reason_code（不是「一律 unknown_tool」式偷懒）。"""
    text = sample() if callable(sample) else sample
    outcome = validate_plan(text)
    assert isinstance(outcome, PlanRejection), name
    assert outcome.reason_code == expected_code, (name, outcome.reason_code, outcome.detail)
    assert outcome.detail  # 拒绝细节非空——它是回喂 planner 的任务数据


def test_empty_plan_and_extra_field_are_rejected() -> None:
    """两个补充维度：空计划（steps=[]）与多余字段——计划是数据合同：
    没内容的计划、合同外的东西都不收（extra_forbidden）。"""
    base = json.loads(demo.legal_plan_text(CLAIM))

    empty = validate_plan(json.dumps({**base, "steps": []}, ensure_ascii=False))
    assert isinstance(empty, PlanRejection) and empty.reason_code == "empty_plan"

    extra = json.loads(demo.legal_plan_text(CLAIM))
    extra["steps"][0]["urgency"] = "high"
    outcome = validate_plan(json.dumps(extra, ensure_ascii=False))
    assert isinstance(outcome, PlanRejection) and outcome.reason_code == "bad_plan_shape"


def test_rejection_reason_codes_cover_all_dimensions() -> None:
    """覆盖型 meta（L0.1 ex2 先例 / Unit 3 contract 补维度先例）：全部脏样本的
    reason_code 种类集逐维断言——把某维样本改成与另一维同码，本测试当场红。"""
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


def test_allowlist_matches_executor_registry() -> None:
    """meta：校验门的白名单与执行器的注册表必须同源——谁漂移了，这条当场红。"""
    assert TOOL_ALLOWLIST == frozenset(executor.TOOL_REGISTRY)
