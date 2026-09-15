# 参考答案：ex3_verdict_model（练习文件的完整解法——完成前别看）
"""verdict 值域：Literal 声明 + 归一化 + fail-closed。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

REJECT_REASONS = ("INVALID_AMOUNT", "ITEM_OVER_LIMIT", "TOTAL_OVER_LIMIT")

Verdict = Literal[
    "PASS",
    "REJECT:INVALID_AMOUNT",
    "REJECT:ITEM_OVER_LIMIT",
    "REJECT:TOTAL_OVER_LIMIT",
]


class Decision(BaseModel):
    """预审决策模型。"""

    claim_id: str = Field(pattern=r"^CLM-\d{4}-\d{4}$")
    verdict: Verdict = Field(description="PASS 或 REJECT:<INVALID_AMOUNT|ITEM_OVER_LIMIT|TOTAL_OVER_LIMIT>")
    reason: str = Field(min_length=1)
    reviewer: str = "night-school-agent"


def normalize_verdict(raw: str) -> str:
    """把模型输出的 verdict 归一化到合法值：大小写与空格容错；未知值抛 ValueError。"""
    cleaned = raw.strip().upper().replace(": ", ":")
    valid = {"PASS"} | {f"REJECT:{reason}" for reason in REJECT_REASONS}
    if cleaned in valid:
        return cleaned
    raise ValueError(f"未知 verdict: {raw!r}（合法值：{sorted(valid)}）")
