"""讲义区验收（四）：图端到端（自动批准驱动）——四单结论、重规划环回喂、超限哨兵、门的账。

L5.3 副本声明（对版纪律）：与 L5.3 的 test_demo 相比差异都是「submit 换芯 + 执行门」的
连锁——run_pipeline 内置自动批准段（图必停 submit）；四单断言多了 paid_cents 与
events 尾部的 gate/payment 记录；0003 的终态 reason 从 REJECT:INVALID_AMOUNT 变为
REJECT:GATE_DENIED（脏数据单被人批了，门也不付——纵深防御的体感）。
"""

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
        "approval_rejects": [],
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
            "approval_rejects": [],
        }
        return state

    assert graph.route_after_gate(gate_state([rejection])) == "planner"
    assert graph.route_after_gate(gate_state([rejection, rejection])) == "planner"
    assert graph.route_after_gate(gate_state([rejection] * 3)) == "escalate"
    assert graph.MAX_REPLANS == 2  # 边界钉死：第 3 次拒绝时 replans=2 已用满


def test_four_claims_clean_mode_match_expectations(tmp_path) -> None:
    """图端到端（clean 剧本 + 自动批准 + 宽门）：四单 advice 与 review_mock 的 expect_* 逐字段
    全等、过门付款、工具真实执行（CALL_LOG 取证）。0003 是纵深防御现场：脏数据单（负总额）
    被自动批准后过门 → 意图不可解析 → DENY（终态 reason 因此从 INVALID_AMOUNT 变 GATE_DENIED）。"""
    paid_or_denied = {"CLM-2026-0001": 7100, "CLM-2026-0002": 8800, "CLM-2026-0004": 5000}
    for claim in mock_tools.claims_table():
        mock_tools.CALL_LOG.clear()
        final = asyncio.run(demo.run_pipeline(claim["id"]))
        advice = final["advice"]
        assert advice.claim_id == claim["id"]
        assert advice.decision == claim["expect_decision"], (claim["id"], advice.decision)
        if claim["id"] == "CLM-2026-0003":
            assert advice.reason == graph.ESCALATE_GATE_REASON  # 门拦下：金额 -500 不可解析
            assert "paid_cents" not in final  # 没付款
            assert final["sent"] is False  # 门哨兵收口：送审标志被改写为「未送出」（不付款）
        else:
            assert advice.reason == claim["expect_reason"], (claim["id"], advice.reason)
            assert final["paid_cents"] == paid_or_denied[claim["id"]]  # 过门原样付款
            assert final["sent"] is True
        assert final["events"][-2] in {"gate.allowed", "gate.denied:unparseable_intent"}
        assert {"check_budget", "verify_invoice"} <= set(mock_tools.CALL_LOG), claim["id"]
        assert final["results"]["budget"]["remaining_cents"] == claim["expect_remaining_cents"]


def test_dirty_once_replans_with_reason_fed_back() -> None:
    """重规划环：脏计划（未知工具）被拒→原因+上一版回喂→第 2 轮通过→正常收尾（L5.1 语义原样）。"""
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
        "submit.approved",
        "gate.allowed",
        "payment.executed",
    ]
    assert final["advice"].reason == "REJECT:ITEM_OVER_LIMIT"  # 0002 的剧本预期，回喂不改变业务结论
    assert final["paid_cents"] == 8800  # 自动批准后过门付款（宽门）
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
    assert final["advice"].reason == graph.ESCALATE_REASON  # 重规划烧满（不是门哨兵——门从没见过这单）
    assert final["sent"] is False
    assert mock_tools.CALL_LOG == []  # 计划从未合法——工具一个都没被碰过（fail-closed 的取证面）
    assert "gate_result" not in final  # 门从未被叫：submit 都没到


def test_submit_approval_records_config_hash(tmp_path) -> None:
    """审批回执进 state：approve 恢复后 approval 键带 CONFIRMED + 与内容自洽的指纹（A7 的档）。"""
    final = asyncio.run(demo.run_pipeline("CLM-2026-0001"))
    approval = final["approval"]
    assert approval["decision"] == "CONFIRMED"
    assert len(approval["content_hash"]) == 16
    candidate = final["plan"]
    assert approval["content_hash"] == graph.content_hash(final["advice"], candidate.claim_total_cents)
    assert final["events"].count("submit.approved") == 1
