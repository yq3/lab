# 练习 1（单变量编辑约束：只改 TODO 标注的类体，其余不要动）
"""把手写类改写成 dataclass——体验「行为等价」的改写。

下方 ExpenseLine（报销明细行）是讲义 §3 手写痛苦版的缩影：__init__ / __repr__ / __eq__
全手写、可变默认值用 None 哨兵。你要在 TODO 区用 @dataclass 写出行为等价的 ExpenseLineData。

行为等价的判据（test_ex1.py 逐条验收）：
  1. 三个字段可按位置或关键字构造；
  2. tags 缺省时为空列表，且每个实例各拿各的（不能共享同一个 list 对象）；
  3. 全字段相等比较（类型不同判不等）；
  4. repr 形如 ExpenseLineData(description='餐饮', amount_cents=3500, tags=[...])；
  5. is_dataclass(ExpenseLineData) 为 True（不许把上面的手写类抄下来糊弄）。
完成后：uv run pytest exercises/test_ex1.py 全绿。
"""

from dataclasses import dataclass


class ExpenseLine:
    """手写版（不要改）：dataclass 要与它行为等价。"""

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


# ── TODO(ex1)：把 ExpenseLine 改写成 dataclass，类名必须是 ExpenseLineData ──────────
@dataclass
class ExpenseLineData:
    """TODO(ex1): 把 ExpenseLine 的三个字段搬进类体（字段名与顺序保持一致）。

    提醒：tags 的默认空列表不能写 tags: list[str] = []（dataclass 会拒绝——想想为什么）。
    需要的可变默认值工具在 dataclasses 模块里，import 语句可以加。
    """


# ── TODO(ex1) 区结束 ───────────────────────────────────────────────────────────────
