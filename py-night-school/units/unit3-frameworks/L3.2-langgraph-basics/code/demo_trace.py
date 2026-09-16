"""Step3 离线 demo 全程轨迹：stream 模式逐 superstep 打印（讲义 §3 的实跑产出）。

离线（默认）：MockLLMEndpoint + review_rules 剧本，行为确定性——events 审计流水、
消息史、模型请求次数每次完全一致。真实端点（--real）：读 .env 三变量，跑同一张图。

langsmith 追踪：不设 LANGSMITH_* 环境变量即默认关闭、零外发——对照 L3.1 开课先关 trace。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import demo
import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint


def _brief(message) -> str:  # noqa: ANN001 -- langchain 消息对象，讲义脚本从简
    """把一条消息压成一行轨迹（role + 内容摘要）。"""
    role = type(message).__name__.removesuffix("Message").lower()
    if getattr(message, "tool_calls", None):
        names = ", ".join(c["name"] for c in message.tool_calls)
        return f"{role}: [并行选了工具: {names}]"
    text = str(message.content).replace("\n", " ")
    return f"{role}: {text[:44]}{'…' if len(text) > 44 else ''}"


async def run_offline(claim_id: str) -> None:
    print(f"== L3.2 StateGraph 审查 agent：{claim_id}（离线剧本） ==")
    print("图: START → reviewer ─条件边→ tools → reviewer（成环）；无 tool_calls → finalize → END\n")
    first_turn, advice_json, expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        graph = demo.build_graph(demo.model_for_url(ep.url))
        print("== superstep 轨迹（stream_mode='values'，每步给全量状态） ==")
        final: dict = {}
        seen = 0  # 上一状态的消息数——本步新增的就是刚写的
        async for state in graph.astream(
            {"messages": demo.initial_messages(claim_id)},
            config={"recursion_limit": demo.RECURSION_LIMIT},
            stream_mode="values",
        ):
            final = state
            if not state.get("events"):
                continue  # values 模式的首块是入口状态（还没执行任何节点）
            node = state["events"][-1]  # 审计流水末位 = 刚执行完的节点
            if len(state["messages"]) > seen:
                for message in state["messages"][seen:]:
                    print(f"  [{node:>8}] + {_brief(message)}")
            else:
                print(f"  [{node:>8}] （不新增消息——只读状态收束，advice 键被写入）")
            seen = len(state["messages"])
        requests = ep.requests
    advice_out: Advice = final["advice"]
    print("\n== 收口 ==")
    print(f"  advice   : {advice_out.decision} / {advice_out.reason} / 剩余 {advice_out.remaining_cents} 分")
    print(f"  （剧本预期: {expected.decision} / {expected.reason} / 剩余 {expected.remaining_cents} 分）")
    print(f"  events   : {final['events']}")
    print(f"  模型请求 : {len(requests)} 次（第 1 次带 2 个工具 schema；第 2 次带 2 条 ToolMessage 回喂）")
    tools_seen = [t["function"]["name"] for t in requests[0]["tools"]]
    print(f"  绑定工具 : {tools_seen}（bind_tools 自动生成的 schema，对照 L2.2 手写版）")


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


async def run_real(claim_id: str) -> None:
    env = _load_env()
    missing = [k for k in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "MODEL_NAME") if not env.get(k)]
    if missing:
        print(f"缺 .env 变量: {missing}（先 cp .env.example .env 并填写）")
        return
    graph = demo.build_graph(demo.model_for_url(env["OPENAI_BASE_URL"], env["OPENAI_API_KEY"], env["MODEL_NAME"]))
    result = await graph.ainvoke(
        {"messages": demo.initial_messages(claim_id)},
        config={"recursion_limit": demo.RECURSION_LIMIT},
    )
    advice_out: Advice = result["advice"]
    print(f"== 真实端点（{env['MODEL_NAME']}）审查 {claim_id} ==")
    print(f"  advice : {advice_out.decision} / {advice_out.reason} / 剩余 {advice_out.remaining_cents} 分")
    print(f"  events : {result['events']}")
    print(f"  工具真实执行: {sorted(set(mock_tools.CALL_LOG))}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    claim_id = args[0] if args else "CLM-2026-0004"
    if "--real" in sys.argv[1:]:
        asyncio.run(run_real(claim_id))
    else:
        asyncio.run(run_offline(claim_id))


if __name__ == "__main__":
    main()
