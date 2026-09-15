"""实验①：ReAct agent 完整跑一轮（离线剧本驱动，轨迹全程打印）。

离线模式（默认）：ScriptedModel 回放「查单 → 预审 → 结论」剧本——你看到的消息轨迹、
工具执行、轮数计数与真实端点完全同构。
真端点模式：uv run python code/demo_agent.py --real（需 .env；调用顺序由模型自己决定）。
"""

from __future__ import annotations

import asyncio
import sys

import finance  # noqa: F401 —— import 即注册
from agent import ReActAgent, print_trace
from model import HttpModelClient, ScriptedModel
from tools import TOOL_REGISTRY

QUESTION = "请审查报销单 CLM-2026-0003。"

SCRIPT = [
    {"tool_calls": [{"id": "call_001", "name": "get_claim", "arguments": {"claim_id": "CLM-2026-0003"}}]},
    {"tool_calls": [{"id": "call_002", "name": "preapprove", "arguments": {"items_cents": [-500]}}]},
    {"content": "REJECT:INVALID_AMOUNT（报销单含负数金额明细，属脏数据）。"},
]


async def run_offline() -> None:
    model = ScriptedModel(SCRIPT)
    agent = ReActAgent(model, max_turns=6)
    print(f"== ReAct agent 离线跑 ==\n注册表: {sorted(TOOL_REGISTRY)}\nuser: {QUESTION}")
    result = await agent.run(QUESTION)
    print(f"\n== 消息轨迹（{len(result.messages)} 条，消耗 {result.turns} 轮） ==")
    print_trace(result.messages)
    print(f"\n最终回答: {result.final_text}")


async def run_real() -> None:
    from client import ChatConfig
    from env_loader import load_env

    load_env()
    async with HttpModelClient(ChatConfig.from_env()) as model:
        agent = ReActAgent(model, max_turns=6)
        result = await agent.run(QUESTION)
        print_trace(result.messages)
        print(f"\n最终回答（{result.turns} 轮）: {result.final_text}")


def main() -> None:
    if "--real" in sys.argv[1:]:
        asyncio.run(run_real())
    else:
        asyncio.run(run_offline())


if __name__ == "__main__":
    main()
