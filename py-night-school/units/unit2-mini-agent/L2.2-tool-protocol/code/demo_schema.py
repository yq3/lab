"""实验①：schema 观察——Pydantic 模型怎么变成模型看得懂的契约。"""

from __future__ import annotations

import json

from finance import GetClaimArgs, PreapproveArgs
from tools import TOOL_REGISTRY, to_openai_tools

if __name__ == "__main__":
    print("== PreapproveArgs 的 JSON Schema ==")
    print(json.dumps(PreapproveArgs.model_json_schema(), ensure_ascii=False, indent=2))
    print()
    print("== GetClaimArgs 的 JSON Schema（关注 required 与 pattern） ==")
    print(json.dumps(GetClaimArgs.model_json_schema(), ensure_ascii=False, indent=2))
    print()
    print("== 注册表 -> OpenAI tools 载荷（发给端点的形状） ==")
    print(f"已注册: {sorted(TOOL_REGISTRY)}")
    print(json.dumps(to_openai_tools()[1], ensure_ascii=False, indent=2))
