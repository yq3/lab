"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from time import sleep

from ex1_timing import TIMINGS, timing


def test_ex1_return_passthrough() -> None:
    @timing
    def precheck() -> str:
        return "PASS"

    assert precheck() == "PASS"


def test_ex1_arguments_flow_through() -> None:
    @timing
    def audit() -> int:
        return 42

    assert audit() == 42


def test_ex1_records_one_timing_per_call() -> None:
    TIMINGS.clear()

    @timing
    def slow() -> None:
        sleep(0.02)

    slow()
    slow()
    assert len(TIMINGS) == 2  # 一次调用一条记录
    assert all(t >= 0.02 for t in TIMINGS)  # 真的计到了耗时（sleep 至少 0.02s）


def test_ex1_wraps_metadata_preserved() -> None:
    @timing
    def preapprove_v2() -> str:
        """预审 v2。"""
        return "PASS"

    assert preapprove_v2.__name__ == "preapprove_v2"
    assert preapprove_v2.__doc__ == "预审 v2。"
