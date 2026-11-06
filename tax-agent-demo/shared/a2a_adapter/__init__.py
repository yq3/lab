"""A2A 适配层：deepagents ↔ A2A 协议的薄封装。

- server.py：deepagents 编译图 → A2A AgentExecutor（对外服务）
- client.py：A2A Client → 主 agent 的委派工具（对内调用）

业务 agent 代码不感知协议细节；换协议只动本包。
"""

from shared.a2a_adapter.client import build_delegate_tool, build_delegate_tools
from shared.a2a_adapter.server import (
    NEED_INPUT_PREFIX,
    DeepAgentExecutor,
    build_agent_card,
    build_server_app,
)

__all__ = [
    "NEED_INPUT_PREFIX",
    "DeepAgentExecutor",
    "build_agent_card",
    "build_delegate_tool",
    "build_delegate_tools",
    "build_server_app",
]
