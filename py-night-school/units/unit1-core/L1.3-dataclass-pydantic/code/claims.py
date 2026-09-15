"""Pydantic 版报销模型——Java 三件套（bean + Bean Validation + Jackson）的合体。

一句话：BaseModel 的构造函数 = Jackson 的 readValue + Validator 的 validate，
model_dump()/model_dump_json() = Jackson 的 writeValueAsString。
agent 框架选它当「血管」的原因：LLM 吐出的是 JSON——model_validate() 一步
「解析 + 校验 + 类型收敛」，不合法就抛 ValidationError 拒收（L2.4 结构化输出的地基）。
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field


class ExpenseClaim(BaseModel):
    """报销单（Pydantic 版）：字段约束全部写在 Field(...) 里，构造那一刻执行。

    字段语义：
      claim_id     必须形如 CLM-2026-0001（年 4 位 + 流水 4 位，与 data/expense mock 同格式）；
      items_cents  非空正整数分列表——列表元素的约束用 Annotated[int, Field(gt=0)] 写进泛型参数；
      submitter    提交人，非空串；
      submitted_at 提交时间，可选；给 ISO 字符串会被 Pydantic 自动转成 datetime 对象。
    """

    claim_id: str = Field(pattern=r"^CLM-\d{4}-\d{4}$")
    items_cents: list[Annotated[int, Field(gt=0)]]
    submitter: str = Field(min_length=1)
    submitted_at: datetime | None = None

    @classmethod
    def from_cents_string(cls, claim_id: str, submitter: str, cents_string: str) -> "ExpenseClaim":
        """替代构造（对照 Java 静态工厂 valueOf / of）："1200,3500,2400" -> 报销单。

        classmethod 的意思是：第一个参数是类本身（惯用名 cls）而非实例——
        在类还没「出生」的场景（工厂方法）里用它引用「正在构造的类」，子类继承时也自动正确。
        解析出负数或 0 不用自己判断：转交给 cls(...) 的构造校验（gt=0）去拒。
        """
        items: list[int] = []
        # 显式循环版（列表推导式是 L1.4 的正课，到时把这四行缩成一行）
        for part in cents_string.split(","):
            items.append(int(part.strip()))
        return cls(claim_id=claim_id, submitter=submitter, items_cents=items)


class ClaimBatch(BaseModel):
    """嵌套模型：批次含多张报销单。claims 的每个元素都会走 ExpenseClaim 的全部校验。"""

    batch_id: str = Field(pattern=r"^BATCH-\d{4}-\d{2}$")  # 形如 BATCH-2026-09
    claims: list[ExpenseClaim] = Field(default_factory=list)
