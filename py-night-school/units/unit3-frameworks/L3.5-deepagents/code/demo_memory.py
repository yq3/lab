"""Step 4 讲义演示：MemoryMiddleware——记忆文件如何在请求到达模型前注入 system。

三件事：
  A. 声明 memory=["/memory/AGENTS.md"] + invoke 预置该文件 → 第一个请求的
     system 消息里出现 <agent_memory> 块（记忆正文原文注入）；
  B. hook 时机取证：before_agent 读文件进 state["memory_contents"]（私有字段，
     最终 state 里看不到）；wrap_model_call 把它拼进 system——对照 Java 的
     Filter 链 / Interceptor：请求进模型之前改写请求体；
  C. 记忆条目并不神秘：它就是虚拟文件系统里的一个文件（state["files"] 里能找到）。

源码对应：deepagents/middleware/memory.py 的 before_agent/abefore_agent
（下载 → state）与 wrap_model_call/awrap_model_call（state → system 注入），
MEMORY_SYSTEM_PROMPT 模板的 {agent_memory} 槽位。

用法：uv run python code/demo_memory.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deepagents import create_deep_agent  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import SecretStr  # noqa: E402

import demo  # noqa: E402
import mock_tools  # noqa: E402
from advice import Advice  # noqa: E402
from mock_endpoint import MockLLMEndpoint  # noqa: E402

MEMORY_PATH = "/memory/AGENTS.md"
MEMORY_CONTENT = """# 审查记忆
- 金额一律整数分，报告里禁止出现小数
- 人审清单写到 /review/ 目录，按单号命名
<!-- 这是作者备注，注入前会被剥离（HTML 注释不进 system） -->
"""


def _system_text(request: dict) -> str:
    sysmsg = next((m for m in request["messages"] if m.get("role") == "system"), None)
    if sysmsg is None:
        return ""
    content = sysmsg["content"]
    if isinstance(content, list):  # OpenAI 多模态内容块形态
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return str(content)


async def main() -> None:
    with MockLLMEndpoint() as ep:
        model = ChatOpenAI(base_url=ep.url, api_key=SecretStr(ep.api_key), model=ep.model)
        agent = create_deep_agent(
            model=model,
            tools=[mock_tools.check_budget],
            system_prompt="你是报销单审查助手。",
            memory=[MEMORY_PATH],
            response_format=Advice,
        )
        ep.script_tool_calls([{"id": "call_budget", "name": "check_budget", "arguments": {"dept": "DEV"}}])
        final = {
            "claim_id": "CLM-2026-0003",
            "decision": "ESCALATE",
            "reason": "REJECT:INVALID_AMOUNT",
            "remaining_cents": 40000,
        }
        ep.script_tool_calls([{"id": "call_advice", "name": "Advice", "arguments": final}])
        question = "请审查报销单 CLM-2026-0003（明细 -500 分）。"
        result = await agent.ainvoke(demo.input_with_files(question, {MEMORY_PATH: {"content": MEMORY_CONTENT}}))

    print("== A. 第一个请求的 system 消息（节选） ==")
    text = _system_text(ep.requests[0])
    start = text.find("你是报销单审查助手。")
    end = text.find("<memory_guidelines>")
    print(text[start : min(end, start + 700)])
    print("……（后面还有很长的 memory_guidelines 使用守则，见 middleware/memory.py 的 MEMORY_SYSTEM_PROMPT）")

    print("\n== B. hook 时机 ==")
    print("  before_agent: 记忆文件 → state['memory_contents']（PrivateStateAttr，不进最终 state）")
    print("  wrap_model_call: state → system 消息尾部（<agent_memory> 块）——请求出栈前最后一步改写")
    print("  最终 state 键:", sorted(result.keys()), "（没有 memory_contents——私有字段被剥离）")
    print("  HTML 注释剥离了吗:", "作者备注" not in text)

    print("\n== C. 记忆条目 = 虚拟文件系统里的一个文件 ==")
    print("  最终 files:", {p: d["content"][:24] for p, d in result["files"].items()})
    print("  —— 与 Step 2 同一条 state['files'] channel：记忆的存储形态就是文件")


if __name__ == "__main__":
    asyncio.run(main())
