"""本课的「装配车间」：把 mock 工具装配成 adk 的 LlmAgent + Runner（四课 demo 的 adk 版骨架）。

四课对版的题面（mock_tools / review_rules / mock_endpoint）一个字不改；
这层只回答一个问题：**同一个题，全家桶框架怎么装配**——

- 工具绑定：L2.2 我们手写 JSON Schema 注册表，adk 直接放裸函数——
  FunctionTool 从 docstring + 签名自动生成 declaration（demo_schema.py 展开）；
- 模型绑定：LiteLlm 把 OpenAI 兼容端点包成 BaseLlm——api_base / api_key
  作为 kwargs 原样转交 litellm 的 acompletion（demo_events.py 打印实际请求取证）；
- 运行时：Runner 持 agent + session_service，run_async 每次吐 Event——
  agent 循环（L2.3 的 while）整个住进了框架里。
"""

from __future__ import annotations

import warnings
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

import mock_tools
from mock_endpoint import MockLLMEndpoint

warnings.filterwarnings(  # adk 2.9.0 的实验特性公告，与本课无关，静音保持输出干净
    "ignore", message=".*JSON_SCHEMA_FOR_FUNC_DECL.*", category=UserWarning
)

APP_NAME = "expense_review"
USER_ID = "night-school"

INSTRUCTION = (
    "你是报销单审查助手。收到报销单号后：先调用 check_budget 查部门预算、"
    "verify_invoice 校验关联发票，再按审查规则给出结论，"
    "最终只输出一个 JSON 对象（字段 claim_id/decision/reason/remaining_cents），不要输出其他文字。"
)


def build_reviewer(ep: MockLLMEndpoint) -> LlmAgent:
    """装配 LlmAgent：裸函数进 tools，LiteLlm 指向 mock 端点。

    LiteLlm 传参（对照 google/adk-python@7b246e01#src/google/adk/models/lite_llm.py
    的 __init__ / generate_content_async）：构造 kwargs 存进 _additional_args，
    请求时原样并入 litellm acompletion 的参数——所以 base_url 与 key 用的是
    litellm 自己的参数名 api_base / api_key，不是 adk 的命名。
    """
    return LlmAgent(
        name="expense_reviewer",
        model=LiteLlm(model="openai/mock-model", api_base=ep.url, api_key=ep.api_key),
        instruction=INSTRUCTION,
        tools=[mock_tools.check_budget, mock_tools.verify_invoice],
    )


def build_runner(agent: LlmAgent) -> Runner:
    """Runner = agent + 会话存储：InMemorySessionService 是全家桶的默认内存件。"""
    return Runner(agent=agent, app_name=APP_NAME, session_service=InMemorySessionService())


async def new_session(runner: Runner, state: dict[str, Any] | None = None) -> str:
    """在 runner 的会话存储里开一个新会话（可带初始 state），返回 session_id。

    session 是 adk 的一等概念：对话历史与会话状态（session.state）都挂在它上面，
    由 SessionService 持久化——「同一个 agent，不同会话不同记忆」的支点（demo_state.py）。
    """
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID, state=state or {})
    return session.id


async def ask(runner: Runner, session_id: str, question: str) -> AsyncGenerator[types.Event, None]:
    """向会话发一条 user 消息，异步生成框架产出的每个 Event（工具调用、回喂、最终回答）。"""
    content = types.Content(role="user", parts=[types.Part(text=question)])
    async for event in runner.run_async(user_id=USER_ID, session_id=session_id, new_message=content):
        yield event


def final_text(events: list[types.Event]) -> str:
    """从事件流里取最终回答文本（模型的软终止轮——mini-agent 循环的 return 行）。"""
    for event in reversed(events):
        if event.is_final_response() and event.content and event.content.parts:
            texts = [part.text for part in event.content.parts if part.text]
            if texts:
                return "".join(texts)
    raise ValueError("事件流里没有 final response 文本（模型没有正常收束）")
