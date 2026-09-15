"""练习 1 验收（不要改本文件——它就是你的判卷老师）。

真协议验收：把你的 server 当子进程拉起（stdio 传输），走 initialize → list_tools →
call_tool 全流程。跑得慢（秒级）是因为真的起了进程——值得。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

SERVER = Path(__file__).resolve().parent / "ex1_mcp_server.py"


def _call_tool(name: str, arguments: dict) -> tuple[bool, str]:
    async def scenario() -> tuple[bool, str]:
        params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments=arguments)
                assert isinstance(result, CallToolResult)
                text = next(part.text for part in result.content if isinstance(part, TextContent))
                return result.is_error, text

    return asyncio.run(scenario())


def test_get_claim_returns_detail_json() -> None:
    is_error, text = _call_tool("get_claim", {"claim_id": "CLM-2026-0001"})
    assert not is_error
    claim = json.loads(text)
    assert claim["id"] == "CLM-2026-0001"
    assert claim["items_cents"] == [1200, 3500, 2400]
    assert claim["submitter"] == "王工"


def test_get_claim_not_found_returns_error_json() -> None:
    is_error, text = _call_tool("get_claim", {"claim_id": "CLM-2026-9999"})
    assert not is_error  # 查无此单是业务结果（error JSON），不是协议错误（is_error）
    assert json.loads(text)["error"] == "claim_not_found: CLM-2026-9999"


def test_tool_is_discoverable() -> None:
    async def scenario() -> list[str]:
        params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                return [tool.name for tool in listed.tools]

    assert asyncio.run(scenario()) == ["get_claim"]
