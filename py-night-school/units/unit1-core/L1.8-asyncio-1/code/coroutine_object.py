"""Step 3：协程对象——调用 async 函数只是「造出一张待办单」，函数体一行都不会跑。

这是 asyncio 新手的第一个困惑点：Java 里调用方法就是执行；Python 里调用协程函数
只是创建协程对象，必须有归宿（await / asyncio.run / close）它才会（或永不）执行。

运行：uv run python code/coroutine_object.py
（第 3 节故意制造 never awaited 警告——看 stderr 的 RuntimeWarning）
"""

import asyncio
import gc


async def review(claim_id: str) -> str:
    """模拟审单：真正执行时才打印这一行。"""
    print(f"    review({claim_id!r}) 的函数体此刻才真正开始执行")
    await asyncio.sleep(0.05)
    return "PASS"


def fire_and_forget() -> None:
    """事故写法：调用 async 函数却不接住返回的协程对象。"""
    # 下一行就是「协程未 await」的事故写法——pyright 的 reportUnusedCoroutine
    # 能静态抓住它（这正是这个坑的便宜保险），讲义故意演示，故在此关闭该检查。
    review("CLM-C")  # pyright: ignore[reportUnusedCoroutine]


def main() -> None:
    print("== 1. 调用 async 函数：只拿到协程对象 ==")
    coro = review("CLM-A")
    print(f"    coro = {coro}")
    print(f"    type(coro).__name__ = {type(coro).__name__}")
    print("    （注意：上面没有出现 review 函数体的输出——它还没执行）")
    coro.close()  # 不打算 await 的协程要显式关闭，否则留下 never awaited 警告

    print("\n== 2. 归宿之一：asyncio.run 直接驱动 ==")
    verdict = asyncio.run(review("CLM-B"))
    print(f"    asyncio.run 的返回值: {verdict}")

    print("\n== 3. 事故现场：造了协程对象却谁也不管 ==")
    fire_and_forget()
    gc.collect()  # 强制回收：被丢弃的协程对象在回收瞬间触发 RuntimeWarning
    print("    （往上翻 stderr：RuntimeWarning: coroutine 'review' was never awaited）")


if __name__ == "__main__":
    main()
