"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio

import pytest

import ex2_repair as ex2

GOOD = '{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT", "reason": "单笔超限"}'
BAD = '```json\n{"claim_id": "CLM-2026-0002", "verdict": "REJECT:OVER"}\n```'


def test_repairs_on_second_attempt_with_full_history() -> None:
    model = ex2.ScriptedLite([BAD, f"修正：{GOOD}"])
    decision, messages = asyncio.run(ex2.ask_structured(model, "问一下", attempts=3))
    assert decision.verdict == "REJECT:ITEM_OVER_LIMIT"
    assert model.request_count == 2
    # 好坏产出都入史（审计），失败后紧跟修复指令
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user", "assistant"]
    assert messages[3]["role"] == "user"  # 修复指令是 user 消息


def test_first_attempt_success_has_three_messages() -> None:
    model = ex2.ScriptedLite([GOOD])
    decision, messages = asyncio.run(ex2.ask_structured(model, "问一下"))
    assert decision.claim_id == "CLM-2026-0002"
    assert [m["role"] for m in messages] == ["system", "user", "assistant"]


def test_attempts_exhausted_raises_with_count() -> None:
    model = ex2.ScriptedLite(["我就是不想输出 JSON。"] * 3)

    async def scenario() -> str:
        with pytest.raises(ex2.DecisionError) as excinfo:
            await ex2.ask_structured(model, "问一下", attempts=3)
        return str(excinfo.value)

    message = asyncio.run(scenario())
    assert "3" in message
    assert model.request_count == 3  # 恰好 attempts 次——重试也要有预算
