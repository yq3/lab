"""L4.2 图装配：辩论-裁决上诉图（对版 graph/setup.py#GraphSetup.setup_graph）。

对版拓扑（TauricResearch/TradingAgents@be952b8，产品 9 agent → 本课 10 节点）：

    START → 政策分析师 ─条件边(有 tool_calls?)→ 政策工具 → 政策分析师（回边成环）
                     └─(无 tool_calls)→ 清理上下文 → 申辩人
    申辩人 ─┐
    合规官 ─┴─条件边 should_continue_debate（DEBATE_PATH_MAP）→ 对手 / 裁决官
    裁决官 → 宽松解释 ─┐
    严格合规 ─┬────────┤条件边 should_continue_risk（RISK_PATH_MAP）→ 下一方 / 终审官
    例外处理 ─┘
    终审官 → END

对版要点：
- 两条辩论回边的条件边**共享同一个 path_map 全量映射**（对版 setup.py 对 Bull/Bear 两条边
  共用 DEBATE_PATH_MAP，#1088）——路由器返回集大于单条边的自然去向，不全量映射就会
  在标签漂移时图中途崩掉；
- 分析师条件边走简写 [工具节点, 清理节点] 列表（对版 [current_tools, current_clear]），
  路由器返回的就是节点名本身；
- 轮次从 AppealConfig 流进路由器（对版 ConditionalLogic(max_debate_rounds=...)——
  ex1 练的就是这条路）；产品 Trader 环节在本课无对应物，教学版裁掉（README §2 映射表）。
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

import policy_tools
from conditional import (
    APPLICANT_ADVOCATE,
    COMPLIANCE_OFFICER,
    DEBATE_PATH_MAP,
    EXCEPTION_HANDLER,
    FINAL_JUDGE,
    LENIENT_INTERPRETER,
    RISK_PATH_MAP,
    RULING_OFFICIAL,
    STRICT_COMPLIANCE,
    AppealConditionalLogic,
)
from config import AppealConfig
from debaters import (
    create_applicant_advocate,
    create_compliance_officer,
    create_final_judge,
    create_policy_analyst,
    create_risk_debater,
    create_ruling_official,
)
from msg_clear import create_msg_delete
from states import AppealState

POLICY_ANALYST = "政策分析师"
POLICY_TOOLS = "政策工具"
MSG_CLEAR = "清理上下文"

RECURSION_LIMIT = 100  # superstep 预算（对版 default_config.py#max_recur_limit——另一条预算轴）

# 节点执行顺序（demo_trace 的段落切分依据；11 个 superstep = 默认配置的图形状）
NODE_ORDER = [
    POLICY_ANALYST,
    POLICY_TOOLS,
    MSG_CLEAR,
    APPLICANT_ADVOCATE,
    COMPLIANCE_OFFICER,
    RULING_OFFICIAL,
    LENIENT_INTERPRETER,
    STRICT_COMPLIANCE,
    EXCEPTION_HANDLER,
    FINAL_JUDGE,
]


async def policy_tool_dispatch(state: AppealState) -> dict:
    """政策工具节点：把最后一条消息的 tool_calls 分发到 mock 工具并回喂（L3.2 同款）。"""
    calls = state["messages"][-1].tool_calls
    return {"messages": policy_tools.policy_tools_node(calls)}


def route_after_analyst(state: AppealState) -> Literal["政策工具", "清理上下文"]:
    """分析师条件边：还有 tool_calls 继续行动，没有就清场进辩论（对版 should_continue_market）。"""
    return "政策工具" if state["messages"][-1].tool_calls else "清理上下文"


def build_appeal_graph(
    config: AppealConfig, analyst_model: Any, quick_model: Any, deep_model: Any
) -> CompiledStateGraph:
    """装配整张上诉图：分析师模型过 bind_tools，quick 给辩手/风险三方，deep 只给两裁决官。

    三个模型参数对应产品「工具按角色静态划分」的取向（每个分析师一个专属 ToolNode，
    辩手拿裸 llm）——辩论段的请求体里**没有** tools 字段，取证时看得见这条白名单边界。
    """
    builder = StateGraph(AppealState)
    builder.add_node(POLICY_ANALYST, create_policy_analyst(analyst_model))
    builder.add_node(POLICY_TOOLS, policy_tool_dispatch)
    builder.add_node(MSG_CLEAR, create_msg_delete())
    builder.add_node(APPLICANT_ADVOCATE, create_applicant_advocate(quick_model))
    builder.add_node(COMPLIANCE_OFFICER, create_compliance_officer(quick_model))
    builder.add_node(RULING_OFFICIAL, create_ruling_official(deep_model))
    builder.add_node(LENIENT_INTERPRETER, create_risk_debater(quick_model, LENIENT_INTERPRETER))
    builder.add_node(STRICT_COMPLIANCE, create_risk_debater(quick_model, STRICT_COMPLIANCE))
    builder.add_node(EXCEPTION_HANDLER, create_risk_debater(quick_model, EXCEPTION_HANDLER))
    builder.add_node(FINAL_JUDGE, create_final_judge(deep_model))

    builder.add_edge(START, POLICY_ANALYST)
    builder.add_conditional_edges(POLICY_ANALYST, route_after_analyst, [POLICY_TOOLS, MSG_CLEAR])
    builder.add_edge(POLICY_TOOLS, POLICY_ANALYST)  # 回边成环：分析师的 ReAct 循环

    router = AppealConditionalLogic(config)  # 轮次从配置流进路由器（ex1 的改造主线）
    builder.add_edge(MSG_CLEAR, APPLICANT_ADVOCATE)  # 清场后固定进申辩人（对版进 Bull Researcher）
    for debate_node in (APPLICANT_ADVOCATE, COMPLIANCE_OFFICER):  # 两条辩论边共享全量 path_map（#1088）
        builder.add_conditional_edges(debate_node, router.should_continue_debate, DEBATE_PATH_MAP)
    builder.add_edge(RULING_OFFICIAL, LENIENT_INTERPRETER)
    for risk_node in (LENIENT_INTERPRETER, STRICT_COMPLIANCE, EXCEPTION_HANDLER):
        builder.add_conditional_edges(risk_node, router.should_continue_risk, RISK_PATH_MAP)
    builder.add_edge(FINAL_JUDGE, END)
    return builder.compile()


def initial_state(claim_id: str, brief: str) -> AppealState:
    """入口状态：分析师消息 + 两个辩论嵌套 dict 的零值（对版 trading_graph 初始 state）。"""
    return {
        "messages": [
            {"role": "system", "content": "你是报销政策分析师。请先用工具查相关政策条目，再归纳政策结论。"},
            {"role": "user", "content": brief},
        ],
        "claim_id": claim_id,
        "policy_report": "",
        "debate": {
            "applicant_history": "",
            "office_history": "",
            "history": "",
            "current_speaker": "",
            "count": 0,
        },
        "risk": {"history": "", "latest_speaker": "", "count": 0},
    }
