# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""重规划环补全：plan_gate 的拒绝分支（原因入 state）+ 条件边三分支路由。

考察点：A29「失败原因显式状态键」——PlanRejection 进 plan_rejections（合并语义的键），
events 落 plan.rejected:<原因码>；route_after_gate 三分支（valid→executor /
invalid 未超限→回 planner / 超限→escalate），MAX_REPLANS=2 封顶——第 3 次拒绝时
重规划已用满，转收尾哨兵。图装配已给定（本题考点在环，不在连线）。
planner 是离线替身 FakePlanner（无 HTTP），重规划的回喂消息已给定——
它每次调用收到的消息都会被记录（invocations），验收用它断言「原因真的被回喂了」。

完成判据：uv run pytest exercises/test_ex3.py 全绿——3 个测试：
  clean：一轮通过——events 恰好 [planner, plan.approved, executor, submit]、sent=True、零拒绝；
  dirty_once：恰好一次拒绝（unknown_tool）+ 恰好一次回喂（planner 第 2 次调用才看到拒绝原因）
    + 第 2 轮通过正常收尾；
  always_dirty：三次拒绝、planner 恰好 3 轮（replans==2 用满）、escalate 收尾、sent=False、
    events 含 plan.rejected:<原因码> 审计事件。
本文件无需新增 import——TODO 用到的都已预置。
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

from plan import Plan, PlanRejection, validate_plan

MAX_REPLANS = 2


class ReplanState(TypedDict):
    """重规划环的最小状态：计划半边 + 审计流水 + 送审标志（讲义 ExpenseState 的环内子集）。"""

    messages: Annotated[list, add_messages]
    plan: NotRequired[Plan]
    plan_rejections: Annotated[list[PlanRejection], operator.add]
    events: Annotated[list[str], operator.add]
    sent: NotRequired[bool]


class FakePlanner:
    """离线模型替身（given）：按剧本依次回 AIMessage；记录每次调用看到的输入消息。"""

    def __init__(self, scripts: list[str]) -> None:
        self._scripts = list(scripts)
        self.invocations: list[list] = []

    async def ainvoke(self, messages: list) -> AIMessage:
        self.invocations.append(list(messages))
        return AIMessage(content=self._scripts.pop(0))


def make_planner(model: FakePlanner):
    """planner 节点（given）：重规划轮把最新拒绝原因与上一版计划作为 user 消息回喂。"""

    async def planner(state: ReplanState) -> dict:
        extra: list[dict] = []
        rejections = state.get("plan_rejections") or []
        if rejections:
            previous_plan = state["messages"][-1].content
            extra.append(
                {
                    "role": "user",
                    "content": (
                        f"上一版计划被拒（{rejections[-1].reason_code}）：{rejections[-1].detail}\n"
                        f"上一版原文：\n{previous_plan}\n请重新规划。"
                    ),
                }
            )
        response = await model.ainvoke(state["messages"] + extra)
        return {"messages": extra + [response], "events": ["planner"]}

    return planner


def plan_gate(state: ReplanState) -> dict:
    """校验门（本体复用讲义 plan.validate_plan）：你的 TODO 是拒绝分支的「原因入 state」。"""
    outcome = validate_plan(state["messages"][-1].content)
    if isinstance(outcome, PlanRejection):
        # TODO(ex3): 拒绝原因怎么入 state——问：放进哪个键？值的形态是什么
        #   （提示：那个键的 Annotated reducer 每次收到的是什么）？events 里按讲义约定登记
        #   「plan.rejected:」拼什么？合法分支（已给定）怎么写的，对照着推。
        raise NotImplementedError("TODO(ex3): 拒绝分支")
    return {"plan": outcome, "events": ["plan.approved"]}


def route_after_gate(state: ReplanState) -> Literal["executor", "planner", "escalate"]:
    # TODO(ex3): 三分支路由——问：合法与否看哪个键（NotRequired 键缺席时 state.get 给什么）？
    #   未超限的条件拿 plan_rejections 的长度与 MAX_REPLANS 怎么比（第 3 次拒绝时 replans 是几）？
    raise NotImplementedError("TODO(ex3): 三分支路由")


# ---- 下游节点与装配（given）：executor 环节以桩代之，本题只练环 ----


def executor_stub(state: ReplanState) -> dict:
    return {"events": ["executor"]}


def submit(state: ReplanState) -> dict:
    return {"sent": True, "events": ["submit"]}


def escalate(state: ReplanState) -> dict:
    return {"sent": False, "events": ["escalate"]}


def build(model: FakePlanner) -> CompiledStateGraph:
    """装配（given）：START → planner → plan_gate ─三分支→ executor→submit / planner（环）/ escalate。"""
    builder = StateGraph(ReplanState)
    builder.add_node("planner", make_planner(model))
    builder.add_node("plan_gate", plan_gate)
    builder.add_node("executor", executor_stub)
    builder.add_node("submit", submit)
    builder.add_node("escalate", escalate)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "plan_gate")
    builder.add_conditional_edges("plan_gate", route_after_gate)
    builder.add_edge("executor", "submit")
    builder.add_edge("submit", END)
    builder.add_edge("escalate", END)
    return builder.compile()


def initial_state(brief: str) -> dict:
    return {"messages": [{"role": "user", "content": brief}]}
