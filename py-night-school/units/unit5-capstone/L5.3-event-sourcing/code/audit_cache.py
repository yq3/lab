"""缓存即审计的 SQLite 版（本课核心之二，A13）——L4.1 文件版的升级。

L4.1 精读过 virattt/ai-hedge-fund 的 PromptCache：一决定一 JSON 文件，缓存=审计=调试
三合一。今晚把它升级成一张表 llm_decisions(prompt_hash PRIMARY KEY, model, prompt,
response, created_at)：同 prompt_hash 命中→直接回放 response（第二次零模型请求），
审计查询「这轮模型看到了什么/说了什么」一行 SQL 出原话——不再是「打开某个 JSON 文件」，
而是可 join、可聚合的表（与事件表同库：一个 db 文件就是一单的完整审计面）。

key 纪律（L4.1 §5「相等不等哈希」的正解，本课以 canonical 序列化落地）：
canonical_prompt 把消息序列归一成确定文本——dict 消息与同内容的 langchain 消息对象
（human/user、assistant/ai 两种叫法）哈希到同一个 key；prompt_hash 再把模型名拼进去
（同 prompt 换模型=不同决策，不同 key）。

时钟纪律与 eventstore 同款：created_at 注入时钟，默认系统 UTC 钟。
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from eventstore import RunRecorder

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_decisions (
    prompt_hash TEXT PRIMARY KEY,
    model       TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    response    TEXT NOT NULL,
    created_at  TEXT NOT NULL
)
"""

# 消息角色的两种方言归一：OpenAI 协议说 user/assistant，langchain 对象说 human/ai
_ROLE_ALIASES = {"human": "user", "assistant": "ai"}


def _role_of(message: object) -> str:
    if isinstance(message, dict):
        return str(message.get("role", ""))
    return str(getattr(message, "type", ""))


def _content_of(message: object) -> str:
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", ""))


def canonical_prompt(messages: list) -> str:
    """消息序列的规范化文本：逐条 `role|content` 按序拼接。

    这是「相等不等哈希」的正解位置——决定 key 的不是随手 str(messages)（对象 repr
    带内存地址与类型名，永远不相等），而是显式声明的规范形：角色归一（human=user）、
    内容取全文、顺序就是消息顺序（列表有序，无 dict 键序歧义）。
    """
    lines = []
    for message in messages:
        role = _role_of(message)
        lines.append(f"{_ROLE_ALIASES.get(role, role)}|{_content_of(message)}")
    return "\n".join(lines)


def prompt_hash(model: str, messages: list) -> str:
    """决策键：sha256(model + canonical_prompt)——模型名进键（同 prompt 换模型≠同决策）。"""
    payload = f"{model}\n{canonical_prompt(messages)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def system_clock() -> str:
    """默认系统 UTC 钟（与 eventstore 同款纪律；测试注入固定钟换掉它）。"""
    return datetime.now(UTC).isoformat()


class DecisionCache:
    """决策缓存表：get/put 主键点查 + audit_query 一行 SQL 出原话。"""

    def __init__(self, path: str | Path, clock: Callable[[], str] | None = None) -> None:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute(SCHEMA)
        conn.commit()
        self._conn = conn
        self._clock = clock or system_clock

    def get(self, digest: str) -> dict | None:
        """按 prompt_hash 点查；miss 返回 None（缓存语义：缺就是缺，不猜）。"""
        row = self._conn.execute(
            "SELECT prompt_hash, model, prompt, response, created_at FROM llm_decisions WHERE prompt_hash = ?",
            (digest,),
        ).fetchone()
        return None if row is None else dict(row)

    def put(self, digest: str, model: str, prompt: str, response: str) -> None:
        """落一条决策记录（INSERT OR REPLACE：同 key 重写——缓存与审计都以「最新原话」为准）。"""
        sql = (
            "INSERT OR REPLACE INTO llm_decisions (prompt_hash, model, prompt, response, created_at) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        with self._conn:  # 与 EventStore.append 同款事务纪律
            self._conn.execute(sql, (digest, model, prompt, response, self._clock()))

    def audit_query(self, digest: str) -> dict | None:
        """审计查询：这轮模型看到了什么（prompt 全文）、说了什么（response 全文）。

        合规问「当时的原话」，答案就是主键点查——缓存即审计的意思是审计查询
        不需要另一套存储，同一张表既是性能件又是取证件。
        """
        return self.get(digest)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> DecisionCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AuditedModel(Runnable):
    """过审计层的模型调用（Runnable 子类——图与节点零感知，换的是芯不是壳）。

    每次 ainvoke：算 prompt_hash → 查 llm_decisions——
    - 命中：直接回放缓存 response（零模型请求、零成本事件）；
    - 未命中：真调用 → 落缓存 → recorder 发 llm.decision + cost.recorded 事件
      （tokens 从模型响应的 usage_metadata 取——mock 端点也带真实 usage，零 key 也真实）。
    recorder=None 时只做缓存不发事件（缓存与事件两层各自可独立关）。
    """

    def __init__(
        self,
        base,
        cache: DecisionCache,
        recorder: RunRecorder | None,
        node: str,
    ) -> None:
        super().__init__()
        self._base = base
        self._cache = cache
        self._recorder = recorder
        self._node = node
        self._model_name = str(getattr(base, "model_name", "unknown"))

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:  # 参数名就叫 input——Runnable 的签名
        """同步路径不设防：本图全异步（ainvoke），同步调用是使用错误，响亮失败。"""
        raise NotImplementedError("AuditedModel 只走异步 ainvoke（本课图全异步节点）")

    async def ainvoke(self, messages: list, config: Any = None, **kwargs: Any) -> AIMessage:
        digest = prompt_hash(self._model_name, messages)
        hit = self._cache.get(digest)
        if hit is not None:
            if self._recorder is not None:
                self._recorder.emit(
                    "llm.decision",
                    {"node": self._node, "prompt_hash": digest, "model": self._model_name, "cached": True},
                )
            return AIMessage(content=hit["response"])  # 回放缓存的原话——模型一个请求都没收到
        response = await self._base.ainvoke(messages, config, **kwargs)
        self._cache.put(digest, self._model_name, canonical_prompt(messages), str(response.content))
        if self._recorder is not None:
            self._recorder.emit(
                "llm.decision", {"node": self._node, "prompt_hash": digest, "model": self._model_name, "cached": False}
            )
            usage = getattr(response, "usage_metadata", None) or {}
            self._recorder.emit(
                "cost.recorded",
                {
                    "node": self._node,
                    "model": self._model_name,
                    "prompt_tokens": int(usage.get("input_tokens", 0)),
                    "completion_tokens": int(usage.get("output_tokens", 0)),
                },
            )
        return response
