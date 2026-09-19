"""讲义区验收（四）：图的端到端——四单 clean 全对、重规划环回喂、超限 escalate 哨兵。

（契约的图内视角版：expect_* 判分字段来自 review_mock.json，与 L3.2 test_contract 同思想；
本课没有五课对版的 contract 约束——毕业设计的图是单份本体，验收住在本文件。）"""

from __future__ import annotations

import asyncio
import operator
from typing import get_type_hints

import demo
import graph
import mock_tools
from plan import PlanRejection


def test_state_declares_reducers() -> None:
    """meta：合并语义的键必须带 Annotated reducer——plan_rejections/events 用 operator.add，
    results 用自定义 merge_results（dict 版）；漏了注解，流水/拒绝轨迹/取数产物会被覆盖语义吞掉。"""
    hints = get_type_hints(graph.ExpenseState, include_extras=True)
    assert hints["plan_rejections"].__metadata__ == (operator.add,)
    assert hints["events"].__metadata__ == (operator.add,)
    assert hints["results"].__metadata__ == (graph.merge_results,)
    assert graph.merge_results({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}  # 合并而非覆盖


def test_route_after_gate_three_branches() -> None:
    """条件边三分支（路由决策零 LLM）：valid→executor；1/2 次拒绝→planner；3 次→escalate。"""
    valid_plan = graph.Plan.model_construct(steps=[], claim_total_cents=0)
    valid_state: graph.ExpenseState = {
        "claim_id": "CLM-2026-0001",
        "messages": [],
        "plan_rejections": [],
        "results": {},
        "events": [],
        "plan": valid_plan,
    }
    assert graph.route_after_gate(valid_state) == "executor"

    rejection = PlanRejection(reason_code="unknown_tool", detail="x")

    def gate_state(rejections: list[PlanRejection]) -> graph.ExpenseState:
        state: graph.ExpenseState = {
            "claim_id": "CLM-2026-0001",
            "messages": [],
            "plan_rejections": rejections,
            "results": {},
            "events": [],
        }
        return state

    assert graph.route_after_gate(gate_state([rejection])) == "planner"
    assert graph.route_after_gate(gate_state([rejection, rejection])) == "planner"
    assert graph.route_after_gate(gate_state([rejection] * 3)) == "escalate"
    assert graph.MAX_REPLANS == 2  # 边界钉死：第 3 次拒绝时 replans=2 已用满


def test_four_claims_clean_mode_match_expectations() -> None:
    """图端到端（clean 剧本）：四单 advice 与 review_mock 的 expect_* 逐字段全等，
    全部正常送审，工具真实执行（CALL_LOG 取证）。"""
    for claim in mock_tools.claims_table():
        mock_tools.CALL_LOG.clear()
        final = asyncio.run(demo.run_pipeline(claim["id"]))
        advice = final["advice"]
        assert advice.claim_id == claim["id"]
        assert advice.decision == claim["expect_decision"], (claim["id"], advice.decision)
        assert advice.reason == claim["expect_reason"], (claim["id"], advice.reason)
        assert advice.remaining_cents == claim["expect_remaining_cents"], claim["id"]
        assert final["sent"] is True
        assert "plan.approved" in final["events"] and final["events"][-1] == "submit"
        assert {"check_budget", "verify_invoice"} <= set(mock_tools.CALL_LOG), claim["id"]
        assert final["results"]["budget"]["remaining_cents"] == claim["expect_remaining_cents"]


def test_dirty_once_replans_with_reason_fed_back() -> None:
    """重规划环：脏计划（未知工具）被拒→原因+上一版回喂→第 2 轮通过→正常收尾。"""
    final = asyncio.run(demo.run_pipeline("CLM-2026-0002", mode="dirty_once"))
    rejections = final["plan_rejections"]
    assert [r.reason_code for r in rejections] == ["unknown_tool"]  # 恰好一次拒绝
    assert "query_erp_balance" in rejections[0].detail  # 拒绝细节指向脏工具名

    # A29 回喂验收：会话里存在一条 user 消息，同时含拒绝原因码与上一版脏计划原文
    feedbacks = [m.content for m in final["messages"] if m.type == "human" and "拒绝原因码" in m.content]
    assert len(feedbacks) == 1
    assert "unknown_tool" in feedbacks[0] and "query_erp_balance" in feedbacks[0]

    assert final["events"] == [
        "intake",
        "planner",
        "plan.rejected:unknown_tool",
        "planner",
        "plan.approved",
        "executor",
        "drafter",
        "submit",
    ]
    assert final["advice"].reason == "REJECT:ITEM_OVER_LIMIT"  # 0002 的剧本预期，回喂不改变业务结论
    assert final["sent"] is True


def test_always_dirty_escalates_after_max_replans() -> None:
    """超限哨兵：三轮各脏一种维度→重规划烧完（replans==2）→escalate，不送审、零工具执行。"""
    mock_tools.CALL_LOG.clear()
    final = asyncio.run(demo.run_pipeline("CLM-2026-0003", mode="always_dirty"))
    rejections = final["plan_rejections"]
    assert [r.reason_code for r in rejections] == ["unknown_tool", "missing_field", "bad_amount"]
    assert len(rejections) - 1 == graph.MAX_REPLANS  # replans 恰好用满 2 次（第 3 次拒绝不再回 planner）
    assert final["events"].count("planner") == 3  # planner 恰好 3 轮：初次 + 2 次重规划
    assert final["events"][-1] == "escalate"
    assert final["advice"].decision == "ESCALATE"
    assert final["advice"].reason == graph.ESCALATE_REASON
    assert final["sent"] is False
    assert mock_tools.CALL_LOG == []  # 计划从未合法——工具一个都没被碰过（fail-closed 的取证面）


def test_submit_stub_marks_sent_without_extra_messages() -> None:
    """送审桩：只落 sent=True 与事件，不新增消息——L5.2 在这里换 interrupt，接口形状先钉住。"""
    final = asyncio.run(demo.run_pipeline("CLM-2026-0001"))
    assert final["sent"] is True
    human_says = [m.content for m in final["messages"] if m.type == "human"]
    assert len(human_says) == 2  # intake 的单据摘要 + drafter 的起草指令——submit 零消息
