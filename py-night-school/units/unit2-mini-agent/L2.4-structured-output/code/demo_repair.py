"""实验②：校验错误回喂重试——模型第一次交了张错单，修复指令把它救回来（离线）。

剧本：第 1 次输出围栏 JSON 且 verdict 不在值域、缺 reason（两处校验伤）；
第 2 次散文夹带但字段齐全（extract_json 第 3 层 + 校验全过）。
真端点模式：uv run python code/demo_repair.py --real（需 .env；错误形态由模型自由发挥）。
"""

from __future__ import annotations

import asyncio
import sys

from model import HttpModelClient, ScriptedModel
from structured import ask_structured

QUESTION = "报销单 CLM-2026-0002（明细单笔 8800 分）的预审决策是什么？"

SCRIPT = [
    '```json\n{"claim_id": "CLM-2026-0002", "verdict": "REJECT:OVER_LIMIT"}\n```',
    '抱歉，修正后的决策如下：{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT",'
    ' "reason": "单笔 8800 分超过 5000 分上限"} 希望这次格式正确。',
]


def show_trace(messages: list[dict]) -> None:
    print(f"== 修复后的消息轨迹（{len(messages)} 条） ==")
    for message in messages:
        content = str(message["content"])
        preview = content[:64].replace("\n", "\\n") + ("…" if len(content) > 64 else "")
        print(f"  {message['role']:>9}: {preview}")


async def run_offline() -> None:
    model = ScriptedModel([{"content": text} for text in SCRIPT])
    decision, messages = await ask_structured(model, QUESTION, attempts=3)
    print("== 第 1 次输出：围栏 + 值域越界 + 缺 reason ==\n== 第 2 次输出：散文夹带但字段齐全 ==")
    print(f"\n拿到决策对象: {decision.model_dump_json()}")
    show_trace(messages)


async def run_real() -> None:
    from client import ChatConfig
    from env_loader import load_env

    load_env()
    async with HttpModelClient(ChatConfig.from_env()) as model:
        decision, messages = await ask_structured(model, QUESTION, attempts=3)
        print(f"拿到决策对象: {decision.model_dump_json()}")
        show_trace(messages)


def main() -> None:
    if "--real" in sys.argv[1:]:
        asyncio.run(run_real())
    else:
        asyncio.run(run_offline())


if __name__ == "__main__":
    main()
