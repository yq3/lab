"""L3.3 压轴实验：暂停 → 杀进程 → 恢复（真分进程版，讲义 Step2 的本体）。

两个子命令各自是一个独立进程，共享的唯一东西是同一个 sqlite 文件：
- start  CLM-2026-0003：跑到 human_gate 暂停，打印 thread_id 与恢复命令后正常退出
  （进程退出 = 内存里的图、模型连接、剧本全部消失——「杀进程」不需要 kill -9）；
- approve|deny <thread-id>：另一个进程打开同一个 db，Command(resume=...) 注入人工决策，
  图从暂停点继续跑到 finalize。

离线剧本：start 布置两份（两轮审查）；approve/deny 在自己进程里布置一份（人审后收束）——
恢复侧的 MockLLMEndpoint 是全新实例，start 的剧本对它不存在（无状态模型 + 有状态图）。
--real：读 .env 三变量跑真实端点（剧本全部不布置，模型自己决策）。

用法（bash 与 PowerShell 同形，分条执行）：
    uv run python code/demo_resume.py start CLM-2026-0003
    uv run python code/demo_resume.py approve claim-CLM-2026-0003-<时间戳>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Literal

from langgraph.types import Command

import demo
import review_rules
from mock_endpoint import MockLLMEndpoint

DEFAULT_DB = "checkpoints/demo.sqlite3"


def _load_env() -> dict[str, str]:
    """极简 .env 读取（L2.1 env_loader 的迷你版）：KEY=VALUE 行，忽略注释。"""
    env: dict[str, str] = {}
    path = Path(".env")
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.split(" #")[0].strip()
    return env


def _real_model():
    env = _load_env()
    missing = [k for k in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "MODEL_NAME") if not env.get(k)]
    if missing:
        print(f"缺 .env 变量: {missing}（先 cp .env.example .env 并填写）")
        sys.exit(1)
    return demo.model_for_url(env["OPENAI_BASE_URL"], env["OPENAI_API_KEY"], env["MODEL_NAME"])


async def cmd_start(claim_id: str, db: str, real: bool) -> str:
    """进程 1：跑到人审门暂停后退出。返回 thread_id（打印给学员，用于恢复命令）。"""
    thread_id = f"claim-{claim_id}-{time.strftime('%H%M%S')}"
    cfg = demo.thread_config(thread_id)
    print(f"== 进程 1（pid {os.getpid()}）：start {claim_id} ==")
    print(f"db: {db}（目录不存在会自动创建）")
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    if real:
        async with demo.open_saver(db) as saver:
            graph = demo.build_graph(_real_model(), checkpointer=saver)
            async for chunk in graph.astream({"messages": demo.initial_messages(claim_id)}, cfg):
                for node in chunk:
                    print(f"  [{node}]")
            snapshot = await graph.aget_state(cfg)
    else:
        first_turn, advice_json, _expected = review_rules.script_for(claim_id)
        with MockLLMEndpoint() as ep:
            ep.script_tool_calls(first_turn)
            ep.script_text(advice_json)
            async with demo.open_saver(db) as saver:
                graph = demo.build_graph(demo.model_for_url(ep.url), checkpointer=saver)
                async for chunk in graph.astream({"messages": demo.initial_messages(claim_id)}, cfg):
                    for node in chunk:
                        print(f"  [{node}]")
                snapshot = await graph.aget_state(cfg)
            requests = len(ep.requests)
        print(f"模型请求: {requests} 次（剧本已耗尽，本进程退出后不复存在）")
    if not snapshot.next:
        print(f"单据 {claim_id} 未触发人审（非 ESCALATE），一跑到底：{snapshot.values['advice']}")
        return thread_id
    payload = snapshot.interrupts[0].value if snapshot.interrupts else {}
    print(f"图暂停：next={snapshot.next}，step={(snapshot.metadata or {}).get('step')}")
    print(f"interrupt payload: {payload}")
    print(f"thread_id: {thread_id}")
    print("本进程即将退出——内存里的图、模型连接、剧本全部消失，存活的只有 db 里的 checkpoint。")
    print("恢复命令（另开终端或紧接着执行，是新进程）：")
    print(f"  uv run python code/demo_resume.py approve {thread_id}")
    return thread_id


async def cmd_resume(decision: Literal["approve", "deny"], thread_id: str, db: str, real: bool) -> None:
    """进程 2：同一个 db、另一个进程，Command(resume=decision) 恢复。"""
    cfg = demo.thread_config(thread_id)
    print(f"== 进程 2（pid {os.getpid()}）：{decision} {thread_id} ==")
    print(f"db: {db}（与进程 1 是同一个文件，此外两进程无任何共享）")
    if real:
        async with demo.open_saver(db) as saver:
            graph = demo.build_graph(_real_model(), checkpointer=saver)
            snapshot = await graph.aget_state(cfg)
            if not snapshot.next:
                print("该 thread 没有暂停点（已跑完或不存在）——恢复无从谈起。")
                return
            result: dict = await graph.ainvoke(Command(resume=decision), cfg)
    else:
        with MockLLMEndpoint() as ep:  # 全新端点实例：start 的剧本不在这里
            async with demo.open_saver(db) as saver:
                graph = demo.build_graph(demo.model_for_url(ep.url), checkpointer=saver)
                snapshot = await graph.aget_state(cfg)
                if not snapshot.next:
                    print("该 thread 没有暂停点（已跑完或不存在）——恢复无从谈起。")
                    return
                # 从暂停点反推单据：最后一条 AI 消息就是 reviewer 的 ESCALATE 建议单
                paused = demo.parse_advice_text(snapshot.values["messages"][-1].content)
                if paused is None:
                    print("暂停点状态里解析不出建议单——db 与代码版本不匹配？")
                    return
                final_json = demo.post_human_advice(paused, decision).model_dump_json()
                ep.script_text(final_json)
                print(f"恢复前快照: next={snapshot.next}，interrupts={len(snapshot.interrupts)} 条")
                print(f"从 checkpoint 反推单据: {paused.claim_id}（{paused.reason}）")
                result = await graph.ainvoke(Command(resume=decision), cfg)
            requests = len(ep.requests)
            sent = len(ep.requests[0]["messages"]) if ep.requests else 0
        print(f"模型请求: {requests} 次，发送 {sent} 条消息——历史全部来自 db，剧本只供最后一轮台词")
    outcome: demo.ReviewOutcome = result["advice"]
    print(
        f"ReviewOutcome: {outcome.decision} / {outcome.reason} / 剩余 {outcome.remaining_cents} 分"
        f" / human={outcome.human}"
    )
    print(f"events: {result['events']}")
    print("两次 invoke 分属两个进程：状态一分不少地活过了进程死亡——这就是 HITL 的机制底座。")


def main() -> None:
    parser = argparse.ArgumentParser(description="暂停 → 杀进程 → 恢复（真分进程演示）")
    parser.add_argument("--db", default=DEFAULT_DB, help="checkpoint sqlite 文件（两个进程必须一致）")
    parser.add_argument("--real", action="store_true", help="用 .env 真实端点（默认离线剧本）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_start = sub.add_parser("start", help="跑到人审门暂停后退出")
    p_start.add_argument("claim_id", nargs="?", default="CLM-2026-0003")
    p_resume = sub.add_parser("approve", help="人工放行，恢复暂停的图")
    p_deny = sub.add_parser("deny", help="人工拒绝，恢复暂停的图")
    p_resume.add_argument("thread_id")
    p_deny.add_argument("thread_id")
    args = parser.parse_args()
    if args.cmd == "start":
        asyncio.run(cmd_start(args.claim_id, args.db, args.real))
    else:
        decision: Literal["approve", "deny"] = "deny" if args.cmd == "deny" else "approve"
        asyncio.run(cmd_resume(decision, args.thread_id, args.db, args.real))


if __name__ == "__main__":
    main()
