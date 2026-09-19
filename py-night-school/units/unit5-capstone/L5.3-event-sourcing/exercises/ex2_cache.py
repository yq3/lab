# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""决策缓存补全：prompt_hash 键（canonical 序列化）+ 命中零请求 + 审计查询。

考察点：L4.1 §5「相等不等哈希」的正解——决定 key 的不是 str(messages)（对象 repr
带类型名，永远不相等），而是显式声明的规范形（canonical_prompt）；同 prompt_hash
命中时零模型请求；审计查询把「模型看到/说了什么」的原话一行点查出来。
讲义 code/audit_cache.py 是同构完整版（对版参照）。

验收口径（与 hints 同源）：
- canonical：dict 消息与同内容 langchain 消息（human=user、assistant=ai）同 hash；
- 不同 prompt / 不同模型 → 不同 hash（不误命中的根）；
- 第二遍（新端点、不装剧本）零请求、响应与第一遍同文；
- 审计查询返回完整原话（prompt 全文 + response 全文）；
- 不同单不误命中（新 prompt → 真调用发生）。

完成判据：uv run pytest exercises/test_ex2.py 全绿——5 个测试。
TODO 所需的顶部 import：
  import hashlib
"""

from __future__ import annotations

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
    # TODO(ex2): 问：每条消息取哪两样拼成一行、行与行怎么连接？role 里的 human/assistant
    #   归一成 user/ai 用哪个 given 的映射（键不存在时取谁）？
    raise NotImplementedError("TODO(ex2): canonical_prompt")


def prompt_hash(model: str, messages: list) -> str:
    """决策键：sha256(model + canonical_prompt)——模型名进键（同 prompt 换模型≠同决策）。"""
    # TODO(ex2): 问：模型名与规范文本怎么合成一个串（中间的分隔符自定，但必须确定）？
    #   hashlib 的哪个函数吃 bytes、怎么编码、取什么形态返回？
    raise NotImplementedError("TODO(ex2): prompt_hash")


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
    """模型调用过缓存层：返回 (response 文本, 是否命中缓存)。

    命中路径必须零请求（不发 ainvoke、不碰端点）；未命中真调用后把
    (digest, model_name, 规范文本, response 文本) 落回缓存——put 的四个入参
    各取自哪里想清楚再写。
    """
    # TODO(ex2): 问：digest 用哪个函数、哪些入参算？查哪张表、拿到什么算命中——
    #   命中时返回元组的两样各是什么（response 文本从行的哪个键取）？
    #   未命中时先 await 什么、再把哪四样 put 回去？
    raise NotImplementedError("TODO(ex2): cached_complete")


def audit_query(cache: DecisionCache, digest: str) -> dict | None:
    """审计查询：这个决策的完整原话——{"model", "prompt", "response"} 三键全量，不截断。"""
    # TODO(ex2): 问：点查用哪个 given 方法、返回行的哪三个键搬进结果？miss 时返回什么？
    raise NotImplementedError("TODO(ex2): audit_query")
