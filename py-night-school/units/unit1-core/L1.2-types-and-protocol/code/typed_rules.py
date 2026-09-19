"""报销预审函数族——现代类型标注全景（L0.1 budget.py 的类型化扩编版）。

本文件的每个签名都是一课：list[int] 内置泛型、str | None 联合类型、
dict.get 的默认值、以及「联合类型入口先收窄」的正确姿势（对照 §5 陷阱）。

重要认知：这些标注**运行时不强制**——它们是写给 pyright / IDE / 读者看的。
"""

DAILY_MEAL_LIMIT_CENTS = 5000
TRIP_TOTAL_LIMIT_CENTS = 500000


def parse_amounts(raw: str) -> list[int]:
    """把 "1200,3500,2400" 解析成 [1200, 3500, 2400]（推导式，L1.1 §2.7）。"""
    return [int(part) for part in raw.split(",")]


def preapprove(items_cents: list[int]) -> str:
    """三条规则按优先级裁决（与 L0.1/L1.1 相同的规则本体）。"""
    if any(c <= 0 for c in items_cents):
        return "REJECT:INVALID_AMOUNT"
    if any(c > DAILY_MEAL_LIMIT_CENTS for c in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    if sum(items_cents) > TRIP_TOTAL_LIMIT_CENTS:
        return "REJECT:TOTAL_OVER_LIMIT"
    return "PASS"


def first_rejected(results: list[tuple[str, str]]) -> str | None:
    """返回第一张被拒单据的 id；全部放行返回 None。

    str | None 读作「字符串或 None」——对照 Java 的 @Nullable String，
    但它是类型系统的一等公民，pyright 会盯着你收窄。
    """
    for claim_id, verdict in results:
        if verdict != "PASS":
            return claim_id
    return None


def reject_tally(results: list[tuple[str, str]]) -> dict[str, int]:
    """统计每种拒绝原因的单据数：dict.get(键, 默认值) ≈ Map.getOrDefault。"""
    counts: dict[str, int] = {}
    for _, verdict in results:
        if verdict != "PASS":
            counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def late_fee_cents(days_late: int | None) -> int:
    """逾期滞纳金：每天 100 分；days_late 为 None 表示日期缺失。

    §5 陷阱的正确示范：联合类型入口**先收窄**（if x is None: raise ...），
    收窄之后 pyright 才允许把 x 当 int 用（类型收窄，讲义 §2.7）。
    """
    if days_late is None:
        raise ValueError("days_late 不能为 None：日期缺失的单据应走人工通道")
    return days_late * 100
