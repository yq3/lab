"""练习 3 验收（不要改本文件——它就是你的判卷老师）。

双通道：行为不变 + Any 清零（meta-test 递归检查标注里不许再藏任何 Any——
包括 dict[str, Any] 这种「套壳 Any」）。
"""

from typing import Any, get_type_hints

import ex3_tighten
from ex3_tighten import clip_to_limit, rejection_code, verdict_counts

RESULTS: list[tuple[str, str]] = [
    ("CLM-2026-0001", "PASS"),
    ("CLM-2026-0002", "REJECT:ITEM_OVER_LIMIT"),
    ("CLM-2026-0003", "REJECT:INVALID_AMOUNT"),
    ("CLM-2026-0004", "REJECT:ITEM_OVER_LIMIT"),
]


def test_behavior_unchanged() -> None:
    assert clip_to_limit([1200, 8800]) == [1200, 5000]
    assert rejection_code("REJECT:ITEM_OVER_LIMIT") == "ITEM_OVER_LIMIT"
    assert rejection_code("PASS") == ""
    assert verdict_counts(RESULTS) == {"PASS": 1, "REJECT:ITEM_OVER_LIMIT": 2, "REJECT:INVALID_AMOUNT": 1}


def _contains_any(t: object) -> bool:
    """递归检查一个标注里是否藏着 Any（list[Any]、dict[str, Any] 也算）。"""
    if t is Any:
        return True
    args = getattr(t, "__args__", None)
    if args is None:
        return False
    return any(_contains_any(a) for a in args)


def test_no_any_left() -> None:
    """meta-test：三个函数的全部标注精确到位（与 ex3 注释里的预期同一口径）。"""
    expected: dict[str, dict[str, object]] = {
        "clip_to_limit": {"amounts": list[int], "return": list[int]},
        "rejection_code": {"verdict": str, "return": str},
        "verdict_counts": {"results": list[tuple[str, str]], "return": dict[str, int]},
    }
    for name, want in expected.items():
        hints = get_type_hints(getattr(ex3_tighten, name))
        assert set(hints) == set(want), f"{name}：标注不全，现有 {sorted(hints)}"
        for param, expected_type in want.items():
            assert hints[param] == expected_type, f"{name} 的 {param} 应为 {expected_type}"
            assert not _contains_any(hints[param]), f"{name} 的 {param} 里还藏着 Any"
