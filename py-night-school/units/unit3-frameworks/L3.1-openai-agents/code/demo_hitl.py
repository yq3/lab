"""实验⑤（进阶）：RunState 的 HITL——工具审批：暂停 → 序列化 → 批准 → 恢复。

场景：审查结论要「记入复核台账」——写操作是敏感动作，规定必须有人点头。
openai-agents 的机制（docs/human_in_the_loop.md，机制源码在 run_state.py）：

  1. function_tool(needs_approval=True)：模型点名调它时，run **暂停**并正常返回
     （不抛异常）——result.interruptions 里是待审批的 ToolApprovalItem；
  2. result.to_state()：把整个运行拍成可序列化的 RunState 快照（to_string 是 JSON）；
  3. state.approve(item) / state.reject(item)：人工决定写回快照；
  4. Runner.run(agent, state)：从断点恢复——已被批准的工具执行、继续后续轮次。

本实验还演示「杀进程再恢复」：把快照 to_string 存成字符串、再 from_string 重建——
这是 L3.3（langgraph checkpoint/interrupt）将做的同一件事在另一个框架里的形态，
毕业设计「审批暂停→恢复」的预习课。

台词（实测三轮）：工具轮 → 记台账轮（触发暂停）→ 恢复后的结论轮。
"""

from __future__ import annotations

import asyncio

from agents import Agent, Runner, RunState, function_tool, set_tracing_disabled
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

import mock_tools
import review_rules
from advice import Advice
from demo import INSTRUCTIONS, _user_message
from mock_endpoint import MockLLMEndpoint

set_tracing_disabled(True)


@function_tool(needs_approval=True)
def log_decision(claim_id: str, decision: str) -> str:
    """把审查结论记入复核台账（敏感写操作，需人工批准后才会真正执行）。"""
    mock_tools.CALL_LOG.append("log_decision")
    return f"logged: {claim_id} -> {decision}"


def _build_agent(ep: MockLLMEndpoint) -> Agent[None]:
    model = OpenAIChatCompletionsModel(model=ep.model, openai_client=AsyncOpenAI(base_url=ep.url, api_key=ep.api_key))
    return Agent(
        name="Reviewer",
        instructions=INSTRUCTIONS + "\n两个查询工具用完后，调 log_decision 记台账，再给最终建议单。",
        model=model,
        tools=[
            function_tool(mock_tools.check_budget),
            function_tool(mock_tools.verify_invoice),
            log_decision,
        ],
        output_type=Advice,
    )


def _script(ep: MockLLMEndpoint, claim_id: str) -> None:
    """台词：查询轮 → 记台账轮（触发暂停）→ 恢复后的建议单轮。"""
    first_turn, final_text, _expected = review_rules.script_for(claim_id)
    ep.script_tool_calls(first_turn)
    ep.script_tool_calls(
        [{"id": "call_log", "name": "log_decision", "arguments": {"claim_id": claim_id, "decision": "REJECT"}}]
    )
    ep.script_text(final_text)


async def main() -> None:
    claim_id = "CLM-2026-0002"  # 任一张单都行；这张单本身不需要人审，演示的是「工具」要人审
    mock_tools.CALL_LOG.clear()
    with MockLLMEndpoint() as ep:
        _script(ep, claim_id)
        agent = _build_agent(ep)

        print("== 第 1 段：跑到记台账，run 在审批点暂停 ==")
        result = await Runner.run(agent, _user_message(claim_id))
        print(f"模型请求: {len(ep.requests)} 次（查询轮 + 记台账轮）")
        print(f"CALL_LOG: {mock_tools.CALL_LOG}（log_decision 还没执行——等批准）")
        item = result.interruptions[0]
        print(f"待审批: tool={item.tool_name}  arguments={item.arguments}")
        print(f"final_output: {result.final_output!r}（没有结论——run 没跑完）")

        print("\n== 第 2 段：快照 → 杀进程（字符串进出）→ 批准 → 恢复 ==")
        blob: str = result.to_state().to_string()
        print(f"RunState 快照: {len(blob)} 字符的 JSON（含历史、审批状态、轮数）")
        state: RunState[None, Agent[None]] = await RunState.from_string(agent, blob)
        state.approve(state.get_interruptions()[0])  # 拒绝就用 reject(item)
        resumed = await Runner.run(agent, state)
        print(f"模型请求累计: {len(ep.requests)} 次（+1：恢复后的建议单轮）")
        print(f"CALL_LOG: {mock_tools.CALL_LOG}（log_decision 被批准后真实执行了）")
        print(f"final_output: {resumed.final_output!r}")


if __name__ == "__main__":
    asyncio.run(main())
