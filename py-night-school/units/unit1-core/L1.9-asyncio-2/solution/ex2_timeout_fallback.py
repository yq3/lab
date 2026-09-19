"""参考答案（ex2）——先完成练习再看。

wait_for 的预算掐断 + TimeoutError 捕获降级，就是毕业设计执行层
「慢端点不拖垮汇总」的最小完整版。
"""

import asyncio

TIMEOUT_SECONDS = 0.1
FAST_DELAY = 0.05
SLOW_DELAY = 0.3

AMOUNTS: dict[str, int] = {"west": 3500, "north": 8800}

LOG: list[str] = []  # 并发证据用（与 ex1 同法）：start/done 事件按发生顺序入册


async def fetch_ledger(region: str) -> int:
    LOG.append(f"start:{region}")
    await asyncio.sleep(SLOW_DELAY if region == "north" else FAST_DELAY)
    LOG.append(f"done:{region}")
    return AMOUNTS[region]


async def fetch_with_fallback(region: str) -> int:
    try:
        return await asyncio.wait_for(fetch_ledger(region), timeout=TIMEOUT_SECONDS)
    except TimeoutError:
        return 0  # 降级：本次没拉到，先按空台账处理


async def fetch_two() -> list[int]:
    results = await asyncio.gather(fetch_with_fallback("west"), fetch_with_fallback("north"))
    return list(results)
