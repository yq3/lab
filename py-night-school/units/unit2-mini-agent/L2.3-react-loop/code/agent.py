"""ReAct 循环：agent = 模型 + 工具循环。

整个循环一句话：把 messages 发给模型；模型要工具就执行并回喂，再发；模型回答了就收工；
预算耗尽就报警。LangGraph、openai-agents 的 runner，剥掉分布式与可观测性，
骨架就是这 ~70 行（与 openai-cookbook 对照原件的 run_full_turn 同构——见延伸）。

终止条件有两个，缺一不可：
  软终止：模型不再要工具（它的选择，概率性）；
  硬终止：max_turns 轮数预算（你的护栏，确定性）——§5 坑位的答案。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from model import ModelClient
from tools import TOOL_REGISTRY, ToolSpec, run_tool, to_openai_tools

DEFAULT_SYSTEM = (
    "你是财务预审助手。先用 get_claim 查单据明细，再用 preapprove 预审，最后按工具结果回答；"
    "结论只用 PASS 或 REJECT:<原因>。"
)


class AgentBudgetExceeded(Exception):
    """轮数预算耗尽——模型一直要工具，硬终止触发。"""


@dataclass(frozen=True)
class AgentResult:
    final_text: str
    messages: list[dict]  # 完整对话史（审计与调试用）
    turns: int  # 实际消耗的轮数（一次模型调用 = 一轮）


class ReActAgent:
    """注册表驱动的 ReAct agent。client 只依赖 ModelClient 协议（真实/离线可互换）。"""

    def __init__(self, client: ModelClient, registry: dict[str, ToolSpec] = TOOL_REGISTRY, max_turns: int = 8):
        self._client = client
        self._registry = registry
        self._max_turns = max_turns

    async def run(self, user_message: str, system: str = DEFAULT_SYSTEM) -> AgentResult:
        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]
        tools = to_openai_tools(self._registry)  # 契约随每一轮下发（无状态协议，L2.1 §2.2）
        for turn in range(1, self._max_turns + 1):
            response = await self._client.complete(messages, tools)
            message = response["choices"][0]["message"]
            messages.append(message)  # 模型的消息原样入史（含 tool_calls，不可裁剪）
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return AgentResult(final_text=message.get("content") or "", messages=messages, turns=turn)
            for tool_call in tool_calls:  # 并行 tool_calls：逐个执行、逐个回喂
                result = run_tool(
                    tool_call["function"]["name"],
                    tool_call["function"]["arguments"],
                    registry=self._registry,
                )
                messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result})
        raise AgentBudgetExceeded(
            f"{self._max_turns} 轮预算耗尽（历史 {len(messages)} 条消息仍未收敛）——"
            f"检查 system 提示是否诱导无限调用，或工具结果是否总在报错。"
        )


def print_trace(messages: Sequence[dict]) -> None:
    """按角色打印完整消息史（demo 取证用）。"""
    for message in messages:
        role = message["role"]
        if "tool_calls" in message:
            calls = ", ".join(c["function"]["name"] for c in message["tool_calls"])
            print(f"  {role:>9}: [选了工具: {calls}]")
        elif role == "tool":
            print(f"  {role:>9}: {str(message['content'])[:46]}  (id={message['tool_call_id']})")
        else:
            print(f"  {role:>9}: {str(message['content'])[:46]}")
