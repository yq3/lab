"""L5.1 图本体：静态拓扑「取数→分析→生成建议单→送审」+ 重规划环 + 超限收尾（本课核心之二）。

固定拓扑（StateGraph，静态可审计——图形状能 diff、能签名，见 step2_signature.py）：

    START → intake → planner → plan_gate ─(valid)→ executor → drafter → submit → END
                        ↑ └─(invalid 且未超限：原因回喂重规划，MAX_REPLANS=2 封顶)
                        └─────────────────(超限)──────→ escalate → END（收尾哨兵，不送审）

两条设计轴（讲义 §2 展开）：
- 拓扑静态：LLM 动态性被压进两个合法位置——planner 产计划、drafter 叙述建议单；
  路由决策（route_after_gate）是确定性代码，对照 DataAgent 的 PlanExecutorDispatcher；
- 执行确定：executor 是纯 dispatcher，步进游标由代码掌握（executor.py），数字代码算。

状态键的合并/覆盖语义（L3.2 §2.3 的延续）：messages/events/plan_rejections 合并
（append-only 审计），results 用自定义 reducer 合并 dict（Annotated[list] 的 dict 版），
plan/advice/sent 覆盖（全图只有一个写者）。
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

import mock_tools
import prompts
from advice import Advice
from executor import execute_plan
from plan import Plan, PlanRejection, validate_plan

MAX_REPLANS = 2  # 重规划封顶：planner 最多被叫 1+2 次，第 3 次拒绝即超限转 escalate
RECURSION_LIMIT = 12  # superstep 预算：最坏链 intake+3×(planner+gate)+escalate=8，余量充足
ESCALATE_REASON = "REJECT:PLAN_REPLANS_EXCEEDED"  # 超限哨兵的枚举风格结论码


def merge_results(old: dict, new: dict) -> dict:
    """results 键的合并 reducer：dict 版的 Annotated[list, operator.add]。

    本课 executor 是唯一写者、一次写全；显式声明合并是为 L5.2/L5.3 预留契约——
    审批节点回写、事件溯源回放都会成为第二个写者，「覆盖」语义会静默吞数据（§5 坑位）。
    """

    return {**old, **new}


class ExpenseState(TypedDict):
    """图状态：节点间唯一的通信媒介。

    - messages：会话史（intake 的 system+brief、planner 的计划与重规划指令、drafter 的指令与建议单）；
    - plan / plan_rejections：计划半边的两个状态键——合法计划与拒绝原因（A29 显式状态键）；
    - results：executor 的取数产物（produces 键 → 工具返回），合并语义；
    - advice / sent：出口半边——建议单与送审标志，覆盖语义、单写者。
    """

    claim_id: str
    messages: Annotated[list, add_messages]
    plan: NotRequired[Plan]
    plan_rejections: Annotated[list[PlanRejection], operator.add]  # 拒绝原因逐次累积（回喂+审计）
    results: Annotated[dict[str, dict], merge_results]
    advice: NotRequired[Advice]
    events: Annotated[list[str], operator.add]  # 审计流水：节点名 + plan.approved/plan.rejected:<码>
    sent: NotRequired[bool]


# ---- 节点：纯「读状态 → 返回更新」的函数 ----


async def intake(state: ExpenseState) -> dict:
    """载单：读 mock 表组装单据摘要，planner 的岗位书（system）与事实来源（user）进场。"""
    view = mock_tools.claim_view(state["claim_id"])
    return {
        "messages": [
            {"role": "system", "content": prompts.PLANNER_SYSTEM},
            {"role": "user", "content": prompts.planner_brief(view)},
        ],
        "events": ["intake"],
    }


def make_planner(model: Runnable):
    """planner 节点工厂：产计划 JSON（LLM 合法位置①）。

    重规划轮：把最新拒绝原因与上一版计划作为 user 消息回喂（A29）——
    planner 不 bind_tools，工具选择在计划数据里，不在 function calling 协议里。
    """

    async def planner(state: ExpenseState) -> dict:
        rejections = state.get("plan_rejections") or []
        extra: list[dict] = []
        if rejections:
            previous_plan = state["messages"][-1].content  # 最新一条 AI 消息 = 上一版计划原文
            extra.append({"role": "user", "content": prompts.replan_instruction(previous_plan, rejections[-1])})
        response = await model.ainvoke(state["messages"] + extra)
        return {"messages": extra + [response], "events": ["planner"]}

    return planner


async def plan_gate(state: ExpenseState) -> dict:
    """校验门（纯代码，非 LLM）：判别联合分派 + 白名单 + 必填/金额校验。

    拒绝原因入 state（plan_rejections）而不是抛异常——它是回喂 planner 的任务数据；
    events 落 plan.rejected:<码>，审计流水与状态键同一口径。
    """
    outcome = validate_plan(state["messages"][-1].content)
    if isinstance(outcome, PlanRejection):
        return {"plan_rejections": [outcome], "events": [f"plan.rejected:{outcome.reason_code}"]}
    return {"plan": outcome, "events": ["plan.approved"]}


def route_after_gate(state: ExpenseState) -> Literal["executor", "planner", "escalate"]:
    """条件边三分支：路由决策是确定性代码（LLM 在这里零发言权）。

    valid → executor；invalid 且拒绝次数未超 MAX_REPLANS → 回 planner（原因已入 state）；
    超限 → escalate 收尾哨兵。拒绝次数含当前这次：第 1/2 次拒绝回去重规划，
    第 3 次拒绝时已用满 2 次重规划（replans = 拒绝次数 - 1 == MAX_REPLANS）→ 超限。
    """
    if state.get("plan") is not None:
        return "executor"
    if len(state.get("plan_rejections") or []) <= MAX_REPLANS:
        return "planner"
    return "escalate"


async def executor_node(state: ExpenseState) -> dict:
    """执行器节点：确定性步进的薄包装——本体在 executor.execute_plan（纯函数）。"""
    candidate = state.get("plan")
    assert candidate is not None  # 路由保证：只有过门的合法计划才会走到本节点（NotRequired 键的守门读法）
    return {"results": execute_plan(candidate), "events": ["executor"]}


def make_drafter(model: Runnable):
    """drafter 节点工厂：依取数结果产建议单（LLM 合法位置②）。

    出口纪律（L2.4/L3.2 延续）：LLM 只产 JSON 文本，Advice 的 schema 把守在边界上。
    """

    async def drafter(state: ExpenseState) -> dict:
        user = {"role": "user", "content": prompts.drafter_instruction(state["results"])}
        response = await model.ainvoke(state["messages"] + [user])
        advice = Advice.model_validate_json(response.content.strip())
        return {"messages": [user, response], "advice": advice, "events": ["drafter"]}

    return drafter


async def submit(state: ExpenseState) -> dict:
    """送审桩（stub）：本课只落「已送审」事件并置 sent=True。

    L5.2 把这里换成 interrupt()（L3.3 的抛-捕-落盘）+ 审批 API（REST 建单 + SSE 推送）——
    图形状不变、换芯不换壳，这就是静态拓扑给后续课留的稳定接口。
    """
    return {"sent": True, "events": ["submit"]}


async def escalate(state: ExpenseState) -> dict:
    """超限收尾哨兵：重规划烧完仍非法——不送审、转人工（拒绝静默降级，A16）。

    remaining_cents=0 表示「未取到」（取数从未发生），哨兵建议单与正常建议单同型
    （Advice），下游审批 API 只有一个出口类型。
    """
    advice = Advice(
        claim_id=state["claim_id"],
        decision="ESCALATE",
        reason=ESCALATE_REASON,
        remaining_cents=0,
    )
    return {"advice": advice, "sent": False, "events": ["escalate"]}


def build_graph(model: Runnable) -> CompiledStateGraph:
    """装配固定拓扑：六节点 + 条件边三分支 + escalate 终态（装配即部署，对照 L3.2）。"""
    builder = StateGraph(ExpenseState)
    builder.add_node("intake", intake)
    builder.add_node("planner", make_planner(model))
    builder.add_node("plan_gate", plan_gate)
    builder.add_node("executor", executor_node)
    builder.add_node("drafter", make_drafter(model))
    builder.add_node("submit", submit)
    builder.add_node("escalate", escalate)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", "planner")
    builder.add_edge("planner", "plan_gate")
    builder.add_conditional_edges("plan_gate", route_after_gate)  # 三分支：executor | planner | escalate
    builder.add_edge("executor", "drafter")
    builder.add_edge("drafter", "submit")
    builder.add_edge("submit", END)
    builder.add_edge("escalate", END)
    return builder.compile()


def initial_state(claim_id: str) -> dict:
    """入口状态：claim_id 进场，消息史从空开始（intake 写头两条）。

    合并语义的键显式给空初值（reducer 从空累积），覆盖语义的键（plan/advice/sent）
    是 NotRequired——第一个写它们的节点才让它们出现。
    """
    return {"claim_id": claim_id, "messages": [], "plan_rejections": [], "results": {}, "events": []}
