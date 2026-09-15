"""实验②：注册表驱动的三回合工具对话（L2.1 的两回合升级版，全部走注册表）。

mock 剧本：user 报单号 → 模型先 get_claim 查明细 → 再 preapprove 预审 → 最终结论。
真端点模式：uv run python code/demo_registry.py --real（需 .env；模型自己决定调序）。
"""

from __future__ import annotations

import asyncio
import sys

import finance  # noqa: F401 —— import 即注册
from client import ChatClient, ChatConfig
from mock_endpoint import MockLLMEndpoint
from tools import TOOL_REGISTRY, run_tool, to_openai_tools

SYSTEM = "你是财务预审助手：先用 get_claim 查单据明细，再用 preapprove 预审，最后按结果回答。"
USER = "请审查报销单 CLM-2026-0002。"


def execute_and_feed(messages: list[dict], assistant_message: dict) -> None:
    """执行一条 assistant 消息里的全部 tool_calls 并回喂（L2.1 ex3 的注册表版）。"""
    messages.append(assistant_message)
    for tool_call in assistant_message["tool_calls"]:
        name = tool_call["function"]["name"]
        arguments_json = tool_call["function"]["arguments"]
        result = run_tool(name, arguments_json)
        print(f"  -> {name}({arguments_json})")
        print(f"     结果: {result}")
        messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result})


async def run_offline() -> None:
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls([{"id": "call_001", "name": "get_claim", "arguments": {"claim_id": "CLM-2026-0002"}}])
        ep.script_tool_calls([{"id": "call_002", "name": "preapprove", "arguments": {"items_cents": [8800]}}])
        ep.script_text("报销单 CLM-2026-0002（项目验收宴请）预审拒绝：单笔 8800 分超过 5000 分上限。")
        async with ChatClient(ChatConfig(ep.url, "test-key", "mock-model")) as client:
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}]
            tools = to_openai_tools()
            print(f"== 随请求下发的工具契约: {sorted(TOOL_REGISTRY)} ==\n== 对话开始 ==")
            while True:
                response = await client.complete(messages, tools=tools)
                assistant_message = response["choices"][0]["message"]
                if assistant_message.get("tool_calls"):
                    execute_and_feed(messages, assistant_message)
                    continue
                messages.append(assistant_message)
                print(f"  [最终回答] {assistant_message['content']}")
                break


async def run_real() -> None:
    from env_loader import load_env

    load_env()
    config = ChatConfig.from_env()
    async with ChatClient(config) as client:
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}]
        tools = to_openai_tools()
        for _ in range(6):  # 真端点也给自己上个轮数护栏（L2.3 的预告）
            response = await client.complete(messages, tools=tools)
            assistant_message = response["choices"][0]["message"]
            if assistant_message.get("tool_calls"):
                execute_and_feed(messages, assistant_message)
                continue
            print(f"[最终回答] {assistant_message['content']}")
            return
        print("达到轮数上限，强制收束")


def main() -> None:
    if "--real" in sys.argv[1:]:
        asyncio.run(run_real())
    else:
        asyncio.run(run_offline())


if __name__ == "__main__":
    main()
