"""计税 agent 的 A2A 服务入口。

启动：uv run python -m tax_calc.server
协议：A2A 1.0 JSONRPC 绑定，AgentCard 在 /.well-known/agent-card.json
"""

from __future__ import annotations

import contextlib
import logging

import uvicorn
from a2a.types import AgentSkill

from shared.a2a_adapter import DeepAgentExecutor, build_agent_card, build_server_app
from shared.config import AGENT_REGISTRY
from tax_calc.agent import build_graph

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("tax_calc.server")


def create_app(model=None, port: int | None = None):
    """构建 FastAPI 应用；model/port 可注入（契约测试零 key 用测试端口）。"""
    endpoint = AGENT_REGISTRY["tax_calc"]
    serve_port = port or endpoint.port
    card = build_agent_card(
        name=endpoint.title,
        description=endpoint.description,
        port=serve_port,
        skills=[
            AgentSkill(
                id="annual_reconciliation_calc",
                name="综合所得年度汇算计税",
                description="按 2025 年度税率表对指定纳税人做年度汇算计税，返回结构化应补(退)税结论",
                tags=["tax", "calculation"],
            ),
            AgentSkill(
                id="deduction_verify",
                name="专项附加扣除校验",
                description="校验专项附加扣除项及佐证材料齐全性，列出缺失项",
                tags=["tax", "verification"],
            ),
        ],
    )
    executor = DeepAgentExecutor(lambda: build_graph(model))
    return build_server_app(card, executor)


def main() -> None:
    endpoint = AGENT_REGISTRY["tax_calc"]
    logger.info("计税 agent 启动：http://%s（AgentCard: /.well-known/agent-card.json）", endpoint.base_url)
    with contextlib.suppress(KeyboardInterrupt):
        uvicorn.run(create_app(), host="127.0.0.1", port=endpoint.port, log_level="warning")


if __name__ == "__main__":
    main()
