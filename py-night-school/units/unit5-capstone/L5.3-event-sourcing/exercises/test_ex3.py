"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

import pytest

import demo
from eventstore import EventStore
from ex3_version import CLAIM, GraphVersionMismatch, assert_compatible, build_chain, guarded_start, run_key
from step2_signature import topology_signature


def test_run_key_stable_for_same_graph_and_claim() -> None:
    """同图同 claim 稳定：两次 build 同签名 → 同 run_key；换单换 key。"""
    sig_a = topology_signature(build_chain(with_archive=False))
    sig_b = topology_signature(build_chain(with_archive=False))
    assert sig_a == sig_b  # 同装配签名可复现（L5.1 的纪律）
    assert run_key(CLAIM, sig_a) == run_key(CLAIM, sig_b)
    assert run_key(CLAIM, sig_a).startswith(f"{CLAIM}@")
    assert run_key("CLM-2026-0002", sig_a) != run_key(CLAIM, sig_a)


def test_adding_or_removing_node_changes_signature_and_key() -> None:
    """加/删节点签名变：四节点链 vs 三节点链（archive 在/不在）——签名变、run_key 跟着变。"""
    sig_three = topology_signature(build_chain(with_archive=False))
    sig_four = topology_signature(build_chain(with_archive=True))
    assert sig_three != sig_four
    assert run_key(CLAIM, sig_three) != run_key(CLAIM, sig_four)


def test_assert_compatible_accepts_same_and_rejects_different() -> None:
    """守门两态：同版本放行；不同版本抛 GraphVersionMismatch（异常带双方签名）。"""
    assert_compatible("a" * 64, "a" * 64)  # 放行：无异常即通过
    with pytest.raises(GraphVersionMismatch) as excinfo:
        assert_compatible("a" * 64, "b" * 64)
    assert excinfo.value.stored == "a" * 64
    assert excinfo.value.current == "b" * 64


def test_resume_old_key_rejected_and_new_key_normal(tmp_path) -> None:
    """续跑守门闭环：旧 key 换图续跑被拒（旧事件分毫未动）；新 key 正常落 run.started。"""
    db = tmp_path / "v.db"
    sig_old = topology_signature(build_chain(with_archive=False))
    sig_new = topology_signature(build_chain(with_archive=True))
    with EventStore.open(db, clock=lambda: "t") as store:
        old_key = run_key(CLAIM, sig_old)
        guarded_start(store, old_key, sig_old)  # 旧世界开账
        with pytest.raises(GraphVersionMismatch):
            guarded_start(store, old_key, sig_new)  # 换图续旧账：拒
        assert len(store.events_for(old_key)) == 1  # 拒绝不留半个事件，旧账原样
        new_key = run_key(CLAIM, sig_new)
        guarded_start(store, new_key, sig_new)  # 新世界新 key：正常
        rows = store.events_for(new_key, type="run.started")
        assert len(rows) == 1 and rows[0]["seq"] == 0  # 新聚合从 seq 0 起步
        assert rows[0]["payload"]["graph_version"] == sig_new  # 出生证明带版本


def test_demo_run_started_payload_carries_graph_version(tmp_path) -> None:
    """demo 集成路径：run_audited 落的 run.started 事件 payload 含 graph_version（A15）。"""
    db = tmp_path / "a.db"
    result = asyncio.run(demo.run_audited(CLAIM, db, mode="clean", clock=lambda: "t"))
    with EventStore.open(db, clock=lambda: "t") as store:
        started = store.events_for(result["run_key"], type="run.started")
    assert len(started) == 1
    assert started[0]["payload"]["graph_version"] == result["graph_version"]
    assert result["run_key"] == run_key(CLAIM, result["graph_version"])  # demo 与你的是同一把钥匙
