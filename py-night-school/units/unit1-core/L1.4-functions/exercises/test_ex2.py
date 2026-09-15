"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

import inspect

from ex2_closures import make_counter, make_greeter


def test_ex2_greeter_format() -> None:
    greeter = make_greeter("晚上好")
    assert greeter("王工") == "晚上好，王工！"


def test_ex2_greeters_are_independent() -> None:
    evening = make_greeter("晚上好")
    morning = make_greeter("早上好")
    assert evening("王工") == "晚上好，王工！"
    assert morning("王工") == "早上好，王工！"


def test_ex2_counter_sequence() -> None:
    counter = make_counter()
    assert [counter(), counter(), counter()] == [1, 2, 3]


def test_ex2_counter_start_and_step() -> None:
    assert make_counter(100, 10)() == 110
    assert make_counter(step=5)() == 5


def test_ex2_counters_do_not_share_state() -> None:
    # state 必须活在闭包环境里：全局变量版在这里穿帮（两个计数器互相推进）
    a = make_counter()
    b = make_counter()
    a()
    a()
    assert b() == 1
    assert a() == 3


def test_ex2_counter_uses_nonlocal() -> None:
    """题目要求「必须用到 nonlocal」的机器判定：检查 make_counter 源码。"""
    source = inspect.getsource(make_counter)
    assert "nonlocal" in source, "make_counter 必须用 nonlocal 推进闭包状态"
