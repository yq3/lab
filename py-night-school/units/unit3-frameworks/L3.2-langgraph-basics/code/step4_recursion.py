"""Step4 recursion_limit：图引擎的硬终止（对照 L2.3 的 max_turns / AgentBudgetExceeded）。

两个最小图，零模型调用：
1) 无限 ping-pong 图：没有出口的环。recursion_limit=6 时跑到第 6 个 superstep
   就抛 GraphRecursionError——确定性硬终止，一个 superstep 都不多跑。
2) 收敛循环图：条件边 count < 3 时继续循环，否则走 END——正常出口是条件边，
   预算只是护栏（双终止：软出口在图里、硬预算在配置里）。

源码证据（延伸路标）：
- langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/errors.py —— GraphRecursionError
- langchain-ai/langchain@348c9dc57#libs/core/langchain_core/runnables/config.py —— 默认 25
"""

from __future__ import annotations

import asyncio
import operator
from typing import Annotated, TypedDict

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph


class PingPongState(TypedDict):
    steps: Annotated[list[str], operator.add]  # 审计流水：数一数实际跑了几个 superstep


def ping(state: PingPongState) -> dict:
    return {"steps": ["ping"]}


def pong(state: PingPongState) -> dict:
    return {"steps": ["pong"]}


def build_pingpong() -> StateGraph:  # type: ignore[type-arg]
    b = StateGraph(PingPongState)
    b.add_node("ping", ping)
    b.add_node("pong", pong)
    b.add_edge(START, "ping")
    b.add_edge("ping", "pong")
    b.add_edge("pong", "ping")  # 成环且无出口：只有预算能停它
    return b


class CountState(TypedDict):
    count: int  # 无 reducer 覆盖：每个节点写「自己算好的新值」
    steps: Annotated[list[str], operator.add]


def tick(state: CountState) -> dict:
    return {"count": state["count"] + 1, "steps": ["tick"]}  # 读旧值算新值——无 reducer 的纪律


def route_by_count(state: CountState) -> str:
    """条件边返回 END 哨兵 = 正常出口（返回值既可以是节点名，也可以是 END）。"""
    return "tick" if state["count"] < 3 else END


def build_counter() -> StateGraph:  # type: ignore[type-arg]
    b = StateGraph(CountState)
    b.add_node("tick", tick)
    b.add_edge(START, "tick")
    b.add_conditional_edges("tick", route_by_count)  # 自环：条件边指回自己
    return b


async def main() -> None:
    print("== Step4 recursion_limit：图引擎的硬终止 ==")

    print("[无限 ping-pong 图，recursion_limit=6]")
    graph = build_pingpong().compile()
    executed: list[str] = []
    try:
        async for chunk in graph.astream({"steps": []}, config={"recursion_limit": 6}, stream_mode="updates"):
            executed.extend(chunk.keys())
    except GraphRecursionError as e:
        print(f"  {type(e).__name__}: {e}")
        print(f"  实际执行 superstep 数: {len(executed)}（{'/'.join(executed)}）——预算烧满即停，一个不多")
        print("  对照 L2.3: AgentBudgetExceeded('5 轮预算耗尽')——同一条纪律换成了图引擎的配置项")
    print("  默认 recursion_limit=25（langchain_core 的 DEFAULT_RECURSION_LIMIT）——生产图应显式给，")
    print("  demo.py 的 run_review 里 config={'recursion_limit': 8} 就是这句话的落地。")

    r2 = await build_counter().compile().ainvoke({"count": 0, "steps": []})
    print("[收敛循环图：条件边 count<3 继续，否则 END]")
    print(f"  正常结束: count={r2['count']}, steps={r2['steps']}——正常出口是条件边，预算只是护栏")


if __name__ == "__main__":
    asyncio.run(main())
