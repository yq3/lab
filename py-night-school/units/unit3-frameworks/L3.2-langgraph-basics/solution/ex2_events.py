# 参考答案：ex2_events（练习文件的完整解法——完成前别看）
"""自定义 reducer：给状态加审计流水 events，每个节点登记自己。"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph


class AuditState(TypedDict):
    items_cents: list[int]
    messages: Annotated[list, add_messages]
    events: Annotated[list[str], operator.add]  # 合并语义：每个节点的登记都会累积


def intake(state: AuditState) -> dict:
    return {
        "messages": [{"role": "user", "content": f"报销明细（分）：{state['items_cents']}"}],
        "events": ["intake"],
    }


def check(state: AuditState) -> dict:
    over = any(cents > 5000 for cents in state["items_cents"])
    return {
        "messages": [{"role": "assistant", "content": "check 完成：" + ("有超标明细" if over else "无超标明细")}],
        "events": ["check"],
    }


def route_after_check(state: AuditState) -> Literal["reject", "approve"]:
    over = any(cents > 5000 for cents in state["items_cents"])
    return "reject" if over else "approve"


def reject(state: AuditState) -> dict:
    return {"messages": [{"role": "assistant", "content": "REJECT:ITEM_OVER_LIMIT"}], "events": ["reject"]}


def approve(state: AuditState) -> dict:
    return {"messages": [{"role": "assistant", "content": "PASS"}], "events": ["approve"]}


def build() -> CompiledStateGraph:
    builder = StateGraph(AuditState)
    builder.add_node("intake", intake)
    builder.add_node("check", check)
    builder.add_node("reject", reject)
    builder.add_node("approve", approve)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", "check")
    builder.add_conditional_edges("check", route_after_check)
    builder.add_edge("reject", END)
    builder.add_edge("approve", END)
    return builder.compile()
