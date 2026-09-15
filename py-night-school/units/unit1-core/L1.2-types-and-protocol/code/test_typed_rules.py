"""讲义测试：typed_rules 的行为 + None 语义（is None 判等）。"""

import pytest

from typed_rules import first_rejected, late_fee_cents, parse_amounts, preapprove, reject_tally

RESULTS: list[tuple[str, str]] = [
    ("CLM-2026-0001", "PASS"),
    ("CLM-2026-0002", "REJECT:ITEM_OVER_LIMIT"),
    ("CLM-2026-0003", "REJECT:INVALID_AMOUNT"),
    ("CLM-2026-0004", "REJECT:ITEM_OVER_LIMIT"),
]


def test_parse_amounts() -> None:
    assert parse_amounts("1200,3500,2400") == [1200, 3500, 2400]


def test_preapprove() -> None:
    assert preapprove([1200, 3500, 2400]) == "PASS"
    assert preapprove([8800]) == "REJECT:ITEM_OVER_LIMIT"


def test_first_rejected_returns_id_or_none() -> None:
    assert first_rejected(RESULTS) == "CLM-2026-0002"
    # None 的判等永远用 is：== 可能被自定义 __eq__ 劫持，is 是身份比较
    assert first_rejected([("CLM-2026-0001", "PASS")]) is None


def test_reject_tally() -> None:
    assert reject_tally(RESULTS) == {"REJECT:ITEM_OVER_LIMIT": 2, "REJECT:INVALID_AMOUNT": 1}
    assert reject_tally([]) == {}


def test_late_fee_narrowing() -> None:
    assert late_fee_cents(3) == 300
    # 联合类型入口先收窄：None 路径抛 ValueError（pytest.raises ≈ assertThrows）
    with pytest.raises(ValueError, match="人工通道"):
        late_fee_cents(None)
