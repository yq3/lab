# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""always 规则修订：RuleBook 匹配器 + 自动批准接入 + 可审计规则记录（讲义 approvals 的规则半边同构）。

A6「批准并记住 = 可审计规则修订」：一条 always 规则要能回答审计四问——谁批的
（approved_by）、何时（approved_at）、批了什么 pattern（dept + max_total_cents）、
当时绑的是哪一版内容（content_hash）。它是账，不是内存 yes 集合。
A1 的自动半边：新单进门先查规则，命中即代行批准（approval.auto_applied 事件 + 零人审），
未命中返回假——单留给人工（对照 A2「无人在线不隐式作答」：自动面只答规则授权过的）。

given：ApprovalRule 模型（审计四问的字段全在）、事件表 emit、内容指纹 content_hash_of；
TODO 三处——grant（建一条可审计规则）、match（dept 相符且 total_cents ≤ cap 才命中）、
admit（新单进门的自动批准接入）。

完成判据：uv run pytest exercises/test_ex3.py 全绿——5 个测试：
  match 两维逐维断言（异部门不中 / 超 cap 不中 / 恰等 cap 命中）；
  同部门小额单零人审自动过（事件 approval.auto_applied 带 rule_id 与 ticket_id）；
  超 cap 或异部门不命中照常留给人工（无 auto 事件）；
  规则记录可审计（谁/何时可解析/pattern/绑定 hash 四问各有断言）；
  内容变了 hash 变、同内容 hash 确定（A6 内容绑定）。
grant 的时间戳需要顶部补 import（hints 第 3 级点名）。
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

EVENTS: list[dict] = []  # 事件表（given：极简版，测试夹具用 reset_events 复位）


def emit(event: str, data: dict) -> None:
    """记一条事件（given）。"""
    EVENTS.append({"event": event, "data": data})


def reset_events() -> None:
    """清空事件表（given：测试夹具复位用）。"""
    EVENTS.clear()


def content_hash_of(advice: dict, total_cents: int) -> str:
    """被审内容指纹（given，与讲义 graph.content_hash 同款）：规范化 JSON → sha256 前 16 位。"""
    payload = json.dumps({"advice": advice, "total_cents": total_cents}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ApprovalRule(BaseModel):
    """always 规则（given 模型）：审计四问各有一列——谁/何时/pattern/绑哪版内容。"""

    rule_id: str
    dept: str
    max_total_cents: int
    approved_by: str
    approved_at: str
    content_hash: str


class RuleBook:
    """规则簿（你的 TODO 在 grant 与 match）：「批准并记住」的完整闭环。"""

    def __init__(self) -> None:
        self._rules: list[ApprovalRule] = []

    def all(self) -> list[ApprovalRule]:
        """全部规则（given：审计读）。"""
        return list(self._rules)

    def grant(self, dept: str, cap_cents: int, approved_by: str, content_hash: str) -> ApprovalRule:
        """建一条可审计规则（你的 TODO）。

        问：rule_id 怎么编号（对照「rule-001」的期望）？approved_at 记什么——当前时间
        的 ISO 字符串从哪个标准库来？四个审计字段各自从哪个参数来？
        """
        # TODO(ex3): 建规则（编号/时间戳/四元组全录）并存进 self._rules
        raise NotImplementedError("TODO(ex3): grant")

    def match(self, dept: str, total_cents: int) -> ApprovalRule | None:
        """规则命中查询（你的 TODO）：dept 相符且 total_cents ≤ cap 才命中。

        问：两维条件怎么组合？命中返回什么、未命中返回什么（对照返回类型注解）？
        多条规则都可能命中时，返回哪条（讲义口径：先建者胜）？
        """
        # TODO(ex3): 匹配器（两维判定）
        raise NotImplementedError("TODO(ex3): match")


def admit(ticket: dict, rules: RuleBook) -> bool:
    """新单进门的自动批准（你的 TODO）：查规则——命中即代行批准。

    契约：命中 → emit("approval.auto_applied", {"ticket_id": ..., "rule_id": <命中规则的 id>})
    并返回 True；未命中 → 不发任何事件、返回 False（单留给人工）。
    问：ticket 里哪两个字段是匹配维度（对照 match 的形参）？
    """
    # TODO(ex3): 自动批准接入（查规则 + 事件 + 返回值）
    raise NotImplementedError("TODO(ex3): admit")
