# 参考答案：ex1_agent_loop（练习文件的完整解法——完成前别看）
"""ReAct 循环核心：模型选工具 → 执行 → 回喂 → 直到模型回答。"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence

SYSTEM = "你是财务预审助手：必须调用 preapprove 工具获得结论后才能回答。"


def _preapprove(items_cents: list[int]) -> str:
    if any(cents <= 0 for cents in items_cents):
        return "REJECT:INVALID_AMOUNT"
    if any(cents > 5000 for cents in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    return "PASS"


REGISTRY: dict[str, Callable[..., str]] = {"preapprove": _preapprove}


class ScriptedLite:
    """离线模型：按顺序回放脚本（讲义 ScriptedModel 的极简版）。"""

    def __init__(self, scripts: list[dict]) -> None:
        self._scripts = list(scripts)
        self.request_count = 0

    async def complete(self, messages: Sequence[dict]) -> dict:
        self.request_count += 1
        script = self._scripts.pop(0)
        if "tool_calls" in script:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                        },
                    }
                    for call in script["tool_calls"]
                ],
            }
        else:
            message = {"role": "assistant", "content": script["content"]}
        return {"choices": [{"index": 0, "message": message}]}


def _error_json(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)


async def run(model: ScriptedLite, user_message: str, system: str = SYSTEM) -> tuple[str, list[dict]]:
    """跑完整 ReAct 循环，返回 (最终回答, 完整消息史)。"""
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]
    while True:
        message = (await model.complete(messages))["choices"][0]["message"]
        messages.append(message)  # 原样入史（含 tool_calls）
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return message.get("content") or "", messages
        for tool_call in tool_calls:
            name = tool_call["function"]["name"]
            func = REGISTRY.get(name)
            if func is None:
                result = _error_json(f"unknown_tool: {name}")
            else:
                arguments = json.loads(tool_call["function"]["arguments"])
                result = str(func(**arguments))
            messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result})
