"""MCP 桥接（T3）：MCP 工具 ↔ OpenAI 工具协议。

给定：McpToolError。你的任务：补全两个函数——payload 转换与协议执行。
写得对不对，mcp_server.py 子进程会用真实协议告诉你。
"""

from __future__ import annotations

from collections.abc import Sequence

from mcp import ClientSession
from mcp.types import Tool


class McpToolError(Exception):
    """MCP 工具执行失败（is_error=True 或未知工具）。"""


def mcp_tools_payload(tools: Sequence[Tool]) -> list[dict]:
    """MCP 工具列表 → OpenAI tools 载荷：parameters 直接放 input_schema（同一份 JSON Schema）。"""
    # TODO(t3): 每个工具一个三层 dict；description 为 None 归一成空串
    raise NotImplementedError("TODO(t3): 补全 mcp_tools_payload")


async def run_mcp_tool(session: ClientSession, name: str, arguments_json: str) -> str:
    """经 MCP 协议执行一个工具调用，返回文本结果；失败抛 McpToolError。"""
    # TODO(t3): json.loads 拆 arguments（需补 import json；坏 JSON 抛 McpToolError("invalid_arguments: ...")）
    # TODO(t3): await session.call_tool(name, arguments=...)；content 是联合类型列表，收文本要收窄
    # TODO(t3): result.is_error 为真 -> raise McpToolError(f"{name}: <文本>")；否则返回拼接文本
    raise NotImplementedError("TODO(t3): 补全 run_mcp_tool")
