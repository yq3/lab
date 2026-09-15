# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""协程对象三归宿实验：调用 async 函数 ≠ 执行——亲手把三个归宿都摸一遍。

考察点：协程对象是「待办单」；await / asyncio.run / close 是它的三个归宿。
完成判据：uv run pytest exercises/test_ex3.py 全绿。
"""

import asyncio


async def review_note(claim_id: str) -> str:
    """模拟审单（给定，不要改）：await 让出 0.05s 后给出结论。"""
    await asyncio.sleep(0.05)
    return f"PASS:{claim_id}"


def demo_fates(claim_id: str) -> dict[str, str]:
    """协程对象的三个归宿，返回观察记录（恰好三个键：type / await / run）。"""
    # TODO(ex3): 依次完成三件事，把观察结果收进返回的 dict：
    # ① "type"：coro = review_note(claim_id) 只创建不执行，
    #    记录 type(coro).__name__；然后 coro.close() 显式关闭（否则有 never awaited 警告）；
    # ② "await"：在 main 里写一个 async def 帮手，在其中 await 一个新的协程对象，
    #    用 asyncio.run 驱动帮手，把 await 拿到的返回值记录下来；
    # ③ "run"：再创建一个新的协程对象，直接 asyncio.run 它，记录返回值。
    raise NotImplementedError("TODO(ex3): 按 ①②③ 补全 demo_fates")
