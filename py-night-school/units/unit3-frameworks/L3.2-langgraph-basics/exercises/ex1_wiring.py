# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""图装配：节点函数与状态已给定，把 reviewer/tools/finalize 连成一张能跑的图。

考察点：add_node / add_edge / add_conditional_edges / START / END / compile——
L2.3 的 `while True + if not tool_calls` 在这里被替换成「回边成环 + 条件边」。
模型是离线替身 FakeChatModel（无 HTTP）；工具是真实的（mock_tools，CALL_LOG 是取证）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——三个测试：
  节点执行序列恰好 [reviewer, tools, reviewer, finalize]（stream 断言）；
  完整跑通：最终回答来自第 2 次模型请求、工具真实执行、回喂的是执行结果；
  未知工具被回喂 error 而不是 raise（节点已给定——装配时别把它绕开）。
TODO 所需的顶部 import：
  from langgraph.graph import END, START, StateGraph
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

import mock_tools

TOOL_FUNCS: dict[str, Callable[..., dict]] = {
    "check_budget": mock_tools.check_budget,
    "verify_invoice": mock_tools.verify_invoice,
}


class LoopState(TypedDict):
    """图状态（demo.ClaimState 的极简版）：messages 合并、final 只由 finalize 写。"""

    messages: Annotated[list, add_messages]
    final: NotRequired[str]  # NotRequired：入口状态没有这个键，第一个写它的节点才让它出现


class FakeChatModel:
    """离线模型替身：按剧本依次回 AIMessage（讲义 mock 端点的迷你版——不发 HTTP，直接返回消息对象）。"""

    def __init__(self, scripts: list[AIMessage]) -> None:
        self._scripts = list(scripts)
        self.request_count = 0

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        self.request_count += 1
        return self._scripts.pop(0)


def build(model: FakeChatModel) -> CompiledStateGraph:
    """装配审查图：START → reviewer →（条件边：最后一条消息有 tool_calls？）→ tools → 回 reviewer；
    无 tool_calls → finalize → END。"""

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
                content = json.dumps(func(**call["args"]), ensure_ascii=False)  # 工具真实执行
            results.append({"role": "tool", "tool_call_id": call["id"], "content": content})
        return {"messages": results}

    def route_after_reviewer(state: LoopState) -> Literal["tools", "finalize"]:
        return "tools" if state["messages"][-1].tool_calls else "finalize"

    async def finalize(state: LoopState) -> dict:
        return {"final": state["messages"][-1].content}

    # TODO(ex1): 用 StateGraph(LoopState) 装配（顶部 import 见文件 docstring）：
    #   add_node 挂三个节点；START 出发到 reviewer；reviewer 之后挂条件边
    #   （path 用 route_after_reviewer，它的返回值就是节点名）；tools 回 reviewer 成环；
    #   finalize 收口到 END；最后 compile() 返回。
    raise NotImplementedError("TODO(ex1): 补全图装配")
