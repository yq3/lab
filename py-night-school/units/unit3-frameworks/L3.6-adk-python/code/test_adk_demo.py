"""讲义代码验收（发货态必须全绿；练习区的红在 exercises/）。

覆盖 Step 1–5 的关键断言：装配与事件流、declaration 自动生成、
session.state 两条注入路径、guardrail 零请求短路、eval 确定性指标。
"""

from __future__ import annotations

import asyncio
import json

from google.adk.evaluation.eval_case import IntermediateData, Invocation
from google.adk.evaluation.eval_metrics import EvalMetric, ToolTrajectoryCriterion
from google.adk.evaluation.trajectory_evaluator import TrajectoryEvaluator
from google.adk.models.llm_request import LlmRequest
from google.adk.tools import FunctionTool
from google.genai import types as genai_types

import demo_state
import mock_tools
import review_rules
from adk_review import ask, build_reviewer, build_runner, final_text, new_session
from advice import Advice
from demo import run_review
from demo_callback import BLOCKED_REPLY, build_guarded, claim_id_guard
from demo_eval import expected_invocation
from mock_endpoint import MockLLMEndpoint


def test_review_one_claim_via_runner_events() -> None:
    """Step 1：Runner 事件流里能看到工具调用、回喂与最终 Advice JSON。"""
    claim_id = "CLM-2026-0001"
    first_turn, final_json, expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(final_json)
        runner = build_runner(build_reviewer(ep))
        session_id = asyncio.run(new_session(runner))
        events = asyncio.run(_collect(ask(runner, session_id, f"请审查报销单 {claim_id}")))
    # 端点取证：litellm 中转后 model 名精确、鉴权与路径由端点把关
    assert len(ep.requests) == 2
    assert ep.requests[0]["model"] == "mock-model"
    assert [t["function"]["name"] for t in ep.requests[0]["tools"]] == [
        "check_budget",
        "verify_invoice",
    ]
    # 事件流取证：两个工具都被模型选中过
    called = [
        part.function_call.name
        for event in events
        if event.content
        for part in event.content.parts or []
        if part.function_call
    ]
    assert sorted(called) == ["check_budget", "verify_invoice"]
    advice = Advice.model_validate_json(final_text(events))
    assert advice == expected
    assert {"check_budget", "verify_invoice"} <= set(mock_tools.CALL_LOG)


async def _collect(async_gen) -> list:  # noqa: ANN001
    return [event async for event in async_gen]


def test_function_tool_declaration_from_docstring_and_signature() -> None:
    """Step 2：名字/描述/参数 schema 全部来自函数自身；ToolContext 参数被剔除。"""
    from demo_schema import check_budget_stateful

    decl = FunctionTool(func=mock_tools.check_budget)._get_declaration()
    assert decl is not None
    assert decl.name == "check_budget"
    assert decl.description == mock_tools.check_budget.__doc__
    schema = decl.parameters_json_schema
    assert schema is not None
    assert schema["type"] == "object"
    assert schema["properties"]["dept"]["type"] == "string"
    assert schema["required"] == ["dept"]

    stateful = FunctionTool(func=check_budget_stateful)._get_declaration()
    assert stateful is not None
    stateful_schema = stateful.parameters_json_schema
    assert stateful_schema is not None
    properties = stateful_schema["properties"]
    assert "tool_context" not in properties  # 框架上下文参数不外泄给模型
    assert list(properties) == ["dept"]


def test_session_state_flows_into_instruction_and_tool() -> None:
    """Step 3：create_session(state=...) 同时改写 instruction 占位符与工具读到的值。"""
    for limit in (5000, 3000):
        mock_tools.CALL_LOG.clear()
        asyncio.run(demo_state.run_one(limit))
        assert f"limit_report:{limit}" in mock_tools.CALL_LOG  # state 一路流到工具


def test_before_model_callback_blocks_without_model_request() -> None:
    """Step 4：坏单号短路——模型零请求、工具零执行、回答是拦截文案。"""
    first_turn, final_json, _expected = review_rules.script_for("CLM-2026-0002")
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(final_json)
        runner = build_runner(build_guarded(ep))
        session_id = asyncio.run(new_session(runner))
        mock_tools.CALL_LOG.clear()
        events = asyncio.run(_collect(ask(runner, session_id, "请审查报销单 CLM-26-2")))
        assert ep.requests == []  # 拦截发生在网络调用之前
        assert mock_tools.CALL_LOG == []
        assert final_text(events) == BLOCKED_REPLY

    # 放行路径：格式合规的单号照常走模型（callback 返回 None）
    assert claim_id_guard(None, _request_with("请审查报销单 CLM-2026-0002")) is None


def _request_with(text: str) -> LlmRequest:
    """最小 LlmRequest 替身，只喂一条 user 消息。"""
    request = LlmRequest()
    request.contents.append(genai_types.Content(role="user", parts=[genai_types.Part(text=text)]))
    return request


def test_trajectory_evaluator_deterministic_scoring() -> None:
    """Step 5：确定性指标离线可跑——轨迹匹配 1.0，参数标错 0.0。"""
    question = "请审查报销单 CLM-2026-0004"
    first_turn, _final_json, _expected = review_rules.script_for("CLM-2026-0004")
    expected = expected_invocation(question, first_turn)
    evaluator = TrajectoryEvaluator(
        eval_metric=EvalMetric(
            metric_name="tool_trajectory",
            criterion=ToolTrajectoryCriterion(match_type=ToolTrajectoryCriterion.MatchType.ANY_ORDER, threshold=1.0),
        )
    )
    result = evaluator.evaluate_invocations(actual_invocations=[expected], expected_invocations=[expected])
    assert result.overall_score == 1.0
    wrong = Invocation(
        user_content=genai_types.Content(role="user", parts=[genai_types.Part(text=question)]),
        intermediate_data=IntermediateData(
            tool_uses=[genai_types.FunctionCall(id="call_wrong", name="check_budget", args={"dept": "SALES"})]
        ),
    )
    result_bad = evaluator.evaluate_invocations(actual_invocations=[expected], expected_invocations=[wrong])
    assert result_bad.overall_score == 0.0


def test_run_review_contract_offline() -> None:
    """统一出口自证：与 test_contract 同口径抽查一单（CLM-2026-0004 发票无效场景）。"""
    advice = asyncio.run(run_review("CLM-2026-0004"))
    assert json.loads(advice.model_dump_json()) == {
        "claim_id": "CLM-2026-0004",
        "decision": "REJECT",
        "reason": "REJECT:INVOICE_INVALID",
        "remaining_cents": 40000,
    }
