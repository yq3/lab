"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import json

import ex3_trim as ex3


def _history() -> list[dict]:
    return [
        {"role": "system", "content": "S" * 40},
        {"role": "user", "content": "U" * 120},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "function": {"name": "t"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "R" * 120},
        {"role": "assistant", "content": "A" * 120},
        {"role": "user", "content": "U2" * 80},
        {"role": "assistant", "content": "final"},
    ]


def test_within_budget_returns_same_sequence() -> None:
    messages = _history()
    assert ex3.trim_messages(messages, ex3.estimate_chars(messages)) == messages


def test_trim_respects_budget_and_keeps_system_and_latest() -> None:
    messages = _history()
    budget = ex3.estimate_chars(messages) - 300  # 强制裁掉最老的两条左右
    trimmed = ex3.trim_messages(messages, budget)
    assert ex3.estimate_chars(trimmed) <= budget  # 预算纪律
    assert trimmed[0]["role"] == "system"  # system 永远保留
    assert trimmed[-1]["content"] == "final"  # 最新消息保留
    tail = [m["content"] for m in messages[-(len(trimmed) - 1) :]]  # system 之外的尾部
    assert [m["content"] for m in trimmed[1:]] == tail  # 保序：裁剪只砍头，不重排


def test_trim_never_leads_with_orphan_tool() -> None:
    messages = _history()
    # 选一个预算：裁掉 user 后，下一条正好是 tool（孤儿）——必须连坐
    chars = ex3.estimate_chars(messages)
    head = len(json.dumps(messages[0], ensure_ascii=False)) + len(json.dumps(messages[1], ensure_ascii=False))
    budget = chars - (head + 10)  # 大约裁掉 user 之后
    trimmed = ex3.trim_messages(messages, budget)
    assert trimmed[1]["role"] != "tool"
    assert ex3.estimate_chars(trimmed) <= budget


def test_trim_does_not_mutate_original() -> None:
    messages = _history()
    before = len(messages)
    ex3.trim_messages(messages, ex3.estimate_chars(messages) // 3)  # 裁得很狠
    assert len(messages) == before  # 原历史是审计证据，一字不动
