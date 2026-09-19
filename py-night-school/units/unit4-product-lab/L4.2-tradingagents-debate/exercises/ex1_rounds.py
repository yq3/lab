# 练习 1（单变量编辑约束：只改本文件 TODO 标注区**与所需的顶部 import**，其余不要动）
"""辩论轮次参数化：骨架把轮次写死成 1（路由器硬编码 + 装配无视 config），改造成 config 驱动。

对版改造（产品的第一个旋钮）：TradingAgents 的 max_debate_rounds 从 default_config.py
流进 ConditionalLogic 构造器（还有 TRADINGAGENTS_MAX_DEBATE_ROUNDS env 第二层覆盖）；
讲义 code/conditional.py#AppealConditionalLogic(config) 是同构成品。本练习的图只有
辩论段 + 裁决官（政策分析师/风险段都裁掉），模型是离线替身 FakeChatModel——零 HTTP。

完成判据：uv run pytest exercises/test_ex1.py 全绿——三个测试：
  rounds=1：节点序列恰好 [申辩人, 合规官, 裁决官]，模型恰好 2 次调用（辩论段 = 2*rounds；
            裁决官是占位节点，不调模型）；
  rounds=2：节点序列 [申辩人, 合规官, 申辩人, 合规官, 裁决官]（申辩人与合规官交替），
            模型恰好 4 次调用——辩论段恰好 2*rounds 次；
  path_map 覆盖：两态跑完出现过的节点恰好铺满 DEBATE_PATH_MAP 的键集（无死条目）。
TODO 所需的顶部 import：无（全部已预置）。
"""

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

# 对版 setup.py#DEBATE_PATH_MAP（#1088）：每条辩论条件边都映射路由器的全部可能返回值
# 注解 dict[Hashable, str]：langgraph 的 path_map 形参是不变型的 dict[Hashable, str]
DEBATE_PATH_MAP: dict[Hashable, str] = {
    APPLICANT: APPLICANT,
    OFFICER: OFFICER,
    RULING: RULING,
}


@dataclass(frozen=True)
class RoundsConfig:
    """轮次配置（讲义 AppealConfig 的辩论子集——immutable config bean）。"""

    max_debate_rounds: int = 1


class MiniDebateState(TypedDict):
    """辩论小图状态：嵌套 debate 无 reducer（整体替换，辩手工回填全部键）。"""

    messages: Annotated[list, add_messages]
    debate: dict  # history / current_speaker / count
    ruling: NotRequired[str]


class FakeChatModel:
    """离线模型替身：按剧本依次回 AIMessage（request_count 是次数断言的取证）。"""

    def __init__(self, scripts: list[str]) -> None:
        self._scripts = list(scripts)
        self.request_count = 0

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        self.request_count += 1
        return AIMessage(content=self._scripts.pop(0))


def create_debater(model: FakeChatModel, speaker: str):
    """辩手节点：1 次模型调用 + 手工回填嵌套 debate 全部键（讲义 debaters.py 同款纪律）。"""

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
    """裁决官占位节点（不调模型——只收口）。"""
    return {"ruling": f"裁决：辩论共 {state['debate']['count']} 次发言"}


class DebateRouter:
    """对版 conditional_logic.py#ConditionalLogic——终止计数与前缀轮转的**逻辑已给对**。

    唯一的问题：轮次被写死成 1，构造后不再看任何配置。
    """

    def __init__(self) -> None:
        # TODO(ex1-a): 这个 1 不该写死——轮次应该从哪里来？给构造器加什么参数、装配处怎么传，
        # 才能让同一个路由器类既服务 rounds=1 也服务 rounds=2？（提示：RoundsConfig 已经在场）
        self.max_debate_rounds = 1

    def should_continue_debate(self, state: MiniDebateState) -> str:
        """计数终止 + 前缀轮转（这段逻辑保持原样，不要动）。"""
        if state["debate"]["count"] >= 2 * self.max_debate_rounds:
            return RULING
        if state["debate"]["current_speaker"].startswith(APPLICANT):
            return OFFICER
        return APPLICANT


def build(config: RoundsConfig, model: FakeChatModel) -> CompiledStateGraph:
    """装配辩论小图：START → 申辩人 ⇄（条件边）合规官 →（计数终止）裁决官 → END。

    辩论双方的条件边都挂 DebateRouter.should_continue_debate，并共享 DEBATE_PATH_MAP
    全量映射（对版 setup.py：两条辩论边共用一个 path_map，#1088）。
    """
    builder = StateGraph(MiniDebateState)
    builder.add_node(APPLICANT, create_debater(model, APPLICANT))
    builder.add_node(OFFICER, create_debater(model, OFFICER))
    builder.add_node(RULING, ruling_node)
    # TODO(ex1-b): 装配按 config——router 现在无视 config 里的轮次（现状：永远 1 轮）。
    # 让 router 拿到的轮次跟着 config 走（与 ex1-a 是同一个改动的两端）。
    router = DebateRouter()
    builder.add_edge(START, APPLICANT)
    for node in (APPLICANT, OFFICER):
        builder.add_conditional_edges(node, router.should_continue_debate, DEBATE_PATH_MAP)
    builder.add_edge(RULING, END)
    return builder.compile()
