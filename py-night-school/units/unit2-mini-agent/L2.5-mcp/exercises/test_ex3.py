"""练习 3 验收（不要改本文件——它就是你的判卷老师）。

对讲义的 finance_server.py（code/，完整可用）走真实 stdio 协议调用。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import ex3_mcp_client as ex3

SERVER = Path(__file__).resolve().parents[1] / "code" / "finance_server.py"


def _run(calls: list[tuple[str, str]]) -> list[str]:
    """按顺序执行若干 (name, arguments_json)；正常结果与 McpToolError 都按序收进列表。"""

    async def scenario() -> list[str]:
        outcomes: list[str] = []
        params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for name, arguments_json in calls:
                    try:
                        outcomes.append(await ex3.run_mcp_tool(session, name, arguments_json))
                    except ex3.McpToolError as exc:
                        outcomes.append(f"McpToolError: {exc}")
        return outcomes

    return asyncio.run(scenario())


def test_preapprove_states_through_protocol() -> None:
    outcomes = _run(
        [
            ("preapprove", '{"items_cents": [1200, 3500, 2400]}'),
            ("preapprove", '{"items_cents": [8800]}'),
            ("preapprove", '{"items_cents": [-500]}'),
            ("preapprove", json.dumps({"items_cents": [4000] * 126})),  # 每笔合法，合计 504000 分超总额
        ]
    )
    assert outcomes == [
        "PASS",
        "REJECT:ITEM_OVER_LIMIT",
        "REJECT:INVALID_AMOUNT",
        "REJECT:TOTAL_OVER_LIMIT",
    ]


def test_unknown_tool_becomes_mcp_tool_error() -> None:
    outcomes = _run([("no_such_tool", "{}")])
    assert outcomes[0].startswith("McpToolError")  # 未知工具必须走有名异常，不许静默成功


def test_bad_arguments_json_becomes_mcp_tool_error() -> None:
    outcomes = _run([("preapprove", "不是 JSON")])
    assert outcomes[0].startswith("McpToolError: invalid_arguments")
