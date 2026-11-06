"""计税引擎手算对账（零 key）。

期望值按 2025 年综合所得年度汇算口径手算：
收入额 = 工资全额 + 劳务×80% + 稿酬×80%×70%
扣除 = 基本减除 60000 + 三险一金 + 佐证齐全的专项附加 + 其他
税额 = 应纳税所得额 × 税率 − 速算扣除数（分档）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tax_calc.engine import (
    calc_annual_reconciliation,
    calc_tax,
    find_bracket,
    income_amount,
    incomplete_evidence_items,
    total_deduction,
)

DATA = Path(__file__).resolve().parents[2] / "data"
BRACKETS = json.loads((DATA / "tax_brackets_2025.json").read_text(encoding="utf-8"))["brackets"]
PROFILES = {
    p["taxpayer_id"]: p for p in json.loads((DATA / "taxpayer_profiles.json").read_text(encoding="utf-8"))["profiles"]
}


def test_income_amount_折算口径():
    assert income_amount({"wages": 300000, "labor_remuneration": 20000, "author_remuneration": 0}) == 316000
    # 稿酬 ×80%×70% = ×56%
    assert income_amount({"wages": 0, "labor_remuneration": 80000, "author_remuneration": 40000}) == 86400


def test_total_deduction_fail_closed():
    # 李四：继续教育材料缺失，该项 3600 元不计入
    lisi = PROFILES["T2025-002"]
    # 60000 + 36000(三险一金) + 24000 + 30000（材料齐的两项）+ 0 = 150000
    assert total_deduction(lisi) == 150000
    assert incomplete_evidence_items(lisi) == ["继续教育（3600 元）"]


@pytest.mark.parametrize(
    ("taxable", "level", "rate"),
    [
        (36000, 1, 0.03),
        (36001, 2, 0.10),
        (144000, 2, 0.10),  # 边界：含下不含上
        (166000, 3, 0.20),
        (434800, 5, 0.30),
    ],
)
def test_find_bracket(taxable, level, rate):
    bracket = find_bracket(taxable, BRACKETS)
    assert bracket["level"] == level
    assert bracket["rate"] == rate


def test_calc_tax_负数按零():
    assert calc_tax(-5000, BRACKETS) == 0
    assert calc_tax(166000, BRACKETS) == 166000 * 0.20 - 16920


@pytest.mark.parametrize(
    ("tid", "income", "deduction", "taxable", "tax", "net"),
    [
        # 张三：316000 − 150000 = 166000 → 20% 档 16280 → 已预缴 18000 → 应退 1720
        ("T2025-001", 316000, 150000, 166000, 16280, -1720),
        # 李四：584800 − 150000 = 434800 → 30% 档 77520 → 应退 8480（继续教育扣除已 fail-closed）
        ("T2025-002", 584800, 150000, 434800, 77520, -8480),
        # 王五：206400 − 94000 = 112400 → 10% 档 8720 → 应退 3280
        ("T2025-003", 206400, 94000, 112400, 8720, -3280),
    ],
)
def test_calc_annual_reconciliation_三人对账(tid, income, deduction, taxable, tax, net):
    result = calc_annual_reconciliation(PROFILES[tid], BRACKETS)
    assert result["income_amount"] == income
    assert result["total_deduction"] == deduction
    assert result["taxable_income"] == taxable
    assert result["tax_amount"] == tax
    assert result["payable_or_refund"] == net
