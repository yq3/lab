"""Step5 subgraph：把「模型 + 工具」的审查循环打包成一个节点，挂进外层流程图。

外层图：START → intake → review(子图) → report → END
子图内：START → reviewer ⇄(条件边) tools → finalize → END（与 demo.build_graph 同构）

两个教学点：
- 编译好的图可以直接 add_node——「图即节点」，对照 Java 工作流引擎的子流程（call activity）；
- 子图对外是黑盒：内部状态只有 messages + advice，外层的 events 流水看不到子图内部——
  这是有意的（reducer 在子图边界会重复施加，operator.add 的 events 会被算两遍；
  messages 的 add_messages 按 id 去重，跨图边界安全——本脚本实测为证）。

langsmith 追踪：本课不设 LANGSMITH_* 环境变量，默认关闭、零外发（对照 L3.1 开课先关 trace）。
"""

from __future__ import annotations

import asyncio
import json
import operator
from typing import Annotated, NotRequired, TypedDict

from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

import demo
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint


class ReviewState(TypedDict):
    """子图状态：审查循环只关心消息史与最终建议单（刻意不含 events——见模块 docstring）。"""

    messages: Annotated[list, add_messages]
    advice: NotRequired[Advice]


class FlowState(TypedDict):
    """外层状态：claim_id 进、advice 出；events 只登记外层节点。"""

    claim_id: str
    messages: Annotated[list, add_messages]
    advice: NotRequired[Advice]
    events: Annotated[list[str], operator.add]


# ---- 子图节点：与 demo.py 同构，但不写 events（黑盒边界的教学取舍） ----


def make_reviewer(model: Runnable):
    async def reviewer(state: ReviewState) -> dict:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response]}

    return reviewer


async def tools_node(state: ReviewState) -> dict:
    results: list[dict] = []
    for call in state["messages"][-1].tool_calls:
        func = demo.TOOL_REGISTRY.get(call["name"])
        if func is None:
            content = json.dumps({"error": f"unknown_tool: {call['name']}"}, ensure_ascii=False)
        else:
            content = json.dumps(func(**call["args"]), ensure_ascii=False)  # 工具真实执行
        results.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    return {"messages": results}


def route_after_reviewer(state: ReviewState) -> str:
    return "tools" if state["messages"][-1].tool_calls else "finalize"


async def finalize(state: ReviewState) -> dict:
    text = state["messages"][-1].content
    return {"advice": Advice.model_validate_json(text.strip())}


def build_review_subgraph(model: Runnable) -> CompiledStateGraph:
    """模型 + 工具 + 收束节点 → 打包成一个子图（对外就是一个节点）。"""
    b = StateGraph(ReviewState)
    b.add_node("reviewer", make_reviewer(model))
    b.add_node("tools", tools_node)
    b.add_node("finalize", finalize)
    b.add_edge(START, "reviewer")
    b.add_conditional_edges("reviewer", route_after_reviewer)
    b.add_edge("tools", "reviewer")
    b.add_edge("finalize", END)
    return b.compile()


# ---- 外层节点：intake 组装上下文，report 收口 ----


async def intake(state: FlowState) -> dict:
    return {"messages": demo.initial_messages(state["claim_id"]), "events": ["intake"]}


async def report(state: FlowState) -> dict:
    return {"events": ["report"]}


def build_flow(model: Runnable) -> CompiledStateGraph:
    b = StateGraph(FlowState)
    b.add_node("intake", intake)
    b.add_node("review", build_review_subgraph(model))  # 图即节点：编译产物直接 add_node
    b.add_node("report", report)
    b.add_edge(START, "intake")
    b.add_edge("intake", "review")
    b.add_edge("review", "report")
    b.add_edge("report", END)
    return b.compile()


async def main() -> None:
    claim_id = "CLM-2026-0001"
    print(f"== Step5 subgraph：把审查循环打包成一个节点（{claim_id}） ==")
    print("外层: START → intake → review(子图) → report → END")
    first_turn, advice_json, _expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        graph = build_flow(demo.model_for_url(ep.url))
        result = await graph.ainvoke(
            {"claim_id": claim_id, "messages": [], "events": []},
            config={"recursion_limit": demo.RECURSION_LIMIT},
        )
        requests = len(ep.requests)
    advice_out: Advice = result["advice"]
    print(f"advice: {advice_out.decision} / {advice_out.reason} / 剩余 {advice_out.remaining_cents} 分")
    print(f"外层 events: {result['events']}  <- 子图是黑盒，内部审计留在内部")
    print(f"消息史: {len(result['messages'])} 条（intake 写 2 条 + 子图回 4 条，add_messages 跨边界按 id 去重）")
    print(f"模型请求: {requests} 次——整条流水线的行为与 demo.py 的扁平图完全一致")


if __name__ == "__main__":
    asyncio.run(main())
