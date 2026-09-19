# 练习 2（单变量编辑约束：只改 TODO 标注的两个函数体，其余不要动）
"""闭包工厂两连——一个读捕获，一个写捕获（必须用到 nonlocal）。

判据（test_ex2.py 逐条验收）：
  1. make_greeter：返回的函数拼接问候语（只读外层变量，不需要 nonlocal）；
  2. make_counter：每次调用返回下一个值，state 用 nonlocal 推进；
  3. 两次工厂调用各自独立——把 state 写成模块级全局变量会当场穿帮（测试专查这个）。
完成后：uv run pytest exercises/test_ex2.py 全绿。
"""

from collections.abc import Callable


def make_greeter(greeting: str) -> Callable[[str], str]:
    """TODO(ex2a): 返回 f(name) -> "{greeting}，{name}！" 的函数（greeting 被闭包捕获）。"""
    raise NotImplementedError("TODO(ex2a): 内层函数读 greeting，外层返回它")


def make_counter(start: int = 0, step: int = 1) -> Callable[[], int]:
    """TODO(ex2b): 返回计数器函数：每次调用返回 start+step、start+2*step、...

    必须用「写外层变量的那个关键字」推进闭包里的 state（验收测试会检查函数源码里
    出现了该关键字——这是本函数的考点，不许用全局变量或列表容器绕过）。
    """
    raise NotImplementedError("TODO(ex2b): state 存外层，内层声明关键字后推进并返回")
