# 参考答案（ex2）：与骨架的差异只在 append 的广播一行与 subscribe 的实现——其余 given 原样。
"""SSE 事件流与断线重放：EventLog 的订阅 =「先重放历史，再无缝接实时」。

题目与契约见 exercises/ex2_replay.py 的 docstring；本文件是它的参考答案。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator


class EventLog:
    """append-only 事件表 + 订阅器（参考答案）。"""

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._subscribers: list[asyncio.Queue[dict]] = []

    def snapshot(self, after_id: int = 0) -> list[dict]:
        """读表（given）：after_id 之后的全部事件。"""
        return [record for record in self._events if record["id"] > after_id]

    def append(self, event: str, data: dict) -> dict:
        """记一条事件并广播（参考答案）：put_nowait 非阻塞投递——订阅者各自异步消费。"""
        record = {"id": len(self._events) + 1, "event": event, "data": data}
        self._events.append(record)
        for queue in self._subscribers:
            queue.put_nowait(record)
        return record

    async def subscribe(self, last_id: int = 0) -> AsyncIterator[dict]:
        """订阅（参考答案）：重放与登记之间无 await——无缝；断开时 finally 注销。

        顺序契约：登记之前发生的事件只可能来自 snapshot（重放）；登记之后的只可能来自
        广播队列（实时）。两个动作之间没有 await，单线程事件循环里不会有事件插队——
        这就是「不重不漏」的全部机制。
        """
        queue: asyncio.Queue[dict] = asyncio.Queue()
        replay = self.snapshot(last_id)
        self._subscribers.append(queue)
        try:
            for record in replay:
                yield record
            while True:
                record = await queue.get()
                yield record
        finally:
            self._subscribers.remove(queue)
