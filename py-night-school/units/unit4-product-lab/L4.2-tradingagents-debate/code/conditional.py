"""L4.2 路由器：条件边循环的「纯计数器终止 + 前缀轮转」（本课教学主轴）。

对版 TauricResearch/TradingAgents@be952b8#tradingagents/graph/conditional_logic.py：
- should_continue_debate：`count >= 2 * max_debate_rounds → 裁决官`，否则按 current_response
  前缀（"Bull"/"Bear"）轮转对手——纯计数器，**没有任何收敛判断**（不问「辩出结果了吗」）；
- should_continue_risk_analysis：`count >= 3 * max_risk_discuss_rounds → Portfolio Manager`，
  Aggressive→Conservative→Neutral 前缀轮转。
轮次写死 vs 配置驱动是本课第一个改造点（ex1）：产品的轮次从 default_config 流进
ConditionalLogic 构造器——本课 AppealConditionalLogic(config) 同构。

DEBATE_PATH_MAP / RISK_PATH_MAP：全量映射防 fall-through（对版 setup.py，issue #1088）——
同一路由器的返回集大于任何单条边「自然」的去向集合，每条条件边都映射**全部**可能返回值，
提示词/国际化/重构漂移出意外返回值时也绝不在图中途崩掉。讲义区 test_conditional.py
直测「路由返回值必落 path_map 内」（对版 tests/test_risk_router_path_map.py）。
"""

from __future__ import annotations

from collections.abc import Hashable

from config import AppealConfig
from states import AppealState

# ---- 节点名常量（路由器、装配、测试三方共用一套名字） ----
APPLICANT_ADVOCATE = "申辩人"
COMPLIANCE_OFFICER = "合规官"
RULING_OFFICIAL = "裁决官"
LENIENT_INTERPRETER = "宽松解释"
STRICT_COMPLIANCE = "严格合规"
EXCEPTION_HANDLER = "例外处理"
FINAL_JUDGE = "终审官"

# 每条辩论条件边都映射路由器的**全部**可能返回值（对版 setup.py#DEBATE_PATH_MAP，#1088）
# 注解 dict[Hashable, str]：langgraph 的 path_map 形参是不变型的 dict[Hashable, str]
DEBATE_PATH_MAP: dict[Hashable, str] = {
    APPLICANT_ADVOCATE: APPLICANT_ADVOCATE,
    COMPLIANCE_OFFICER: COMPLIANCE_OFFICER,
    RULING_OFFICIAL: RULING_OFFICIAL,
}
RISK_PATH_MAP: dict[Hashable, str] = {
    LENIENT_INTERPRETER: LENIENT_INTERPRETER,
    STRICT_COMPLIANCE: STRICT_COMPLIANCE,
    EXCEPTION_HANDLER: EXCEPTION_HANDLER,
    FINAL_JUDGE: FINAL_JUDGE,
}


class AppealConditionalLogic:
    """辩论/风险两台路由器（对版 conditional_logic.py#ConditionalLogic）。"""

    def __init__(self, config: AppealConfig):
        self.max_debate_rounds = config.max_debate_rounds
        self.max_risk_rounds = config.max_risk_rounds

    def should_continue_debate(self, state: AppealState) -> str:
        """辩论终止 = 纯计数器：count >= 2 * 轮次 → 裁决官；否则按前缀轮转对手。"""
        if state["debate"]["count"] >= 2 * self.max_debate_rounds:
            return RULING_OFFICIAL
        if state["debate"]["current_speaker"].startswith(APPLICANT_ADVOCATE):
            return COMPLIANCE_OFFICER
        return APPLICANT_ADVOCATE

    def should_continue_risk(self, state: AppealState) -> str:
        """风险辩论同构：count >= 3 * 轮次 → 终审官；宽松→严格→例外 固定顺序轮转。"""
        if state["risk"]["count"] >= 3 * self.max_risk_rounds:
            return FINAL_JUDGE
        if state["risk"]["latest_speaker"].startswith(LENIENT_INTERPRETER):
            return STRICT_COMPLIANCE
        if state["risk"]["latest_speaker"].startswith(STRICT_COMPLIANCE):
            return EXCEPTION_HANDLER
        return LENIENT_INTERPRETER
