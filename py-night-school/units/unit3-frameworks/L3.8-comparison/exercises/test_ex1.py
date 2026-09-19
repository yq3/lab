"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import ex1_contract_column as ex1

BASE = '''"""四框架同题 demo 的共用验收脚本（合成版）。"""


def test_contract() -> None:
    assert True
'''

DRIFTED = BASE + "\n\ndef test_extra() -> None:\n    assert True\n"  # 多了一个测试——字节不再一致


def digest(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


def make_lesson(root: Path, name: str, content: str | None) -> Path:
    """造一个合成课时：content 为 None 表示没有契约文件。"""
    lesson = root / name
    code = lesson / "code"
    code.mkdir(parents=True, exist_ok=True)
    if content is not None:
        (code / "test_contract.py").write_text(content, encoding="utf-8")
    return lesson


def test_five_identical_contracts_all_in_place(tmp_path: Path) -> None:
    dirs = {n: make_lesson(tmp_path, n, BASE) for n in ("L3.1", "L3.2", "L3.4", "L3.5", "L3.6")}
    column = ex1.contract_column(dirs)
    expected = f"in-place({digest(BASE)})"
    assert column == {n: expected for n in dirs}  # 五课对版：全部 in-place 且指纹正确


def test_one_drifted_contract_is_called_out(tmp_path: Path) -> None:
    dirs = {
        "L3.1": make_lesson(tmp_path, "L3.1", BASE),
        "L3.2": make_lesson(tmp_path, "L3.2", BASE),
        "L3.4": make_lesson(tmp_path, "L3.4", BASE),
        "L3.5": make_lesson(tmp_path, "L3.5", BASE),
        "L3.6": make_lesson(tmp_path, "L3.6", DRIFTED),  # 这一课悄悄改版了
    }
    column = ex1.contract_column(dirs)
    assert column["L3.6"] == f"drift({digest(DRIFTED)})"  # 少数派被点名
    in_place = f"in-place({digest(BASE)})"
    assert {k: v for k, v in column.items() if k != "L3.6"} == {n: in_place for n in ("L3.1", "L3.2", "L3.4", "L3.5")}


def test_missing_contract_column_reports_missing(tmp_path: Path) -> None:
    dirs = {
        "L3.1": make_lesson(tmp_path, "L3.1", BASE),
        "L3.2": make_lesson(tmp_path, "L3.2", BASE),
        "L3.4": make_lesson(tmp_path, "L3.4", BASE),
        "L3.5": make_lesson(tmp_path, "L3.5", None),  # 只有本课时 checkout 的场景：文件不存在
    }
    column = ex1.contract_column(dirs)
    assert column["L3.5"] == "missing"
    assert column["L3.1"] == f"in-place({digest(BASE)})"


def test_tie_break_is_deterministic(tmp_path: Path) -> None:
    # 2:2 并列（各两课同指纹）：基准取字典序最小的指纹——同一组输入永远同一列
    other = BASE.replace("assert True", "assert 1 + 1 == 2")
    dirs = {
        "L3.1": make_lesson(tmp_path, "L3.1", BASE),
        "L3.2": make_lesson(tmp_path, "L3.2", BASE),
        "L3.4": make_lesson(tmp_path, "L3.4", other),
        "L3.5": make_lesson(tmp_path, "L3.5", other),
    }
    baseline = min(digest(BASE), digest(other))  # 字典序最小的指纹当基准
    drifted = max(digest(BASE), digest(other))
    column = ex1.contract_column(dirs)
    assert sorted(column.values()) == sorted(
        [f"in-place({baseline})", f"in-place({baseline})", f"drift({drifted})", f"drift({drifted})"]
    )
