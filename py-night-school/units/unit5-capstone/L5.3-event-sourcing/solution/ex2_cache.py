# 练习 2 参考答案（solution/ 不进学员主线视野；先完成练习再回来对照）
"""决策缓存补全：prompt_hash 键（canonical 序列化）+ 命中零请求 + 审计查询。"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_decisions (
    prompt_hash TEXT PRIMARY KEY,
    model       TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    response    TEXT NOT NULL,
    created_at  TEXT NOT NULL
)
"""

# 消息角色的两种方言（OpenAI 协议 vs langchain 对象）——归一是 canonical 的一部分
_ROLE_ALIASES = {"human": "user", "assistant": "ai"}


def _role_of(message: object) -> str:
    """（给定）dict 消息取 role，langchain 消息对象取 type——统一到同一名下再谈相等。"""
    if isinstance(message, dict):
        return str(message.get("role", ""))
    return str(getattr(message, "type", ""))


def _content_of(message: object) -> str:
    """（给定）两种消息形态的 content 都取全文 str。"""
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", ""))


def canonical_prompt(messages: list) -> str:
    """消息序列的规范化文本：逐条 `role|content` 按序拼接（role 经 _ROLE_ALIASES 归一）。"""
    lines = []
    for message in messages:
        role = _role_of(message)
        lines.append(f"{_ROLE_ALIASES.get(role, role)}|{_content_of(message)}")
    return "\n".join(lines)


def prompt_hash(model: str, messages: list) -> str:
    """决策键：sha256(model + canonical_prompt)——模型名进键（同 prompt 换模型≠同决策）。"""
    payload = f"{model}\n{canonical_prompt(messages)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DecisionCache:
    """决策缓存表（given）：建表 / put / get / 关闭——存储层全部给定，本题练键与回路。"""

    def __init__(self, path: str | Path, clock: Callable[[], str] | None = None) -> None:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute(SCHEMA)
        conn.commit()
        self._conn = conn
        self._clock = clock or system_clock

    def put(self, digest: str, model: str, prompt: str, response: str) -> None:
        """（给定）落一条决策记录（INSERT OR REPLACE；created_at 取注入钟）。"""
        sql = (
            "INSERT OR REPLACE INTO llm_decisions (prompt_hash, model, prompt, response, created_at) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        with self._conn:
            self._conn.execute(sql, (digest, model, prompt, response, self._clock()))

    def get(self, digest: str) -> dict | None:
        """（给定）按 prompt_hash 主键点查；miss 返回 None。"""
        row = self._conn.execute(
            "SELECT prompt_hash, model, prompt, response, created_at FROM llm_decisions WHERE prompt_hash = ?",
            (digest,),
        ).fetchone()
        return None if row is None else dict(row)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> DecisionCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def system_clock() -> str:
    """（给定）默认系统 UTC 钟（测试注入固定钟换掉它）。"""
    return datetime.now(UTC).isoformat()


async def cached_complete(cache: DecisionCache, model, messages: list, model_name: str) -> tuple[str, bool]:
    """模型调用过缓存层：返回 (response 文本, 是否命中缓存)。"""
    digest = prompt_hash(model_name, messages)
    hit = cache.get(digest)
    if hit is not None:
        return hit["response"], True  # 命中：零请求，直接回放原话
    response = await model.ainvoke(messages)
    cache.put(digest, model_name, canonical_prompt(messages), str(response.content))
    return str(response.content), False


def audit_query(cache: DecisionCache, digest: str) -> dict | None:
    """审计查询：这个决策的完整原话——{"model", "prompt", "response"} 三键全量，不截断。"""
    row = cache.get(digest)
    if row is None:
        return None
    return {"model": row["model"], "prompt": row["prompt"], "response": row["response"]}
