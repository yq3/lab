"""mini-agent 演示入口：三种模式跑同一条「审查报销单」链路。

uv run python main.py          # 离线全链路：剧本模型 × 本地工具注册表 × 结构化决策
uv run python main.py --mcp    # 离线全链路：工具换成 MCP server（stdio 子进程）
uv run python main.py --real   # 真端点（需先配好 .env；模型自己决定调用顺序）
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import finance  # noqa: F401 —— import 即注册（本地工具模式）
from agent import ReActAgent, print_trace
from mcp_bridge import McpToolError, run_mcp_tool
from model import ScriptedModel
from structured import PreapprovalDecision, ask_structured, extract_json

QUESTION = "请审查报销单 CLM-2026-0002。"

# 离线剧本：查单 → 预审 → 最终回答（内容是散文夹决策 JSON——正好走一遍 extract）
SCRIPT = [
    {"tool_calls": [{"id": "call_001", "name": "get_claim", "arguments": {"claim_id": "CLM-2026-0002"}}]},
    {"tool_calls": [{"id": "call_002", "name": "preapprove", "arguments": {"items_cents": [8800]}}]},
    {
        "content": '结论如下：{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT", '
        '"reason": "单笔 8800 分超过 5000 分上限"}'
    },
]

STRUCTURED_SCRIPT = [
    '```json\n{"claim_id": "CLM-2026-0002", "verdict": "REJECT:OVER"}\n```',  # 第 1 次交错单：围栏 + 值域越界
    '修正：{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT", "reason": "单笔超限"}',
]


def mcp_executor(session):  # noqa: ANN001 —— 接缝只要求形状（ToolExecutor 协议风格的鸭子类型）
    """把 MCP 执行器包成 ToolExecutor 接缝：错误转 error JSON 回喂（回喂不抛的纪律）。"""

    async def execute(name: str, arguments_json: str) -> str:
        try:
            return await run_mcp_tool(session, name, arguments_json)
        except McpToolError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    return execute


async def run_local() -> None:
    print("== 模式 A：离线 × 本地工具注册表 ==")
    agent = ReActAgent(ScriptedModel(SCRIPT), max_turns=6)
    result = await agent.run(QUESTION)
    print_trace(result.messages)
    decision = PreapprovalDecision.model_validate(extract_json(result.final_text))
    print(f"\n结构化决策: {decision.model_dump_json()}")
    print(f"消耗 {result.turns} 轮 / 历史 {len(result.messages)} 条")


async def run_structured_demo() -> None:
    print("\n== 模式 A 附：结构化输出修复回路 ==")
    model = ScriptedModel([{"content": text} for text in STRUCTURED_SCRIPT])
    decision, _ = await ask_structured(model, QUESTION + "（结构化决策版）")
    print(f"修复后决策: {decision.model_dump_json()}")


async def run_mcp() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from mcp_bridge import mcp_tools_payload

    server = Path(__file__).resolve().parent / "mcp_server.py"
    params = StdioServerParameters(command=sys.executable, args=[str(server)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = [item["function"]["name"] for item in mcp_tools_payload(listed.tools)]
            print(f"== 模式 B：离线 × MCP server（经协议发现工具: {names}） ==")
            agent = ReActAgent(ScriptedModel(SCRIPT), max_turns=6, registry={})
            # registry 为空：工具契约与执行全部走 MCP 接缝——agent 循环一行不改
            result = await agent.run(QUESTION, execute=mcp_executor(session))
            print_trace(result.messages)
            decision = PreapprovalDecision.model_validate(extract_json(result.final_text))
            print(f"\n结构化决策: {decision.model_dump_json()}（执行发生在 server 子进程）")


async def run_real() -> None:
    from client import ChatConfig
    from env_loader import load_env
    from model import HttpModelClient

    print("== 模式 C：真实端点（.env 三变量） ==")
    load_env()
    async with HttpModelClient(ChatConfig.from_env()) as model:
        agent = ReActAgent(model, max_turns=6)
        result = await agent.run(QUESTION)
        print_trace(result.messages)
        print(f"\n最终回答（{result.turns} 轮）: {result.final_text}")


def main() -> None:
    args = sys.argv[1:]
    if "--mcp" in args:
        asyncio.run(run_mcp())
    elif "--real" in args:
        asyncio.run(run_real())
    else:
        asyncio.run(run_local())
        asyncio.run(run_structured_demo())


if __name__ == "__main__":
    main()
