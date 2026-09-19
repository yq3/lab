"""Step4 翻开 checkpoint：暂停那一刻，db 里到底躺了什么。

先跑 start 侧把 CLM-2026-0003 打到人审门暂停，然后三层观察：
1. StateSnapshot（graph.aget_state）：next（下一步是谁）、tasks（待执行的活）、
   interrupts（interrupt() 的 payload）、metadata（source/step）、values（全量状态）；
2. get_state_history：这条 thread 的全部快照，从 step=-1（input）到暂停点——
   每个「循环快照」对应一个 superstep 的完成，next 就是那一拍要跑的节点；
3. 直接 sqlite 查表（sqlite3 标准库）：checkpoints 表（每快照一行的 BLOB）与
   writes 表（挂起的写入——暂停点的 __interrupt__ 行就在这里，channel 列是明文）。

源码对应：CheckPoint 结构定义在 langgraph.checkpoint.base（讲义 §6 路标）。
"""

from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path

import demo
import review_rules
from mock_endpoint import MockLLMEndpoint


async def pause_claim(db: str) -> str:
    """start 侧：把 0003 打到人审门暂停，返回 thread_id。"""
    thread = "inside-demo"
    cfg = demo.thread_config(thread)
    first_turn, advice_json, _expected = review_rules.script_for("CLM-2026-0003")
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        async with demo.open_saver(db) as saver:
            graph = demo.build_graph(demo.model_for_url(ep.url), checkpointer=saver)
            await graph.ainvoke({"messages": demo.initial_messages("CLM-2026-0003")}, cfg)
    return thread


async def main() -> None:
    print("== Step4 翻开 checkpoint：暂停点长什么样 ==")
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "inside.sqlite3")
        thread = await pause_claim(db)
        cfg = demo.thread_config(thread)

        print("[1] StateSnapshot（aget_state——不跑图，纯读）")
        async with demo.open_saver(db) as saver:
            graph = demo.build_graph(demo.model_for_url("http://127.0.0.1:1"), checkpointer=saver)
            snapshot = await graph.aget_state(cfg)
            print(f"  next        = {snapshot.next}   <- 恢复后第一个要执行的节点")
            print(f"  interrupts  = {[i.value for i in snapshot.interrupts]}")
            print(f"  tasks       = {[(t.name, t.interrupts) for t in snapshot.tasks]}")
            print(f"  metadata    = {snapshot.metadata}   <- source=loop：循环里存的；step=superstep 计数")
            print(f"  values keys = {sorted(snapshot.values)}   <- events 已有 3 条：reviewer/tools/reviewer")
            print(f"  created_at  = {snapshot.created_at}")
            print("\n[2] get_state_history（新→旧迭代，这里反转为旧→新）")
            history = [snap async for snap in graph.aget_state_history(cfg)]
            for snap in reversed(history):
                meta = snap.metadata or {}
                print(f"  step={meta.get('step'):>2} source={meta.get('source'):<5} next={snap.next}")

        print("\n[3] 直接查 sqlite（两个进程之外，第三个读者）")
        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT checkpoint_id, thread_id FROM checkpoints ORDER BY rowid").fetchall()
        print(f"  checkpoints 表 {len(rows)} 行（每个快照一行的 BLOB，含 channel_values 整只状态）")
        writes = conn.execute("SELECT task_id, channel, type FROM writes ORDER BY rowid").fetchall()
        print(f"  writes 表 {len(writes)} 行（任务执行后的写入都落在账上；暂停的秘密在最后一行）：")
        for task_id, channel, type_ in writes:
            print(f"    channel={channel!r:<16} type={type_!r:<8} task={task_id[:8]}…")
        conn.close()
        print("  <- channel='__interrupt__' 的那行就是 interrupt() 的 payload；")
        print("     恢复时 Command(resume=...) 会在这里追加 channel='__resume__' 的行（源码 _loop.py）")


if __name__ == "__main__":
    asyncio.run(main())
