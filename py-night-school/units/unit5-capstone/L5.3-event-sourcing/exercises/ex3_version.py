# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""图版本绑定补全：run_key 组装 + assert_compatible 续跑守门。

考察点：A15「审计绑定版本」——拓扑签名进审计键：run_key 把 (单号, 签名) 合成
聚合键（同图同单稳定，图一改自动换世界）；assert_compatible 是续跑守门（库里记的
版本 ≠ 当前装配的版本 → GraphVersionMismatch，语义是「旧账作废、重开新 run」）。
讲义 code/versioning.py 是同构完整版（对版参照）。guarded_start 给定：它用你的
assert_compatible 把「旧 key 续跑被拒」跑成真流程。

验收口径（与 hints 同源）：
- 同图同 claim 稳定（两次 build 同签名 → 同 run_key）；换单换 key；
- 加/删节点签名变（build_chain 的 archive 开关）→ run_key 跟着变；
- 旧 key 续跑抛 GraphVersionMismatch（异常带 stored/current 双方签名）；
- 新 key 正常（guarded_start 在新聚合上落 run.started）；
- run.started 事件 payload 含 graph_version（demo 集成路径）。

完成判据：uv run pytest exercises/test_ex3.py 全绿——5 个测试。
本文件无需新增 import——TODO 用到的都已预置。
"""

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
    # TODO(ex3): 问：两段怎么拼（中间的分隔符自定，但必须确定）？签名取多长、用哪个切片？
    #   同 (单号, 签名) 必须产出同一个串——这个函数为什么天然可复现？
    raise NotImplementedError("TODO(ex3): run_key")


def assert_compatible(stored_sig: str, current_sig: str) -> None:
    """续跑守门：库里记的版本必须等于当前装配的版本；不等抛 GraphVersionMismatch。"""
    # TODO(ex3): 问：比较什么、不等时抛哪个异常（构造参数是哪两个）？相等时要做什么
    #   （放行的形状是什么——静默通过还是有返回值）？
    raise NotImplementedError("TODO(ex3): assert_compatible")


def guarded_start(store: EventStore, aggregate_id: str, current_sig: str) -> None:
    """（given）带守门的 run.started：聚合已有 run.started 且版本不符 → 拒；否则落事件 #0。

    它只用你的 assert_compatible 与 eventstore.EventStore（讲义区共享件）——
    续跑守门的完整回路在讲义 demo.run_audited 里，这里是可单测的最小版。
    """
    for row in store.events_for(aggregate_id, type="run.started"):
        assert_compatible(row["payload"]["graph_version"], current_sig)
    store.append(aggregate_id, "run.started", {"claim_id": CLAIM, "graph_version": current_sig})
