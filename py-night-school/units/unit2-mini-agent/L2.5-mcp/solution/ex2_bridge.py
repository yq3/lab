# 参考答案：ex2_bridge（练习文件的完整解法——完成前别看）
"""桥接：MCP 工具描述 → OpenAI tools 载荷。"""

from __future__ import annotations

from collections.abc import Sequence

from mcp.types import Tool

TOOLS: list[Tool] = [
    Tool(
        name="preapprove",
        description="对报销单明细金额做规则预审。",
        input_schema={
            "type": "object",
            "properties": {"items_cents": {"type": "array", "items": {"type": "integer"}}},
            "required": ["items_cents"],
        },
    ),
    Tool(name="claim_count", description="统计报销单总数。", input_schema={"type": "object", "properties": {}}),
]


def mcp_tools_payload(tools: Sequence[Tool]) -> list[dict]:
    """MCP 工具列表 → OpenAI tools 载荷：parameters 直接放 input_schema（同一份 JSON Schema）。"""
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
