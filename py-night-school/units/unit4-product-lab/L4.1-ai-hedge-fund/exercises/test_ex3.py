"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import ex3_limits as ex3


def test_single_cap_fires_before_total_and_order_is_recorded() -> None:
    result = ex3.apply_limits({"A": 8000, "B": 6000}, 5000, 8000)
    assert result.amounts == {"A": 4000, "B": 4000}
    kinds = [c.limit for c in result.clamps]
    assert kinds == ["max_single_cents", "max_single_cents", "max_dept_total_cents"]  # 先单后总
    single_a, single_b, total = result.clamps
    assert (single_a.item, single_a.before, single_a.after) == ("A", 8000, 5000)
    assert (single_b.item, single_b.before, single_b.after) == ("B", 6000, 5000)
    assert (total.item, total.before, total.after) == (None, 10000, 8000)


def test_only_shrink_never_grow_and_floor_keeps_sum_under_cap() -> None:
    untouched = ex3.apply_limits({"A": 3000, "B": 800}, 5000, 4000)
    assert untouched.amounts == {"A": 3000, "B": 800}  # 不该动的金额一个不动
    assert untouched.clamps == []  # 也没有事件
    awkward = ex3.apply_limits({"A": 3334, "B": 3333, "C": 3333}, 5000, 8000)
    assert awkward.amounts == {"A": 2667, "B": 2666, "C": 2666}  # floor(0.8 * x)
    assert sum(awkward.amounts.values()) == 7999 <= 8000  # 只缩不放：总和压到上限以内
    assert all(a <= b for a, b in zip(awkward.amounts.values(), (3334, 3333, 3333), strict=False))


def test_events_match_final_amounts() -> None:
    """对账：批次级事件的 after 恰是结果表总和；单笔事件的 after 是封顶值，缩后只会更低。"""
    result = ex3.apply_limits({"A": 8000, "B": 6000}, 5000, 8000)
    total = result.clamps[-1]
    assert total.limit == "max_dept_total_cents"
    assert total.after == sum(result.amounts.values())  # 记缩后真总和，不是上限值
    for clamp in result.clamps[:-1]:
        assert clamp.item is not None
        assert clamp.after == 5000  # 单笔刀的落点是封顶值
        assert result.amounts[clamp.item] <= clamp.after  # 后续等比缩只可能再降
    only_single = ex3.apply_limits({"A": 8800, "B": 1200}, 5000, 10000)  # 无总额刀的场景
    assert only_single.clamps[0].after == only_single.amounts["A"]  # 此时落点恰是结果表的值


def test_idempotent_double_run() -> None:
    first = ex3.apply_limits({"A": 8000, "B": 6000}, 5000, 8000)
    second = ex3.apply_limits(first.amounts, 5000, 8000)
    assert second.amounts == first.amounts  # 双跑全等
    assert second.clamps == []  # 第二遍零事件——先单后总的顺序保证了这一点
