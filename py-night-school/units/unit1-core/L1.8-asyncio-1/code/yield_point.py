"""Step 5：两个 await 之间是原子的——asyncio.sleep(0) 是显式让出。

两个「窗口」各处理三张单据。唯一的多线程感时刻：把 await asyncio.sleep(0)
删掉再跑一遍——输出立刻变成 A 连跑三轮、B 才开张。让出点就是唯一的交错机会。

运行：uv run python code/yield_point.py
"""

import asyncio


async def officer(counter_name: str, rounds: int, log: list[str]) -> None:
    for i in range(1, rounds + 1):
        log.append(f"{counter_name}:{i}")
        print(f"{counter_name} 处理第 {i} 单")
        await asyncio.sleep(0)  # 立即让出：把我排到就绪队列队尾，让别人跑一轮


async def interleave(rounds: int = 3) -> list[str]:
    log: list[str] = []
    await asyncio.gather(officer("窗口A", rounds, log), officer("窗口B", rounds, log))
    return log


def main() -> None:
    log = asyncio.run(interleave())
    print(f"log: {log}")
    print("窗口A 与 窗口B 交替出现——每次 await 都是一次让出机会。")
    print("动手验证原子性：把 await asyncio.sleep(0) 改成 pass 再跑——")
    print("窗口A 会连跑三轮窗口B 才动：两个 await 之间不会被任何人打断。")


if __name__ == "__main__":
    main()
