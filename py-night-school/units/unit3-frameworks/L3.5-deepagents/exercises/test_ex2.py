"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

import ex2_budget_subagent as ex2
import mock_tools


def test_specialist_listed_in_task_catalog() -> None:
    """声明生效：task 工具目录里挂上 budget-specialist（描述也能被主代理读到）。"""
    _, trace = asyncio.run(ex2.run_via_specialist("CLM-2026-0001"))
    task_tool = next(t for t in trace["requests"][0]["tools"] if t["function"]["name"] == "task")
    description = task_tool["function"]["description"]
    assert "- budget-specialist:" in description
    assert "预算" in description.split("budget-specialist:")[1].splitlines()[0]


def test_budget_checked_inside_subagent_rounds() -> None:
    """转交真实发生：四轮模型调用，预算查询发生在子代理的轮（无 task 工具）。"""
    advice, trace = asyncio.run(ex2.run_via_specialist("CLM-2026-0002"))
    requests = trace["requests"]
    assert len(requests) == 4  # 主 task 转交 → 子查预算 → 子报告 → 主收尾
    # R2/R3 是子代理的模型轮：工具清单无 task（不能再转交），有 check_budget
    for i in (1, 2):
        names = {t["function"]["name"] for t in requests[i]["tools"]}
        assert "task" not in names
        assert "check_budget" in names
    # R1 主代理确实按名字转交
    humans = [m for m in requests[2]["messages"] if m.get("role") == "user"]
    assert humans[0]["content"].startswith("查询报销单 CLM-2026-0002 所属部门 SALES 的预算余额")
    assert "check_budget" in mock_tools.CALL_LOG  # 工具真实执行（在子代理手里）
    assert (advice.decision, advice.reason) == ("REJECT", "REJECT:ITEM_OVER_LIMIT")
