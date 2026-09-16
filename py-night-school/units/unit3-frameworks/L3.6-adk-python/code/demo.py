"""L3.6 统一出口（四课同题 demo 契约）：`async run_review(claim_id) -> Advice`。

离线确定性：内部起 MockLLMEndpoint（test-key / mock-model），台词由
review_rules.script_for 预生成——第 1 轮并行调用两个工具，第 2 轮给出
Advice JSON 文本；demo 侧用 Pydantic 校验解析（L2.4 纪律延续：LLM 不是
序列化层，边界上的 schema 由 Pydantic 把守——哪怕框架有 output_schema，
出口这道闸也留给验收方）。
"""

from __future__ import annotations

import mock_tools
import review_rules
from adk_review import ask, build_reviewer, build_runner, final_text, new_session
from advice import Advice
from mock_endpoint import MockLLMEndpoint


async def run_review(claim_id: str) -> Advice:
    """离线跑一次报销单审查：装配 → 预生成剧本 → 跑 Runner → 解析 Advice。"""
    mock_tools.CALL_LOG.clear()
    first_turn, final_json, _expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(final_json)
        runner = build_runner(build_reviewer(ep))
        session_id = await new_session(runner)
        events = [event async for event in ask(runner, session_id, f"请审查报销单 {claim_id}")]
    return Advice.model_validate_json(final_text(events))
