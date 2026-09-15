# 练习 1（单变量编辑约束：只改 TODO 标注的三个函数体，其余不要动）
"""规则函数序列版 preapprove——L0.1 的 if 链，这次拆成「数据化的规则」。

check_invalid 已给全（示范「命中返回 str / 未命中返回 None」的形状）；
你要完成另外两条规则和主函数。判据（test_ex1.py 逐条验收）：
  1. 三条规则的行为与 L0.1 完全同口径（含边界与冲突优先级用例）；
  2. preapprove 必须消费 RULES 这个列表本身——测试会往里面注入规则验证行为变化
     （把逻辑硬编码进 preapprove 的 if 链是过不了验收的，这正是本题的考点）。
完成后：uv run pytest exercises/test_ex1.py 全绿。
"""

from collections.abc import Callable

DAILY_MEAL_LIMIT_CENTS = 5000
TRIP_TOTAL_LIMIT_CENTS = 500000

Rule = Callable[[list[int]], str | None]


def check_invalid(items_cents: list[int]) -> str | None:
    """任意金额 <= 0 -> "REJECT:INVALID_AMOUNT"，否则 None。"""
    if any(c <= 0 for c in items_cents):
        return "REJECT:INVALID_AMOUNT"
    return None


def check_item_limit(items_cents: list[int]) -> str | None:
    """TODO(ex1a): 任意单笔 > DAILY_MEAL_LIMIT_CENTS -> "REJECT:ITEM_OVER_LIMIT"，否则 None。"""
    raise NotImplementedError("TODO(ex1a): 参照 check_invalid 的形状实现")


def check_total_limit(items_cents: list[int]) -> str | None:
    """TODO(ex1b): 合计 > TRIP_TOTAL_LIMIT_CENTS -> "REJECT:TOTAL_OVER_LIMIT"，否则 None。"""
    raise NotImplementedError("TODO(ex1b): 参照 check_invalid 的形状实现")


# 规则序列：列表顺序就是判定优先级（不要改本行）
RULES: list[Rule] = [check_invalid, check_item_limit, check_total_limit]


def preapprove(items_cents: list[int]) -> str:
    """TODO(ex1c): 按序对 RULES 逐个调用，第一条返回非 None 的结果就是 verdict；全 None -> "PASS"。"""
    raise NotImplementedError("TODO(ex1c): for 循环消费 RULES，返回第一个非 None 的 verdict")
