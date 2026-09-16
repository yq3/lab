# 解答（ex1_custom_tool）：与 exercises/ex1_custom_tool.py 同名全覆盖——毕业态把它拷回 exercises/ 验证。
"""参考答案：改造题 1——自定义工具 lookup_policy（命中记日志，未命中回错误行）+ 双工具注册。"""

from __future__ import annotations

from deepagents import create_deep_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph
from pydantic import SecretStr

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

SYSTEM = "你是报销单审查助手：先查政策与预算，再按规则表出结论（金额一律整数分）。"

# 练习素材（内联声明）：用途关键词 → 政策话术行
POLICY_TABLE: dict[str, dict] = {
    "宴请": {
        "keyword": "宴请",
        "policy": "工作餐人均不超过 150 元；项目验收宴请需部门总监事前批准",
        "limit_cents": 5000,
    },
    "交通": {
        "keyword": "交通",
        "policy": "市内交通实报实销；打车单程超过 200 元需说明事由",
        "limit_cents": 100000,
    },
    "物料": {
        "keyword": "物料",
        "policy": "展会物料采购需附三家比价记录",
        "limit_cents": 50000,
    },
}
POLICY_LOG: list[str] = []


def lookup_policy(purpose_keyword: str) -> dict:
    """按报销用途关键词查政策话术：返回政策行（含 policy 原文与限额，单位分）。"""
    lowered = purpose_keyword.lower()
    for key, row in POLICY_TABLE.items():
        if key in lowered:
            POLICY_LOG.append("lookup_policy")
            return dict(row)
    return {"keyword": purpose_keyword, "error": "policy_not_found"}


def build_agent(model: BaseChatModel) -> CompiledStateGraph:
    """组装本题的 agent：check_budget 与 lookup_policy 双工具 + Advice 结构化收尾。"""
    return create_deep_agent(
        model=model,
        tools=[mock_tools.check_budget, lookup_policy],
        system_prompt=SYSTEM,
        response_format=Advice,
    )


async def run_with_policy(claim_id: str, keyword: str) -> tuple[Advice, dict]:
    """given：剧本跑一轮「查政策 + 查预算 → 建议单」，返回 (建议单, 最终 state)。"""
    mock_tools.CALL_LOG.clear()
    POLICY_LOG.clear()
    _, _, expected = review_rules.script_for(claim_id)
    view = mock_tools.claim_view(claim_id)
    with MockLLMEndpoint() as ep:
        model = ChatOpenAI(base_url=ep.url, api_key=SecretStr(ep.api_key), model=ep.model)
        agent = build_agent(model)
        ep.script_tool_calls(
            [
                {"id": "call_policy", "name": "lookup_policy", "arguments": {"purpose_keyword": keyword}},
                {"id": "call_budget", "name": "check_budget", "arguments": {"dept": view["dept"]}},
            ]
        )
        ep.script_tool_calls([{"id": "call_advice", "name": "Advice", "arguments": expected.model_dump()}])
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=f"请审查报销单 {claim_id}：{view['purpose']}，部门 {view['dept']}。")]}
        )
    structured = result.get("structured_response")
    if not isinstance(structured, Advice):
        raise AssertionError(f"结构化收尾缺失: {structured!r}")
    return structured, dict(result)
