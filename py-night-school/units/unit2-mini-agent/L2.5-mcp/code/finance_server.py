"""MCP server：财务 mock 工具 ×3（list_claims / get_claim / preapprove）。

MCP（Model Context Protocol）解决的问题是**工具的可移植性**：工具不再焊死在你的
agent 进程里，而是由独立进程（server）提供，任何 MCP client（你的 agent、IDE、
别人写的 agent）都能消费同一份工具——「一次编写，处处挂载」。

形态：本文件是一个独立进程，用 stdio 传输运行（stdin/stdout 上跑 JSON-RPC）：
    uv run python code/finance_server.py     # 它会「挂起」等你输入——这就是 server 在等 client
对照 Java：一个暴露 RPC 端点的小服务（像 JDK 内置 HttpServer 起的最小 API），
只是传输从 HTTP 换成了进程间管道、协议从 REST 换成 JSON-RPC。

SDK 版本说明：官方 python-sdk 2.x 把 server 类从 FastMCP 改名为 MCPServer
（import 路径 mcp.server.mcpserver）；你在网上看到的大量 FastMCP 教程是 1.x 时代
或独立的 fastmcp 包——思想一致，名字换了。夜校锚定 2.x。
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer

BUDGET_FILE = Path(__file__).resolve().parents[4] / "data" / "expense" / "budget_mock.json"

ITEM_LIMIT_CENTS = 5000
TOTAL_LIMIT_CENTS = 500000

server = MCPServer("night-school-finance")


def _load_claims() -> list[dict]:
    return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))["expense_claims"]


@server.tool()
def list_claims() -> str:
    """列出全部报销单（单号、提交人、事由）。"""
    summary = [
        {"id": claim["id"], "submitter": claim["submitter"], "purpose": claim["purpose"]} for claim in _load_claims()
    ]
    return json.dumps(summary, ensure_ascii=False)


@server.tool()
def get_claim(claim_id: str) -> str:
    """按单号查询报销单明细（提交人、事由、金额列表，单位分）。"""
    for claim in _load_claims():
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


@server.tool()
def preapprove(items_cents: list[int]) -> str:
    """对报销单明细金额（单位分）做规则预审，返回 PASS 或 REJECT:<原因>。"""
    if any(cents <= 0 for cents in items_cents):
        return "REJECT:INVALID_AMOUNT"
    if any(cents > ITEM_LIMIT_CENTS for cents in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    if sum(items_cents) > TOTAL_LIMIT_CENTS:
        return "REJECT:TOTAL_OVER_LIMIT"
    return "PASS"


if __name__ == "__main__":
    server.run("stdio")
