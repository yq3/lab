# 参考答案：ex2_prebuilt（练习文件的完整解法——完成前别看）
"""prebuilt 装配改造：用 create_react_agent 满足 Unit 3 统一出口 run_review。"""

from __future__ import annotations

import warnings

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.warnings import LangGraphDeprecatedSinceV10
from pydantic import SecretStr

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

SYSTEM_PROMPT = """你是报销单审查助手。审查规则（先命中先停）：
1) 明细含非正数金额 → ESCALATE / REJECT:INVALID_AMOUNT
2) 任一明细 > 5000 分 → REJECT / REJECT:ITEM_OVER_LIMIT
3) 关联发票校验未过 → REJECT / REJECT:INVOICE_INVALID
4) 总额 > 部门剩余预算 → REJECT / REJECT:BUDGET_EXCEEDED
5) 以上全不中 → APPROVE / PASS
先用工具核实部门预算与发票校验，最后一条消息只输出建议单 JSON
（claim_id / decision / reason / remaining_cents 四字段，金额单位分）。"""

RECURSION_LIMIT = 8


def model_for_url(url: str) -> ChatOpenAI:
    return ChatOpenAI(base_url=url, api_key=SecretStr("test-key"), model="mock-model", max_retries=0, timeout=10)


def user_brief(claim_id: str) -> str:
    view = mock_tools.claim_view(claim_id)
    return (
        f"请审查报销单 {view['id']}（{view['submitter']}，{view['purpose']}）。\n"
        f"明细（分）：{view['items_cents']}，总额 {view['total_cents']} 分；"
        f"部门 {view['dept']}；关联发票 {view['invoice_ids']}。\n"
        "请先用工具核实预算与发票，再输出建议单 JSON。"
    )


def build_agent(model: ChatOpenAI):
    """prebuilt 装配：一个调用换掉 L3.2 的整张手装图（工具由框架绑定与包装）。"""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=LangGraphDeprecatedSinceV10)
        return create_react_agent(
            model,
            tools=[mock_tools.check_budget, mock_tools.verify_invoice],
            prompt=SYSTEM_PROMPT,
        )


async def run_review(claim_id: str) -> Advice:
    """Unit 3 统一出口：剧本编排 + ainvoke + Advice.model_validate_json 出口把关。"""
    mock_tools.CALL_LOG.clear()
    first_turn, advice_json, _expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        agent = build_agent(model_for_url(ep.url))
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_brief(claim_id)}]},
            config={"recursion_limit": RECURSION_LIMIT},
        )
    return Advice.model_validate_json(result["messages"][-1].content.strip())
