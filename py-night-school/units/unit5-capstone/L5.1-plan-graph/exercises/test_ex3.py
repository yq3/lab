"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

import demo
import ex3_replan as ex3


def _run(scripts: list[str]) -> tuple[dict, ex3.FakePlanner]:
    model = ex3.FakePlanner(scripts)
    graph = ex3.build(model)
    result = asyncio.run(graph.ainvoke(ex3.initial_state("请规划 CLM-2026-0001 的取数步骤。")))
    return result, model


def _user_texts(messages: list) -> list[str]:
    """把 planner 收到的消息归一成 user 侧文本——state 里的消息是对象、extra 是裸 dict，两种都在场。"""

    def role_of(m: object) -> str:
        if isinstance(m, dict):
            return str(m.get("role", ""))
        return str(getattr(m, "type", ""))

    def content_of(m: object) -> str:
        if isinstance(m, dict):
            return str(m.get("content", ""))
        return str(getattr(m, "content", ""))

    return [content_of(m) for m in messages if role_of(m) in ("user", "human")]


def test_clean_plan_finishes_in_one_round() -> None:
    final, model = _run([demo.legal_plan_text("CLM-2026-0001")])
    assert final["events"] == ["planner", "plan.approved", "executor", "submit"]
    assert final["sent"] is True
    assert not final.get("plan_rejections")  # 零拒绝
    assert len(model.invocations) == 1  # planner 恰好一轮


def test_dirty_once_is_rejected_fed_back_then_passes() -> None:
    """脏一轮→拒一次→回喂一次→第 2 轮通过：拒绝次数、回喂次数、收尾三件事各自断言。"""
    final, model = _run([demo.dirty_plan_unknown_tool("CLM-2026-0001"), demo.legal_plan_text("CLM-2026-0001")])
    rejections = final["plan_rejections"]
    assert [r.reason_code for r in rejections] == ["unknown_tool"]  # 恰好一次拒绝
    assert final["events"] == [
        "planner",
        "plan.rejected:unknown_tool",
        "planner",
        "plan.approved",
        "executor",
        "submit",
    ]
    assert final["sent"] is True

    assert len(model.invocations) == 2  # planner 恰好两轮
    first, second = model.invocations
    assert not any("上一版计划被拒" in text for text in _user_texts(first))  # 第 1 轮没见过拒绝原因
    feedback = [text for text in _user_texts(second) if "上一版计划被拒" in text]
    assert len(feedback) == 1  # 恰好一次回喂
    assert "unknown_tool" in feedback[0] and "query_erp_balance" in feedback[0]  # 原因码+上一版脏计划都在场


def test_always_dirty_escalates_after_replans_exhausted() -> None:
    """连续脏三轮：重规划烧满（replans==2）→escalate 哨兵收尾，不送审。"""
    claim = "CLM-2026-0001"
    final, model = _run(
        [
            demo.dirty_plan_unknown_tool(claim),
            demo.dirty_plan_missing_field(claim),
            demo.dirty_plan_bad_amount(claim),
        ]
    )
    rejections = final["plan_rejections"]
    assert [r.reason_code for r in rejections] == ["unknown_tool", "missing_field", "bad_amount"]
    assert len(rejections) - 1 == ex3.MAX_REPLANS  # replans==2：第 3 次拒绝不再回 planner
    assert len(model.invocations) == 3  # planner 恰好 3 轮（初次 + 2 次重规划，没有第 4 次）
    assert final["events"] == [
        "planner",
        "plan.rejected:unknown_tool",
        "planner",
        "plan.rejected:missing_field",
        "planner",
        "plan.rejected:bad_amount",
        "escalate",
    ]
    assert final["sent"] is False
    assert any(event.startswith("plan.rejected:") for event in final["events"])  # 审计流水含 plan.rejected
