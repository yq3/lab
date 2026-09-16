"""本地 mock 端点——夜校的「协议级测试替身」（Java 同学可以理解为 WireMock / MockWebServer）。

给定基础设施（不要改）：在 127.0.0.1 上起一个真的 HTTP 服务，按脚本回放响应。
它让「裸调 LLM API」的全部代码离线可跑、离线验收——你的 client 面对的是与真实端点
相同的 HTTP 状态码、JSON 结构与 SSE 字节流，不需要 API key，不需要网络。

它还会记录收到的每个请求体（ep.requests），供演示打印与测试断言。

用法（上下文管理器，用完自动关）：
    with MockLLMEndpoint() as ep:
        ep.script_text("你好")
        async with ChatClient(ChatConfig(ep.url, "test-key", "mock-model")) as client:
            response = await client.complete(messages)
"""

from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DONE = "[DONE]"


def _sse_bytes(fragments: list[str]) -> bytes:
    """把若干 delta 文本片段编码成一段 SSE 字节流（data: 行 + 空行分隔 + [DONE] 哨兵）。"""
    lines: list[bytes] = []
    for i, fragment in enumerate(fragments):
        delta = {"role": "assistant", "content": fragment} if i == 0 else {"content": fragment}
        finish_reason = "stop" if i == len(fragments) - 1 else None
        event = {
            "id": "chatcmpl-mock-stream",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        lines.append(b"data: " + json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n\n")
    lines.append(b"data: " + DONE.encode("utf-8") + b"\n\n")
    return b"".join(lines)


class MockLLMEndpoint:
    """脚本化的 /v1/chat/completions 端点：script_* 入队，HTTP 请求出队。"""

    def __init__(self, api_key: str = "test-key", model: str = "mock-model") -> None:
        self.api_key = api_key
        self.model = model
        self.url = ""  # start() 后可用，形如 http://127.0.0.1:<port>/v1
        self.requests: list[dict] = []  # 收到的请求体（演示与测试取证用）
        self._scripts: queue.Queue[dict] = queue.Queue()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ---- 脚本编排：每次 HTTP 请求消费一条 ----

    def script_text(self, text: str) -> None:
        """下一次请求回放：非流式文本回答（finish_reason=stop）。"""
        self._scripts.put({"kind": "text", "text": text})

    def script_stream(self, fragments: list[str]) -> None:
        """下一次请求回放：SSE 流式文本，每个 fragment 一个 delta 事件。"""
        self._scripts.put({"kind": "stream", "fragments": fragments})

    def script_tool_calls(self, calls: list[dict]) -> None:
        """下一次请求回放：模型选择工具（finish_reason=tool_calls）。

        calls 形如 [{"id": "call_001", "name": "preapprove", "arguments": {"items_cents": [8800]}}]，
        arguments 会被编码成 JSON 字符串——与真实端点一致（这是 L2.1 §5 坑位的原型）。
        仅支持非流式：真实端点的流式 tool_calls 是分片拼装的，本课明确不做（讲义有说明）。
        """
        self._scripts.put({"kind": "tool_calls", "calls": calls})

    def script_error(self, status: int, message: str) -> None:
        """下一次请求回放：HTTP 错误（如 401），body 为 OpenAI 风格 error JSON。"""
        self._scripts.put({"kind": "error", "status": status, "message": message})

    # ---- 生命周期 ----

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 —— http.server 的约定方法名
                if self.path != "/v1/chat/completions":
                    self._reply_json(404, {"error": {"message": f"unknown path {self.path}"}})
                    return
                auth = self.headers.get("Authorization", "")
                if auth != f"Bearer {outer.api_key}":
                    self._reply_json(401, {"error": {"message": "Invalid API key"}})
                    return
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if body.get("model") != outer.model:
                    self._reply_json(400, {"error": {"message": f"model {body.get('model')!r} not found"}})
                    return
                outer.requests.append(body)
                try:
                    script = outer._scripts.get_nowait()
                except queue.Empty:
                    self._reply_json(500, {"error": {"message": "no script; call script_* before requesting"}})
                    return
                self._dispatch(script, stream=bool(body.get("stream")))

            def _dispatch(self, script: dict, stream: bool) -> None:
                if script["kind"] == "error":
                    self._reply_json(script["status"], {"error": {"message": script["message"]}})
                elif script["kind"] == "stream":
                    # stream 脚本一律按 SSE 回放（无论请求是否带 stream）——教学取舍，见 docstring
                    del stream
                    data = _sse_bytes(script["fragments"])
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(data)
                    self.wfile.flush()
                elif script["kind"] == "tool_calls":
                    tool_calls = [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                            },
                        }
                        for call in script["calls"]
                    ]
                    message = {"role": "assistant", "content": None, "tool_calls": tool_calls}
                    self._reply_json(200, self._completion(message, "tool_calls"))
                else:
                    self._reply_json(200, self._completion({"role": "assistant", "content": script["text"]}, "stop"))

            def _completion(self, message: dict, finish_reason: str) -> dict:
                return {
                    "id": "chatcmpl-mock-001",
                    "object": "chat.completion",
                    "created": 1758000000,
                    "model": outer.model,
                    "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
                }

            def _reply_json(self, status: int, payload: dict) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: object) -> None:  # 静音默认访问日志，保持演示输出干净
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        host, port = self._server.server_address[:2]
        self.url = f"http://{host}:{port}/v1"

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None

    def __enter__(self) -> MockLLMEndpoint:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
