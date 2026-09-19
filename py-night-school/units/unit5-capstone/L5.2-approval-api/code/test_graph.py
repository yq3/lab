"""L5.2 图侧验收：submit 换芯——interrupt 审批单、拒绝回环、封顶哨兵、内容指纹。

跑法与 L3.3 一致：每段 invoke 一个专属 MockLLMEndpoint（恢复侧剧本重布，历史来自
checkpoint——跨实例等价在 L3.3 Step1 已证）。
"""

from __future__ import annotations

import operator
from typing import get_type_hints

from langgraph.types import Command

import demo
import graph
from mock_endpoint import MockLLMEndpoint

RUN_ID = "test-run"


async def _start(claim_id: str, saver, run_id: str = RUN_ID):
    """起跑到 submit 暂停；返回 (cfg, 首个审批 payload, 暂停快照)。"""
    with MockLLMEndpoint() as ep:
        for text in demo.offline_run_scripts(claim_id):
            ep.script_text(text)
        compiled = graph.build_graph(demo.model_for_url(ep.url), checkpointer=saver)
        cfg = graph.run_config(run_id)
        await compiled.ainvoke(graph.initial_state(claim_id), cfg)
        snapshot = await compiled.aget_state(cfg)
        assert snapshot.next == ("submit",), "clean 单应恰好停在送审门"
        return cfg, dict(snapshot.interrupts[0].value), snapshot


async def _resume(saver, cfg, decision: dict, scripts: list[str]):
    """从暂停点恢复一段（新图实例 + 新端点——L3.3 的跨实例恢复形态）；返回快照。"""
    with MockLLMEndpoint() as ep:
        for text in scripts:
            ep.script_text(text)
        compiled = graph.build_graph(demo.model_for_url(ep.url), checkpointer=saver)
        await compiled.ainvoke(Command(resume=decision), cfg)
        return await compiled.aget_state(cfg)


def _revised(claim_id: str, times: int) -> list[str]:
    """驳回回环的 drafter 台词（每回环一轮消费一条）。"""
    return [demo.revised_advice_after_feedback(claim_id) for _ in range(times)]


def test_state_schema_declares_approval_rejects_accumulator() -> None:
    """meta：审批驳回账本是合并语义键（append-only 审计，覆盖语义会静默吞账）。"""
    hints = get_type_hints(graph.ExpenseState, include_extras=True)
    assert hints["approval_rejects"].__metadata__ == (operator.add,)
    assert hints["plan_rejections"].__metadata__ == (operator.add,)  # L5.1 的账本原样延续


async def test_submit_interrupts_with_approval_payload(tmp_path) -> None:
    async with graph.open_saver(str(tmp_path / "c.db")) as saver:
        cfg, payload, snapshot = await _start("CLM-2026-0001", saver)
        assert (cfg.get("configurable") or {}).get("thread_id") == RUN_ID
        assert payload["run_id"] == RUN_ID  # thread_id 即 run_id：审批单的归属凭证
        assert payload["claim_id"] == "CLM-2026-0001"
        assert payload["dept"] == "SALES"
        assert payload["total_cents"] == 7100  # 1200 + 3500 + 2400
        assert payload["advice"] == {"decision": "APPROVE", "reason": "PASS", "remaining_cents": 10000}
        assert len(payload["content_hash"]) == 16  # A6 内容指纹的形态
        assert snapshot.values["events"] == ["intake", "planner", "plan.approved", "executor", "drafter"]
        assert "sent" not in snapshot.values  # 未批准：送审标志还没出现


async def test_approve_resume_completes_without_model_calls(tmp_path) -> None:
    async with graph.open_saver(str(tmp_path / "c.db")) as saver:
        cfg, _payload, _snapshot = await _start("CLM-2026-0001", saver)
        snapshot = await _resume(saver, cfg, {"action": "approve"}, scripts=[])
        assert snapshot.next == ()  # 跑到 END
        assert snapshot.values["sent"] is True
        assert snapshot.values["events"][-1] == "submit.approved"
        advice = snapshot.values["advice"]
        assert (advice.decision, advice.reason) == ("APPROVE", "PASS")


async def test_reject_resume_loops_back_with_feedback_and_new_hash(tmp_path) -> None:
    async with graph.open_saver(str(tmp_path / "c.db")) as saver:
        cfg, first, _snapshot = await _start("CLM-2026-0001", saver)
        snapshot = await _resume(
            saver, cfg, {"action": "reject", "message": "先补三级审批单"}, scripts=_revised("CLM-2026-0001", 1)
        )
        assert snapshot.next == ("submit",)  # 回环重生成后再次停在送审门
        values = snapshot.values
        assert values["events"][-3:] == ["drafter", "submit.rejected", "drafter"]  # 首版→驳回→重起草
        assert values["approval_rejects"] == [{"message": "先补三级审批单"}]
        feedback_seen = [
            m.content
            for m in values["messages"]
            if getattr(m, "type", "") == "human" and "先补三级审批单" in str(m.content)
        ]
        assert feedback_seen, "驳回留言必须作为消息回喂（A1 纠错回路）"
        assert values["advice"].decision == "ESCALATE"  # 修订版：按留言转人工
        assert values["advice"].reason == "REJECT:APPROVAL_FEEDBACK"
        second = dict(snapshot.interrupts[0].value)
        assert second["content_hash"] != first["content_hash"]  # A6：内容一变，指纹变——批的是新一单
        assert second["advice"]["decision"] == "ESCALATE"


async def test_reject_without_message_uses_default_feedback(tmp_path) -> None:
    async with graph.open_saver(str(tmp_path / "c.db")) as saver:
        cfg, _payload, _snapshot = await _start("CLM-2026-0002", saver)
        snapshot = await _resume(saver, cfg, {"action": "reject"}, scripts=_revised("CLM-2026-0002", 1))
        assert snapshot.values["approval_rejects"] == [{"message": graph.DEFAULT_REJECT_FEEDBACK}]


async def test_approval_loop_cap_escalates(tmp_path) -> None:
    """三次驳回：前两次回环重生成，第三次烧满 MAX_APPROVAL_LOOPS → 双哨兵收口不送审。"""
    async with graph.open_saver(str(tmp_path / "c.db")) as saver:
        cfg, _payload, _snapshot = await _start("CLM-2026-0001", saver)
        snapshot = await _resume(saver, cfg, {"action": "reject"}, scripts=_revised("CLM-2026-0001", 1))
        snapshot = await _resume(saver, cfg, {"action": "reject"}, scripts=_revised("CLM-2026-0001", 1))
        snapshot = await _resume(saver, cfg, {"action": "reject"}, scripts=[])
        assert snapshot.next == ()
        assert len(snapshot.values["approval_rejects"]) == graph.MAX_APPROVAL_LOOPS + 1  # 3 次驳回
        assert snapshot.values["events"].count("drafter") == 3  # 首版 + 2 次重生成，没有第 3 次
        assert snapshot.values["events"][-1] == "escalate"
        advice = snapshot.values["advice"]
        assert advice.decision == "ESCALATE"
        assert advice.reason == graph.ESCALATE_APPROVAL_REASON  # 与重规划烧满的哨兵码区分开
        assert snapshot.values["sent"] is False
