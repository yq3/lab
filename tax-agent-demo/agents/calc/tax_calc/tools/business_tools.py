"""计税 agent 业务工具。

工具设计遵循 tool-design 调研结论：
- 面向结果而非 1:1 透传业务 API；docstring 即 prompt 工程（何时用/参数含义/返回结构）
- 只读/写操作分明（本 agent 全只读；写操作在申报 agent）
- 返回 JSON 字符串（模型可解析，也便于跨 A2A 传输）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from shared.config import DATA_DIR
from tax_calc.engine import calc_tax, find_bracket

_PROFILES_FILE = DATA_DIR / "taxpayer_profiles.json"
_BRACKETS_FILE = DATA_DIR / "tax_brackets_2025.json"


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _find_profile(taxpayer_id: str) -> dict[str, Any] | None:
    profiles = _load(_PROFILES_FILE)["profiles"]
    return next((p for p in profiles if p["taxpayer_id"] == taxpayer_id), None)


@tool
def lookup_taxpayer_profile(taxpayer_id: str) -> str:
    """查询纳税人年度档案（收入构成、已预缴税额、专项扣除明细）。

    Args:
        taxpayer_id: 纳税人编号，如 T2025-001。

    Returns:
        档案 JSON 字符串；查无此人时返回 {"error": "..."}。
    """
    profile = _find_profile(taxpayer_id)
    if profile is None:
        return json.dumps({"error": f"纳税人 {taxpayer_id} 不存在，请核对编号"}, ensure_ascii=False)
    return json.dumps(profile, ensure_ascii=False)


@tool
def get_tax_brackets(year: int = 2025) -> str:
    """查询综合所得年度税率表（各级距、税率、速算扣除数、基本减除费用）。

    Args:
        year: 税务年度，当前仅支持 2025。

    Returns:
        税率表 JSON 字符串；年度不支持时返回 {"error": "..."}。
    """
    data = _load(_BRACKETS_FILE)
    if year != data["bracket_year"]:
        return json.dumps({"error": f"暂无 {year} 年税率表（当前仅支持 {data['bracket_year']}）"}, ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False)


@tool
def verify_special_deductions(taxpayer_id: str) -> str:
    """校验专项附加扣除及其佐证材料齐全性（申报前必查）。

    Args:
        taxpayer_id: 纳税人编号。

    Returns:
        JSON：{"complete": bool, "items": [...全部项及材料状态], "missing": [缺失项描述]}。
        missing 非空时这些扣除项在计税中不会被计入（fail-closed）。
    """
    profile = _find_profile(taxpayer_id)
    if profile is None:
        return json.dumps({"error": f"纳税人 {taxpayer_id} 不存在"}, ensure_ascii=False)
    items = [
        {
            "type": item["type"],
            "amount": item["amount"],
            "evidence_complete": item.get("evidence_complete", False),
        }
        for item in profile.get("special_extra_deductions", [])
    ]
    missing = [
        f"{item['type']}（{item['amount']} 元）"
        for item in profile.get("special_extra_deductions", [])
        if not item.get("evidence_complete", False)
    ]
    note = profile.get("missing_evidence_note", "")
    return json.dumps(
        {"complete": not missing, "items": items, "missing": missing, "note": note},
        ensure_ascii=False,
    )


@tool
def calculate_income_tax(taxable_income: int) -> str:
    """按年度税率表计算综合所得应纳税额（速算扣除数法）。

    Args:
        taxable_income: 全年应纳税所得额（整数元，收入额合计减去全部扣除后的余额）。

    Returns:
        JSON：{"taxable_income": ..., "tax_amount": ..., "bracket_level": ..., "rate": ...}。
    """
    data = _load(_BRACKETS_FILE)
    brackets = data["brackets"]
    tax = calc_tax(taxable_income, brackets)
    bracket = find_bracket(taxable_income, brackets)
    return json.dumps(
        {
            "taxable_income": taxable_income,
            "tax_amount": tax,
            "bracket_level": bracket["level"],
            "rate": bracket["rate"],
        },
        ensure_ascii=False,
    )


CALC_TOOLS = [lookup_taxpayer_profile, get_tax_brackets, verify_special_deductions, calculate_income_tax]
