"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio
import operator
from typing import get_type_hints

import ex2_events as ex2


def test_reject_path_events_sequence_is_exact() -> None:
    result = asyncio.run(ex2.build().ainvoke({"items_cents": [8800], "messages": []}))
    assert result["events"] == ["intake", "check", "reject"]  # 合并语义才攒得出完整流水
    assert result["messages"][-1].content == "REJECT:ITEM_OVER_LIMIT"


def test_approve_path_events_sequence_is_exact() -> None:
    result = asyncio.run(ex2.build().ainvoke({"items_cents": [1200], "messages": []}))
    assert result["events"] == ["intake", "check", "approve"]
    assert result["messages"][-1].content == "PASS"
    assert len(result["messages"]) == 3  # 三个节点各写一条，add_messages 合并（given 部分的行为印证）


def test_events_annotation_must_be_operator_add() -> None:
    """meta：events 必须声明 operator.add 合并语义（覆盖语义会让前两个测试的流水只剩最后一条）。"""
    hints = get_type_hints(ex2.AuditState, include_extras=True)
    assert hints["events"].__metadata__ == (operator.add,)
