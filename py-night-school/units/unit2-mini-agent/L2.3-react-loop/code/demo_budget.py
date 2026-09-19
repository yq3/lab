"""实验②：预算护栏——一个「永远想再查一单」的模型，硬终止如何救场（离线）。

没有 max_turns 的版本：这个循环不会停（剧本无限续）；预算是唯一的确定性刹车。
"""

from __future__ import annotations

import asyncio

import finance  # noqa: F401 —— import 即注册
from agent import AgentBudgetExceeded, ReActAgent
from model import ScriptedModel


def endless_script(rounds: int) -> list[dict]:
    """永远在要工具的「执念模型」：每轮换一张单据查。"""
    return [
        {
            "tool_calls": [
                {"id": f"call_{i:03d}", "name": "get_claim", "arguments": {"claim_id": f"CLM-2026-000{i % 9 + 1}"}}
            ]
        }
        for i in range(rounds)
    ]


def main() -> None:
    model = ScriptedModel(endless_script(100))  # 剧本给足：让它「能」永远跑下去
    agent = ReActAgent(model, max_turns=5)
    print("== 执念模型 × 5 轮预算 ==")

    async def scenario() -> None:
        try:
            await agent.run("把所有报销单都审一遍，一张都不要漏。")
        except AgentBudgetExceeded as exc:
            print(f"AgentBudgetExceeded: {exc}")

    asyncio.run(scenario())
    print(f"模型实际被调用: {len(model.calls)} 次（预算 5 轮，一次不多）")
    print("没有护栏的下场：这个剧本有 100 轮——它真的会跑满 100 轮才停。")


if __name__ == "__main__":
    main()
