"""主 agent 交互 CLI：astream 流式渲染 + HITL 审批交互。

用法：
    uv run python -m tax_main.cli                          # 交互模式
    uv run python -m tax_main.cli --task "..."             # 无头模式（跑完即退）
    uv run python -m tax_main.cli --task "..." --auto-approve   # 无头 + 审批自动通过（冒烟用）

展示点：
- graph.astream(stream_mode=["messages", "updates"])：token 级文本流 + 节点级更新
- interrupt → 人工审批 → Command(resume={"decisions": [...]}) 恢复（checkpointer 支撑）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from typing import Any

from langgraph.types import Command

from shared.config import load_env
from tax_main.agent import build_graph
from tax_main.state import TaxContext

EXIT_COMMANDS = {"exit", "quit", "q", "退出"}


def short_args(args: dict[str, Any], limit: int = 160) -> str:
    """工具参数摘要（打断长 JSON）。"""
    try:
        text = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(args)
    return text if len(text) <= limit else f"{text[:limit]}…"


def render_todos(todos: list[dict[str, Any]]) -> None:
    """write_todos 的计划看板。"""
    marks = {"completed": "✅", "in_progress": "🔄", "pending": "⬜"}
    lines = [f"  {marks.get(t.get('status', ''), '·')} {t.get('content', '')}" for t in todos]
    print("\n📋 计划：\n" + "\n".join(lines))


def render_update(delta: Any) -> None:
    """节点更新的增量渲染：todos / 工具调用 / 工具结果。"""
    if not isinstance(delta, dict):
        return
    if "todos" in delta:
        render_todos(delta["todos"])
    messages = delta.get("messages")
    if isinstance(messages, list):
        for message in messages:
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                for call in tool_calls:
                    print(f"\n⚙️  调用 {call['name']}({short_args(call.get('args', {}))})")
            elif type(message).__name__ == "ToolMessage":
                preview = str(message.content).replace("\n", " ")
                preview = preview if len(preview) <= 120 else f"{preview[:120]}…"
                print(f"   ← {preview}")


def format_interrupt(value: Any) -> str:
    """渲染 HITL 审批请求（HumanInterrupt：action_requests + allowed_decisions）。"""
    try:
        requests = value["action_requests"]
        allowed = value.get("allowed_decisions", [])
    except (TypeError, KeyError, IndexError):
        return str(value)
    lines = ["\n" + "═" * 60, "⏸  人工审批请求（HITL interrupt）"]
    for request in requests:
        lines.append(f"  工具：{request['name']}")
        lines.append(f"  参数：{short_args(request.get('args', {}), limit=400)}")
        desc = request.get("description")
        if desc:
            lines.append(f"  说明：{str(desc)[:200]}")
    lines.append(f"  允许的决策：{allowed}")
    lines.append("═" * 60)
    return "\n".join(lines)


async def stream_once(
    graph,
    payload: Any,
    config: dict,
    context: TaxContext | None,
    auto_approve: bool,
) -> tuple[bool, Any]:
    """流式执行一次图调用。

    Returns:
        (interrupted, interrupt_value)：interrupted=True 表示需要审批后 resume。
    """
    interrupted = False
    interrupt_value: Any = None
    async for mode, chunk in graph.astream(
        payload, config=config, context=context, stream_mode=["messages", "updates"]
    ):
        if mode == "messages":
            message, _meta = chunk
            content = message.content
            if isinstance(content, str) and content and not getattr(message, "tool_call_chunks", None):
                print(content, end="", flush=True)
        else:  # updates
            for node, delta in chunk.items():
                if node == "__interrupt__":
                    interrupted = True
                    interrupts = delta if isinstance(delta, (list, tuple)) else (delta,)
                    interrupt_value = interrupts[0].value if interrupts else None
                else:
                    render_update(delta)
    print()
    return interrupted, interrupt_value


async def approve_loop(graph, config: dict, context: TaxContext | None, auto_approve: bool, initial_value: Any) -> None:
    """审批交互循环：approve / reject(带理由) → resume，直到本轮不再需要审批。"""
    value = initial_value
    while True:
        print(format_interrupt(value))
        if auto_approve:
            decision: dict[str, Any] = {"type": "approve"}
            print("（--auto-approve：自动批准）")
        else:
            answer = input("批准该操作吗？[y 批准 / n 拒绝 / 理由文本=拒绝并反馈] > ").strip()
            if answer.lower() in ("y", "yes", "批准"):
                decision = {"type": "approve"}
            elif answer.lower() in ("n", "no", "拒绝"):
                decision = {"type": "reject", "message": "操作员拒绝了本次操作"}
            else:
                decision = {"type": "reject", "message": f"操作员反馈：{answer}"}

        interrupted, value = await stream_once(
            graph, Command(resume={"decisions": [decision]}), config, context, auto_approve
        )
        if not interrupted:
            return


async def chat_loop(args: argparse.Namespace) -> None:
    from shared.llm import build_chat_model  # 有真实端点时才构建模型

    graph = build_graph(build_chat_model())
    context = TaxContext(operator=args.operator, taxpayer_id=args.taxpayer_id)
    config = {"configurable": {"thread_id": f"cli-{uuid.uuid4().hex[:8]}"}}
    print(
        f"计税申报助手（thread={config['configurable']['thread_id']}，操作员={args.operator}，在办纳税人={args.taxpayer_id}）"
    )
    print("输入 exit/quit 退出。\n")

    if args.task:  # 无头模式：单任务跑完即退
        interrupted, value = await stream_once(
            graph, {"messages": [{"role": "user", "content": args.task}]}, config, context, args.auto_approve
        )
        if interrupted:
            await approve_loop(graph, config, context, args.auto_approve, value)
        return

    while True:
        try:
            user_text = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_text or user_text.lower() in EXIT_COMMANDS:
            break
        interrupted, value = await stream_once(
            graph, {"messages": [{"role": "user", "content": user_text}]}, config, context, args.auto_approve
        )
        if interrupted:
            await approve_loop(graph, config, context, args.auto_approve, value)
        print()
    print("再见。")


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="计税申报助手 CLI")
    parser.add_argument("--task", default=None, help="无头模式：直接执行该任务后退出")
    parser.add_argument("--taxpayer-id", default="T2025-001", help="在办纳税人编号（注入 context_schema）")
    parser.add_argument("--operator", default="OP-9001", help="操作员工号（注入 context_schema）")
    parser.add_argument("--auto-approve", action="store_true", help="HITL 审批自动通过（冒烟测试用）")
    args = parser.parse_args()
    asyncio.run(chat_loop(args))


if __name__ == "__main__":
    main()
