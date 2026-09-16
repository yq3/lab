# 解答（ex2_budget_subagent）：与 exercises/ex2_budget_subagent.py 同名全覆盖——毕业态把它拷回 exercises/ 验证。
"""参考答案：改造题 2——声明 budget-specialist 子代理（四键齐全，只带 check_budget）。"""

from __future__ import annotations

from typing import Any, cast

from deepagents import SubAgent, create_deep_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph
from pydantic import SecretStr

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

SYSTEM = "你是报销单审查助手：预算余额必须转交 budget-specialist 子代理查询，再按规则表出结论。"

BUDGET_SPECIALIST: dict[str, Any] = {
    "name": "budget-specialist",
    "description": "预算查询专员：查询部门预算余额与剩余额度，需要 check_budget 结果时转交",
    "system_prompt": "你是预算查询专员，只负责调用 check_budget 工具查部门预算，并简短报告余额。",
    "tools": [mock_tools.check_budget],
}


def build_agent(model: BaseChatModel) -> CompiledStateGraph:
    """given：主代理零自定义工具，只有子代理一条路（cast 是类型断言，Java 同款老朋友）。"""
    return create_deep_agent(
        model=model,
        system_prompt=SYSTEM,
        subagents=[cast(SubAgent, BUDGET_SPECIALIST)],
        response_format=Advice,
    )


async def run_via_specialist(claim_id: str) -> tuple[Advice, dict]:
    """given：剧本四轮——R1 主代理 task 转交；R2 子代理 check_budget；R3 子代理报告；R4 主代理 Advice。"""
    mock_tools.CALL_LOG.clear()
    _, _, expected = review_rules.script_for(claim_id)
    view = mock_tools.claim_view(claim_id)
    budget = mock_tools.budget_row(view["dept"])
    if budget is None:
        raise KeyError(f"mock 数据缺行: {claim_id}")
    remaining = budget["budget_cents"] - budget["spent_cents"]
    with MockLLMEndpoint() as ep:
        model = ChatOpenAI(base_url=ep.url, api_key=SecretStr(ep.api_key), model=ep.model)
        agent = build_agent(model)
        ep.script_tool_calls(
            [
                {
                    "id": "call_task",
                    "name": "task",
                    "arguments": {
                        "description": f"查询报销单 {claim_id} 所属部门 {view['dept']} 的预算余额",
                        "subagent_type": "budget-specialist",
                    },
                }
            ]
        )
        ep.script_tool_calls([{"id": "call_budget", "name": "check_budget", "arguments": {"dept": view["dept"]}}])
        report = (
            f"部门 {view['dept']} 预算 {budget['budget_cents']} 分，"
            f"已花 {budget['spent_cents']} 分，剩余 {remaining} 分。"
        )
        ep.script_text(report)
        ep.script_tool_calls([{"id": "call_advice", "name": "Advice", "arguments": expected.model_dump()}])
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=f"请审查报销单 {claim_id}：{view['purpose']}，部门 {view['dept']}。")]}
        )
        trace = {"requests": list(ep.requests), "state": dict(result)}
    structured = result.get("structured_response")
    if not isinstance(structured, Advice):
        raise AssertionError(f"结构化收尾缺失: {structured!r}")
    return structured, trace
