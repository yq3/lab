# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体**与所需的顶部 import**，其余不要动）
"""apply_limits + ClampEvent：风控的两道硬闸门（对版 hedge_fund/risk/limits.py）。

"Conviction requests, risk disposes"：检查员只能请求，风控用确定性算术处置。
两道闸门的顺序就是幂等的来源：

    1) 单笔封顶：任一明细 > max_single_cents 砍到上限，一刀一事件；
    2) 总额等比缩：封顶后的总和仍超 max_dept_total_cents 时全部明细等比缩小。

三条纪律（验收逐条对）：先单后总的顺序；只缩不放（floor 取整，缩后总和
不超过上限）；每一刀 ClampEvent(limit, item, before, after) 留审计、双跑幂等。

完成判据：uv run pytest exercises/test_ex3.py 全绿——四个测试：
  先单后总：单笔事件在前、批次级事件在后，金额与事件逐条对得上；
  只缩不放：低于上限的金额一个不动，floor 后总和不超过上限；
  事件与结果对账：total 事件的 after 恰是结果表的总和（item 为 None）；
    单笔事件的 after 是封顶值，其后的等比缩只会让结果表更低；
  幂等：apply(apply(x)) 与 apply(x) 全等，第二遍零事件。
"""

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
    # TODO(ex3): 第一段怎么遍历才让事件顺序确定？砍到上限时事件的 before/after 各记什么？
    #   第二段的「等比缩」缩谁、比例怎么算、整数的向下取整怎么取？
    #   批次级事件的 item 记什么、after 记缩后总和还是上限值（想想验收怎么对账）？
    raise NotImplementedError("TODO(ex3): 补全两段 clamp")
