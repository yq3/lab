"""讲义区测试：L3.5 demo 的 harness 机制断言（契约之外的本课考点）。

与 test_contract.py（五课共用）的分工：contract 只认 run_review 的输出与
CALL_LOG；本文件断言 deepagents 特有的机制——五轮剧本的结构（谁是主代理
谁是子代理）、审查底稿落盘、task 工具目录、子代理隔离、MemoryMiddleware
注入、默认工具清单与显式收窄。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

import demo
from advice import Advice
from mock_endpoint import MockLLMEndpoint


def _run_and_trace(claim_id: str) -> tuple[Advice, dict]:
    return asyncio.run(demo.run_review_with_trace(claim_id))


def test_five_rounds_main_and_subagent_split() -> None:
    """五轮模型调用：R1/R4/R5 主代理（有 task），R2/R3 子代理（无 task）。"""
    _, trace = _run_and_trace("CLM-2026-0001")
    requests = trace["requests"]
    assert len(requests) == 5
    for i in (0, 3, 4):  # 主代理轮：工具清单含 task 与 Advice
        names = {t["function"]["name"] for t in requests[i]["tools"]}
        assert {"task", "Advice", "check_budget"} <= names
    for i in (1, 2):  # 子代理轮：无 task（不能再转交），有 verify_invoice
        names = {t["function"]["name"] for t in requests[i]["tools"]}
        assert "task" not in names
        assert "verify_invoice" in names


def test_dossier_written_to_state_files() -> None:
    """审查底稿落盘：state['files'] 里有 /review/<单号>.md，内容含关键事实。"""
    advice, trace = _run_and_trace("CLM-2026-0002")
    files = trace["state"]["files"]
    path = f"/review/{advice.claim_id}.md"
    assert path in files, sorted(files)
    content = files[path]["content"]
    assert advice.claim_id in content
    assert advice.reason in content  # 结论码（REJECT:ITEM_OVER_LIMIT）
    assert "剩余 10000 分" in content  # check_budget 的镜像（SALES 剩余）


def test_structured_response_is_advice_instance() -> None:
    """结构化收尾：收尾轮是 Advice 工具调用，structured_response 是 Pydantic 实例。"""
    advice, trace = _run_and_trace("CLM-2026-0003")
    assert isinstance(advice, Advice)
    assert trace["state"]["structured_response"] == advice
    last_ai = next(m for m in reversed(trace["state"]["messages"]) if m.type == "ai")
    assert [c["name"] for c in last_ai.tool_calls] == ["Advice"]


def test_task_tool_catalog_lists_specialist_and_default_gp() -> None:
    """task 工具目录：我们声明的 invoice-specialist + harness 默认塞进来的 general-purpose。"""
    _, trace = _run_and_trace("CLM-2026-0004")
    task_tool = next(t for t in trace["requests"][0]["tools"] if t["function"]["name"] == "task")
    description = task_tool["function"]["description"]
    assert "invoice-specialist: 发票校验专员" in description
    assert "general-purpose:" in description  # 默认值：不声明 subagents 也会自动加


def test_subagent_isolation_first_human_message_is_task() -> None:
    """子代理隔离：R3 请求里第一条 human 消息就是任务描述，不是主代理的原始对话。"""
    _, trace = _run_and_trace("CLM-2026-0001")
    sub_final = trace["requests"][2]["messages"]
    humans = [m for m in sub_final if m.get("role") == "user"]
    assert len(humans) == 1
    assert humans[0]["content"].startswith("复核报销单 CLM-2026-0001 的关联发票")
    assert "客户拜访" not in humans[0]["content"]  # 主代理 user 消息里的单据叙述没进来


def test_memory_middleware_injects_into_system() -> None:
    """MemoryMiddleware：预置记忆文件 → 第一个请求的 system 出现 <agent_memory> 块。"""

    async def run_once() -> dict:
        with MockLLMEndpoint() as ep:
            model = ChatOpenAI(base_url=ep.url, api_key=SecretStr(ep.api_key), model=ep.model)
            agent = create_deep_agent(model=model, memory=["/memory/AGENTS.md"])
            ep.script_text("收到。")
            files = {"/memory/AGENTS.md": {"content": "# 审查记忆\n金额一律整数分。"}}
            await agent.ainvoke(demo.input_with_files("noop", files))
            return dict(ep.requests[0])

    request = asyncio.run(run_once())
    sysmsg = next(m for m in request["messages"] if m.get("role") == "system")
    content = sysmsg["content"]
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    assert "<agent_memory>" in content
    assert "金额一律整数分" in content


def test_default_builtin_tools_and_narrowing() -> None:
    """默认工具清单与最小权限收窄：默认全套内置件；自定义 FilesystemMiddleware 原位替换后收窄。"""

    async def run_twice() -> tuple[set[str], set[str]]:
        with MockLLMEndpoint() as ep:
            model = ChatOpenAI(base_url=ep.url, api_key=SecretStr(ep.api_key), model=ep.model)
            default_agent = demo.build_agent(model)
            ep.script_text("ok")
            await default_agent.ainvoke({"messages": [HumanMessage(content="noop")]})
            default_names = {t["function"]["name"] for t in ep.requests[0]["tools"]}

            narrowed = create_deep_agent(
                model=model,
                middleware=[FilesystemMiddleware(backend=StateBackend(), tools=["ls", "read_file", "write_file"])],
            )
            ep.requests.clear()
            ep.script_text("ok")
            await narrowed.ainvoke({"messages": [HumanMessage(content="noop")]})
            narrowed_names = {t["function"]["name"] for t in ep.requests[0]["tools"]}
            return default_names, narrowed_names

    default_names, narrowed_names = asyncio.run(run_twice())
    # harness 默认给了你什么（以请求取证）：文件系统 7 件 + task + 我们的 1 件 + Advice
    builtin = {"ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep"}
    assert builtin | {"task", "check_budget", "Advice"} == default_names
    assert "execute" not in default_names  # StateBackend 不是 sandbox 后端，execute 不提供
    # 显式收窄后：glob/grep/edit_file/delete 从模型视野消失
    assert narrowed_names == {"ls", "read_file", "write_file", "task"}
