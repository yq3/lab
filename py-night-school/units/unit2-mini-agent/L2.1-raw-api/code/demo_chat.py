"""实验②：非流式一问一答——看 messages 进，看 choices 出。

离线模式（默认）：起本地 mock 端点，请求/响应全程打印，可反复复现。
真端点模式：uv run python code/demo_chat.py --real（需先配好 .env，输出依端点而异）。
"""

from __future__ import annotations

import asyncio
import sys

from client import ChatClient, ChatConfig
from mock_endpoint import MockLLMEndpoint

MESSAGES = [
    {"role": "system", "content": "你是财务预审助手，结论只用 PASS 或 REJECT:<原因>。"},
    {"role": "user", "content": "预审报销单 CLM-2026-0001，明细：1200、3500、2400（单位：分）。"},
]


def show_request(request_body: dict) -> None:
    print("== 端点收到了什么（请求体骨架） ==")
    print(f"  model: {request_body['model']}  stream: {request_body.get('stream', False)}")
    print(f"  messages: {len(request_body['messages'])} 条")
    for message in request_body["messages"]:
        preview = message["content"][:18] + ("…" if len(message["content"]) > 18 else "")
        print(f"    - {message['role']}: {preview}")


async def run_offline() -> None:
    with MockLLMEndpoint() as ep:
        ep.script_text("报销单 CLM-2026-0001 预审通过：三笔明细均合规，合计 7100 分未超总额上限。")
        async with ChatClient(ChatConfig(ep.url, "test-key", "mock-model")) as client:
            response = await client.complete(MESSAGES)
            show_request(ep.requests[0])
            choice = response["choices"][0]
            print("== 我们拿到了什么（响应骨架） ==")
            print(f"  message.content: {choice['message']['content']}")
            print(f"  finish_reason:   {choice['finish_reason']}")
            print(f"  usage:           {response['usage']}")


async def run_real() -> None:
    async with ChatClient(ChatConfig.from_env()) as client:
        response = await client.complete(MESSAGES)
        choice = response["choices"][0]
        print(f"[真实端点 {client.model}] {choice['message']['content']}")
        print(f"finish_reason: {choice['finish_reason']}  usage: {response.get('usage')}")


def main() -> None:
    if "--real" in sys.argv[1:]:
        asyncio.run(run_real())
    else:
        asyncio.run(run_offline())


if __name__ == "__main__":
    main()
