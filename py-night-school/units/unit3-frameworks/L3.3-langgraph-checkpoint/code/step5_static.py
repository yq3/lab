"""Step5（可选）静态中断对照：interrupt_before= 与 interrupt() 的两种暂停。

langgraph 有两套暂停机制，都要求 compile(checkpointer=...)：
- 静态：compile(interrupt_before=["tools"])——编译期点名节点，图在该节点「开跑之前」
  暂停；恢复是 invoke(None, config)——不带任何值（暂停点没有 payload 可言）；
- 动态：节点内部运行期 interrupt(payload)（本课 Step2/3 的机制）——暂停点在节点
  「执行到一半」，payload 随状态落盘，恢复必须 Command(resume=值)。

本脚本对 CLM-2026-0001（干净单）用静态中断在 tools 前摁停，然后 invoke(None) 放行。
选型直觉（讲义 §2 有对照表）：静态适合「按节点一刀切」的审批位（布局固定、每个
请求都要人看），动态适合「按内容判断要不要人审」（本课的 ESCALATE 路由 + interrupt
组合拳——干净单零暂停，脏数据单才摁停）。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

import demo
import review_rules
from mock_endpoint import MockLLMEndpoint


def build_static_graph(model, saver) -> CompiledStateGraph:  # noqa: ANN001 -- 与 demo.build_graph 同构，仅 compile 参数不同
    """与 demo.build_graph 同一张图，compile 多给两个参数：checkpointer + interrupt_before。"""
    builder = StateGraph(demo.ClaimState)
    builder.add_node("reviewer", demo.make_reviewer(model))
    builder.add_node("tools", demo.tools_node)
    builder.add_node("human_gate", demo.human_gate)
    builder.add_node("finalize", demo.finalize)
    builder.add_edge(START, "reviewer")
    builder.add_conditional_edges("reviewer", demo.route_after_reviewer)
    builder.add_edge("tools", "reviewer")
    builder.add_edge("human_gate", "reviewer")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=saver, interrupt_before=["tools"])


async def main() -> None:
    print("== Step5 静态中断：compile(interrupt_before=['tools']) 对照动态 interrupt() ==")
    claim = "CLM-2026-0001"
    first_turn, advice_json, _expected = review_rules.script_for(claim)
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "static.sqlite3")
        cfg = demo.thread_config("static-demo")
        with MockLLMEndpoint() as ep:
            ep.script_tool_calls(first_turn)
            ep.script_text(advice_json)
            async with demo.open_saver(db) as saver:
                graph = build_static_graph(demo.model_for_url(ep.url), saver)
                result: dict = await graph.ainvoke({"messages": demo.initial_messages(claim)}, cfg)
                snapshot = await graph.aget_state(cfg)
                print(f"[第一次 invoke] 停在 {snapshot.next} 之前（step={(snapshot.metadata or {}).get('step')}）")
                print(f"  interrupts = {list(snapshot.interrupts)}   <- 空：静态中断没有 payload")
                print(f"  messages 共 {len(result['messages'])} 条——tools 还没跑，模型只出声过一次")
                first_requests = len(ep.requests)
                result = await graph.ainvoke(None, cfg)  # 恢复不带值：None
                print(
                    f"[invoke(None, config)] 放行到 END：模型共请求 {len(ep.requests)} 次"
                    f"（第一次 {first_requests} 次 + 恢复后 {len(ep.requests) - first_requests} 次）"
                )
                outcome = result["advice"]
                print(f"  ReviewOutcome: {outcome.decision} / {outcome.reason} / human={outcome.human}")
                print(f"  events: {result['events']}")
    print("\n对照：动态 interrupt() 暂停在节点执行到一半（payload 落盘），")
    print("恢复必须 Command(resume=值)——值就是 interrupt() 的返回值；静态恢复传 None 就够。")


if __name__ == "__main__":
    asyncio.run(main())
