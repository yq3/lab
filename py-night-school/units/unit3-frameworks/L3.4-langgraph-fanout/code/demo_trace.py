"""Step2 轮次轨迹解剖：prebuilt agent 的逐轮证据（讲义 §3 的实跑产出）。

离线（默认）：MockLLMEndpoint + review_rules 剧本，行为确定性——stream 轨迹、
模型请求逐轮解剖（消息构成 / 绑定工具 schema / 回喂的 ToolMessage）、CALL_LOG 取证。
真实端点（--real）：读 .env 三变量，跑同一个装配（一行不改）。

langsmith 追踪：不设 LANGSMITH_* 环境变量即默认关闭、零外发（与 L3.2 相同）。
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
    print(f"== L3.4 prebuilt 审查 agent：{claim_id}（离线剧本） ==")
    print("装配: create_react_agent(ChatOpenAI, [check_budget, verify_invoice], prompt=SYSTEM_PROMPT)")
    print(f"图节点: {sorted(demo.build_agent(demo.model_for_url('http://unused.local/v1')).get_graph().nodes)}\n")
    first_turn, advice_json, expected = review_rules.script_for(claim_id)
    mock_tools.CALL_LOG.clear()
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        agent = demo.build_agent(demo.model_for_url(ep.url))
        print("== superstep 轨迹（stream_mode='updates'） ==")
        final: dict = {}
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": demo.user_brief(claim_id)}]},
            config={"recursion_limit": demo.RECURSION_LIMIT},
            stream_mode="updates",
        ):
            for node, update in chunk.items():
                final = update if update else final
                new = update.get("messages", []) if update else []
                for message in new:
                    call_id = getattr(message, "tool_call_id", None)
                    suffix = f"  (id={call_id})" if call_id else ""
                    print(f"  [{node:>6}] + {_brief(message)}{suffix}")
        requests = ep.requests
    advice_out: Advice = Advice.model_validate_json(final["messages"][-1].content.strip())
    print("\n== 模型请求逐轮解剖（ep.requests）——对照 L2.3 循环十行 ==")
    for number, request in enumerate(requests, start=1):
        roles = [m["role"] for m in request["messages"]]
        tools = [t["function"]["name"] for t in request.get("tools", [])]
        print(f"  第 {number} 次请求: {len(roles)} 条消息 {roles}；携带工具 schema {tools}")
    print("  <- 第 2 次请求里的 2 条 tool 消息就是回喂：历史全量重发 + 工具结果垫后（L2.1 §2.2）")
    print("\n== 收口 ==")
    print(f"  advice   : {advice_out.decision} / {advice_out.reason} / 剩余 {advice_out.remaining_cents} 分")
    print(f"  （剧本预期: {expected.decision} / {expected.reason} / 剩余 {expected.remaining_cents} 分）")
    print(f"  工具执行 : {mock_tools.CALL_LOG}（真实执行，不是剧本自说自话）")


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
    agent = demo.build_agent(demo.model_for_url(env["OPENAI_BASE_URL"], env["OPENAI_API_KEY"], env["MODEL_NAME"]))
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": demo.user_brief(claim_id)}]},
        config={"recursion_limit": demo.RECURSION_LIMIT},
    )
    advice_out: Advice = Advice.model_validate_json(result["messages"][-1].content.strip())
    print(f"== 真实端点（{env['MODEL_NAME']}）审查 {claim_id} ==")
    print(f"  advice : {advice_out.decision} / {advice_out.reason} / 剩余 {advice_out.remaining_cents} 分")
    print(f"  消息史 : {len(result['messages'])} 条；工具真实执行: {sorted(set(mock_tools.CALL_LOG))}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    claim_id = args[0] if args else "CLM-2026-0003"
    if "--real" in sys.argv[1:]:
        asyncio.run(run_real(claim_id))
    else:
        asyncio.run(run_offline(claim_id))


if __name__ == "__main__":
    main()
