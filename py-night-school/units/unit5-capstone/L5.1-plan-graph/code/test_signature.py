"""讲义区验收（三）：图形状签名的稳定性——同装配双 build 相等、图一改即变。"""

from __future__ import annotations

import re

import demo
import graph
from step2_signature import _mini_graph, topology_signature


def test_same_assembly_yields_same_signature() -> None:
    """同一装配函数两次 build（模型客户端各建各的）：签名必须相等——可复现的指纹。"""
    model = demo.model_for_url("http://127.0.0.1:9/v1")  # 只构造不调用，build 零网络
    first = topology_signature(graph.build_graph(model))
    second = topology_signature(graph.build_graph(model))
    assert first == second


def test_signature_is_sha256_hex() -> None:
    model = demo.model_for_url("http://127.0.0.1:9/v1")
    assert re.fullmatch(r"[0-9a-f]{64}", topology_signature(graph.build_graph(model)))


def test_added_node_changes_signature() -> None:
    """图一改（三节点链 → 四节点链）：签名立刻变——L5.3 图版本绑定依赖的敏感性。"""
    without_archive = topology_signature(_mini_graph(with_archive=False))
    with_archive = topology_signature(_mini_graph(with_archive=True))
    assert without_archive != with_archive
