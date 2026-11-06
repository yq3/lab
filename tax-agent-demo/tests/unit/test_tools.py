"""业务工具单测（零 key）：计税工具返回结构 + 申报工具全流程 + 幂等键。"""

from __future__ import annotations

import json

import pytest
from tax_calc.tools.business_tools import (
    calculate_income_tax,
    get_tax_brackets,
    lookup_taxpayer_profile,
    verify_special_deductions,
)
from tax_filing.tools.filing_tools import (
    generate_return_draft,
    query_submission_status,
    submit_return,
    validate_return_draft,
)

# ---------- 计税 agent 工具 ----------


def test_lookup_profile_命中与未命中():
    hit = json.loads(lookup_taxpayer_profile.invoke({"taxpayer_id": "T2025-001"}))
    assert hit["name"] == "张三"
    miss = json.loads(lookup_taxpayer_profile.invoke({"taxpayer_id": "NOPE"}))
    assert "error" in miss


def test_get_tax_brackets_年度校验():
    ok = json.loads(get_tax_brackets.invoke({"year": 2025}))
    assert len(ok["brackets"]) == 7
    bad = json.loads(get_tax_brackets.invoke({"year": 1999}))
    assert "error" in bad


def test_verify_special_deductions_缺材料列出():
    result = json.loads(verify_special_deductions.invoke({"taxpayer_id": "T2025-002"}))
    assert result["complete"] is False
    assert result["missing"] == ["继续教育（3600 元）"]
    assert "证书" in result["note"]


def test_calculate_income_tax():
    result = json.loads(calculate_income_tax.invoke({"taxable_income": 166000}))
    assert result["tax_amount"] == 16280
    assert result["bracket_level"] == 3


# ---------- 申报 agent 工具（工作区产物写到临时目录） ----------


@pytest.fixture
def draft_file(tmp_path, monkeypatch):
    """把申报工作区重定向到临时目录，测试自清理。"""
    monkeypatch.setattr("tax_filing.tools.filing_tools.WORKSPACE_DIR", tmp_path)
    return json.loads(
        generate_return_draft.invoke(
            {
                "taxpayer_id": "T2025-001",
                "year": 2025,
                "taxpayer_name": "张三",
                "income_amount": 316000,
                "total_deduction": 150000,
                "taxable_income": 166000,
                "tax_amount": 16280,
                "prepaid_tax": 18000,
                "payable_or_refund": -1720,
            }
        )
    )


def test_generate_return_draft_落盘(draft_file, tmp_path):
    path = tmp_path / draft_file["file_path"]  # file_path 为工作区相对路径
    assert path.exists()
    draft = json.loads(path.read_text(encoding="utf-8"))
    assert draft["form_type"].startswith("个人所得税年度自行申报表")


def test_validate_勾稽通过(draft_file):
    result = json.loads(
        validate_return_draft.invoke({"file_path": draft_file["file_path"], "taxpayer_id": "T2025-001"})
    )
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["missing_evidence"] == []


def test_路径词汇_相对路径全流程(draft_file, tmp_path):
    """generate 返回相对路径 → validate/submit/内置 read_file 同词汇可解析。

    回归：真实冒烟曾因 generate 返回绝对路径、内置 read_file 读不到而陷入死循环。
    """
    # generate 现在返回相对路径（草稿文件名本身）
    assert draft_file["file_path"] == draft_file["file_name"]
    # 相对路径走 validate（经工作区解析）
    result = json.loads(
        validate_return_draft.invoke({"file_path": draft_file["file_name"], "taxpayer_id": "T2025-001"})
    )
    assert result["valid"] is True
    # 相对路径走 submit（经工作区解析；幂等键带后缀避免与其他用例撞车）
    submitted = json.loads(
        submit_return.invoke({"file_path": draft_file["file_name"], "idempotency_key": "T2025-001-2025-rel"})
    )
    assert submitted["receipt_no"].startswith("RCP-")
    # 内置文件工具读同一相对路径（FilesystemBackend 与业务工具同根）
    from deepagents.backends import FilesystemBackend

    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
    read_result = backend.read(draft_file["file_name"])
    assert read_result.error is None
    assert read_result.file_data is not None
    assert "个人所得税年度自行申报表" in read_result.file_data["content"]


def test_validate_勾稽不平(draft_file, tmp_path):
    draft_path = tmp_path / draft_file["file_name"]
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["taxable_income"] += 1  # 破坏勾稽
    draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    result = json.loads(
        validate_return_draft.invoke({"file_path": draft_file["file_name"], "taxpayer_id": "T2025-001"})
    )
    assert result["valid"] is False
    assert any("勾稽不平" in e for e in result["errors"])


def test_validate_缺材料(tmp_path, monkeypatch):
    # 李四材料缺失场景：生成一份合法勾稽的草稿，校验应指出缺失
    monkeypatch.setattr("tax_filing.tools.filing_tools.WORKSPACE_DIR", tmp_path)
    generated = json.loads(
        generate_return_draft.invoke(
            {
                "taxpayer_id": "T2025-002",
                "year": 2025,
                "taxpayer_name": "李四",
                "income_amount": 584800,
                "total_deduction": 150000,
                "taxable_income": 434800,
                "tax_amount": 77520,
                "prepaid_tax": 86000,
                "payable_or_refund": -8480,
            }
        )
    )
    result = json.loads(validate_return_draft.invoke({"file_path": generated["file_path"], "taxpayer_id": "T2025-002"}))
    assert result["valid"] is False
    assert result["missing_evidence"] == ["继续教育（3600 元）"]


def test_submit_幂等(draft_file):
    first = json.loads(
        submit_return.invoke({"file_path": draft_file["file_path"], "idempotency_key": "T2025-001-2025"})
    )
    assert first["duplicate"] is False
    assert first["receipt_no"].startswith("RCP-")

    second = json.loads(
        submit_return.invoke({"file_path": draft_file["file_path"], "idempotency_key": "T2025-001-2025"})
    )
    assert second["duplicate"] is True
    assert second["receipt_no"] == first["receipt_no"]

    status = json.loads(query_submission_status.invoke({"receipt_no": first["receipt_no"]}))
    assert status["status"] == "已受理"

    missing = json.loads(query_submission_status.invoke({"receipt_no": "RCP-NOT-EXIST"}))
    assert "error" in missing
