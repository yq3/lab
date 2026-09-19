"""Step1 checkpointer 实验：给图装记忆——同一 thread_id 的两段对话（A/B 对照）。

最小图（零工具、零 HTTP）：START → chat → END，chat 把消息史发给 FakeChatModel
（直接数自己每次收到几条消息——证据比打印更硬）。三组观察：

A. 无 checkpointer：两段各自为政——第二段完全不知道第一段说过什么；
B. compile(checkpointer=AsyncSqliteSaver(...)) + 同一 thread_id：第二段进来时，
   第一段的 user+assistant 从 sqlite 恢复——模型一次看到 3 条消息；
   换个 thread_id 再问：又只剩 1 条——thread_id 是会话边界（隔离）。

B 的两段刻意用两个先后打开的 saver 连接跑（图实例也是两个）——内存里没有任何
共享变量，「记忆」只能来自 db 文件。这是 Step2 跨进程恢复的预演。
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

import demo


class ChatState(TypedDict):
    """单键状态：messages 合并语义（L3.2 §2.3 的纪律在这里就是「记忆」的载体）。"""

    messages: Annotated[list, add_messages]


class FakeChat:
    """离线模型替身：记录每次请求看到的消息条数，回一条自曝家底的回答。"""

    def __init__(self) -> None:
        self.seen: list[int] = []

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        self.seen.append(len(messages))
        return AIMessage(content=f"（我看到了 {len(messages)} 条历史）")


def build_chat(model: FakeChat) -> StateGraph:  # type: ignore[type-arg]
    builder = StateGraph(ChatState)

    async def chat(state: ChatState) -> dict:
        reply = await model.ainvoke(state["messages"])
        return {"messages": [reply]}

    builder.add_node("chat", chat)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    return builder


SEGMENT_1 = "报销单 CLM-2026-0001 是哪个部门的？"
SEGMENT_2 = "它还剩多少预算？"
SEGMENT_3 = "新会话：报一下你自己。"


async def control_without_checkpointer() -> list[int]:
    """对照组 A：普通 compile()——图跑完即忘。"""
    model = FakeChat()
    graph = build_chat(model).compile()
    await graph.ainvoke({"messages": [("user", SEGMENT_1)]})
    await graph.ainvoke({"messages": [("user", SEGMENT_2)]})
    return model.seen


async def treatment_with_checkpointer(db: str) -> tuple[list[int], int, int]:
    """实验组 B：两个 saver 连接 + 两个图实例，同一个 db 文件、同一个 thread_id。"""
    model = FakeChat()
    cfg = demo.thread_config("mem-demo")  # thread_id 是唯一要带的钥匙
    async with demo.open_saver(db) as saver:  # 连接 1：第一段
        graph1 = build_chat(model).compile(checkpointer=saver)
        await graph1.ainvoke({"messages": [("user", SEGMENT_1)]}, cfg)
    async with demo.open_saver(db) as saver:  # 连接 2：第二段（图和连接都是新的）
        graph2 = build_chat(model).compile(checkpointer=saver)
        await graph2.ainvoke({"messages": [("user", SEGMENT_2)]}, cfg)
        await graph2.ainvoke({"messages": [("user", SEGMENT_3)]}, demo.thread_config("mem-other"))
        snapshot_main = await graph2.aget_state(cfg)
        snapshot_other = await graph2.aget_state(demo.thread_config("mem-other"))
    return model.seen, len(snapshot_main.values["messages"]), len(snapshot_other.values["messages"])


async def main() -> None:
    print("== Step1 checkpointer：给图装记忆（FakeChat 直接数每次看到几条消息） ==")
    control = await control_without_checkpointer()
    print("[A 对照：无 checkpointer，两段对话]")
    print(f"  第 1 段模型看到 {control[0]} 条；第 2 段模型看到 {control[1]} 条 <- 跑完即忘")
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "mem.sqlite3")
        seen, mem_len, other_len = await treatment_with_checkpointer(db)
        size = Path(db).stat().st_size
        print("[B 实验：compile(checkpointer=...)，两段各自新开 saver/图实例]")
        print(f"  第 1 段模型看到 {seen[0]} 条；第 2 段模型看到 {seen[1]} 条 <- 第一段的对话从 db 回来了")
        print(f"  换 thread_id 再问：模型看到 {seen[2]} 条 <- 会话隔离，thread_id 是边界")
        print(f"  快照 messages 共 {mem_len} 条（两问两答）；另一 thread 自己 {other_len} 条（一问一答）")
        print(f"  sqlite 文件 {size} 字节——图的执行状态整只躺在里面，进程死活与它无关")


if __name__ == "__main__":
    asyncio.run(main())
