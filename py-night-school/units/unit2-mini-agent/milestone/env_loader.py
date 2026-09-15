"""端点配置三件套：.env 文件 → os.environ → ChatConfig。

夜校的模型端点中立约定（每课目录的 .env.example）：
    OPENAI_BASE_URL   # 任一 OpenAI 兼容端点，含 /v1 或等价前缀
    OPENAI_API_KEY    # 该端点的密钥
    MODEL_NAME        # 该端点提供的模型名

为什么不用 python-dotenv：三变量 十行解析，正好当 pathlib / 字符串切分的教学素材；
生产里你会用 python-dotenv 或直接进 CI secrets——机制是一样的。
"""

from __future__ import annotations

import os
from pathlib import Path

# 本目录 .env 的默认位置：里程碑根（与课时的 code/env_loader.py 相比少一层目录）
ENV_PATH = Path(__file__).resolve().parent / ".env"

REQUIRED_KEYS = ("OPENAI_BASE_URL", "OPENAI_API_KEY", "MODEL_NAME")


def parse_env_file(path: Path) -> dict[str, str]:
    """解析 KEY=VALUE 文件：# 注释行与空行跳过；行内「 #」之后视为注释。

    例：MODEL_NAME=glm-4.6  # 以你的端点文档为准 → {"MODEL_NAME": "glm-4.6"}
    文件不存在返回空 dict（.env 是可选的：环境变量直接配好也行）。
    """
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip()  # 行内注释剥掉，引号不去（教程不用引号写法）
        values[key.strip()] = value
    return values


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    """把 .env 的键值写进 os.environ——用 setdefault：真实环境变量优先，文件不覆盖它。"""
    for key, value in parse_env_file(path).items():
        os.environ.setdefault(key, value)
    return {key: os.environ[key] for key in REQUIRED_KEYS if key in os.environ}
