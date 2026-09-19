"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import warnings
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, create_react_agent
from langgraph.warnings import LangGraphDeprecatedSinceV10
from pydantic import SecretStr

import ex3_facts
import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint


def _unused_model() -> ChatOpenAI:
    """只用于装配（不发请求）的模型客户端。"""
    return ChatOpenAI(base_url="http://unused.local/v1", api_key=SecretStr("test-key"), model="mock-model")


def _build(model: ChatOpenAI, **kwargs) -> CompiledStateGraph:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=LangGraphDeprecatedSinceV10)
        return create_react_agent(
            model, tools=[mock_tools.check_budget, mock_tools.verify_invoice], prompt="你是审查助手。", **kwargs
        )


def _scripted_model(ep: MockLLMEndpoint) -> ChatOpenAI:
    """指向 mock 端点的模型客户端（剧本由调用方预先编排）。"""
    return ChatOpenAI(base_url=ep.url, api_key=SecretStr("test-key"), model="mock-model", max_retries=0, timeout=10)


def _stream_chunk_names(agent: CompiledStateGraph, ep: MockLLMEndpoint) -> list[str]:
    """跑一趟单审剧本，返回每个超步的节点名（updates 模式每块恰好一个节点键）。"""
    first_turn, advice_json, _expected = review_rules.script_for("CLM-2026-0003")
    ep.script_tool_calls(first_turn)
    ep.script_text(advice_json)
    return [
        list(chunk.keys())[0]
        for chunk in agent.stream(
            {"messages": [{"role": "user", "content": "审查 CLM-2026-0003"}]},
            stream_mode="updates",
        )
    ]


def test_facts_node_names_match_stream_roles() -> None:
    """①② 节点名用 stream 轨迹验证：第一个超步是模型节点、中间两个是工具节点——填反了会红。"""
    agent = _build(_unused_model())
    assert set(agent.get_graph().nodes) == {
        "__start__",
        "__end__",
        str(ex3_facts.FACTS["model_node_name"]),
        str(ex3_facts.FACTS["tools_node_name"]),
    }
    with MockLLMEndpoint() as ep:
        chunks = _stream_chunk_names(_build(_scripted_model(ep)), ep)
    assert chunks[0] == ex3_facts.FACTS["model_node_name"]  # 第一个超步：模型节点
    assert chunks[1] == ex3_facts.FACTS["tools_node_name"]  # 中间超步：工具节点
    assert chunks[3] == ex3_facts.FACTS["model_node_name"]  # 收束超步：又回到模型节点


def test_facts_route_behavior_and_fanout_task_count() -> None:
    """③④ 路由语义与扇出任务数：v2 默认下 should_continue 返回 Send 列表——一轮 2 个工具调用
    会出现 2 个独立的 tools 超步（每个 tool_call 一个 Send 任务），而不是 1 个装 2 条的 tools 块。"""
    first_turn, _advice_json, _expected = review_rules.script_for("CLM-2026-0003")
    with MockLLMEndpoint() as ep:
        chunks = _stream_chunk_names(_build(_scripted_model(ep)), ep)
    tools_chunks = [name for name in chunks if name == ex3_facts.FACTS["tools_node_name"]]
    assert ex3_facts.FACTS["route_fn_behavior"] == "send_list"
    assert ex3_facts.FACTS["tools_tasks_for_two_calls"] == len(tools_chunks)  # 2 个 tool_call → 2 个 Send 任务
    assert len(first_turn) == 2  # 本单剧本确实是并行选了 2 个工具


def test_facts_structured_output_node_name() -> None:
    """⑤ response_format=Advice 的装配多一个结构化输出节点——名字要在图节点集里。"""
    agent = _build(_unused_model(), response_format=Advice)
    names = set(agent.get_graph().nodes)
    assert str(ex3_facts.FACTS["structured_node_name"]) in names
    assert names == {"__start__", "__end__", "agent", "tools", str(ex3_facts.FACTS["structured_node_name"])}


def test_facts_out_of_steps_reply_sentinel() -> None:
    """⑥ 预算哨兵：recursion_limit=2 且模型还要调工具时，模型节点替模型回那句固定文案（不再发请求）。"""
    first_turn, _advice_json, _expected = review_rules.script_for("CLM-2026-0001")
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)  # 只给 1 份剧本：哨兵路径不应再请求模型
        agent = _build(_scripted_model(ep))
        result = agent.invoke(
            {"messages": [{"role": "user", "content": "审查 CLM-2026-0001"}]},
            config={"recursion_limit": 2},
        )
        requests = len(ep.requests)
    assert requests == 1
    assert result["messages"][-1].content == ex3_facts.FACTS["out_of_steps_reply"]


def test_facts_unknown_tool_behavior() -> None:
    """⑦ ToolNode 对未注册工具名：回喂 error ToolMessage 而不是 raise（L2.2 纪律的框架版）。"""

    class ToolsState(TypedDict):
        messages: Annotated[list, add_messages]

    builder = StateGraph(ToolsState)
    builder.add_node("tools", ToolNode([mock_tools.check_budget, mock_tools.verify_invoice]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()
    message = AIMessage(content="", tool_calls=[{"name": "no_such_tool", "args": {"x": 1}, "id": "call_bad"}])
    result = graph.invoke({"messages": [message]})  # 若 raise 这里直接炸——事实写错就红
    assert ex3_facts.FACTS["unknown_tool_behavior"] == "feed_back"
    tool_message = result["messages"][-1]
    assert type(tool_message).__name__ == "ToolMessage"
    assert "not a valid tool" in str(tool_message.content)
