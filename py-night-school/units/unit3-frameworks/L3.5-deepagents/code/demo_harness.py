"""Step 1 讲义演示：harness 跑通离线 demo——「默认给了你什么」的取证。

三件事（全部用 ep.requests 取证，不靠背文档）：
  A. 同题 demo 跑通：五轮剧本的消息轨迹 + 结构化收尾 + 底稿落盘；
  B. 默认工具清单：模型第 1 个请求里实际看到的工具列表；
     再用 FilesystemMiddleware(tools=...) 显式收窄（最小权限），对比清单变化；
  C.（可选 --real）真实端点：同样一行 create_deep_agent，模型自己决定轮次。

用法：
  uv run python code/demo_harness.py            # 离线（默认，零 key）
  uv run python code/demo_harness.py --real     # 可选加餐（需配好 .env 三变量）
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import StateBackend  # noqa: E402
from deepagents.middleware.filesystem import FilesystemMiddleware  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import SecretStr  # noqa: E402

import demo  # noqa: E402
import mock_tools  # noqa: E402
from advice import Advice  # noqa: E402
from mock_endpoint import MockLLMEndpoint  # noqa: E402


def _brief(msg: object) -> str:
    """消息的一行摘要（轨迹展示用）。"""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: PLC0415

    if isinstance(msg, AIMessage):
        if msg.tool_calls:
            calls = ", ".join(f"{c['name']}{dict(c['args'])}" for c in msg.tool_calls)
            return f"assistant: [选了工具: {calls}]"
        return f"assistant: {msg.text[:60]}"
    if isinstance(msg, ToolMessage):
        return f"     tool: {str(msg.content)[:70]}  (id={msg.tool_call_id})"
    if isinstance(msg, HumanMessage):
        return f"user: {str(msg.content)[:70]}"
    return f"{type(msg).__name__.lower()}: {str(getattr(msg, 'content', ''))[:70]}"


def part_a_and_b() -> None:
    print("== A. 同题 demo：deepagents 五轮剧本 ==")
    advice, trace = asyncio.run(demo.run_review_with_trace("CLM-2026-0004"))
    requests, state = trace["requests"], trace["state"]
    print(f"模型实际被调用 {len(requests)} 次：")
    for i, req in enumerate(requests):
        names = [t["function"]["name"] for t in req.get("tools", [])]
        print(f"  R{i + 1} 工具清单({len(names)}): {names}")
    print("\n-- 消息轨迹 --")
    for msg in state["messages"]:
        print(" ", _brief(msg))
    print("\n最终 state 键:", sorted(state.keys()))
    print("结构化收尾:", advice)
    print("CALL_LOG（工具真实执行）:", mock_tools.CALL_LOG)
    dossier = state["files"]["/review/CLM-2026-0004.md"]["content"]
    print("底稿内容:\n" + "\n".join("    " + line for line in dossier.splitlines()))

    print("\n== B. 默认工具清单 vs 最小权限收窄 ==")
    with MockLLMEndpoint() as ep:
        model = ChatOpenAI(base_url=ep.url, api_key=SecretStr(ep.api_key), model=ep.model)
        # 默认：不传 middleware——create_deep_agent 自己装全套 FilesystemMiddleware
        default_agent = demo.build_agent(model)
        ep.script_text("收到。")  # 一轮就收尾，只为取证请求里的工具清单
        asyncio.run(default_agent.ainvoke({"messages": [HumanMessage(content="noop")]}))
        default_tools = [t["function"]["name"] for t in ep.requests[0]["tools"]]

        # 收窄：自定义 FilesystemMiddleware 按 name 原位替换默认件（最小权限）
        narrowed_agent = create_deep_agent(
            model=model,
            tools=[mock_tools.check_budget],
            middleware=[
                FilesystemMiddleware(backend=StateBackend(), tools=["ls", "read_file", "write_file"]),
            ],
            response_format=Advice,
        )
        ep.requests.clear()
        ep.script_text("收到。")
        asyncio.run(narrowed_agent.ainvoke({"messages": [HumanMessage(content="noop")]}))
        narrowed_tools = [t["function"]["name"] for t in ep.requests[0]["tools"]]
    print(f"  默认清单({len(default_tools)}): {default_tools}")
    print(f"  收窄清单({len(narrowed_tools)}): {narrowed_tools}")
    print("  —— glob/grep/edit_file/delete 从模型的视野里消失了（对照 Spring 自动装配：默认全开，生产要显式收窄）")


def part_real() -> None:
    print("== C. 真实端点加餐（--real） ==")
    env: dict[str, str] = {}
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                env[key.strip()] = value.split("#")[0].strip()
    base_url = env.get("OPENAI_BASE_URL", "")
    api_key = env.get("OPENAI_API_KEY", "")
    model_name = env.get("MODEL_NAME", "")
    if not (base_url and api_key and model_name):
        print("  .env 三变量不全（OPENAI_BASE_URL / OPENAI_API_KEY / MODEL_NAME），跳过。")
        return
    model = ChatOpenAI(base_url=base_url, api_key=SecretStr(api_key), model=model_name)
    agent = demo.build_agent(model)
    question = "请审查报销单 CLM-2026-0001：客户拜访：交通 + 工作餐，明细 [1200, 3500, 2400] 分，部门 SALES。"
    result = asyncio.run(agent.ainvoke({"messages": [HumanMessage(content=question)]}))
    print("-- 消息轨迹（模型自己决定轮次） --")
    for msg in result["messages"]:
        print(" ", _brief(msg))
    structured = result.get("structured_response")
    print("结构化收尾:", structured)
    print("底稿文件:", sorted((result.get("files") or {}).keys()))


if __name__ == "__main__":
    if "--real" in sys.argv:
        part_real()
    else:
        part_a_and_b()
