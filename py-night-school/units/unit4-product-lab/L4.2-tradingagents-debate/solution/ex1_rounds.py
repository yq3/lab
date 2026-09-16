# 参考答案：ex1_rounds（练习文件的完整解法——完成前别看）
"""辩论轮次参数化：路由器与装配都改成 config 驱动。"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

APPLICANT = "申辩人"
OFFICER = "合规官"
RULING = "裁决官"

DEBATE_PATH_MAP: dict[Hashable, str] = {
    APPLICANT: APPLICANT,
    OFFICER: OFFICER,
    RULING: RULING,
}


@dataclass(frozen=True)
class RoundsConfig:
    max_debate_rounds: int = 1


class MiniDebateState(TypedDict):
    messages: Annotated[list, add_messages]
    debate: dict
    ruling: NotRequired[str]


class FakeChatModel:
    def __init__(self, scripts: list[str]) -> None:
        self._scripts = list(scripts)
        self.request_count = 0

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        self.request_count += 1
        return AIMessage(content=self._scripts.pop(0))


def create_debater(model: FakeChatModel, speaker: str):
    async def debater(state: MiniDebateState) -> dict:
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

    return debater


async def ruling_node(state: MiniDebateState) -> dict:
    return {"ruling": f"裁决：辩论共 {state['debate']['count']} 次发言"}


class DebateRouter:
    """改造后：轮次由构造参数传入（对版 ConditionalLogic(max_debate_rounds=...)）。"""

    def __init__(self, max_debate_rounds: int) -> None:
        self.max_debate_rounds = max_debate_rounds

    def should_continue_debate(self, state: MiniDebateState) -> str:
        if state["debate"]["count"] >= 2 * self.max_debate_rounds:
            return RULING
        if state["debate"]["current_speaker"].startswith(APPLICANT):
            return OFFICER
        return APPLICANT


def build(config: RoundsConfig, model: FakeChatModel) -> CompiledStateGraph:
    builder = StateGraph(MiniDebateState)
    builder.add_node(APPLICANT, create_debater(model, APPLICANT))
    builder.add_node(OFFICER, create_debater(model, OFFICER))
    builder.add_node(RULING, ruling_node)
    router = DebateRouter(config.max_debate_rounds)  # 装配按 config：轮次跟着配置走
    builder.add_edge(START, APPLICANT)
    for node in (APPLICANT, OFFICER):
        builder.add_conditional_edges(node, router.should_continue_debate, DEBATE_PATH_MAP)
    builder.add_edge(RULING, END)
    return builder.compile()
