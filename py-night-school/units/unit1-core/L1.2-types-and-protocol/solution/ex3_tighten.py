"""参考答案（ex3）——Any 全部收紧；Any 的 import 已无处使用，一并删除。"""


def clip_to_limit(amounts: list[int]) -> list[int]:
    """把每笔金额封顶到单笔上限（超限的按上限计，做「软拒绝」统计用）。"""
    return [min(a, 5000) for a in amounts]


def rejection_code(verdict: str) -> str:
    """取拒绝原因码："REJECT:ITEM_OVER_LIMIT" -> "ITEM_OVER_LIMIT"；非拒绝 -> ""。"""
    if verdict.startswith("REJECT:"):
        return verdict.split(":", 1)[1]
    return ""


def verdict_counts(results: list[tuple[str, str]]) -> dict[str, int]:
    """统计每种判定的单据数：{"PASS": 2, "REJECT:INVALID_AMOUNT": 1}。"""
    counts: dict[str, int] = {}
    for _, verdict in results:
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts
