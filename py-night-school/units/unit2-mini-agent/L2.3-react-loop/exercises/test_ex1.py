"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio

import ex1_agent_loop as ex1


def test_run_completes_one_tool_round() -> None:
    model = ex1.ScriptedLite(
        [
            {"tool_calls": [{"id": "call_001", "name": "preapprove", "arguments": {"items_cents": [8800]}}]},
            {"content": "REJECT:ITEM_OVER_LIMIT"},
        ]
    )
    final, messages = asyncio.run(ex1.run(model, "预审 CLM-2026-0002，明细 8800 分。"))
    assert final == "REJECT:ITEM_OVER_LIMIT"
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "assistant"]
    # assistant 原样入史（含 tool_calls），id 与回喂一一配对
    assert messages[2]["tool_calls"][0]["id"] == messages[3]["tool_call_id"]
    # 工具真实执行过：回喂内容是执行结果，不是脚本里的 arguments
    assert messages[3]["content"] == "REJECT:ITEM_OVER_LIMIT"
    assert model.request_count == 2


def test_run_chains_two_tool_rounds() -> None:
    model = ex1.ScriptedLite(
        [
            {"tool_calls": [{"id": "call_a", "name": "preapprove", "arguments": {"items_cents": [-500]}}]},
            {"tool_calls": [{"id": "call_b", "name": "preapprove", "arguments": {"items_cents": [1200]}}]},
            {"content": "第一单脏数据拒绝，第二单通过。"},
        ]
    )
    final, messages = asyncio.run(ex1.run(model, "预审两张单。"))
    assert final == "第一单脏数据拒绝，第二单通过。"
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "assistant", "tool", "assistant"]
    assert messages[3]["content"] == "REJECT:INVALID_AMOUNT"  # 第 2 轮请求带上了第 1 轮的结果
    assert messages[5]["content"] == "PASS"


def test_run_feeds_unknown_tool_error_instead_of_raising() -> None:
    model = ex1.ScriptedLite(
        [
            {"tool_calls": [{"id": "call_x", "name": "no_such_tool", "arguments": {"x": 1}}]},
            {"content": "工具不存在，改用已知结论回答。"},
        ]
    )
    final, messages = asyncio.run(ex1.run(model, "预审一下"))
    assert final == "工具不存在，改用已知结论回答。"
    assert "unknown_tool" in messages[3]["content"]  # 错误回喂给模型，模型自己修了
