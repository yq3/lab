# 参考答案：ex3_limits（练习文件的完整解法——完成前别看）
"""apply_limits + ClampEvent：风控的两道硬闸门（对版 hedge_fund/risk/limits.py）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClampEvent(BaseModel):
    """一刀 clamp 的审计事件（对版产品同名模型）。"""

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
    """对一批明细金额（整数分）施加两道硬限额。"""
    clamped: dict[str, int] = {}
    clamps: list[ClampEvent] = []

    # 1) 单笔封顶：sorted 遍历保证事件顺序确定（可重放）
    for item in sorted(claims_amounts):
        amount = claims_amounts[item]
        if amount > max_single_cents:
            clamps.append(ClampEvent(limit="max_single_cents", item=item, before=amount, after=max_single_cents))
            clamped[item] = max_single_cents
        else:
            clamped[item] = amount

    # 2) 总额等比缩：floor 取整只缩不放，缩后总和不超过上限
    total = sum(clamped.values())
    if total > max_dept_total_cents:
        scale = max_dept_total_cents / total
        clamped = {item: int(amount * scale) for item, amount in clamped.items()}
        clamps.append(ClampEvent(limit="max_dept_total_cents", item=None, before=total, after=sum(clamped.values())))

    return LimitsResult(amounts=clamped, clamps=clamps)
