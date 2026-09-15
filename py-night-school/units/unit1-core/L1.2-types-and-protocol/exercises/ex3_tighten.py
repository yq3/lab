# 练习 3（单变量编辑约束：只改函数签名里的 Any 标注，函数体一行都不要动）
"""把 Any 滥用点收紧成精确类型——Any 是逃生舱，不是默认选项。

三个函数的行为已写好且测试全过；签名上的 Any 是「懒得写」的痕迹，
你的任务是把它们换成精确类型（预期见各函数的 TODO 注释——与验收同口径）。

修完后若 from typing import Any 已无处使用，把它一并删掉（ruff 的 F401 会盯上它）。
"""

from typing import Any


def clip_to_limit(amounts: Any) -> Any:
    """把每笔金额封顶到单笔上限（超限的按上限计，做「软拒绝」统计用）。

    TODO(ex3): 预期 amounts: list[int]，返回 list[int]
    """
    return [min(a, 5000) for a in amounts]


def rejection_code(verdict: Any) -> Any:
    """取拒绝原因码："REJECT:ITEM_OVER_LIMIT" -> "ITEM_OVER_LIMIT"；非拒绝 -> ""。

    TODO(ex3): 预期 verdict: str，返回 str
    """
    if verdict.startswith("REJECT:"):
        return verdict.split(":", 1)[1]
    return ""


def verdict_counts(results: Any) -> Any:
    """统计每种判定的单据数：{"PASS": 2, "REJECT:INVALID_AMOUNT": 1}。

    TODO(ex3): 预期 results: list[tuple[str, str]]，返回 dict[str, int]
    """
    counts: dict[str, int] = {}
    for _, verdict in results:
        counts[verdict] = counts.get(verdict, 0) + 1  # dict.get(键, 默认值) ≈ getOrDefault
    return counts
