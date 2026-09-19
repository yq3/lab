"""Step3 interrupt 双路：approve / deny / skipped 三条路一次看全（单进程对照版）。

对 CLM-2026-0003（脏数据 ESCALATE 单）分别走 approve 与 deny 两条恢复路，
对 CLM-2026-0001（干净单）看「根本不暂停」的第三条路。每组打印：
暂停证据（next / payload）、恢复命令注入、ReviewOutcome、events 审计流水、模型请求次数。

对照 demo_resume.py：那边是两个真进程，这边是同进程两张图 + 同一个 db——
pytest 里的「杀进程」就是用这种等价模拟（讲义 Step2 有说明）。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Literal

from langgraph.types import Command

import demo
import review_rules
from mock_endpoint import MockLLMEndpoint


async def run_gate(claim_id: str, decision: Literal["approve", "deny"]) -> None:
    """跑一条完整的人审路：进程 1 跑到暂停，进程 2（等价模拟）恢复。"""
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "gate.sqlite3")
        thread = f"gate-{claim_id}-{decision}"
        cfg = demo.thread_config(thread)
        first_turn, advice_json, expected = review_rules.script_for(claim_id)
        with MockLLMEndpoint() as ep1:  # 「进程 1」：跑到暂停
            ep1.script_tool_calls(first_turn)
            ep1.script_text(advice_json)
            async with demo.open_saver(db) as saver:
                graph1 = demo.build_graph(demo.model_for_url(ep1.url), checkpointer=saver)
                await graph1.ainvoke({"messages": demo.initial_messages(claim_id)}, cfg)
                snapshot = await graph1.aget_state(cfg)
        print(f"[{claim_id} + {decision}]")
        if not snapshot.next:
            print(f"  非 ESCALATE 单不暂停（expect={expected.decision}），一跑到底：")
            outcome = snapshot.values["advice"]
            print(f"  ReviewOutcome: {outcome.decision} / {outcome.reason} / human={outcome.human}")
            print(f"  events: {snapshot.values['events']}，模型请求 {len(ep1.requests)} 次（零恢复）")
            return
        payload = snapshot.interrupts[0].value
        print(f"  暂停: next={snapshot.next}，payload={payload}，模型请求 {len(ep1.requests)} 次")
        with MockLLMEndpoint() as ep2:  # 「进程 2」：恢复（新端点、新图、同一个 db）
            paused = demo.parse_advice_text(snapshot.values["messages"][-1].content)
            assert paused is not None
            ep2.script_text(demo.post_human_advice(paused, decision).model_dump_json())
            async with demo.open_saver(db) as saver:
                graph2 = demo.build_graph(demo.model_for_url(ep2.url), checkpointer=saver)
                result: dict = await graph2.ainvoke(Command(resume=decision), cfg)
            sent = len(ep2.requests[0]["messages"]) if ep2.requests else 0
        outcome = result["advice"]
        print(f"  恢复: Command(resume={decision!r})，模型再请求 {len(ep2.requests)} 次（带 {sent} 条历史）")
        print(f"  ReviewOutcome: {outcome.decision} / {outcome.reason} / human={outcome.human}")
        print(f"  events: {result['events']}")


async def main() -> None:
    print("== Step3 interrupt 人审门：approve / deny / skipped 三条路 ==")
    print("图: reviewer →(ESCALATE)→ human_gate --暂停--> [人工] --Command(resume)--> reviewer → finalize\n")
    await run_gate("CLM-2026-0003", "approve")
    print()
    await run_gate("CLM-2026-0003", "deny")
    print()
    await run_gate("CLM-2026-0001", "approve")  # 决策参数被无视：这单根本不会暂停


if __name__ == "__main__":
    asyncio.run(main())
