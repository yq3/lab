"""里程碑验收（不要改本文件——它就是结业判卷老师）。

测试形态即夜校异步模板：全部是同步 test 函数，内部用 asyncio.run 包住真正的异步断言
（不引入 pytest-asyncio——模板本身就是教学点，L1.8 讲义有展开）。
全部通过 = Unit 1 结业。
"""

import asyncio
import time

import fetcher


def _collect() -> tuple[fetcher.Summary, float]:
    fetcher.reset_mock()
    t0 = time.perf_counter()
    summary = asyncio.run(fetcher.collect_all())
    return summary, time.perf_counter() - t0


def test_result_completeness() -> None:
    summary, _ = _collect()
    assert [r.region for r in summary.regions] == fetcher.REGIONS  # 5 区域齐全且保序
    assert [r.count for r in summary.regions] == [0, 1, 1, 2, 1]
    assert [r.total_cents for r in summary.regions] == [0, 7100, 8800, 7100, 5000]
    assert summary.grand_total_cents == 28000  # 金额合计（整数分）


def test_retry_happened_on_flaky_only() -> None:
    _collect()
    assert fetcher.call_count("east") == 3  # 前 2 次抖动 + 第 3 次成功（重试装饰器工作）
    assert fetcher.call_count("south") == 1  # 稳定端点不重试
    assert fetcher.call_count("west") == 1


def test_degraded_marked_for_slow_region() -> None:
    summary, _ = _collect()
    north = {r.region: r for r in summary.regions}["north"]
    assert north.status == "DEGRADED"  # 慢端点被预算掐断，拿到降级标记
    assert north.count == 0
    assert north.total_cents == 0


def test_status_kinds() -> None:
    summary, _ = _collect()
    statuses = {r.region: r.status for r in summary.regions}
    assert statuses["east"] == "RETRY_OK"  # 抖动后重试成功
    assert statuses["south"] == "PASS"  # 一次成功
    assert statuses["west"] == "PASS"
    assert statuses["central"] == "PASS"


def test_peak_concurrency_capped() -> None:
    _collect()
    peak = fetcher.peak_concurrency()
    assert peak <= fetcher.MAX_CONCURRENCY  # 限流生效：最多 2 路同时在飞
    assert peak >= 2  # 且确实两两并发过（不是假并发，也不是假限流）


def test_total_elapsed_within_budget() -> None:
    _, elapsed = _collect()
    # 全串行（重试生效、慢端点被预算掐断）约 0.46s——不并发过不了关；
    # Semaphore(2) 限流并发后约 0.25s。阈值放宽到 0.40。
    assert elapsed < 0.40
