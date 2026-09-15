"""实验①：client 三步走——连接 stdio server、发现工具、调用工具（全程离线）。

它启动 finance_server.py 子进程（真实 stdio 传输），完成 initialize 握手、
list_tools 发现、call_tool 调用。没有任何 LLM 参与——MCP 是工具层协议。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

SERVER = Path(__file__).resolve().parent / "finance_server.py"


def first_text(result: CallToolResult | object) -> str:
    """取结果里第一段文本（content 是联合类型的列表——isinstance 收窄后再取 .text）。"""
    assert isinstance(result, CallToolResult)
    for part in result.content:
        if isinstance(part, TextContent):
            return part.text
    return ""


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()  # 协议握手：交换身份与能力（对照 TCP 之后的 HELLO）
            print("== 连接成功，发现工具 ==")
            listed = await session.list_tools()
            for tool in listed.tools:
                print(f"  {tool.name}: {tool.description}")
            print("== input_schema 就是 JSON Schema（与 L2.2 的 parameters 同构） ==")
            schema = listed.tools[2].input_schema  # 第 3 个注册的是 preapprove
            print(f"  preapprove.input_schema = {json.dumps(schema, ensure_ascii=False)}")

            print("== 调用工具 ==")
            listed_claims = await session.call_tool("list_claims", arguments={})
            claims = json.loads(first_text(listed_claims))
            print(f"  list_claims() -> {len(claims)} 张单: {[c['id'] for c in claims]}")
            detail = await session.call_tool("get_claim", arguments={"claim_id": "CLM-2026-0003"})
            print(f"  get_claim('CLM-2026-0003') -> {first_text(detail)}")
            verdict = await session.call_tool("preapprove", arguments={"items_cents": [8800]})
            print(f"  preapprove([8800]) -> {first_text(verdict)}")
            print("  （工具不在本进程——执行发生在 server 子进程里，结果经 JSON-RPC 回来）")


if __name__ == "__main__":
    asyncio.run(main())
