"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio
import time

import ex2_timeout_fallback as ex2


def test_ex2_timeout_degrades_slow_keeps_fast() -> None:
    t0 = time.perf_counter()
    results = asyncio.run(ex2.fetch_two())
    elapsed = time.perf_counter() - t0

    # 快端点真值保留；慢端点拿到降级值 0
    assert results == [3500, 0]
    # 并发 + 0.1s 预算掐断 0.3s 慢端点：总耗时 ≈ 0.1s；不套预算会拖到 0.3s。阈值放宽到 0.25。
    assert elapsed < 0.25
