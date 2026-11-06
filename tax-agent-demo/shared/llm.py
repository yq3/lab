"""端点中立 LLM 工厂：.env 三变量（+可选 LLM_EXTRA_BODY）→ langchain ChatOpenAI。

换模型供应商只改 .env（GLM / DeepSeek / Qwen / OpenAI 兼容端点均可），
各 agent 代码不感知具体端点；模型私有开关（如思考模式）配在 LLM_EXTRA_BODY。
"""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from shared.config import llm_env, llm_extra_body


def build_chat_model(model_override: str | None = None, **kwargs: Any) -> ChatOpenAI:
    """构建 ChatOpenAI 实例。

    Args:
        model_override: 覆盖 .env 里的 MODEL_NAME（测试注入 fake model 时不用这个，
            而是直接传模型实例给 create_deep_agent）。
        **kwargs: 透传给 ChatOpenAI 的其他参数。
    """
    env = llm_env()
    extra_body = llm_extra_body()
    if extra_body is not None:
        kwargs.setdefault("extra_body", extra_body)
    return ChatOpenAI(
        model=model_override or env["MODEL_NAME"],
        api_key=SecretStr(env["OPENAI_API_KEY"]),
        base_url=env["OPENAI_BASE_URL"],
        temperature=0,
        **kwargs,
    )
