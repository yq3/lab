# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""checkpointer 接线：给一张单节点对话图装上跨实例记忆。

考察点：compile(checkpointer=...) 的接线位置；thread_id 怎么经 config 传给 invoke；
「杀进程」的等价模拟——两个函数各自打开 saver、各自 compile 出自己的图实例，
共享的只有 db 文件路径。model.seen 记录每次模型请求看到几条消息（证据）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——三个测试：
  同一 thread_id 第二段能看到第一段的历史（seen == [1, 3]）；
  换 thread_id 的新会话从零开始（seen == [1, 3, 1]）；
  两段结束后 db 里的状态：主 thread 4 条消息（两问两答）、另一 thread 2 条。
TODO 所需的顶部 import：import demo（open_saver / thread_config 都在它名下）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class ChatState(TypedDict):
    """单键状态：messages 合并语义——「记忆」的载体（讲义 Step1 同款）。"""

    messages: Annotated[list, add_messages]


class CountingChat:
    """离线模型替身：记录每次请求看到的消息条数，回一条回声。"""

    def __init__(self) -> None:
        self.seen: list[int] = []

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        self.seen.append(len(messages))
        return AIMessage(content="回声")


def build_chat(model: CountingChat) -> StateGraph:  # type: ignore[type-arg]
    """装配单节点对话图（给定）：START → chat → END。"""

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
    # TODO(ex1): 打开 saver（demo.open_saver(db_path)，异步上下文管理器）→
    #   build_chat(model).compile(...) 把 saver 接进去 → ainvoke 发 SEGMENT_1，
    #   config 用 demo.thread_config(thread_id)（thread_id 是取货凭证）
    raise NotImplementedError("TODO(ex1): 补全第一段对话的 checkpointer 接线")


async def second_segment(db_path: str, thread_id: str, other_thread: str, model: CountingChat) -> None:
    """「进程 2」（等价于杀掉进程 1 后重启）：新 saver 连接 + 新图实例，同一个 db 文件。

    先用同一个 thread_id 追问 SEGMENT_2（应看到第一段的历史），
    再用 other_thread 发 SEGMENT_3（新会话，从零开始）。
    """
    # TODO(ex1): 与 first_segment 同样的接线（新开 saver、重新 compile），
    #   连续两次 ainvoke：先 SEGMENT_2 配 thread_id，再 SEGMENT_3 配 other_thread
    raise NotImplementedError("TODO(ex1): 补全第二段对话与隔离对照")
