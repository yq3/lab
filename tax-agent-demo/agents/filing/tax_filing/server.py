"""申报 agent 的 A2A 服务入口。

启动：uv run python -m tax_filing.server
协议：A2A 1.0 JSONRPC 绑定，AgentCard 在 /.well-known/agent-card.json

Task 状态机展示：
- 常规路径：submitted → working → completed（提交申报含 2 秒模拟受理耗时）
- 材料缺失路径：submitted → working → input-required
  （executor 把 [[NEED_INPUT]] 前缀翻译为协议状态，主 agent 转问用户）
"""

from __future__ import annotations

import contextlib
import logging

import uvicorn
from a2a.types import AgentSkill

from shared.a2a_adapter import DeepAgentExecutor, build_agent_card, build_server_app
from shared.config import AGENT_REGISTRY
from tax_filing.agent import build_graph

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("tax_filing.server")


def create_app(model=None, port: int | None = None):
    """构建 FastAPI 应用；model/port 可注入（契约测试零 key 用测试端口）。"""
    endpoint = AGENT_REGISTRY["tax_filing"]
    serve_port = port or endpoint.port
    card = build_agent_card(
        name=endpoint.title,
        description=endpoint.description,
        port=serve_port,
        skills=[
            AgentSkill(
                id="return_filing",
                name="个税年度申报",
                description="依据计税结论生成申报表草稿、校验勾稽与材料、提交电子税务局并返回回执号；"
                "材料缺失时任务进入等待补充信息状态",
                tags=["tax", "filing"],
            ),
            AgentSkill(
                id="filing_status_query",
                name="申报状态查询",
                description="按回执号查询申报受理状态",
                tags=["tax", "query"],
            ),
        ],
    )
    executor = DeepAgentExecutor(lambda: build_graph(model))
    return build_server_app(card, executor)


def main() -> None:
    endpoint = AGENT_REGISTRY["tax_filing"]
    logger.info("申报 agent 启动：http://%s（AgentCard: /.well-known/agent-card.json）", endpoint.base_url)
    with contextlib.suppress(KeyboardInterrupt):
        uvicorn.run(create_app(), host="127.0.0.1", port=endpoint.port, log_level="warning")


if __name__ == "__main__":
    main()
