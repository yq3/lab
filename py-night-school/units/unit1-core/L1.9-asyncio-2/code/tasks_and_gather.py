"""Step 1 与 2：create_task 的「提交调度」，与 gather 的多端点并发拉取。

明线场景：报销汇总要并发拉 5 个区域台账端点——串行 0.6s，gather 并发 ≈ 0.2s（最大延迟），
且 gather 的返回结果严格按传入顺序排列（谁先完成与谁排第几无关）。

运行：uv run python code/tasks_and_gather.py
"""

import asyncio
import time

# 5 个区域台账端点的模拟延迟与单据金额合计（整数分）
REGION_ENDPOINTS: list[tuple[str, float, int]] = [
    ("north", 0.20, 8800),
    ("south", 0.05, 7100),
    ("east", 0.08, 1200),
    ("west", 0.12, 3500),
    ("central", 0.15, 2400),
]


async def fetch_region(region: str, delay: float, total_cents: int, log: list[str]) -> dict[str, int | str]:
    """mock 端点：asyncio.sleep 模拟网络延迟。"""
    log.append(f"start:{region}")
    await asyncio.sleep(delay)
    log.append(f"done:{region}")
    return {"region": region, "total_cents": total_cents}


async def run_two_tasks() -> tuple[list[dict[str, int | str]], list[str], float]:
    """Step 1：create_task 提交两个任务后再 await——两单同时在飞。

    create_task：协程立刻进入事件循环排期（「已提交调度」），返回 Task；
    随后的 await task 只是「等它出结果」，不再是「现在才开始跑」。
    """
    log: list[str] = []
    t0 = time.perf_counter()
    task_a = asyncio.create_task(fetch_region("north", 0.1, 8800, log))
    task_b = asyncio.create_task(fetch_region("south", 0.1, 7100, log))
    a = await task_a
    b = await task_b
    return [a, b], log, time.perf_counter() - t0


async def run_gather_all() -> tuple[list[dict[str, int | str]], list[str], float]:
    """Step 2：gather 一行并发拉取 5 个端点——结果按传入顺序保序。"""
    log: list[str] = []
    t0 = time.perf_counter()
    results = await asyncio.gather(
        *(fetch_region(region, delay, cents, log) for region, delay, cents in REGION_ENDPOINTS)
    )
    return list(results), log, time.perf_counter() - t0


def main() -> None:
    print("== Step 1：create_task 双任务并发 ==")
    results, log, elapsed = asyncio.run(run_two_tasks())
    print(f"  log: {log}")
    print(f"  总耗时: {elapsed:.3f}s（两个 0.1s 任务同时在飞，≈ max 而非相加）\n")

    print("== Step 2：gather 并发拉取 5 个区域台账 ==")
    results, log, elapsed = asyncio.run(run_gather_all())
    print(f"  完成序（log 里 done 的出现序）: {[e.split(':')[1] for e in log if e.startswith('done')]}")
    print(f"  结果序（gather 的返回序）:      {[r['region'] for r in results]}")
    print(f"  总耗时: {elapsed:.3f}s（串行 = 0.6s 相加；并发 ≈ 0.2s 最大延迟）")
    print("  ——south 最先完成却排在第二位：gather 按传入序交付结果，保序是它的重要契约。")


if __name__ == "__main__":
    main()
