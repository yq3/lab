# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""手撕 SSE：从网络字节块到 delta 文本。

考察点：bytes 与 str 的边界（网络来的是 bytes，UTF-8 解码只能在完整事件上做）；
跨块缓冲（TCP 不保证块边界对齐任何行——「报」字的 3 个字节可能分两块到达）；
SSE 事件的空行分隔与 [DONE] 哨兵。这是本课的硬核题。

完成判据：uv run pytest exercises/test_ex2.py 全绿——
  三个字节块（含半个中文字符、半个 JSON 事件）解出 3 个事件；
  delta 文本拼接完整。
提示：先在纸上写出缓冲区状态怎么变，再动手；str 拼接用列表收集再 join（L1.4 讲过为什么）。
"""

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
    """增量 SSE 解析：逐块吃 bytes，逐个吐出完整事件的 data 载荷字符串。

    规则：事件以空行（\\n\\n）收尾；只取 data: 开头的行（前缀后的一个可选空格剥掉）；
    [DONE] 也是普通 data 载荷，照常吐出（终止由调用方决定）；
    不完整的尾部留在缓冲区等下一块。
    """
    # TODO(ex2): 维护一个 bytes 缓冲区；循环找 \\n\\n；切出完整块、提取 data 行、解码返回
    raise NotImplementedError("TODO(ex2): 补全 iter_sse_data")


def collect_content(data_events: Iterable[str]) -> str:
    """把 data 载荷流拼成完整文本：逐个 json.loads，取 delta.content；[DONE] 与空 delta 跳过。"""
    # TODO(ex2): 收集每段 delta 文本并拼接（注意 [DONE] 不是 JSON，先判等再解析）
    raise NotImplementedError("TODO(ex2): 补全 collect_content")
