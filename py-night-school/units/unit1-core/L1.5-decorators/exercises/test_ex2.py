"""练习 2 验收（不要改本文件——它就是你的判卷老师）。

用「可控失败次数」的 mock 函数驱动：flaky 前两次失败、第三次成功。
"""

import pytest

from ex2_retry import retry


def test_ex2_succeeds_within_budget() -> None:
    calls: list[int] = []

    @retry(max_attempts=3, retry_on=(ConnectionError,))
    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError(f"第 {len(calls)} 次失败")
        return "PASS"

    assert flaky() == "PASS"  # 三次中两次失败，仍成功
    assert len(calls) == 3


def test_ex2_exhausted_raises_last_exception() -> None:
    calls: list[int] = []

    @retry(max_attempts=3, retry_on=(ConnectionError,))
    def always_down() -> str:
        calls.append(1)
        raise ConnectionError(f"第 {len(calls)} 次失败")

    with pytest.raises(ConnectionError, match="第 3 次失败"):
        always_down()  # 耗尽：抛的是「最后一次」异常
    assert len(calls) == 3


def test_ex2_success_never_retries() -> None:
    calls: list[int] = []

    @retry(max_attempts=3)
    def always_ok() -> str:
        calls.append(1)
        return "PASS"

    assert always_ok() == "PASS"
    assert len(calls) == 1


def test_ex2_unlisted_exception_propagates_immediately() -> None:
    calls: list[int] = []

    @retry(max_attempts=3, retry_on=(TimeoutError,))
    def wrong_kind() -> str:
        calls.append(1)
        raise ConnectionError("不在重试名单")

    with pytest.raises(ConnectionError):
        wrong_kind()
    assert len(calls) == 1  # 名单外异常：不重试，立刻上抛
