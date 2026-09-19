"""Step5（可选）：ToolNode 错误回喂——L3.2 手写 tools 节点的框架化对照（零模型调用、零 HTTP）。

L2.2 的纪律：工具层的错误（未知工具名 / 参数校验失败）回喂 error 文本而不是 raise——
错误是给模型的修复指令。ToolNode 把这条纪律做成了参数（handle_tool_errors）。

实测三种输入（输出贴在讲义 §3 Step5）：
1. 未注册的工具名   -> ToolMessage('Error: no_such_tool is not a valid tool, try one of [...]')
2. 参数类型不对     -> ToolMessage('Error invoking tool ... Input should be a valid string')
   （框架把裸函数包成 StructuredTool 时生成了 pydantic 参数校验——L2.2 手写版没有这层）
3. 正常调用         -> 工具真实执行，结果 JSON 回喂（对照 CALL_LOG）

注：ToolNode 是 RunnableCallable，需要图的 runtime 上下文——直接 .invoke 裸状态会报
「Missing required config key」，所以这里把它挂进一张单节点图（也是它的正常用法）。
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

import demo
import mock_tools


class ToolsState(TypedDict):
    messages: Annotated[list, add_messages]


def build_tools_only_graph() -> CompiledStateGraph:
    """单节点图：进一条 AIMessage(tool_calls)，出 N 条 ToolMessage。"""
    builder = StateGraph(ToolsState)
    builder.add_node("tools", ToolNode(demo.TOOL_FUNCS))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    return builder.compile()


def main() -> None:
    print("== Step5 ToolNode 错误回喂（对照 L2.2 纪律 / L3.2 手写 tools 节点） ==")
    graph = build_tools_only_graph()
    cases = [
        (
            "未注册工具名",
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "no_such_tool", "args": {"x": 1}, "id": "call_unknown"},
                ],
            ),
        ),
        (
            "参数类型不对",
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "check_budget", "args": {"dept": 123}, "id": "call_bad_args"},
                ],
            ),
        ),
        (
            "正常调用",
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "check_budget", "args": {"dept": "DEV"}, "id": "call_ok"},
                ],
            ),
        ),
    ]
    mock_tools.CALL_LOG.clear()
    for title, message in cases:
        result = graph.invoke({"messages": [message]})
        tool_message = result["messages"][-1]
        content = str(tool_message.content).replace("\n", " ")
        print(f"[{title}]")
        print(f"  {tool_message.tool_call_id} -> {content[:110]}")
    print(f"CALL_LOG: {mock_tools.CALL_LOG} <- 只有「正常调用」真实执行；前两种回喂 error、不抛异常")


if __name__ == "__main__":
    main()
