"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage

import ex1_wiring as ex1
import mock_tools


def _scripts() -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "check_budget", "args": {"dept": "DEV"}, "id": "call_a"},
                {"name": "verify_invoice", "args": {"invoice_id": "INV-2026-0003"}, "id": "call_b"},
            ],
        ),
        AIMessage(content="DEV 部门剩余 40000 分，发票有效：建议 APPROVE。"),
    ]


def test_node_sequence_is_exactly_reviewer_tools_reviewer_finalize() -> None:
    graph = ex1.build(ex1.FakeChatModel(_scripts()))
    chunks: list[list[str]] = []

    async def stream() -> None:
        async for chunk in graph.astream(
            {"messages": [{"role": "user", "content": "预审 CLM-2026-0003。"}]}, stream_mode="updates"
        ):
            chunks.append(list(chunk.keys()))

    asyncio.run(stream())
    assert chunks == [["reviewer"], ["tools"], ["reviewer"], ["finalize"]]


def test_full_loop_collects_final_answer_with_real_tools() -> None:
    model = ex1.FakeChatModel(_scripts())
    graph = ex1.build(model)
    mock_tools.CALL_LOG.clear()
    result = asyncio.run(graph.ainvoke({"messages": [{"role": "user", "content": "预审 CLM-2026-0003。"}]}))
    assert result["final"] == "DEV 部门剩余 40000 分，发票有效：建议 APPROVE。"
    assert model.request_count == 2  # reviewer 执行两轮：第 1 轮选工具，第 2 轮收束
    assert {"check_budget", "verify_invoice"} <= set(mock_tools.CALL_LOG)  # 工具真实执行
    tool_contents = [m.content for m in result["messages"] if type(m).__name__ == "ToolMessage"]
    assert any("40000" in c for c in tool_contents)  # 回喂的是执行结果，不是剧本的 arguments


def test_unknown_tool_is_fed_back_not_raised() -> None:
    model = ex1.FakeChatModel(
        [
            AIMessage(content="", tool_calls=[{"name": "no_such_tool", "args": {"x": 1}, "id": "call_x"}]),
            AIMessage(content="工具不存在，改用已知结论回答。"),
        ]
    )
    graph = ex1.build(model)
    result = asyncio.run(graph.ainvoke({"messages": [{"role": "user", "content": "预审一下。"}]}))
    assert result["final"] == "工具不存在，改用已知结论回答。"
    tool_contents = [m.content for m in result["messages"] if type(m).__name__ == "ToolMessage"]
    assert any("unknown_tool" in c for c in tool_contents)  # 错误回喂给模型，模型自己修了
