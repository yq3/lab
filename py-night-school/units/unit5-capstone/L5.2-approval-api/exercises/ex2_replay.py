# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""SSE 事件流与断线重放：EventLog 的订阅 =「先重放历史，再无缝接实时」（讲义 approvals.EventLog 同构）。

A2「审批是可重放事件」的两条纪律都压在 TODO 上：
- append 的广播半边：新事件要「立刻」送达每个在线订阅者——非阻塞投递（他们各自在等什么？）；
- subscribe：先重放 id > last_id 的历史（新订阅者/断线重连一条不丢），再无缝接实时——
  重放快照与订阅注册之间**不能有缝**（这两个动作之间若 await 了，中间 append 的事件去哪了？），
  消费方不再迭代时要注销（不然队列越积越多、对象泄漏）。

given：snapshot（Last-Event-ID 截断的读表口径）、append 的记账半边（事件表是真相之源）。

完成判据：uv run pytest exercises/test_ex2.py 全绿——4 个测试：
  新订阅者重放全部历史（无人订阅期间的事件一条不丢）；Last-Event-ID 只重放其后；
  重放完无缝接实时（每条恰好一次、顺序与事件表一致、断开注销）；两个并发订阅者同序。
本文件无需新增 import——TODO 用到的都已预置。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator


class EventLog:
    """append-only 事件表 + 订阅器（L5.3 会把它升级成 SQLite 事件溯源，接口不变）。"""

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._subscribers: list[asyncio.Queue[dict]] = []

    def snapshot(self, after_id: int = 0) -> list[dict]:
        """读表（given）：after_id 之后的全部事件——Last-Event-ID 截断的口径。"""
        return [record for record in self._events if record["id"] > after_id]

    def append(self, event: str, data: dict) -> dict:
        """记一条事件（记账半边 given）；广播半边是你的 TODO——返回带 id 的存档记录。"""
        record = {"id": len(self._events) + 1, "event": event, "data": data}
        self._events.append(record)
        # TODO(ex2): 广播——每个在线订阅者怎么「立刻」收到这条？
        #   （问：投递要不要等对方消费？多个订阅者时投给谁？）
        return record

    async def subscribe(self, last_id: int = 0) -> AsyncIterator[dict]:
        """订阅（你的 TODO）：先重放 id > last_id 的历史，再无缝接实时，断开时注销。

        问：重放从哪来（已有 given 的哪个方法）？「重放完」和「开始等新事件」之间
        为什么不能 await？新事件从哪等（谁往里放）？消费方不再迭代时 finally 做什么？
        """
        # TODO(ex2): 重放 + 注册 + 实时 + 注销
        raise NotImplementedError("TODO(ex2): subscribe")
        yield  # 不可达：仅让本函数是异步生成器（作答时整段重写，删掉本行）
