"""Step 3：session.state——「同一个 agent，不同会话不同策略」。

全家桶的招牌能力：会话状态由框架的 SessionService 管理（对照 Java 的
HttpSession——但这里 state 不在应用进程的会话缓存里，而在框架的会话存储里，
生产可换 DatabaseSessionService / VertexAiSessionService 落库）。

两条注入路径，本 demo 都离线实测：
  ① instruction 占位符：instruction 里的 {item_limit_cents} 在每次请求前由
     session.state 填充（对照 Spring 的 property placeholder）；
  ② 工具读 state：签名里声明 tool_context 参数，框架注入后用
     tool_context.state["item_limit_cents"] 读——工具代码不用改，策略跟着会话走。

运行：uv run python code/demo_state.py
"""

from __future__ import annotations

import asyncio

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.tool_context import ToolContext
from google.genai import types

import mock_tools
from adk_review import APP_NAME, USER_ID, final_text
from mock_endpoint import MockLLMEndpoint

STATEFUL_INSTRUCTION = (
    "你是报销审查助手。本会话的单笔上限是 {item_limit_cents} 分。先调用 limit_report 了解本会话策略，再回答。"
)


def limit_report(tool_context: ToolContext) -> dict:
    """报告本会话的单笔上限策略。

    Args:
        tool_context: 框架注入的会话上下文，用来读 session.state
    """
    limit = tool_context.state.get("item_limit_cents", mock_tools.ITEM_LIMIT_CENTS)
    mock_tools.CALL_LOG.append(f"limit_report:{limit}")  # 取证：state 真的流到了工具
    return {"item_limit_cents": limit}


async def run_one(item_limit_cents: int) -> None:
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls([{"id": "call_limit", "name": "limit_report", "arguments": {}}])
        ep.script_text(f"本会话单笔上限 {item_limit_cents} 分。")
        agent = LlmAgent(
            name="stateful_reviewer",
            model=LiteLlm(model="openai/mock-model", api_base=ep.url, api_key=ep.api_key),
            instruction=STATEFUL_INSTRUCTION,
            tools=[limit_report],
        )
        from adk_review import build_runner

        runner = build_runner(agent)
        session = await runner.session_service.create_session(  # 策略在会话创建时注入
            app_name=APP_NAME, user_id=USER_ID, state={"item_limit_cents": item_limit_cents}
        )
        content = types.Content(role="user", parts=[types.Part(text="本会话策略是什么？")])
        events = []
        async for event in runner.run_async(user_id=USER_ID, session_id=session.id, new_message=content):
            events.append(event)
        system_msgs = [m for m in ep.requests[0]["messages"] if m["role"] == "system"]
        # adk 会在我们的 instruction 后面追加自己的 agent 身份段（You are an agent...）——只看首段
        filled_instruction = system_msgs[0]["content"].split("\n\nYou are an agent")[0] if system_msgs else "<无>"
        tool_feedback = [m["content"] for m in ep.requests[1]["messages"] if m["role"] == "tool"]
        print(f"-- 注入 item_limit_cents={item_limit_cents} --")
        print(f"  ① instruction 填充后: {filled_instruction}")
        print(f"  ② 工具回喂(第2轮请求里): {tool_feedback[0]}")
        print(f"  最终回答: {final_text(events)}")


async def main() -> None:
    print("== 同一个 agent 定义，两个会话两套策略 ==")
    await run_one(5000)
    print()
    await run_one(3000)
    print()
    print(f"工具取证 CALL_LOG: {mock_tools.CALL_LOG}")
    print("agent 与工具的代码一行没换——策略差异全部来自 create_session(state=...)。")


if __name__ == "__main__":
    asyncio.run(main())
