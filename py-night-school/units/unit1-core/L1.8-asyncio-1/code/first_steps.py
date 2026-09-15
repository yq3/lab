"""实验①与②：两个协程的「顺序 await」与「gather 并发」对照。

同样的函数、同样的延迟，只换驱动方式——总耗时从「相加」变成「最大值」。
这是你人生第一个 async 程序与第一次并发初体验（gather 的完整规格是 L1.9 的正餐）。

运行：uv run python code/first_steps.py
"""

import asyncio
import time

# 每张单据的模拟网络延迟（秒）：刻意两单相同，方便口算「相加 vs 取最大」
CLAIM_DELAY = 0.1


async def fetch_receipt(claim_id: str, log: list[str]) -> str:
    """模拟从台账端点拉取一张报销单。

    asyncio.sleep 是「异步等待」：当前协程挂起，事件循环去跑别的任务——
    对应 Java 世界里 Thread.sleep 的时间，但等待期间不占用任何线程。
    """
    log.append(f"start:{claim_id}")
    await asyncio.sleep(CLAIM_DELAY)
    log.append(f"done:{claim_id}")
    return f"{claim_id}:OK"


async def run_sequential() -> tuple[list[str], list[str], float]:
    """实验①：两个 await 排队——B 要等 A 完全结束才开始。"""
    log: list[str] = []
    t0 = time.perf_counter()
    a = await fetch_receipt("CLM-A", log)
    b = await fetch_receipt("CLM-B", log)
    return [a, b], log, time.perf_counter() - t0


async def run_gather() -> tuple[list[str], list[str], float]:
    """实验②：gather 一行换并发——两张单据同时在飞。"""
    log: list[str] = []
    t0 = time.perf_counter()
    results = await asyncio.gather(fetch_receipt("CLM-A", log), fetch_receipt("CLM-B", log))
    return list(results), log, time.perf_counter() - t0


def main() -> None:
    print("== 实验①：顺序 await（总耗时 = 两段延迟相加）==")
    results, log, elapsed = asyncio.run(run_sequential())
    print(f"  log: {log}")
    print(f"  结果: {results}")
    print(f"  总耗时: {elapsed:.3f}s ≈ {CLAIM_DELAY} + {CLAIM_DELAY}")
    print("  ——await 的字面意思：等它做完，我才能继续。\n")

    print("== 实验②：gather 并发（总耗时 ≈ 最大延迟）==")
    results, log, elapsed = asyncio.run(run_gather())
    print(f"  log: {log}")
    print(f"  结果: {results}")
    print(f"  总耗时: {elapsed:.3f}s ≈ max({CLAIM_DELAY}, {CLAIM_DELAY})——两张单据同时在飞")
    print("  ——只改了驱动方式，代码一行没动：并发是「怎么调度」的事，不是「怎么写」的事。")


if __name__ == "__main__":
    main()
