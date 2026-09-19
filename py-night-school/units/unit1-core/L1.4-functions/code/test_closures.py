"""讲义示例测试：闭包工厂的读捕获、写捕获（nonlocal）与状态隔离。"""

from closures import make_counter, make_threshold


def test_threshold_reads_captured_limit() -> None:
    exceeds = make_threshold(5000)
    assert exceeds(5000) is False  # 边界：恰好等于上限不算超
    assert exceeds(5001) is True


def test_two_thresholds_are_independent() -> None:
    # 两次工厂调用 = 两套独立的闭包环境，互不串扰
    assert make_threshold(5000)(6000) is True
    assert make_threshold(6000)(6000) is False


def test_counter_writes_state_via_nonlocal() -> None:
    counter = make_counter()
    assert [counter(), counter(), counter()] == [1, 2, 3]


def test_counter_step_and_start() -> None:
    assert [make_counter(100, 10)(), make_counter(100, 10)()] == [110, 110]  # 新工厂从起点重计
    assert make_counter(step=5)() == 5


def test_counters_do_not_share_state() -> None:
    # state 活在闭包环境里，不是全局变量：两个计数器各数各的
    a = make_counter()
    b = make_counter()
    a()  # 推进两次：1、2
    a()
    assert b() == 1
    assert a() == 3
