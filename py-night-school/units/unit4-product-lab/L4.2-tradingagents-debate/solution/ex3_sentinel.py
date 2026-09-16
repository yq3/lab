# 参考答案：ex3_sentinel（练习文件的完整解法——完成前别看）
"""哨兵 + 脏字段归一：_coerce_optional_cents 与 parse_ruling 的完整实现。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator

Verdict = Literal["APPROVE", "APPROVE_WITH_CAP", "ESCALATE", "REJECT", "REVIEW"]

_NULLISH_CENTS = {"", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown", "不适用"}


def _coerce_optional_cents(value: object) -> object:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.lower() in _NULLISH_CENTS or text.endswith("%"):
        return None  # 占位串 / 百分比：绝不冒充金额
    cleaned = text.replace(",", "").lstrip("¥$€£").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)  # 整数形态：折成整数分
    except ValueError:
        return None  # 带小数货币串 / 乱码：宁可丢字段，绝不猜单位


class AppealRuling(BaseModel):
    verdict: Verdict
    rationale: str
    capped_amount_cents: int | None = None

    @field_validator("capped_amount_cents", mode="before")
    @classmethod
    def _dirty_cents_to_none(cls, v: object) -> object:
        return _coerce_optional_cents(v)


def parse_ruling(text: str) -> AppealRuling:
    try:
        return AppealRuling.model_validate_json(text.strip())
    except ValidationError as exc:
        return AppealRuling(verdict="REVIEW", rationale=f"裁决输出不可解析，转人工复核：{str(exc)[:120]}")
