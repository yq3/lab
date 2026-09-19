"""讲义区验收：prebuilt 装配与 Send 扇出的装配纪律与离线行为（与 test_contract.py 互补——
契约只管出口，这里管装配事实：官方节点名、轮次结构、扇出形状、自定义 reducer、批量确定性）。"""

from __future__ import annotations

import asyncio
from typing import get_type_hints

from langchain_core.messages import AIMessage
from langgraph.types import Send

import demo
import demo_batch
import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint


def test_prebuilt_assembly_node_names() -> None:
    """装配事实：prebuilt 图的节点恰好 __start__/agent/tools/__end__（ex3 事实题的行为底座）。"""
    agent = demo.build_agent(demo.model_for_url("http://unused.local/v1"))  # 装配不发请求
    assert set(agent.get_graph().nodes) == {"__start__", "agent", "tools", "__end__"}


def test_full_loop_stream_chunks_and_two_requests() -> None:
    """整图离线跑：superstep 序列 agent→tools×2（Send 扇出）→agent、2 次模型请求、Advice 出口。"""
    first_turn, advice_json, expected = review_rules.script_for("CLM-2026-0002")
    mock_tools.CALL_LOG.clear()
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        agent = demo.build_agent(demo.model_for_url(ep.url))
        chunks: list[list[str]] = []
        final_message = AIMessage(content="")

        def stream() -> None:
            nonlocal final_message
            for chunk in agent.stream(
                {"messages": [{"role": "user", "content": demo.user_brief("CLM-2026-0002")}]},
                config={"recursion_limit": demo.RECURSION_LIMIT},
                stream_mode="updates",
            ):
                chunks.append(list(chunk.keys()))
                last_update = chunk.get("agent")
                if last_update:
                    final_message = last_update["messages"][-1]

        stream()
        requests = ep.requests
    assert chunks == [["agent"], ["tools"], ["tools"], ["agent"]]  # v2 默认：每个 tool_call 一个 Send 分支
    assert len(requests) == 2  # 模型恰好被调 2 次（对照 L2.3 的「reviewer 执行两轮」）
    assert {"check_budget", "verify_invoice"} <= set(mock_tools.CALL_LOG)
    assert Advice.model_validate_json(str(final_message.content).strip()) == expected


def test_run_review_matches_scripted_expectation_for_every_claim() -> None:
    """统一入口逐单验收：Advice 四字段与 review_rules 预期完全一致（契约的装配内视角版）。"""
    for claim in mock_tools.claims_table():
        advice_out = asyncio.run(demo.run_review(claim["id"]))
        _first, _text, expected = review_rules.script_for(claim["id"])
        assert advice_out == expected, claim["id"]
        assert isinstance(advice_out, Advice)


def test_merge_results_reducer_semantics() -> None:
    """自定义 reducer 的直接行为：浅合并、new 覆盖同名键（dict 不支持 +，operator.add 在这里会炸）。"""
    assert demo_batch.merge_results({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
    assert demo_batch.merge_results({"a": 1, "shared": "old"}, {"shared": "new"}) == {"a": 1, "shared": "new"}


def test_batch_state_declares_custom_dict_reducer() -> None:
    """meta：results/timing 必须挂自定义 dict 合并 reducer（覆盖型检查，L0.1 ex2 先例）。"""
    hints = get_type_hints(demo_batch.BatchState, include_extras=True)
    assert hints["results"].__metadata__ == (demo_batch.merge_results,)
    assert hints["timing"].__metadata__ == (demo_batch.merge_results,)


def test_fan_out_builds_one_send_per_claim() -> None:
    """扇出形状：条件边返回 N 个 Send——节点名 review、arg 是带 claim_id 的分支专属状态。"""
    claim_ids = [claim["id"] for claim in mock_tools.claims_table()]
    state: demo_batch.BatchState = {
        "claim_ids": claim_ids,
        "ep_urls": {c: f"http://127.0.0.1:1{i}/v1" for i, c in enumerate(claim_ids)},
        "results": {},
        "timing": {},
    }
    sends = demo_batch.fan_out(state)
    assert len(sends) == 4 and all(isinstance(send, Send) for send in sends)
    assert {send.node for send in sends} == {"review"}
    assert [send.arg["claim_id"] for send in sends] == claim_ids
    assert all(send.arg["ep_url"].startswith("http://") for send in sends)


def test_batch_reviews_all_claims_with_eight_model_requests() -> None:
    """批量线整图：四单按 claim_id 落位、计数正确、每单恰好 2 次模型请求（4 端点 × 2）。"""
    claim_ids = [claim["id"] for claim in mock_tools.claims_table()]
    endpoints = {claim_id: MockLLMEndpoint() for claim_id in claim_ids}
    for endpoint in endpoints.values():
        endpoint.start()
    try:
        state = demo_batch.run_batch(claim_ids, endpoints=endpoints)
        results = state["results"]
        assert set(results) == set(claim_ids)
        for claim in mock_tools.claims_table():
            _first, _text, expected = review_rules.script_for(claim["id"])
            assert results[claim["id"]] == expected, claim["id"]
        assert state["report"]["counts"] == {"APPROVE": 1, "REJECT": 2, "ESCALATE": 1}
        assert state["report"]["total_cents"] == 20400
        assert [len(endpoint.requests) for endpoint in endpoints.values()] == [2, 2, 2, 2]  # 每单恰好 2 次
        assert len(mock_tools.CALL_LOG) == 8  # 4 单 × 每单 2 个工具，全部真实执行
    finally:
        for endpoint in endpoints.values():
            endpoint.stop()


def test_batch_is_deterministic_across_runs() -> None:
    """两次独立批量跑的 results/report 完全一致——并发执行、确定归并（合并顺序与跑完顺序无关）。"""
    first = demo_batch.run_batch()
    second = demo_batch.run_batch()
    assert first["results"] == second["results"]
    assert first["report"] == second["report"]
