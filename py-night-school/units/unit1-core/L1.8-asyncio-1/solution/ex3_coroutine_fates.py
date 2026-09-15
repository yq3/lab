"""参考答案（ex3）——先完成练习再看。

三个归宿各用一个新造的协程对象：协程对象是一次性的，close / run 之后即报废。
"""

import asyncio


async def review_note(claim_id: str) -> str:
    await asyncio.sleep(0.05)
    return f"PASS:{claim_id}"


def demo_fates(claim_id: str) -> dict[str, str]:
    observed: dict[str, str] = {}

    # 归宿 0（对照）：只创建——函数体不执行，拿到的是协程对象
    coro = review_note(claim_id)
    observed["type"] = type(coro).__name__
    coro.close()  # 不打算 await 的协程，显式关闭是礼貌归宿

    # 归宿一：被 await——await 只能出现在 async 函数里，所以需要一个帮手
    async def await_once() -> str:
        return await review_note(claim_id)

    observed["await"] = asyncio.run(await_once())

    # 归宿二：被 asyncio.run 直接驱动
    observed["run"] = asyncio.run(review_note(claim_id))
    return observed
