# 参考答案：ex1_fanout（练习文件的完整解法——完成前别看）
"""Send 扇出改造：把批量审查图补完——自定义 dict 合并 reducer + 条件边返回 Send 列表。"""

from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

import mock_tools
import review_rules
from advice import Advice


def review_one(claim_id: str) -> Advice:
    """单审纯函数：真实调用两个 mock 工具 + 规则表决策。"""
    view = mock_tools.claim_view(claim_id)
    budget = mock_tools.check_budget(view["dept"])
    invoice = mock_tools.verify_invoice(view["invoice_ids"][0])
    return review_rules.decide(view, budget, invoice)


def merge_advice(old: dict, new: dict) -> dict:
    """自定义 dict 合并 reducer：浅合并——各分支写不同的 claim_id 键，天然无冲突。"""
    return {**old, **new}


class BatchState(TypedDict):
    claim_ids: list[str]
    results: Annotated[dict[str, Advice], merge_advice]  # 归并：按 claim_id 落位（自定义 reducer）
    counts: NotRequired[dict[str, int]]


class WorkerState(TypedDict):
    """Send 分支的专属状态：Send 的 arg 就是 worker 的整个输入——只有本单单号。"""

    claim_id: str


def review_worker(state: WorkerState) -> dict:
    """worker：返回值写主图的 results 通道（map-reduce 的 map 半边）。"""
    return {"results": {state["claim_id"]: review_one(state["claim_id"])}}


def reduce(state: BatchState) -> dict:
    counts: dict[str, int] = {}
    for claim_id in sorted(state["results"]):
        decision = state["results"][claim_id].decision
        counts[decision] = counts.get(decision, 0) + 1
    return {"counts": counts}


def dispatch(state: BatchState) -> dict:
    return {}


def fan_out(state: BatchState) -> list[Send]:
    return [Send("review", {"claim_id": claim_id}) for claim_id in state["claim_ids"]]


def build() -> CompiledStateGraph:
    builder = StateGraph(BatchState)
    builder.add_node("dispatch", dispatch)
    builder.add_node("review", review_worker)
    builder.add_node("reduce", reduce)
    builder.add_edge(START, "dispatch")
    builder.add_conditional_edges("dispatch", fan_out)  # Send 列表 = 运行时动态并行分支
    builder.add_edge("review", "reduce")
    builder.add_edge("reduce", END)
    return builder.compile()
