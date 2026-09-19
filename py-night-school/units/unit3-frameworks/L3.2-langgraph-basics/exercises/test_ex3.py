"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

import ex3_gate as ex3
import mock_tools
import review_rules
from mock_endpoint import MockLLMEndpoint


def test_valid_claim_reviews_through_subgraph() -> None:
    claim_id = "CLM-2026-0004"
    first_turn, advice_json, expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        graph = ex3.build_gate(ex3.model_for(ep.url))
        mock_tools.CALL_LOG.clear()
        result = asyncio.run(graph.ainvoke({"claim_id": claim_id, "messages": ex3.initial_messages(claim_id)}))
        requests = ep.requests
    assert result["advice"] == expected  # Advice 四字段与规则表预期全等
    assert len(requests) == 2  # 子图内模型恰好跑两轮（第 1 轮选工具、第 2 轮收束）
    assert {"check_budget", "verify_invoice"} <= set(mock_tools.CALL_LOG)  # 工具真实执行


def test_unknown_claim_short_circuits_without_model_call() -> None:
    with MockLLMEndpoint() as ep:
        # 故意备好剧本：如果 precheck 失效、模型被调，剧本会被消费——断言请求数就会露馅
        ep.script_tool_calls([{"id": "call_x", "name": "check_budget", "arguments": {"dept": "SALES"}}])
        ep.script_text("{}")
        graph = ex3.build_gate(ex3.model_for(ep.url))
        mock_tools.CALL_LOG.clear()
        result = asyncio.run(
            graph.ainvoke({"claim_id": "CLM-2026-9999", "messages": ex3.initial_messages("CLM-2026-9999")})
        )
        requests = ep.requests
    advice_out = result["advice"]
    assert advice_out.claim_id == "CLM-2026-9999"
    assert advice_out.decision == "ESCALATE"
    assert advice_out.reason == "REJECT:CLAIM_NOT_FOUND"
    assert len(requests) == 0  # deny 短路：一次模型请求都没有
    assert mock_tools.CALL_LOG == []  # 工具也没被碰
