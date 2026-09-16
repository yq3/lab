# 参考答案：ex1_wiring（练习文件的完整解法——完成前别看）
"""图装配：节点函数与状态已给定，把 reviewer/tools/finalize 连成一张能跑的图。"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

import mock_tools

TOOL_FUNCS: dict[str, Callable[..., dict]] = {
    "check_budget": mock_tools.check_budget,
    "verify_invoice": mock_tools.verify_invoice,
}


class LoopState(TypedDict):
    messages: Annotated[list, add_messages]
    final: NotRequired[str]


class FakeChatModel:
    """离线模型替身：按剧本依次回 AIMessage。"""

    def __init__(self, scripts: list[AIMessage]) -> None:
        self._scripts = list(scripts)
        self.request_count = 0

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        self.request_count += 1
        return self._scripts.pop(0)


def build(model: FakeChatModel) -> CompiledStateGraph:
    """装配审查图：START → reviewer →（条件边）→ tools → 回 reviewer；无 tool_calls → finalize → END。"""

    async def reviewer(state: LoopState) -> dict:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response]}

    async def tools_node(state: LoopState) -> dict:
        results: list[dict] = []
        for call in state["messages"][-1].tool_calls:
            func = TOOL_FUNCS.get(call["name"])
            if func is None:
                content = json.dumps({"error": f"unknown_tool: {call['name']}"}, ensure_ascii=False)
            else:
                content = json.dumps(func(**call["args"]), ensure_ascii=False)
            results.append({"role": "tool", "tool_call_id": call["id"], "content": content})
        return {"messages": results}

    def route_after_reviewer(state: LoopState) -> Literal["tools", "finalize"]:
        return "tools" if state["messages"][-1].tool_calls else "finalize"

    async def finalize(state: LoopState) -> dict:
        return {"final": state["messages"][-1].content}

    builder = StateGraph(LoopState)
    builder.add_node("reviewer", reviewer)
    builder.add_node("tools", tools_node)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "reviewer")
    builder.add_conditional_edges("reviewer", route_after_reviewer)
    builder.add_edge("tools", "reviewer")  # 回边成环：ReAct 循环的图形态
    builder.add_edge("finalize", END)
    return builder.compile()
