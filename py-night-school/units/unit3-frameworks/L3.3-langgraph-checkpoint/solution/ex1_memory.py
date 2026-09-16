# 参考答案：ex1（与骨架同构，只填 TODO 区——对照要点见 solution/README.md）
"""checkpointer 接线：给一张单节点对话图装上跨实例记忆。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

import demo


class ChatState(TypedDict):
    messages: Annotated[list, add_messages]


class CountingChat:
    def __init__(self) -> None:
        self.seen: list[int] = []

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        self.seen.append(len(messages))
        return AIMessage(content="回声")


def build_chat(model: CountingChat) -> StateGraph:  # type: ignore[type-arg]
    async def chat(state: ChatState) -> dict:
        reply = await model.ainvoke(state["messages"])
        return {"messages": [reply]}

    builder = StateGraph(ChatState)
    builder.add_node("chat", chat)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    return builder


SEGMENT_1 = "报销单 CLM-2026-0001 是哪个部门的？"
SEGMENT_2 = "它还剩多少预算？"
SEGMENT_3 = "新会话：报一下你自己。"


async def first_segment(db_path: str, thread_id: str, model: CountingChat) -> None:
    """「进程 1」：第一段对话。"""
    async with demo.open_saver(db_path) as saver:
        graph = build_chat(model).compile(checkpointer=saver)
        await graph.ainvoke({"messages": [("user", SEGMENT_1)]}, demo.thread_config(thread_id))


async def second_segment(db_path: str, thread_id: str, other_thread: str, model: CountingChat) -> None:
    """「进程 2」：新 saver 连接 + 新图实例，同一个 db 文件。"""
    async with demo.open_saver(db_path) as saver:
        graph = build_chat(model).compile(checkpointer=saver)
        await graph.ainvoke({"messages": [("user", SEGMENT_2)]}, demo.thread_config(thread_id))
        await graph.ainvoke({"messages": [("user", SEGMENT_3)]}, demo.thread_config(other_thread))
