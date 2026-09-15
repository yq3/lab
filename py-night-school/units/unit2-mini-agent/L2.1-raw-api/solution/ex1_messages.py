# 参考答案：ex1_messages（练习文件的完整解法——完成前别看）
"""messages 协议：组装请求与解剖响应。"""

# 响应标本 A：模型直接回答（finish_reason=stop，content 是正文）
RESPONSE_TEXT: dict = {
    "id": "chatcmpl-mock-001",
    "model": "mock-model",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "报销单 CLM-2026-0001 预审通过。"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
}

# 响应标本 B：模型选择工具（finish_reason=tool_calls，content 为 None，选择在 tool_calls 里）
RESPONSE_TOOL_CALLS: dict = {
    "id": "chatcmpl-mock-002",
    "model": "mock-model",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_001",
                        "type": "function",
                        "function": {"name": "preapprove", "arguments": '{"items_cents": [8800]}'},
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 15, "completion_tokens": 6, "total_tokens": 21},
}


def build_messages(system: str, user: str) -> list[dict]:
    """组装两消息请求：system 在前、user 在后（协议对顺序敏感，历史按时间排列）。"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def extract_reply(response: dict) -> tuple[str, str]:
    """从完整响应 dict 中取出 (content, finish_reason)；content 为 None 归一成空串。"""
    choice = response["choices"][0]
    content = choice["message"]["content"]
    return (content if content is not None else "", choice["finish_reason"])
