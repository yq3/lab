"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import ex1_messages as ex1


def test_build_messages_structure() -> None:
    messages = ex1.build_messages("你是财务预审助手。", "预审 CLM-2026-0001")
    assert messages == [
        {"role": "system", "content": "你是财务预审助手。"},
        {"role": "user", "content": "预审 CLM-2026-0001"},
    ]


def test_extract_reply_from_text_response() -> None:
    assert ex1.extract_reply(ex1.RESPONSE_TEXT) == ("报销单 CLM-2026-0001 预审通过。", "stop")


def test_extract_reply_from_tool_calls_response() -> None:
    # content 为 None：归一成空串；finish_reason 是协议的分支信号，必须原样带出
    assert ex1.extract_reply(ex1.RESPONSE_TOOL_CALLS) == ("", "tool_calls")
