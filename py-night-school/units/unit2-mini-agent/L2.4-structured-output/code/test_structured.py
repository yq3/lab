"""讲义代码验收（发货态必须全绿；练习区的红在 exercises/）。"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from model import ScriptedModel
from structured import (
    SYSTEM_DECISION,
    PreapprovalDecision,
    StructuredOutputError,
    ask_structured,
    extract_json,
    feedback_message,
)

GOOD = '{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT", "reason": "单笔超限"}'


# ---- extract_json：三层剥壳 ----


def test_extract_json_three_layers() -> None:
    assert extract_json(GOOD)["verdict"] == "REJECT:ITEM_OVER_LIMIT"  # 第 0 层：干净
    fenced = f"```json\n{GOOD}\n```"
    assert extract_json(fenced)["claim_id"] == "CLM-2026-0002"  # 第 1 层：```json 围栏
    bare_fence = f"```\n{GOOD}\n```"
    assert extract_json(bare_fence)["reason"] == "单笔超限"  # 第 2 层：无语言围栏
    prose = f"决策如下：{GOOD} 请查收。"
    assert extract_json(prose)["verdict"] == "REJECT:ITEM_OVER_LIMIT"  # 第 3 层：散文夹带


def test_extract_json_raises_on_garbage() -> None:
    with pytest.raises(ValueError, match="找不到 JSON"):
        extract_json("这张单据我看没什么问题，直接通过吧。")
    with pytest.raises(ValueError, match="JSON 语法错误"):
        extract_json("{verdict: PASS}")  # 键没加引号——语法伤也要翻译成人话


# ---- 决策模型：Literal 值域 ----


def test_decision_literal_verdict_domain() -> None:
    decision = PreapprovalDecision.model_validate_json(GOOD)
    assert decision.verdict == "REJECT:ITEM_OVER_LIMIT"
    assert decision.reviewer == "night-school-agent"  # 默认值兜底（不在 required，模型可省略）
    with pytest.raises(ValidationError):
        PreapprovalDecision.model_validate_json(
            '{"claim_id": "CLM-2026-0001", "verdict": "REJECT:OVER", "reason": "x"}'
        )
    schema = PreapprovalDecision.model_json_schema()
    assert "enum" in schema["properties"]["verdict"]  # Literal 在 schema 里广告成 enum——模型看得见值域
    assert "reviewer" not in schema["required"]  # 有默认值 → 不进 required（L2.2 的漂移点）


def test_feedback_message_translates_errors_for_model() -> None:
    try:
        PreapprovalDecision.model_validate_json('{"claim_id": "bad", "verdict": "REJECT:OVER", "reason": ""}')
    except ValidationError as exc:
        message = feedback_message(exc)
        assert message["role"] == "user"
        assert "claim_id" in message["content"] and "verdict" in message["content"]
        assert "JSON" in message["content"]


# ---- 修复循环 ----


def test_ask_structured_repairs_and_succeeds() -> None:
    model = ScriptedModel(
        [
            {"content": '```json\n{"claim_id": "CLM-2026-0002", "verdict": "REJECT:OVER"}\n```'},
            {"content": f"修正后：{GOOD}"},
        ]
    )

    async def scenario() -> tuple[PreapprovalDecision, list[dict]]:
        return await ask_structured(model, "问一下 CLM-2026-0002", attempts=3, system=SYSTEM_DECISION)

    decision, messages = asyncio.run(scenario())
    assert decision.verdict == "REJECT:ITEM_OVER_LIMIT"
    assert len(model.calls) == 2  # 恰好两次模型调用
    # 历史里能看到完整修复过程：坏产出原样入史 + 修复指令回喂
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user", "assistant", "user", "assistant"]
    assert "REJECT:OVER" in messages[2]["content"]  # 审计：坏产出留在案底
    assert "verdict" in messages[3]["content"]  # 修复指令点名了字段


def test_ask_structured_raises_after_attempts_exhausted() -> None:
    model = ScriptedModel([{"content": "我还是觉得直接通过比较好。"}] * 3)  # 永远交不出 JSON

    async def scenario() -> str:
        with pytest.raises(StructuredOutputError) as excinfo:
            await ask_structured(model, "问一下", attempts=3)
        return str(excinfo.value)

    message = asyncio.run(scenario())
    assert "3 次" in message
    assert len(model.calls) == 3  # 恰好 attempts 次，一次不多（重试也要有预算——L2.3 的纪律）
