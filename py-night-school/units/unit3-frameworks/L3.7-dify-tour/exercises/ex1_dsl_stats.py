# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域与所需的顶部 import，其余不要动）
"""DSL 节点统计器：对一份内联的 dify workflow 图做静态审查。

考察点：平台图是数据（nodes/edges 两个列表），图论邻接在这里落地——
类型计数是遍历 nodes 取 data.type；孤立节点检测是「入度+出度都为 0」，
即从未出现在任何一条边的 source 或 target 里的节点（画布上拉出来没接线的节点，
平台运行时永远走不到它——静态审查就能发现，不用起平台）。

图（升级版审查流，与讲义样例不同的拓扑）：start 并行扇出两个 tool 节点、
汇入 llm、if-else 分支到 end；另有 assigner 节点 flag_update 未接线。
共 7 节点 / 6 边。

完成判据：uv run pytest exercises/test_ex1.py 全绿——
  类型计数精确匹配（6 种类型）；计数总和等于节点总数；孤立节点恰好 1 个。
"""

from __future__ import annotations

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
    """统计节点类型：返回 {类型: 个数}。

    类型取每个节点 data.type（dify 平台真实类型名：start / tool / llm / if-else /
    end / assigner / human-input / …）。
    """
    # TODO(ex1): 遍历 graph["nodes"]，按 data.type 累计计数（需要的 import 自补）
    raise NotImplementedError("TODO(ex1): 补全 count_node_types")


def find_orphan_nodes(graph: dict) -> list[str]:
    """找孤立节点：入度与出度都为 0（从未出现在任何边的 source 或 target 里）。

    返回按 id 排序的列表（断言要确定性）。注意：start 没有入边、end 没有出边，
    但它们都不是孤立节点——孤立的定义是「两边都没有」。
    """
    # TODO(ex1): 从 graph["edges"] 折叠出「被边碰过的节点」集合，再从 nodes 里减出孤立者
    raise NotImplementedError("TODO(ex1): 补全 find_orphan_nodes")
