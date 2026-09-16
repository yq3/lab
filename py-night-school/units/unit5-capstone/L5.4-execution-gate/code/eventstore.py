"""append-only 事件表——事件溯源的最小实现（L5.3 交付，L5.4 登记门事件）。

L5.4 副本声明（对版纪律「合理差异就地注释」）：表结构、append/events_for/fold/replay、
RunRecorder、时钟纪律与 L5.3 字节相同；差异只有两处——
1) EVENT_TYPES 从九类扩到十二类：登记 L5.4 执行门的三个新事件
   gate.checked（每次过门留裁决）/ payment.executed（付款完成——事件表即账本）/
   gate.denied（门未放行：DENY 与 PAUSE 都不付款，payload.action 区分裁决）；
2) fold 的投影多消费上述三类（paid_cents / gate / gate_denied 三个新视图键）——
   事件词汇表是封闭集合，新事件必须显式登记才能进账（append 对表外类型 fail-closed）。

设计出处：research/agent-oss/report.md §2.1 A11（事件溯源会话存储：
event(aggregate_id, seq) + 唯一索引；审批/成本皆一等事件类型；JSONL 只做归档不做主存）。
产品先例：sst/opencode 的 event 表（aggregate_id+seq 唯一索引，见讲义 §6 路标）。

一张表，四个字段，一条铁律：
    events(aggregate_id, seq, type, payload, created_at)  PRIMARY KEY (aggregate_id, seq)
铁律是 append-only：**本类没有 update / 没有 delete 方法**——这不是「暂时没做」，
是接口形状（纪律不是缺功能，讲义区测试有 meta 断言钉住它）。
「不可改」的更重实现是 L4.3 读过的哈希链账本；本课是最小实现，里程碑可再叠。

L5.4 的账本读法：当日已付清单 = 日历聚合 ledger:<date> 上 payment.executed 事件的
投影（graph.PaymentLedger）——事件表即账本，账本不是第二张表。

时钟纪律（对版 L4.3 的 clock 注入）：created_at 来自构造时注入的时钟，默认系统 UTC 钟，
测试与 demo 注入固定钟——两次运行的事件流逐字节可复现。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from advice import Advice

# 事件类型一等（常量表）：会话/run 的生命周期、计划审批、工具执行、模型决策、成本、
# 执行门——每类审计事实一个类型码，append 对表外的类型 fail-closed（ValueError）。
EVENT_TYPES: frozenset[str] = frozenset(
    {
        "run.started",  # 一次管线执行的出生证明（claim_id + 图版本签名）
        "intake.loaded",  # 载单完成（单据视图摘要）
        "plan.approved",  # 校验门放行（计划全文）
        "plan.rejected",  # 校验门拒绝（reason_code + detail）
        "tool.called",  # 工具真实执行（step_id/tool/produces/result）
        "llm.decision",  # 模型决策进缓存层（node + prompt_hash + cached 标记）
        "advice.drafted",  # 建议单产出（含 escalate 哨兵路径）
        "submitted",  # 送审完成
        "cost.recorded",  # 成本事件：每次真实模型调用的 prompt/completion tokens
        "gate.checked",  # 执行门裁决留痕（action/reason_code/detail/clamp——每次过门一条）
        "payment.executed",  # 付款完成（amount_cents→paid_cents；日历聚合上即「当日账本」）
        "gate.denied",  # 门未放行（DENY/PAUSE 都不付款；payload.action 区分裁决三态中的哪一态）
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
    """同 (aggregate_id, seq) 已有事件——唯一索引冲突的语义化翻译。

    append-only 的乐观并发防线：两个写者争同一个序号，后到的响亮失败而不是静默覆盖。
    """

    def __init__(self, aggregate_id: str, seq: int) -> None:
        self.aggregate_id = aggregate_id
        self.seq = seq
        super().__init__(f"event exists: aggregate={aggregate_id!r} seq={seq}")


def system_clock() -> str:
    """默认系统 UTC 钟（ISO 字符串）——测试注入固定钟换掉它。"""
    return datetime.now(UTC).isoformat()


class EventStore:
    """append-only 事件表：只许追加、只许按聚合读取，状态靠 fold 重放。

    连接管理：open(path) 建表并返回实例（上下文管理器用完即关）；
    事务语义：append 内部 `with conn:`——成功 commit、任何失败 rollback
    （L5.3 §5「自动提交错觉」坑位的正面教材：写路径永远不裸 execute 后忘提交）。
    """

    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], str] | None = None) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self._clock = clock or system_clock

    @classmethod
    def open(cls, path: str | Path, clock: Callable[[], str] | None = None) -> EventStore:
        """打开（必要时创建）事件库：建表 + 提交 DDL + Row 工厂。"""
        conn = sqlite3.connect(path)
        conn.execute(SCHEMA)
        conn.commit()
        return cls(conn, clock=clock)

    def append(self, aggregate_id: str, type: str, payload: Any, seq: int | None = None) -> int:
        """追加一条事件，返回它的 seq。

        - type 必须在 EVENT_TYPES 常量表内（表外类型 ValueError——审计词汇表是封闭集合）；
        - seq=None 时自动取「该聚合当前最大 seq + 1」（单写者常态，从 0 起步）；
          显式 seq 用于补写/乐观并发校验——撞唯一索引抛 EventSeqConflict；
        - payload 序列化为 JSON 文本；不可序列化在事务内失败 → 回滚，半个事件都不留。
        """
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
        """读一个聚合的事件流（按 seq 升序）；type 给定时按类型过滤。

        返回 [{"seq", "type", "payload"(已解析的 dict), "created_at"}]——payload 在边界上
        解析回结构化数据，消费方（fold / 审计查询 / 当日账本投影）不接触 JSON 文本。
        """
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

    # 注意：这里没有 update / delete / truncate——append-only 是接口形状（meta 测试在钉）。

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@contextmanager
def connect(path: str | Path, clock: Callable[[], str] | None = None):
    """上下文管理器版打开：`with connect(path) as store:`——连接生命周期收拢一处。

    注意与 `with conn:` 的分工（L5.3 §5 坑位）：本 with 管「开/关连接」，
    append 内部的 `with self._conn:` 才管「提交/回滚事务」——两个 with，两件事。
    """
    store = EventStore.open(path, clock=clock)
    try:
        yield store
    finally:
        store.close()


class RunRecorder:
    """轻量事件记录器：绑定 (store, aggregate_id)——节点只说「发生了什么」。

    「往哪写、以谁的名义写」收拢在这一个对象里（对照 Java 的 AOP 审计切面，
    只是这里是显式传参而非注解魔法——静态图里审计点在装配代码上看得见）。
    """

    def __init__(self, store: EventStore, aggregate_id: str) -> None:
        self._store = store
        self._aggregate_id = aggregate_id

    def emit(self, type: str, payload: Any) -> None:
        self._store.append(self._aggregate_id, type, payload)


# ---- 重放：事件表是唯一真相源，状态是投影 ----


def fold(rows: list[dict], view: dict | None = None) -> dict:
    """把事件序列重放成当前视图：results 聚合、advice 终值、拒绝轨迹、成本累计、门的账。

    每个 superstep 的事实先后到达，fold 只做「按序归约」——它不取时钟、不碰网络、
    不读表（输入就是 events_for 的返回），所以同一串事件永远 fold 出同一个视图。
    未被投影消费的类型（run.started 之外的元信息）进 view["events"] 留痕。
    L5.4 新增三个视图键：paid_cents（实付）、gate（最后一次过门裁决）、gate_denied（未放行原因）。
    """
    projection: dict = {
        "events": [],
        "graph_version": None,
        "results": {},
        "plan_rejections": [],
        "advice": None,
        "sent": False,
        "cost": {"prompt_tokens": 0, "completion_tokens": 0},
        "paid_cents": None,
        "gate": None,
        "gate_denied": None,
    }
    if view is not None:
        projection.update(view)
    for row in rows:
        event_type = row["type"]
        payload = row["payload"]
        projection["events"].append(event_type)
        if event_type == "run.started":
            projection["graph_version"] = payload.get("graph_version")
        elif event_type == "tool.called":
            projection["results"][payload["produces"]] = payload["result"]
        elif event_type == "plan.rejected":
            projection["plan_rejections"].append({"reason_code": payload["reason_code"], "detail": payload["detail"]})
        elif event_type == "advice.drafted":
            projection["advice"] = Advice.model_validate(payload)
        elif event_type == "submitted":
            projection["sent"] = True
        elif event_type == "cost.recorded":
            projection["cost"]["prompt_tokens"] += int(payload.get("prompt_tokens", 0))
            projection["cost"]["completion_tokens"] += int(payload.get("completion_tokens", 0))
        elif event_type == "gate.checked":
            projection["gate"] = {"action": payload.get("action"), "reason_code": payload.get("reason_code")}
        elif event_type == "payment.executed":
            projection["paid_cents"] = int(payload.get("paid_cents", 0))
        elif event_type == "gate.denied":
            projection["gate_denied"] = {"action": payload.get("action"), "reason_code": payload.get("reason_code")}
    return projection


def replay(store: EventStore, aggregate_id: str) -> dict:
    """重放一个聚合：读事件流 → fold 成当前视图（state 的「投影」读法）。"""
    return fold(store.events_for(aggregate_id))
