# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""ex3 callback guardrail：before_model_callback 拦不合规单号，模型零请求。

背景（Step 4 的完整版）：讲义的 claim_id_guard 只拦「格式像单号但不合规」的请求；
本题收紧策略：user 消息里出现的任何单号（CLM- 开头的记号）必须匹配
CLM-YYYY-NNNN，否则整个请求在发往模型之前被短路。

完成判据：uv run pytest exercises/test_ex3.py 全绿——共 4 个测试：
  ① 单元·放行：合规单号（如 CLM-2026-0002）→ 返回 None（照常走模型）；
  ② 单元·拦截：坏单号（如 CLM-99-1）→ 返回 LlmResponse，内容文本恰为 BLOCKED_REPLY；
  ③ 集成·拦截即零请求：坏单号跑完整 agent → ep.requests 为空 + 最终回答为 BLOCKED_REPLY；
  ④ 集成·放行不受影响：合规单号照常出 Advice（模型请求 2 次、工具真实执行）。

所需的顶部 import（骨架未预置，自己加；注意从具体模块导入，pyright 才认）：
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types
"""

from __future__ import annotations

import re

from google.adk.agents import LlmAgent
from google.adk.models.llm_response import LlmResponse
from google.genai import types

import mock_tools
from adk_review import build_reviewer
from mock_endpoint import MockLLMEndpoint

CLAIM_ID_RE = re.compile(r"^CLM-\d{4}-\d{4}$")
BLOCKED_REPLY = "REJECT:CLAIM_ID_INVALID（单号不合规：必须是 CLM-YYYY-NNNN 格式）"


# TODO(ex3): 实现 before_model_callback——签名已给定（框架按 (callback_context, llm_request) 调用）。
# 策略：从 llm_request 最后一条 contents 里取 user 文本，找出 CLM- 开头的记号；
#   记号存在且不匹配 CLAIM_ID_RE → 构造短路响应返回（文本用 BLOCKED_REPLY，role 记 "model"）；
#   其余情况（没单号 / 单号合规）→ 返回 None 放行。
# 构造短路响应的 API 形状见讲义 Step 4（code/demo_callback.py 的 LlmResponse 用法）。
def claim_guard(callback_context, llm_request) -> LlmResponse | None:  # noqa: ANN001
    last_content = llm_request.contents[-1] if llm_request.contents else None
    user_text = ""
    if last_content and last_content.parts:
        user_text = last_content.parts[0].text or ""
    match = re.search(r"CLM[-\w]*", user_text)
    claim_id = match.group(0) if match else ""
    if claim_id and not CLAIM_ID_RE.fullmatch(claim_id):
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=BLOCKED_REPLY)]))
    return None


def build_guarded(ep: MockLLMEndpoint) -> LlmAgent:
    """装配带闸 agent（given）：与讲义 demo_callback.build_guarded 同构。"""
    base = build_reviewer(ep)
    return LlmAgent(
        name=base.name,
        model=base.model,
        instruction=base.instruction,
        tools=[mock_tools.check_budget, mock_tools.verify_invoice],
        before_model_callback=claim_guard,
    )
