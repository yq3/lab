"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

import ex2_prebuilt as ex2
import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint


def test_run_review_satisfies_contract_for_every_claim() -> None:
    """契约（对版 test_contract 的练习内版）：四张 mock 单逐单验收 + 工具真实执行。"""
    for claim in mock_tools.claims_table():
        mock_tools.CALL_LOG.clear()
        advice = asyncio.run(ex2.run_review(claim["id"]))
        assert isinstance(advice, Advice), (claim["id"], type(advice))
        assert advice.claim_id == claim["id"]
        assert advice.decision == claim["expect_decision"], (claim["id"], advice.decision)
        assert advice.reason == claim["expect_reason"], (claim["id"], advice.reason)
        assert advice.remaining_cents == claim["expect_remaining_cents"], claim["id"]
        assert {"check_budget", "verify_invoice"} <= set(mock_tools.CALL_LOG), (claim["id"], list(mock_tools.CALL_LOG))


def test_agent_makes_exactly_two_model_requests_per_claim() -> None:
    """轮数断言：单审恰好 2 次模型请求（第 1 轮并行选两工具、第 2 轮回 Advice JSON）。"""
    first_turn, advice_json, expected = review_rules.script_for("CLM-2026-0001")
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        agent = ex2.build_agent(ex2.model_for_url(ep.url))
        result = asyncio.run(
            agent.ainvoke(
                {"messages": [{"role": "user", "content": ex2.user_brief("CLM-2026-0001")}]},
                config={"recursion_limit": ex2.RECURSION_LIMIT},
            )
        )
        assert len(ep.requests) == 2
        assert len(ep.requests[0]["tools"]) == 2  # 框架内部 bind_tools：第 1 次请求就带两个工具 schema
    advice = Advice.model_validate_json(result["messages"][-1].content.strip())
    assert advice == expected


def test_assembly_node_names_are_official() -> None:
    """装配断言：prebuilt 图节点恰好 __start__/agent/tools/__end__（装配不发请求，URL 随便给）。"""
    agent = ex2.build_agent(ex2.model_for_url("http://unused.local/v1"))
    assert set(agent.get_graph().nodes) == {"__start__", "agent", "tools", "__end__"}
