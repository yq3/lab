"""风控限额——检查员无法逾越的硬闸门（对版 hedge_fund/risk/limits.py#apply_limits）。

"Conviction requests, risk disposes"（产品 limits.py 的开场白）：
检查员只能「请求」（投票），风控用确定性算术「处置」（clamp）。本课的报销映射：

    max_position_pct（单票 |weight| 上限） -> max_single_cents（单笔明细金额上限）
    max_gross_exposure（组合总敞口上限）   -> max_dept_total_cents（部门剩余预算总额上限）

三条纪律与产品逐字对齐：
1. 先单笔封顶，再总额等比缩——顺序保证幂等（缩只会变小，缩完不会重新违反单笔上限）；
2. 只缩不放：clamp 永不上调任何金额（放大会让风控阶段获得「加钱」能力，与职责相反）；
3. 被砍掉的金额不重分配——留在预算里（对版「留在现金」：重分配=变相加仓）。

每一刀都留 ClampEvent(limit, item, before, after)——风控动作可解释、可回放。
金额整数分：等比缩用向下取整（floor），保证缩后总和不超过上限。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClampEvent(BaseModel):
    """一刀 clamp 的审计事件（对版 ClampEvent——"recorded so every clamp is explainable"）。"""

    limit: Literal["max_single_cents", "max_dept_total_cents"]
    item: str | None = Field(default=None, description="被砍的明细名；None=批次级总额刀")
    before: int = Field(description="砍前金额（分）")
    after: int = Field(description="砍后金额（分）")


class LimitsResult(BaseModel):
    """clamp 后的金额表 + 每一刀的审计流水（对版 RiskResult）。"""

    amounts: dict[str, int] = Field(description="明细名 -> clamp 后金额（分）")
    clamps: list[ClampEvent] = Field(default_factory=list)


def apply_limits(
    claims_amounts: dict[str, int],
    max_single_cents: int,
    max_dept_total_cents: int,
) -> LimitsResult:
    """对一批明细金额施加两道硬限额（对版 apply_limits 的整数分版）。

    顺序 matters 且使两道闸门幂等：
    1. 单笔封顶：任一明细 > max_single_cents 的砍到上限，一刀一事件；
    2. 总额等比缩：总和仍超 max_dept_total_cents 时，全部明细按比例缩小
       （floor 取整，只缩不放），另记一条批次级事件。
    按明细名排序遍历——事件顺序确定，回放才有唯一答案。
    """
    clamped: dict[str, int] = {}
    clamps: list[ClampEvent] = []

    for item in sorted(claims_amounts):
        amount = claims_amounts[item]
        if amount > max_single_cents:
            clamps.append(ClampEvent(limit="max_single_cents", item=item, before=amount, after=max_single_cents))
            clamped[item] = max_single_cents
        else:
            clamped[item] = amount

    total = sum(clamped.values())
    if total > max_dept_total_cents:
        scale = max_dept_total_cents / total
        clamped = {item: int(amount * scale) for item, amount in clamped.items()}
        clamps.append(
            ClampEvent(
                limit="max_dept_total_cents",
                item=None,
                before=total,
                after=sum(clamped.values()),
            )
        )

    return LimitsResult(amounts=clamped, clamps=clamps)
