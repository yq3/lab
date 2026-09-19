"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

import ex2_bridge as ex2


def test_payload_structure_per_tool() -> None:
    payload = ex2.mcp_tools_payload(ex2.TOOLS)
    by_name = {item["function"]["name"]: item["function"] for item in payload}
    assert set(by_name) == {"preapprove", "claim_count"}
    for function in by_name.values():
        assert set(function) == {"name", "description", "parameters"}


def test_schema_passthrough() -> None:
    payload = ex2.mcp_tools_payload(ex2.TOOLS)
    preapprove = next(item for item in payload if item["function"]["name"] == "preapprove")
    # input_schema 原样透传成 parameters——协议接轨点（同一份 JSON Schema，一个字节不改）
    assert preapprove["function"]["parameters"] == ex2.TOOLS[0].input_schema
    assert preapprove["function"]["parameters"]["required"] == ["items_cents"]


def test_empty_description_becomes_empty_string() -> None:
    from mcp.types import Tool

    bare = Tool(name="bare", description=None, input_schema={"type": "object", "properties": {}})
    payload = ex2.mcp_tools_payload([bare])
    assert payload[0]["function"]["description"] == ""  # None 会炸下游——归一成空串
