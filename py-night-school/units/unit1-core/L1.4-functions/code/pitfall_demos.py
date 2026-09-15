"""两个坑的可运行复现（讲义 §5）：可变默认参数坑 + late binding 闭包坑。

运行：uv run python code/pitfall_demos.py
每段输出的「意外结果」都在讲义里拆解；修复版紧跟其后输出对照组。
"""

from collections.abc import Callable


def add_item_buggy(item: str, items: list[str] = []) -> list[str]:  # noqa: B006 —— 坑位样本：B006 就是这个坑的机器名
    """坑：默认值只在 def 执行时求值一次——所有调用共享同一个列表对象。"""
    items.append(item)
    return items


def add_item_fixed(item: str, items: list[str] | None = None) -> list[str]:
    """修复纪律：默认 None + 函数体内现做新列表。"""
    items = items if items is not None else []
    items.append(item)
    return items


def late_binding_lambdas() -> list[Callable[[], int]]:
    """坑：循环里建的 lambda 捕获的是变量 i 本身（引用），不是当时的值。"""
    return [lambda: i for i in range(3)]  # noqa: B023 —— 坑位样本：B023 就是这个坑的机器名


def pinned_lambdas() -> list[Callable[[], int]]:
    """修复：用默认参数在「定义那一刻」钉住值——每次循环都是新函数 + 新默认值对象。"""
    return [lambda i=i: i for i in range(3)]


print("── 可变默认参数坑 ──")
first = add_item_buggy("打车")
second = add_item_buggy("工作餐")
print(f"两次调用各传一个元素，第二次结果：{second}")
print(f"第一次的结果也被改了：{first}")
print(f"两次拿到的是同一个 list 对象：{first is second}")

print("── late binding 闭包坑 ──")
late = [f() for f in late_binding_lambdas()]
pinned = [f() for f in pinned_lambdas()]
print(f"循环里建的三个 lambda，调用结果：{late}")
print(f"默认参数钉值修复后：{pinned}")
