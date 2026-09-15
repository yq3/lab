# 练习 3（单变量编辑约束：只改本文件 TODO 标注的区域，其余不要动）
"""verdict 值域：Literal 声明 + 归一化 + fail-closed。

考察点：typing.Literal 把值域写进类型（pydantic 会把它广告成 schema 的 enum）；
Field 约束（pattern / min_length）补齐校验；
normalize_verdict 对模型输出做大小写/空格容错——但绝不发明值域外的结论（fail-closed：
收窄可以，放宽不行——未知的 REJECT 原因必须抛错，不许猜）。

完成判据：uv run pytest exercises/test_ex3.py 全绿——
  坏单号 / 空 reason 被 ValidationError 拒；四个归一化样本全对；未知原因 ValueError。
提示：Literal 在 typing 里 import；归一化先 strip + upper，再去掉冒号后的空格。
"""

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
    """预审决策模型：字段已声明，你补上约束（TODO 两行）。

    claim_id 需要 pattern（形如 CLM-2026-0001）；reason 需要 min_length=1；
    reviewer 的默认值写法是「有默认 → 不进 required」的活例子，不要动。
    """

    # TODO(ex3): 给 claim_id 加 Field(pattern=...)——单号格式在门口拦住幻觉
    claim_id: str
    verdict: Verdict = Field(description="PASS 或 REJECT:<INVALID_AMOUNT|ITEM_OVER_LIMIT|TOTAL_OVER_LIMIT>")
    # TODO(ex3): 给 reason 加 Field(min_length=1)——空理由不算理由
    reason: str
    reviewer: str = "night-school-agent"


def normalize_verdict(raw: str) -> str:
    """把模型输出的 verdict 归一化到合法值：大小写与空格容错；未知值抛 ValueError。

    样本：" pass " -> "PASS"；"reject:item_over_limit" -> "REJECT:ITEM_OVER_LIMIT"；
          "REJECT: ITEM_OVER_LIMIT" -> "REJECT:ITEM_OVER_LIMIT"；"REJECT:NEW_RULE" -> ValueError。
    """
    # TODO(ex3): strip + upper + 去掉冒号后空格；合法值集合里查；查不到 raise ValueError
    raise NotImplementedError("TODO(ex3): 补全 normalize_verdict")
