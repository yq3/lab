# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""上下文裁剪：预算之内砍最老，孤儿 tool 不许当排头。

考察点：while 循环的收敛条件（字符量 <= 预算 且 剩得够少时停）；
system 永远保留；tool 消息与其 assistant(tool_calls) 不许拆散——裁掉 assistant 后，
排头的孤儿 tool 必须连坐裁掉；不修改原列表（返回新列表）。

完成判据：uv run pytest exercises/test_ex3.py 全绿——
  预算内原样返回；超预算裁到线内；system/最新消息保留；排头永不是 tool；原列表不动。
提示：裁剪永远发生在 index 1（index 0 是 system）；estimate_chars 给定。
"""

from __future__ import annotations

import json


def estimate_chars(messages: list[dict]) -> int:
    """给定：每条消息序列化后的字符长度总和（token 的近似标尺）。"""
    return sum(len(json.dumps(message, ensure_ascii=False)) for message in messages)


def trim_messages(messages: list[dict], max_chars: int) -> list[dict]:
    """丢最老的非 system 消息直到字符量 <= max_chars；孤儿 tool 连坐；返回新列表。"""
    # TODO(ex3): 复制列表；while 两条收敛条件；pop(1) 后处理排头孤儿 tool
    raise NotImplementedError("TODO(ex3): 补全 trim_messages")
