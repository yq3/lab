"""讲义区验收：checkpointer 与 interrupt 的行为纪律（demo 图的机制测试——
出口契约由 ReviewOutcome 承担，这里管暂停/恢复/隔离/双路的全套证据）。"""

from __future__ import annotations

import asyncio
import operator
from collections.abc import Sequence
from typing import Annotated, Literal, TypedDict, get_type_hints

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, StateSnapshot

import demo
import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint


def test_state_declares_reducers_and_gate_key() -> None:
    """meta：messages/events 必须带合并语义的 Annotated reducer；人审键在 schema 里（L0.1 ex2 先例）。"""
    hints = get_type_hints(demo.ClaimState, include_extras=True)
    assert hints["messages"].__metadata__ == (add_messages,)
    assert hints["events"].__metadata__ == (operator.add,)
    assert set(hints) == {"messages", "events", "advice", "human_decision"}


def test_review_outcome_inherits_advice() -> None:
    """meta：ReviewOutcome 必须继承共享 Advice 并只加 human 字段（Pydantic 模型继承）。"""
    assert issubclass(demo.ReviewOutcome, Advice)
    base_fields = set(Advice.model_fields)
    assert set(demo.ReviewOutcome.model_fields) == base_fields | {"human"}
    plain = Advice(claim_id="x", decision="APPROVE", reason="PASS", remaining_cents=1)
    merged = demo.ReviewOutcome(**plain.model_dump(), human="approve")
    assert merged.human == "approve"
    assert merged.claim_id == "x"  # 父类校验与字段原样继承


def test_route_after_reviewer_is_three_way() -> None:
    with_tools = AIMessage(content="", tool_calls=[{"name": "check_budget", "args": {"dept": "DEV"}, "id": "c1"}])
    assert demo.route_after_reviewer({"messages": [with_tools], "events": []}) == "tools"
    escalate_text = (
        '{"claim_id":"CLM-2026-0003","decision":"ESCALATE","reason":"REJECT:INVALID_AMOUNT","remaining_cents":40000}'
    )
    escalate = AIMessage(content=escalate_text)
    assert demo.route_after_reviewer({"messages": [escalate], "events": []}) == "human_gate"
    clean_text = '{"claim_id":"CLM-2026-0001","decision":"APPROVE","reason":"PASS","remaining_cents":10000}'
    clean = AIMessage(content=clean_text)
    assert demo.route_after_reviewer({"messages": [clean], "events": []}) == "finalize"
    garbage = AIMessage(content="还没想好")
    assert demo.route_after_reviewer({"messages": [garbage], "events": []}) == "finalize"


def test_checkpointer_gives_memory_across_graph_instances(tmp_path) -> None:  # noqa: ANN001 -- pytest fixture
    """跨实例记忆：两张图 + 两个 saver 连接 + 同一个 db——第二段能看到第一段的历史。"""

    class ChatState(TypedDict):
        messages: Annotated[list, add_messages]

    class CountingChat:
        def __init__(self) -> None:
            self.seen: list[int] = []

        async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
            self.seen.append(len(messages))
            return AIMessage(content="回声")

    async def scene() -> list[int]:
        model = CountingChat()
        cfg = demo.thread_config("mem-test")
        db = str(tmp_path / "mem.sqlite3")

        def build() -> StateGraph:  # type: ignore[type-arg]
            builder = StateGraph(ChatState)

            async def chat(state: ChatState) -> dict:
                return {"messages": [await model.ainvoke(state["messages"])]}

            builder.add_node("chat", chat)
            builder.add_edge(START, "chat")
            builder.add_edge("chat", END)
            return builder

        async with demo.open_saver(db) as saver:
            await build().compile(checkpointer=saver).ainvoke({"messages": [("user", "问 A")]}, cfg)
        async with demo.open_saver(db) as saver:  # 新连接、新图实例：记忆只能来自 db
            await build().compile(checkpointer=saver).ainvoke({"messages": [("user", "追问 B")]}, cfg)
        return model.seen

    assert asyncio.run(scene()) == [1, 3]  # 第二段一次看到 3 条：A + 回声 + B


async def _pause_scene(tmp_path, thread: str) -> tuple[dict, StateSnapshot, int]:  # noqa: ANN001
    """start 侧：把 ESCALATE 单打到人审门暂停，返回 (invoke 结果, 快照, 模型请求数)。"""
    claim = "CLM-2026-0003"
    first_turn, advice_json, _expected = review_rules.script_for(claim)
    db = str(tmp_path / f"{thread}.sqlite3")
    cfg = demo.thread_config(thread)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        async with demo.open_saver(db) as saver:
            graph = demo.build_graph(demo.model_for_url(ep.url), checkpointer=saver)
            result: dict = await graph.ainvoke({"messages": demo.initial_messages(claim)}, cfg)
            snapshot = await graph.aget_state(cfg)
        return result, snapshot, len(ep.requests)


def test_escalate_pauses_at_human_gate_with_payload(tmp_path) -> None:  # noqa: ANN001
    """ESCALATE 单在人审门暂停：next/interrupts/events/模型请求四件证据。"""
    result, snapshot, requests = asyncio.run(_pause_scene(tmp_path, "pause-test"))
    assert "advice" not in result  # 图没跑完：finalize 没执行，advice 键不存在
    assert snapshot.next == ("human_gate",)
    assert [i.value for i in snapshot.interrupts] == [{"claim_id": "CLM-2026-0003", "reason": "REJECT:INVALID_AMOUNT"}]
    assert snapshot.metadata is not None
    assert (snapshot.metadata.get("source"), snapshot.metadata.get("step")) == ("loop", 3)
    assert snapshot.values["events"] == ["reviewer", "tools", "reviewer"]
    assert requests == 2


async def _resume_flow(  # noqa: ANN001
    tmp_path, decision: Literal["approve", "deny"]
) -> tuple[demo.ReviewOutcome, list[str], int, int]:
    """「杀进程」的等价模拟：进程 1 跑到暂停退出 endpoint；进程 2 新 endpoint + 新图 + 同一 db 恢复。"""
    claim = "CLM-2026-0003"
    first_turn, advice_json, _expected = review_rules.script_for(claim)
    db = str(tmp_path / f"resume-{decision}.sqlite3")
    cfg = demo.thread_config(f"resume-{decision}")
    with MockLLMEndpoint() as ep1:
        ep1.script_tool_calls(first_turn)
        ep1.script_text(advice_json)
        async with demo.open_saver(db) as saver:
            await demo.build_graph(demo.model_for_url(ep1.url), checkpointer=saver).ainvoke(
                {"messages": demo.initial_messages(claim)}, cfg
            )
    with MockLLMEndpoint() as ep2:  # 全新端点：进程 1 的剧本对它不存在
        async with demo.open_saver(db) as saver:
            graph2 = demo.build_graph(demo.model_for_url(ep2.url), checkpointer=saver)
            snapshot = await graph2.aget_state(cfg)
            paused = demo.parse_advice_text(snapshot.values["messages"][-1].content)
            assert paused is not None
            ep2.script_text(demo.post_human_advice(paused, decision).model_dump_json())
            result: dict = await graph2.ainvoke(Command(resume=decision), cfg)
        sent = len(ep2.requests[0]["messages"]) if ep2.requests else 0
    return result["advice"], result["events"], len(ep2.requests), sent


def test_resume_approve_on_fresh_graph_instance(tmp_path) -> None:  # noqa: ANN001
    outcome, events, requests, sent = asyncio.run(_resume_flow(tmp_path, "approve"))
    assert (outcome.decision, outcome.reason, outcome.human) == ("APPROVE", "PASS", "approve")
    assert outcome.remaining_cents == 40000  # 预算镜像：人工放行不改变余额
    assert events == ["reviewer", "tools", "reviewer", "human_gate", "reviewer", "finalize"]
    assert requests == 1  # 恢复侧只差最后一轮收束
    assert sent == 7  # system/user/ai(tool_calls)/tool/tool/ai/人工决策——历史全部来自 db


def test_resume_deny_on_fresh_graph_instance(tmp_path) -> None:  # noqa: ANN001
    outcome, events, requests, _sent = asyncio.run(_resume_flow(tmp_path, "deny"))
    assert (outcome.decision, outcome.reason, outcome.human) == ("REJECT", "REJECT:HUMAN_DENIED", "deny")
    assert events == ["reviewer", "tools", "reviewer", "human_gate", "reviewer", "finalize"]
    assert requests == 1


def test_non_escalate_runs_through_without_pause(tmp_path) -> None:  # noqa: ANN001
    """非 ESCALATE 单零暂停：一跑到底，human=skipped，没有第三次模型请求。"""
    claim = "CLM-2026-0004"
    first_turn, advice_json, _expected = review_rules.script_for(claim)
    db = str(tmp_path / "skip.sqlite3")
    cfg = demo.thread_config("skip-test")

    async def scene() -> tuple[demo.ReviewOutcome, StateSnapshot, int]:
        with MockLLMEndpoint() as ep:
            ep.script_tool_calls(first_turn)
            ep.script_text(advice_json)
            async with demo.open_saver(db) as saver:
                graph = demo.build_graph(demo.model_for_url(ep.url), checkpointer=saver)
                result: dict = await graph.ainvoke({"messages": demo.initial_messages(claim)}, cfg)
                snapshot = await graph.aget_state(cfg)
            return result["advice"], snapshot, len(ep.requests)

    outcome, snapshot, requests = asyncio.run(scene())
    assert (outcome.decision, outcome.reason, outcome.human) == ("REJECT", "REJECT:INVOICE_INVALID", "skipped")
    assert snapshot.next == () and not snapshot.interrupts  # 跑完了：无暂停点
    assert requests == 2


def test_history_lists_every_superstep_up_to_pause(tmp_path) -> None:  # noqa: ANN001
    """state history：从 step=-1 的 input 快照到暂停点，next 就是每一拍要跑的节点。"""
    _result, _snapshot, _requests = asyncio.run(_pause_scene(tmp_path, "hist-test"))

    async def scene() -> list[tuple[object, tuple[str, ...]]]:
        db = str(tmp_path / "hist-test.sqlite3")
        cfg = demo.thread_config("hist-test")
        async with demo.open_saver(db) as saver:
            graph = demo.build_graph(demo.model_for_url("http://127.0.0.1:1"), checkpointer=saver)
            history = [snap async for snap in graph.aget_state_history(cfg)]
        return [((snap.metadata or {}).get("step"), snap.next) for snap in reversed(history)]

    steps = asyncio.run(scene())
    assert steps == [
        (-1, ("__start__",)),
        (0, ("reviewer",)),
        (1, ("tools",)),
        (2, ("reviewer",)),
        (3, ("human_gate",)),
    ]


def test_static_interrupt_before_tools_pauses_without_payload(tmp_path) -> None:  # noqa: ANN001
    """静态中断对照：interrupt_before 在节点边界摁停（无 payload），invoke(None) 放行。"""
    import step5_static

    claim = "CLM-2026-0001"
    first_turn, advice_json, _expected = review_rules.script_for(claim)
    db = str(tmp_path / "static.sqlite3")
    cfg = demo.thread_config("static-test")

    async def scene() -> tuple[StateSnapshot, demo.ReviewOutcome, int, int]:
        with MockLLMEndpoint() as ep:
            ep.script_tool_calls(first_turn)
            ep.script_text(advice_json)
            async with demo.open_saver(db) as saver:
                graph = step5_static.build_static_graph(demo.model_for_url(ep.url), saver)
                await graph.ainvoke({"messages": demo.initial_messages(claim)}, cfg)
                snapshot = await graph.aget_state(cfg)
                first_requests = len(ep.requests)
                result: dict = await graph.ainvoke(None, cfg)  # 静态恢复：不带值
            return snapshot, result["advice"], first_requests, len(ep.requests)

    snapshot, outcome, first_requests, total = asyncio.run(scene())
    assert snapshot.next == ("tools",) and not snapshot.interrupts  # 停在节点之前，没有 payload
    assert first_requests == 1
    assert (outcome.decision, outcome.reason, outcome.human) == ("APPROVE", "PASS", "skipped")
    assert total == 2  # 恢复后 tools → reviewer（第 2 次模型请求）→ finalize


def test_run_review_covers_all_claims() -> None:
    """统一入口逐单：非 ESCALATE 与规则表全等；ESCALATE 按人审决定收口。"""
    for claim in (c["id"] for c in mock_tools.claims_table()):
        _first, _text, expected = review_rules.script_for(claim)
        if expected.decision == "ESCALATE":
            outcome = asyncio.run(demo.run_review(claim, "deny"))
            assert (outcome.decision, outcome.reason, outcome.human) == ("REJECT", "REJECT:HUMAN_DENIED", "deny")
        else:
            outcome = asyncio.run(demo.run_review(claim))
            assert (outcome.decision, outcome.reason, outcome.remaining_cents) == (
                expected.decision,
                expected.reason,
                expected.remaining_cents,
            )
            assert outcome.human == "skipped"
