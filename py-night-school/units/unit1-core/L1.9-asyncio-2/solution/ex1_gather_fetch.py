"""参考答案（ex1）——先完成练习再看；不追求与你的写法一致，追求通过验收且读得舒服。"""

import asyncio

REGION_ENDPOINTS: dict[str, tuple[float, int]] = {
    "north": (0.20, 8800),
    "south": (0.05, 7100),
    "east": (0.08, 1200),
    "west": (0.12, 3500),
    "central": (0.15, 2400),
}

LOG: list[str] = []


async def fetch_region(region: str) -> dict[str, int | str]:
    delay, total_cents = REGION_ENDPOINTS[region]
    LOG.append(f"start:{region}")
    await asyncio.sleep(delay)
    LOG.append(f"done:{region}")
    return {"region": region, "total_cents": total_cents}


async def fetch_all() -> list[dict[str, int | str]]:
    results = await asyncio.gather(*(fetch_region(region) for region in REGION_ENDPOINTS))
    return list(results)
