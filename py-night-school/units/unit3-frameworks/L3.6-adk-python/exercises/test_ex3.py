"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio

from google.adk.models.llm_request import LlmRequest
from google.genai import types as genai_types

import ex3_guardrail as ex3
import mock_tools
import review_rules
from adk_review import ask, build_runner, final_text, new_session
from advice import Advice
from mock_endpoint import MockLLMEndpoint

GOOD_QUESTION = "请审查报销单 CLM-2026-0002"
BAD_QUESTION = "请审查报销单 CLM-99-1"


def _request_with(text: str) -> LlmRequest:
    request = LlmRequest()
    request.contents.append(genai_types.Content(role="user", parts=[genai_types.Part(text=text)]))
    return request


def test_guard_passes_valid_claim_id() -> None:
    assert ex3.claim_guard(None, _request_with(GOOD_QUESTION)) is None


def test_guard_blocks_malformed_claim_id() -> None:
    response = ex3.claim_guard(None, _request_with(BAD_QUESTION))
    assert response is not None
    assert response.content is not None and response.content.parts
    assert response.content.parts[0].text == ex3.BLOCKED_REPLY


def _collect_question(question: str):
    first_turn, final_json, _expected = review_rules.script_for("CLM-2026-0002")

    async def run_all():
        with MockLLMEndpoint() as ep:
            ep.script_tool_calls(first_turn)
            ep.script_text(final_json)
            runner = build_runner(ex3.build_guarded(ep))
            session_id = await new_session(runner)
            mock_tools.CALL_LOG.clear()
            events = [event async for event in ask(runner, session_id, question)]
            return ep.requests, events

    return asyncio.run(run_all())


def test_integration_blocked_means_zero_model_requests() -> None:
    requests, events = _collect_question(BAD_QUESTION)
    assert requests == []  # 拦截发生在网络调用之前——模型零请求
    assert mock_tools.CALL_LOG == []  # 工具自然也没执行
    assert final_text(events) == ex3.BLOCKED_REPLY


def test_integration_valid_claim_still_works() -> None:
    requests, events = _collect_question(GOOD_QUESTION)
    assert len(requests) == 2  # 工具轮 + 回答轮，照常走模型
    assert {"check_budget", "verify_invoice"} <= set(mock_tools.CALL_LOG)
    advice = Advice.model_validate_json(final_text(events))
    assert advice.decision == "REJECT"
    assert advice.reason == "REJECT:ITEM_OVER_LIMIT"
