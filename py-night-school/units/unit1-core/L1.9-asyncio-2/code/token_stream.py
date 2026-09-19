"""Step 5：异步生成器——LLM 流式输出的机制彩排（L2.1 手撕 SSE 的直接前置）。

mock「模型」把审批意见按词吐出：async def + yield 定义异步生成器，
async for 消费整条流，await anext(...) 手动推进一次。
LLM 的流式输出就是这个形状：token 一段段到达，消费端一段段处理。

运行：uv run python code/token_stream.py
"""

import asyncio
from collections.abc import AsyncGenerator

# mock 模型的分段（把 token 粒度夸张成词，便于肉眼看清节奏）
OPINION_CHUNKS: list[str] = ["单据", "CLM-2026-0001", "金额", "1200", "分", "，", "结论", "PASS"]


async def stream_opinion() -> AsyncGenerator[str, None]:
    """异步生成器：async def + yield。每段之前 await 一次，模拟网络节奏。

    注解小课：消费方只 async for 时，注解通常写 AsyncIterator[str]（消费视角）；
    本演示要调 aclose() 手动关流，那是 AsyncGenerator 才有的方法，故用全功能注解。
    """
    for chunk in OPINION_CHUNKS:
        await asyncio.sleep(0.02)  # 模拟「下一段 token 还在路上」
        yield chunk


async def consume_all() -> tuple[str, int]:
    """async for 消费：token 一段段到达，一段段处理，最后拼成完整意见。"""
    parts: list[str] = []
    received = 0
    async for chunk in stream_opinion():
        parts.append(chunk)
        received += 1
    return "".join(parts), received


async def peek_first_token() -> str:
    """await anext(...) 手动推进一次：不等整条流，只取第一个 token。

    anext(stream) 是「异步版 next()」；不想继续消费就 aclose() 关流。
    """
    stream = stream_opinion()
    first = await anext(stream)
    await stream.aclose()
    return first


def main() -> None:
    sentence, received = asyncio.run(consume_all())
    print(f"async for 消费完毕: 「{sentence}」（共 {received} 段）")
    first = asyncio.run(peek_first_token())
    print(f"anext 手动推进一段: 「{first}」——首 token 到手即可开始渲染，不必等全文")


if __name__ == "__main__":
    main()
