# 练习 3（单变量编辑约束：只改本文件 TODO 标注的区域，其余不要动）
"""registry 装饰器 + 按名调用——亲手搭一个迷你「框架工具注册表」。

考察点：注册型无参装饰器（登记进 dict、原样返回）、@ 语法在 def 时立即执行、按名分发。
验收（test_ex3.py 三方对齐）：
  1. TOOLS 里有两个工具：check_item_limit、check_total_limit（由 @register 登记）；
  2. 两个工具的裁决规则见下方 TODO 注释（返回 "PASS" / "REJECT:XXX"，金额整数分）；
  3. run_tool(name, items) 按名调用；名字不存在抛 KeyError。
完成后：uv run pytest exercises/test_ex3.py 全绿。
"""

from collections.abc import Callable

# 工具注册表：函数名 -> 函数（import 本模块的瞬间，@register 就会往里登记）
TOOLS: dict[str, Callable[[list[int]], str]] = {}


def register(func: Callable[[list[int]], str]) -> Callable[[list[int]], str]:
    """无参装饰器：把函数以 __name__ 登记进 TOOLS，并「原样返回」（不包装）。

    参考讲义 §3 Step 2：注册型装饰器不改行为，装饰的意义就在登记这个动作。
    """
    # TODO(ex3): 两行以内——登记 + 原样返回
    raise NotImplementedError("TODO(ex3): 实现 register 装饰器")


# TODO(ex3): 用 @register 定义两个报销工具（放在这里，def 体自己写）：
#   check_item_limit(items_cents) -> 任意单笔 > 5000 返回 "REJECT:ITEM_OVER_LIMIT"，否则 "PASS"
#   check_total_limit(items_cents) -> 合计 > 500000 返回 "REJECT:TOTAL_OVER_LIMIT"，否则 "PASS"


def run_tool(name: str, items_cents: list[int]) -> str:
    """按名调用 TOOLS 里的工具；名字不存在时抛 KeyError。"""
    # TODO(ex3): 查表调用；查不到就抛 KeyError（可以参考讲义 code/registry.py 的写法）
    raise NotImplementedError("TODO(ex3): 实现按名调用")
