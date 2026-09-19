# 参考答案：ex2_budget（练习文件的完整解法——完成前别看）
"""预算封顶：LLMCallBudget 补全——检查在放行前、计数在放行后、委托给被包装模型。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, NotRequired, Protocol, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

APPLICANT = "申辩人"
OFFICER = "合规官"
SETTLE = "整理"
RULING = "裁决官"


class ChatClient(Protocol):
    async def ainvoke(self, messages: Sequence[object]) -> AIMessage: ...


class MiniState(TypedDict):
    messages: Annotated[list, add_messages]
    debate: dict
    settlement: NotRequired[str]
    ruling: NotRequired[str]


class BudgetExceeded(Exception):
    """模型调用预算耗尽（对照 L2.3 AgentBudgetExceeded / langgraph GraphRecursionError）。"""


class FakeChatModel:
    def __init__(self, scripts: list[str]) -> None:
        self._scripts = list(scripts)
        self.request_count = 0

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        self.request_count += 1
        return AIMessage(content=self._scripts.pop(0))


def create_speaker(model: ChatClient, speaker: str):
    async def speaker_node(state: MiniState) -> dict:
        debate = state["debate"]
        response = await model.ainvoke([{"role": "user", "content": f"你是{speaker}，请发言"}])
        turn = f"{speaker}：{response.content}"
        return {
            "debate": {
                "history": (debate.get("history", "") + "\n" + turn).strip("\n"),
                "current_speaker": turn,
                "count": debate["count"] + 1,
            }
        }

    return speaker_node


def create_ruling(model: ChatClient):
    async def ruling_node(state: MiniState) -> dict:
        response = await model.ainvoke([{"role": "user", "content": "请裁决"}])
        return {"ruling": f"裁决：{response.content}"}

    return ruling_node


async def settle_node(state: MiniState) -> dict:
    return {"settlement": f"辩论定稿：{state['debate']['history'][:20]}…"}


def build(model: ChatClient) -> CompiledStateGraph:
    builder = StateGraph(MiniState)
    builder.add_node(APPLICANT, create_speaker(model, APPLICANT))
    builder.add_node(OFFICER, create_speaker(model, OFFICER))
    builder.add_node(SETTLE, settle_node)
    builder.add_node(RULING, create_ruling(model))
    builder.add_edge(START, APPLICANT)
    builder.add_edge(APPLICANT, OFFICER)
    builder.add_edge(OFFICER, SETTLE)
    builder.add_edge(SETTLE, RULING)
    builder.add_edge(RULING, END)
    return builder.compile()


class LLMCallBudget:
    """补全后的预算包装：检查-放行-计数-委托（对照讲义 code/budget.py#BudgetedModel）。"""

    def __init__(self, model: FakeChatModel, limit: int | None = None) -> None:
        self._model = model
        self._limit = limit
        self._used = 0

    @property
    def used(self) -> int:
        return self._used

    @property
    def limit(self) -> int | None:
        return self._limit

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        if self._limit is not None and self._used >= self._limit:  # 检查在放行前：不超卖
            raise BudgetExceeded(f"LLM 调用预算耗尽：limit={self._limit}, 已调用 {self._used} 次")
        result = await self._model.ainvoke(messages)  # 委托给被包装的模型
        self._used += 1  # 计数在放行后：被拒的调用不计入
        return result
