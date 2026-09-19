"""实验②：MCP 工具插进 L2.3 的循环——agent 的工具从「本进程」搬到「隔壁进程」。

离线剧本：模型先 get_claim 查明细，再 preapprove 预审，最后回答。
循环形状与 L2.3 一字不差；两处换件：tools 载荷来自 MCP 的 list_tools，
工具执行从 run_tool（进程内）换成 run_mcp_tool（JSON-RPC 往返）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from bridge import mcp_tools_payload, run_mcp_tool

SERVER = Path(__file__).resolve().parent / "finance_server.py"

SCRIPT = [
    {"tool_calls": [{"id": "call_001", "name": "get_claim", "arguments": {"claim_id": "CLM-2026-0001"}}]},
    {"tool_calls": [{"id": "call_002", "name": "preapprove", "arguments": {"items_cents": [1200, 3500, 2400]}}]},
    {"content": "预审 PASS：三笔明细合规，合计 7100 分未超总额上限。"},
]


class ModelClient(Protocol):
    async def complete(self, messages: list[dict], tools: list[dict]) -> dict: ...


class ScriptedModel:
    """L2.3 ScriptedModel 的本课内联版（避免引入 httpx 依赖）。"""

    def __init__(self, scripts: list[dict]) -> None:
        self._scripts = list(scripts)

    async def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        script = self._scripts.pop(0)
        if "tool_calls" in script:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                        },
                    }
                    for call in script["tool_calls"]
                ],
            }
        else:
            message = {"role": "assistant", "content": script["content"]}
        return {"choices": [{"index": 0, "message": message}]}


async def run_agent(model: ModelClient, session: ClientSession) -> tuple[str, list[dict]]:
    """L2.3 的 ReAct 循环，换上 MCP 工具（对照读 agent.py：只有两行不同）。"""
    messages: list[dict] = [
        {"role": "system", "content": "你是财务预审助手：先查明细再预审。"},
        {"role": "user", "content": "请审查报销单 CLM-2026-0001。"},
    ]
    listed = await session.list_tools()
    tools = mcp_tools_payload(listed.tools)  # 换件 ①：契约来自 MCP 发现
    for turn in range(1, 5):  # 预算照旧（L2.3 的纪律）
        message = (await model.complete(messages, tools))["choices"][0]["message"]
        messages.append(message)
        if not message.get("tool_calls"):
            return message["content"], messages
        for tool_call in message["tool_calls"]:
            result = await run_mcp_tool(  # 换件 ②：执行走 JSON-RPC 往返
                session, tool_call["function"]["name"], tool_call["function"]["arguments"]
            )
            print(f"  第 {turn} 轮: {tool_call['function']['name']} -> {result[:60]}")
            messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result})
    raise RuntimeError("预算耗尽")


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            model = ScriptedModel(SCRIPT)
            print("== ReAct agent × MCP 工具（执行在 server 子进程） ==")
            final, _ = await run_agent(model, session)
            print(f"最终回答: {final}")


if __name__ == "__main__":
    asyncio.run(main())
