"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import json

import pytest

import mock_tools
from ex2_executor import PlanExecutionError, execute_plan
from plan import FetchBudgetStep, Plan, VerifyInvoiceStep, validate_plan


def _plan_of(payload: dict) -> Plan:
    outcome = validate_plan(json.dumps(payload, ensure_ascii=False))
    assert isinstance(outcome, Plan)
    return outcome


BASE = {"claim_total_cents": 5000}


def test_execution_order_follows_plan_with_call_log_evidence() -> None:
    """执行顺序与计划一致：正排与倒排两份计划，CALL_LOG 跟着变——游标由代码掌握。"""
    forward = _plan_of(
        {
            **BASE,
            "steps": [
                {"step_id": "s1", "tool": "fetch_claim", "claim_id": "CLM-2026-0004", "produces": "claim"},
                {"step_id": "s2", "tool": "check_budget", "dept": "DEV", "produces": "budget"},
                {"step_id": "s3", "tool": "verify_invoice", "invoice_id": "INV-2026-0005", "produces": "invoice"},
            ],
        }
    )
    mock_tools.CALL_LOG.clear()
    results = execute_plan(forward)
    assert mock_tools.CALL_LOG == ["check_budget", "verify_invoice"]  # fetch_claim 纯读取不记账
    assert results["claim"]["dept"] == "DEV"
    assert results["budget"]["remaining_cents"] == 40000  # 来自真实工具，不是计划里的数字
    assert results["invoice"]["valid"] is False

    backward = _plan_of(
        {
            **BASE,
            "steps": [
                {"step_id": "s1", "tool": "verify_invoice", "invoice_id": "INV-2026-0005", "produces": "invoice"},
                {"step_id": "s2", "tool": "check_budget", "dept": "DEV", "produces": "budget"},
            ],
        }
    )
    mock_tools.CALL_LOG.clear()
    execute_plan(backward)
    assert mock_tools.CALL_LOG == ["verify_invoice", "check_budget"]


def test_same_plan_twice_yields_equal_results() -> None:
    """确定性：同计划双跑全等——数字代码算，同一输入永远同一输出。"""
    import demo

    plan = _plan_of(json.loads(demo.legal_plan_text("CLM-2026-0001")))
    assert execute_plan(plan) == execute_plan(plan)


def test_smuggled_unknown_tool_fails_loudly() -> None:
    """绕过校验门（model_construct 不走 Pydantic）夹带的计划外工具：dispatcher 必须拦——
    结构化失败（step_id/tool 读得出），且一个工具都没被执行。"""
    smuggled = FetchBudgetStep.model_construct(step_id="s9", tool="steal_money", produces="vault", dept="DEV")
    plan = Plan.model_construct(steps=[smuggled], claim_total_cents=0, note="")
    mock_tools.CALL_LOG.clear()
    with pytest.raises(PlanExecutionError) as excinfo:
        execute_plan(plan)
    assert "s9" in str(excinfo.value) and "steal_money" in str(excinfo.value)
    assert excinfo.value.reason == "unknown_tool"
    assert mock_tools.CALL_LOG == []


def test_duplicate_produces_fails_loudly() -> None:
    """produces 冲突可见不静默：两步写同一个键必须被拒（duplicate_produces），不是后者顶掉前者。"""
    invoice = VerifyInvoiceStep(step_id="s1", tool="verify_invoice", invoice_id="INV-2026-0001", produces="same_key")
    budget = FetchBudgetStep(step_id="s2", tool="check_budget", dept="SALES", produces="same_key")
    plan = Plan(steps=[invoice, budget], claim_total_cents=7100)
    with pytest.raises(PlanExecutionError) as excinfo:
        execute_plan(plan)
    assert "duplicate_produces" in excinfo.value.reason
