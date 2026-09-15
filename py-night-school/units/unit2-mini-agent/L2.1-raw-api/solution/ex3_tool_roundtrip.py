# 参考答案：ex3_tool_roundtrip（练习文件的完整解法——完成前别看）
"""工具调用协议：解析 tool_calls、执行、组装 role=tool 回喂消息。"""

from __future__ import annotations

import json

ITEM_LIMIT_CENTS = 5000
TOTAL_LIMIT_CENTS = 500000

# 标本：模型一次要审两张报销单——并行 tool_calls（真实协议允许，一条消息多个调用）
TOOL_CALL_ASSISTANT: dict = {
    "role": "assistant",
    "content": None,
    "tool_calls": [
        {
            "id": "call_001",
            "type": "function",
            "function": {"name": "preapprove", "arguments": '{"items_cents": [1200, 3500, 2400]}'},
        },
        {
            "id": "call_002",
            "type": "function",
            "function": {"name": "preapprove", "arguments": '{"items_cents": [8800]}'},
        },
    ],
}


def preapprove(items_cents: list[int]) -> str:
    """L0.1 的预审规则原样复刻：脏数据最先挡，再查单笔，再查合计。"""
    if any(cents <= 0 for cents in items_cents):
        return "REJECT:INVALID_AMOUNT"
    if any(cents > ITEM_LIMIT_CENTS for cents in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    if sum(items_cents) > TOTAL_LIMIT_CENTS:
        return "REJECT:TOTAL_OVER_LIMIT"
    return "PASS"


def handle_tool_calls(assistant_message: dict) -> list[dict]:
    """执行全部 tool_calls 并组装 role=tool 回喂消息（不认识的名字跳过——L2.2 换成注册表）。"""
    results: list[dict] = []
    for tool_call in assistant_message["tool_calls"]:
        name = tool_call["function"]["name"]
        if name != "preapprove":
            continue
        arguments = json.loads(tool_call["function"]["arguments"])  # 字符串套娃坑：先拆封
        results.append({"role": "tool", "tool_call_id": tool_call["id"], "content": preapprove(**arguments)})
    return results
