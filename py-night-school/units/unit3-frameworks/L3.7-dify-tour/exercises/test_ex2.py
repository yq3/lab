"""练习 2 验收（meta-test，L0.1 ex2 先例：清单表本身是被测数据；不要改本文件）。

四个测试：必须维度齐全 / 字段完整且无 TODO 占位 / 每行对应物点名真实课程或诚实写「无」/
行数与维度唯一性。防「删行偷懒」与「留空过关」。
"""

import ex2_capabilities as ex2

ALLOWED_MARKERS = (
    "mini-agent",
    "L3.1",
    "L3.2",
    "L3.3",
    "L3.4",
    "langgraph",
    "L3.5",
    "deepagents",
    "L3.6",
    "adk",
    "无",
)
REQUIRED_DIMENSIONS = {"画布编排", "HITL 表单", "知识库", "模型接入", "观测与运营", "部署形态"}


def test_six_required_dimensions_present() -> None:
    dims = {row["dimension"] for row in ex2.CAPABILITIES}
    missing = REQUIRED_DIMENSIONS - dims
    assert not missing, f"清单缺维度: {missing}"


def test_every_row_complete_and_no_todo_placeholder() -> None:
    for row in ex2.CAPABILITIES:
        for field in ex2.FIELDS:
            value = row.get(field, "")
            assert value, f"[{row.get('dimension')}] 字段 {field} 为空"
            assert "TODO" not in value, f"[{row.get('dimension')}] 字段 {field} 还留着 TODO 占位"


def test_counterpart_names_real_marker_per_row() -> None:
    """对应物列必须点名真实课程（或诚实写「无」）——空话、形容词堆砌过不了。"""
    for row in ex2.CAPABILITIES:
        counterpart = row["library_counterpart"]
        assert any(marker in counterpart for marker in ALLOWED_MARKERS), (
            f"[{row['dimension']}] 对应物没提到任何课程标记或「无」: {counterpart}"
        )


def test_at_least_seven_rows_unique_dimensions() -> None:
    dims = [row["dimension"] for row in ex2.CAPABILITIES]
    assert len(dims) >= 7, "六行之外至少还要有你自己的一行"
    assert len(dims) == len(set(dims)), f"维度重复: {dims}"
