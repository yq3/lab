"""讲义区验收 4/4：整图离线契约——请求次数精确断言、轮次参数化两态、MsgClear 效果、预算封顶。

「可预算」的机器证明全在这份文件里：默认配置恰好 quick 7 + deep 2 = 9 次（辩论段 2、
风险段 3）；rounds=2 时辩论段翻倍到 4。每条断言都是 ep.requests 的实测取证。
"""

from __future__ import annotations

import asyncio

import pytest

import demo
import policy_tools
from budget import BudgetExceeded
from config import AppealConfig
from schemas import AppealRuling, FinalDecision


def test_full_graph_offline_contract_default_config() -> None:
    """端到端：9 次调用（quick 7 + deep 2）、辩论 2 轮、风险 3 方、终审与裁决一致、工具真实执行。"""
    outcome = asyncio.run(demo.run_appeal())
    assert (outcome.quick_calls, outcome.deep_calls, outcome.llm_calls) == (7, 2, 9)
    assert outcome.state["debate"]["count"] == 2  # 恰好 2 * max_debate_rounds
    assert outcome.state["risk"]["count"] == 3  # 恰好 3 * max_risk_rounds
    ruling: AppealRuling = outcome.state["ruling"]
    final: FinalDecision = outcome.state["final"]
    assert ruling.verdict == demo.EXPECTED_VERDICT == "APPROVE_WITH_CAP"
    assert ruling.capped_amount_cents == demo.EXPECTED_CAP_CENTS == 4000
    assert (final.verdict, final.capped_amount_cents) == ("APPROVE_WITH_CAP", 4000)
    assert {"POL-7.2", "POL-9.1"} <= set(policy_tools.CALL_LOG)  # 政策工具被图真实执行


def test_request_forensics_tools_only_in_analyst_segment() -> None:
    """取证：工具白名单只在分析师段——首请求绑定 lookup_policy，辩论段请求不带 tools 字段。"""
    outcome = asyncio.run(demo.run_appeal())
    first = outcome.quick_requests[0]
    assert [t["function"]["name"] for t in first["tools"]] == ["lookup_policy"]
    debate_requests = outcome.quick_requests[2:4]  # 第 3、4 次 quick 调用 = 申辩人/合规官
    assert all("tools" not in request for request in debate_requests)


def test_msg_clear_leaves_single_anchored_placeholder() -> None:
    """MsgClear 效果：分析师段 6 条消息被清空，只剩 1 条锚定占位（对版 #888：不是裸 Continue）。"""
    outcome = asyncio.run(demo.run_appeal())
    messages = outcome.state["messages"]
    assert len(messages) == 1
    placeholder = str(messages[0].content)
    assert demo.CLAIM_ID in placeholder  # 锚定到争议单号
    assert "policy_report" in placeholder  # 锚定到已归档结论
    assert "POL-9.1" in placeholder  # 锚定到任务本身
    assert outcome.state["policy_report"]  # 报告以独立字段传下游，不靠消息史


def test_rounds_two_doubles_debate_segment_exactly() -> None:
    """改造一（轮次参数化）：rounds=2 → 辩论段恰好 4 次调用、count=4，其余段落不变。"""
    outcome = asyncio.run(demo.run_appeal(AppealConfig(max_debate_rounds=2)))
    assert (outcome.quick_calls, outcome.deep_calls, outcome.llm_calls) == (9, 2, 11)
    assert outcome.state["debate"]["count"] == 4
    assert outcome.state["risk"]["count"] == 3
    assert outcome.state["final"].verdict == "APPROVE_WITH_CAP"  # 裁决链路不受轮次影响


def test_budget_cap_burns_midrun_with_exact_used() -> None:
    """改造二（预算封顶）：cap=5 烧穿在风险段，异常抛出且已调用次数恰好 = cap。"""
    with pytest.raises(BudgetExceeded) as excinfo:
        asyncio.run(demo.run_appeal(AppealConfig(max_llm_calls=5)))
    assert excinfo.value.limit == 5
    assert excinfo.value.used == 5
