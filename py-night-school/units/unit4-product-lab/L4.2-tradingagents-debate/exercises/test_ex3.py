"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import json
from typing import get_args

import pytest

import ex3_sentinel as ex3


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("N/A", None),  # 占位串
        ("none", None),  # 占位串（大小写不敏感）
        ("85%", None),  # 百分比绝不冒充金额
        ("¥1,234.50", None),  # 带小数货币串：整数分字段无法安全定单位
        ("乱码￥％％", None),  # 认不出的串：宁可丢字段，绝不猜单位
        ("12,345", 12345),  # 逗号整数 → 整数分
        ("¥12,345", 12345),  # 带币符整数 → 整数分
        (" 4000 ", 4000),  # 纯数字串带空白 → 整数分
    ],
)
def test_dirty_cents_field_normalized(raw: object, expected: int | None) -> None:
    assert ex3._coerce_optional_cents(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "完全是胡话，不是 JSON",
        '{"verdict":"MAYBE","rationale":"坏档位"}',  # verdict 不在五档内
        '{"verdict":"APPROVE","rationale":"缺右括号"',  # JSON 断裂
        "乱码￥％％",
    ],
)
def test_parse_ruling_unparseable_yields_review_sentinel(text: str) -> None:
    """哨兵纪律：解析失败 → REVIEW（可见的失败），绝不捏造四档可执行结论。"""
    ruling = ex3.parse_ruling(text)
    assert ruling.verdict == "REVIEW"
    assert ruling.capped_amount_cents is None
    assert "不可解析" in ruling.rationale  # 人工复核要看得懂为什么进复核


def test_valid_json_with_dirty_field_survives() -> None:
    """一个坏字段不毁整份裁决：脏金额被归一，裁决本体存活。"""
    payload = {"verdict": "APPROVE_WITH_CAP", "rationale": "按 POL-9.1 封顶", "capped_amount_cents": "85%"}
    ruling = ex3.parse_ruling(json.dumps(payload, ensure_ascii=False))
    assert ruling.verdict == "APPROVE_WITH_CAP"
    assert ruling.capped_amount_cents is None
    # 五档枚举里 REVIEW 是哨兵档（解析失败是一等业务状态，不是异常路径）
    assert set(get_args(ex3.Verdict)) == {"APPROVE", "APPROVE_WITH_CAP", "ESCALATE", "REJECT", "REVIEW"}
