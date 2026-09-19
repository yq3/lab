# 参考答案：ex1_handoff（练习文件的完整解法——完成前别看）
"""handoff 改造解法：复核专员是无工具的结构化输出 agent；审查员多挂一个 handoff。

台词侧的关键认知：handoff 在 wire 上就是一个普通工具调用——离线剧本第 2 轮
script_tool_calls 点名 transfer_to_humanspecialist，框架收到后换 agent 继续循环。
"""

from __future__ import annotations

from agents import Agent, Runner, function_tool, handoff
from agents.models.interface import Model
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

# （骨架里的常量与 given 函数在毕业态同名保留——本文件是练习文件的完整覆盖版）
HANDOFF_TOOL_NAME = "transfer_to_humanspecialist"

REVIEWER_INSTRUCTIONS = (
    "你是报销单审查员。先用 check_budget 查预算、verify_invoice 校验发票，"
    "发现明细含非正数金额（脏数据）时，转交人工复核专员。"
)
SPECIALIST_INSTRUCTIONS = "你是人工复核专员：对转来的报销单复核后给出 ESCALATE 建议单。"
SPECIALIST_DESCRIPTION = "处理脏数据等需要人工介入的报销单"


def _user_message(claim_id: str) -> str:
    view = mock_tools.claim_view(claim_id)
    return (
        f"请审查报销单 {view['id']}（提交人 {view['submitter']}，部门 {view['dept']}，"
        f"关联发票 {view['invoice_ids'][0]}，明细分：{view['items_cents']}）。"
    )


def build_single_agent(model: Model) -> Agent:
    """改造前：单 agent 审查员。"""
    return Agent(
        name="Reviewer",
        instructions=REVIEWER_INSTRUCTIONS,
        model=model,
        tools=[function_tool(mock_tools.check_budget), function_tool(mock_tools.verify_invoice)],
        output_type=Advice,
    )


def build_agents(model: Model) -> tuple[Agent, Agent]:
    """双 agent 装配：专员在前（reviewer 的 handoffs 要引用它）。"""
    specialist = Agent(
        name="HumanSpecialist",
        handoff_description=SPECIALIST_DESCRIPTION,
        instructions=SPECIALIST_INSTRUCTIONS,
        model=model,
        output_type=Advice,
    )
    reviewer = Agent(
        name="Reviewer",
        instructions=REVIEWER_INSTRUCTIONS,
        model=model,
        tools=[function_tool(mock_tools.check_budget), function_tool(mock_tools.verify_invoice)],
        handoffs=[handoff(specialist)],
        output_type=Advice,
    )
    return reviewer, specialist


def script_rounds(ep: MockLLMEndpoint, claim_id: str) -> None:
    """排台词：工具轮 →（ESCALATE 才有转交轮）→ 建议单文本轮。"""
    first_turn, final_text, expected = review_rules.script_for(claim_id)
    ep.script_tool_calls(first_turn)
    if expected.decision == "ESCALATE":
        ep.script_tool_calls([{"id": "call_handoff", "name": HANDOFF_TOOL_NAME, "arguments": {}}])
    ep.script_text(final_text)


def _build_model(ep: MockLLMEndpoint) -> OpenAIChatCompletionsModel:
    return OpenAIChatCompletionsModel(model=ep.model, openai_client=AsyncOpenAI(base_url=ep.url, api_key=ep.api_key))


async def run_review(claim_id: str) -> tuple[Advice, str, int]:
    mock_tools.CALL_LOG.clear()
    with MockLLMEndpoint() as ep:
        reviewer, _specialist = build_agents(_build_model(ep))
        script_rounds(ep, claim_id)
        result = await Runner.run(reviewer, _user_message(claim_id))
        return result.final_output, result.last_agent.name, len(ep.requests)
