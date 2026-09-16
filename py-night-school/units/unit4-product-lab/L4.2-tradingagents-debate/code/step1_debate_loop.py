"""Step1 辩论循环（零 LLM：FakeChatModel + 真路由 conditional.py）——本课教学主轴的最小复现。

三段演示（全部零 HTTP）：
1) 路由器直调：终止计数、前缀轮转、开场先手（空 current_speaker）逐条指认；
2) rounds=1 / rounds=2 两态跑真图（申辩人⇄合规官→裁决官）：打印每轮 count 与轮转，
   模型调用恰好 2*rounds 次——「可预算」的实证；
3) path_map 漂移防御（对版 issue #1088）：带标签漂移/空串的 current_speaker 走 startswith
   轮转，返回值全部落在 DEBATE_PATH_MAP 内——全量映射为什么必须存在。

对版源码：TauricResearch/TradingAgents@be952b8#tradingagents/graph/conditional_logic.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

from conditional import (
    APPLICANT_ADVOCATE,
    COMPLIANCE_OFFICER,
    DEBATE_PATH_MAP,
    RULING_OFFICIAL,
    AppealConditionalLogic,
)
from config import AppealConfig
from states import AppealState


class FakeChatModel:
    """离线模型替身：按剧本依次回 AIMessage（讲义 mock 端点的迷你版——不发 HTTP）。"""

    def __init__(self, scripts: list[str]) -> None:
        self._scripts = list(scripts)
        self.request_count = 0

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        self.request_count += 1
        return AIMessage(content=self._scripts.pop(0))


class LoopState(TypedDict):
    """辩论小图状态（AppealState 的辩论子集）：messages 只为占位，主角是嵌套 debate。"""

    messages: Annotated[list, add_messages]
    debate: dict  # 嵌套 dict 无 reducer：辩手必须回填全部键（debaters.py 同款纪律）
    ruling: NotRequired[str]


def create_debater(model: FakeChatModel, speaker: str):
    """辩手节点：1 次模型调用 + 手工回填嵌套 debate 全部键。"""

    async def debater(state: LoopState) -> dict:
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


async def ruling_placeholder(state: LoopState) -> dict:
    """裁决官占位节点（不调模型——本步只看辩论循环）。"""
    return {"ruling": f"终局：辩论共 {state['debate']['count']} 次发言后裁决"}


def build_debate_loop(config: AppealConfig, model: FakeChatModel) -> CompiledStateGraph:
    """装配辩论小图：申辩人⇄合规官（计数终止）→ 裁决官 → END（graph.py 辩论段的最小版）。"""
    builder = StateGraph(LoopState)
    builder.add_node(APPLICANT_ADVOCATE, create_debater(model, APPLICANT_ADVOCATE))
    builder.add_node(COMPLIANCE_OFFICER, create_debater(model, COMPLIANCE_OFFICER))
    builder.add_node(RULING_OFFICIAL, ruling_placeholder)
    router = AppealConditionalLogic(config)
    builder.add_edge(START, APPLICANT_ADVOCATE)
    for node in (APPLICANT_ADVOCATE, COMPLIANCE_OFFICER):  # 两条辩论边共享全量 path_map（#1088）
        builder.add_conditional_edges(node, router.should_continue_debate, DEBATE_PATH_MAP)
    builder.add_edge(RULING_OFFICIAL, END)
    return builder.compile()


def debate_state(count: int, speaker: str) -> AppealState:
    """构造只有 debate 有值的完整 AppealState（路由器只读这一个键——窄接口的实证）。"""
    return {
        "messages": [],
        "claim_id": "CLM-2026-0004",
        "policy_report": "",
        "debate": {
            "applicant_history": "",
            "office_history": "",
            "history": "",
            "current_speaker": speaker,
            "count": count,
        },
        "risk": {"history": "", "latest_speaker": "", "count": 0},
    }


async def main() -> None:
    print("== Step1 辩论循环：条件边循环 + 纯计数器终止（零 LLM） ==")

    print("[路由器直调（rounds=1，终止计数 = 2*1 = 2）]")
    router = AppealConditionalLogic(AppealConfig(max_debate_rounds=1))
    cases = [
        (0, "", "开场：current_speaker 为空 → 申辩人先手"),
        (1, "申辩人（钱工代理）：…", "申辩人刚发言（前缀轮转）→ 合规官"),
        (2, "合规官：…", "count=2 已达 2*rounds → 裁决官（终止）"),
        (1, "合规官：…", "count<2 且非申辩人前缀 → 申辩人"),
    ]
    for count, speaker, why in cases:
        target = router.should_continue_debate(debate_state(count, speaker))
        print(f"  count={count} speaker={speaker[:12]:<14} -> {target}  <- {why}")

    for rounds in (1, 2):
        scripts = [f"第{i}轮发言" for i in range(1, 2 * rounds + 1)]
        model = FakeChatModel(scripts)
        graph = build_debate_loop(AppealConfig(max_debate_rounds=rounds), model)
        print(f"[rounds={rounds} 真图轨迹（终止计数 = 2*{rounds} = {2 * rounds}）]")
        steps: list[str] = []
        async for chunk in graph.astream(
            {"messages": [], "debate": {"count": 0, "current_speaker": ""}}, stream_mode="updates"
        ):
            steps.extend(chunk.keys())
        print(f"  节点序列: {' → '.join(steps)}（裁决官是占位节点，不调模型）")
        print(f"  模型调用: {model.request_count} 次 = 恰好 2*rounds({2 * rounds})——辩论段可预算的实证")
        assert model.request_count == 2 * rounds

    print("[path_map 漂移防御（#1088）：任何 current_speaker，返回值都必落 DEBATE_PATH_MAP]")
    for speaker in ("申辩人（钱工代理）：…", "合规官（新标签）：…", "", "申辩人（Agresivo 漂移）：…"):
        target = router.should_continue_debate(debate_state(1, speaker))
        assert target in DEBATE_PATH_MAP
        print(f"  speaker={speaker[:16]:<18} -> {target}（∈ DEBATE_PATH_MAP）")


if __name__ == "__main__":
    asyncio.run(main())
