"""Step1 挂起的两种形态：内存门闩 vs 落盘暂停（零 API、零模型、零数据库）。

本课的「审批外化」= 图在 submit 暂停 + REST/SSE 在外面转。暂停的语义分两层，先用
最小可跑实验把「内存挂起」那一层看清（Java 对照 CountDownLatch / CompletableFuture），
再把「落盘暂停」那一层对回 L3.3 的 interrupt——它俩长得像，机制完全不同。

四段实验：
[1] asyncio.Event：两个等待者并发挂起、一次 set 全醒——耗时 ≈ 单个等待时长（并发证据）；
[2] 挂起不占线程：等待者挂住的同时，同一个事件循环还在跑别的任务（heartbeat）；
[3] 反例：threading.Event.wait() 冒充挂起——阻塞调用冻结整个循环（§5 坑位的内核预告）；
[4] 对照表：内存门闩 vs interrupt+checkpoint（L3.3 的抛-捕-落盘，本课的产品化内核）。
"""

from __future__ import annotations

import asyncio
import threading
import time

WAIT_SECONDS = 0.2  # 门闩打开前等待者要挂多久（实验计时基准）
BLOCK_SECONDS = 0.15  # [3] 阻塞等待的时长（错开 0.05 的心跳节奏，让「冻结」一眼可见）


async def _waiter(name: str, gate: asyncio.Event, traces: list[str]) -> None:
    """等待者：挂在 gate 上直到被 set——挂起期间零 CPU（协作式让出）。"""
    traces.append(f"{name} 挂起")
    await gate.wait()
    traces.append(f"{name} 醒来")


async def _gatekeeper(gate: asyncio.Event, delay: float) -> None:
    """守门人：delay 秒后打开门闩（对照 latch.countDown()）。"""
    await asyncio.sleep(delay)
    gate.set()


async def _heartbeat(traces: list[str], ticks: int) -> None:
    """心跳任务：证明等待者挂住时循环没死——别的事照跑。"""
    for i in range(1, ticks + 1):
        await asyncio.sleep(0.05)
        traces.append(f"loop alive: tick {i}")


async def _blocked_waiter(traces: list[str]) -> None:
    """错误示范：在 async 里用阻塞的 threading.Event.wait 冒充挂起——等待期间循环冻结。"""
    traces.append("waiter-D 阻塞 wait(0.15)")
    threading.Event().wait(BLOCK_SECONDS)  # 阻塞调用：整个事件循环停摆 0.15s
    traces.append("waiter-D 返回")


def _print_contrast() -> None:
    print("[4] 对照表：内存门闩 vs interrupt+checkpoint（本课审批的内核）")
    rows = [
        ("挂起时占什么", "一个等待点（await）", "一个 checkpoint 行（db 落盘）"),
        ("谁来唤醒", "set() 的任务（同进程）", "Command(resume=)（任意进程，取货凭证 thread_id）"),
        ("进程死了怎样", "等待点蒸发，没有然后", "暂停点还在 db 里，新进程接着跑"),
        ("Java 最近似物", "CountDownLatch / CompletableFuture", "DeferredResult 逾期作废 vs 状态可恢复"),
    ]
    for left, mid, right in rows:
        print(f"  {left:<10} | 内存门闩：{mid}")
        print(f"  {'':<10} | 落盘暂停：{right}")
    print("  <- L3.3 的结论今晚产品化：审批等待的不是线程，是 db 里那行 checkpoint")


async def main() -> None:
    print("== Step1 挂起的两种形态：内存门闩 vs 落盘暂停（零 API） ==")

    print("[1] asyncio.Event：两个等待者并发挂起，一次 set 全醒（对照 CountDownLatch）")
    gate = asyncio.Event()
    traces: list[str] = []
    start = time.perf_counter()
    await asyncio.gather(
        _waiter("waiter-A", gate, traces),
        _waiter("waiter-B", gate, traces),
        _gatekeeper(gate, WAIT_SECONDS),
    )
    elapsed = time.perf_counter() - start
    print(f"  两个等待者 × {WAIT_SECONDS}s 门闩 → 总耗时 {elapsed:.3f}s")
    print(f"  轨迹: {traces}")
    print("  <- 串行等待应 ≈ 2× 门闩时长；实测 ≈ 1×：等待是并发的，set 一次全醒")

    print("[2] 挂起不占线程：等待者挂住的同时，同一个循环还在跑别的任务")
    gate2 = asyncio.Event()
    traces2: list[str] = []
    start2 = time.perf_counter()
    await asyncio.gather(_waiter("waiter-C", gate2, traces2), _gatekeeper(gate2, WAIT_SECONDS), _heartbeat(traces2, 3))
    elapsed2 = time.perf_counter() - start2
    print(f"  总耗时 {elapsed2:.3f}s")
    print(f"  轨迹: {traces2}")
    print("  <- waiter-C 挂着不动的那 0.2s 里，heartbeat 打了 3 个点：等待者让出的是循环，不是线程")

    print("[3] 反例：threading.Event.wait() 在 async 里冒充挂起——冻结整个循环")
    traces3: list[str] = []
    start3 = time.perf_counter()
    await asyncio.gather(_blocked_waiter(traces3), _heartbeat(traces3, 3))
    elapsed3 = time.perf_counter() - start3
    print(f"  总耗时 {elapsed3:.3f}s（正确写法应 ≈ {max(BLOCK_SECONDS, 3 * 0.05):.2f}s）")
    print(f"  轨迹: {traces3}")
    print("  <- 阻塞 wait 期间一个心跳点都没有：循环被冻住了——§5 坑位的内核")

    _print_contrast()


if __name__ == "__main__":
    asyncio.run(main())
