"""实验④：Semaphore(2) 限流——最多 2 个端点同时在飞，峰值眼见为实。

对应 java.util.concurrent.Semaphore：几乎同构（acquire/release vs async with），
差别只是获取名额的等待会让出事件循环而不是挂起线程。

运行：uv run python code/semaphore_demo.py
"""

import asyncio
import time

MAX_CONCURRENCY = 2  # 台账端点的礼数：同时最多 2 路请求

REGION_ENDPOINTS: list[tuple[str, float]] = [
    ("north", 0.20),
    ("south", 0.05),
    ("east", 0.08),
    ("west", 0.12),
    ("central", 0.15),
]


class Gauge:
    """在飞计数器：记录「同一时刻正在请求的端点数」的最大值（峰值）。"""

    def __init__(self) -> None:
        self.in_flight = 0
        self.peak = 0

    def enter(self) -> None:
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)

    def exit(self) -> None:
        self.in_flight -= 1


async def fetch(region: str, delay: float, gauge: Gauge, log: list[str]) -> str:
    log.append(f"start:{region}")
    try:
        gauge.enter()
        await asyncio.sleep(delay)
    finally:
        gauge.exit()
    log.append(f"done:{region}")
    return region


async def limited_fetch(region: str, delay: float, sem: asyncio.Semaphore, gauge: Gauge, log: list[str]) -> str:
    # 经典四行限流模式的第一行：async with sem 拿名额，出块自动还名额
    async with sem:
        return await fetch(region, delay, gauge, log)


async def run_limited() -> tuple[int, list[str], float]:
    """Semaphore(2) 下并发拉 5 端点。返回 (峰值并发, log, 总耗时)。"""
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    gauge = Gauge()
    log: list[str] = []
    t0 = time.perf_counter()
    await asyncio.gather(*(limited_fetch(r, d, sem, gauge, log) for r, d in REGION_ENDPOINTS))
    return gauge.peak, log, time.perf_counter() - t0


def main() -> None:
    peak, log, elapsed = asyncio.run(run_limited())
    print(f"峰值并发: {peak}（上限 {MAX_CONCURRENCY}——5 个端点排队过 2 车道闸机）")
    print(f"log: {log}")
    print(f"总耗时: {elapsed:.3f}s（全串行 = 0.6s；2 车道排队 ≈ 0.4s）")


if __name__ == "__main__":
    main()
