"""Step3 风控 clamp 的三条纪律（零模型调用）——limits.apply_limits 逐幕验证。

对版 risk/limits.py#apply_limits：先单笔封顶、再总额等比缩、只缩不放、
被砍金额不重分配、每刀 ClampEvent 留审计、幂等。
"""

from __future__ import annotations

from limits import LimitsResult, apply_limits


def show(title: str, amounts: dict[str, int], single: int, total: int) -> LimitsResult:
    print(f"[{title}] 明细={amounts} 单笔上限={single} 总额上限={total}")
    result = apply_limits(amounts, single, total)
    for clamp in result.clamps:
        item = clamp.item if clamp.item is not None else "（批次级）"
        print(f"  clamp: {clamp.limit:<20} {item:<8} {clamp.before} -> {clamp.after} 分")
    print(f"  结果: {result.amounts}（缩后总和 {sum(result.amounts.values())} 分）")
    return result


def main() -> None:
    print("== Step3 风控 clamp：conviction requests, risk disposes ==")

    print("幕一 单笔封顶：只有一笔超单笔上限，一刀砍到上限，一刀一事件")
    show("幕一", {"A": 8800, "B": 1200}, 5000, 10000)

    print("幕二 先单后总：两笔各自超单笔上限，封顶后总额仍超，再等比缩")
    r2 = show("幕二", {"A": 8000, "B": 6000}, 5000, 8000)
    print("  <- 顺序即语义：先砍单笔 [5000,5000]，总额 10000 仍超 8000，等比缩 0.8 -> [4000,4000]")
    print("     缩只会变小，缩完不会重新违反单笔上限——这对组合因此幂等")

    print("幕三 只缩不放 + 幂等：不该动的金额一个不动；跑两遍结果一致")
    show("幕三a 低于两道上限", {"A": 3000, "B": 800}, 5000, 4000)
    again = apply_limits(r2.amounts, 5000, 8000)
    print(f"[幕三b 幂等] 再跑一遍幕二的结果: amounts={again.amounts} clamps={again.clamps}")
    print("  <- 全等且零事件；被砍金额不重分配——留在预算里（对版「留在现金」）")


if __name__ == "__main__":
    main()
