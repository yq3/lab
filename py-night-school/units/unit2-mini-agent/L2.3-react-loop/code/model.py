"""模型客户端抽象：Protocol 让「真实端点」与「离线脚本」可互换。

L1.2 讲过 Protocol 是结构化类型：不继承、只看形状。今晚兑现——
ReActAgent 只依赖 complete(messages, tools) 这个形状，不关心背后是 httpx 还是脚本列表。
这是 agent 代码可测试性的关键一步（对照 Java：面向接口编程，Mockito 造测试替身；
这里连 Mockito 都不需要，一个普通类长成协议的形状就行）。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Protocol

from client import ChatClient, ChatConfig


class ModelClient(Protocol):
    """agent 依赖的全部模型能力：进 messages + tools，出一个 chat-completion 形状的 dict。"""

    async def complete(self, messages: Sequence[dict], tools: Sequence[dict]) -> dict: ...


class HttpModelClient:
    """真实端点适配器：把 L2.1 的 ChatClient 包成 ModelClient 形状。"""

    def __init__(self, config: ChatConfig) -> None:
        self._chat = ChatClient(config)
        self.model = config.model

    async def complete(self, messages: Sequence[dict], tools: Sequence[dict]) -> dict:
        return await self._chat.complete(messages, tools=tools)

    async def __aenter__(self) -> HttpModelClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._chat.aclose()


class ScriptExhausted(Exception):
    """ScriptedModel 的剧本演完了——测试里这通常意味着循环多跑了一轮。"""


class ScriptedModel:
    """离线测试替身：按顺序回放脚本化的响应，并记录每次收到的请求。

    scripts 元素两种形态：
        {"content": "回答文本"}                                  —— 模型直接回答（stop）
        {"tool_calls": [{"id": ..., "name": ..., "arguments": {...}}]} —— 模型选工具
    回放时转成与真实端点一致的响应形状（arguments 编码为 JSON 字符串）。
    """

    def __init__(self, scripts: list[dict]) -> None:
        self._scripts = list(scripts)
        self.calls: list[dict] = []  # 每次 complete 收到的 (messages, tools) 取证

    async def complete(self, messages: Sequence[dict], tools: Sequence[dict]) -> dict:
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        if not self._scripts:
            raise ScriptExhausted("剧本演完了仍在请求模型——循环多跑了一轮？")
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
            finish_reason = "tool_calls"
        else:
            message = {"role": "assistant", "content": script["content"]}
            finish_reason = "stop"
        return {"choices": [{"index": 0, "message": message, "finish_reason": finish_reason}]}
