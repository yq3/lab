"""练习 1 验收（不要改本文件——它就是你的判卷老师）。

双通道：行为不变 + 标注精确（get_type_hints 在运行时取出你写的标注逐个比对——
标注不强制，但它是真实存储在函数对象上的数据，可以机器检查）。
"""

from typing import get_type_hints

import ex1_annotate
from ex1_annotate import first_rejected, is_clean, parse_amounts, reject_tally

RESULTS: list[tuple[str, str]] = [
    ("CLM-2026-0001", "PASS"),
    ("CLM-2026-0002", "REJECT:ITEM_OVER_LIMIT"),
    ("CLM-2026-0003", "PASS"),
    ("CLM-2026-0004", "REJECT:ITEM_OVER_LIMIT"),
]


def test_behavior_unchanged() -> None:
    assert parse_amounts("1200,3500") == [1200, 3500]
    assert first_rejected(RESULTS) == "CLM-2026-0002"
    assert first_rejected([("CLM-2026-0001", "PASS")]) is None
    assert reject_tally(RESULTS) == {"PASS": 2, "REJECT:ITEM_OVER_LIMIT": 2}
    assert is_clean(["PASS"]) is True
    assert is_clean(["PASS", "REJECT:ITEM_OVER_LIMIT"]) is False


# 期望的标注（三方对齐：题目注释、hints、本表同一口径）
EXPECTED_HINTS: dict[str, dict[str, object]] = {
    "parse_amounts": {"raw": str, "return": list[int]},
    "first_rejected": {"results": list[tuple[str, str]], "return": str | None},
    "reject_tally": {"results": list[tuple[str, str]], "return": dict[str, int]},
    "is_clean": {"verdicts": list[str], "return": bool},
}


def test_annotations_present_and_precise() -> None:
    for name, expected in EXPECTED_HINTS.items():
        hints = get_type_hints(getattr(ex1_annotate, name))
        for param, expected_type in expected.items():
            actual = hints.get(param)
            assert actual == expected_type, f"{name} 的 {param} 标注应为 {expected_type}，实际是 {actual}"
