"""真实端点冒烟：主 agent → A2A 计税 → HITL 审批（自动批准）→ A2A 申报 → 回执。

前置条件：
1. .env 已配置可用的 LLM 端点（OPENAI_BASE_URL / OPENAI_API_KEY / MODEL_NAME）
2. 两个 A2A server 已启动（bash scripts/start_all.sh）

用法：uv run python scripts/smoke.py
"""

from __future__ import annotations

import asyncio
import re
import sys
import uuid
from pathlib import Path

from langgraph.types import Command
from tax_main.state import TaxContext

from shared.config import AGENT_REGISTRY, llm_env, load_env


async def precheck() -> None:
    """冒烟前置检查：LLM 端点变量 + 两个 A2A server 在线。"""
    load_env()
    llm_env()  # 缺变量直接抛 RuntimeError

    import httpx

    async with httpx.AsyncClient() as http:
        for endpoint in AGENT_REGISTRY.values():
            url = f"{endpoint.base_url}/.well-known/agent-card.json"
            try:
                await http.get(url, timeout=3)
            except httpx.HTTPError as exc:
                raise SystemExit(
                    f"{endpoint.title} 不可达（{url}）：{exc.__class__.__name__}。请先运行 bash scripts/start_all.sh"
                ) from exc
    print("[precheck] LLM 三变量就绪，两个 A2A server 在线\n")


async def run_once(graph, payload, config, context):
    """跑一次 ainvoke；返回 (result, interrupt_value_or_None)。"""
    result = await graph.ainvoke(payload, config=config, context=context)
    interrupts = result.get("__interrupt__")
    if interrupts:
        value = interrupts[0].value
        print("[HITL] 触发人工审批（冒烟模式自动批准）：")
        for request in getattr(value, "get", lambda *_: [])("action_requests", []):
            print(f"    工具 {request.get('name')}，参数 {str(request.get('args'))[:160]}")
        return result, value
    return result, None


async def main() -> int:
    await precheck()

    from langchain_core.messages import AIMessage
    from tax_main.agent import build_graph

    from shared.llm import build_chat_model

    graph = build_graph(build_chat_model())
    context = TaxContext(operator="OP-SMOKE", taxpayer_id="T2025-001")
    config = {"configurable": {"thread_id": f"smoke-{uuid.uuid4().hex[:8]}"}}
    task = (
        "请为在办纳税人 T2025-001（张三）办理 2025 年度个税年度汇算并提交申报："
        "先计算应补(退)税额；操作员已提前确认计税结论，无需再次向我确认，算完直接提交申报，"
        "最后告诉我受理回执号。"
    )
    print(f"[smoke] 任务：{task}\n")

    result, value = await run_once(graph, {"messages": [{"role": "user", "content": task}]}, config, context)
    while value is not None:  # HITL 审批循环（冒烟 = 自动批准）
        result, value = await run_once(graph, Command(resume={"decisions": [{"type": "approve"}]}), config, context)

    transcript = "\n".join(str(m.content) for m in result.get("messages", []) if isinstance(m, AIMessage) and m.content)
    print("\n[smoke] 最终回复（最后一条）：")
    final = [m for m in result.get("messages", []) if isinstance(m, AIMessage) and m.content]
    print(final[-1].content if final else "（无）")

    # 断言要严格：真实回执号格式（RCP-十六进制12位）+ 申报草稿真实落盘，
    # 避免 transcript 里提到"RCP- 开头的回执号"字样造成误报
    receipts = re.findall(r"RCP-[0-9A-F]{12}", transcript)
    draft_name = "return_draft_T2025-001_2025.json"
    draft_file = Path(__file__).resolve().parent.parent / "agents/filing/tax_filing/workspace" / draft_name
    if receipts and draft_file.exists():
        print(f"\n[smoke] PASS：全链路跑通，回执 {receipts[0]}，草稿已落盘 {draft_name}")
        return 0
    print("\n[smoke] FAIL：未见真实受理回执或草稿未落盘——请检查上方 transcript 与 server 日志")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
