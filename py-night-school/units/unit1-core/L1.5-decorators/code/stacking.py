"""叠放顺序实验——两个装饰器各打一行日志，看清「自下而上应用」。

运行本文件：
    uv run python code/stacking.py

预期输出（先看讲义 §2 的展开规则再回来对照）：
    [apply] b 正在包装 audit      <- import/def 时就发生（离函数近的先应用）
    [apply] a 正在包装 audit      <- 包的是「b 已经包过的 audit」
    [call ] a 的前置              <- 调用时：洋葱外层先说话
    [call ] b 的前置
    PASS
"""

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def _log_deco(label: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """做一个「调用前打印 label」的装饰器（用函数造装饰器，顺便复习闭包）。"""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        print(f"[apply] {label} 正在包装 {func.__name__}")  # def 的瞬间就会打印——装饰器立即执行

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            print(f"[call ] {label} 的前置")
            return func(*args, **kwargs)

        return wrapper

    return decorator


a = _log_deco("a")
b = _log_deco("b")


# @a @b 叠放 ≡ audit = a(b(audit))：离函数近的（b）先应用，像穿衣服由内向外
@a
@b
def audit(items_cents: list[int]) -> str:
    """单笔 > 5000 分拒绝的旧规则。"""
    if any(c > 5000 for c in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    return "PASS"


if __name__ == "__main__":
    print(audit([1200, 3500]))  # 调用时：a 前置 -> b 前置 -> audit 本体

    # 手工展开验证：下面两行与「@a @b 叠放」完全等价（对照 Java——Java 注解没有这种展开式）
    def raw_audit(items_cents: list[int]) -> str:
        if any(c > 5000 for c in items_cents):
            return "REJECT:ITEM_OVER_LIMIT"
        return "PASS"

    manual = a(b(raw_audit))  # 直译：先 b 后 a
    print(manual([8800]))  # REJECT:ITEM_OVER_LIMIT，行为与 audit 一致
