# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""Send 扇出改造：把批量审查图补完——自定义 dict 合并 reducer + 条件边返回 Send 列表。

考察点：归并半边的自定义 reducer——Annotated 第二参放你自己写的 (旧, 新) -> 合并 函数
（不是 operator.add：dict 不支持 +）；扇出半边的 Send——分支数到条件边执行那一刻才确定，
每个 Send 带一份分支专属状态。零模型、零 HTTP：worker 直接真实调用两个 mock 工具。

完成判据：uv run pytest exercises/test_ex1.py 全绿——三个测试：
  fan_out 返回 4 个 Send（目标节点名 / arg 形状：每份 arg 带 claim_id）；
  整图跑通：results 恰好按 claim_id 落位、四单 advice 与规则表预期全等、工具真实执行 8 次；
  注解 meta：results 必须挂「dict 浅合并」语义的自定义 reducer（覆盖语义会让 results 只剩最后一个分支）。
TODO 所需的顶部 import：
  from typing import Annotated
  from langgraph.graph import END   （加进现有那行 import）
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

import mock_tools
import review_rules
from advice import Advice


def review_one(claim_id: str) -> Advice:
    """单审纯函数（given）：真实调用两个 mock 工具 + 规则表决策——本题主角是图，不是它。"""
    view = mock_tools.claim_view(claim_id)
    budget = mock_tools.check_budget(view["dept"])
    invoice = mock_tools.verify_invoice(view["invoice_ids"][0])
    return review_rules.decide(view, budget, invoice)


class BatchState(TypedDict):
    """批量图状态：claim_ids 入口给定；counts 只由 reduce 写（覆盖语义）。"""

    claim_ids: list[str]
    # TODO(ex1): 把下面这行改成 Annotated[dict[str, Advice], 你的自定义 reducer]——
    #   reducer 是你自己写的具名函数（签名 (旧: dict, 新: dict) -> dict，返回 {**旧, **新}），
    #   定义放在模块顶部、Annotated 第二参放「函数对象」（不是函数调用）
    results: dict[str, Advice]  # <- 改这一行（目前是覆盖语义：Send 分支同超步多写会直接炸）
    counts: NotRequired[dict[str, int]]


class WorkerState(TypedDict):
    """Send 分支的专属状态（given）：Send 的 arg 就是 worker 的整个输入——只有本单单号。"""

    claim_id: str


def review_worker(state: WorkerState) -> dict:
    """worker（given）：它返回的更新写的是「主图」的 results 通道（节点返回值永远是通道更新，
    与输入 schema 无关）——map-reduce 的 map 半边。"""
    return {"results": {state["claim_id"]: review_one(state["claim_id"])}}


def reduce(state: BatchState) -> dict:
    """汇总节点（given）：全部分支落账后的下一个超步统一收割。"""
    counts: dict[str, int] = {}
    for claim_id in sorted(state["results"]):
        decision = state["results"][claim_id].decision
        counts[decision] = counts.get(decision, 0) + 1
    return {"counts": counts}


def dispatch(state: BatchState) -> dict:
    """入口节点（given）：不写状态——给扇出条件边一个锚点。"""
    return {}


def fan_out(state: BatchState) -> list[Send]:
    """扇出条件边：按 claim 列表造 N 个动态分支（你的 TODO）。"""
    # TODO(ex1): 返回 [Send("review", {"claim_id": claim_id}) for claim_id in state["claim_ids"]]
    raise NotImplementedError("TODO(ex1): 补 Send 列表")


def build() -> CompiledStateGraph:
    """装配（你的 TODO）：START → dispatch →（条件边 fan_out）→ review ×N → reduce → END。"""
    builder = StateGraph(BatchState)
    builder.add_node("dispatch", dispatch)
    builder.add_node("review", review_worker)
    builder.add_node("reduce", reduce)
    builder.add_edge(START, "dispatch")
    # TODO(ex1): dispatch 之后挂条件边（path 用 fan_out，它的返回值是 Send 列表）；
    #   review 到 reduce（N 个分支全部落账后 reduce 才在下一个超步执行）；reduce 收口到 END
    raise NotImplementedError("TODO(ex1): 补装配")
