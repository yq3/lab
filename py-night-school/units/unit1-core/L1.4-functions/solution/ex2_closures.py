"""参考答案（ex2）——先完成练习再看。

要点：返回函数名不带括号（返回函数本身）；读捕获零声明、写捕获 nonlocal；
每次工厂调用都是一套全新环境——独立性是闭包版计数器对全局变量版的完胜点。
"""

from collections.abc import Callable


def make_greeter(greeting: str) -> Callable[[str], str]:
    def greet(name: str) -> str:
        return f"{greeting}，{name}！"  # 只读外层变量：免费

    return greet  # 返回函数本身，不带括号


def make_counter(start: int = 0, step: int = 1) -> Callable[[], int]:
    state = start

    def next_value() -> int:
        nonlocal state  # 要赋值外层变量，先声明「我写的是外层那个」
        state += step
        return state

    return next_value
