"""参考答案（ex1）——先完成练习再看；不追求与你的写法一致，追求通过验收且读得舒服。"""

import asyncio

LOG: list[str] = []


async def fetch_receipt(claim_id: str, delay: float, total_cents: int) -> dict[str, int | str]:
    LOG.append(f"start:{claim_id}")
    await asyncio.sleep(delay)
    LOG.append(f"done:{claim_id}")
    return {"claim_id": claim_id, "total_cents": total_cents}


async def main() -> list[dict[str, int | str]]:
    a = await fetch_receipt("CLM-A", 0.05, 1200)
    b = await fetch_receipt("CLM-B", 0.05, 8800)
    return [a, b]


def run() -> list[dict[str, int | str]]:
    return asyncio.run(main())
