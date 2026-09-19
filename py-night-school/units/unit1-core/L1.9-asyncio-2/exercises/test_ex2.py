"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio
import time

import ex2_timeout_fallback as ex2


def test_ex2_timeout_degrades_slow_keeps_fast() -> None:
    ex2.LOG.clear()
    t0 = time.perf_counter()
    results = asyncio.run(ex2.fetch_two())
    elapsed = time.perf_counter() - t0

    # 快端点真值保留；慢端点拿到降级值 0
    assert results == [3500, 0]
    # 总时长 < 全串行总和（0.05 + 0.3 = 0.35s）——宽松墙钟，防高负载机器上调度抖动误伤；
    # 预算是否真掐住慢端点，由上面的值断言硬证（不套预算 north 会返回 8800）
    assert elapsed < ex2.FAST_DELAY + ex2.SLOW_DELAY
    # 并发证据（与 ex1 同法）：2 个 start 都挤在任何 done 之前——串行版做不到
    assert sorted(e for e in ex2.LOG if e.startswith("start:")) == ["start:north", "start:west"]
    assert all(not e.startswith("done:") for e in ex2.LOG[:2])
