# 练习 2（单变量编辑约束：只改本文件 TODO 标注区**与所需的顶部 import**，其余不要动）
"""预算封顶：补全 LLMCallBudget 的 ainvoke——计数 + 超限抛 BudgetExceeded。

对版改造（产品的第二个旋钮）：TradingAgents 只有 superstep 预算（max_recur_limit=100），
没有模型调用预算——本课补上这条轴（讲义 code/budget.py 是同构成品，对照 L2.3 的
AgentBudgetExceeded）。图是给定的「申辩人 → 合规官 → 整理 → 裁决官」四节点小图：
3 次模型调用、4 个 superstep——「整理」不调模型，两条预算轴从这里分叉。

完成判据：uv run pytest exercises/test_ex2.py 全绿——三个测试：
  cap=3（恰好够）：全图完成，budget.used == 3，终态有裁决文本；
  cap=2（中途烧穿）：BudgetExceeded 抛出，budget.used == 2（已调用次数恰好 = cap，
                   被拒的那次没有打到模型——inner.request_count 也是 2）；
  recursion_limit=3（另一条轴）：抛 GraphRecursionError 而不是 BudgetExceeded，
                   模型只被调了 2 次——superstep 预算在不调模型的「整理」上照样烧。
TODO 所需的顶部 import：无（全部已预置）。
"""

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
    """能 ainvoke 的就是模型客户端（L1.2 Protocol 复习）——替身与预算包装都满足它。"""

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage: ...


class MiniState(TypedDict):
    """小图状态：嵌套 debate 无 reducer；settlement 是「整理」节点的产出。"""

    messages: Annotated[list, add_messages]
    debate: dict  # history / current_speaker / count
    settlement: NotRequired[str]
    ruling: NotRequired[str]


class BudgetExceeded(Exception):
    """模型调用预算耗尽（对照 L2.3 AgentBudgetExceeded / langgraph GraphRecursionError）。"""


class FakeChatModel:
    """离线模型替身：按剧本依次回 AIMessage（request_count 是两轴分叉的取证）。"""

    def __init__(self, scripts: list[str]) -> None:
        self._scripts = list(scripts)
        self.request_count = 0

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        self.request_count += 1
        return AIMessage(content=self._scripts.pop(0))


def create_speaker(model: ChatClient, speaker: str):
    """发言节点：1 次模型调用 + 手工回填嵌套 debate 全部键。"""

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
    """裁决官节点：第 3 次模型调用。"""

    async def ruling_node(state: MiniState) -> dict:
        response = await model.ainvoke([{"role": "user", "content": "请裁决"}])
        return {"ruling": f"裁决：{response.content}"}

    return ruling_node


async def settle_node(state: MiniState) -> dict:
    """整理节点：不调模型（superstep 照烧、模型预算不动——两条轴的分叉点）。"""
    return {"settlement": f"辩论定稿：{state['debate']['history'][:20]}…"}


def build(model: ChatClient) -> CompiledStateGraph:
    """装配：申辩人 → 合规官 → 整理 → 裁决官 → END（线性给定，不需要改）。

    model 同时喂给三个发言节点（对照讲义「一个预算罩住整张图」的最小版）。
    """
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
    """模型调用预算：包装模型客户端——计数、超限抛 BudgetExceeded。

    build(budget) 的三个发言节点都经它调用模型：预算是模型调用层面的闸门，
    图结构一行不改（对照讲义 code/budget.py 的 BudgetedModel 拆分，这里单类简化）。
    """

    def __init__(self, model: FakeChatModel, limit: int | None = None) -> None:
        self._model = model
        self._limit = limit
        self._used = 0

    @property
    def used(self) -> int:
        """已放行的模型调用次数。"""
        return self._used

    @property
    def limit(self) -> int | None:
        """预算上限（None = 不限）。"""
        return self._limit

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        # TODO(ex2): 检查-放行-计数-委托的顺序是什么？limit 为 None 意味着什么？
        # 超限时抛 BudgetExceeded——异常信息要让运维看得懂（带上限与已用次数）；
        # 被拒的调用不能打到被包装的模型（不超卖）。签名已给，补全函数体。
        raise NotImplementedError("TODO(ex2): 补全预算检查与计数")
