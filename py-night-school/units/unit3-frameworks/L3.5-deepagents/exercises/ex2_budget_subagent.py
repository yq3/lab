# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体/区域与所需的顶部 import，其余不要动）
"""改造题 2：增设「预算专员」子代理。

demo 里发票专员（invoice-specialist）把 verify_invoice 收进了子代理；本题把
check_budget 也交出去：声明 `budget-specialist` 子代理（**名字必须严格是
budget-specialist**——given 剧本的转交台词与验收测试都按它找人），只给它
check_budget 一个工具；主代理自己不带任何自定义工具，全靠 task 转交。

SubAgent 是声明式 TypedDict：主代理读 `description` 决定何时转交，子代理的
人设在 `system_prompt`，能力边界在 `tools`——三个键的受众各不相同。

TODO 一处：BUDGET_SPECIALIST 的四个键（name / description / system_prompt / tools）。

完成判据：uv run pytest exercises/test_ex2.py 全绿（两个测试）——
  task 工具目录里挂上 budget-specialist；预算查询确实发生在子代理自己的模型轮里。
"""

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
    # TODO(ex2): 补全四个键——
    #   "name": 必须是 "budget-specialist"
    #   "description": 给主代理看的转交说明（何时找它、它能干什么）
    #   "system_prompt": 子代理自己的人设（只管查预算、简短报告）
    #   "tools": 它独享的工具列表（本题只给 mock_tools.check_budget，不给别的）
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
    """given：剧本四轮——R1 主代理 task 转交；R2 子代理 check_budget；R3 子代理报告；R4 主代理 Advice。

    返回 (建议单, 取证 dict：requests + state)。
    """
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
