"""参考答案（ex2）——先完成练习再看。

修法只有一行：time.sleep(VERIFY_DELAY) -> await asyncio.sleep(VERIFY_DELAY)，
外加删掉不再使用的 import time。
对照着想 Java：虚拟线程里 Thread.sleep 合法且无害；协程里 time.sleep 是全场事故。
"""

import asyncio

LOG: list[str] = []

VERIFY_DELAY = 0.08  # 查重接口的模拟网络延迟
RULE_DELAY = 0.04  # 规则引擎的模拟计算延迟


async def verify_claim(claim_id: str) -> str:
    LOG.append(f"start:{claim_id}")
    await asyncio.sleep(VERIFY_DELAY)
    LOG.append(f"rechecked:{claim_id}")
    await asyncio.sleep(RULE_DELAY)
    LOG.append(f"done:{claim_id}")
    return f"PASS:{claim_id}"


async def verify_three() -> list[str]:
    results = await asyncio.gather(
        verify_claim("CLM-A"),
        verify_claim("CLM-B"),
        verify_claim("CLM-C"),
    )
    return list(results)
