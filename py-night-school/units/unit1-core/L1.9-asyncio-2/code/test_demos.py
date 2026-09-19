"""讲义示例测试：同步 test 函数 + asyncio.run 包住真正的异步断言（夜校异步测试模板）。

对照 Java：相当于在普通 @Test 里对 CompletableFuture 调 join() 再断言——
测试本身不必「变成异步」，需要时进入异步世界取证即可。
"""

import asyncio

from cancel_demo import run_cancel, run_cpu_hog_unkillable
from semaphore_demo import MAX_CONCURRENCY, run_limited
from tasks_and_gather import REGION_ENDPOINTS, run_gather_all, run_two_tasks
from timeout_demo import DEGRADED_LEDGER, fetch_with_budget
from token_stream import OPINION_CHUNKS, consume_all, peek_first_token


def test_two_tasks_concurrent() -> None:
    async def part() -> tuple[list[str], float]:
        _, log, elapsed = await run_two_tasks()
        return log, elapsed

    log, elapsed = asyncio.run(part())
    assert log[:2] == ["start:north", "start:south"]  # 两个任务都已提交调度
    assert elapsed < 0.18  # 并发 ≈ max(0.1, 0.1)；顺序执行是 0.2 相加


def test_gather_preserves_order() -> None:
    async def part() -> tuple[list[dict[str, int | str]], list[str], float]:
        results, log, elapsed = await run_gather_all()
        return results, log, elapsed

    results, log, elapsed = asyncio.run(part())
    assert [r["region"] for r in results] == [e[0] for e in REGION_ENDPOINTS]  # 传入序 = 返回序
    assert log.index("done:south") < log.index("done:north")  # south 先完成……
    assert [r["region"] for r in results].index("south") == 1  # ……却仍排在第二位
    assert elapsed >= 0.19  # 不可能快过最慢单端点（0.2s）
    assert elapsed < 0.35  # 串行是 0.6s


def test_wait_for_degrades() -> None:
    async def part() -> tuple[dict[str, int | str], float]:
        result, elapsed = await fetch_with_budget()
        return result, elapsed

    result, elapsed = asyncio.run(part())
    assert result == DEGRADED_LEDGER  # 超时拿到降级空台账
    assert elapsed < 0.25  # 0.3s 的慢端点被 0.1s 预算掐断


def test_semaphore_caps_peak() -> None:
    async def part() -> tuple[int, float]:
        peak, _, elapsed = await run_limited()
        return peak, elapsed

    peak, elapsed = asyncio.run(part())
    assert peak <= MAX_CONCURRENCY  # 限流生效：5 端点过 2 车道闸机
    assert peak == 2  # 且确实两两并发过（不是假限流）
    assert elapsed >= 0.19  # 不可能快过最慢单端点
    assert elapsed < 0.55  # 全串行是 0.6s


def test_token_stream_collects_all() -> None:
    async def part() -> tuple[str, int]:
        return await consume_all()

    sentence, received = asyncio.run(part())
    assert sentence == "".join(OPINION_CHUNKS)
    assert received == len(OPINION_CHUNKS)


def test_peek_first_token() -> None:
    async def part() -> str:
        return await peek_first_token()

    assert asyncio.run(part()) == OPINION_CHUNKS[0]


def test_cancel_at_await_point() -> None:
    log = asyncio.run(run_cancel())
    assert "AUD-1:CANCELLED_CLEANUP" in log  # 取消在 await 点落地，清理跑了
    assert "main:观察到任务已取消" in log
    assert "AUD-1:AUDIT_OK" not in log  # 审计没跑完


def test_cpu_hog_survives_cancel() -> None:
    log = asyncio.run(run_cpu_hog_unkillable())
    # HOG 跑完了，而「想取消它」的日志排在它后面——协作式的铁证
    cancel_idx = next(i for i, entry in enumerate(log) if entry.startswith("main:cancel() 返回 False"))
    assert log.index("HOG-1:RAN_TO_COMPLETION") < cancel_idx
    assert any("取消来晚了" in entry for entry in log)
