"""综合所得年度汇算计税引擎（纯函数，零 LLM 依赖，可独立单测）。

口径（2025 年现行）：
- 收入额：工资薪金全额；劳务报酬 ×80%；稿酬 ×80%×70%
- 应纳税所得额 = 收入额合计 − 基本减除费用(60000) − 专项扣除(三险一金)
                 − 专项附加扣除 − 其他扣除
- 应纳税额：全年应纳税所得额按年度税率表超额累进（速算扣除数法）
- 应补(退)税额 = 应纳税额 − 已预缴税额（正=应补，负=应退）

金额一律整数元。
"""

from __future__ import annotations

from typing import Any

BASIC_DEDUCTION = 60000


def income_amount(incomes: dict[str, int]) -> int:
    """收入额折算（整数元）。"""
    wages = incomes.get("wages", 0)
    labor = incomes.get("labor_remuneration", 0)
    author = incomes.get("author_remuneration", 0)
    return wages + round(labor * 0.8) + round(author * 0.8 * 0.7)


def total_deduction(profile: dict[str, Any]) -> int:
    """扣除合计 = 基本减除费用 + 三险一金 + 专项附加扣除 + 其他扣除。

    注意：佐证材料缺失的专项附加扣除项**不计入**（fail-closed：
    材料不齐的扣除不放行，由申报环节补材料后再算）。
    """
    special = sum(
        item["amount"] for item in profile.get("special_extra_deductions", []) if item.get("evidence_complete", False)
    )
    return BASIC_DEDUCTION + profile.get("social_insurance", 0) + special + profile.get("other_deductions", 0)


def incomplete_evidence_items(profile: dict[str, Any]) -> list[str]:
    """列出佐证材料缺失的专项附加扣除项描述。"""
    return [
        f"{item['type']}（{item['amount']} 元）"
        for item in profile.get("special_extra_deductions", [])
        if not item.get("evidence_complete", False)
    ]


def find_bracket(taxable_income: int, brackets: list[dict[str, Any]]) -> dict[str, Any]:
    """定位应纳税所得额适用的税率级。

    税法口径"含上不含下"：级距边界归属上一档（36000 元适用 3% 档，
    36001 元起适用 10% 档），即取第一个 max >= taxable 的档。末级无上界。
    """
    if taxable_income < 0:
        return brackets[0]
    for bracket in brackets:
        if bracket["max"] is None or taxable_income <= bracket["max"]:
            return bracket
    return brackets[-1]


def calc_tax(taxable_income: int, brackets: list[dict[str, Any]]) -> int:
    """应纳税额 = 应纳税所得额 × 税率 − 速算扣除数（负数按 0 计）。"""
    if taxable_income <= 0:
        return 0
    bracket = find_bracket(taxable_income, brackets)
    return round(taxable_income * bracket["rate"] - bracket["quick_deduction"])


def calc_annual_reconciliation(profile: dict[str, Any], brackets: list[dict[str, Any]]) -> dict[str, Any]:
    """综合所得年度汇算全流程计算，返回结构化结论。"""
    income = income_amount(profile["incomes"])
    deduction = total_deduction(profile)
    taxable = income - deduction
    tax = calc_tax(taxable, brackets)
    prepaid = profile.get("prepaid_tax", 0)
    bracket = find_bracket(taxable, brackets) if taxable > 0 else brackets[0]
    return {
        "taxpayer_id": profile["taxpayer_id"],
        "taxpayer_name": profile["name"],
        "year": profile["year"],
        "income_amount": income,
        "total_deduction": deduction,
        "taxable_income": taxable,
        "tax_amount": tax,
        "prepaid_tax": prepaid,
        "payable_or_refund": tax - prepaid,
        "bracket_level": bracket["level"],
        "rate": bracket["rate"],
    }
