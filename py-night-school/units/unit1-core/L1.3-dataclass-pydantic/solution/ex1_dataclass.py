"""参考答案（ex1）——先完成练习再看；不追求与你的写法一致，追求通过验收且读得舒服。

要点：三个字段声明 + tags 的 default_factory（本练习唯一真正的考点）。
"""

from dataclasses import dataclass, field


class ExpenseLine:
    """手写版（与练习文件同源，保持文件可独立运行）。"""

    def __init__(self, description: str, amount_cents: int, tags: list[str] | None = None) -> None:
        self.description = description
        self.amount_cents = amount_cents
        self.tags = tags if tags is not None else []

    def __repr__(self) -> str:
        return f"ExpenseLine(description={self.description!r}, amount_cents={self.amount_cents!r}, tags={self.tags!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ExpenseLine):
            return NotImplemented
        return (
            self.description == other.description
            and self.amount_cents == other.amount_cents
            and self.tags == other.tags
        )


@dataclass
class ExpenseLineData:
    description: str
    amount_cents: int
    tags: list[str] = field(default_factory=list)
