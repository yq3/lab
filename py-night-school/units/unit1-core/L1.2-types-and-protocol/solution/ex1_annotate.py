"""参考答案（ex1）——四个签名补全，函数体与练习版一字不差。"""


def parse_amounts(raw: str) -> list[int]:
    """把 "1200,3500,2400" 解析成 [1200, 3500, 2400]。"""
    return [int(part) for part in raw.split(",")]


def first_rejected(results: list[tuple[str, str]]) -> str | None:
    """返回第一张被拒单据的 id；全部放行返回 None。"""
    for claim_id, verdict in results:
        if verdict != "PASS":
            return claim_id
    return None


def reject_tally(results: list[tuple[str, str]]) -> dict[str, int]:
    """统计每种判定的单据数：{"PASS": 2, "REJECT:ITEM_OVER_LIMIT": 1}。"""
    counts: dict[str, int] = {}
    for _, verdict in results:
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def is_clean(verdicts: list[str]) -> bool:
    """整组判定是否全部放行（无任何 REJECT）。"""
    return all(v == "PASS" for v in verdicts)
