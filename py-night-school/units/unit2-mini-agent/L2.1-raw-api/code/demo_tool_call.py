"""实验④：工具调用两回合——tools 下行、tool_calls 上行、role=tool 回喂（完整时序）。

这是 function calling 协议的最小完整标本，也是 L2.3 ReAct 循环的单圈原型。
离线模式（默认）用 mock 端点脚本化两回合；真端点模式 --real 需 .env（模型是否选工具不可脚本化，
多试几张单据观察）。
"""

from __future__ import annotations

import asyncio
import json
import sys

from client import ChatClient, ChatConfig
from mock_endpoint import MockLLMEndpoint

# L0.1 的预审规则原样复刻——今晚它第一次被「模型」调用
ITEM_LIMIT_CENTS = 5000
TOTAL_LIMIT_CENTS = 500000


def preapprove(items_cents: list[int]) -> str:
    if any(cents <= 0 for cents in items_cents):
        return "REJECT:INVALID_AMOUNT"
    if any(cents > ITEM_LIMIT_CENTS for cents in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    if sum(items_cents) > TOTAL_LIMIT_CENTS:
        return "REJECT:TOTAL_OVER_LIMIT"
    return "PASS"


# 工具的 API 契约：名字 + 描述 + 参数 JSON Schema（L2.2 用 Pydantic 自动生成它，今晚手写）
PREAPPROVE_TOOL = {
    "type": "function",
    "function": {
        "name": "preapprove",
        "description": "对报销单明细金额（单位：分）做规则预审，返回 PASS 或 REJECT:<原因>。",
        "parameters": {
            "type": "object",
            "properties": {
                "items_cents": {"type": "array", "items": {"type": "integer"}, "description": "明细金额列表，单位分"}
            },
            "required": ["items_cents"],
        },
    },
}


def show_trace(messages: list[dict]) -> None:
    print("== 两回合后的完整消息轨迹 ==")
    for message in messages:
        role = message["role"]
        if "tool_calls" in message:
            calls = ", ".join(c["function"]["name"] for c in message["tool_calls"])
            print(f"  {role:>9}: [选了工具: {calls}]")
        elif role == "tool":
            preview = str(message["content"])[:40]
            print(f"  {role:>9}: {preview}  (tool_call_id={message['tool_call_id']})")
        else:
            preview = str(message["content"])[:30] + ("…" if len(str(message["content"])) > 30 else "")
            print(f"  {role:>9}: {preview}")


async def run_offline() -> None:
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls([{"id": "call_001", "name": "preapprove", "arguments": {"items_cents": [8800]}}])
        ep.script_text("报销单 CLM-2026-0002 预审拒绝：REJECT:ITEM_OVER_LIMIT（单笔 8800 分超过上限 5000 分）。")
        async with ChatClient(ChatConfig(ep.url, "test-key", "mock-model")) as client:
            messages = [
                {"role": "system", "content": "你是财务预审助手：必须先调用 preapprove 工具，再按其结果回答。"},
                {"role": "user", "content": "预审报销单 CLM-2026-0002，明细：8800（单位：分）。"},
            ]

            print("== 第 1 回合：把工具契约随请求发给端点 ==")
            first = await client.complete(messages, tools=[PREAPPROVE_TOOL])
            assistant_message = first["choices"][0]["message"]
            print(f"  finish_reason = {first['choices'][0]['finish_reason']}  content = {assistant_message['content']}")
            messages.append(assistant_message)  # 模型的选择原样入史（含 tool_calls，不可裁剪）

            print("== 本地执行工具并回喂（role=tool） ==")
            for tool_call in assistant_message["tool_calls"]:
                raw_arguments = tool_call["function"]["arguments"]
                arguments = json.loads(raw_arguments)  # 坑位主角：它是 JSON 字符串，不是 dict
                result = preapprove(**arguments)  # ** 解包：{'items_cents': [...]} → 关键字实参（L1.4 复习）
                print(f"  {tool_call['function']['name']}({arguments}) -> {result}")
                messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result})

            print("== 第 2 回合：带着工具结果再请求 ==")
            second = await client.complete(messages, tools=[PREAPPROVE_TOOL])
            messages.append(second["choices"][0]["message"])
            print(f"  最终回答: {second['choices'][0]['message']['content']}")
            show_trace(messages)


async def run_real() -> None:
    async with ChatClient(ChatConfig.from_env()) as client:
        messages = [
            {"role": "system", "content": "你是财务预审助手：必须先调用 preapprove 工具，再按其结果回答。"},
            {"role": "user", "content": "预审报销单 CLM-2026-0002，明细：8800（单位：分）。"},
        ]
        first = await client.complete(messages, tools=[PREAPPROVE_TOOL])
        assistant_message = first["choices"][0]["message"]
        print(f"finish_reason = {first['choices'][0]['finish_reason']}")
        if not assistant_message.get("tool_calls"):
            print("模型未选工具，直接回答了：", assistant_message.get("content"))
            return
        messages.append(assistant_message)
        for tool_call in assistant_message["tool_calls"]:
            arguments = json.loads(tool_call["function"]["arguments"])
            result = preapprove(**arguments)
            print(f"{tool_call['function']['name']}({arguments}) -> {result}")
            messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result})
        second = await client.complete(messages, tools=[PREAPPROVE_TOOL])
        print("最终回答:", second["choices"][0]["message"]["content"])


def main() -> None:
    if "--real" in sys.argv[1:]:
        asyncio.run(run_real())
    else:
        asyncio.run(run_offline())


if __name__ == "__main__":
    main()
