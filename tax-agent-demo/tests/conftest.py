"""测试公共件：带 bind_tools 的假模型 + A2A server 进程内拉起。

契约测试零 key：模型层用剧本假模型，传输层走真实 HTTP（uvicorn + SSE）。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from itertools import chain, repeat

import httpx
import pytest
import uvicorn
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

# 测试专用端口（避开注册表的 9101/9102，防与 dev server 冲突）
TEST_PORT_CALC = 19211
TEST_PORT_FILING = 19212
TEST_PORT_EXPLODE = 19213


class FakeToolChatModel(GenericFakeChatModel):
    """GenericFakeChatModel 不实现 bind_tools，而 deepagents 循环必调它。"""

    def bind_tools(self, tools, **kwargs):  # noqa: ANN003, ANN001
        return self


class ExplodingChatModel(FakeToolChatModel):
    """每次模型调用都炸：验证 executor 的 failed 状态翻译。"""

    async def _agenerate(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("模拟模型故障")


def scripted_model(*messages: AIMessage) -> FakeToolChatModel:
    """剧本假模型；剧本耗尽后重复最后一条（防 deepagents 结构化输出二次调用 StopIteration）。"""
    seq = list(messages)
    return FakeToolChatModel(messages=iter(chain(seq, repeat(seq[-1]))))


@contextlib.asynccontextmanager
async def spawn_a2a_server(create_app_fn, model, port: int) -> AsyncIterator[str]:
    """进程内拉起一个 A2A server，yield base_url；用完即退。"""
    app = create_app_fn(model, port=port)  # 卡片里的端点 URL 必须与实际服务端口一致
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    task = asyncio.create_task(server.serve())
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):  # 等 AgentCard 就绪（最多 5 秒）
            await asyncio.sleep(0.1)
            try:
                async with httpx.AsyncClient() as http:
                    await http.get(f"{url}/.well-known/agent-card.json", timeout=1)
                break
            except httpx.HTTPError:
                continue
        yield url
    finally:
        server.should_exit = True
        await task


@pytest.fixture
def clean_filing_state():
    """隔离 mock 税务局内存态 + 申报工作区产物。"""
    from pathlib import Path

    from tax_filing import tax_bureau_mock

    tax_bureau_mock.reset()
    yield
    tax_bureau_mock.reset()
    for f in Path(__file__).parent.parent.glob("agents/filing/tax_filing/workspace/return_draft_*.json"):
        f.unlink()
