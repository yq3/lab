"""报销单时点快照——检查员被允许知道的全部事实（对版 hedge_fund/features/snapshot.py）。

产品原则：让 LLM 对事实推理，而非重做算术——总额、剩余预算、发票校验结果
全部由 Python 预计算进快照，人格检查员只读 render() 出的文本投票。

content_hash 是缓存的地基（对版 FundamentalsSnapshot.content_hash）：
同一张单子无论构建多少次，hash 必然一致——「同数据不二次付费」靠它成立。
产品用 pydantic 的 model_dump_json 做确定性序列化（字段按声明序、不走 json.dumps
的插入序），本课照抄；§5 的「相等不等哈希」坑位讲的就是这件事的另一半。

数据来源：data/expense/review_mock.json（明线素材唯一来源 data/，Unit 3 同一份四单）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

REVIEW_FILE = Path(__file__).resolve().parents[4] / "data" / "expense" / "review_mock.json"

# 单笔明细上限（分）：与 review_mock.json 的 limits.item_over_cents 同源同值
ITEM_LIMIT_CENTS = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))["limits"]["item_over_cents"]


class ClaimSnapshot(BaseModel):
    """一张报销单的时点快照（对版 FundamentalsSnapshot——纯数据，建一次、哈希、喂给人格）。

    extra="forbid"：对版产品 fund/spec.py 的纪律——快照是要哈希、要进审计的数据，
    多一个字段就该在构造期炸响，不是等到哈希对不上时才疑惑。
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    submitter: str
    purpose: str
    items: dict[str, int] = Field(description="明细名 -> 金额（分）", default_factory=dict)
    total_cents: int = Field(description="Python 预计算的明细总额（分）——LLM 不重做算术")
    dept: str
    remaining_cents: int = Field(description="Python 预核实的部门剩余预算（分）")
    invoice_ids: list[str] = Field(default_factory=list)
    invoice_valid: bool = Field(description="Python 预核实的发票校验结果")
    invoice_reason: str = Field(default="", description="发票校验的人类可读原因")

    @property
    def content_hash(self) -> str:
        """内容的稳定哈希（对版 content_hash，缓存 key 的地基）。"""
        canonical = self.model_dump_json()
        return hashlib.sha256(canonical.encode()).hexdigest()[:24]

    def render(self) -> str:
        """压成给 LLM 的紧凑文本（对版 render()——快照的 prompt 形态）。"""
        items = "、".join(f"{name} {cents} 分" for name, cents in self.items.items())
        verdict = "通过" if self.invoice_valid else "未通过"
        return (
            f"报销单 {self.claim_id}（{self.submitter}，{self.purpose}）。\n"
            f"明细：{items}；总额 {self.total_cents} 分。\n"
            f"部门 {self.dept} 剩余预算 {self.remaining_cents} 分。\n"
            f"发票校验：{verdict}（{self.invoice_reason}）。"
        )


def build_snapshot(claim_id: str) -> ClaimSnapshot:
    """从共享 mock 素材构建快照（对版 build_snapshot 的数据预取角色）。"""
    data = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
    claim = next((c for c in data["claims"] if c["id"] == claim_id), None)
    if claim is None:
        raise KeyError(f"claim_not_found: {claim_id}")
    budget = next(b for b in data["budgets"] if b["dept"] == claim["dept"])
    invoice_id = claim["invoice_ids"][0]
    invoice = next((i for i in data["invoices"] if i["id"] == invoice_id), None)
    return ClaimSnapshot(
        claim_id=claim["id"],
        submitter=claim["submitter"],
        purpose=claim["purpose"],
        items={f"明细{i + 1}": cents for i, cents in enumerate(claim["items_cents"])},
        total_cents=sum(claim["items_cents"]),
        dept=claim["dept"],
        remaining_cents=budget["budget_cents"] - budget["spent_cents"],
        invoice_ids=list(claim["invoice_ids"]),
        invoice_valid=bool(invoice and invoice["valid"]),
        invoice_reason=invoice["reason"] if invoice else "invoice_not_found",
    )
