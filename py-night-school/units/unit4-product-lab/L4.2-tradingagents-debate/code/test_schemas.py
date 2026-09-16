"""讲义区验收 2/4：输出卫生两道闸——脏字段归一（_coerce_optional_cents）与 REVIEW 哨兵。

对版 TradingAgents 两大「硬」保护（其余全是 prompt 软约束——调研结论）：
- schemas.py#_coerce_optional_float（#1058/#1288）：占位串/百分比/人写货币的归一；
  百分比绝不冒充绝对数额。本课是整数分字段的变体：带小数货币串同样不可抢救 → None。
- signal_processing.py（#1170）：解析失败返回 REVIEW 哨兵，绝不捏造可执行结论。
"""

from __future__ import annotations

from typing import get_args

import pytest

from schemas import Verdict, _coerce_optional_cents, parse_final_decision, parse_ruling


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("N/A", None),  # 占位串（对版 _NULLISH_FLOAT）
        ("none", None),  # 占位串大小写不敏感
        ("85%", None),  # 百分比绝不冒充金额（对版 #1288 的取向）
        ("¥1,234.50", None),  # 带小数货币串：整数分字段无法安全定单位 → 与百分比同判不可抢救
        ("乱码￥％％", None),  # 认不出的串：宁可丢字段，绝不猜单位
        ("12,345", 12345),  # 逗号整数：可抢救，折成整数分
        ("¥12,345", 12345),  # 带币符整数：同上（对版 "$1,234.50"→1234.5 的整数版）
        (" 4000 ", 4000),  # 纯数字串带空白
        (4000, 4000),  # 非字符串原样放行（模型本来填对了）
    ],
)
def test_dirty_cents_field_normalized(raw: object, expected: int | None) -> None:
    assert _coerce_optional_cents(raw) == expected


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
    """哨兵纪律：任何解析失败 → REVIEW（可见的失败），绝不捏造四档可执行结论。"""
    ruling = parse_ruling(text)
    assert ruling.verdict == "REVIEW"
    assert ruling.capped_amount_cents is None
    assert "不可解析" in ruling.rationale


def test_parse_ruling_valid_json_with_dirty_field_survives() -> None:
    """一个坏字段不毁整份裁决：脏金额被归一，裁决本体存活（对版「null 掉坏字段」取向）。"""
    ruling = parse_ruling('{"verdict":"APPROVE_WITH_CAP","rationale":"按 POL-9.1 封顶","capped_amount_cents":"85%"}')
    assert ruling.verdict == "APPROVE_WITH_CAP"
    assert ruling.capped_amount_cents is None


def test_parse_final_decision_shares_sentinel_discipline() -> None:
    final = parse_final_decision("终审官今天不想输出 JSON")
    assert final.verdict == "REVIEW"
    ok = parse_final_decision('{"verdict":"REJECT","summary":"维持驳回","capped_amount_cents":"¥4,000"}')
    assert (ok.verdict, ok.capped_amount_cents) == ("REJECT", 4000)


def test_verdict_literal_is_five_tier_with_review_sentinel() -> None:
    """meta：五档枚举齐全，REVIEW 哨兵在枚举里（「解析失败」是一等业务状态）。"""
    assert set(get_args(Verdict)) == {"APPROVE", "APPROVE_WITH_CAP", "ESCALATE", "REJECT", "REVIEW"}
