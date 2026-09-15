# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""ReAct 循环核心：模型选工具 → 执行 → 回喂 → 直到模型回答。

考察点：循环的两个出口（模型回答 / 预算耗尽——本题先做前者，预算是 ex2）；
assistant 消息原样入史；tool_calls 逐个执行、id 一一回带；查不到的工具回喂 error
（不是 raise——错误是给模型的修复指令，L2.2 的纪律在循环里延续）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——
  最终回答正确；消息轨迹 7 条角色序列精确匹配；id 配对；未知工具被回喂。
提示：循环体每一轮的动作只有三件：请求模型 → 分支判断 → 追加消息。
"""

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
    """离线模型：按顺序回放脚本（讲义 ScriptedModel 的极简版）。

    scripts 元素：{"content": str}（直接回答）或 {"tool_calls": [{"id", "name", "arguments": dict}]}。
    """

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
    """跑完整 ReAct 循环，返回 (最终回答, 完整消息史)。

    循环纪律：assistant 消息原样入史；每个 tool_call 执行后回喂
    {"role": "tool", "tool_call_id": <原 id>, "content": <结果字符串>}；
    注册表里没有的名字回喂 _error_json("unknown_tool: <名字>")；模型不再要工具即收工。
    """
    # TODO(ex1): 组装初始 messages（system + user），循环请求模型并按上述纪律推进
    raise NotImplementedError("TODO(ex1): 补全 run")
