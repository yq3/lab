"""ReAct agent（T1）：把 L2.3 的循环亲手装回来。

给定：AgentResult / AgentBudgetExceeded / 构造器 / 默认执行器接缝。
你的任务：补全 run() 的循环体——软硬双终止、原样入史、逐个回喂。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from model import ModelClient
from tools import TOOL_REGISTRY, ToolSpec, run_tool

DEFAULT_SYSTEM = (
    "你是财务预审助手。先用 get_claim 查单据明细，再用 preapprove 预审，最后按工具结果回答；"
    "结论只用 PASS 或 REJECT:<原因>。"
)

# 工具执行器接缝：(工具名, arguments JSON 字符串) -> 结果文本
# 默认走本地注册表；MCP 模式注入走协议的执行器（main.py --mcp 的全部秘密）
ToolExecutor = Callable[[str, str], Awaitable[str]]


class AgentBudgetExceeded(Exception):
    """轮数预算耗尽——模型一直要工具，硬终止触发（L2.3 §5 的纪律）。"""


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
        # TODO(t1): executor = execute or self._default_execute（接缝二选一）
        # TODO(t1): 顶部补 to_openai_tools 的 import；契约由 to_openai_tools(self._registry) 生成
        # TODO(t1): 组装初始 messages（system + user）
        # TODO(t1): for turn in range(1, max_turns + 1)：请求模型 → 消息原样入史 → 分支
        # TODO(t1):   无 tool_calls -> 返回 AgentResult(文本, messages, turn)（软终止）
        # TODO(t1):   有 -> 逐个执行 executor(name, arguments) 并回喂（id 配对）
        # TODO(t1): 耗尽 -> raise AgentBudgetExceeded（信息带轮数与历史条数）
        raise NotImplementedError("TODO(t1): 补全 run")


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
