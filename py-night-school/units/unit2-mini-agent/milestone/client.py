"""裸调 LLM API 的最小客户端：httpx + json，零 SDK。

本文件是 L2.1 的主角，四个部件由浅入深：
    build_payload   请求体组装（纯函数）
    SSEDecoder      增量 SSE 解码器（纯类）——手撕流式的全部核心
    ChatConfig      端点三变量（dataclass + from_env 替代构造，L1.3 复习）
    ChatClient      HTTP 客户端（async with 上下文管理器，L1.7 复习）

协议约定（OpenAI 兼容端点的公共契约）：
    POST {base_url}/chat/completions
    请求头 Authorization: Bearer {api_key}；请求体 JSON（model/messages/tools/stream）
    非流式 → 响应体是一个 JSON；流式 → 响应体是 text/event-stream（SSE）字节流。
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

import httpx

from env_loader import load_env

DONE = "[DONE]"  # 流结束哨兵：一条 data: [DONE] 事件，不是 JSON


def build_payload(
    messages: Sequence[dict],
    model: str,
    tools: Sequence[dict] | None = None,
    stream: bool = False,
) -> dict:
    """组装 /chat/completions 请求体。tools 元素形如：
    {"type": "function", "function": {"name": ..., "description": ..., "parameters": <JSON Schema>}}
    """
    payload: dict = {"model": model, "messages": list(messages)}
    if tools is not None:
        payload["tools"] = list(tools)
    if stream:
        payload["stream"] = True
    return payload


class SSEDecoder:
    """增量 SSE 解码器：字节块进，data 载荷出；跨字节块的半行自动缓冲。

    SSE 协议（W3C 事件流）与聊天端点的公共子集：
    - 一个事件 = 若干行 + 空行（\\n\\n）结尾；
    - 我们只关心 data: 开头的行（前缀后可有一个可选空格）；
    - 多行 data 用 \\n 拼接为一个载荷（本端点家族一事件一行，但按规范实现）；
    - [DONE] 是普通 data 载荷，解码器不特判，由调用方决定终止。

    只按 \\n 分行（OpenAI 兼容端点不用 \\r\\n；规范实现需归一化 CRLF，见练习 hints 第 3 级）。
    """

    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, chunk: bytes) -> list[str]:
        """喂入一段网络字节，返回其中完整事件的 data 载荷（UTF-8 解码后的字符串）。"""
        self._buffer += chunk
        payloads: list[str] = []
        while True:
            index = self._buffer.find(b"\n\n")  # 事件以空行收尾；找不到说明事件未到齐
            if index == -1:
                break
            block, self._buffer = self._buffer[:index], self._buffer[index + 2 :]
            data_lines = [line[len(b"data:") :] for line in block.split(b"\n") if line.startswith(b"data:")]
            for i, line in enumerate(data_lines):
                if line.startswith(b" "):  # "data: " 的那个可选空格剥掉
                    data_lines[i] = line[1:]
            if data_lines:
                payloads.append(b"\n".join(data_lines).decode("utf-8"))
        return payloads


@dataclass
class ChatConfig:
    """端点三变量（.env 三行的运行时形态）。"""

    base_url: str
    api_key: str
    model: str

    @classmethod
    def from_env(cls) -> ChatConfig:
        """从环境变量构造；.env 文件已由 load_env() 灌入 os.environ。"""
        load_env()
        missing = [key for key in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "MODEL_NAME") if not os.environ.get(key)]
        if missing:
            raise RuntimeError(
                f"缺少环境变量 {missing}：先 cp .env.example .env 并填写（本课演示可用 mock 端点离线跑）"
            )
        return cls(
            base_url=os.environ["OPENAI_BASE_URL"], api_key=os.environ["OPENAI_API_KEY"], model=os.environ["MODEL_NAME"]
        )


class ChatClient:
    """极简聊天客户端：非流式 complete() + 流式 stream()。"""

    def __init__(self, config: ChatConfig) -> None:
        # AsyncClient ≈ Java 的 HttpClient（一次构建、复用连接池）；Bearer 头对齐端点鉴权约定
        self.model = config.model
        self._http = httpx.AsyncClient(
            base_url=config.base_url,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30.0,
        )

    async def __aenter__(self) -> ChatClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def complete(self, messages: Sequence[dict], tools: Sequence[dict] | None = None) -> dict:
        """非流式：发一轮对话，返回完整响应 JSON（dict）。HTTP 错误码抛 httpx.HTTPStatusError。"""
        response = await self._http.post("/chat/completions", json=build_payload(messages, self.model, tools))
        response.raise_for_status()  # 4xx/5xx 在这里变成异常（L1.7 EAFP 风格）
        return response.json()

    def stream(self, messages: Sequence[dict]) -> AsyncIterator[str]:
        """流式：异步生成器逐段吐出 delta 文本。

        注意形状：方法本身是普通 def，返回一个异步生成器（L1.9 async for 的生产端）。
        本方法不解析流式 tool_calls 分片——讲义明确了这一取舍（工具调用走非流式）。
        """

        async def _events() -> AsyncIterator[str]:
            decoder = SSEDecoder()
            async with self._http.stream(
                "POST", "/chat/completions", json=build_payload(messages, self.model, stream=True)
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():  # 网络字节块，边界不保证对齐任何行
                    for data in decoder.feed(chunk):
                        if data == DONE:
                            return
                        event = json.loads(data)
                        delta = event["choices"][0]["delta"].get("content")
                        if delta:  # 首 chunk 带 role、末 chunk 可能只有 finish_reason——content 为空就跳过
                            yield delta

        return _events()
