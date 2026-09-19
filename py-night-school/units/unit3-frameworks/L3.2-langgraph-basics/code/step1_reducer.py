"""Step1 状态 schema 与 reducer：同一张图里「覆盖」与「合并」两种语义的最小对照。

两个最小图，零模型调用：
1) 顺序图 START → a → b → END：无 reducer 的 note 被 b 静默覆盖；
   带 Annotated reducer 的 trail 逐步合并——这正是 messages 能 append-only 的原因。
2) 并行图 START → a ∥ b → sink → END：无 reducer 的 note 在同一 superstep 被写两次，
   langgraph 拒绝（InvalidUpdateError，源码见 channels/last_value.py 的 update）；
   只有 reducer 键的并行图则安然合并。

源码证据（延伸路标）：
- langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/channels/last_value.py —— LastValue.update
- langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/channels/binop.py —— BinaryOperatorAggregate.update
"""

from __future__ import annotations

import asyncio
import operator
from typing import Annotated, TypedDict

from langgraph.errors import InvalidUpdateError
from langgraph.graph import END, START, StateGraph


class NoteState(TypedDict):
    note: str  # 无 reducer：默认 LastValue 通道——「谁后写谁赢」的覆盖语义
    trail: Annotated[list[str], operator.add]  # 有 reducer：BinaryOperatorAggregate——合并语义


class TrailOnlyState(TypedDict):
    trail: Annotated[list[str], operator.add]


def speak_a(state: NoteState) -> dict:
    return {"note": "节点A写的", "trail": ["a"]}


def speak_b(state: NoteState) -> dict:
    return {"note": "节点B写的", "trail": ["b"]}


def write_left(state: NoteState) -> dict:
    return {"note": "左边写的", "trail": ["left"]}


def write_right(state: NoteState) -> dict:
    return {"note": "右边写的", "trail": ["right"]}


def merge_left(state: TrailOnlyState) -> dict:
    return {"trail": ["left"]}


def merge_right(state: TrailOnlyState) -> dict:
    return {"trail": ["right"]}


def noop(state: NoteState | TrailOnlyState) -> dict:
    return {}  # 空更新是合法的：这个节点只做 fan-in 的汇合点


def build_sequential() -> StateGraph:  # type: ignore[type-arg]
    b = StateGraph(NoteState)
    b.add_node("a", speak_a)
    b.add_node("b", speak_b)
    b.add_edge(START, "a")
    b.add_edge("a", "b")
    b.add_edge("b", END)
    return b


def build_parallel(state_cls: type, left, right) -> StateGraph:  # type: ignore[type-arg,no-untyped-def]
    b = StateGraph(state_cls)  # type: ignore[arg-type]
    b.add_node("left", left)
    b.add_node("right", right)
    b.add_node("sink", noop)
    b.add_edge(START, "left")
    b.add_edge(START, "right")
    b.add_edge(["left", "right"], "sink")  # fan-in：等两个上游都完成才走 sink
    b.add_edge("sink", END)
    return b


async def main() -> None:
    print("== Step1 覆盖 vs 合并（零模型调用） ==")

    r1 = await build_sequential().compile().ainvoke({"note": "入口", "trail": []})
    print("[顺序图 START→a→b→END]")
    print(f"  note  = {r1['note']!r}  <- 无 reducer：b 静默覆盖 a（LastValue.update 取 values[-1]）")
    print(f"  trail = {r1['trail']!r}   <- 有 reducer：operator.add 逐次合并")

    print("[并行图 START→left∥right→sink，left/right 都写 note]")
    try:
        await build_parallel(NoteState, write_left, write_right).compile().ainvoke({"note": "入口", "trail": []})
        print("  意外：没有报错？")
    except InvalidUpdateError as e:
        print(f"  InvalidUpdateError: {str(e).splitlines()[0]}")
        print("  <- 同一 superstep 双写无 reducer 键被拒绝；带 reducer 的键本可以安然合并")

    r3 = await build_parallel(TrailOnlyState, merge_left, merge_right).compile().ainvoke({"trail": []})
    print("[并行图（只留 trail 键）]")
    print(f"  trail = {r3['trail']!r} <- 并行写 + reducer = 合并——L3.4 的 Send 扇出靠的就是这个语义")


if __name__ == "__main__":
    asyncio.run(main())
