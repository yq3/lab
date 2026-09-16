"""Step1 判别联合：带 tag 精确分派 vs 无 tag 的顺序尝试歧义（零模型调用，讲义 §2 用）。

三段对照（Java 心智：Jackson 多态反序列化 @JsonTypeInfo(use=NAME)）：
1) 带 tag 的联合：tool 字段的 Literal 让 Pydantic 一步分派到具体步型——
   每个成员读自己的字段，报错也报到具体步型上；
2) 无 tag 的联合：两个同形状成员，Union 按声明顺序「先到先得」——
   数据本身无法表达「我要的是哪一个」，成员顺序换了、类型跟着换（歧义）；
3) 判别失败的错误形态：白名单外的 tool 得到 union_tag_invalid——错误指在
   steps[i] 的 tag 上（plan.validate_plan 据此映射 unknown_tool，见 plan.py）。
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from plan import Plan

# ---- 对照组：无 tag 的同形状对（判别信息被抽走——只剩数据形状）----


class RawBudget(BaseModel):
    dept: str
    limit_cents: int


class RawLedger(BaseModel):
    dept: str
    limit_cents: int


# ---- 对照组：带 tag 的同形状对（source 的 Literal 是判别符）----


class BudgetProbe(BaseModel):
    source: Literal["budget"]
    dept: str
    limit_cents: int


class LedgerProbe(BaseModel):
    source: Literal["ledger"]
    dept: str
    limit_cents: int


TaggedProbe = Annotated[BudgetProbe | LedgerProbe, Field(discriminator="source")]


def main() -> None:
    print("== Step1 判别联合：tag 精确分派 vs 顺序尝试歧义（零模型调用） ==")

    print("[1] 计划步联合（Field(discriminator='tool')）：按 tag 精确分派")
    legal = json.dumps(
        {
            "claim_total_cents": 7100,
            "steps": [
                {"step_id": "s1", "tool": "fetch_claim", "claim_id": "CLM-2026-0001", "produces": "claim"},
                {"step_id": "s2", "tool": "check_budget", "dept": "SALES", "produces": "budget"},
                {"step_id": "s3", "tool": "verify_invoice", "invoice_id": "INV-2026-0001", "produces": "invoice"},
            ],
        }
    )
    plan = TypeAdapter(Plan).validate_json(legal)
    for step in plan.steps:
        print(f"  steps[{step.step_id}] -> {type(step).__name__:<18} tool={step.tool!r}")

    print("[2] 同形状两成员、无 tag：Union 按声明顺序先到先得（歧义）")
    raw = {"dept": "DEV", "limit_cents": 5000}  # 两个模型都完全吃得下这份数据
    first_wins = TypeAdapter(RawBudget | RawLedger).validate_python(raw)
    print(f"  验证 {raw} -> {type(first_wins).__name__}（声明顺序第一个：RawBudget 抢先）")
    swapped = TypeAdapter(RawLedger | RawBudget).validate_python(raw)
    print(f"  成员顺序对调后再验 -> {type(swapped).__name__}（同一份数据，类型跟着声明顺序变）")
    print("  <- 无 tag 时「是哪个」取决于声明顺序而非数据——判别信息丢了，这就是歧义")

    print("[2b] 同一对加上 tag（discriminator='source'）：数据自带判别信息")
    ledger_like = {"source": "ledger", "dept": "DEV", "limit_cents": 5000}
    tagged = TypeAdapter(TaggedProbe).validate_python(ledger_like)
    print(f"  验证 source={ledger_like['source']!r} -> {type(tagged).__name__}（精确分派，与声明顺序无关）")
    swapped_tagged = TypeAdapter(Annotated[LedgerProbe | BudgetProbe, Field(discriminator="source")])
    print(
        f"  成员顺序对调后再验 -> {type(swapped_tagged.validate_python(ledger_like)).__name__}（tag 在，顺序说了不算）"
    )

    print("[3] 判别失败：白名单外工具的错误形态（指在 tag 上）")
    dirty = json.loads(legal)
    dirty["steps"][1]["tool"] = "query_erp_balance"
    try:
        TypeAdapter(Plan).validate_python(dirty)
        print("  意外：没有报错？")
    except ValidationError as exc:
        error = exc.errors()[0]
        print(f"  ValidationError: type={error['type']} loc={error['loc']}")
        print(f"  msg={error['msg'].splitlines()[0]}")
        print("  <- 错误指在 steps[1] 的 tag 上——未知工具是「判别失败」，不是「字段拼错」")


if __name__ == "__main__":
    main()
