"""L4.2 图状态：扁平字段 + 两个嵌套辩论 dict（对版 agent_states.py 的 AgentState）。

对版 TauricResearch/TradingAgents@be952b8#tradingagents/agents/utils/agent_states.py：
- 产品 AgentState = MessagesState + 8 个业务字段 + 两个嵌套辩论 state（InvestDebateState /
  RiskDebateState）。嵌套 dict **没有 reducer**——LastValue 通道整体替换，节点必须手工
  回填全部键（漏键即坑，§5 主角）。本课原样保留该纪律：DebateState 5 键、RiskDebateState 3 键。
- current_speaker / latest_speaker 一字段两用（对版产品的 current_response / latest_speaker）：
  值是「发言人前缀 + 论点全文」——路由器按前缀轮转对手，辩手按全文取对方最新论点。
  前缀匹配用 startswith（容忍「申辩人（钱工）：」这类带标签漂移，对版 startswith("Bull")）。
- messages 只服务政策分析师的 ReAct 段：MsgClear（msg_clear.py）在阶段结束清空全部消息、
  换一条锚定占位——辩论/裁决阶段不再读 messages，跨阶段传递靠 policy_report 等独立字段
  （产品同款：报告以 str 字段传下游，不靠消息史）。

Java 对照：嵌套 TypedDict ≈ 内部静态类，但语义是**整体替换**不是引用共享——
Java 人「取出嵌套对象、改一个字段、set 回去」在这里等效于「丢掉其余全部字段」。
"""

from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from langgraph.graph.message import add_messages

from schemas import AppealRuling, FinalDecision


class DebateState(TypedDict):
    """申辩人⇄合规官辩论的嵌套状态（对版 InvestDebateState：无 reducer、节点手工回填全部键）。"""

    applicant_history: str  # 申辩人专属发言史
    office_history: str  # 合规官专属发言史
    history: str  # 双方合并发言史（裁决官读这份）
    current_speaker: str  # 「申辩人（钱工）：…」/「合规官：…」——路由前缀 + 论点全文同体
    count: int  # 已发言次数；终止条件 count >= 2 * max_debate_rounds


class RiskDebateState(TypedDict):
    """三方风险辩论的嵌套状态（对版 RiskDebateState 的精简版：同样无 reducer 手工回填）。"""

    history: str  # 三方合并发言史（终审官读这份）
    latest_speaker: str  # 「宽松解释：…」/「严格合规：…」/「例外处理：…」——前缀轮转依据
    count: int  # 已发言次数；终止条件 count >= 3 * max_risk_rounds


class AppealState(TypedDict):
    """报销争议上诉图状态：节点间唯一的通信媒介（L3.2 §2.1 的纪律原样成立）。"""

    messages: Annotated[list, add_messages]  # 分析师 ReAct 段专用；MsgClear 后只剩 1 条锚定占位
    claim_id: str  # 争议单号（锚定占位与提示词用，明线：CLM-2026-0004）
    policy_report: str  # 政策分析师结论——跨阶段传递的独立字段（不靠消息史）
    debate: DebateState  # 嵌套 dict 无 reducer：整体替换，辩手节点必须回填全部键
    risk: RiskDebateState  # 同上
    ruling: NotRequired[AppealRuling]  # 裁决官产出（deep 模型 + Pydantic 出口）
    final: NotRequired[FinalDecision]  # 终审官产出（deep 模型 + Pydantic 出口）
