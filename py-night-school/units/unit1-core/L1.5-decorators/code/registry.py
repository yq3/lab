"""registry 装饰器——框架 @tool 的秘密：把函数登记进注册表。

langchain / crewAI 的 @tool 做的事情本质上就是这一课的 TOOLS 字典：
「import 这个模块的瞬间，装饰器执行，函数被登记」——模型运行时按名字查表调用。

运行本文件：
    uv run python code/registry.py
"""

from collections.abc import Callable

# 工具注册表：名字 -> 函数。框架里它通常藏在某个 ToolRegistry 对象里。
TOOLS: dict[str, Callable[[list[int]], str]] = {}


def tool(func: Callable[[list[int]], str]) -> Callable[[list[int]], str]:
    """无参装饰器：把函数以 __name__ 登记进 TOOLS，并原样返回（不包装、不改行为）。

    这是「注册型装饰器」：装饰的意义不在增强函数，而在登记这个动作本身。
    """
    TOOLS[func.__name__] = func
    return func


@tool  # import/执行到这一行时：TOOLS["check_item_limit"] = check_item_limit
def check_item_limit(items_cents: list[int]) -> str:
    """单笔金额检查：任意一笔 > 5000 分则拒绝。"""
    if any(c > 5000 for c in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    return "PASS"


@tool
def check_total_limit(items_cents: list[int]) -> str:
    """合计金额检查：总额 > 500000 分则拒绝。"""
    if sum(items_cents) > 500000:
        return "REJECT:TOTAL_OVER_LIMIT"
    return "PASS"


def run_tool(name: str, items_cents: list[int]) -> str:
    """按名调用注册表里的工具——agent 运行时「模型选工具」之后走的就是这条路。"""
    if name not in TOOLS:
        raise KeyError(f"未注册的工具: {name!r}，可用: {sorted(TOOLS)}")
    return TOOLS[name](items_cents)


if __name__ == "__main__":
    # 注册表里有什么（注意：我们从头到尾没有手动往 TOOLS 里塞过任何东西）
    for name in TOOLS:
        print(f"已注册工具: {name}")

    # 按名调用——把「字符串」变成「函数调用」的那一步
    print(run_tool("check_item_limit", [1200, 8800]))  # REJECT:ITEM_OVER_LIMIT
    print(run_tool("check_total_limit", [1200, 3500, 2400]))  # PASS
