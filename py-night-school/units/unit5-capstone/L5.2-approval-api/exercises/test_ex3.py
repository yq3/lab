"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

from datetime import datetime

import ex3_always as ex3


def _book() -> ex3.RuleBook:
    """一本已有一条 SALES≤8800 规则的规则簿（第一张 always 单批出来的）。"""
    rules = ex3.RuleBook()
    rules.grant("SALES", 8800, "审批人-老王", ex3.content_hash_of({"decision": "REJECT"}, 8800))
    return rules


def test_match_requires_dept_and_cap() -> None:
    """匹配器两维逐维断言：部门一维、金额上限一维，各单独破掉都不命中。"""
    rules = _book()
    hit = rules.match("SALES", 7100)
    assert hit is not None and hit.rule_id == "rule-001"  # 两维都中
    assert rules.match("SALES", 8801) is None  # 超 cap 一维破掉
    assert rules.match("DEV", 100) is None  # 异部门一维破掉
    boundary = rules.match("SALES", 8800)  # 边界：恰好等于 cap 也命中
    assert boundary is not None and boundary.rule_id == "rule-001"


def test_second_small_claim_auto_applies_without_human() -> None:
    """A1 完整闭环：同部门小额单零人审自动过——approval.auto_applied 带 rule_id 与 ticket_id。"""
    ex3.reset_events()
    rules = _book()
    ticket = {
        "ticket_id": "tkt-0002",
        "claim_id": "CLM-2026-0001",
        "dept": "SALES",
        "total_cents": 7100,
        "content_hash": "h2",
    }
    assert ex3.admit(ticket, rules) is True
    assert len(ex3.EVENTS) == 1  # 恰好一条事件——零人审
    assert ex3.EVENTS[0]["event"] == "approval.auto_applied"
    assert ex3.EVENTS[0]["data"] == {"ticket_id": "tkt-0002", "rule_id": "rule-001"}


def test_over_cap_or_other_dept_still_needs_human() -> None:
    """超 cap 或异部门不命中：不代行批准、不发事件——单照常留给人工。"""
    ex3.reset_events()
    rules = _book()
    over_cap = {"ticket_id": "t1", "claim_id": "C1", "dept": "SALES", "total_cents": 8801, "content_hash": "h"}
    other_dept = {"ticket_id": "t2", "claim_id": "C2", "dept": "DEV", "total_cents": 100, "content_hash": "h"}
    assert ex3.admit(over_cap, rules) is False
    assert ex3.admit(other_dept, rules) is False
    assert ex3.EVENTS == []  # 没有事件：不隐式作答，单在 pending 表里等人


def test_rule_record_is_auditable() -> None:
    """审计四问各有断言：谁批的 / 何时（可解析回时间戳）/ 批了什么 pattern / 绑哪版内容。"""
    rules = ex3.RuleBook()
    bound = ex3.content_hash_of({"decision": "APPROVE", "reason": "PASS", "remaining_cents": 10000}, 7100)
    rule = rules.grant("SALES", 8800, "审批人-老王", bound)
    assert rule.rule_id == "rule-001"  # 编号从 001 起
    assert rule.approved_by == "审批人-老王"  # 谁
    assert datetime.fromisoformat(rule.approved_at) is not None  # 何时：ISO 字符串可解析回时间戳
    assert (rule.dept, rule.max_total_cents) == ("SALES", 8800)  # 批了什么 pattern
    assert rule.content_hash == bound  # 绑的是批准时那版内容
    assert rules.all() == [rule]  # 规则入簿（审计读得到）


def test_content_hash_binds_content() -> None:
    """A6：内容变了 hash 变；同内容 hash 确定（可重复对账）。"""
    approve = {"decision": "APPROVE", "reason": "PASS", "remaining_cents": 10000}
    escalate = {"decision": "ESCALATE", "reason": "REJECT:APPROVAL_FEEDBACK", "remaining_cents": 10000}
    assert ex3.content_hash_of(approve, 7100) != ex3.content_hash_of(escalate, 7100)  # 建议单内容变
    assert ex3.content_hash_of(approve, 7100) != ex3.content_hash_of(approve, 8800)  # 总额变
    assert ex3.content_hash_of(approve, 7100) == ex3.content_hash_of(dict(approve), 7100)  # 同内容确定
    assert len(ex3.content_hash_of(approve, 7100)) == 16  # 形态：sha256 前 16 位
