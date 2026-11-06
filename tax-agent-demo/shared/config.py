"""平台公共配置：.env 加载 + 远端 agent 注册表。

真实企业里这一层等价于服务发现/注册中心（Nacos、Consul 等），
demo 用一个静态注册表模拟：主 agent 通过注册表发现 subagent。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# demo 应用根目录（tax-agent-demo/）
DEMO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = DEMO_ROOT / "data"

# LLM 端点中立三变量（沿用 py-night-school 纪律）
LLM_ENV_KEYS = ("OPENAI_BASE_URL", "OPENAI_API_KEY", "MODEL_NAME")
# 可选第四变量：模型私有开关（JSON，透传进请求体），如思考模式关闭
LLM_EXTRA_BODY_KEY = "LLM_EXTRA_BODY"


def load_env() -> None:
    """加载 tax-agent-demo/.env（文件不存在时静默跳过，可重复调用）。"""
    load_dotenv(DEMO_ROOT / ".env")


def llm_env() -> dict[str, str]:
    """读取 LLM 三变量，缺失时给出可操作的报错。"""
    load_env()
    missing = [key for key in LLM_ENV_KEYS if not os.environ.get(key)]
    if missing:
        raise RuntimeError(
            f".env 缺少变量 {missing}，请参照 .env.example 配置（OPENAI_BASE_URL / OPENAI_API_KEY / MODEL_NAME）"
        )
    return {key: os.environ[key] for key in LLM_ENV_KEYS}


def llm_extra_body() -> dict | None:
    """读取可选的模型私有开关（LLM_EXTRA_BODY，JSON 文本）。

    用途举例：DeepSeek 思考模式默认开启时会拒绝 tool_choice 强制（影响 langchain
    结构化输出的二次调用），配 LLM_EXTRA_BODY='{"thinking": {"type": "disabled"}}' 关闭。
    """
    load_env()
    raw = os.environ.get(LLM_EXTRA_BODY_KEY)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f".env 的 {LLM_EXTRA_BODY_KEY} 不是合法 JSON：{exc}") from exc
    return parsed if isinstance(parsed, dict) else None


@dataclass(frozen=True)
class AgentEndpoint:
    """注册表中一个远端 subagent 的坐标。"""

    name: str  # 注册名，同时是委派工具名后缀（delegate_to_<name>）
    title: str  # 展示名（中文）
    description: str  # 一句话职责描述（进 AgentCard 与委派工具 description）
    port: int

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


# 静态注册表：demo 约定 subagent 端口 9101/9102
AGENT_REGISTRY: dict[str, AgentEndpoint] = {
    ep.name: ep
    for ep in (
        AgentEndpoint(
            name="tax_calc",
            title="计税 agent",
            description="税务计算团队维护：查询纳税人档案与税率表、校验专项附加扣除、综合所得年度汇算计税",
            port=9101,
        ),
        AgentEndpoint(
            name="tax_filing",
            title="申报 agent",
            description="申报报送团队维护：生成申报表草稿、校验勾稽、提交申报（长任务）与查询申报状态",
            port=9102,
        ),
    )
}
