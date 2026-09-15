"""讲义代码验收（发货态必须全绿；练习区的红在 exercises/）。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from client import DONE, ChatClient, ChatConfig, SSEDecoder, build_payload
from env_loader import parse_env_file
from mock_endpoint import MockLLMEndpoint

# ---- env_loader：.env 解析 ----


def test_parse_env_file_handles_comments_and_missing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# 注释行\n"
        "\n"
        "OPENAI_BASE_URL=https://api.deepseek.com\n"
        "OPENAI_API_KEY=sk-demo\n"
        "MODEL_NAME=deepseek-chat  # 行内注释\n"
        "NO_EQUAL_SIGN_LINE\n",
        encoding="utf-8",
    )
    assert parse_env_file(env) == {
        "OPENAI_BASE_URL": "https://api.deepseek.com",
        "OPENAI_API_KEY": "sk-demo",
        "MODEL_NAME": "deepseek-chat",
    }
    assert parse_env_file(tmp_path / "absent.env") == {}  # 文件不存在：空 dict 而不是异常


# ---- build_payload：请求体组装 ----


def test_build_payload_shape() -> None:
    messages = [{"role": "user", "content": "hi"}]
    payload = build_payload(messages, model="m1")
    assert payload == {"model": "m1", "messages": messages}
    assert build_payload(messages, "m1", stream=True).get("stream") is True
    tools = [{"type": "function", "function": {"name": "t"}}]
    assert build_payload(messages, "m1", tools=tools)["tools"] == tools


# ---- SSEDecoder：跨块半行重组（手撕流式的核心验收） ----


def test_sse_decoder_reassembles_events_split_across_chunks() -> None:
    decoder = SSEDecoder()
    # 第 1 个事件的 JSON 被切在两个网络块中间；第 2 块还顺带捎上了完整的第 2 个事件
    first = decoder.feed(b'data: {"choices": [{"delta": {"content": "reimbur')
    assert first == []  # 事件未以空行收尾——还在缓冲区里等着
    second = decoder.feed(b'sement"}}]}\n\ndata: {"choices": [{"delta": {"content": " claim"}}]}\n\n')
    assert len(second) == 2
    assert '"reimbursement"' in second[0]
    assert '" claim"' in second[1]
    done = decoder.feed(b"data: [DONE]\n\n")
    assert done == [DONE]


def test_sse_decoder_optional_space_and_multiline_data() -> None:
    decoder = SSEDecoder()
    events = decoder.feed(b"data:nospace\n\ndata: one\ndata: two\n\n")  # 规范允许省略空格；多行 data 用 \n 拼接
    assert events == ["nospace", "one\ntwo"]


# ---- ChatClient × MockLLMEndpoint：真实 HTTP + SSE 的集成验收 ----


def test_complete_roundtrip_against_mock_endpoint() -> None:
    with MockLLMEndpoint() as ep:
        ep.script_text("通过。")

        async def scenario() -> None:
            async with ChatClient(ChatConfig(ep.url, "test-key", "mock-model")) as client:
                response = await client.complete([{"role": "user", "content": "预审 CLM-2026-0001"}])
                assert response["choices"][0]["message"]["content"] == "通过。"
                assert response["choices"][0]["finish_reason"] == "stop"

        asyncio.run(scenario())
        assert ep.requests[0]["model"] == "mock-model"  # 请求被端点如实记录
        assert ep.requests[0]["messages"][0]["role"] == "user"


def test_stream_roundtrip_against_mock_endpoint() -> None:
    with MockLLMEndpoint() as ep:
        ep.script_stream(["报销单 ", "通过"])

        async def scenario() -> tuple[str, int]:
            async with ChatClient(ChatConfig(ep.url, "test-key", "mock-model")) as client:
                parts = [delta async for delta in client.stream([{"role": "user", "content": "结论？"}])]
                return "".join(parts), len(parts)

        text, count = asyncio.run(scenario())
        assert text == "报销单 通过"
        assert count == 2


def test_wrong_api_key_raises_http_status_error() -> None:
    with MockLLMEndpoint(api_key="right-key") as ep:
        ep.script_text("x")  # 鉴权失败发生在脚本出队之前——不需要脚本，但保持好习惯

        async def scenario() -> None:
            async with ChatClient(ChatConfig(ep.url, "wrong-key", "mock-model")) as client:
                await client.complete([{"role": "user", "content": "hi"}])

        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            asyncio.run(scenario())
        assert excinfo.value.response.status_code == 401
