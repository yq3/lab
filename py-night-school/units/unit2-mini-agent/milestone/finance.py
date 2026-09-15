"""报销域的两个工具：@tool 装饰器的第一批客户。

明线素材唯一来源：data/expense/budget_mock.json（夜校工程纪律）。
注意校验分层（讲义 L2.2 §2.5）：schema 只管「形状」（是 list[int]、单号格式对），
业务值（负数、超限）留给规则函数判断——负数金额必须能进 preapprove，
才有 "REJECT:INVALID_AMOUNT" 这个合法输出。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from tools import error_result, tool

# 与课时版（code/finance.py）唯一的差异：里程碑文件少一层目录，parents[4] -> parents[3]
BUDGET_FILE = Path(__file__).resolve().parents[3] / "data" / "expense" / "budget_mock.json"

ITEM_LIMIT_CENTS = 5000
TOTAL_LIMIT_CENTS = 500000


class PreapproveArgs(BaseModel):
    """preapprove 的参数形状：明细金额列表，单位分（允许任何整数——业务合法性由规则判断）。"""

    items_cents: list[int] = Field(min_length=1, description="报销明细金额列表，单位分")


class GetClaimArgs(BaseModel):
    """get_claim 的参数形状：单号格式用 pattern 在门口拦住幻觉单号。"""

    claim_id: str = Field(pattern=r"^CLM-\d{4}-\d{4}$", description="报销单号，形如 CLM-2026-0001")


def _load_claims() -> list[dict]:
    return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))["expense_claims"]


@tool(PreapproveArgs)
def preapprove(items_cents: list[int]) -> str:
    """对报销单明细金额做规则预审，返回 PASS 或 REJECT:<原因>。"""
    if any(cents <= 0 for cents in items_cents):
        return "REJECT:INVALID_AMOUNT"
    if any(cents > ITEM_LIMIT_CENTS for cents in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    if sum(items_cents) > TOTAL_LIMIT_CENTS:
        return "REJECT:TOTAL_OVER_LIMIT"
    return "PASS"


@tool(GetClaimArgs)
def get_claim(claim_id: str) -> str:
    """按单号查询报销单（提交人、事由、明细金额）；查无此单返回 error JSON。"""
    for claim in _load_claims():
        if claim["id"] == claim_id:
            return json.dumps(
                {
                    "id": claim["id"],
                    "submitter": claim["submitter"],
                    "purpose": claim["purpose"],
                    "items_cents": claim["items_cents"],
                },
                ensure_ascii=False,
            )
    return error_result(f"claim_not_found: {claim_id}")


# 本模块被 import 时，两个工具已登记进 TOOL_REGISTRY（装饰器副作用）
