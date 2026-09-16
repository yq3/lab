"""讲义区验收（八）：端到端——四单事件流水完整、重放视图与终态全等、重跑追加不重花。"""

from __future__ import annotations

import asyncio

import demo
import graph
import mock_tools
from advice import Advice
from eventstore import EventStore, replay

CLEAN_TYPES = [
    "run.started",
    "intake.loaded",
    "llm.decision",
    "cost.recorded",
    "plan.approved",
    "tool.called",
    "tool.called",
    "tool.called",
    "llm.decision",
    "cost.recorded",
    "advice.drafted",
    "submitted",
]
DIRTY_ONCE_TYPES = [
    "run.started",
    "intake.loaded",
    "llm.decision",
    "cost.recorded",
    "plan.rejected",
    "llm.decision",
    "cost.recorded",
    "plan.approved",
    "tool.called",
    "tool.called",
    "tool.called",
    "llm.decision",
    "cost.recorded",
    "advice.drafted",
    "submitted",
]
ALWAYS_DIRTY_TYPES = [
    "run.started",
    "intake.loaded",
    "llm.decision",
    "cost.recorded",
    "plan.rejected",
    "llm.decision",
    "cost.recorded",
    "plan.rejected",
    "llm.decision",
    "cost.recorded",
    "plan.rejected",
    "advice.drafted",
]


def _expected_types(mode: str) -> list[str]:
    return {"clean": CLEAN_TYPES, "dirty_once": DIRTY_ONCE_TYPES, "always_dirty": ALWAYS_DIRTY_TYPES}[mode]


def test_four_claims_event_streams_are_complete(tmp_path) -> None:
    """四单跑完：每聚合的事件 type 序列与剧本形态逐条全等（seq 0..n 连续、事件流水完整）。"""
    db = tmp_path / "flow.db"
    clock = lambda: "t"  # noqa: E731
    for claim in mock_tools.claims_table():
        claim_id = claim["id"]
        mode = demo.CLAIM_MODES[claim_id]
        result = asyncio.run(demo.run_audited(claim_id, db, mode=mode, clock=clock))
        with EventStore.open(db, clock=clock) as store:
            rows = store.events_for(result["run_key"])
        assert [r["type"] for r in rows] == _expected_types(mode), claim_id
        assert [r["seq"] for r in rows] == list(range(len(rows)))  # seq 连续无洞
        # 建议单逐字段对账：clean/dirty_once 单与 review_mock 的 expect_* 全等（dirty_once 回喂不改业务结论）；
        # always_dirty 单走超限哨兵枚举码
        advice: Advice = result["final"]["advice"]
        if mode == "always_dirty":
            assert advice.decision == "ESCALATE" and advice.reason == graph.ESCALATE_REASON, claim_id
        else:
            assert advice.decision == claim["expect_decision"], claim_id
            assert advice.reason == claim["expect_reason"], claim_id


def test_replayed_view_equals_final_state(tmp_path) -> None:
    """重放视图与终态全等：fold(events) 的 advice/results/sent/拒绝轨迹 == 图跑出来的 state。"""
    db = tmp_path / "flow.db"
    clock = lambda: "t"  # noqa: E731
    for claim in mock_tools.claims_table():
        claim_id = claim["id"]
        result = asyncio.run(demo.run_audited(claim_id, db, mode=demo.CLAIM_MODES[claim_id], clock=clock))
        with EventStore.open(db, clock=clock) as store:
            view = replay(store, result["run_key"])
        final = result["final"]
        assert view["advice"] == final["advice"], claim_id
        assert view["results"] == final["results"], claim_id
        assert view["sent"] == final["sent"], claim_id
        assert [r["reason_code"] for r in view["plan_rejections"]] == [r.reason_code for r in final["plan_rejections"]]


def test_cost_events_accumulate_per_real_call(tmp_path) -> None:
    """成本事件累计：每次真实模型调用一条 cost.recorded（12/8 来自端点 usage），fold 累计=次数×单次。"""
    db = tmp_path / "flow.db"
    clock = lambda: "t"  # noqa: E731
    expected_calls = {"CLM-2026-0001": 2, "CLM-2026-0002": 3, "CLM-2026-0003": 3, "CLM-2026-0004": 2}
    for claim_id, calls in expected_calls.items():
        result = asyncio.run(demo.run_audited(claim_id, db, mode=demo.CLAIM_MODES[claim_id], clock=clock))
        assert result["requests"] == calls, claim_id  # 真实请求数 = 剧本轮次（planner 各轮 + drafter）
        with EventStore.open(db, clock=clock) as store:
            costs = store.events_for(result["run_key"], type="cost.recorded")
            assert len(costs) == calls, claim_id
            assert all(c["payload"]["prompt_tokens"] == 12 and c["payload"]["completion_tokens"] == 8 for c in costs)
            assert replay(store, result["run_key"])["cost"] == {
                "prompt_tokens": 12 * calls,
                "completion_tokens": 8 * calls,
            }, claim_id


def test_rerun_appends_events_without_new_cost(tmp_path) -> None:
    """同一单重跑：事件追加（两遍各一套流水）、成本零新增、缓存命中留痕（cached 标记翻面）。"""
    db = tmp_path / "flow.db"
    clock = lambda: "t"  # noqa: E731
    first = asyncio.run(demo.run_audited("CLM-2026-0002", db, mode="dirty_once", clock=clock))
    second = asyncio.run(demo.run_audited("CLM-2026-0002", db, mode="dirty_once", clock=clock))
    assert second["requests"] == 0
    assert second["final"]["advice"] == first["final"]["advice"]  # 重放的建议单与第一遍全等
    with EventStore.open(db, clock=clock) as store:
        rows = store.events_for(first["run_key"])
        rerun_types = [t for t in DIRTY_ONCE_TYPES if t != "cost.recorded"]  # 命中路径：无 cost 事件
        assert len(rows) == len(DIRTY_ONCE_TYPES) + len(rerun_types)  # 两遍流水：第一遍全量 + 第二遍去成本
        assert [r["type"] for r in rows[len(DIRTY_ONCE_TYPES) :]] == rerun_types
        assert len(store.events_for(first["run_key"], type="cost.recorded")) == 3  # 成本零新增
        assert len(store.events_for(first["run_key"], type="run.started")) == 2  # 两次出生证明
