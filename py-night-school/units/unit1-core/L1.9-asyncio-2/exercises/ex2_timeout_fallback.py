# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""wait_for 超时降级：慢端点给默认空结果，快端点结果保留。

考察点：wait_for 套预算 + 捕获 TimeoutError + 降级值返回；gather 并发驱动。
完成判据：uv run pytest exercises/test_ex2.py 全绿——
  west 快端点拿到真实值；north 慢端点降级为 0；总时长 < 全串行总和；2 个 start 挤在最前（并发证据）。
"""

import asyncio

TIMEOUT_SECONDS = 0.1  # 每个端点的拉取预算
FAST_DELAY = 0.05  # west 的延迟
SLOW_DELAY = 0.3  # north「永远慢」

# mock 数据·整数分：两个区域各自的台账金额合计
AMOUNTS: dict[str, int] = {"west": 3500, "north": 8800}

LOG: list[str] = []  # 并发证据用（与 ex1 同法）：start/done 事件按发生顺序入册


async def fetch_ledger(region: str) -> int:
    """mock 端点（给定，不要改）：west 快，north 永远慢。"""
    LOG.append(f"start:{region}")
    await asyncio.sleep(SLOW_DELAY if region == "north" else FAST_DELAY)
    LOG.append(f"done:{region}")
    return AMOUNTS[region]


async def fetch_with_fallback(region: str) -> int:
    """带预算的拉取：超时则返回降级值 0（「本次没拉到，先按空台账处理」）。"""
    # TODO(ex2): 用 asyncio.wait_for 给 fetch_ledger(region) 套 TIMEOUT_SECONDS 预算；
    # 捕获 TimeoutError 返回 0；正常则返回端点结果
    raise NotImplementedError("TODO(ex2): 补全 fetch_with_fallback")


async def fetch_two() -> list[int]:
    """并发拉 west（快）与 north（慢），返回 [west 的结果, north 的结果]。"""
    # TODO(ex2): 用 asyncio.gather 并发驱动两个 fetch_with_fallback，返回结果列表
    raise NotImplementedError("TODO(ex2): 补全 fetch_two")
