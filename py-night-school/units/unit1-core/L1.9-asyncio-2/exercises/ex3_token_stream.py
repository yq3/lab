# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""异步生成器：mock LLM 按词吐出审批意见，async for 收集完整句子。

考察点：async def + yield 定义异步生成器；async for 消费整条流。
完成判据：uv run pytest exercises/test_ex3.py 全绿——
  句子完整 + 分段数正确 + 逐段节奏（总时长 >= 每段延迟 x 段数）。
提示：函数体里要用到 asyncio.sleep，记得在顶部补 import asyncio。
"""

from collections.abc import AsyncIterator

CHUNK_DELAY = 0.02  # 每段 token 的模拟网络节奏
CHUNKS: list[str] = ["报销单", "CLM-07", "预审", "通过", "，", "金额", "1200", "分"]


async def stream_review() -> AsyncIterator[str]:
    """mock 模型（你来实现）：按 CHUNKS 逐段产出，每段前异步等 CHUNK_DELAY。"""
    # TODO(ex3): for 循环遍历 CHUNKS：每段先 await asyncio.sleep(CHUNK_DELAY)，再 yield 当前段
    raise NotImplementedError("TODO(ex3): 补全 stream_review")


async def collect() -> tuple[str, int]:
    """消费整条流：async for 收集，返回 (完整句子, 分段数)。"""
    # TODO(ex3): async for 消费 stream_review：把每段拼进句子，统计段数，最后一起返回
    raise NotImplementedError("TODO(ex3): 补全 collect")
