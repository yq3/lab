"""参考答案——先完成里程碑再看；不追求与你的写法一致，追求通过验收且读得舒服。

与 fetcher.py 的差异只有三处 TODO 的实现（T1 重试循环 / T2 超时降级 / T3 限流汇总）。
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

T = TypeVar("T")

# ---------------- mock 端点层（与学员版一致） ----------------

REGIONS = ["north", "south", "east", "west", "central"]

REGION_DELAY: dict[str, float] = {
    "north": 0.30,
    "south": 0.05,
    "east": 0.05,
    "west": 0.08,
    "central": 0.10,
}

LEDGERS: dict[str, list[int]] = {
    "north": [1200, 3500, 2400],
    "south": [7100],
    "east": [8800],
    "west": [4500, 2600],
    "central": [5000],
}

EAST_FLAKY_TIMES = 2

FETCH_TIMEOUT = 0.15
MAX_CONCURRENCY = 2

_calls: dict[str, int] = {}
_in_flight = 0
_peak = 0


def reset_mock() -> None:
    global _in_flight, _peak
    _calls.clear()
    _in_flight = 0
    _peak = 0


def call_count(region: str) -> int:
    return _calls.get(region, 0)


def peak_concurrency() -> int:
    return _peak


async def fetch_region(region: str) -> list[int]:
    global _in_flight, _peak
    _calls[region] = _calls.get(region, 0) + 1
    try:
        _in_flight += 1
        _peak = max(_peak, _in_flight)
        if region == "east" and _calls["east"] <= EAST_FLAKY_TIMES:
            await asyncio.sleep(0.01)
            raise TimeoutError(f"east endpoint flaky (attempt {_calls['east']})")
        await asyncio.sleep(REGION_DELAY[region])
        return list(LEDGERS[region])
    finally:
        _in_flight -= 1


# ---------------- T1：带参 retry 装饰器（参考实现） ----------------


def retry(
    max_retries: int = 2,
    exceptions: tuple[type[BaseException], ...] = (TimeoutError,),
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """带参重试装饰器工厂：三层嵌套，wrapper 是 async def 并保持 awaitable 签名。"""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> T:
            last_error: BaseException | None = None
            for _ in range(max_retries + 1):  # 首次 + 最多 max_retries 次重试
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_error = exc  # CancelledError 不在 exceptions 里，取消原样放行
            assert last_error is not None  # 循环走完必有一次失败
            raise last_error

        return wrapper

    return decorator


@retry(max_retries=2, exceptions=(TimeoutError,))
async def fetch_region_with_retry(region: str) -> list[int]:
    return await fetch_region(region)


# ---------------- T2：超时降级（参考实现） ----------------


async def fetch_region_guarded(region: str) -> tuple[list[int], bool]:
    try:
        receipts = await asyncio.wait_for(fetch_region_with_retry(region), timeout=FETCH_TIMEOUT)
    except TimeoutError:
        return [], True
    return receipts, False


# ---------------- T3：限流并发 + 汇总报告（参考实现） ----------------


@dataclass
class RegionReport:
    region: str
    count: int
    total_cents: int
    status: str


@dataclass
class Summary:
    regions: list[RegionReport] = field(default_factory=list)
    grand_total_cents: int = 0


async def collect_all() -> Summary:
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def collect_one(region: str) -> RegionReport:
        async with sem:
            receipts, degraded = await fetch_region_guarded(region)
        if degraded:
            status = "DEGRADED"
        elif call_count(region) > 1:
            status = "RETRY_OK"
        else:
            status = "PASS"
        return RegionReport(region, len(receipts), sum(receipts), status)

    reports = await asyncio.gather(*(collect_one(region) for region in REGIONS))
    return Summary(list(reports), sum(r.total_cents for r in reports))


async def _print_report() -> None:
    reset_mock()
    t0 = asyncio.get_running_loop().time()
    summary = await collect_all()
    elapsed = asyncio.get_running_loop().time() - t0
    for r in summary.regions:
        print(f"{r.region:8} 单据数 {r.count}  金额合计 {r.total_cents:6} 分  状态 {r.status}")
    print(f"总计 {summary.grand_total_cents} 分")
    print(f"耗时 {elapsed:.3f}s（全串行约 0.46s+）；峰值并发 {peak_concurrency()}；east 调用 {call_count('east')} 次")


def main() -> None:
    asyncio.run(_print_report())


if __name__ == "__main__":
    main()
