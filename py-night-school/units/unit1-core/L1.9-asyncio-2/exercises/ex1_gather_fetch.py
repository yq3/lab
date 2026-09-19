# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""gather 并发拉取补全：5 个区域台账端点，结果保序 + 总耗时 = 最大延迟。

考察点：gather 提交并发、按传入顺序保序收集。
完成判据：uv run pytest exercises/test_ex1.py 全绿——
  结果顺序 = 端点表顺序；总时长 < 阈值（全串行是 0.6s）；5 个 start 挤在最前（并发证据）。
"""

import asyncio

# 区域 -> (模拟延迟秒, 单据金额合计·整数分)。均为 mock 端点，不要改。
REGION_ENDPOINTS: dict[str, tuple[float, int]] = {
    "north": (0.20, 8800),
    "south": (0.05, 7100),
    "east": (0.08, 1200),
    "west": (0.12, 3500),
    "central": (0.15, 2400),
}

LOG: list[str] = []


async def fetch_region(region: str) -> dict[str, int | str]:
    """mock 端点（给定，不要改）：按上表延迟返回该区域汇总。"""
    delay, total_cents = REGION_ENDPOINTS[region]
    LOG.append(f"start:{region}")
    await asyncio.sleep(delay)
    LOG.append(f"done:{region}")
    return {"region": region, "total_cents": total_cents}


async def fetch_all() -> list[dict[str, int | str]]:
    """并发拉取全部 5 个区域，结果顺序与 REGION_ENDPOINTS 的迭代序一致。"""
    # TODO(ex1): 用 asyncio.gather 并发驱动 5 个 fetch_region（生成器表达式展开即可），
    # 返回 gather 的结果——它天然按传入顺序排列
    raise NotImplementedError("TODO(ex1): 补全 fetch_all")
