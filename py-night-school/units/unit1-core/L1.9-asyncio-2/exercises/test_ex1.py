"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio
import time

import ex1_gather_fetch as ex1


def test_ex1_gather_preserves_order() -> None:
    ex1.LOG.clear()
    results = asyncio.run(ex1.fetch_all())
    assert [r["region"] for r in results] == list(ex1.REGION_ENDPOINTS)
    assert [r["total_cents"] for r in results] == [8800, 7100, 1200, 3500, 2400]


def test_ex1_concurrent_cost_is_max() -> None:
    ex1.LOG.clear()
    t0 = time.perf_counter()
    asyncio.run(ex1.fetch_all())
    elapsed = time.perf_counter() - t0

    # 5 端点全串行 = 0.6s 相加；并发 ≈ 0.2s（最大延迟）。阈值放宽到 0.35。
    assert elapsed < 0.35
    # 并发证据：5 个 start 全部排在前 5 位——任何 done 之前（串行版做不到）
    starts = [e for e in ex1.LOG if e.startswith("start:")]
    assert starts == ex1.LOG[:5] == [f"start:{r}" for r in ex1.REGION_ENDPOINTS]
