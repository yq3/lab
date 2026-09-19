# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""EventStore 补全：append-only 事件表的写（append）与读（events_for）。

考察点：append 的事务三件套（常量表校验 / JSON 序列化 / 唯一索引冲突翻译）+
seq 自动分配；events_for 的参数化查询与按类型过滤。讲义 code/eventstore.py 是
同构完整版（对版参照），先自己写，全绿后再去对照读。

验收口径（与 hints 同源）：
- 顺序追加 seq 0..n（自动分配），事件流按 seq 升序、payload 已解析回 dict；
- 同 (aggregate, seq) 二次追加抛 EventSeqConflict，冲突者不留半个事件；
- 跨 aggregate 隔离：A 的流不含 B 的事件，seq 各自从 0 起步；
- 事务回滚：注入一次失败（payload 不可 JSON 序列化），半个事件都不留、seq 不烧；
- 时钟注入：固定钟下两次运行 created_at 逐字节可复现；
- 按类型过滤；EVENT_TYPES 之外的类型 fail-closed（ValueError，**报错消息里要含「EVENT_TYPES」
  字样**——把合法词汇表名写进报错是运维排错刚需，验收断言会认它）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——8 个测试。
TODO 所需的顶部 import：
  import json
"""

from __future__ import annotations

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
        """追加一条事件，返回它的 seq。

        步骤（讲义 §3 Step1 的 JDBC 对照）：常量表校验（表外类型 ValueError）→
        事务内：取时钟 → payload 序列化（不可序列化即失败回滚）→ seq 自动分配
        （该聚合当前最大 seq + 1；显式 seq 时不分配）→ INSERT（撞唯一索引翻译成
        EventSeqConflict）→ 返回 seq。
        """
        # TODO(ex1): 问：type 不在 EVENT_TYPES 时抛什么（放在事务里还是事务外——先校验还是先开门）？
        #   `with self._conn:` 的事务块里要做哪几件事、顺序是什么（哪一步天然是失败点）？
        #   seq=None 时「当前最大 seq + 1」用哪条 SQL 取（聚合无关的行怎么排除）？
        #   INSERT 撞 PRIMARY KEY 时 sqlite 抛什么异常、怎么翻译成 EventSeqConflict（from 链别丢）？
        raise NotImplementedError("TODO(ex1): append")

    def events_for(self, aggregate_id: str, type: str | None = None) -> list[dict]:
        """读一个聚合的事件流（seq 升序）；type 给定时按类型过滤；payload 解析回 dict。"""
        # TODO(ex1): 问：两种形状（带/不带 type 过滤）的 WHERE 子句各长什么样——
        #   过滤值怎么进 SQL 才不是字符串拼接（对照讲义 §3 Step1 的注入对照）？
        #   排序用哪个字段？Row 的四列（seq/type/payload/created_at）怎么组装成
        #   payload 已解析的 dict（哪列需要 json 处理）？
        raise NotImplementedError("TODO(ex1): events_for")

    def close(self) -> None:
        """（给定）关连接。注意：本类刻意没有 update/delete——append-only 是接口形状。"""
        self._conn.close()

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
