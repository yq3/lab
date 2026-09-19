"""Step 3 讲义演示：子代理——handoff-as-tool 的 harness 版。

四件事（全部用 ep.requests / messages 取证）：
  A. task 工具的描述里挂着子代理目录：默认还自动加了一个 general-purpose；
  B. 子代理的轮次是独立的模型调用（R2/R3），工具清单里没有 task——不能再转交；
  C. 隔离性：子代理的 user 消息只有任务描述，看不见主代理的对话历史；
  D. 主代理只收到子代理的最终报告（作为 task 工具的 ToolMessage 回喂）。

源码对应：deepagents/middleware/subagents.py 的 _build_task_tool（task 工具
由 subagents 列表编译而来）、_return_command_with_state_update（取最后一条
非空 AIMessage 文本回喂）。

用法：uv run python code/demo_subagent.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo  # noqa: E402


def main() -> None:
    print("== 同题 demo 的子代理轨迹（CLM-2026-0002） ==")
    _, trace = asyncio.run(demo.run_review_with_trace("CLM-2026-0002"))
    requests, state = trace["requests"], trace["state"]

    print("\n== A. task 工具描述里的子代理目录 ==")
    task_tool = next(t for t in requests[0]["tools"] if t["function"]["name"] == "task")
    for line in task_tool["function"]["description"].splitlines():
        if line.startswith("Specify"):  # 目录区结束，后面是使用守则
            break
        if line.startswith("- "):
            print("   ", line[:100])

    print("\n== B. 五轮模型调用，谁是主代理谁是子代理？ ==")
    for i, req in enumerate(requests):
        names = [t["function"]["name"] for t in req["tools"]]
        who = "子代理（无 task，不能再转交）" if "task" not in names else "主代理"
        print(f"  R{i + 1} [{who}] 工具: {names}")

    print("\n== C. 隔离性：R3（子代理收尾轮）发给模型的消息 ==")
    for m in requests[2]["messages"]:
        content = m.get("content") or ""
        if isinstance(content, list):
            content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
        text = str(content).replace("\n", " ")[:80]
        role = m.get("role") or ("tool" if m.get("tool_call_id") else "?")
        print(f"  {role}: {text}")
    print("  —— 子代理的第一条 human 消息就是任务描述本身，主代理的对话历史没有传进来")

    print("\n== D. 主代理的视角：task 工具的回喂 ==")
    from langchain_core.messages import ToolMessage  # noqa: PLC0415

    task_msg = next(m for m in state["messages"] if isinstance(m, ToolMessage) and m.tool_call_id == "call_task")
    print(f"  task 工具回喂: {task_msg.content}")
    print("  —— 子代理的中间轮次（R2 的 verify_invoice、R3 的报告过程）对主代理不可见")


if __name__ == "__main__":
    main()
