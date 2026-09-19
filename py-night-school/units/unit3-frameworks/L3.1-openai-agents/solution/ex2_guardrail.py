# 参考答案：ex2_guardrail（练习文件的完整解法——完成前别看）
"""guardrail 改造解法：护栏函数 = 抽单号 + 查表 + GuardrailFunctionOutput。"""

from __future__ import annotations

from agents import Agent, Runner, function_tool, input_guardrail
from agents.guardrail import GuardrailFunctionOutput
from agents.items import TResponseInputItem
from agents.models.interface import Model
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

REVIEWER_INSTRUCTIONS = "你是报销单审查员。先用 check_budget 查预算、verify_invoice 校验发票，再按规则出建议单。"


def _extract_claim_id(text: str) -> str | None:
    """从消息里抠 CLM-xxxx-xxxx 单号（护栏的解析器）。"""
    import re

    matched = re.search(r"CLM-\d{4}-\d{4}", text)
    return matched.group(0) if matched else None


def _build_model(ep: MockLLMEndpoint) -> Model:
    return OpenAIChatCompletionsModel(model=ep.model, openai_client=AsyncOpenAI(base_url=ep.url, api_key=ep.api_key))


def _script_if_known(ep: MockLLMEndpoint, message: str) -> None:
    claim_id = _extract_claim_id(message)
    if claim_id is not None and claim_id in {c["id"] for c in mock_tools.claims_table()}:
        first_turn, final_text, _expected = review_rules.script_for(claim_id)
        ep.script_tool_calls(first_turn)
        ep.script_text(final_text)


async def run_unguarded(message: str) -> tuple[Advice, int]:
    """改造前：没有护栏的入口。"""
    with MockLLMEndpoint() as ep:
        _script_if_known(ep, message)
        agent = Agent(
            name="Reviewer",
            instructions=REVIEWER_INSTRUCTIONS,
            model=_build_model(ep),
            tools=[function_tool(mock_tools.check_budget), function_tool(mock_tools.verify_invoice)],
            output_type=Advice,
        )
        result = await Runner.run(agent, message)
        return result.final_output, len(ep.requests)


@input_guardrail(name="claim_id_exists")
def claim_id_guardrail(ctx: object, agent: object, input: str | list[TResponseInputItem]) -> GuardrailFunctionOutput:
    """输入护栏：单号必须存在于 mock 用例表，宁拒收不猜。"""
    text = input if isinstance(input, str) else str(input)
    claim_id = _extract_claim_id(text)
    known = claim_id is not None and claim_id in {c["id"] for c in mock_tools.claims_table()}
    return GuardrailFunctionOutput(
        output_info={"claim_id": claim_id, "known": known},
        tripwire_triggered=not known,
    )


async def run_guarded(message: str) -> tuple[Advice, int]:
    """带护栏的入口：与 run_unguarded 唯一差异是 input_guardrails。"""
    with MockLLMEndpoint() as ep:
        _script_if_known(ep, message)
        agent = Agent(
            name="Reviewer",
            instructions=REVIEWER_INSTRUCTIONS,
            model=_build_model(ep),
            tools=[function_tool(mock_tools.check_budget), function_tool(mock_tools.verify_invoice)],
            output_type=Advice,
            input_guardrails=[claim_id_guardrail],
        )
        result = await Runner.run(agent, message)
        return result.final_output, len(ep.requests)
