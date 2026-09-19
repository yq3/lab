# 参考答案（ex3）：与骨架的差异在 grant / match / admit 三个函数体与顶部补的时间 import。
"""always 规则修订：RuleBook 匹配器 + 自动批准接入 + 可审计规则记录。

题目与契约见 exercises/ex3_always.py 的 docstring；本文件是它的参考答案。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from pydantic import BaseModel

EVENTS: list[dict] = []


def emit(event: str, data: dict) -> None:
    """记一条事件（given）。"""
    EVENTS.append({"event": event, "data": data})


def reset_events() -> None:
    """清空事件表（given）。"""
    EVENTS.clear()


def content_hash_of(advice: dict, total_cents: int) -> str:
    """被审内容指纹（given）。"""
    payload = json.dumps({"advice": advice, "total_cents": total_cents}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ApprovalRule(BaseModel):
    """always 规则（given 模型）：审计四问各有一列。"""

    rule_id: str
    dept: str
    max_total_cents: int
    approved_by: str
    approved_at: str
    content_hash: str


class RuleBook:
    """规则簿（参考答案）：grant 建可审计规则、match 两维命中查询。"""

    def __init__(self) -> None:
        self._rules: list[ApprovalRule] = []

    def all(self) -> list[ApprovalRule]:
        """全部规则（given）。"""
        return list(self._rules)

    def grant(self, dept: str, cap_cents: int, approved_by: str, content_hash: str) -> ApprovalRule:
        """建一条可审计规则（参考答案）：编号自增、UTC ISO 时间戳、四元组全录。"""
        rule = ApprovalRule(
            rule_id=f"rule-{len(self._rules) + 1:03d}",
            dept=dept,
            max_total_cents=cap_cents,
            approved_by=approved_by,
            approved_at=datetime.now(UTC).isoformat(timespec="seconds"),
            content_hash=content_hash,
        )
        self._rules.append(rule)
        return rule

    def match(self, dept: str, total_cents: int) -> ApprovalRule | None:
        """规则命中查询（参考答案）：dept 相符且 total_cents ≤ cap——先建者胜。"""
        for rule in self._rules:
            if rule.dept == dept and total_cents <= rule.max_total_cents:
                return rule
        return None


def admit(ticket: dict, rules: RuleBook) -> bool:
    """新单进门的自动批准（参考答案）：命中即代行批准（事件+True），未命中留给人工。"""
    hit = rules.match(ticket["dept"], ticket["total_cents"])
    if hit is None:
        return False
    emit("approval.auto_applied", {"ticket_id": ticket["ticket_id"], "rule_id": hit.rule_id})
    return True
