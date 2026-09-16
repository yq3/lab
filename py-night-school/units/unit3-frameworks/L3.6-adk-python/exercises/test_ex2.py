"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio

import ex2_state as ex2
import mock_tools
from mock_endpoint import MockLLMEndpoint

CLAIM_ID = "CLM-2026-0001"  # data/ 用例：明细 [1200, 3500, 2400]，SALES，剩余 10000 分


def _run(limit: int):
    with MockLLMEndpoint() as ep:
        mock_tools.CALL_LOG.clear()
        return asyncio.run(ex2.review_with_limit(ep, CLAIM_ID, limit))


def test_limit_3000_rejects_over_limit_item() -> None:
    advice = _run(3000)
    assert advice.decision == "REJECT", advice
    assert advice.reason == "REJECT:ITEM_OVER_LIMIT"  # 3500 > 3000
    assert "limit_check:3000" in mock_tools.CALL_LOG  # state 真的流到了工具
    assert advice.remaining_cents == 10000


def test_limit_5000_approves_same_claim() -> None:
    advice = _run(5000)
    assert advice.decision == "APPROVE", advice
    assert advice.reason == "PASS"  # 无明细超过 5000
    assert "limit_check:5000" in mock_tools.CALL_LOG
    assert advice.remaining_cents == 10000
