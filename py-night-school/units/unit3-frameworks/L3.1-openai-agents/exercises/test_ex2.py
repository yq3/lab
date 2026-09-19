"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio

import pytest
from agents.exceptions import InputGuardrailTripwireTriggered

import ex2_guardrail as ex2
from advice import Advice


def test_guardrail_function_passes_known_claim() -> None:
    """护栏本体脱机直调（框架公开字段 guardrail_function）：好单号 tripwire=False。"""
    from typing import Any, cast

    func = cast(Any, ex2.claim_id_guardrail).guardrail_function
    output = func(None, None, "请审查报销单 CLM-2026-0001。")
    assert output.tripwire_triggered is False
    assert output.output_info == {"claim_id": "CLM-2026-0001", "known": True}


def test_guarded_review_passes_good_claim() -> None:
    advice, requests = asyncio.run(ex2.run_guarded("请审查报销单 CLM-2026-0002。"))
    assert isinstance(advice, Advice)
    assert advice.decision == "REJECT"
    assert advice.reason == "REJECT:ITEM_OVER_LIMIT"
    assert requests == 2


def test_guarded_review_trips_on_unknown_claim() -> None:
    with pytest.raises(InputGuardrailTripwireTriggered) as excinfo:
        asyncio.run(ex2.run_guarded("请审查报销单 CLM-2026-9999。"))
    assert excinfo.value.guardrail_result.output.output_info == {
        "claim_id": "CLM-2026-9999",
        "known": False,
    }


def test_guarded_review_trips_when_no_claim_id() -> None:
    with pytest.raises(InputGuardrailTripwireTriggered) as excinfo:
        asyncio.run(ex2.run_guarded("帮我把昨天的报销都过一遍。"))
    assert excinfo.value.guardrail_result.output.output_info == {"claim_id": None, "known": False}
