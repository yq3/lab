"""解析教学版 dify DSL：节点类型计数、边邻接、找「会停下来的节点」（讲义 Step 2）。

输入是 data/review_workflow.dsl.yaml（按 dify App DSL 格式手工构造的教学样例，
非平台导出；顶层 version/kind/app/workflow 与 graph.nodes/edges 的形状依据
langgenius/dify@79effdd498#api/services/app_dsl_service.py 的 export_dsl()）。

对照 L3.2：langgraph 的 StateGraph 是**代码构图**（Python 函数与条件边），
平台的图是**数据**（YAML 里的 nodes/edges）——所以平台图能离线静态审查，
这一课的全部动手都建立在「图是数据」上。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

LESSON_ROOT = Path(__file__).resolve().parents[1]
DSL_FILE = LESSON_ROOT / "data" / "review_workflow.dsl.yaml"

# 会「停下来等人」的节点类型——平台侧 HITL 的真实类型名（planner_prompts.py 节点表：
# "human-input" — pause for a person to review, approve, or enter data）。
PAUSING_NODE_TYPES = frozenset({"human-input"})


def load_dsl(path: Path = DSL_FILE) -> dict:
    """读 DSL YAML，返回解析后的字典。"""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def graph_of(dsl: dict) -> dict:
    """取 workflow.graph（workflow / advanced-chat 两种 app 模式的图都在这）。"""
    return dsl.get("workflow", {}).get("graph", {})


def node_types(graph: dict) -> Counter[str]:
    """节点类型计数：graph.nodes[*].data.type 的 Counter。"""
    return Counter(str(node.get("data", {}).get("type")) for node in graph.get("nodes", []))


def edge_adjacency(graph: dict) -> dict[str, list[str]]:
    """边邻接表：source -> [target, ...]（graph.edges 每条边有 source/target 两个键）。"""
    adjacency: dict[str, list[str]] = {}
    for edge in graph.get("edges", []):
        adjacency.setdefault(edge["source"], []).append(edge["target"])
    return adjacency


def pausing_nodes(graph: dict) -> list[str]:
    """找会停下来的节点 id（类型在 PAUSING_NODE_TYPES 里，如 human-input）。

    这是平台侧 HITL 的形态：运行到 human-input 节点时工作流暂停、等人填表单
    （paragraph/select/file 输入 + 同意/驳回按钮，按钮 id 就是出边的 sourceHandle），
    提交后沿所选动作边恢复——对照 L3.3 的 interrupt：同一需求的库形态是代码暂停。
    """
    return [
        str(node["id"]) for node in graph.get("nodes", []) if node.get("data", {}).get("type") in PAUSING_NODE_TYPES
    ]


def print_report(dsl: dict) -> None:
    """打印静态审查报告：版本 / 模式 / 类型计数 / 邻接 / 暂停节点。"""
    graph = graph_of(dsl)
    app = dsl.get("app", {})
    print(f"== DSL 静态审查：{app.get('name')} ==")
    print(f"kind={dsl.get('kind')} version={dsl.get('version')} mode={app.get('mode')}")
    print(f"节点类型计数: {dict(node_types(graph))}")
    for source, targets in edge_adjacency(graph).items():
        print(f"  {source} -> {targets}")
    print(f"会停下来的节点（{sorted(PAUSING_NODE_TYPES)}）: {pausing_nodes(graph)}")


if __name__ == "__main__":
    print_report(load_dsl())
