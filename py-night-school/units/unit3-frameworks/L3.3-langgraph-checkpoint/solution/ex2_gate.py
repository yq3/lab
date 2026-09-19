# 参考答案：ex2（与骨架同构，只填 TODO 区——对照要点见 solution/README.md）
"""interrupt 双路：human_gate 的暂停调用与恢复侧的 Command(resume=...)。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt

import demo
import review_rules
from advice import Advice
from demo import HumanDecision, ReviewOutcome
from mock_endpoint import MockLLMEndpoint


class GateState(TypedDict):
    messages: Annotated[list, demo.add_messages]
    events: Annotated[list[str], demo.operator.add]
    advice: NotRequired[ReviewOutcome]
    human_decision: NotRequired[HumanDecision]


def parse_last_advice(state: GateState) -> Advice | None:
    return demo.parse_advice_text(state["messages"][-1].content)


def make_reviewer(model: Runnable):
    async def reviewer(state: GateState) -> dict:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response], "events": ["reviewer"]}

    return reviewer


async def tools_node(state: GateState) -> dict:
    tool_funcs: dict[str, Callable[..., dict]] = dict(demo.TOOL_REGISTRY)
    results: list[dict] = []
    for call in state["messages"][-1].tool_calls:
        func = tool_funcs.get(call["name"])
        if func is None:
            content = json.dumps({"error": f"unknown_tool: {call['name']}"}, ensure_ascii=False)
        else:
            content = json.dumps(func(**call["args"]), ensure_ascii=False)
        results.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    return {"messages": results, "events": ["tools"]}


def route_after_reviewer(state: GateState) -> Literal["tools", "human_gate", "finalize"]:
    if state["messages"][-1].tool_calls:
        return "tools"
    advice = parse_last_advice(state)
    if advice is not None and advice.decision == "ESCALATE":
        return "human_gate"
    return "finalize"


async def human_gate(state: GateState) -> dict:
    """人审门：interrupt() 第一次抛 GraphInterrupt 暂停；恢复重执行时返回人工决策。"""
    advice = parse_last_advice(state)
    if advice is None:
        raise ValueError("human_gate 只应在 reviewer 给出 ESCALATE 建议单后到达")
    answer = interrupt({"claim_id": advice.claim_id, "reason": advice.reason})
    return {
        "messages": [{"role": "user", "content": f"人工审批结果：{answer}。请输出最终建议单 JSON。"}],
        "events": ["human_gate"],
        "human_decision": answer,
    }


async def finalize(state: GateState) -> dict:
    advice = parse_last_advice(state)
    if advice is None:
        raise ValueError("finalize 收到无法解析的最终回答")
    human: HumanDecision = state.get("human_decision", "skipped")
    return {"advice": ReviewOutcome(**advice.model_dump(), human=human), "events": ["finalize"]}


def build_gate(model: Runnable, checkpointer: BaseCheckpointSaver[str] | None) -> CompiledStateGraph:
    builder = demo.StateGraph(GateState)
    builder.add_node("reviewer", make_reviewer(model))
    builder.add_node("tools", tools_node)
    builder.add_node("human_gate", human_gate)
    builder.add_node("finalize", finalize)
    builder.add_edge(demo.START, "reviewer")
    builder.add_conditional_edges("reviewer", route_after_reviewer)
    builder.add_edge("tools", "reviewer")
    builder.add_edge("human_gate", "reviewer")
    builder.add_edge("finalize", demo.END)
    return builder.compile(checkpointer=checkpointer)


async def start_side(db_path: str, claim_id: str) -> tuple[dict, str]:
    thread_id = f"ex2-{claim_id}"
    cfg = demo.thread_config(thread_id)
    first_turn, advice_json, _expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        async with demo.open_saver(db_path) as saver:
            graph = build_gate(demo.model_for_url(ep.url), saver)
            result: dict = await graph.ainvoke({"messages": demo.initial_messages(claim_id)}, cfg)
    return result, thread_id


async def resume_side(db_path: str, thread_id: str, decision: Literal["approve", "deny"]) -> dict:
    """「进程 2」：新端点、新图实例、同一个 db——Command(resume=) 注入人工决策。"""
    cfg = demo.thread_config(thread_id)
    with MockLLMEndpoint() as ep:
        async with demo.open_saver(db_path) as saver:
            graph = build_gate(demo.model_for_url(ep.url), saver)
            snapshot = await graph.aget_state(cfg)
            paused = parse_last_advice({"messages": snapshot.values["messages"], "events": []})
            if paused is None:
                raise ValueError("暂停点状态里解析不出建议单")
            ep.script_text(demo.post_human_advice(paused, decision).model_dump_json())
            result: dict = await graph.ainvoke(Command(resume=decision), cfg)
    return result
