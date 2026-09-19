"""讲义区验收：平台能力清单的 meta 检查（覆盖型数据表的判卷先例，L0.1 ex2）。"""

import capabilities


def test_six_dimensions_covered() -> None:
    assert {row["dimension"] for row in capabilities.CAPABILITIES} == {
        "画布编排",
        "HITL 表单",
        "知识库",
        "模型接入",
        "观测与运营",
        "部署形态",
    }


def test_every_row_has_complete_fields() -> None:
    assert len(capabilities.CAPABILITIES) == 6
    for row in capabilities.CAPABILITIES:
        for field in capabilities.FIELDS:
            assert row.get(field), f"{row.get('dimension')} 缺字段 {field}"


def test_counterparts_reference_real_lessons() -> None:
    """库形态对应物必须点名真实课程（防「随便填」）：四框架课至少各出现一次。"""
    joined = " ".join(row["library_counterpart"] for row in capabilities.CAPABILITIES)
    for marker in ("L3.1", "L3.2", "L3.6", "mini-agent"):
        assert marker in joined, f"对应物列没提到 {marker}"
