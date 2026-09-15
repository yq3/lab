"""参考答案（ex2）——两个实现零继承，纯靠形状过审。"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class AuditSink(Protocol):
    """审计出口协议：把（单据号, 判定）记录到某个地方，返回记录行。"""

    def record(self, claim_id: str, verdict: str) -> str: ...


class ConsoleSink:
    def record(self, claim_id: str, verdict: str) -> str:
        return f"[console] {claim_id} {verdict}"


class TeamSink:
    def record(self, claim_id: str, verdict: str) -> str:
        return f"[team] {claim_id} {verdict}"
