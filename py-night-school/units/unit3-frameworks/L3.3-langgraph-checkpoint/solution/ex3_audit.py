# 参考答案：ex3（与骨架同构，只填 TODO 区——对照要点见 solution/README.md）
"""恢复后轨迹审计：从 checkpoint 的 state history 重建执行轨迹。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from langgraph.types import Command, StateSnapshot

import demo
import review_rules
from mock_endpoint import MockLLMEndpoint

SENTINELS = ("__start__", "__end__")


@dataclass
class Trajectory:
    nodes_ran: tuple[str, ...]
    paused_at: tuple[str, ...]
    supersteps: int
    interrupt_payload: dict[str, Any] | None


async def pause_claim(db_path: str, claim_id: str = "CLM-2026-0003") -> str:
    thread_id = f"ex3-{claim_id}"
    cfg = demo.thread_config(thread_id)
    first_turn, advice_json, _expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        async with demo.open_saver(db_path) as saver:
            graph = demo.build_graph(demo.model_for_url(ep.url), checkpointer=saver)
            await graph.ainvoke({"messages": demo.initial_messages(claim_id)}, cfg)
    return thread_id


async def resume_claim(db_path: str, thread_id: str, decision: Literal["approve", "deny"]) -> None:
    cfg = demo.thread_config(thread_id)
    with MockLLMEndpoint() as ep:
        async with demo.open_saver(db_path) as saver:
            graph = demo.build_graph(demo.model_for_url(ep.url), checkpointer=saver)
            snapshot = await graph.aget_state(cfg)
            paused = demo.parse_advice_text(snapshot.values["messages"][-1].content)
            if paused is None:
                raise ValueError("暂停点状态里解析不出建议单")
            ep.script_text(demo.post_human_advice(paused, decision).model_dump_json())
            await graph.ainvoke(Command(resume=decision), cfg)


async def fetch_history(db_path: str, thread_id: str) -> list[StateSnapshot]:
    async with demo.open_saver(db_path) as saver:
        graph = demo.build_graph(demo.model_for_url("http://127.0.0.1:1"), checkpointer=saver)
        return [snap async for snap in graph.aget_state_history(demo.thread_config(thread_id))]


def rebuild(snaps: list[StateSnapshot]) -> Trajectory:
    """重建轨迹：相邻快照之间，前者的 next 就是跑过的节点；最后者的 next 是暂停点。"""
    ordered = sorted(snaps, key=lambda snap: (snap.metadata or {}).get("step", -1))
    ran: list[str] = []
    for prev, _cur in zip(ordered, ordered[1:], strict=False):
        ran.extend(node for node in prev.next if node not in SENTINELS)
    last = ordered[-1]
    paused_at = tuple(node for node in last.next if node not in SENTINELS)
    payload = last.interrupts[0].value if paused_at and last.interrupts else None
    return Trajectory(
        nodes_ran=tuple(ran),
        paused_at=paused_at,
        supersteps=(last.metadata or {}).get("step", 0),
        interrupt_payload=payload,
    )
