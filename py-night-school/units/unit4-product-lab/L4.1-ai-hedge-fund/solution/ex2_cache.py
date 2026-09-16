# 参考答案：ex2_cache（练习文件的完整解法——完成前别看）
"""DecisionCache：一决定一 JSON 文件——缓存 = 审计记录 = 调试踪迹。"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def decision_key(checker: str, model: str, system: str, user: str) -> str:
    """缓存 key：四个字段 -> 确定性字符串 -> sha256 十六进制截前 24 位（对版 prompt_key）。"""
    payload = f"{checker}|{model}|{system}|{user}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


class DecisionCache:
    """一决定一 JSON 文件（对版 PromptCache）。"""

    def __init__(self, cache_dir: Path | str) -> None:
        self._dir = Path(cache_dir)

    def get(self, key: str) -> dict | None:
        """读一条决策记录；文件不存在或损坏都当 miss。"""
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None  # 损坏条目当 miss——下一次 put 会重写它

    def put(self, key: str, record: dict) -> None:
        """落一条决策记录，补上 created_at（审计字段在这里加）。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        record = {**record, "created_at": datetime.now(UTC).isoformat()}
        path = self._dir / f"{key}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


# ---- given 基础设施（与练习骨架同款，不要改）----


class ScriptClient:
    """离线模型替身：按剧本依次回文本，并数自己被调了几次。"""

    def __init__(self, replies: list[str]) -> None:
        self.model = "mock-model"
        self._replies = list(replies)
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self._replies.pop(0)


class MiniChecker:
    """讲义 reviewers.LLMCheckerBase 的缩影：命中缓存直接用；miss 才调 client；失败留盘。"""

    SYSTEM = "你是测试用检查员"

    def __init__(self, name: str, client: ScriptClient, cache: DecisionCache) -> None:
        self._name = name
        self._client = client
        self._cache = cache

    def review(self, user: str) -> dict:
        key = decision_key(self._name, self._client.model, self.SYSTEM, user)
        cached = self._cache.get(key)
        if cached is not None and "parsed" in cached:
            return cached["parsed"]
        response = self._client.complete(self.SYSTEM, user)
        record = {
            "checker": self._name,
            "model": self._client.model,
            "system": self.SYSTEM,
            "user": user,
            "response": response,
        }
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as exc:
            self._cache.put(key, {**record, "parse_error": str(exc)})
            return {"abstained": True, "parse_error": str(exc)}
        self._cache.put(key, {**record, "parsed": parsed})
        return parsed
