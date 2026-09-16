"""讲义区验收：demo 图的装配纪律与离线行为（与 test_contract.py 互补——
契约只管出口，这里管图内部：路由、工具分发、审计流水、reducer 注解）。"""

from __future__ import annotations

import asyncio
import operator
from typing import get_type_hints

from langchain_core.messages import AIMessage

import demo
import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint


def test_state_declares_reducers() -> None:
    """meta：messages/events 必须带合并语义的 Annotated reducer（覆盖型检查，L0.1 ex2 先例）。"""
    hints = get_type_hints(demo.ClaimState, include_extras=True)
    assert hints["messages"].__metadata__ == (demo.add_messages,)
    assert hints["events"].__metadata__ == (operator.add,)


def test_route_after_reviewer_reads_tool_calls() -> None:
    with_tools = AIMessage(content="", tool_calls=[{"name": "check_budget", "args": {"dept": "DEV"}, "id": "c1"}])
    assert demo.route_after_reviewer({"messages": [with_tools], "events": []}) == "tools"
    without = AIMessage(content='{"claim_id": "x"}')
    assert demo.route_after_reviewer({"messages": [without], "events": []}) == "finalize"


def test_tools_node_dispatches_registry_and_feeds_unknown() -> None:
    """注册表分发 + 未知工具回喂 error（L2.2 的纪律在图节点里原样成立）。"""
    mock_tools.CALL_LOG.clear()
    message = AIMessage(
        content="",
        tool_calls=[
            {"name": "check_budget", "args": {"dept": "DEV"}, "id": "call_ok"},
            {"name": "no_such_tool", "args": {"x": 1}, "id": "call_bad"},
        ],
    )
    update = asyncio.run(demo.tools_node({"messages": [message], "events": []}))
    assert "check_budget" in mock_tools.CALL_LOG  # 已知工具真实执行
    [ok, bad] = update["messages"]
    assert ok["tool_call_id"] == "call_ok" and "remaining_cents" in ok["content"]  # 执行结果回喂
    assert bad["tool_call_id"] == "call_bad" and "unknown_tool" in bad["content"]  # 错误回喂不抛
    assert update["events"] == ["tools"]


def test_graph_runs_full_loop_with_audit_and_two_requests() -> None:
    """整图离线跑：节点序列、审计流水、2 次模型请求、Advice 出口一次验全。"""
    first_turn, advice_json, expected = review_rules.script_for("CLM-2026-0003")
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        graph = demo.build_graph(demo.model_for_url(ep.url))
        chunks = []

        async def stream() -> None:
            async for chunk in graph.astream(
                {"messages": demo.initial_messages("CLM-2026-0003")},
                config={"recursion_limit": demo.RECURSION_LIMIT},
                stream_mode="updates",
            ):
                chunks.append(list(chunk.keys()))

        asyncio.run(stream())
        requests = len(ep.requests)
    assert chunks == [["reviewer"], ["tools"], ["reviewer"], ["finalize"]]
    assert requests == 2  # astream 一趟恰好消耗两份剧本（reviewer 执行两轮）


def test_run_review_matches_scripted_expectation_for_every_claim() -> None:
    """统一入口逐单验收：Advice 四字段与 review_rules 预期完全一致（契约的图内视角版）。"""
    for claim in mock_tools.claims_table():
        advice_out = asyncio.run(demo.run_review(claim["id"]))
        _first, _text, expected = review_rules.script_for(claim["id"])
        assert advice_out == expected, claim["id"]
        assert isinstance(advice_out, Advice)


def test_finalize_parses_advice_from_final_message() -> None:
    _first, advice_json, _expected = review_rules.script_for("CLM-2026-0001")
    state: demo.ClaimState = {  # 带空白也稳（finalize 里 .strip()）
        "messages": [AIMessage(content=f"  {advice_json} ")],
        "events": [],
    }
    update = asyncio.run(demo.finalize(state))
    assert update["advice"].decision == "APPROVE"
    assert update["events"] == ["finalize"]
