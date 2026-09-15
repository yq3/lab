# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体与所需的顶部 import，其余不要动）
"""工具调用协议：解析 tool_calls、执行、组装 role=tool 回喂消息。

考察点：arguments 是「JSON 字符串」不是 dict（§5 坑位的主角，这里亲手拆一次雷）；
一条 assistant 消息可以并行携带多个 tool_calls（每个都要回喂，id 一一对应）；
role=tool 消息的三要素：role / tool_call_id / content。

完成判据：uv run pytest exercises/test_ex3.py 全绿——
  preapprove 四态规则正确；两条 tool 消息顺序、id、结果全对。
提示：** 解包（L1.4）可以让 preapprove(**arguments) 直接吃字典；
解析 arguments 要用 json，记得在顶部补 import json。
"""

from __future__ import annotations

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
    """L0.1 的预审规则原样复刻（warm-up）：按优先级返回四态结论。

    1. 任意金额 <= 0 -> "REJECT:INVALID_AMOUNT"
    2. 任意单笔 > ITEM_LIMIT_CENTS -> "REJECT:ITEM_OVER_LIMIT"
    3. 合计 > TOTAL_LIMIT_CENTS -> "REJECT:TOTAL_OVER_LIMIT"
    4. 否则 -> "PASS"
    """
    # TODO(ex3): 四条规则按优先级实现（先自己默写，再翻 L0.1 对照）
    raise NotImplementedError("TODO(ex3): 补全 preapprove")


def handle_tool_calls(assistant_message: dict) -> list[dict]:
    """执行一条 assistant 消息里的全部 tool_calls，返回要追加进历史的 role=tool 消息列表。

    对每个 tool_call：json.loads 它的 function.arguments（字符串！）→ 用 ** 解包调用 preapprove
    → 组装 {"role": "tool", "tool_call_id": <原 id>, "content": <结果字符串>}；
    多个调用按出现顺序输出。本函数只认 preapprove，别的名字直接跳过（真实注册表在 L2.2）。
    """
    # TODO(ex3): 遍历 tool_calls → 解析 arguments → 执行 → 组装回喂消息
    raise NotImplementedError("TODO(ex3): 补全 handle_tool_calls")
