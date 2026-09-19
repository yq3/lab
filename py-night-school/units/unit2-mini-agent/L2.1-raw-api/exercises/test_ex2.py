"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

import json

import ex2_sse_parser as ex2


def test_iter_sse_data_reassembles_worst_case_cuts() -> None:
    events = list(ex2.iter_sse_data(ex2.CHUNKS))
    assert len(events) == 3  # 两个 delta 事件 + [DONE]
    assert json.loads(events[0]) == {"choices": [{"delta": {"content": "报销单"}}]}
    assert json.loads(events[1]) == {"choices": [{"delta": {"content": "通过"}}]}
    assert events[2] == "[DONE]"
    # 「报」字的 UTF-8 三字节被第 1 刀劈开——按块解码的做法在这里必然 UnicodeDecodeError


def test_iter_sse_data_multiple_events_in_one_chunk() -> None:
    chunk = b'data: {"delta": "a"}\n\ndata: {"delta": "b"}\n\ndata: [DONE]\n\n'
    events = list(ex2.iter_sse_data([chunk]))
    assert events[-1] == "[DONE]"  # 哨兵照常吐出
    assert [json.loads(e)["delta"] for e in events[:-1]] == ["a", "b"]  # 一块三个事件照样切开


def test_collect_content_joins_and_skips_done() -> None:
    events = [
        json.dumps({"choices": [{"delta": {"content": "报销单"}}]}, ensure_ascii=False),
        json.dumps({"choices": [{"delta": {}}]}, ensure_ascii=False),  # 空 delta：没有 content 键
        "[DONE]",
        json.dumps({"choices": [{"delta": {"content": "通过"}}]}, ensure_ascii=False),
    ]
    assert ex2.collect_content(events) == "报销单通过"
    assert ex2.collect_content(list(ex2.iter_sse_data(ex2.CHUNKS))) == "报销单通过"
