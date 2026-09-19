"""讲义区（code/）验收：demo 机制的确定性检查——test_contract.py 之外的框架行为取证。

覆盖：docstring-as-schema（L2.2 对照点）、run_review 与剧本预期逐字段相等、
handoff 的 last_agent/请求数、guardrail 的 tripwire 与零模型请求、HITL 暂停→批准→恢复。
"""

from __future__ import annotations

import asyncio

import pytest
from agents.exceptions import InputGuardrailTripwireTriggered

import demo
import mock_tools
import review_rules
from advice import Advice
from demo import _build_tools, run_review
from mock_endpoint import MockLLMEndpoint


def test_function_tool_schema_from_signature_and_docstring() -> None:
    """function_tool 装饰时生成 schema：签名→参数表、docstring→描述（对照 L2.2 手写注册表）。"""
    budget_tool = _build_tools()[0]
    assert budget_tool.name == "check_budget"
    assert budget_tool.description == mock_tools.check_budget.__doc__
    assert budget_tool.params_json_schema["required"] == ["dept"]
    assert budget_tool.params_json_schema["properties"]["dept"]["type"] == "string"
    invoice_tool = _build_tools()[1]
    assert invoice_tool.params_json_schema["required"] == ["invoice_id"]


def test_run_review_equals_scripted_expectation_for_all_claims() -> None:
    """四张单：run_review 返回值与剧本预期逐字段相等，且都是校验过的 Advice 实例。"""
    for claim in mock_tools.claims_table():
        advice = asyncio.run(run_review(claim["id"]))
        _, _, expected = review_rules.script_for(claim["id"])
        assert isinstance(advice, Advice)
        assert advice == expected, claim["id"]


def test_handoff_routes_escalation_to_specialist() -> None:
    """handoff 改造（讲义 Step 3）：ESCALATE 单由复核专员收尾（3 次请求），其余仍两轮。"""
    from demo_handoff import run_two_agent_review

    advice, last_agent, evidence = asyncio.run(run_two_agent_review("CLM-2026-0003"))
    assert last_agent == "HumanSpecialist"
    assert len(evidence) == 3
    assert advice.decision == "ESCALATE"

    advice, last_agent, evidence = asyncio.run(run_two_agent_review("CLM-2026-0001"))
    assert last_agent == "Reviewer"
    assert len(evidence) == 2
    assert advice.decision == "APPROVE"


def test_guardrail_trips_on_unknown_claim_without_model_call() -> None:
    """输入护栏（讲义 Step 4）：坏单号 tripwire 且模型零请求；好单号照常出建议单。"""
    from agents import Runner

    from demo_guardrail import _build_agent, extract_claim_id

    assert extract_claim_id("请审查报销单 CLM-2026-0001。") == "CLM-2026-0001"
    assert extract_claim_id("帮我把报销都过一遍。") is None

    with MockLLMEndpoint() as ep:
        ep.script_text("不应被消费")
        bad_message = "请审查报销单 CLM-2026-9999（部门 SALES，关联发票 INV-2026-0001）。"
        with pytest.raises(InputGuardrailTripwireTriggered) as excinfo:
            asyncio.run(Runner.run(_build_agent(ep), bad_message))
        assert excinfo.value.guardrail_result.output.output_info == {
            "claim_id": "CLM-2026-9999",
            "known": False,
        }
        assert len(ep.requests) == 0  # 护栏先到，模型任务被取消


def test_hitl_pause_serialize_approve_resume() -> None:
    """RunState HITL（讲义 Step 5）：记台账工具暂停 → 快照字符串 → 批准 → 恢复出 Advice。"""
    from agents import Runner, RunState

    from demo_hitl import _build_agent, _script

    claim_id = "CLM-2026-0002"
    mock_tools.CALL_LOG.clear()
    with MockLLMEndpoint() as ep:
        _script(ep, claim_id)
        agent = _build_agent(ep)
        paused = asyncio.run(Runner.run(agent, demo._user_message(claim_id)))
        assert paused.final_output is None
        assert paused.interruptions[0].tool_name == "log_decision"
        assert "log_decision" not in mock_tools.CALL_LOG  # 等批准，未执行

        blob = paused.to_state().to_string()
        state = asyncio.run(RunState.from_string(agent, blob))
        state.approve(state.get_interruptions()[0])
        resumed = asyncio.run(Runner.run(agent, state))
        assert resumed.final_output is not None
        assert resumed.final_output.decision == "REJECT"
        assert "log_decision" in mock_tools.CALL_LOG  # 批准后真实执行
        assert len(ep.requests) == 3
