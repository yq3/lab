"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import pytest
from pydantic import ValidationError

from ex3_batch import ClaimItem, WeeklyBatch


def test_ex3_dump_structure_is_exact() -> None:
    """验收主判据：model_dump 的输出结构逐键断言。"""
    batch = WeeklyBatch.from_lines("RPT-2026-W37", "王工", ["餐饮|3500", "交通|1200"])
    assert batch.model_dump() == {
        "report_id": "RPT-2026-W37",
        "submitted_by": "王工",
        "items": [
            {"category": "餐饮", "amount_cents": 3500},
            {"category": "交通", "amount_cents": 1200},
        ],
    }


def test_ex3_items_are_real_models() -> None:
    batch = WeeklyBatch.from_lines("RPT-2026-W37", "王工", ["餐饮|3500"])
    assert isinstance(batch.items[0], ClaimItem)  # 嵌套元素是模型实例，不是 dict
    assert batch.items[0].amount_cents == 3500


def test_ex3_report_id_pattern_enforced() -> None:
    # 直接构造与经 from_lines 构造，非法 report_id 都要在「构造那一刻」被拒
    with pytest.raises(ValidationError):
        WeeklyBatch(report_id="bad", submitted_by="王工")
    with pytest.raises(ValidationError):
        WeeklyBatch.from_lines("RPT-2026-W99X", "王工", [])  # W 后必须恰好两位数字


@pytest.mark.parametrize(
    "line",
    [
        "餐饮|-100",  # 金额为负：ClaimItem 的 gt=0 在构造时拒
        "|3500",  # 类目为空：min_length 拒
    ],
)
def test_ex3_bad_values_rejected_as_validation_error(line: str) -> None:
    with pytest.raises(ValidationError):
        WeeklyBatch.from_lines("RPT-2026-W37", "王工", [line])


def test_ex3_malformed_line_raises_value_error() -> None:
    # 没有 "|" 的行拆不出两段：split 解包的 ValueError 自然抛出（不包装、不吞）
    with pytest.raises(ValueError):
        WeeklyBatch.from_lines("RPT-2026-W37", "王工", ["餐饮3500"])


def test_ex3_from_lines_is_a_classmethod() -> None:
    # 类上直接调用（不需要实例）——Java 静态工厂的调用形态
    assert WeeklyBatch.from_lines("RPT-2026-W37", "王工", []).items == []
