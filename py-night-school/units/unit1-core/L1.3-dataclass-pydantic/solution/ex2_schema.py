"""参考答案（ex2）——先完成练习再看。

要点：三种约束参数各就各位（pattern / gt+le / min_length）；
非法样本表覆盖三个字段 + 边界（5001 恰好越上限）+ 下界（0 与 -1 各体现一种「不正」）。
"""

from pydantic import BaseModel, Field


class ReceiptSubmission(BaseModel):
    """发票提交单。"""

    receipt_no: str = Field(pattern=r"^RCP-\d{4}-\d{6}$")
    amount_cents: int = Field(gt=0, le=5000)
    payer: str = Field(min_length=1)


INVALID_CASES: list[tuple[str, dict[str, object]]] = [
    ("receipt_no", {"receipt_no": "bad", "amount_cents": 100, "payer": "美团"}),
    ("receipt_no", {"receipt_no": "RCP-26-1", "amount_cents": 100, "payer": "美团"}),  # 年份/流水位数不对
    ("amount_cents", {"receipt_no": "RCP-2026-000001", "amount_cents": 0, "payer": "美团"}),  # 下界
    ("amount_cents", {"receipt_no": "RCP-2026-000001", "amount_cents": 5001, "payer": "美团"}),  # 上界+1
    ("payer", {"receipt_no": "RCP-2026-000001", "amount_cents": 100, "payer": ""}),  # 空串
]
