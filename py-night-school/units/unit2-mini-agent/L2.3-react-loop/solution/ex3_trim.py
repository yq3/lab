# 参考答案：ex3_trim（练习文件的完整解法——完成前别看）
"""上下文裁剪：预算之内砍最老，孤儿 tool 不许当排头。"""

from __future__ import annotations

import json


def estimate_chars(messages: list[dict]) -> int:
    """给定：每条消息序列化后的字符长度总和（token 的近似标尺）。"""
    return sum(len(json.dumps(message, ensure_ascii=False)) for message in messages)


def trim_messages(messages: list[dict], max_chars: int) -> list[dict]:
    """丢最老的非 system 消息直到字符量 <= max_chars；孤儿 tool 连坐；返回新列表。"""
    trimmed = list(messages)
    while estimate_chars(trimmed) > max_chars and len(trimmed) > 2:
        trimmed.pop(1)  # 永远裁 index 1：index 0 是 system
        while len(trimmed) > 1 and trimmed[1]["role"] == "tool":
            trimmed.pop(1)  # 孤儿 tool 不许当排头（协议会 400）
    return trimmed
