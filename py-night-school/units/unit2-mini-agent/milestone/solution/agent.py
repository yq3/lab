"""ReAct agent（T1 参考答案）：L2.3 的循环 + 执行器接缝。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from model import ModelClient
from tools import TOOL_REGISTRY, ToolSpec, run_tool, to_openai_tools

DEFAULT_SYSTEM = (
    "你是财务预审助手。先用 get_claim 查单据明细，再用 preapprove 预审，最后按工具结果回答；"
    "结论只用 PASS 或 REJECT:<原因>。"
)

# 工具执行器接缝：(工具名, arguments JSON 字符串) -> 结果文本
ToolExecutor = Callable[[str, str], Awaitable[str]]


class AgentBudgetExceeded(Exception):
    """轮数预算耗尽——模型一直要工具，硬终止触发。"""


@dataclass(frozen=True)
class AgentResult:
    final_text: str
    messages: list[dict]
    turns: int


class ReActAgent:
    def __init__(self, client: ModelClient, registry: dict[str, ToolSpec] = TOOL_REGISTRY, max_turns: int = 8):
        self._client = client
        self._registry = registry
        self._max_turns = max_turns

    async def _default_execute(self, name: str, arguments_json: str) -> str:
        return run_tool(name, arguments_json, registry=self._registry)

    async def run(
        self,
        user_message: str,
        system: str = DEFAULT_SYSTEM,
        execute: ToolExecutor | None = None,
    ) -> AgentResult:
        """跑完整循环。execute 为 None 用本地注册表，否则用注入的执行器（MCP 桥接）。"""
        executor = execute or self._default_execute
        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]
        tools = to_openai_tools(self._registry)
        for turn in range(1, self._max_turns + 1):
            message = (await self._client.complete(messages, tools))["choices"][0]["message"]
            messages.append(message)  # 原样入史（含 tool_calls，不可裁剪）
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return AgentResult(final_text=message.get("content") or "", messages=messages, turns=turn)
            for tool_call in tool_calls:
                result = await executor(tool_call["function"]["name"], tool_call["function"]["arguments"])
                messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result})
        raise AgentBudgetExceeded(f"{self._max_turns} 轮预算耗尽（历史 {len(messages)} 条消息仍未收敛）")


def print_trace(messages: Sequence[dict]) -> None:
    """按角色打印完整消息史（main.py 取证用）。"""
    for message in messages:
        role = message["role"]
        if "tool_calls" in message:
            calls = ", ".join(c["function"]["name"] for c in message["tool_calls"])
            print(f"  {role:>9}: [选了工具: {calls}]")
        elif role == "tool":
            print(f"  {role:>9}: {str(message['content'])[:46]}  (id={message['tool_call_id']})")
        else:
            print(f"  {role:>9}: {str(message['content'])[:46]}")
