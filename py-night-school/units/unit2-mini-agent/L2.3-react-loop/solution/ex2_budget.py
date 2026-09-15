# 参考答案：ex2_budget（练习文件的完整解法——完成前别看）
"""轮数预算：硬终止护栏。"""

from __future__ import annotations

import json
from collections.abc import Sequence


class BudgetExceeded(Exception):
    """轮数预算耗尽。"""


def _preapprove(items_cents: list[int]) -> str:
    if any(cents <= 0 for cents in items_cents):
        return "REJECT:INVALID_AMOUNT"
    return "PASS"


class ObsessedModel:
    """执念模型：每轮都要再查一次工具，永远不会直接回答（软终止永不来）。"""

    def __init__(self) -> None:
        self.request_count = 0

    async def complete(self, messages: Sequence[dict]) -> dict:
        self.request_count += 1
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{self.request_count:03d}",
                    "type": "function",
                    "function": {"name": "preapprove", "arguments": '{"items_cents": [1200]}'},
                }
            ],
        }
        return {"choices": [{"index": 0, "message": message}]}


async def run_with_budget(model: ObsessedModel, user_message: str, max_turns: int) -> list[dict]:
    """带预算的循环：模型回答则返回完整历史；max_turns 轮耗尽抛 BudgetExceeded。"""
    messages: list[dict] = [
        {"role": "system", "content": "你是财务预审助手。"},
        {"role": "user", "content": user_message},
    ]
    for _turn in range(1, max_turns + 1):  # 软终止：模型的概率性选择
        message = (await model.complete(messages))["choices"][0]["message"]
        messages.append(message)
        if not message.get("tool_calls"):
            return messages
        for tool_call in message["tool_calls"]:
            arguments = json.loads(tool_call["function"]["arguments"])
            result = _preapprove(**arguments)
            messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result})
    raise BudgetExceeded(f"{max_turns} 轮预算耗尽（历史 {len(messages)} 条消息仍未收敛）")  # 硬终止：你的确定性护栏
