"""结构化建议单——Unit 3 四框架同题 demo 的统一输出契约（框架课对版）。

L2.4 的纪律在框架课延续：LLM 不是序列化层，边界上的 schema 由 Pydantic 把守。
各课的 demo 不管框架差异多大，出口都是这个模型——共用验收脚本只认它。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal["APPROVE", "REJECT", "ESCALATE"]


class Advice(BaseModel):
    """报销单审查结论（金额一律整数分）。"""

    claim_id: str = Field(description="报销单号，形如 CLM-2026-0001")
    decision: Decision = Field(description="APPROVE=建议通过；REJECT=建议拒绝；ESCALATE=转人工复核")
    reason: str = Field(description="枚举风格结论码：PASS / REJECT:<原因>（如 REJECT:ITEM_OVER_LIMIT）")
    remaining_cents: int = Field(ge=0, description="审查时点该部门剩余预算（分），check_budget 的镜像")
