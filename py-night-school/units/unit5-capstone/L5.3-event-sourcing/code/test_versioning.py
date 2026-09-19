"""讲义区验收（七）：图版本绑定三态——同图同 key / 改图拒续 / 事件带版本。"""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.runnables import Runnable

import demo
import graph
import versioning
from eventstore import EventStore


def _model() -> Runnable:
    return demo.model_for_url("http://127.0.0.1:9/v1")  # 只构造不调用，build 零网络


def test_run_key_stable_for_same_graph_and_claim() -> None:
    """同图同单：run_key 稳定（两次装配同一个 key）；换单换 key——聚合键跟着事实走。"""
    signature = versioning.topology_signature(graph.build_graph(_model()))
    assert versioning.run_key("CLM-2026-0001", signature) == versioning.run_key("CLM-2026-0001", signature)
    assert versioning.run_key("CLM-2026-0001", signature) == f"CLM-2026-0001@{signature[:12]}"
    assert versioning.run_key("CLM-2026-0002", signature) != versioning.run_key("CLM-2026-0001", signature)
    # 本课图拓扑与 L5.1 一字不差：签名相同（事件层是旁路，不改形状——对版证据）
    assert signature.startswith("5dbfa594e113")


def test_graph_shape_change_changes_signature_and_key() -> None:
    """图一改（+audit_stamp 节点）：签名立刻变、run_key 跟着变——旧执行态自动指向旧世界。"""
    plain = versioning.topology_signature(graph.build_graph(_model()))
    stamped = versioning.topology_signature(graph.build_graph(_model(), extra_stamp=True))
    assert plain != stamped
    assert versioning.run_key("C1", plain) != versioning.run_key("C1", stamped)


def test_assert_compatible_accepts_same_and_rejects_different() -> None:
    """续跑守门：同版本放行（无返回值即放行）；不同版本抛 GraphVersionMismatch（带双方签名）。"""
    versioning.assert_compatible("a" * 64, "a" * 64)  # 相同：安静通过
    with pytest.raises(versioning.GraphVersionMismatch) as excinfo:
        versioning.assert_compatible("a" * 64, "b" * 64)
    assert excinfo.value.stored == "a" * 64
    assert excinfo.value.current == "b" * 64


def test_run_started_payload_carries_graph_version(tmp_path) -> None:
    """run.started 事件 payload 含 graph_version——审计记录绑定产生它的拓扑版本（A15）。"""
    result = asyncio.run(demo.run_audited("CLM-2026-0001", tmp_path / "a.db", clock=lambda: "t"))
    with EventStore.open(tmp_path / "a.db", clock=lambda: "t") as store:
        started = store.events_for(result["run_key"], type="run.started")
    assert len(started) == 1 and started[0]["seq"] == 0  # 出生证明是事件 #0
    assert started[0]["payload"]["graph_version"] == result["graph_version"]
    assert started[0]["payload"]["claim_id"] == "CLM-2026-0001"


def test_resume_old_aggregate_under_changed_graph_is_rejected(tmp_path) -> None:
    """旧 run_key 续跑被拒：改图后拿旧聚合续跑 → GraphVersionMismatch，旧事件分毫未动。"""
    db = tmp_path / "a.db"
    clock = lambda: "t"  # noqa: E731
    first = asyncio.run(demo.run_audited("CLM-2026-0004", db, clock=clock))
    stamp_build = lambda m, recorder, cache: graph.build_graph(m, recorder, cache, extra_stamp=True)  # noqa: E731
    with pytest.raises(versioning.GraphVersionMismatch):
        asyncio.run(
            demo.run_audited("CLM-2026-0004", db, clock=clock, aggregate=first["run_key"], graph_builder=stamp_build)
        )
    with EventStore.open(db, clock=clock) as store:
        assert len(store.events_for(first["run_key"])) == 12  # 拒续不留半个事件，旧账 append-only 原样


def test_fresh_run_key_under_new_graph_is_normal(tmp_path) -> None:
    """新 key 正常：改图后不指定旧聚合 → 新 run_key → 新聚合从头记账，正常收尾。"""
    db = tmp_path / "a.db"
    clock = lambda: "t"  # noqa: E731
    first = asyncio.run(demo.run_audited("CLM-2026-0004", db, clock=clock))
    stamp_build = lambda m, recorder, cache: graph.build_graph(m, recorder, cache, extra_stamp=True)  # noqa: E731
    second = asyncio.run(demo.run_audited("CLM-2026-0004", db, clock=clock, graph_builder=stamp_build))
    assert second["run_key"] != first["run_key"]  # 新世界新 key
    assert second["final"]["sent"] is True  # 正常跑完
    assert "audit_stamp" in second["final"]["events"]  # 新拓扑真的生效（+1 节点在状态流水里）
    with EventStore.open(db, clock=clock) as store:
        assert store.events_for(second["run_key"])[0]["type"] == "run.started"  # 新聚合从 seq 0 起步
