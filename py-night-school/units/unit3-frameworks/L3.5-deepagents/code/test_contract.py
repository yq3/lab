"""四框架同题 demo 的共用验收脚本（Unit 3 宪法级约定：L3.1 / L3.2 / L3.4 / L3.5 / L3.6
各持一份字节相同的副本——改一处必须同步五课，宪法「共享模块对版纪律」）。

它只依赖各课 demo 的统一入口 `run_review(claim_id) -> Advice`：
  - 用例不硬编码：直接读 data/expense/review_mock.json（明线素材唯一来源）；
  - 覆盖型 meta 检查（L0.1 ex2 先例）：用例表必须覆盖四种结论场景、三种 decision、
    两个部门——防止「删一个用例照样绿」；
  - CALL_LOG 证明工具被框架真实执行过（剧本模型不能自说自话）。
"""

from __future__ import annotations

import asyncio

import mock_tools
from advice import Advice
from demo import run_review


def test_contract_covers_all_claims_and_decisions() -> None:
    claims = mock_tools.claims_table()
    assert {c["id"] for c in claims} == {
        "CLM-2026-0001",
        "CLM-2026-0002",
        "CLM-2026-0003",
        "CLM-2026-0004",
    }
    assert {c["expect_decision"] for c in claims} == {"APPROVE", "REJECT", "ESCALATE"}
    assert {c["dept"] for c in claims} == {"SALES", "DEV"}


def test_contract_review_each_claim() -> None:
    for claim in mock_tools.claims_table():
        mock_tools.CALL_LOG.clear()
        advice = asyncio.run(run_review(claim["id"]))
        assert isinstance(advice, Advice), (claim["id"], type(advice))
        assert advice.claim_id == claim["id"]
        assert advice.decision == claim["expect_decision"], (claim["id"], advice.decision)
        assert advice.reason == claim["expect_reason"], (claim["id"], advice.reason)
        assert advice.remaining_cents == claim["expect_remaining_cents"], claim["id"]
        assert {"check_budget", "verify_invoice"} <= set(mock_tools.CALL_LOG), (
            claim["id"],
            list(mock_tools.CALL_LOG),
        )
