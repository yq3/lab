"""审查规则表与离线剧本生成器（框架课对版）——Unit 3 demo 的「替身模型大脑」。

诚实边界（各课讲义必须向学员讲清）：离线验收时模型台词由本模块预计算——
被测对象是框架的管道（工具分发、消息回喂、结构化输出解析），不是模型的质量。
真实端点模式下，这些决策由模型自己读工具结果后作出——规则表就是那时
system 提示里写的审查规则，两者同源。

规则优先级（教学约定的审查规则，先命中先停）：
  1) 明细含非正数金额     → ESCALATE / REJECT:INVALID_AMOUNT（脏数据转人审）
  2) 任一明细 > 5000 分    → REJECT / REJECT:ITEM_OVER_LIMIT
  3) 关联发票校验未过      → REJECT / REJECT:INVOICE_INVALID
  4) 总额 > 部门剩余预算   → REJECT / REJECT:BUDGET_EXCEEDED
  5) 以上全不中            → APPROVE / PASS
"""

from __future__ import annotations

import mock_tools
from advice import Advice


def decide(view: dict, budget: dict, invoice: dict) -> Advice:
    """按规则表对「单据视图 + 工具结果」出建议单——替身模型的决策函数。"""
    remaining_cents = budget["budget_cents"] - budget["spent_cents"]
    if any(cents <= 0 for cents in view["items_cents"]):
        decision, reason = "ESCALATE", "REJECT:INVALID_AMOUNT"
    elif any(cents > mock_tools.ITEM_LIMIT_CENTS for cents in view["items_cents"]):
        decision, reason = "REJECT", "REJECT:ITEM_OVER_LIMIT"
    elif invoice["valid"] is False:
        decision, reason = "REJECT", "REJECT:INVOICE_INVALID"
    elif view["total_cents"] > remaining_cents:
        decision, reason = "REJECT", "REJECT:BUDGET_EXCEEDED"
    else:
        decision, reason = "APPROVE", "PASS"
    return Advice(
        claim_id=view["id"],
        decision=decision,
        reason=reason,
        remaining_cents=remaining_cents,
    )


def script_for(claim_id: str) -> tuple[list[dict], str, Advice]:
    """预生成剧本模型的全部台词：第 1 轮并行调用两个工具，第 2 轮给出建议单 JSON。

    返回 (第一轮 tool_calls 列表, 第二轮最终文本, 预期 Advice)——demo 只负责把台词
    喂给 mock 端点、把框架跑起来；预期 Advice 供讲义演示对照，验收以 test_contract 为准。
    注意：本函数只走纯读取（budget_row / invoice_row），不污染 mock_tools.CALL_LOG。
    """
    view = mock_tools.claim_view(claim_id)
    budget = mock_tools.budget_row(view["dept"])
    invoice = mock_tools.invoice_row(view["invoice_ids"][0])
    if budget is None or invoice is None:
        raise KeyError(f"mock 数据缺行: {claim_id}")
    expected = decide(view, budget, invoice)
    first_turn = [
        {"id": "call_budget", "name": "check_budget", "arguments": {"dept": view["dept"]}},
        {"id": "call_invoice", "name": "verify_invoice", "arguments": {"invoice_id": view["invoice_ids"][0]}},
    ]
    return first_turn, expected.model_dump_json(), expected
