# 参考答案：ex3_mcp_client（练习文件的完整解法——完成前别看）
"""client 侧执行：经 MCP 协议调用工具（run_mcp_tool）。"""

from __future__ import annotations

import json

from mcp import ClientSession


class McpToolError(Exception):
    """MCP 工具执行失败（is_error=True 或未知工具）。"""


async def run_mcp_tool(session: ClientSession, name: str, arguments_json: str) -> str:
    """经 MCP 协议执行一个工具调用，返回文本结果；失败抛 McpToolError。"""
    try:
        arguments = json.loads(arguments_json)
    except json.JSONDecodeError as exc:
        raise McpToolError(f"invalid_arguments: {exc.msg}") from exc
    result = await session.call_tool(name, arguments=arguments)
    texts = [text for part in result.content if (text := getattr(part, "text", None))]
    if result.is_error:
        raise McpToolError(f"{name}: {'; '.join(texts)}")
    return "\n".join(texts)
