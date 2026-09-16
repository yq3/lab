# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""interrupt 双路：human_gate 的暂停调用与恢复侧的 Command(resume=...)。

考察点：节点里 interrupt(payload) 的「抛-捕-暂停」语义（payload 随状态落盘、
恢复时同一节点从头重执行、interrupt() 返回人工值）；恢复侧 invoke 的第一个参数
是 Command(resume=值) 而不是状态输入——状态从 checkpoint 来，人工只递「决策」。
非 ESCALATE 单根本不会走到 human_gate（条件边直送 finalize，零暂停）。

完成判据：uv run pytest exercises/test_ex2.py 全绿——三个测试：
  ESCALATE 单停在 human_gate（next 与 payload 断言）；
  approve 与 deny 两路最终结论不同（APPROVE/PASS/human=approve vs
  REJECT/REJECT:HUMAN_DENIED/human=deny）；
  非 ESCALATE 单零暂停（next 为空、advice.human == "skipped"）。
TODO 所需的顶部 import：
  from langgraph.types import Command, interrupt
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

import demo
import review_rules
from advice import Advice
from demo import HumanDecision, ReviewOutcome
from mock_endpoint import MockLLMEndpoint


class GateState(TypedDict):
    """图状态（讲义 ClaimState 同构）：messages/events 合并，advice 只由 finalize 写。"""

    messages: Annotated[list, demo.add_messages]
    events: Annotated[list[str], demo.operator.add]
    advice: NotRequired[ReviewOutcome]
    human_decision: NotRequired[HumanDecision]


def parse_last_advice(state: GateState) -> Advice | None:
    """把最后一条 AI 消息解析成 Advice；解析不了返回 None（给定）。"""
    return demo.parse_advice_text(state["messages"][-1].content)


def make_reviewer(model: Runnable):
    """reviewer 节点工厂（给定，与讲义同构）。"""

    async def reviewer(state: GateState) -> dict:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response], "events": ["reviewer"]}

    return reviewer


async def tools_node(state: GateState) -> dict:
    """tools 节点（给定）：注册表分发 + 回喂 ToolMessage。"""
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
    """条件边（给定）：有 tool_calls 去 tools；ESCALATE 建议单进人审门；其他直接收束。"""
    if state["messages"][-1].tool_calls:
        return "tools"
    advice = parse_last_advice(state)
    if advice is not None and advice.decision == "ESCALATE":
        return "human_gate"
    return "finalize"


async def human_gate(state: GateState) -> dict:
    """人审门（你的 TODO）：ESCALATE 单在这里暂停等人。

    payload 必须是 {"claim_id": ..., "reason": ...}（单号与触发转审的原因码）；
    interrupt() 的返回值是人工决策，把它写进状态：human_decision 键（原样字符串）
    + 一条 user 消息把决策告知模型（讲义 human_gate 同构）。
    """
    # TODO(ex2): advice = parse_last_advice(state)；answer = interrupt(带 claim_id/reason 的 dict)；
    #   返回 {"messages": [一条 user 消息，内容含 answer], "events": ["human_gate"], "human_decision": answer}
    raise NotImplementedError("TODO(ex2): 补全 human_gate 的 interrupt 调用与状态更新")


async def finalize(state: GateState) -> dict:
    """finalize 节点（给定）：解析最终回答 + human_decision 合成 ReviewOutcome。"""
    advice = parse_last_advice(state)
    if advice is None:
        raise ValueError("finalize 收到无法解析的最终回答")
    human: HumanDecision = state.get("human_decision", "skipped")
    return {"advice": ReviewOutcome(**advice.model_dump(), human=human), "events": ["finalize"]}


def build_gate(model: Runnable, checkpointer: BaseCheckpointSaver[str] | None) -> CompiledStateGraph:
    """装配（给定）：三节点审查图 + human_gate，checkpointer 由调用方传入。"""
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
    """「进程 1」（给定）：跑到人审门暂停（或非 ESCALATE 一跑到底）。返回 (invoke 结果, thread_id)。"""
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
    """「进程 2」（你的 TODO 在最后一行）：新端点、新图实例、同一个 db——注入人工决策。

    剧本已布置好（post_human_advice 按你的 decision 生成最终台词）；
    你只欠一次恢复调用：第一个参数不是状态 dict，而是带着人工决策的 Command。
    """
    cfg = demo.thread_config(thread_id)
    with MockLLMEndpoint() as ep:
        async with demo.open_saver(db_path) as saver:
            graph = build_gate(demo.model_for_url(ep.url), saver)
            snapshot = await graph.aget_state(cfg)
            paused = parse_last_advice({"messages": snapshot.values["messages"], "events": []})
            if paused is None:
                raise ValueError("暂停点状态里解析不出建议单")
            ep.script_text(demo.post_human_advice(paused, decision).model_dump_json())
            # TODO(ex2): result = await graph.ainvoke(???, cfg) —— ??? 处放 Command(resume=decision)
            result: dict = {}
    return result
