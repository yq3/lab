# 参考答案：ex3_gate（练习文件的完整解法——完成前别看）
"""subgraph 改造：模型 + 工具打包成子图，外层 precheck 拦非法单号直接短路。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import SecretStr

import demo
import mock_tools
from advice import Advice


class ReviewState(TypedDict):
    messages: Annotated[list, add_messages]
    advice: NotRequired[Advice]


class GateState(TypedDict):
    claim_id: str
    messages: Annotated[list, add_messages]
    advice: NotRequired[Advice]


def make_reviewer(model: Runnable):
    async def reviewer(state: ReviewState) -> dict:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response]}

    return reviewer


async def tools_node(state: ReviewState) -> dict:
    tool_funcs: dict[str, Callable[..., dict]] = dict(demo.TOOL_REGISTRY)
    results: list[dict] = []
    for call in state["messages"][-1].tool_calls:
        func = tool_funcs.get(call["name"])
        if func is None:
            content = json.dumps({"error": f"unknown_tool: {call['name']}"}, ensure_ascii=False)
        else:
            content = json.dumps(func(**call["args"]), ensure_ascii=False)
        results.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    return {"messages": results}


def route_after_reviewer(state: ReviewState) -> Literal["tools", "finalize"]:
    return "tools" if state["messages"][-1].tool_calls else "finalize"


async def finalize(state: ReviewState) -> dict:
    return {"advice": Advice.model_validate_json(state["messages"][-1].content.strip())}


async def precheck(state: GateState) -> dict:
    return {}  # 路由判断在条件边函数里；本节点是挂条件边的锚点


def route_after_precheck(state: GateState) -> Literal["review", "deny"]:
    known = any(claim["id"] == state["claim_id"] for claim in mock_tools.claims_table())
    return "review" if known else "deny"


async def deny(state: GateState) -> dict:
    return {
        "advice": Advice(
            claim_id=state["claim_id"],
            decision="ESCALATE",
            reason="REJECT:CLAIM_NOT_FOUND",
            remaining_cents=0,
        )
    }


def model_for(url: str) -> Runnable:
    return ChatOpenAI(
        base_url=url, api_key=SecretStr("test-key"), model="mock-model", max_retries=0, timeout=10
    ).bind_tools(list(demo.TOOL_REGISTRY.values()))


def initial_messages(claim_id: str) -> list[dict]:
    return [
        {"role": "system", "content": demo.SYSTEM_PROMPT},
        {"role": "user", "content": f"请审查报销单 {claim_id}。"},
    ]


def build_review_subgraph(model: Runnable) -> CompiledStateGraph:
    builder = StateGraph(ReviewState)
    builder.add_node("reviewer", make_reviewer(model))
    builder.add_node("tools", tools_node)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "reviewer")
    builder.add_conditional_edges("reviewer", route_after_reviewer)
    builder.add_edge("tools", "reviewer")
    builder.add_edge("finalize", END)
    return builder.compile()


def build_gate(model: Runnable) -> CompiledStateGraph:
    builder = StateGraph(GateState)
    builder.add_node("precheck", precheck)
    builder.add_node("review", build_review_subgraph(model))  # 图即节点：编译产物直接挂
    builder.add_node("deny", deny)
    builder.add_edge(START, "precheck")
    builder.add_conditional_edges("precheck", route_after_precheck)
    builder.add_edge("review", END)
    builder.add_edge("deny", END)
    return builder.compile()
