# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体与所需的顶部 import，其余不要动）
"""写一个 MCP server：把 get_claim 做成跨进程可用的工具。

考察点：@server.tool() 装饰器（L1.5/L2.2 的装饰器纪律第三次落地——docstring 即描述、
类型标注即 schema）；工具函数返回 str（回喂给模型的 content）；查无此单返回 error JSON
（回喂不抛——错误是给模型的修复指令）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——
  子进程真实走 stdio 协议：发现 get_claim、按单号查到明细、查无此单拿到 error JSON。
提示：先 uv run python code/demo_client.py 看 client 侧长什么样，再写 server 侧。
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver import MCPServer

BUDGET_FILE = Path(__file__).resolve().parents[4] / "data" / "expense" / "budget_mock.json"

server = MCPServer("claims-lookup")


@server.tool()
def get_claim(claim_id: str) -> str:
    """按单号查询报销单（提交人、事由、明细金额，单位分）；查无此单返回 error JSON。"""
    # TODO(ex1): 读 BUDGET_FILE 的 expense_claims，找 id == claim_id 的单据
    # TODO(ex1): 找到：返回 json.dumps({"id":..., "submitter":..., "purpose":..., "items_cents":...},
    #           ensure_ascii=False)；找不到：返回 error JSON（键 error，值 "claim_not_found: <单号>"）
    raise NotImplementedError("TODO(ex1): 补全 get_claim")


if __name__ == "__main__":
    server.run("stdio")
