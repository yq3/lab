# 练习 3 参考答案（solution/ 不进学员主线视野；先完成练习再回来对照）
"""图版本绑定补全：run_key 组装 + assert_compatible 续跑守门。"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from eventstore import EventStore

CLAIM = "CLM-2026-0001"


class ChainState(TypedDict):
    """最小链状图的状态（given）：只带一条留痕 reducer。"""

    trail: Annotated[list[str], operator.add]


def _emit(name: str):
    def node(state: ChainState) -> dict:
        return {"trail": [name]}

    return node


def build_chain(with_archive: bool) -> CompiledStateGraph:
    """（given）三节点链 vs 四节点链：archive 开关就是「改图」的最小实验台。"""
    builder = StateGraph(ChainState)
    builder.add_node("intake", _emit("intake"))
    builder.add_node("drafter", _emit("drafter"))
    if with_archive:
        builder.add_node("archive", _emit("archive"))
    builder.add_node("submit", _emit("submit"))
    builder.add_edge(START, "intake")
    builder.add_edge("intake", "drafter")
    if with_archive:
        builder.add_edge("drafter", "archive")
        builder.add_edge("archive", "submit")
    else:
        builder.add_edge("drafter", "submit")
    builder.add_edge("submit", END)
    return builder.compile()


class GraphVersionMismatch(RuntimeError):
    """续跑时的图版本不符——旧执行态作废（不是报错完蛋：重开新 run 就是了）。"""

    def __init__(self, stored: str, current: str) -> None:
        self.stored = stored
        self.current = current
        super().__init__(f"graph version mismatch: stored={stored[:12]}… current={current[:12]}…")


def run_key(aggregate_id: str, signature: str) -> str:
    """聚合键：单号 + 签名前 12 位（可读性截断；全签名在 run.started payload 里留档）。"""
    return f"{aggregate_id}@{signature[:12]}"


def assert_compatible(stored_sig: str, current_sig: str) -> None:
    """续跑守门：库里记的版本必须等于当前装配的版本；不等抛 GraphVersionMismatch。"""
    if stored_sig != current_sig:
        raise GraphVersionMismatch(stored_sig, current_sig)  # 相等时静默放行


def guarded_start(store: EventStore, aggregate_id: str, current_sig: str) -> None:
    """（given）带守门的 run.started：聚合已有 run.started 且版本不符 → 拒；否则落事件 #0。

    它只用你的 assert_compatible 与 eventstore.EventStore（讲义区共享件）——
    续跑守门的完整回路在讲义 demo.run_audited 里，这里是可单测的最小版。
    """
    for row in store.events_for(aggregate_id, type="run.started"):
        assert_compatible(row["payload"]["graph_version"], current_sig)
    store.append(aggregate_id, "run.started", {"claim_id": CLAIM, "graph_version": current_sig})
