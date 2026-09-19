# 练习 1 参考答案（solution/ 不进学员主线视野；先完成练习再回来对照）
"""EventStore 补全：append-only 事件表的写（append）与读（events_for）。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVENT_TYPES: frozenset[str] = frozenset(
    {
        "run.started",
        "intake.loaded",
        "plan.approved",
        "plan.rejected",
        "tool.called",
        "llm.decision",
        "advice.drafted",
        "submitted",
        "cost.recorded",
    }
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    aggregate_id TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    type         TEXT NOT NULL,
    payload      TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (aggregate_id, seq)
)
"""


class EventSeqConflict(RuntimeError):
    """同 (aggregate_id, seq) 已有事件——append-only 的乐观并发防线。"""

    def __init__(self, aggregate_id: str, seq: int) -> None:
        self.aggregate_id = aggregate_id
        self.seq = seq
        super().__init__(f"event exists: aggregate={aggregate_id!r} seq={seq}")


def system_clock() -> str:
    """（给定）默认系统 UTC 钟——测试注入固定钟换掉它。"""
    return datetime.now(UTC).isoformat()


class EventStore:
    """append-only 事件表（骨架）：建表/开关连接已给定，写与读是你的 TODO。"""

    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], str] | None = None) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self._clock = clock or system_clock

    @classmethod
    def open(cls, path: str | Path, clock: Callable[[], str] | None = None) -> EventStore:
        """（给定）打开（必要时创建）事件库：建表 + 提交 DDL + Row 工厂。"""
        conn = sqlite3.connect(path)
        conn.execute(SCHEMA)
        conn.commit()
        return cls(conn, clock=clock)

    def append(self, aggregate_id: str, type: str, payload: Any, seq: int | None = None) -> int:
        """追加一条事件，返回它的 seq。"""
        if type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {type!r}（不在 EVENT_TYPES 常量表——fail-closed）")
        with self._conn:  # 事务边界：块内任何一步失败，整个追加回滚
            created_at = self._clock()
            text = json.dumps(payload, ensure_ascii=False)
            if seq is None:
                row = self._conn.execute(
                    "SELECT COALESCE(MAX(seq), -1) + 1 AS next FROM events WHERE aggregate_id = ?",
                    (aggregate_id,),
                ).fetchone()
                seq = int(row["next"])
            try:
                self._conn.execute(
                    "INSERT INTO events (aggregate_id, seq, type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                    (aggregate_id, seq, type, text, created_at),
                )
            except sqlite3.IntegrityError as exc:  # 唯一索引 (aggregate_id, seq) 冲突
                raise EventSeqConflict(aggregate_id, seq) from exc
        return seq

    def events_for(self, aggregate_id: str, type: str | None = None) -> list[dict]:
        """读一个聚合的事件流（seq 升序）；type 给定时按类型过滤；payload 解析回 dict。"""
        if type is None:
            rows = self._conn.execute(
                "SELECT seq, type, payload, created_at FROM events WHERE aggregate_id = ? ORDER BY seq",
                (aggregate_id,),
            )
        else:
            rows = self._conn.execute(
                "SELECT seq, type, payload, created_at FROM events WHERE aggregate_id = ? AND type = ? ORDER BY seq",
                (aggregate_id, type),
            )
        return [
            {
                "seq": row["seq"],
                "type": row["type"],
                "payload": json.loads(row["payload"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def close(self) -> None:
        """（给定）关连接。注意：本类刻意没有 update/delete——append-only 是接口形状。"""
        self._conn.close()

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
