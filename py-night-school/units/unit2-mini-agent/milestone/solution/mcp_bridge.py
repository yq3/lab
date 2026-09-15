# 参考答案：mcp_bridge.py（T3——完成前别看）
"""桥接层：MCP 工具 ↔ OpenAI 工具协议。

MCP 的工具描述（input_schema）与 OpenAI 的工具契约（parameters）**都是 JSON Schema**——
协议在此接轨：把 MCP server 的 list_tools 结果转成 OpenAI tools 载荷，agent 的模型端
零改动；工具执行从「进程内调用」换成「MCP call_tool 往返」，agent 的循环零改动。
这就是协议分层的红利：L2.3 的循环不关心工具住在本进程还是隔壁进程。
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from mcp import ClientSession
from mcp.types import Tool


class McpToolError(Exception):
    """MCP 工具执行失败（is_error=True 或未知工具）——错误信息来自 server 的 content。"""


def mcp_tools_payload(tools: Sequence[Tool]) -> list[dict]:
    """MCP 工具列表 → OpenAI tools 载荷（name/description/parameters 三件套对齐）。"""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


async def run_mcp_tool(session: ClientSession, name: str, arguments_json: str) -> str:
    """经 MCP 协议执行一个工具调用，返回文本结果（形状与 L2.2 的 run_tool 对齐）。

    arguments_json 是模型给的 JSON 字符串（字符串套娃坑第三次出场）——先拆成 dict
    再走协议；is_error=True 时抛 McpToolError（server 端的业务错误信息在 content 里）。
    """
    try:
        arguments = json.loads(arguments_json)
    except json.JSONDecodeError as exc:
        raise McpToolError(f"invalid_arguments: {exc.msg}") from exc
    result = await session.call_tool(name, arguments=arguments)
    texts = [text for part in result.content if (text := getattr(part, "text", None))]
    if result.is_error:
        raise McpToolError(f"{name}: {'; '.join(texts)}")
    return "\n".join(texts)
