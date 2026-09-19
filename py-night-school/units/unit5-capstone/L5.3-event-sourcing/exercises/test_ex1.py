"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import pytest

from ex1_store import EVENT_TYPES, EventSeqConflict, EventStore


def test_sequential_appends_assign_seq_zero_to_n(tmp_path) -> None:
    """顺序追加：seq 自动 0..n，按 seq 升序、payload 已解析、created_at 来自注入钟。"""
    moments = ["2026-09-16T21:00:00+00:00", "2026-09-16T21:00:01+00:00", "2026-09-16T21:00:02+00:00"]
    clock = iter(moments)
    with EventStore.open(tmp_path / "e.db", clock=lambda: next(clock)) as store:
        seqs = [store.append("run:1", "run.started", {"claim_id": "C1"}) for _ in range(3)]
        assert seqs == [0, 1, 2]
        rows = store.events_for("run:1")
        assert [r["seq"] for r in rows] == [0, 1, 2]
        assert rows[0]["type"] == "run.started"
        assert rows[0]["payload"] == {"claim_id": "C1"}  # 边界上已解析回 dict
        assert rows[0]["created_at"] == moments[0]


def test_same_seq_second_append_raises_conflict(tmp_path) -> None:
    """同 (aggregate, seq) 二次追加 → EventSeqConflict；冲突者不留半个事件（表状态不变）。"""
    with EventStore.open(tmp_path / "e.db", clock=lambda: "t") as store:
        store.append("run:1", "run.started", {"i": 1}, seq=0)
        with pytest.raises(EventSeqConflict) as excinfo:
            store.append("run:1", "advice.drafted", {"i": 2}, seq=0)
        assert excinfo.value.seq == 0
        rows = store.events_for("run:1")
        assert len(rows) == 1 and rows[0]["payload"] == {"i": 1}


def test_aggregates_are_isolated(tmp_path) -> None:
    """跨聚合隔离：A 的流不含 B 的事件；seq 各自从 0 起步（唯一索引按聚合分区）。"""
    with EventStore.open(tmp_path / "e.db", clock=lambda: "t") as store:
        store.append("run:A", "run.started", {})
        store.append("run:B", "run.started", {})
        store.append("run:B", "submitted", {})
        assert [r["type"] for r in store.events_for("run:A")] == ["run.started"]
        assert [r["type"] for r in store.events_for("run:B")] == ["run.started", "submitted"]
        assert [r["seq"] for r in store.events_for("run:B")] == [0, 1]


def test_failed_append_leaves_nothing_and_burns_no_seq(tmp_path) -> None:
    """事务回滚：注入一次失败（payload 不可 JSON 序列化）——半个事件不留、seq 不烧。"""
    with EventStore.open(tmp_path / "e.db", clock=lambda: "t") as store:
        store.append("run:1", "run.started", {"a": 1})
        store.append("run:1", "intake.loaded", {"b": 2})
        with pytest.raises(TypeError):  # set 不可 JSON 序列化——注入的失败点
            store.append("run:1", "tool.called", {"oops": {1, 2}})
        assert [r["seq"] for r in store.events_for("run:1")] == [0, 1]  # 失败者没落库
        assert store.append("run:1", "submitted", {}) == 2  # 下一个成功追加仍拿 seq 2


def test_injected_clock_makes_created_at_reproducible(tmp_path) -> None:
    """时钟注入：固定钟下两次运行（同库不同聚合、两个库同聚合）created_at 全等可复现。"""
    db = tmp_path / "e.db"

    def run(tag: str) -> list[str]:
        with EventStore.open(db, clock=lambda: "2026-09-16T21:00:00+00:00") as store:
            store.append(tag, "run.started", {})
            store.append(tag, "submitted", {})
            return [r["created_at"] for r in store.events_for(tag)]

    assert run("run:1") == run("run:2") == ["2026-09-16T21:00:00+00:00"] * 2


def test_events_for_filters_by_type(tmp_path) -> None:
    """按类型过滤：type= 只取该类事件、seq 保序——「这单花了几次钱」的查询形状。"""
    with EventStore.open(tmp_path / "e.db", clock=lambda: "t") as store:
        store.append("run:1", "run.started", {})
        store.append("run:1", "cost.recorded", {"prompt_tokens": 12})
        store.append("run:1", "llm.decision", {})
        store.append("run:1", "cost.recorded", {"prompt_tokens": 12})
        costs = store.events_for("run:1", type="cost.recorded")
        assert [r["seq"] for r in costs] == [1, 3]
        assert all(r["type"] == "cost.recorded" for r in costs)
        assert all(r["payload"] == {"prompt_tokens": 12} for r in costs)


def test_unknown_event_type_is_rejected(tmp_path) -> None:
    """EVENT_TYPES 之外的类型 fail-closed（ValueError），表外词进不了审计流。"""
    with EventStore.open(tmp_path / "e.db", clock=lambda: "t") as store:
        with pytest.raises(ValueError, match="EVENT_TYPES"):
            store.append("run:1", "plan.maybe", {})
        assert store.events_for("run:1") == []


def test_no_update_or_delete_api() -> None:
    """meta：append-only 是接口形状——EventStore 上不存在 update/delete 系方法。"""
    for forbidden in ("update", "delete", "update_event", "delete_event", "truncate"):
        assert not hasattr(EventStore, forbidden), forbidden
    assert len(EVENT_TYPES) == 9  # 词汇表恰好九类（防漂移增删）
