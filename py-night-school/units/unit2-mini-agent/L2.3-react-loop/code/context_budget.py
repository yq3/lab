"""加餐：朴素上下文管理——token 计数（字符近似）与历史裁剪。

为什么要管上下文：无状态协议每次全量重发（L2.1 §2.2），历史越长，每次请求的
token 越贵、越可能超过模型的上下文窗口。生产框架有 tokenizer 精确计数与
checkpoint 裁剪策略；本课用「字符数近似」把问题讲清楚——思路一致，精度让位。

两条纪律：
  1. system（第 1 条）永远保留——人设与纪律丢了，后面的对话全部变形；
  2. 裁剪不许拆散 assistant(tool_calls) 与它的 tool 消息——拆散的孤儿 tool 消息
     会被端点 400 拒收（协议要求 tool 必须紧跟对应的 tool_calls）。
"""

from __future__ import annotations

import json


def estimate_chars(messages: list[dict]) -> int:
    """字符量近似：每条消息序列化后的长度和。中文约 1 字符 ≈ 1 token 量级，够当预算标尺。"""
    return sum(len(json.dumps(message, ensure_ascii=False)) for message in messages)


def trim_messages(messages: list[dict], max_chars: int) -> list[dict]:
    """丢最老的非 system 消息，直到字符量 <= max_chars。

    不修改原列表（返回新列表——历史是审计证据，裁剪只影响「发给模型的视图」）。
    排头若是孤儿 tool 消息（它配对的 assistant 已被裁掉），连它一起丢，
    直到排头不是 tool 为止——纪律 2 的落实。
    """
    trimmed = list(messages)
    while estimate_chars(trimmed) > max_chars and len(trimmed) > 2:
        trimmed.pop(1)  # 永远裁第 2 个位置：index 0 是 system
        while len(trimmed) > 1 and trimmed[1]["role"] == "tool":
            trimmed.pop(1)  # 孤儿 tool 不许当排头
    return trimmed
