"""run_intake——报销初审的一趟管线（对版 hedge_fund/pipeline/run_cycle.py#run_cycle）。

    快照 -> 检查员逐个投票 -> blend 加权合成 -> limits 硬 clamp -> 回执

对版三条设计纪律：
- run_cycle 是管线里唯一不纯的一块（它说话的对象是端点与缓存）；它委托的
  weighted_vote / apply_limits / _decide 全是纯函数——数字全部代码算；
- 检查员之间零通信：每个检查员独立对同一快照投票，互相看不见
  （产品用顺序 for 循环跑「并行独立」的语义——互不依赖，所以可并行；有没有并发都不改变结果）；
- 确定性：同样的单据 + 同样的（缓存的）模型响应，回执逐字段一致——
  冷缓存的第一趟是唯一的不确定源，缓存让重放精确（对版 run_cycle 的 determinism 主张）。

「LLM 影响力终止于 Signal」在本课 = 「LLM 影响力终止于 Vote」：
检查员的票只进合成算术；金额处置（limits）与最终建议（_decide）是纯代码。
"""

from __future__ import annotations

from blend import weighted_vote
from cache import DecisionCache
from limits import apply_limits
from review import Advice, Decision, ReviewRecord, Vote
from reviewers import (
    BudgetReviewer,
    ComplianceReviewer,
    HttpClient,
    InvoiceReviewer,
    LLMCheckerBase,
    Reviewer,
    RuleChecker,
)
from snapshot import ITEM_LIMIT_CENTS, build_snapshot

# 合成权重表（对版 StrategySpec.model_weights：mandate 的一级字段，改权重不动代码）
CHECKER_WEIGHTS: dict[str, float] = {
    "compliance": 1.0,
    "budget": 1.0,
    "invoice": 1.0,
    "rules": 1.5,  # 规则表证据硬，话语权略高——纯教学取值
}

# LLM 检查员的调用顺序（入队剧本与断言请求数都按这个顺序）
LLM_CHECKER_ORDER = ("compliance", "budget", "invoice")

# 离线剧本表：claim_id -> checker_name -> 模型台词（JSON 或任何会解析失败的文本）。
# 与 MockLLMEndpoint 一样，这是「协议级测试替身」的剧本——离线验收测的是机制
# （缓存/解析/合成/clamp），不是模型质量；真实端点下这些台词由模型自己产出。
SCRIPTS: dict[str, dict[str, str]] = {
    "CLM-2026-0001": {
        "compliance": '{"stance": "support", "confidence": 80, "reasoning": "交通与工作餐属合理开支"}',
        "budget": '{"stance": "support", "confidence": 75, "reasoning": "总额远低于剩余预算"}',
        "invoice": '{"stance": "support", "confidence": 90, "reasoning": "发票校验通过"}',
    },
    "CLM-2026-0002": {
        "compliance": '{"stance": "oppose", "confidence": 85, "reasoning": "单餐超单笔上限"}',
        "budget": "这单预算没问题，我同意。",  # 无 JSON：parse_error 留盘的教学场景
        "invoice": '{"stance": "support", "confidence": 90, "reasoning": "发票有效，问题不在发票"}',
    },
    "CLM-2026-0003": {
        "compliance": '{"stance": "oppose", "confidence": 60, "reasoning": "负数金额疑似录入错误"}',
        "budget": '{"stance": "support", "confidence": 55, "reasoning": "总额为负不占预算"}',
        "invoice": '{"stance": "support", "confidence": 70, "reasoning": "发票本身有效"}',
    },
    "CLM-2026-0004": {
        "compliance": '{"stance": "support", "confidence": 65, "reasoning": "展会物料采购属正常开支"}',
        "budget": '{"stance": "support", "confidence": 70, "reasoning": "总额在剩余预算内"}',
        "invoice": '{"stance": "oppose", "confidence": 95, "reasoning": "发票已作废不能报销"}',
    },
}


def make_checkers(client: HttpClient, cache: DecisionCache) -> list[Reviewer]:
    """组建检查员队伍：三个 LLM 人格 + 一个量化规则表（对版 strategy 的 staff）。"""
    return [
        ComplianceReviewer(client, cache),
        BudgetReviewer(client, cache),
        InvoiceReviewer(client, cache),
        RuleChecker(),
    ]


def script_endpoint(claim_id: str, ep) -> None:  # noqa: ANN001 -- MockLLMEndpoint 在讲义脚本里具名
    """按调用顺序给 mock 端点入队某单的三个 LLM 台词（离线剧本的装填口）。"""
    for checker in LLM_CHECKER_ORDER:
        ep.script_text(SCRIPTS[claim_id][checker])


def run_intake(claim_id: str, client: HttpClient, cache: DecisionCache) -> ReviewRecord:
    """跑一趟报销初审（对版 run_cycle）：快照 -> 投票 -> 合成 -> clamp -> 回执。"""
    snapshot = build_snapshot(claim_id)
    checkers = make_checkers(client, cache)
    votes: list[Vote] = [checker.review(snapshot) for checker in checkers]  # 零通信，逐个独立投

    blend = weighted_vote(votes, CHECKER_WEIGHTS)

    risk = apply_limits(dict(snapshot.items), ITEM_LIMIT_CENTS, snapshot.remaining_cents)

    rule_code = next(vote.metadata["rule_code"] for vote in votes if vote.checker == "rules")
    advice = _decide(claim_id, rule_code, blend.conviction, snapshot.remaining_cents)

    return ReviewRecord(
        claim_id=claim_id,
        claim_hash=snapshot.content_hash,
        votes=votes,
        conviction=blend.conviction,
        amount_before_cents=snapshot.total_cents,
        amount_after_cents=sum(risk.amounts.values()),
        clamps=risk.clamps,
        advice=advice,
    )


def _decide(claim_id: str, rule_code: str, conviction: float | None, remaining_cents: int) -> Advice:
    """决策门——纯函数，按序短路（本课对「风控光谱③处置层」的映射选择）。

    1) 脏数据（INVALID_AMOUNT）转人审：数据错了先修数据，投票无意义；
    2) 硬规则命中即拒：fail-closed——检查员的票救不回硬规则（clamp 不可协商的决策层投影）；
    3) 全弃权（conviction is None）转人审：显式边界，不捏造中性；
    4) 反对占优（conviction < 0）拒：软证据由合成算术裁决；
    5) 其余通过。
    """

    def _advice(decision: Decision, reason: str) -> Advice:
        return Advice(claim_id=claim_id, decision=decision, reason=reason, remaining_cents=remaining_cents)

    if rule_code == "INVALID_AMOUNT":
        return _advice("ESCALATE", "REJECT:INVALID_AMOUNT")
    if rule_code != "PASS":
        return _advice("REJECT", f"REJECT:{rule_code}")
    if conviction is None:
        return _advice("ESCALATE", "REJECT:ALL_ABSTAINED")
    if conviction < 0:
        return _advice("REJECT", "REJECT:CHECKER_VOTE")
    return _advice("APPROVE", "PASS")


# LLMCheckerBase 在本模块被 re-export 供讲义与测试引用（对版 hedge_fund.llm 的 __all__ 角色）
__all__ = [
    "CHECKER_WEIGHTS",
    "LLMCheckerBase",
    "LLM_CHECKER_ORDER",
    "SCRIPTS",
    "make_checkers",
    "run_intake",
    "script_endpoint",
]
