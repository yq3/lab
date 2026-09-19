# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体与所需的顶部 import，其余不要动）
"""桥接：MCP 工具描述 → OpenAI tools 载荷。

考察点：两套协议在「JSON Schema」上的接轨点——MCP 的 input_schema 原样放进
OpenAI 的 parameters；三层嵌套结构（type/function/{name,description,parameters}）。

完成判据：uv run pytest exercises/test_ex2.py 全绿——载荷结构逐键断言、schema 原样透传。
提示：mcp.types.Tool 的字段访问是 snake_case（tool.input_schema、tool.description）。
"""

from __future__ import annotations

from collections.abc import Sequence

from mcp.types import Tool

# 夹具：两个手工构造的 MCP Tool（形状与 list_tools 返回的一致）
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
    # TODO(ex2): 每个 tool 组一个三层 dict；description 为 None 时给空串
    raise NotImplementedError("TODO(ex2): 补全 mcp_tools_payload")
