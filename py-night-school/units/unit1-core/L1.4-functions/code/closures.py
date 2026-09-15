"""闭包工厂：函数记住了自己出生时的环境（对照 Java lambda 捕获 effectively final 变量）。

两个记忆点：
  - 读外层变量免费：内层函数直接引用外层名字；
  - 给外层变量「赋值」必须 nonlocal 声明——否则赋值语句会创建同名局部变量，
    把外层名字遮蔽（shadowing）。读写规则不对称，是 Python 作用域设计的刻意选择。
两个语言各限制一头，对照着记很妙：
  Java lambda：捕获的变量必须 effectively final——「读随便、写禁止」；
  Python 闭包：随便写——但要先 nonlocal 声明「我写的是外层那个」。
"""

from collections.abc import Callable


def make_threshold(limit_cents: int) -> Callable[[int], bool]:
    """闭包工厂：返回「单笔是否超限」的检查函数。limit_cents 被闭包捕获。

    对照 Java：Integer limit = 5000; Predicate<Integer> exceeds = a -> a > limit;
    ——同一件事，Python 不需要函数式接口这个「适配器类型」。
    """

    def exceeds(amount_cents: int) -> bool:
        return amount_cents > limit_cents  # 只读外层变量：免费，无需任何声明

    return exceeds


def make_counter(start: int = 0, step: int = 1) -> Callable[[], int]:
    """可写闭包：state 存在闭包环境里，每次调用推进一格并返回新值。

    每个 make_counter() 调用都创建一套全新的 state——两次工厂调用互不干扰
    （对照：把 state 放成模块级全局变量，所有计数器就串台了——练习 2 的验收点之一）。
    """

    state = start

    def next_value() -> int:
        nonlocal state  # 没有这行，下面的 state += step 会创建局部变量并报 UnboundLocalError
        state += step
        return state

    return next_value
