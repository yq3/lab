"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import ex1_dsl_stats as ex1


def test_count_node_types_exact() -> None:
    counts = ex1.count_node_types(ex1.GRAPH)
    assert counts == {
        "start": 1,
        "tool": 2,
        "llm": 1,
        "if-else": 1,
        "end": 1,
        "assigner": 1,
    }


def test_counts_sum_equals_node_total() -> None:
    """meta：计数没丢节点——各类型之和等于节点总数（7 个）。"""
    counts = ex1.count_node_types(ex1.GRAPH)
    assert sum(counts.values()) == len(ex1.GRAPH["nodes"]) == 7


def test_orphan_nodes() -> None:
    assert ex1.find_orphan_nodes(ex1.GRAPH) == ["flag_update"]
