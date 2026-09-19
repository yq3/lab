"""Unit 3 同题 demo 的两个 mock 工具（框架课对版：L3.1–L3.6 各持一份，
改一处必须同步全部副本——宪法「共享模块对版纪律」）。

L5.1 副本声明（对版纪律「合理差异就地注释」）：从 L3.2 原样复制，本体零改动；
毕业设计沿用同一素材（review_mock.json）与同一 CALL_LOG 取证纪律，
新增的 fetch_claim 步直接复用本模块的纯读取函数 claim_view（不记 CALL_LOG）。

工具本体是纯函数：读 data/expense/review_mock.json（明线素材唯一来源 data/），
不 import 任何框架——框架绑定（装饰器 / 包装器 / FunctionTool）在各课 demo.py 里做，
正好用来观察「同一份工具代码，四个框架各怎么包装」。

CALL_LOG 记录每次真实执行的工具名——共用验收脚本用它证明「工具真的被框架调过」，
而不是剧本模型自说自话。
"""

from __future__ import annotations

import json
from pathlib import Path

# 里程碑副本声明（对版纪律「合理差异就地注释」）：与 L5.4 code/mock_tools.py 唯一差异是
# 这一行——里程碑模块在仓库内浅一层（py-night-school/units/unit5-capstone/milestone/ 对
# L5.4 的 .../L5.4-execution-gate/code/），data/ 的相对深度由 parents[4] 改为 parents[3]
# （宪法先例：「复制到不同目录层级时核对 parents[N] 深度」）；其余逐字节相同，diff 可验。
REVIEW_FILE = Path(__file__).resolve().parents[3] / "data" / "expense" / "review_mock.json"

ITEM_LIMIT_CENTS = 5000  # 单笔上限（分），与 review_mock.json 的 limits.item_over_cents 同值

CALL_LOG: list[str] = []  # 工具真实执行的取证（共用验收脚本断言用）


def _load() -> dict:
    return json.loads(REVIEW_FILE.read_text(encoding="utf-8"))


# ---- 纯读取（不记 CALL_LOG）——review_rules 预计算剧本时用，避免污染取证 ----


def budget_row(dept: str) -> dict | None:
    """按部门读预算行；查无返回 None。"""
    for row in _load()["budgets"]:
        if row["dept"] == dept:
            return row
    return None


def invoice_row(invoice_id: str) -> dict | None:
    """按发票号读校验行；查无返回 None。"""
    for row in _load()["invoices"]:
        if row["id"] == invoice_id:
            return row
    return None


def claims_table() -> list[dict]:
    """全部审查用例（含 expect_* 判分字段）——共用验收脚本的用例来源。"""
    return _load()["claims"]


def claim_view(claim_id: str) -> dict:
    """把 mock 表拼成单据审查上下文：明细（含总额）+ 部门 + 关联发票。

    demo 用它组装发给模型的 user 消息；剧本生成器（review_rules）也用它预计算台词。
    """
    for claim in _load()["claims"]:
        if claim["id"] == claim_id:
            return {
                "id": claim["id"],
                "submitter": claim["submitter"],
                "purpose": claim["purpose"],
                "items_cents": claim["items_cents"],
                "total_cents": sum(claim["items_cents"]),
                "dept": claim["dept"],
                "invoice_ids": claim["invoice_ids"],
            }
    raise KeyError(f"claim_not_found: {claim_id}")


# ---- 工具本体（记 CALL_LOG）——四个框架课绑定的是这两个函数 ----


def check_budget(dept: str) -> dict:
    """查预算余额：返回部门的预算 / 已花 / 剩余，单位都是分。"""
    row = budget_row(dept)
    if row is None:
        return {"dept": dept, "error": f"unknown_dept: {dept}"}
    CALL_LOG.append("check_budget")
    return {
        "dept": dept,
        "budget_cents": row["budget_cents"],
        "spent_cents": row["spent_cents"],
        "remaining_cents": row["budget_cents"] - row["spent_cents"],
    }


def verify_invoice(invoice_id: str) -> dict:
    """发票校验：返回发票是否有效与人类可读原因。"""
    row = invoice_row(invoice_id)
    if row is None:
        CALL_LOG.append("verify_invoice")
        return {"id": invoice_id, "valid": False, "reason": "invoice_not_found"}
    CALL_LOG.append("verify_invoice")
    return {"id": row["id"], "valid": row["valid"], "reason": row["reason"]}
