"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio

from agents.models.interface import Model
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

import ex1_handoff as ex1
import mock_tools
from advice import Advice
from mock_endpoint import MockLLMEndpoint


def _model_for(ep: MockLLMEndpoint) -> Model:
    return OpenAIChatCompletionsModel(model=ep.model, openai_client=AsyncOpenAI(base_url=ep.url, api_key=ep.api_key))


def test_build_agents_shapes() -> None:
    """结构检查：复核专员无工具、output_type 是 Advice；审查员挂上了 handoff。"""
    with MockLLMEndpoint() as ep:
        reviewer, specialist = ex1.build_agents(_model_for(ep))
    assert specialist.name == "HumanSpecialist"
    assert specialist.tools == []
    assert specialist.output_type is Advice
    assert reviewer.handoffs, "审查员必须挂 handoff(specialist)"


def test_handoff_happens_for_escalation() -> None:
    advice, last_agent, requests = asyncio.run(ex1.run_review("CLM-2026-0003"))
    assert last_agent == "HumanSpecialist"
    assert requests == 3
    assert advice.decision == "ESCALATE"
    assert advice.reason == "REJECT:INVALID_AMOUNT"


def test_no_handoff_for_other_claims() -> None:
    for claim_id in ("CLM-2026-0001", "CLM-2026-0002", "CLM-2026-0004"):
        advice, last_agent, requests = asyncio.run(ex1.run_review(claim_id))
        assert last_agent == "Reviewer", claim_id
        assert requests == 2, claim_id


def test_contract_decisions_unchanged() -> None:
    """改造后契约决策不变：四张单与用例表 expect_* 逐字段一致。"""
    for claim in mock_tools.claims_table():
        advice, _, _ = asyncio.run(ex1.run_review(claim["id"]))
        assert advice.decision == claim["expect_decision"], claim["id"]
        assert advice.reason == claim["expect_reason"], claim["id"]
        assert advice.remaining_cents == claim["expect_remaining_cents"], claim["id"]


def test_tools_really_executed_every_run() -> None:
    for claim in mock_tools.claims_table():
        asyncio.run(ex1.run_review(claim["id"]))
        assert {"check_budget", "verify_invoice"} <= set(mock_tools.CALL_LOG), claim["id"]
