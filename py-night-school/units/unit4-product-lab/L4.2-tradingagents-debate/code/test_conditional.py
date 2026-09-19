"""讲义区验收 1/4：路由器直测——对版 TradingAgents 的 tests/test_risk_router_path_map.py。

两个对版先例逐条落地：
① #1088 漂移防御——路由器对**任何** speaker 标签（空串/改名/i18n 漂移）的返回值都必须
   落在对应 path_map 内（全量映射才能保证这一点）；
② 计数终止边界——count 恰好到 2*rounds / 3*rounds 时切换到裁决节点，差一步都不切。
"""

from __future__ import annotations

import pytest

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
from states import AppealState


def _debate(count: int, speaker: str) -> AppealState:
    """只有 debate 有值的完整状态（路由器只读这一个键——窄接口）。"""
    return {
        "messages": [],
        "claim_id": "CLM-2026-0004",
        "policy_report": "",
        "debate": {
            "applicant_history": "",
            "office_history": "",
            "history": "",
            "current_speaker": speaker,
            "count": count,
        },
        "risk": {"history": "", "latest_speaker": "", "count": 0},
    }


def _risk(count: int, speaker: str) -> AppealState:
    """只有 risk 有值的完整状态。"""
    return {
        "messages": [],
        "claim_id": "CLM-2026-0004",
        "policy_report": "",
        "debate": {"applicant_history": "", "office_history": "", "history": "", "current_speaker": "", "count": 0},
        "risk": {"history": "", "latest_speaker": speaker, "count": count},
    }


@pytest.mark.parametrize(
    "speaker",
    [
        "申辩人（钱工代理）：…",  # 正常前缀
        "合规官：…",  # 对手前缀
        "合规官（新标签）：…",  # 漂移：节点改名
        "",  # 漂移：空标签（先手）
        "申辩人（Agresivo 漂移）：…",  # 漂移：i18n
    ],
)
def test_debate_router_return_always_routable(speaker: str) -> None:
    """① 辩论路由：任何标签的返回值都必落 DEBATE_PATH_MAP（#1088）。"""
    router = AppealConditionalLogic(AppealConfig(max_debate_rounds=1))
    assert router.should_continue_debate(_debate(1, speaker)) in DEBATE_PATH_MAP


@pytest.mark.parametrize(
    "speaker",
    [
        "宽松解释：…",
        "严格合规：…",
        "例外处理：…",
        "例外处理（新标签）：…",
        "",
        "宽松（i18n 漂移）：…",
    ],
)
def test_risk_router_return_always_routable(speaker: str) -> None:
    """① 风险路由：同款漂移防御，返回值必落 RISK_PATH_MAP。"""
    router = AppealConditionalLogic(AppealConfig(max_risk_rounds=1))
    assert router.should_continue_risk(_risk(1, speaker)) in RISK_PATH_MAP


def test_debate_counter_terminates_at_exact_boundary() -> None:
    """② 计数终止：count 达 2*rounds 切裁决官，差一步继续轮转（rounds=2 边界）。"""
    router = AppealConditionalLogic(AppealConfig(max_debate_rounds=2))
    assert router.should_continue_debate(_debate(3, "合规官：…")) == APPLICANT_ADVOCATE  # 3 < 4：继续
    assert router.should_continue_debate(_debate(4, "申辩人：…")) == RULING_OFFICIAL  # 4 >= 4：终止
    assert router.should_continue_debate(_debate(1, "申辩人：…")) == COMPLIANCE_OFFICER  # 前缀轮转


def test_risk_rotation_order_and_termination() -> None:
    """② 风险轮转：宽松→严格→例外→宽松……到 3*rounds 切终审官。"""
    router = AppealConditionalLogic(AppealConfig(max_risk_rounds=1))
    assert router.should_continue_risk(_risk(0, "")) == LENIENT_INTERPRETER  # 先手固定宽松
    assert router.should_continue_risk(_risk(1, "宽松解释：…")) == STRICT_COMPLIANCE
    assert router.should_continue_risk(_risk(2, "严格合规：…")) == EXCEPTION_HANDLER
    assert router.should_continue_risk(_risk(3, "例外处理：…")) == FINAL_JUDGE  # 3 >= 3*1：终止


def test_path_maps_are_total_over_router_targets() -> None:
    """path_map 全量性 meta：两台的返回集恰好铺满各自 path_map 的键（无死条目、无落空）。"""
    router = AppealConditionalLogic(AppealConfig(max_debate_rounds=1, max_risk_rounds=1))
    debate_targets = {
        router.should_continue_debate(_debate(0, "")),
        router.should_continue_debate(_debate(1, "申辩人：…")),
        router.should_continue_debate(_debate(1, "合规官：…")),
        router.should_continue_debate(_debate(2, "合规官：…")),
    }
    risk_targets = {
        router.should_continue_risk(_risk(0, "")),
        router.should_continue_risk(_risk(1, "宽松解释：…")),
        router.should_continue_risk(_risk(1, "严格合规：…")),
        router.should_continue_risk(_risk(1, "例外处理：…")),
        router.should_continue_risk(_risk(3, "例外处理：…")),
    }
    assert debate_targets == set(DEBATE_PATH_MAP)
    assert risk_targets == set(RISK_PATH_MAP)
