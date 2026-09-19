"""实验③：流式一问一答——token 一段段吐出来（SSE 手撕的实测台）。

离线模式（默认）：mock 端点按片段回放 SSE 字节流。
真端点模式：uv run python code/demo_stream.py --real（需 .env；片段切分依端点而异）。
"""

from __future__ import annotations

import asyncio
import sys
import time

from client import ChatClient, ChatConfig
from mock_endpoint import MockLLMEndpoint

MESSAGES = [{"role": "user", "content": "用一句话给出报销单 CLM-2026-0003 的预审结论。"}]

FRAGMENTS = ["报销单 ", "CLM-2026-0003 ", "预审拒绝：", "REJECT:", "INVALID_AMOUNT", "（存在负数金额）。"]


async def consume(client: ChatClient) -> tuple[str, int, float]:
    parts: list[str] = []
    started = time.perf_counter()
    async for delta in client.stream(MESSAGES):
        parts.append(delta)
        print(f"  第 {len(parts):>2} 段到达: {delta!r}")
    return "".join(parts), len(parts), time.perf_counter() - started


async def run_offline() -> None:
    with MockLLMEndpoint() as ep:
        ep.script_stream(FRAGMENTS)
        async with ChatClient(ChatConfig(ep.url, "test-key", "mock-model")) as client:
            print("== async for 逐段消费（SSE data 事件 → delta.content） ==")
            text, count, elapsed = await consume(client)
            print(f"拼装结果: {text}")
            print(f"共 {count} 段，耗时 {elapsed * 1000:.1f}ms——首段到达即可开始渲染，不必等全文")


async def run_real() -> None:
    async with ChatClient(ChatConfig.from_env()) as client:
        print("== 真实端点流式（片段切分依端点/模型而异） ==")
        text, count, elapsed = await consume(client)
        print(f"拼装结果: {text}")
        print(f"共 {count} 段，耗时 {elapsed * 1000:.1f}ms")


def main() -> None:
    if "--real" in sys.argv[1:]:
        asyncio.run(run_real())
    else:
        asyncio.run(run_offline())


if __name__ == "__main__":
    main()
