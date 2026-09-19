"""L5.4 图侧验收：四层合体后的审批换芯 + 执行门接线——interrupt、拒绝回环、三哨兵、hash 不匹配。

L5.2 副本声明（对版纪律）：与 L5.2 的 test_graph 相比差异集中在「approve 出口改道 execute」
——批准恢复的断言从 submit.approved 收口改为过门付款（paid_cents + payment.executed）；
新增 A6/A7 的接线级用例（恢复载荷带假指纹 → 整单 DENY）与门哨兵分码用例。
跑法与 L3.3/L5.2 一致：每段 invoke 一个专属 MockLLMEndpoint（恢复侧剧本重布，历史来自
checkpoint——跨实例等价在 L3.3 Step1 已证）。
"""

from __future__ import annotations

import operator
from typing import get_type_hints

from langgraph.types import Command

import demo
import gate
import graph
from mock_endpoint import MockLLMEndpoint

RUN_ID = "test-run"


async def _start(claim_id: str, saver, run_id: str = RUN_ID, policy: gate.Policy | None = None):
    """起跑到 submit 暂停；返回 (cfg, 首个审批 payload, 暂停快照)。"""
    with MockLLMEndpoint() as ep:
        for text in demo.offline_run_scripts(claim_id):
            ep.script_text(text)
        compiled = graph.build_graph(demo.model_for_url(ep.url), checkpointer=saver, policy=policy)
        cfg = graph.run_config(run_id)
        await compiled.ainvoke(graph.initial_state(claim_id), cfg)
        snapshot = await compiled.aget_state(cfg)
        assert snapshot.next == ("submit",), "clean 单应恰好停在送审门"
        return cfg, dict(snapshot.interrupts[0].value), snapshot


async def _resume(saver, cfg, decision: dict, scripts: list[str], policy: gate.Policy | None = None):
    """从暂停点恢复一段（新图实例 + 新端点——L3.3 的跨实例恢复形态）；返回快照。"""
    with MockLLMEndpoint() as ep:
        for text in scripts:
            ep.script_text(text)
        compiled = graph.build_graph(demo.model_for_url(ep.url), checkpointer=saver, policy=policy)
        await compiled.ainvoke(Command(resume=decision), cfg)
        return await compiled.aget_state(cfg)


def _revised(claim_id: str, times: int) -> list[str]:
    """驳回回环的 drafter 台词（每回环一轮消费一条）。"""
    return [demo.revised_advice_after_feedback(claim_id) for _ in range(times)]


def test_state_schema_declares_accumulators() -> None:
    """meta：合并语义的键必须带 Annotated reducer（append-only 审计，覆盖语义会静默吞账）。"""
    hints = get_type_hints(graph.ExpenseState, include_extras=True)
    assert hints["plan_rejections"].__metadata__ == (operator.add,)
    assert hints["events"].__metadata__ == (operator.add,)
    assert hints["approval_rejects"].__metadata__ == (operator.add,)  # L5.2 的审批驳回账本
    assert hints["results"].__metadata__ == (graph.merge_results,)
    # L5.4 新键都在 schema 里（漏声明的键会被图静默丢弃——gate_reject 踩过才补的课）
    assert {"approval", "gate_result", "gate_reject", "paid_cents"} <= set(hints)


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


async def test_approve_resume_pays_through_gate(tmp_path) -> None:
    """批准恢复 → 改道 execute 过门 → 付款落账（A7：批准之后、END 之前还有一道门）。"""
    async with graph.open_saver(str(tmp_path / "c.db")) as saver:
        cfg, _payload, _snapshot = await _start("CLM-2026-0001", saver)
        snapshot = await _resume(saver, cfg, {"action": "approve"}, scripts=[])
        assert snapshot.next == ()  # 跑到 END
        assert snapshot.values["sent"] is True
        values = snapshot.values
        assert values["events"][-2:] == ["gate.allowed", "payment.executed"]  # 不是 submit.approved 收口了
        assert values["paid_cents"] == 7100  # 实付=提案总额（宽门原样放行）
        assert values["gate_result"]["action"] == "ALLOW"
        approval = values["approval"]  # 审批回执进 state（A7 二次校验的输入留了档）
        assert approval["decision"] == "CONFIRMED" and len(approval["content_hash"]) == 16
        advice = values["advice"]
        assert (advice.decision, advice.reason) == ("APPROVE", "PASS")


async def test_approve_resume_with_wrong_hash_denies_whole_payment(tmp_path) -> None:
    """A6/A7 接线级：恢复载荷声称的审批指纹与执行侧重算不符 → 整单 DENY → 门哨兵收口。

    威胁模型（A7「防中间层缺位/被绕过」）：中间层记错版本/被篡改的回复说「批的是 v1」，
    执行侧重算指纹是 v2——门当场拒绝付款，不带着错账放行。
    """
    async with graph.open_saver(str(tmp_path / "c.db")) as saver:
        cfg, _payload, _snapshot = await _start("CLM-2026-0001", saver)
        snapshot = await _resume(
            saver, cfg, {"action": "approve", "content_hash": "0" * 16, "ticket_id": "tkt-x"}, scripts=[]
        )
        values = snapshot.values
        assert "paid_cents" not in values  # 没付款
        assert values["gate_result"]["reason_code"] == "approval_content_mismatch"
        assert values["events"][-2:] == ["gate.denied:approval_content_mismatch", "escalate"]
        assert values["advice"].decision == "ESCALATE"
        assert values["advice"].reason == graph.ESCALATE_GATE_REASON  # 门哨兵（DENY）与升额码区分
        assert values["sent"] is False


async def test_tight_policy_over_limit_pauses_and_escalates(tmp_path) -> None:
    """紧合同（单笔 5000 分）：8800 分提案批准后过门 → 定量 PAUSE → 未付款 → 升额哨兵。"""
    tight = gate.Policy(
        max_single_cents=5_000, max_daily_total_cents=1_000_000, max_payments_per_day=50, vendor_blocklist=()
    )
    async with graph.open_saver(str(tmp_path / "c.db")) as saver:
        cfg, _payload, _snapshot = await _start("CLM-2026-0002", saver, policy=tight)
        snapshot = await _resume(saver, cfg, {"action": "approve"}, scripts=[], policy=tight)
        values = snapshot.values
        assert "paid_cents" not in values
        assert values["gate_result"]["reason_code"] == "single_over_limit"
        assert values["advice"].reason == graph.ESCALATE_REAUTH_REASON  # PAUSE：升额后重开新 run
        assert values["events"][-2:] == ["gate.paused:single_over_limit", "escalate"]


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
        assert "paid_cents" not in snapshot.values  # 从未过门——账上分文未动
        assert graph.RECURSION_LIMIT >= 16  # 最坏链 16 步（docstring 的预算口径）
