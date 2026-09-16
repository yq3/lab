"""讲义区验收（二）：executor 的确定性——执行顺序、双跑全等、结构化失败可见不静默。"""

from __future__ import annotations

import json

import pytest

import mock_tools
from executor import PlanExecutionError, execute_plan
from plan import FetchBudgetStep, Plan, VerifyInvoiceStep, validate_plan


def _plan_of(text: str) -> Plan:
    outcome = validate_plan(text)
    assert isinstance(outcome, Plan)
    return outcome


def test_execute_plan_follows_plan_order_with_call_log_evidence() -> None:
    """执行顺序与计划一致：CALL_LOG 就是取证——计划正排与倒排，CALL_LOG 跟着变。"""
    plan = _plan_of(
        json.dumps(
            {
                "claim_total_cents": 5000,
                "steps": [
                    {"step_id": "s1", "tool": "fetch_claim", "claim_id": "CLM-2026-0004", "produces": "claim"},
                    {"step_id": "s2", "tool": "check_budget", "dept": "DEV", "produces": "budget"},
                    {"step_id": "s3", "tool": "verify_invoice", "invoice_id": "INV-2026-0005", "produces": "invoice"},
                ],
            },
            ensure_ascii=False,
        )
    )
    mock_tools.CALL_LOG.clear()
    results = execute_plan(plan)
    assert mock_tools.CALL_LOG == ["check_budget", "verify_invoice"]  # 顺序 = 计划顺序（fetch_claim 纯读取不记账）
    assert results["claim"]["dept"] == "DEV"
    assert results["budget"]["remaining_cents"] == 40000  # DEV 剩余预算，来自真实工具
    assert results["invoice"] == {"id": "INV-2026-0005", "valid": False, "reason": "发票已作废（连号重开）"}

    swapped = _plan_of(
        json.dumps(
            {
                "claim_total_cents": 5000,
                "steps": [
                    {"step_id": "s1", "tool": "verify_invoice", "invoice_id": "INV-2026-0005", "produces": "invoice"},
                    {"step_id": "s2", "tool": "check_budget", "dept": "DEV", "produces": "budget"},
                ],
            },
            ensure_ascii=False,
        )
    )
    mock_tools.CALL_LOG.clear()
    execute_plan(swapped)
    assert mock_tools.CALL_LOG == ["verify_invoice", "check_budget"]  # 游标由代码掌握，倒排照倒执行


def test_execute_plan_is_deterministic() -> None:
    """确定性：同计划双跑全等——数字代码算，同一输入永远同一输出。"""
    import demo

    plan = _plan_of(demo.legal_plan_text("CLM-2026-0001"))
    first = execute_plan(plan)
    second = execute_plan(plan)
    assert first == second
    assert first["budget"]["remaining_cents"] == 10000  # SALES 剩余预算


def test_unknown_tool_bypassing_gate_fails_loudly() -> None:
    """纵深防御的验收：绕过校验门构造的「计划外工具」（model_construct 不走校验），
    dispatcher 的白名单再查一层必须拦住——结构化失败，绝不静默执行错东西。"""
    smuggled = FetchBudgetStep.model_construct(step_id="s9", tool="steal_money", produces="vault", dept="DEV")
    plan = Plan.model_construct(steps=[smuggled], claim_total_cents=0, note="")
    mock_tools.CALL_LOG.clear()
    with pytest.raises(PlanExecutionError) as excinfo:
        execute_plan(plan)
    assert "s9" in str(excinfo.value) and "steal_money" in str(excinfo.value)
    assert excinfo.value.reason == "unknown_tool"
    assert mock_tools.CALL_LOG == []  # 什么都没被执行


def test_duplicate_produces_fails_loudly() -> None:
    """produces 冲突可见不静默：两个步骤写同一个键，第二个会静默覆盖第一个——
    dispatcher 拒绝这种计划，报 duplicate_produces。"""
    invoice = VerifyInvoiceStep(step_id="s1", tool="verify_invoice", invoice_id="INV-2026-0001", produces="same_key")
    budget = FetchBudgetStep(step_id="s2", tool="check_budget", dept="SALES", produces="same_key")
    plan = Plan(steps=[invoice, budget], claim_total_cents=7100)
    with pytest.raises(PlanExecutionError) as excinfo:
        execute_plan(plan)
    assert "duplicate_produces" in excinfo.value.reason
