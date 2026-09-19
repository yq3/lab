"""讲义示例测试：叠放顺序（应用自下而上、调用由外向内、与手工展开等价）。"""

from collections.abc import Callable
from typing import ParamSpec, TypeVar

from stacking import audit

P = ParamSpec("P")
R = TypeVar("R")


def _tracer(label: str, log: list[str]) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """本地造一个「记录调用顺序」的装饰器，避免依赖打印。"""

    def deco(func: Callable[P, R]) -> Callable[P, R]:
        def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            log.append(f"call:{label}")
            return func(*args, **kwargs)

        return inner

    return deco


def test_stacked_audit_works() -> None:
    assert audit([1200, 3500]) == "PASS"
    assert audit([8800]) == "REJECT:ITEM_OVER_LIMIT"


def test_stacked_call_order_is_outside_in() -> None:
    log: list[str] = []

    @_tracer("a", log)
    @_tracer("b", log)
    def audited(items_cents: list[int]) -> str:
        log.append("raw")
        return "PASS"

    assert audited([1]) == "PASS"
    assert log == ["call:a", "call:b", "raw"]  # 洋葱：外层装饰器先说话


def test_unroll_equivalence() -> None:
    # @tracer_a @tracer_b ≡ tracer_a(tracer_b(f)) 的直译——行为完全一致
    log1: list[str] = []
    log2: list[str] = []

    @_tracer("a", log1)
    @_tracer("b", log1)
    def sugared(items_cents: list[int]) -> str:
        log1.append("raw")
        return "REJECT:ITEM_OVER_LIMIT"

    def raw(items_cents: list[int]) -> str:
        log2.append("raw")
        return "REJECT:ITEM_OVER_LIMIT"

    manual = _tracer("a", log2)(_tracer("b", log2)(raw))

    assert sugared([8800]) == manual([8800])
    assert log1 == log2 == ["call:a", "call:b", "raw"]
