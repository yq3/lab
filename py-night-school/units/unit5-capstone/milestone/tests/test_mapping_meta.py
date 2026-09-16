r"""毕业测试②：JAVA-MAPPING.md 定稿的结构把关（meta-test，L0.1 ex2 先例：验收直接检查交付物本身）。

不要改本文件。判定规则（毕业判据的第二块）：
- 主表 ≥ 13 行、每行四列且全部非空（模式 / Python 侧 / Java 对应物 / 翻译坑）；
- 「需自建」两行保留（图版本绑定 / 当日账本）——诚实纪律：克隆里没有的对应物老实写
  「需自建」，不许为了「填满」编造 API 名；
- TODO(毕业) 未填行（发货/模板态）：以 solution/JAVA-MAPPING.md 完成版为准——有完成版
  可对照收口即过（先例 Unit 3 milestone 笔记）；学员填完后（根文档零占位）按无残留口径
  直接验收——占位清零是毕业判据，不是装饰。
"""

from __future__ import annotations

import re
from pathlib import Path

MILESTONE_DIR = Path(__file__).resolve().parents[1]
DOC = MILESTONE_DIR / "JAVA-MAPPING.md"
SOLUTION_DOC = MILESTONE_DIR / "solution" / "JAVA-MAPPING.md"
TODO_MARK = "TODO(毕业)"  # 学员未填标记（JAVA-MAPPING.md 表头约定：只允许出现在 Java 对应物列）


def _cells(line: str) -> list[str]:
    r"""一行 markdown 表格 → 单元格列表（未转义 \| 是列界，\| 是单元格内字面管道；已 strip）。"""
    parts = re.split(r"(?<!\\)\|", line.strip())
    cells = [cell.strip().replace("\\|", "|") for cell in parts]
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return cells


def _is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:|-]+\|?", line.strip())) and "-" in line


def _tables(text: str) -> dict[str, list[list[str]]]:
    """markdown → {节名: 数据行}——按 #/## 标题分节，跳过表头行与 |---| 分隔行（L5.4 ex3 同款）。"""
    tables: dict[str, list[list[str]]] = {}
    section = ""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            section = line.lstrip("#").strip()
        elif line.strip().startswith("|"):
            rows: list[list[str]] = []
            i += 1
            if i < len(lines) and _is_separator(lines[i]):
                i += 1
                while i < len(lines) and lines[i].strip().startswith("|"):
                    rows.append(_cells(lines[i]))
                    i += 1
            if rows:
                tables.setdefault(section, []).extend(rows)
            continue
        i += 1
    return tables


def _main_rows(text: str) -> list[list[str]]:
    """主表数据行：节名以 JAVA-MAPPING 开头的那张表（H1 下的四列主表）。"""
    hits = [rows for name, rows in _tables(text).items() if name.startswith("JAVA-MAPPING")]
    assert len(hits) == 1, f"应恰有一张主表，实得 {len(hits)} 张"
    return hits[0]


def _unfilled(rows: list[list[str]]) -> list[int]:
    """Java 对应物列（第 3 列）含 TODO_MARK 的行号（1 起计数）——未填清单。"""
    return [lineno for lineno, row in enumerate(rows, start=1) if len(row) >= 3 and TODO_MARK in row[2]]


def test_main_table_thirteen_rows_four_columns_non_empty() -> None:
    """主表 ≥ 13 行（13 个模式是结业口径）、每行恰四列且全部非空——缺列/空格都是结构破损。"""
    rows = _main_rows(DOC.read_text(encoding="utf-8"))
    assert len(rows) >= 13
    for lineno, row in enumerate(rows, start=1):
        assert len(row) == 4, f"主表第 {lineno} 行不是四列: {len(row)}"
        assert all(cell.strip() for cell in row), f"主表第 {lineno} 行有空单元格"


def test_self_build_rows_preserved() -> None:
    """「需自建」两行保留：图版本绑定 / 当日账本——Java 侧没有现成对应物是核实出来的
    结论，这两行的诚实标注不许在补全时被想象出来的 API 顶掉。"""
    rows = _main_rows(DOC.read_text(encoding="utf-8"))
    by_pattern = {row[0].split("（")[0]: row for row in rows}
    for pattern in ("图版本绑定", "当日账本"):
        assert pattern in by_pattern, f"主表缺「{pattern}」行"
        assert "需自建" in by_pattern[pattern][2], f"「{pattern}」行的 Java 对应物丢了「需自建」标注"
    assert sum(1 for row in rows if "需自建" in row[2]) == 2  # 恰两行——多一行少一行都是口径漂移


def test_todo_rows_have_completed_solution_counterpart() -> None:
    """占位行两态验收（Unit 3 milestone 笔记先例）：
    根文档还有 TODO(毕业) 占位 → solution/JAVA-MAPPING.md 必须是无占位的完成版
    （对照收口的范本）；根文档零占位（学员已填）→ 直接按无残留口径通过。"""
    text = DOC.read_text(encoding="utf-8")
    unfilled = _unfilled(_main_rows(text))
    if not unfilled:
        assert TODO_MARK not in text  # 学员已填完：全文无残留（含表头）
        return
    assert SOLUTION_DOC.is_file(), "JAVA-MAPPING.md 还有占位行，但 solution/JAVA-MAPPING.md 缺失"
    solution_text = SOLUTION_DOC.read_text(encoding="utf-8")
    solution_rows = _main_rows(solution_text)
    assert TODO_MARK not in solution_text, "solution/JAVA-MAPPING.md 不是完成态（仍含占位标记）"
    assert len(solution_rows) == len(_main_rows(text)), "对照版与学员版主表行数不一致"
    assert not _unfilled(solution_rows)
    for pattern in ("图版本绑定", "当日账本"):  # 完成版同样守住诚实纪律
        assert any(pattern in row[0] and "需自建" in row[2] for row in solution_rows)


def test_unfilled_rows_match_todo_marks_in_text() -> None:
    """互证（L5.4 ex3 活检先例）：Java 列的占位行数 == 全文 TODO(毕业) 标记数——
    你每补全一行，两边同步减一；全填完两边归零。标记跑到别的列/表头，这里当场红。"""
    text = DOC.read_text(encoding="utf-8")
    unfilled = _unfilled(_main_rows(text))
    assert len(unfilled) == text.count(TODO_MARK)
