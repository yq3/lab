"""参考答案（ex3）——注册型装饰器 + 按名分发，框架 @tool 的最小原型。"""

from collections.abc import Callable

TOOLS: dict[str, Callable[[list[int]], str]] = {}


def register(func: Callable[[list[int]], str]) -> Callable[[list[int]], str]:
    """无参装饰器：把函数以 __name__ 登记进 TOOLS，并「原样返回」（不包装）。"""
    TOOLS[func.__name__] = func
    return func


@register
def check_item_limit(items_cents: list[int]) -> str:
    """单笔金额检查：任意一笔 > 5000 分则拒绝。"""
    if any(c > 5000 for c in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    return "PASS"


@register
def check_total_limit(items_cents: list[int]) -> str:
    """合计金额检查：总额 > 500000 分则拒绝。"""
    if sum(items_cents) > 500000:
        return "REJECT:TOTAL_OVER_LIMIT"
    return "PASS"


def run_tool(name: str, items_cents: list[int]) -> str:
    """按名调用 TOOLS 里的工具；名字不存在时抛 KeyError。"""
    if name not in TOOLS:
        raise KeyError(f"未注册的工具: {name!r}，可用: {sorted(TOOLS)}")
    return TOOLS[name](items_cents)
