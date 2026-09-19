"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

import demo
import ex1_memory as ex1


def test_second_segment_sees_history(tmp_path) -> None:  # noqa: ANN001 -- pytest fixture
    db = str(tmp_path / "mem.sqlite3")
    model = ex1.CountingChat()
    asyncio.run(ex1.first_segment(db, "mem-main", model))
    seen_before = len(model.seen)
    asyncio.run(ex1.second_segment(db, "mem-main", "mem-other", model))
    assert model.seen[:seen_before] == [1]  # 第一段：只有 1 条 user
    assert model.seen[seen_before] == 3  # 第二段：第一段的 user+回声 + 新问题——记忆来自 db


def test_other_thread_is_fresh(tmp_path) -> None:  # noqa: ANN001
    db = str(tmp_path / "mem.sqlite3")
    model = ex1.CountingChat()
    asyncio.run(ex1.first_segment(db, "mem-main", model))
    asyncio.run(ex1.second_segment(db, "mem-main", "mem-other", model))
    assert model.seen == [1, 3, 1]  # 第三次是另一个 thread：从零开始，看不到前两段


def test_final_state_keeps_both_segments(tmp_path) -> None:  # noqa: ANN001
    db = str(tmp_path / "mem.sqlite3")
    model = ex1.CountingChat()
    asyncio.run(ex1.first_segment(db, "mem-main", model))
    asyncio.run(ex1.second_segment(db, "mem-main", "mem-other", model))

    async def read(thread_id: str) -> int:
        async with demo.open_saver(db) as saver:
            graph = ex1.build_chat(ex1.CountingChat()).compile(checkpointer=saver)
            snapshot = await graph.aget_state(demo.thread_config(thread_id))
        return len(snapshot.values["messages"])

    assert asyncio.run(read("mem-main")) == 4  # 两问两答：追问也有自己的回声
    assert asyncio.run(read("mem-other")) == 2  # 独立会话：一问一答，与主 thread 互不可见
