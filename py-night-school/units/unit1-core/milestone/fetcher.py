"""学段里程碑：async 并发 fetcher——从 5 个区域台账端点并发拉取报销单汇总。

三块积木（也是三个 TODO，任务书见 README.md）：
  T1 带参 retry 装饰器（装饰 async 函数：装饰器内部 async def 包装 + await）；
  T2 wait_for 超时降级（north 永远慢 -> DEGRADED 空结果）；
  T3 Semaphore(2) 限流 + 汇总报告。

状态语义：PASS（一次成功）/ RETRY_OK（重试后成功）/ DEGRADED（超时降级）。
金额单位：整数分。验收：uv run pytest（测试形态即夜校异步模板：同步 test + asyncio.run）。
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

T = TypeVar("T")

# ---------------- mock 端点层（给定，不要改） ----------------

REGIONS = ["north", "south", "east", "west", "central"]

# 各端点延迟（秒）；north「永远慢」专门喂给超时降级
REGION_DELAY: dict[str, float] = {
    "north": 0.30,
    "south": 0.05,
    "east": 0.05,
    "west": 0.08,
    "central": 0.10,
}

# mock 台账数据：每区域若干张单据的金额（整数分）
LEDGERS: dict[str, list[int]] = {
    "north": [1200, 3500, 2400],
    "south": [7100],
    "east": [8800],
    "west": [4500, 2600],
    "central": [5000],
}

# east 的不稳定性：前 2 次调用抛 TimeoutError（模拟抖动），第 3 次成功
EAST_FLAKY_TIMES = 2

# 全局拉取预算：超过即降级（专门为 north 设计）
FETCH_TIMEOUT = 0.15
# 并发上限：同时在飞的端点请求数
MAX_CONCURRENCY = 2

# ---------------- mock 观测仪表（给定，不要改；测试靠它取证） ----------------

_calls: dict[str, int] = {}
_in_flight = 0
_peak = 0


def reset_mock() -> None:
    """重置 mock 状态（每条验收测试前调用；你手动实验时也可用）。"""
    global _in_flight, _peak
    _calls.clear()
    _in_flight = 0
    _peak = 0


def call_count(region: str) -> int:
    """某端点被调用的总次数（含重试）。"""
    return _calls.get(region, 0)


def peak_concurrency() -> int:
    """「同一时刻正在请求的端点数」的最大值——限流验收的取证口。"""
    return _peak


async def fetch_region(region: str) -> list[int]:
    """mock 端点（给定，不要改）：延迟各异；east 前 2 次抛 TimeoutError，第 3 次成功。"""
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


# ---------------- T1：带参 retry 装饰器（你的实现） ----------------


def retry(
    max_retries: int = 2,
    exceptions: tuple[type[BaseException], ...] = (TimeoutError,),
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """带参重试装饰器工厂：比 L1.5 的同步装饰器多两层。

    层数自外向内：retry(max_retries=...) 收参数 -> decorator(func) 收函数 -> wrapper 干活。
    wrapper 必须是 async def（里面要 await func），于是被装饰函数保持 awaitable 签名不变。

    语义：调用被装饰函数；命中 exceptions 的异常则最多重试 max_retries 次（总共最多调用
    1 + max_retries 次）；重试耗尽仍失败则抛最后一个异常；成功则返回其结果。
    注意：CancelledError 继承自 BaseException 而非 Exception——只要你的 except 点名的是
    exceptions（如 TimeoutError），取消就会原样放行，不会破坏 wait_for 的超时机制（T2 依赖这一点）。
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> T:
            # TODO(T1): 补全重试循环（提示见 README 任务书与 hints.py）
            raise NotImplementedError("TODO(T1): 补全 wrapper 的重试循环")

        return wrapper

    return decorator


# 任务书指定的装饰器用法（给定，不要改）：east 的抖动在这层被吃掉
@retry(max_retries=2, exceptions=(TimeoutError,))
async def fetch_region_with_retry(region: str) -> list[int]:
    """raw 端点 + 重试。"""
    return await fetch_region(region)


# ---------------- T2：超时降级（你的实现） ----------------


async def fetch_region_guarded(region: str) -> tuple[list[int], bool]:
    """wait_for 给重试链套 FETCH_TIMEOUT 预算。返回 (单据列表, 是否降级)。

    超时 -> ([], True)；正常 -> (结果, False)。慢端点不该拖垮整个汇总。
    """
    # TODO(T2): 用 asyncio.wait_for 包住 fetch_region_with_retry(region)，预算 FETCH_TIMEOUT；
    # 捕获 TimeoutError 返回 ([], True)；正常返回 (结果, False)
    raise NotImplementedError("TODO(T2): 补全 fetch_region_guarded")


# ---------------- T3：限流并发 + 汇总报告（你的实现） ----------------


@dataclass
class RegionReport:
    """单区域报告。status: "PASS" | "RETRY_OK" | "DEGRADED"。"""

    region: str
    count: int
    total_cents: int
    status: str


@dataclass
class Summary:
    """总报告：按 REGIONS 顺序排列的区域报告 + 金额总计（整数分）。"""

    regions: list[RegionReport] = field(default_factory=list)
    grand_total_cents: int = 0


async def collect_all() -> Summary:
    """Semaphore(MAX_CONCURRENCY) 限流，并发拉取全部区域，产出汇总报告。

    status 判定：降级 -> "DEGRADED"；未降级但 call_count(region) > 1（发生过重试）-> "RETRY_OK"；
    否则 "PASS"。结果按 REGIONS 顺序保序。
    """
    # TODO(T3): ① asyncio.Semaphore(MAX_CONCURRENCY)；
    # ② 每区域一个 async 帮手，在 async with sem 内 await fetch_region_guarded(region)；
    # ③ 用 gather 并发驱动 5 个帮手（保序）；
    # ④ 组装 RegionReport 与 Summary（grand_total_cents = 各区域 total_cents 之和）
    raise NotImplementedError("TODO(T3): 补全 collect_all")


# ---------------- 演示入口（给定，不要改） ----------------


async def _print_report() -> None:
    reset_mock()
    t0 = asyncio.get_running_loop().time()
    summary = await collect_all()
    elapsed = asyncio.get_running_loop().time() - t0
    for r in summary.regions:
        print(f"{r.region:8} 单据数 {r.count}  金额合计 {r.total_cents:6} 分  状态 {r.status}")
    print(f"总计 {summary.grand_total_cents} 分")
    print(f"耗时 {elapsed:.3f}s（全串行约 0.6s）；峰值并发 {peak_concurrency()}；east 调用 {call_count('east')} 次")


def main() -> None:
    """uv run python fetcher.py"""
    asyncio.run(_print_report())


if __name__ == "__main__":
    main()
