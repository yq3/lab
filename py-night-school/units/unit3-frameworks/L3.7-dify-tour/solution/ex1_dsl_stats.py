# 练习 1 参考答案（solution 覆盖版：函数体补全，given 部分与练习骨架逐字一致）
"""DSL 节点统计器：对一份内联的 dify workflow 图做静态审查。

考察点：平台图是数据（nodes/edges 两个列表），图论邻接在这里落地——
类型计数是遍历 nodes 取 data.type；孤立节点检测是「入度+出度都为 0」，
即从未出现在任何一条边的 source 或 target 里的节点（画布上拉出来没接线的节点，
平台运行时永远走不到它——静态审查就能发现，不用起平台）。

图（升级版审查流，与讲义样例不同的拓扑）：start 并行扇出两个 tool 节点、
汇入 llm、if-else 分支到 end；另有 assigner 节点 flag_update 未接线。
共 7 节点 / 6 边。
"""

from __future__ import annotations

from collections import Counter

GRAPH: dict = {
    "nodes": [
        {"id": "start", "data": {"type": "start", "title": "开始"}},
        {"id": "tool_check_budget", "data": {"type": "tool", "title": "查预算"}},
        {"id": "tool_verify_invoice", "data": {"type": "tool", "title": "验发票"}},
        {"id": "precheck", "data": {"type": "llm", "title": "预审"}},
        {"id": "branch", "data": {"type": "if-else", "title": "按规则分支"}},
        {"id": "final", "data": {"type": "end", "title": "出口"}},
        {"id": "flag_update", "data": {"type": "assigner", "title": "回写标记（未接线）"}},
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "tool_check_budget"},
        {"id": "e2", "source": "start", "target": "tool_verify_invoice"},
        {"id": "e3", "source": "tool_check_budget", "target": "precheck"},
        {"id": "e4", "source": "tool_verify_invoice", "target": "precheck"},
        {"id": "e5", "source": "precheck", "target": "branch"},
        {"id": "e6", "source": "branch", "target": "final", "sourceHandle": "true"},
    ],
}


def count_node_types(graph: dict) -> dict[str, int]:
    """统计节点类型：返回 {类型: 个数}。"""
    return dict(Counter(node["data"]["type"] for node in graph["nodes"]))


def find_orphan_nodes(graph: dict) -> list[str]:
    """找孤立节点：入度与出度都为 0（从未出现在任何边的 source 或 target 里）。"""
    touched: set[str] = set()
    for edge in graph["edges"]:
        touched.add(edge["source"])
        touched.add(edge["target"])
    return sorted(node["id"] for node in graph["nodes"] if node["id"] not in touched)
