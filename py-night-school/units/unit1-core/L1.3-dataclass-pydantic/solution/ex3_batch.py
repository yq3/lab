"""参考答案（ex3）——先完成练习再看。

要点：from_lines 只做「解析 + 转发」——类目空、金额非正这些业务判断一个 if 都不写，
全部交给 ClaimItem 的约束在 cls(...) 构造那一刻拒（校验发生在「构造那一刻」）。
"""

from pydantic import BaseModel, Field


class ClaimItem(BaseModel):
    """单条明细：类目非空、金额为正整数分。"""

    category: str = Field(min_length=1)
    amount_cents: int = Field(gt=0)


class WeeklyBatch(BaseModel):
    """周报销汇总（嵌套模型）。"""

    report_id: str = Field(pattern=r"^RPT-\d{4}-W\d{2}$")
    submitted_by: str = Field(min_length=1)
    items: list[ClaimItem] = Field(default_factory=list)

    @classmethod
    def from_lines(cls, report_id: str, submitted_by: str, lines: list[str]) -> "WeeklyBatch":
        items: list[ClaimItem] = []
        for line in lines:
            category, amount = line.split("|")  # 拆不出两段自然抛 ValueError
            items.append(ClaimItem(category=category, amount_cents=int(amount)))
        return cls(report_id=report_id, submitted_by=submitted_by, items=items)
