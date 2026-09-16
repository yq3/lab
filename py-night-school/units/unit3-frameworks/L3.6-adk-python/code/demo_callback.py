"""Step 4：before_model_callback 当 guardrail——坏单号在模型之前被短路。

L3.1 的 guardrail 与这里的 before_model_callback 是同一个概念的两种拼写：
请求在「发给模型之前」过一道你写的闸，闸返回 None 放行、返回 LlmResponse 短路。
Java 对照：Servlet Filter / Spring Interceptor 的 preHandle——返回 false 就不走后续链。

验收最妙的一点：短路的断言不是「回答像被拦了」，而是 **ep.requests 为空**——
模型一次都没被请求。拦截发生在网络调用之前，这是离线可证的。

运行：uv run python code/demo_callback.py
"""

from __future__ import annotations

import asyncio
import re

from google.adk.agents import LlmAgent
from google.adk.models.llm_response import LlmResponse
from google.genai import types

import mock_tools
import review_rules
from adk_review import ask, build_reviewer, build_runner, final_text, new_session
from mock_endpoint import MockLLMEndpoint

CLAIM_ID_PATTERN = re.compile(r"^CLM-\d{4}-\d{4}$")
BLOCKED_REPLY = "REJECT:CLAIM_ID_INVALID（单号不合规：必须是 CLM-YYYY-NNNN 格式）"


def claim_id_guard(callback_context, llm_request) -> LlmResponse | None:  # noqa: ANN001
    """before_model_callback：user 消息里的报销单号不合规 → 直接短路，不请求模型。

    Args:
        callback_context: 框架注入的回调上下文（本闸用不上，签名必须收下）
        llm_request: 即将发给模型的请求（可读可改——本闸只读最后一条 user 消息）
    """
    user_text = ""
    last_content = llm_request.contents[-1] if llm_request.contents else None
    if last_content and last_content.parts:
        user_text = last_content.parts[0].text or ""
    match = re.search(r"CLM[-\w]*", user_text)
    claim_id = match.group(0) if match else ""
    if claim_id and not CLAIM_ID_PATTERN.fullmatch(claim_id):
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=BLOCKED_REPLY)]))
    return None  # 放行：照常请求模型


def build_guarded(ep) -> LlmAgent:  # noqa: ANN001 —— 与 build_reviewer 同构，只多一道闸
    base = build_reviewer(ep)
    return LlmAgent(
        name=base.name,
        model=base.model,
        instruction=base.instruction,
        tools=[mock_tools.check_budget, mock_tools.verify_invoice],
        before_model_callback=claim_id_guard,
    )


async def main() -> None:
    print("== before_model_callback guardrail ==")
    good_id = "CLM-2026-0002"
    for label, question in (
        ("合规单号", f"请审查报销单 {good_id}"),
        ("坏单号(格式错)", "请审查报销单 CLM-26-2"),
        ("没有单号", "帮我看看今天有什么单子"),
    ):
        first_turn, final_json, _expected = review_rules.script_for(good_id)
        with MockLLMEndpoint() as ep:  # 剧本照常备好——短路的场景根本轮不到消耗它
            ep.script_tool_calls(first_turn)
            ep.script_text(final_json)
            runner = build_runner(build_guarded(ep))
            session_id = await new_session(runner)
            mock_tools.CALL_LOG.clear()
            events = [e async for e in ask(runner, session_id, question)]
        print(f"-- {label}: {question!r}")
        print(f"   模型请求次数: {len(ep.requests)}（为 0 即拦截发生在网络调用之前）")
        print(f"   工具执行: {mock_tools.CALL_LOG or '<未执行>'}")
        print(f"   回答: {final_text(events)}")
        print()
    print("对照 mini-agent：这道闸在 L2.3 里要自己写在循环体最前面；")
    print("框架把它命名成回调链的一环——代价是你得知道闸挂在哪（模型前/后、工具前/后共四类）。")


if __name__ == "__main__":
    asyncio.run(main())
