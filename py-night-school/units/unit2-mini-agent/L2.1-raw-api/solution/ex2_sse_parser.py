# 参考答案：ex2_sse_parser（练习文件的完整解法——完成前别看）
"""手撕 SSE：从网络字节块到 delta 文本。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator

_HEAD = b'data: {"choices": [{"delta": {"content": "'


def _event(content: str) -> bytes:
    """把一段 delta 文本编码成一个完整的 SSE 事件字节串（与真实端点的形状一致）。"""
    payload = json.dumps({"choices": [{"delta": {"content": content}}]}, ensure_ascii=False)
    return b"data: " + payload.encode("utf-8") + b"\n\n"


_RAW_STREAM = _event("报销单") + _event("通过") + b"data: [DONE]\n\n"

# 网络切片：故意切在两处「最坏位置」——
# 第 1 刀落在「报」字 UTF-8 三字节（E6 8A A5）的中间；第 2 刀落在第二个事件的 JSON 中间
CHUNKS: list[bytes] = [
    _RAW_STREAM[: len(_HEAD) + 2],
    _RAW_STREAM[len(_HEAD) + 2 : len(_event("报销单")) + 12],
    _RAW_STREAM[len(_event("报销单")) + 12 :],
]


def iter_sse_data(chunks: Iterable[bytes]) -> Iterator[str]:
    """增量 SSE 解析：逐块吃 bytes，逐个吐出完整事件的 data 载荷字符串（生成器版）。"""
    buffer = b""
    for chunk in chunks:
        buffer += chunk
        while True:
            index = buffer.find(b"\n\n")
            if index == -1:
                break
            block, buffer = buffer[:index], buffer[index + 2 :]
            data_lines = [line[5:] for line in block.split(b"\n") if line.startswith(b"data:")]
            data_lines = [line[1:] if line.startswith(b" ") else line for line in data_lines]
            if data_lines:
                yield b"\n".join(data_lines).decode("utf-8")


def collect_content(data_events: Iterable[str]) -> str:
    """把 data 载荷流拼成完整文本：逐个 json.loads，取 delta.content；[DONE] 与空 delta 跳过。"""
    parts: list[str] = []
    for data in data_events:
        if data == "[DONE]":
            continue
        content = json.loads(data)["choices"][0]["delta"].get("content")
        if content:
            parts.append(content)
    return "".join(parts)
