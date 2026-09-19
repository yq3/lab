"""讲义示例测试：timing 装饰器（透传、计时、wraps 元数据）。"""

from time import sleep

from timing import timing


def test_return_passthrough() -> None:
    @timing
    def precheck() -> str:
        return "PASS"

    assert precheck() == "PASS"


def test_arguments_passthrough() -> None:
    @timing
    def audit(items_cents: list[int]) -> str:
        if any(c > 5000 for c in items_cents):
            return "REJECT:ITEM_OVER_LIMIT"
        return "PASS"

    assert audit([8800]) == "REJECT:ITEM_OVER_LIMIT"
    assert audit([1200]) == "PASS"


def test_timing_is_measured() -> None:
    recorded: list[float] = []

    def slow() -> None:
        sleep(0.02)
        recorded.append(1.0)

    slow_timed = timing(slow)
    slow_timed()
    assert recorded == [1.0]  # 原函数副作用完整保留


def test_wraps_metadata_preserved() -> None:
    @timing
    def preapprove_v2() -> str:
        """预审 v2。"""
        return "PASS"

    # wraps 的作用：元数据没被 wrapper 顶掉（§5 陷阱的正面示例）
    assert preapprove_v2.__name__ == "preapprove_v2"
    assert preapprove_v2.__doc__ == "预审 v2。"
