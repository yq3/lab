# 参考答案：ex1_mcp_server（练习文件的完整解法——完成前别看）
"""写一个 MCP server：把 get_claim 做成跨进程可用的工具。"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer

BUDGET_FILE = Path(__file__).resolve().parents[4] / "data" / "expense" / "budget_mock.json"

server = MCPServer("claims-lookup")


@server.tool()
def get_claim(claim_id: str) -> str:
    """按单号查询报销单（提交人、事由、明细金额，单位分）；查无此单返回 error JSON。"""
    claims = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))["expense_claims"]
    for claim in claims:
        if claim["id"] == claim_id:
            return json.dumps(
                {
                    "id": claim["id"],
                    "submitter": claim["submitter"],
                    "purpose": claim["purpose"],
                    "items_cents": claim["items_cents"],
                },
                ensure_ascii=False,
            )
    return json.dumps({"error": f"claim_not_found: {claim_id}"}, ensure_ascii=False)


if __name__ == "__main__":
    server.run("stdio")
