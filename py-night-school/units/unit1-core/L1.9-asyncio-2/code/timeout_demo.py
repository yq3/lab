"""实验③：wait_for 超时——慢端点 0.3s，预算 0.1s，超时降级默认值。

对应 Java 里给 HTTP 调用设 read timeout + fallback 的老习惯；asyncio 的版本是
wait_for（或 3.11+ 的 asyncio.timeout 上下文管理器），超时抛 TimeoutError，捕获后降级。

运行：uv run python code/timeout_demo.py
"""

import asyncio
import time

SLOW_DELAY = 0.3  # north 端点「永远慢」：0.3s 才响应
TIMEOUT_SECONDS = 0.1  # 我们给它的预算

OK_LEDGER: dict[str, int | str] = {"region": "north", "total_cents": 8800, "status": "PASS"}
DEGRADED_LEDGER: dict[str, int | str] = {"region": "north", "total_cents": 0, "status": "DEGRADED"}


async def fetch_slow_ledger() -> dict[str, int | str]:
    """永远拉不动的慢端点（0.3s 才响应）。"""
    await asyncio.sleep(SLOW_DELAY)
    return OK_LEDGER


async def fetch_with_budget() -> tuple[dict[str, int | str], float]:
    """给拉取套 0.1s 预算：超时则捕获 TimeoutError，返回降级空台账。"""
    t0 = time.perf_counter()
    try:
        result = await asyncio.wait_for(fetch_slow_ledger(), timeout=TIMEOUT_SECONDS)
    except TimeoutError:
        # 3.11 起 asyncio.TimeoutError 就是内建 TimeoutError 的别名——except 这一个就够
        result = DEGRADED_LEDGER
    return result, time.perf_counter() - t0


def main() -> None:
    result, elapsed = asyncio.run(fetch_with_budget())
    print(f"结果: {result}")
    print(f"总耗时: {elapsed:.3f}s（慢端点要 0.3s，预算 0.1s 在到点时把它掐断）")
    print("——超时不是异常事故，是设计内的降级路径：拿 DEGRADED 空台账继续汇总。")


if __name__ == "__main__":
    main()
