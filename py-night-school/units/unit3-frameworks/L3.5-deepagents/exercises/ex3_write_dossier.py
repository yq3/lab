# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域与所需的顶部 import，其余不要动）
"""改造题 3：虚拟文件系统——审查底稿落盘的「编排 + 取回」。

demo 的 write_file 轮替主代理把底稿写进了 state["files"]；本题自己来编排这
一轮的两端：**发起**（组装 write_file 工具调用的参数）与**取回**（从最终
state 里把底稿正文捞出来）。中间的执行（StateBackend 把文件写进 state 的
files channel）由 harness 负责——这正是它替你付掉的代码。

TODO 两处：
  1) `_write_arguments(claim_id)`：组装 write_file 轮的 arguments——
     file_path 按 `/review/<单号>.md`；content 至少含三个事实：单号、
     结论码（review_rules.decide 同源决策）、部门剩余预算（分）。
  2) `extract_dossier(result)`：从最终 state 取回底稿正文
     （state 的哪个键 → 哪个路径 → 哪个字段——想 StateBackend 的存储形态）。

完成判据：uv run pytest exercises/test_ex3.py 全绿（两个测试）——
  底稿路径与内容断言；write_file 轮真实执行过（ToolMessage 取证）。
"""

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
    # TODO(ex3-1): 路径 /review/<单号>.md；content 用 mock_tools 的纯读取
    # （claim_view / budget_row / invoice_row）+ review_rules.decide 组三要素：
    # 单号、结论码、剩余预算分。不要调 check_budget / verify_invoice（会污染 CALL_LOG）。
    raise NotImplementedError("TODO(ex3-1): 补全 _write_arguments")


def extract_dossier(result: dict) -> str:
    """从最终 state 取回底稿正文。"""
    # TODO(ex3-2): state 的 files 键 → /review/<单号>.md → FileData 的 content 字段
    raise NotImplementedError("TODO(ex3-2): 补全 extract_dossier")


def build_agent(model: BaseChatModel) -> CompiledStateGraph:
    """given：check_budget 工具 + Advice 结构化收尾（本题不带子代理，聚焦文件系统）。"""
    return create_deep_agent(model=model, tools=[mock_tools.check_budget], system_prompt=SYSTEM, response_format=Advice)


async def run_with_dossier(claim_id: str) -> tuple[Advice, dict, str]:
    """given：剧本三轮——R1 check_budget；R2 write_file（参数来自 _write_arguments）；R3 Advice。

    返回 (建议单, 最终 state, 底稿正文)——底稿正文来自 extract_dossier。
    """
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
