"""讲义区验收：dsl_reader.py 对教学 DSL 样例的静态审查（不要改本文件——判卷口径）。"""

import dsl_reader


def test_top_level_envelope_is_app_dsl() -> None:
    dsl = dsl_reader.load_dsl()
    assert dsl["kind"] == "app"
    assert dsl["version"] == "0.7.0"  # 与 dify api/constants/dsl_version.py 的 CURRENT_APP_DSL_VERSION 一致
    assert dsl["app"]["mode"] == "workflow"


def test_node_type_counts() -> None:
    counts = dsl_reader.node_types(dsl_reader.graph_of(dsl_reader.load_dsl()))
    assert dict(counts) == {
        "start": 1,
        "knowledge-retrieval": 1,
        "llm": 1,
        "human-input": 1,
        "end": 2,
        "code": 1,
    }


def test_edge_adjacency_and_fan_out() -> None:
    adjacency = dsl_reader.edge_adjacency(dsl_reader.graph_of(dsl_reader.load_dsl()))
    assert adjacency["start"] == ["policy_kb"]
    assert adjacency["precheck"] == ["review"]
    assert adjacency["review"] == ["end_ok", "end_reject"]  # 人工复核节点扇出两条动作边


def test_pausing_nodes_are_human_input() -> None:
    assert dsl_reader.pausing_nodes(dsl_reader.graph_of(dsl_reader.load_dsl())) == ["review"]


def test_user_action_ids_are_edge_source_handles() -> None:
    """源码事实（human_input/entities.py）：user_actions 的 id 同时是输出把手——
    出边的 sourceHandle 集合 == 按钮动作 id 集合。"""
    graph = dsl_reader.graph_of(dsl_reader.load_dsl())
    review = next(n for n in graph["nodes"] if n["id"] == "review")
    action_ids = {a["id"] for a in review["data"]["user_actions"]}
    handles = {e["sourceHandle"] for e in graph["edges"] if e["source"] == "review"}
    assert action_ids == handles == {"approve", "reject"}
