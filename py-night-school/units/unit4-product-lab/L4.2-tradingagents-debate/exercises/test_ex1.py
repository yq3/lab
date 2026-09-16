"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

import ex1_rounds as ex1


def _model(rounds: int) -> ex1.FakeChatModel:
    """给 2*rounds 轮辩论备台词；裁决官是占位节点不调模型。"""
    return ex1.FakeChatModel([f"第{i}轮发言" for i in range(1, 2 * rounds + 1)])


def _run(rounds: int) -> tuple[list[str], int]:
    model = _model(rounds)
    graph = ex1.build(ex1.RoundsConfig(max_debate_rounds=rounds), model)
    steps: list[str] = []

    async def stream() -> None:
        async for chunk in graph.astream(
            {"messages": [], "debate": {"count": 0, "current_speaker": ""}}, stream_mode="updates"
        ):
            steps.extend(chunk.keys())

    asyncio.run(stream())
    return steps, model.request_count


def test_rounds_one_is_exactly_two_debate_calls_then_ruling() -> None:
    steps, calls = _run(1)
    assert steps == ["申辩人", "合规官", "裁决官"]
    assert calls == 2  # 辩论段恰好 2*rounds=2 次（裁决官是占位节点，不调模型）


def test_rounds_two_doubles_debate_and_keeps_alternation() -> None:
    steps, calls = _run(2)
    assert steps == ["申辩人", "合规官", "申辩人", "合规官", "裁决官"]  # 申辩人与合规官交替
    assert calls == 4  # 辩论段恰好 2*rounds=4 次


def test_path_map_fully_covered_by_reachable_nodes() -> None:
    """两态跑完出现过的工作节点恰好铺满 DEBATE_PATH_MAP 的键集——无死条目、无落空。"""
    seen: set[str] = set()
    for rounds in (1, 2):
        steps, _calls = _run(rounds)
        seen.update(steps)
    assert seen == set(ex1.DEBATE_PATH_MAP)
    # 终态（裁决官）在两种轮次下都可达——path_map 的每个条目都被真实路由过
    assert "裁决官" in ex1.DEBATE_PATH_MAP
