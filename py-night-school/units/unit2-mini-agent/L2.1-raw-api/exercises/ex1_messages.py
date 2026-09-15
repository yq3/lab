# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""messages 协议：组装请求与解剖响应。

考察点：messages 列表的角色结构；响应 JSON 的 dict 导航（choices[0].message / finish_reason）；
content 为 None 的处理（模型选工具时不写正文——这不是异常，是协议的两种正常形态）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——
  请求组装结构逐键相等；两种响应的 (content, finish_reason) 都取对。
提示：导航多层 dict 时先在 REPL 里把整个响应打印出来看一眼，比盲猜快。
"""

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
    # TODO(ex1): 返回形如 [{"role": "system", "content": ...}, {"role": "user", "content": ...}] 的列表
    raise NotImplementedError("TODO(ex1): 补全 build_messages")


def extract_reply(response: dict) -> tuple[str, str]:
    """从完整响应 dict 中取出 (content, finish_reason)。

    导航路径 choices[0].message.content 与 choices[0].finish_reason；
    content 为 None 时返回空字符串（后续拼接历史时 None 会让 str 操作炸）。
    """
    # TODO(ex1): 完成导航与 None 归一化，返回二元组
    raise NotImplementedError("TODO(ex1): 补全 extract_reply")
