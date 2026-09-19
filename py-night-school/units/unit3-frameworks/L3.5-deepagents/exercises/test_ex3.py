"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

from langchain_core.messages import ToolMessage

import ex3_write_dossier as ex3


def test_dossier_lands_at_review_path() -> None:
    """底稿落盘：state['files'] 里有 /review/<单号>.md，正文与 extract_dossier 取回的一致。"""
    advice, state, dossier = asyncio.run(ex3.run_with_dossier("CLM-2026-0002"))
    path = f"/review/{advice.claim_id}.md"
    assert sorted(state["files"].keys()) == [path]  # 路径断言：/review/<单号>.md，仅此一件
    assert dossier == state["files"][path]["content"]  # 取回的就是落盘正文
    assert advice.claim_id in dossier  # 三要素之一：单号
    assert advice.reason in dossier  # 三要素之二：结论码
    assert "10000" in dossier  # 三要素之三：SALES 剩余预算（分）


def test_write_round_actually_executed() -> None:
    """write_file 轮真实执行过：回喂的 ToolMessage 带回落盘回执，而不是剧本自说自话。"""
    advice, state, _ = asyncio.run(ex3.run_with_dossier("CLM-2026-0004"))
    write_msg = next(m for m in state["messages"] if isinstance(m, ToolMessage) and m.tool_call_id == "call_write")
    assert "/review/CLM-2026-0004.md" in str(write_msg.content)  # 内置工具的回执里带文件路径
    assert advice.reason == "REJECT:INVOICE_INVALID"  # 收尾建议单不受底稿轮影响
