"""讲义区验收（六）：缓存即审计——canonical 键、命中零请求、审计查询出原话。"""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import demo
from audit_cache import DecisionCache, canonical_prompt, prompt_hash
from eventstore import EventStore


def _planner_messages() -> list:
    return [
        {"role": "system", "content": "你是规划器。"},
        {"role": "user", "content": "请规划 CLM-2026-0001 的取数步骤。"},
    ]


def test_canonical_prompt_equates_dict_and_langchain_messages() -> None:
    """canonical 键：dict 消息与同内容 langchain 消息（human=user、assistant=ai）哈希到同一 key。"""
    dict_form = _planner_messages()
    object_form = [SystemMessage(content="你是规划器。"), HumanMessage(content="请规划 CLM-2026-0001 的取数步骤。")]
    assert canonical_prompt(dict_form) == canonical_prompt(object_form)
    assert prompt_hash("mock-model", dict_form) == prompt_hash("mock-model", object_form)
    # assistant/ai 两种叫法同归一
    assert canonical_prompt([{"role": "assistant", "content": "答"}]) == canonical_prompt([AIMessage(content="答")])


def test_different_prompt_or_model_changes_hash() -> None:
    """不同 prompt 或不同模型 → 不同 key（不误命中的根：内容寻址，变一字符就换 key）。"""
    base = prompt_hash("mock-model", _planner_messages())
    changed_prompt = prompt_hash(
        "mock-model", [SystemMessage(content="你是规划器？"), HumanMessage(content="请规划 CLM-2026-0001 的取数步骤。")]
    )
    changed_model = prompt_hash("glm-4.6", _planner_messages())
    assert len({base, changed_prompt, changed_model}) == 3


def test_second_run_hits_cache_with_zero_model_requests(tmp_path) -> None:
    """同一单第二遍：llm_decisions 全命中——零模型请求，建议单与第一遍全等。"""
    db = tmp_path / "audit.db"
    first = asyncio.run(demo.run_audited("CLM-2026-0001", db, clock=lambda: "t"))
    second = asyncio.run(demo.run_audited("CLM-2026-0001", db, clock=lambda: "t"))
    assert first["requests"] == 2  # planner + drafter 各一（第一遍是真调用）
    assert second["requests"] == 0  # 第二遍零模型请求——缓存即审计的免费午餐
    assert second["run_key"] == first["run_key"]  # 同图同单：聚合键稳定
    assert second["final"]["advice"] == first["final"]["advice"]
    with EventStore.open(db, clock=lambda: "t") as store:
        assert len(store.events_for(first["run_key"], type="cost.recorded")) == 2  # 命中不花钱
        decisions = store.events_for(first["run_key"], type="llm.decision")
        assert len(decisions) == 4  # 两遍各两条：miss×2 + hit×2
        assert [d["payload"]["cached"] for d in decisions] == [False, False, True, True]


def test_audit_query_returns_full_original_text(tmp_path) -> None:
    """审计查询：prompt/response 全文原样在表——「当时模型看到了什么、说了什么」主键点查出原话。"""
    db = tmp_path / "audit.db"
    result = asyncio.run(demo.run_audited("CLM-2026-0001", db, mode="clean", clock=lambda: "t"))
    with EventStore.open(db, clock=lambda: "t") as store:
        planner_hash = store.events_for(result["run_key"], type="llm.decision")[0]["payload"]["prompt_hash"]
    with DecisionCache(db) as cache:
        record = cache.audit_query(planner_hash)
        assert record is not None
        assert record["model"] == "mock-model"
        assert "报销单审查流水线的规划器" in record["prompt"]  # system 岗位书全文在场
        assert "请规划报销单 CLM-2026-0001" in record["prompt"]  # user 单据摘要全文在场
        assert record["response"].startswith('{"claim_total_cents"')  # 计划 JSON 原话在场


def test_different_claim_does_not_falsely_hit(tmp_path) -> None:
    """不同单不误命中：prompt 内容不同 → 新 key → 真调用发生、响应不同。"""
    db = tmp_path / "audit.db"
    first = asyncio.run(demo.run_audited("CLM-2026-0001", db, clock=lambda: "t"))
    other = asyncio.run(demo.run_audited("CLM-2026-0004", db, clock=lambda: "t"))
    assert other["requests"] == 2  # 换单 = 新 prompt = 两次真调用（不是 0001 的缓存）
    assert other["final"]["advice"] != first["final"]["advice"]


def test_decision_cache_put_get_roundtrip_and_clock(tmp_path) -> None:
    """put/get 主键点查 + 时钟注入：固定钟下 created_at 可复现；miss 返回 None；同 key 重写。"""
    db = tmp_path / "c.db"
    with DecisionCache(db, clock=lambda: "t0") as cache:
        assert cache.get("deadbeef") is None  # miss 就是 None，不猜
        cache.put("deadbeef", "mock-model", "prompt 原文", "response 原文")
        record = cache.get("deadbeef")
        assert record is not None
        assert (record["prompt"], record["response"], record["created_at"]) == ("prompt 原文", "response 原文", "t0")
        cache.put("deadbeef", "mock-model", "prompt 原文 v2", "response 原文 v2")  # 同 key 重写：最新原话为准
        rewritten = cache.get("deadbeef")
        assert rewritten is not None and rewritten["prompt"] == "prompt 原文 v2"
