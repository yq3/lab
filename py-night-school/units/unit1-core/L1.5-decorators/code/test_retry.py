"""讲义示例测试：带参 retry 装饰器（三次中两次失败仍成功）。"""

import pytest

from retry import fetch_exchange_rate


def test_flaky_succeeds_after_two_failures() -> None:
    # mock：第 1、2 次抛 ConnectionError，第 3 次成功——@retry 让调用方无感
    assert fetch_exchange_rate() == 719


def test_exhausted_raises_last_exception() -> None:
    from retry import retry

    calls: list[int] = []

    @retry(max_attempts=2, retry_on=(ConnectionError,))
    def always_down() -> str:
        calls.append(1)
        raise ConnectionError(f"第 {len(calls)} 次失败")

    with pytest.raises(ConnectionError, match="第 2 次失败"):  # 抛的是「最后一次」异常
        always_down()
    assert len(calls) == 2


def test_retry_only_listed_exceptions() -> None:
    from retry import retry

    calls: list[int] = []

    @retry(max_attempts=3, retry_on=(TimeoutError,))
    def wrong_kind() -> str:
        calls.append(1)
        raise ConnectionError("不在重试名单")

    with pytest.raises(ConnectionError):
        wrong_kind()
    assert len(calls) == 1  # 名单外异常：一次都不重试，立刻上抛
