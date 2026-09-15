"""参考答案（ex3）——先完成练习再看。

与同步生成器逐字对照：yield 一字不改，只是在它前面加一个 await；
消费端 for -> async for。这就是 L2.1 手撕 SSE 流式解析的全部语法定义。
"""

import asyncio
from collections.abc import AsyncIterator

CHUNK_DELAY = 0.02
CHUNKS: list[str] = ["报销单", "CLM-07", "预审", "通过", "，", "金额", "1200", "分"]


async def stream_review() -> AsyncIterator[str]:
    for chunk in CHUNKS:
        await asyncio.sleep(CHUNK_DELAY)  # 模拟「下一段 token 还在路上」
        yield chunk


async def collect() -> tuple[str, int]:
    parts: list[str] = []
    received = 0
    async for chunk in stream_review():
        parts.append(chunk)
        received += 1
    return "".join(parts), received
