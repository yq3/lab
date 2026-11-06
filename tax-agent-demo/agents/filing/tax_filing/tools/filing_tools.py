"""申报 agent 业务工具：申报表生成 / 校验 / 提交 / 状态查询。

工具设计要点（tool-design 军规落地）：
- submit_return 是全链路唯一的"写外部系统"操作，幂等键必带
- generate_return_draft / validate_return_draft 落盘真实文件（与 agent 内置
  write_file 共享同一个 FilesystemBackend root，模型可以直接 read_file 复核）
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from shared.config import DATA_DIR
from tax_filing import tax_bureau_mock

# 与 agent 的 FilesystemBackend root 一致：模型内置文件工具与业务工具看到同一目录
WORKSPACE_DIR = Path(__file__).resolve().parent.parent / "workspace"


def _find_profile(taxpayer_id: str) -> dict[str, Any] | None:
    with (DATA_DIR / "taxpayer_profiles.json").open(encoding="utf-8") as f:
        profiles = json.load(f)["profiles"]
    return next((p for p in profiles if p["taxpayer_id"] == taxpayer_id), None)


@tool
def generate_return_draft(
    taxpayer_id: str,
    year: int,
    taxpayer_name: str,
    income_amount: int,
    total_deduction: int,
    taxable_income: int,
    tax_amount: int,
    prepaid_tax: int,
    payable_or_refund: int,
) -> str:
    """依据计税结论生成申报表草稿，落盘为 JSON 文件。

    Args:
        taxpayer_id: 纳税人编号。
        year: 税务年度。
        taxpayer_name: 纳税人姓名。
        income_amount: 收入额合计（整数元，计税结论里的折算口径）。
        total_deduction: 扣除合计（整数元）。
        taxable_income: 应纳税所得额（整数元）。
        tax_amount: 应纳税额（整数元）。
        prepaid_tax: 已预缴税额（整数元）。
        payable_or_refund: 应补(退)税额，正数应补、负数应退（整数元）。

    Returns:
        JSON：{"file_path": "工作区内相对路径", "file_name": "..."}。file_path 采用
        agent 工作区相对路径——内置 read_file 可直接复核；也可直接传给
        validate_return_draft 与 submit_return。
    """
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"return_draft_{taxpayer_id}_{year}.json"
    (WORKSPACE_DIR / file_name).write_text(
        json.dumps(
            {
                "form_type": "个人所得税年度自行申报表（A 类）",
                "taxpayer_id": taxpayer_id,
                "taxpayer_name": taxpayer_name,
                "year": year,
                "income_amount": income_amount,
                "total_deduction": total_deduction,
                "taxable_income": taxable_income,
                "tax_amount": tax_amount,
                "prepaid_tax": prepaid_tax,
                "payable_or_refund": payable_or_refund,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # 关键：返回相对路径（内置文件工具与业务工具共用同一套路径词汇），绝对路径会被
    # FilesystemBackend(virtual_mode) 拒读，模型会陷入"复核失败→重试"死循环
    return json.dumps({"file_path": file_name, "file_name": file_name}, ensure_ascii=False)


def _resolve_workspace_path(file_path: str) -> Path:
    """解析草稿路径：相对路径按工作区解析；绝对路径原样接受（测试/外部场景）。"""
    path = Path(file_path)
    return path if path.is_absolute() else WORKSPACE_DIR / path


@tool
def validate_return_draft(file_path: str, taxpayer_id: str) -> str:
    """校验申报表草稿：金额勾稽关系 + 纳税人档案一致性 + 佐证材料齐全性。

    Args:
        file_path: generate_return_draft 返回的草稿路径。
        taxpayer_id: 纳税人编号（用于对照档案与材料状态）。

    Returns:
        JSON：{"valid": bool, "errors": [...勾稽错误], "missing_evidence": [...材料缺失项],
        "note": "人工提示"}。
        valid=false 且 missing_evidence 非空时：按系统约定以 [[NEED_INPUT]] 前缀回复
        请求补充材料；仅 errors 非空时直接修正后重新生成。
    """
    resolved = _resolve_workspace_path(file_path)
    if not resolved.exists():
        return json.dumps(
            {"valid": False, "errors": [f"草稿文件不存在：{file_path}"], "missing_evidence": []}, ensure_ascii=False
        )
    draft = json.loads(resolved.read_text(encoding="utf-8"))
    errors: list[str] = []

    # 勾稽关系
    if draft["taxable_income"] != draft["income_amount"] - draft["total_deduction"]:
        errors.append(
            "勾稽不平：应纳税所得额 "
            f"{draft['taxable_income']} ≠ 收入额 {draft['income_amount']} − 扣除 {draft['total_deduction']}"
        )
    if draft["payable_or_refund"] != draft["tax_amount"] - draft["prepaid_tax"]:
        errors.append(
            "勾稽不平：应补(退) "
            f"{draft['payable_or_refund']} ≠ 应纳税额 {draft['tax_amount']} − 已预缴 {draft['prepaid_tax']}"
        )

    # 档案一致性 + 材料齐全性
    profile = _find_profile(taxpayer_id)
    if profile is None:
        errors.append(f"档案中查无纳税人 {taxpayer_id}")
        missing: list[str] = []
    else:
        if draft["taxpayer_name"] != profile["name"]:
            errors.append(f"姓名不一致：草稿 {draft['taxpayer_name']} ≠ 档案 {profile['name']}")
        missing = [
            f"{item['type']}（{item['amount']} 元）"
            for item in profile.get("special_extra_deductions", [])
            if not item.get("evidence_complete", False)
        ]

    result = {
        "valid": not errors and not missing,
        "errors": errors,
        "missing_evidence": missing,
        "note": profile.get("missing_evidence_note", "") if profile else "",
    }
    return json.dumps(result, ensure_ascii=False)


@tool
def submit_return(file_path: str, idempotency_key: str) -> str:
    """把申报表草稿提交到电子税务局（高风险写操作，已由主 agent 人工审批后才会到达这里）。

    Args:
        file_path: 通过 validate_return_draft 校验的草稿路径。
        idempotency_key: 幂等键（防网络重试导致重复申报），
            建议格式 "taxpayer_id-year"（如 T2025-001-2025）。

    Returns:
        JSON：{"receipt_no": "受理回执号", "duplicate": bool, "message": "..."}。
    """
    resolved = _resolve_workspace_path(file_path)
    if not resolved.exists():
        return json.dumps({"error": f"草稿文件不存在：{file_path}"}, ensure_ascii=False)
    draft = json.loads(resolved.read_text(encoding="utf-8"))
    result = tax_bureau_mock.submit_return(draft, idempotency_key)
    return json.dumps(result, ensure_ascii=False)


@tool
def query_submission_status(receipt_no: str) -> str:
    """按回执号查询申报受理状态。

    Args:
        receipt_no: submit_return 返回的回执号（RCP- 开头）。

    Returns:
        JSON：{"receipt_no": ..., "status": "已受理", "submitted_at": ...}；查无回执返回 {"error": ...}。
    """
    result = tax_bureau_mock.query_submission(receipt_no)
    if result is None:
        return json.dumps(
            {"error": f"回执 {receipt_no} 不存在（注意：受理记录存进程内存，server 重启即清空）"}, ensure_ascii=False
        )
    return json.dumps(result, ensure_ascii=False)


FILING_TOOLS = [generate_return_draft, validate_return_draft, submit_return, query_submission_status]
