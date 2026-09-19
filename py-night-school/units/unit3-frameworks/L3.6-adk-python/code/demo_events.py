"""Step 1：库模式离线 demo——把四课同题的报销审查 agent 用 adk 跑起来。

产出两份证据：
  ① 事件流：Runner.run_async 吐出的每个 Event（工具调用 / 回喂 / 最终回答）——
     mini-agent 的消息轨迹在这里是框架的一等公民「事件」；
  ② 端点取证：MockLLMEndpoint 收到的真实 HTTP 请求体——核对 litellm 中转后
     实际发出的 model 名、鉴权（Bearer test-key）、路径（/v1/chat/completions）。

运行：uv run python code/demo_events.py
"""

from __future__ import annotations

import asyncio

import mock_tools
import review_rules
from adk_review import ask, build_reviewer, build_runner, final_text, new_session
from advice import Advice
from mock_endpoint import MockLLMEndpoint

CLAIM_ID = "CLM-2026-0004"  # data/ 的发票无效场景单：两个工具都必须真实执行


def describe(event) -> str:  # noqa: ANN001 —— adk Event 类型在讲义里展开
    """把一个 Event 压缩成一行（工具调用 / 工具回喂 / 文本）。"""
    if not event.content or not event.content.parts:
        return f"[{event.author}] <无内容>"
    out = []
    for part in event.content.parts:
        if part.function_call:
            args = dict(part.function_call.args or {})
            out.append(f"工具调用 {part.function_call.name}({args})")
        elif part.function_response:
            out.append(f"工具回喂 {part.function_response.name}")
        elif part.text:
            text = part.text if len(part.text) <= 60 else part.text[:57] + "..."
            out.append(f"文本 {text}")
    return f"[{event.author}] " + "；".join(out)


async def main() -> None:
    print(f"== adk 库模式离线 demo：审查 {CLAIM_ID} ==")
    first_turn, final_json, expected = review_rules.script_for(CLAIM_ID)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(final_json)
        runner = build_runner(build_reviewer(ep))
        session_id = await new_session(runner)
        events = []
        async for event in ask(runner, session_id, f"请审查报销单 {CLAIM_ID}"):
            events.append(event)
            print(describe(event))
        print()
        print("== 端点收到的请求（litellm 中转后的真实形态） ==")
        for i, request in enumerate(ep.requests):
            print(
                f"request[{i}] model={request['model']!r} messages={len(request['messages'])} "
                f"tools={[t['function']['name'] for t in request.get('tools') or []]}"
            )
        print("鉴权与路径由端点本身把关：Bearer test-key、POST /v1/chat/completions（不对即 401/404/400）。")
    print()
    advice = Advice.model_validate_json(final_text(events))
    print("== 解析出口 ==")
    print(advice.model_dump_json())
    print(f"剧本预期: {expected.model_dump_json()}")
    print(f"工具真实执行取证 CALL_LOG: {mock_tools.CALL_LOG}")
    print(f"匹配: {advice == expected}")


if __name__ == "__main__":
    asyncio.run(main())
