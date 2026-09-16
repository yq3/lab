# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""自定义 reducer：给状态加审计流水 events，每个节点登记自己。

考察点：add_messages 之外的合并语义——events 用 Annotated[list[str], operator.add] 声明；
每个节点的返回值登记一条事件，最终 events 就是精确的执行史（不同分支路由出不同的流水）。
节点函数是同步的（langgraph 节点可同步可异步，引擎自己适配）——本题零模型、零 HTTP。

完成判据：uv run pytest exercises/test_ex2.py 全绿——三个测试：
  超标路径 events 恰好 ["intake", "check", "reject"]；达标路径恰好 ["intake", "check", "approve"]；
  注解 meta 检查：events 必须是 operator.add 合并语义（若是覆盖语义，流水只剩最后一条，
  前两个断言也过不了——行为断言与 meta 检查互为印证）。
TODO 所需的顶部 import：
  import operator
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph


class AuditState(TypedDict):
    """审计流水状态：金额入口给定不再变（无 reducer 覆盖），messages 合并，events 是你要加的。"""

    items_cents: list[int]
    messages: Annotated[list, add_messages]
    # TODO(ex2): 加 events 字段——合并语义声明为 Annotated[list[str], operator.add]


def intake(state: AuditState) -> dict:
    """入口：把明细登记成一条 user 消息。"""
    # TODO(ex2): 返回值里再登记一条审计事件（"events" 键，事件名用节点名 "intake"）
    return {"messages": [{"role": "user", "content": f"报销明细（分）：{state['items_cents']}"}]}


def check(state: AuditState) -> dict:
    """核查：真实系统里这里会调工具；本题只写结论。"""
    over = any(cents > 5000 for cents in state["items_cents"])
    # TODO(ex2): 登记 "check" 事件
    return {"messages": [{"role": "assistant", "content": "check 完成：" + ("有超标明细" if over else "无超标明细")}]}


def route_after_check(state: AuditState) -> Literal["reject", "approve"]:
    """条件边：有超标明细走 reject，否则走 approve（装配已给定，只读 items_cents）。"""
    over = any(cents > 5000 for cents in state["items_cents"])
    return "reject" if over else "approve"


def reject(state: AuditState) -> dict:
    # TODO(ex2): 登记 "reject" 事件
    return {"messages": [{"role": "assistant", "content": "REJECT:ITEM_OVER_LIMIT"}]}


def approve(state: AuditState) -> dict:
    # TODO(ex2): 登记 "approve" 事件
    return {"messages": [{"role": "assistant", "content": "PASS"}]}


def build() -> CompiledStateGraph:
    """装配审计图：START → intake → check →（条件边）→ reject | approve → END（装配不是本题考点，已给定）。"""
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
