"""Step2 图形状签名：topology_signature(graph) -> sha256（讲义 §3 用，L5.3 直接复用）。

静态拓扑的「可审计」落到实处：图形状（节点集 + 边集）序列化后哈希——
同一次装配两次 build 签名相等；图一改（哪怕只加一个节点）签名立刻变。
出处对版：report.md A15「审计绑定版本：图形状签名进 checkpoint key（改图自动作废
旧执行态）」——L5.3 事件溯源的图版本绑定直接 import 本函数，不另起炉灶。

序列化口径（确定性）：节点名排序；边按 (source, target, 是否条件边) 排序；
节点/边的「函数体内容」不进签名——签的是拓扑形状，不是实现。
"""

from __future__ import annotations

import hashlib
import json
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

import demo
import graph


def topology_signature(compiled: CompiledStateGraph) -> str:
    """图形状签名：节点名 + 边（source/target/条件性）排序序列化后 sha256。"""
    drawable = compiled.get_graph()
    nodes = sorted(drawable.nodes)  # get_graph 的 nodes 是 {id: Node}，__start__/__end__ 在内
    edges = sorted((edge.source, edge.target, "cond" if edge.conditional else "edge") for edge in drawable.edges)
    payload = json.dumps({"nodes": nodes, "edges": [list(edge) for edge in edges]}, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---- 对照组：最小图（零模型零数据，只看形状）----


class MiniState(TypedDict):
    trail: Annotated[list[str], operator.add]


def _emit(name: str):
    def node(state: MiniState) -> dict:
        return {"trail": [name]}

    return node


def _mini_graph(with_archive: bool) -> CompiledStateGraph:
    """三节点链 vs 四节点链：加一个 archive 节点——形状差一，签名全变。"""
    builder = StateGraph(MiniState)
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


def main() -> None:
    print("== Step2 图形状签名：拓扑可 diff、可锁定 ==")

    model = demo.model_for_url("http://127.0.0.1:9/v1")  # 只构造不调用——build 不发任何请求
    sig_a = topology_signature(graph.build_graph(model))
    sig_b = topology_signature(graph.build_graph(model))
    print("[1] 本课图：同一装配函数、两次 build")
    print(f"  签名相等: {sig_a == sig_b}（sha256 前 16 位 {sig_a[:16]}…）")

    print("[2] 图一改：drafter 与 submit 之间加一个 archive 节点（最小对照图）")
    sig_c = topology_signature(_mini_graph(with_archive=True))
    sig_d = topology_signature(_mini_graph(with_archive=False))
    print(f"  三节点链 vs 四节点链签名相等: {sig_c == sig_d}（{sig_d[:16]}… vs {sig_c[:16]}…）")
    print("  <- L5.3 的图版本绑定就用这把锁：改图自动作废旧执行态（A15），不用人肉对版本号")

    print("[3] 本课图的节点/边规模（签名覆盖的全部内容）")
    drawable = graph.build_graph(model).get_graph()
    print(f"  节点: {sorted(drawable.nodes)}")
    print(f"  边数: {len(drawable.edges)}（含条件边三分支与 START/END 哨兵）")


if __name__ == "__main__":
    main()
