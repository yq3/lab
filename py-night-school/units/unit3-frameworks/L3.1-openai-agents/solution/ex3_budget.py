# 参考答案：ex3_budget（练习文件的完整解法——完成前别看）
"""max_turns 预算解法：try/finally 记账，MaxTurnsExceeded 原样上抛。"""

from __future__ import annotations

from agents import Agent, Runner, function_tool
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

import mock_tools
from mock_endpoint import MockLLMEndpoint

REQUESTS: list[int] = []

OBSESSION_ROUNDS = 12
USER_MESSAGE = "请审查报销单 CLM-2026-0001（部门 SALES，关联发票 INV-2026-0001）。"
DEPT = "SALES"


def script_obsession(ep: MockLLMEndpoint, rounds: int = OBSESSION_ROUNDS) -> None:
    """执念剧本：每轮回放一次「模型又要查预算」——永不给最终回答。"""
    for i in range(rounds):
        ep.script_tool_calls([{"id": f"call_loop_{i}", "name": "check_budget", "arguments": {"dept": DEPT}}])


async def run_observed(max_turns: int) -> int:
    mock_tools.CALL_LOG.clear()
    with MockLLMEndpoint() as ep:
        script_obsession(ep)
        model = OpenAIChatCompletionsModel(
            model=ep.model, openai_client=AsyncOpenAI(base_url=ep.url, api_key=ep.api_key)
        )
        agent = Agent(
            name="Reviewer",
            instructions="你是报销单审查员。",
            model=model,
            tools=[function_tool(mock_tools.check_budget)],
        )
        try:
            await Runner.run(agent, USER_MESSAGE, max_turns=max_turns)
            return len(ep.requests)
        finally:
            REQUESTS.append(len(ep.requests))
