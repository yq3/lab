# 练习 2（单变量编辑约束：只改 TODO 标注的字段约束与 INVALID_CASES 表，其余不要动）
"""补 Pydantic 模型约束，再补一张非法样本表——「构造即验证」的双向练习。

场景：报销明线的「发票录入」环节。模型语义（test_ex2.py 里的合法样本按它构造）：
  receipt_no   发票号，形如 RCP-2026-000123（RCP-年份 4 位-流水 6 位）；
  amount_cents 金额，整数分：必须 > 0，且单张不超过 5000 分（L0.1 单笔上限同款）；
  payer        付款方名称，不允许空串。

你要做两件事：
  1. TODO(ex2a)：给三个字段加上能表达上述语义的约束（pattern / gt+le / min_length）；
  2. TODO(ex2b)：补 INVALID_CASES——至少 4 组、覆盖三个字段各自的违规，
     每行 (kind, payload)：kind 声明违反哪个字段（"receipt_no"/"amount_cents"/"payer"），
     payload 是会触发 ValidationError 的 dict，且**只违反 kind 这一个字段**——
     验收会比对 Pydantic 实际报错位置与 kind 是否一致，错标 kind 骗不过。
     覆盖是否达标由 meta-test 机器验收。
完成后：uv run pytest exercises/test_ex2.py 全绿。
"""

from pydantic import BaseModel  # TODO(ex2a): 完成约束时需要再从 pydantic import Field


class ReceiptSubmission(BaseModel):
    """发票提交单。"""

    receipt_no: str  # TODO(ex2a): 加 pattern 约束
    amount_cents: int  # TODO(ex2a): 加范围约束（> 0 且 <= 5000）
    payer: str  # TODO(ex2a): 加非空约束


# TODO(ex2b): 每行形如 ("receipt_no", {"receipt_no": "bad", "amount_cents": 100, "payer": "美团"}),
INVALID_CASES: list[tuple[str, dict[str, object]]] = []
