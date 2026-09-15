# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""client 侧执行：经 MCP 协议调用工具（run_mcp_tool）。

考察点：arguments_json 是模型给的 JSON 字符串（字符串套娃坑第三次出场）——先拆成 dict
再走协议；结果 content 列表里取文本；is_error=True 时抛 McpToolError（server 的错误
信息在 content 里，要带给上层）。

完成判据：uv run pytest exercises/test_ex3.py 全绿——
  对讲义 finance_server.py 真实 stdio 调用：预审四态、未知工具抛 McpToolError。
提示：session.call_tool(name, arguments=<dict>)；文本在 part.text（列表可能有多个 part）。
"""

from __future__ import annotations

from mcp import ClientSession


class McpToolError(Exception):
    """MCP 工具执行失败（is_error=True 或未知工具）。"""


async def run_mcp_tool(session: ClientSession, name: str, arguments_json: str) -> str:
    """经 MCP 协议执行一个工具调用，返回文本结果；失败抛 McpToolError。"""
    # TODO(ex3): json.loads 拆 arguments（坏 JSON 抛 McpToolError("invalid_arguments: ...")）
    # TODO(ex3): await session.call_tool(name, arguments=...)；从 result.content 收集文本
    # TODO(ex3): result.is_error 为真 -> raise McpToolError(f"{name}: <文本>")；否则返回拼接文本
    raise NotImplementedError("TODO(ex3): 补全 run_mcp_tool")
