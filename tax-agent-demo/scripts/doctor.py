"""A2A agent 健康检查：拉取各注册 agent 的 AgentCard 并摘要展示。

用法：uv run python scripts/doctor.py
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from shared.config import AGENT_REGISTRY, load_env


async def check(http: httpx.AsyncClient, name: str, base_url: str) -> bool:
    """拉单个 agent card，成功打印摘要，失败打印原因。"""
    url = f"{base_url}/.well-known/agent-card.json"
    try:
        resp = await http.get(url, timeout=5)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"✗ {name}（{url}）：不可达 —— {exc.__class__.__name__}")
        return False
    card = resp.json()
    skills = "、".join(skill.get("name", "?") for skill in card.get("skills", []))
    print(f"✓ {name}（{url}）")
    print(f"    描述：{card.get('description', '')}")
    print(f"    技能：{skills}；streaming={card.get('capabilities', {}).get('streaming')}；版本 {card.get('version')}")
    return True


async def main() -> int:
    load_env()
    all_ok = True
    async with httpx.AsyncClient() as http:
        for endpoint in AGENT_REGISTRY.values():
            all_ok &= await check(http, endpoint.title, endpoint.base_url)
    if not all_ok:
        print("\n提示：先运行 bash scripts/start_all.sh 拉起全部 agent")
        return 1
    print("\n全部 agent 在线。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
