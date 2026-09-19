"""Step 4：阻塞事故——三个任务里混进一个 time.sleep，全场被拖住。

三个任务都交给事件循环「并发」，理想总时长 = max(0.3, 0.1, 0.1) = 0.3s；
实际总时长 ≈ 0.4s：两个 0.1s 的任务连「开始等待」都被排到了 0.3s 之后——
因为 CLM-X 抓着唯一的线程不放，事件循环连调度别人的机会都没有。

运行：uv run python code/blocking_disaster.py
"""

import asyncio
import time

T0 = time.perf_counter()  # 进程起点：仅用于把时间戳打印成相对秒


def stamp() -> str:
    return f"[{time.perf_counter() - T0:5.2f}s]"


def note(msg: str, log: list[str]) -> None:
    """同时落日志（给测试断言用）与打印（给眼睛看时间戳）。"""
    log.append(msg)
    print(f"{stamp()} {msg}")


async def fetch_fast(claim_id: str, log: list[str]) -> str:
    note(f"start {claim_id}", log)
    await asyncio.sleep(0.1)  # 好公民：等待期间把事件循环让给别人
    note(f"done  {claim_id}", log)
    return claim_id


async def fetch_broken(claim_id: str, log: list[str]) -> str:
    note(f"start {claim_id}", log)
    time.sleep(0.3)  # 钉子户：同步阻塞 0.3s——事件循环连同所有任务一起冻结
    note(f"done  {claim_id}", log)
    return claim_id


async def run_disaster() -> tuple[list[str], list[str], float]:
    """三个任务并发拉取，其中 CLM-X 混入了 time.sleep。返回 (结果, log, 总耗时)。"""
    log: list[str] = []
    t0 = time.perf_counter()
    results = await asyncio.gather(
        fetch_broken("CLM-X", log),
        fetch_fast("CLM-Y", log),
        fetch_fast("CLM-Z", log),
    )
    return list(results), log, time.perf_counter() - t0


async def run_healthy() -> tuple[list[str], float]:
    """对照组：CLM-X 同样等 0.3s，但用 asyncio.sleep 让出。返回 (log, 总耗时)。"""
    log: list[str] = []
    t0 = time.perf_counter()
    tasks = [
        asyncio.create_task(fetch_fast("CLM-Y", log)),
        asyncio.create_task(fetch_fast("CLM-Z", log)),
    ]
    note("start CLM-X", log)
    await asyncio.sleep(0.3)  # 同样是 0.3s，但等待期间别人照常推进
    note("done  CLM-X", log)
    await asyncio.gather(*tasks)
    return log, time.perf_counter() - t0


def main() -> None:
    global T0
    print("== 事故版：CLM-X 用 time.sleep(0.3) ==")
    T0 = time.perf_counter()
    _, log, elapsed = asyncio.run(run_disaster())
    print(f"  总耗时: {elapsed:.3f}s（理想 0.3s；Y/Z 被冻到 0.3s 后才起步，再多花 0.1s）")
    print(f"  log: {log}\n")

    print("== 健康版：CLM-X 改用 await asyncio.sleep(0.3) ==")
    T0 = time.perf_counter()
    log, elapsed = asyncio.run(run_healthy())
    print(f"  总耗时: {elapsed:.3f}s（= max(0.3, 0.1, 0.1)，达到理想值）")
    print(f"  log: {log}")


if __name__ == "__main__":
    main()
