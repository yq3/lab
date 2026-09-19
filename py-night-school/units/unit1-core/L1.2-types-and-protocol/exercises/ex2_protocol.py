# 练习 2（单变量编辑约束：只给 TODO 标注的两个类补 record 方法，其余不要动）
"""审计出口——结构化类型的第一次亲手体验。

AuditSink 是一个 Protocol：它只描述「形状」（有一个 record 方法），
不要求任何类显式继承它。你的任务：让下面两个类「长得像」AuditSink——
一个都不许继承它（验收会检查 __bases__），让「长得像」本身成为兼容的证据。

record 返回行的精确格式（验收按此断言）：
    ConsoleSink -> "[console] CLM-2026-0001 PASS"
    TeamSink    -> "[team] CLM-2026-0001 PASS"
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class AuditSink(Protocol):
    """审计出口协议：把（单据号, 判定）记录到某个地方，返回记录行。"""

    def record(self, claim_id: str, verdict: str) -> str: ...


class ConsoleSink:
    """TODO(ex2a): 给我加 record 方法（签名对照 AuditSink），不要继承 AuditSink。"""


class TeamSink:
    """TODO(ex2b): 同上——格式前缀换成 [team]。"""
