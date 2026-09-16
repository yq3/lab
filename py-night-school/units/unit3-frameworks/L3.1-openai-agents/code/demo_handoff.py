"""实验③：handoff-as-tool——审查员 + 人工复核专员双 agent，ESCALATE 单转交。

wire 视角（讲义会贴真实输出）：handoff 在 chat-completions 协议上**就是一个普通工具**——
框架把复核专员包装成 transfer_to_<agent.name>（全小写、驼峰会被压平）的 function tool；
模型「调用」它之后，下一轮请求换了 system（复核专员的人设）、换了工具表，
消息历史却完整保留——这就是「转交」的全部机制，没有任何魔法。

ESCALATE 单（CLM-2026-0003，负数金额脏数据）三轮：
  1. 审查员并行调 check_budget + verify_invoice；
  2. 审查员调 transfer_to_humanspecialist（转交）；
  3. 复核专员（自己的 output_type=Advice）出建议单。
其余单两轮：审查员自己出建议单——handoff 是模型的选择，不是必经之路。
"""

from __future__ import annotations

import asyncio

from agents import Agent, Runner, function_tool, handoff, set_tracing_disabled
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

import mock_tools
import review_rules
from advice import Advice
from demo import INSTRUCTIONS, _user_message
from mock_endpoint import MockLLMEndpoint

set_tracing_disabled(True)
# 框架从 agent.name 生成转交工具名：transfer_to_ + 名字全小写（驼峰不拆、只压平）——
# 离线剧本必须用这个名字点名，错一个字母就是 ModelBehaviorError: Tool ... not found。
HANDOFF_TOOL_NAME = "transfer_to_humanspecialist"


def _build_model(ep: MockLLMEndpoint) -> OpenAIChatCompletionsModel:
    return OpenAIChatCompletionsModel(model=ep.model, openai_client=AsyncOpenAI(base_url=ep.url, api_key=ep.api_key))


def build_agents(ep: MockLLMEndpoint) -> tuple[Agent[None], Agent[None]]:
    """双 agent 装配：复核专员没有工具、只有人设与 output_type；审查员多一个 handoff。"""
    specialist = Agent(
        name="HumanSpecialist",
        handoff_description="处理脏数据等需要人工介入的报销单",  # 转交工具描述里会拼上这句
        instructions="你是人工复核专员：对转来的报销单复核后给出 ESCALATE 建议单。",
        model=_build_model(ep),
        output_type=Advice,
    )
    reviewer = Agent(
        name="Reviewer",
        instructions=INSTRUCTIONS + "\n发现明细含非正数金额（脏数据）时，转交人工复核专员。",
        model=_build_model(ep),
        tools=[function_tool(mock_tools.check_budget), function_tool(mock_tools.verify_invoice)],
        handoffs=[handoff(specialist)],  # handoff-as-tool：专员变成 reviewer 的一个工具
        output_type=Advice,
    )
    return reviewer, specialist


def _script(ep: MockLLMEndpoint, claim_id: str, decision: str, final_text: str) -> None:
    """排台词：工具轮 →（ESCALATE 才有转交轮）→ 建议单文本轮。"""
    first_turn, _ft, _expected = review_rules.script_for(claim_id)
    ep.script_tool_calls(first_turn)
    if decision == "ESCALATE":
        ep.script_tool_calls([{"id": "call_handoff", "name": HANDOFF_TOOL_NAME, "arguments": {}}])
    ep.script_text(final_text)


async def run_two_agent_review(claim_id: str) -> tuple[Advice, str, list[dict]]:
    """双 agent 审查：返回 (Advice, last_agent 名字, 每次请求的取证)。"""
    mock_tools.CALL_LOG.clear()
    with MockLLMEndpoint() as ep:
        first_turn, final_text, expected = review_rules.script_for(claim_id)
        _script(ep, claim_id, expected.decision, final_text)
        reviewer, _specialist = build_agents(ep)
        result = await Runner.run(reviewer, _user_message(claim_id))
        evidence = [
            {
                "roles": [m["role"] for m in req["messages"]],
                "tools": [t["function"]["name"] for t in req.get("tools", [])],
                "system": req["messages"][0]["content"][:14],
            }
            for req in ep.requests
        ]
        return result.final_output, result.last_agent.name, evidence


def main() -> None:
    print("== 双 agent（handoff-as-tool）四张单 ==")
    for claim in mock_tools.claims_table():
        advice, last_agent, evidence = asyncio.run(run_two_agent_review(claim["id"]))
        handoff_happened = last_agent == "HumanSpecialist"
        print(
            f"{claim['id']}  requests={len(evidence)}  last_agent={last_agent:<15} "
            f"handoff={'是' if handoff_happened else '否'}  -> {advice.decision} / {advice.reason}"
        )

    print("\n== ESCALATE 单（CLM-2026-0003）逐请求取证 ==")
    _advice, _agent, evidence = asyncio.run(run_two_agent_review("CLM-2026-0003"))
    for i, req in enumerate(evidence, start=1):
        print(f"request {i}: system={req['system']}…  tools={req['tools']}  roles={req['roles']}")
    print("看点：第 3 次请求 system 换成复核专员的人设、工具表清空，历史消息原样带上——")
    print("      这就是 handoff：换 agent 不换对话。")


if __name__ == "__main__":
    main()
