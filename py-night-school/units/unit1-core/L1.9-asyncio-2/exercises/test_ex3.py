"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio
import time

import ex3_token_stream as ex3


def test_ex3_stream_collects_all_chunks() -> None:
    t0 = time.perf_counter()
    sentence, received = asyncio.run(ex3.collect())
    elapsed = time.perf_counter() - t0

    assert sentence == "".join(ex3.CHUNKS)  # 完整句子一段不缺
    assert received == len(ex3.CHUNKS)  # 分段数恰好
    # 逐段节奏：8 段 x 0.02s = 0.16s 是下限——一次性返回做不到这个时长
    assert elapsed >= 0.15
