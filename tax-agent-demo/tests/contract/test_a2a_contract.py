"""A2A 契约测试：真实 HTTP + 剧本假模型（零 key）。

验证协议层行为，不验证模型智能：
- AgentCard 发现（.well-known/agent-card.json）
- message/stream 全链路：submitted → working → completed → artifact 回传
- [[NEED_INPUT]] → input-required 状态 → client 侧 [INPUT_REQUIRED] 透传
- executor 异常 → failed 状态 → [DELEGATE_FAILED]
- 不可达 → [DELEGATE_UNREACHABLE]
- 委派工具工厂：命名 / 描述 / 通过 StructuredTool 调用
"""

from __future__ import annotations

import httpx
import pytest
from langchain_core.messages import AIMessage

from shared.config import AGENT_REGISTRY
from tests.conftest import (
    TEST_PORT_CALC,
    TEST_PORT_EXPLODE,
    TEST_PORT_FILING,
    ExplodingChatModel,
    scripted_model,
    spawn_a2a_server,
)


@pytest.fixture
async def calc_server():
    from tax_calc.server import create_app

    model = scripted_model(AIMessage("计税结论（fake）：应退 1720 元"))
    async with spawn_a2a_server(create_app, model, TEST_PORT_CALC) as url:
        yield url


@pytest.fixture
async def filing_needs_input_server():
    from tax_filing.server import create_app

    model = scripted_model(AIMessage("[[NEED_INPUT]] 缺少：继续教育执业资格证书复印件。请补传后重新发起申报。"))
    async with spawn_a2a_server(create_app, model, TEST_PORT_FILING) as url:
        yield url


async def test_agent_card_发现(calc_server):
    async with httpx.AsyncClient() as http:
        card = (await http.get(f"{calc_server}/.well-known/agent-card.json")).json()
    assert card["name"] == "计税 agent"
    assert card["capabilities"]["streaming"] is True
    skill_ids = {skill["id"] for skill in card["skills"]}
    assert {"annual_reconciliation_calc", "deduction_verify"} <= skill_ids
    # JSONRPC 1.0 绑定端点存在
    assert any(i["protocolBinding"] == "JSONRPC" for i in card["supportedInterfaces"])


async def test_委派全链路_artifact回传(calc_server):
    from shared.a2a_adapter.client import call_remote_agent

    reply = await call_remote_agent(calc_server, "帮我算 T2025-001 的 2025 年个税")
    assert "1720" in reply
    assert not reply.startswith("[")  # 正常回复不带错误/状态标记


async def test_input_required_状态翻译(filing_needs_input_server):
    from shared.a2a_adapter.client import INPUT_REQUIRED_MARK, call_remote_agent

    reply = await call_remote_agent(filing_needs_input_server, "提交 T2025-002 的申报")
    assert reply.startswith(INPUT_REQUIRED_MARK)
    assert "继续教育" in reply  # 缺失清单透传给主 agent


async def test_executor_异常翻译为_failed():
    from tax_calc.server import create_app

    from shared.a2a_adapter.client import call_remote_agent

    exploding = ExplodingChatModel(messages=iter([AIMessage("unused")]))
    async with spawn_a2a_server(create_app, exploding, TEST_PORT_EXPLODE) as url:
        reply = await call_remote_agent(url, "算税")
    assert reply.startswith("[DELEGATE_FAILED]")


async def test_不可达_映射可读错误():
    from shared.a2a_adapter.client import call_remote_agent

    reply = await call_remote_agent("http://127.0.0.1:19999", "算税")
    assert reply.startswith("[DELEGATE_UNREACHABLE]")
    assert "start_all.sh" in reply


async def test_委派工具工厂_经StructuredTool调用(calc_server):
    from shared.a2a_adapter.client import build_delegate_tool, build_delegate_tools
    from shared.config import AgentEndpoint

    tools = build_delegate_tools(AGENT_REGISTRY)
    names = {t.name for t in tools}
    assert names == {"delegate_to_tax_calc", "delegate_to_tax_filing"}

    # 指向测试 server 的端点 → 工具 → 协程体调用，验证工具包一层后的行为
    test_endpoint = AgentEndpoint(name="tax_calc", title="计税 agent", description="测试端点", port=TEST_PORT_CALC)
    tool = build_delegate_tool(test_endpoint)
    assert tool.coroutine is not None  # coroutine 工具
    result = await tool.coroutine(task="算税")
    assert "1720" in result
