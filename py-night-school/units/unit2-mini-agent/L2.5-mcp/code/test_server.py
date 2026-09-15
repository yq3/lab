"""讲义代码验收（发货态必须全绿；练习区的红在 exercises/）。

两路取证：in-process（直接调 server 方法，毫秒级）与 stdio 子进程（真实传输，
秒级——「真协议」的验收价值配得上这几秒）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp.types import CallToolResult, TextContent

import bridge
from bridge import McpToolError, mcp_tools_payload, run_mcp_tool
from finance_server import server

SERVER_PATH = Path(__file__).resolve().parent / "finance_server.py"


def _text(result: object) -> str:
    assert isinstance(result, CallToolResult)
    return next(part.text for part in result.content if isinstance(part, TextContent))


# ---- server：in-process 直调 ----


def test_server_registers_three_finance_tools() -> None:
    async def scenario() -> list[tuple[str, str]]:
        tools = await server.list_tools()
        return [(t.name, t.description or "") for t in tools]

    listed = asyncio.run(scenario())
    assert [name for name, _ in listed] == ["list_claims", "get_claim", "preapprove"]
    assert listed[2][1].startswith("对报销单明细金额")  # docstring 第一行 = 描述（L2.2 纪律的 MCP 版）


def test_preapprove_four_states_in_process() -> None:
    async def call(items: list[int]) -> str:
        return _text(await server.call_tool("preapprove", {"items_cents": items}))

    assert asyncio.run(call([1200, 3500])) == "PASS"
    assert asyncio.run(call([-500])) == "REJECT:INVALID_AMOUNT"
    assert asyncio.run(call([8800])) == "REJECT:ITEM_OVER_LIMIT"
    assert asyncio.run(call([4000] * 126)) == "REJECT:TOTAL_OVER_LIMIT"


# ---- 桥接：纯函数 ----


def test_mcp_tools_payload_matches_openai_shape() -> None:
    async def scenario() -> list[dict]:
        tools = await server.list_tools()  # in-process 直调返回的就是工具列表（client 侧才包 result）
        return mcp_tools_payload(tools)

    payload = asyncio.run(scenario())
    by_name = {item["function"]["name"]: item["function"] for item in payload}
    assert set(by_name) == {"list_claims", "get_claim", "preapprove"}
    assert by_name["preapprove"]["parameters"]["properties"]["items_cents"]["type"] == "array"
    assert by_name["get_claim"]["parameters"]["required"] == ["claim_id"]


# ---- client：真实 stdio 子进程往返 ----


def _stdio_session_call(name: str, arguments: dict) -> str:
    """起一个真实 server 子进程，走完整协议调用一个工具，返回文本结果。"""

    async def scenario() -> str:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments=arguments)
                return _text(result)

    return asyncio.run(scenario())


def test_stdio_roundtrip_get_claim() -> None:
    text = _stdio_session_call("get_claim", {"claim_id": "CLM-2026-0002"})
    claim = json.loads(text)
    assert claim["items_cents"] == [8800]  # 数据来自 server 子进程读的 data/ 文件


def test_stdio_run_mcp_tool_and_error_path() -> None:
    async def scenario() -> tuple[str, str]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                happy = await run_mcp_tool(session, "preapprove", '{"items_cents": [8800]}')
                with pytest.raises(McpToolError):
                    await run_mcp_tool(session, "no_such_tool", "{}")  # 未知工具：协议层报错
                return happy, happy

    happy, _ = asyncio.run(scenario())
    assert happy == "REJECT:ITEM_OVER_LIMIT"


def test_bridge_module_exports() -> None:
    assert bridge.McpToolError.__name__ == "McpToolError"  # 有名异常：上层可精确捕获分流
