"""notes/ 五页对照笔记的结构把关（meta-test，L0.1 ex2 先例：验收直接检查交付物本身）。

不要改本文件。判定规则：
- 五页齐（文件名与 summary.FRAMEWORKS 一一对应）；
- 每页五个固定小节（summary.NOTES_SECTIONS）齐；
- 含 ``TODO(笔记)`` 占位符的页：**完成态以 solution/notes 对应页为准**——参考答案
  是无占位符且小节齐的完成版即 PASS（学员完成 milestone 时把自己的结论誊写/对照
  solution 收口）；若 solution 页也缺小节或仍含占位符，才是结构红。
"""

from __future__ import annotations

from pathlib import Path

from summary import FRAMEWORKS, NOTES_SECTIONS, PLACEHOLDER, section_body

MILESTONE_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = MILESTONE_DIR / "notes"
SOLUTION_NOTES_DIR = MILESTONE_DIR / "solution" / "notes"


def _sections_complete(text: str) -> list[str]:
    """返回缺失的固定小节标题列表（小节存在且正文非空才算齐）。"""
    return [h for h in NOTES_SECTIONS if not section_body(text, h)]


def test_five_pages_present() -> None:
    for key in FRAMEWORKS:
        assert (NOTES_DIR / f"{key}.md").is_file(), f"缺笔记页: notes/{key}.md"


def test_template_sections_present() -> None:
    for key in FRAMEWORKS:
        text = (NOTES_DIR / f"{key}.md").read_text(encoding="utf-8")
        missing = _sections_complete(text)
        assert not missing, f"notes/{key}.md 缺小节: {missing}"


def test_placeholder_pages_have_completed_solution() -> None:
    """占位符页的完成态以 solution/notes 为准：答案页必须存在、小节齐、无占位符。

    学员完成里程碑 = 把五页的 ``TODO(笔记)`` 全部替换为自己的结论；本测试不判
    「你写得好不好」（那没有机器判据），只判结构上「有完成版可对照收口」。
    """
    for key in FRAMEWORKS:
        text = (NOTES_DIR / f"{key}.md").read_text(encoding="utf-8")
        if PLACEHOLDER not in text:
            continue  # 已完成誊写的页：结构测试直接管（上一条）
        solution_page = SOLUTION_NOTES_DIR / f"{key}.md"
        assert solution_page.is_file(), f"notes/{key}.md 含占位符，但 solution/notes/{key}.md 缺失"
        done = solution_page.read_text(encoding="utf-8")
        missing = _sections_complete(done)
        assert not missing, f"solution/notes/{key}.md 缺小节: {missing}"
        assert PLACEHOLDER not in done, f"solution/notes/{key}.md 仍含占位符（答案不是完成态）"
