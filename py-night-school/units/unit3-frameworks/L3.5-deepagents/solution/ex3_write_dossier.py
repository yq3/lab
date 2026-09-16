# 解答（ex3_write_dossier）：与 exercises/ex3_write_dossier.py 同名全覆盖——毕业态把它拷回 exercises/ 验证。
"""参考答案：改造题 3——write_file 轮参数组装 + 从最终 state 取回底稿正文。"""

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

SYSTEM = "你是报销单审查助手：查完预算把审查底稿写入 /review/<单号>.md，再调用 Advice 提交建议单。"


def _write_arguments(claim_id: str) -> dict:
    """组装 write_file 轮的工具调用参数：{"file_path": ..., "content": ...}。"""
    view = mock_tools.claim_view(claim_id)
    budget = mock_tools.budget_row(view["dept"])
    invoice = mock_tools.invoice_row(view["invoice_ids"][0])
    if budget is None or invoice is None:
        raise KeyError(f"mock 数据缺行: {claim_id}")
    expected = review_rules.decide(view, budget, invoice)
    remaining = budget["budget_cents"] - budget["spent_cents"]
    content = f"# 审查底稿 {claim_id}\n- 结论：{expected.decision} / {expected.reason}\n- 剩余预算：{remaining} 分\n"
    return {"file_path": f"/review/{claim_id}.md", "content": content}


def extract_dossier(result: dict) -> str:
    """从最终 state 取回底稿正文（本轮只落一个 /review/ 文件）。"""
    path = next(p for p in result["files"] if p.startswith("/review/"))
    return result["files"][path]["content"]


def build_agent(model: BaseChatModel) -> CompiledStateGraph:
    """given：check_budget 工具 + Advice 结构化收尾（本题不带子代理，聚焦文件系统）。"""
    return create_deep_agent(model=model, tools=[mock_tools.check_budget], system_prompt=SYSTEM, response_format=Advice)


async def run_with_dossier(claim_id: str) -> tuple[Advice, dict, str]:
    """given：剧本三轮——R1 check_budget；R2 write_file（参数来自 _write_arguments）；R3 Advice。"""
    mock_tools.CALL_LOG.clear()
    _, _, expected = review_rules.script_for(claim_id)
    view = mock_tools.claim_view(claim_id)
    with MockLLMEndpoint() as ep:
        model = ChatOpenAI(base_url=ep.url, api_key=SecretStr(ep.api_key), model=ep.model)
        agent = build_agent(model)
        ep.script_tool_calls([{"id": "call_budget", "name": "check_budget", "arguments": {"dept": view["dept"]}}])
        ep.script_tool_calls([{"id": "call_write", "name": "write_file", "arguments": _write_arguments(claim_id)}])
        ep.script_tool_calls([{"id": "call_advice", "name": "Advice", "arguments": expected.model_dump()}])
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=f"请审查报销单 {claim_id}：{view['purpose']}，部门 {view['dept']}。")]}
        )
    structured = result.get("structured_response")
    if not isinstance(structured, Advice):
        raise AssertionError(f"结构化收尾缺失: {structured!r}")
    return structured, dict(result), extract_dossier(result)
