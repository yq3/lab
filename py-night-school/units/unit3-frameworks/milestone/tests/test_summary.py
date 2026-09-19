"""summary.py 的测试：给定件（section_body 等）发货态就绿；aggregate 是本里程碑
唯一的设计内红——TODO(s1) 未填时 NotImplementedError（填完/solution 覆盖后全绿）。

不要改本文件。全部离线：bench/tablegen 的输入用合成对象，笔记用合成文本，
不碰兄弟课时。
"""

from __future__ import annotations

from bench import LessonResult
from summary import (
    MISSING_NOTE,
    PLACEHOLDER,
    DecisionRow,
    aggregate,
    first_meaningful_line,
    notes_status,
    render_final_table,
    section_body,
)
from tablegen import MetricRow


def _bench(framework: str, status: str) -> LessonResult:
    return LessonResult("L9.9-x", framework, "x", status, 2, 0, 1.0, "")


def _metric(framework: str, deps: int | None, loc: int | None) -> MetricRow:
    return MetricRow(framework, framework, deps, loc, (), "合成口径")


NOTE_DONE = (
    "# 笔记\n\n## 它替 mini-agent 付掉了什么\n- 三件套。\n\n## 它没替你付什么\n- 端点注入。\n\n"
    "## 最惊讶的一个机制\n- 机制 X（L3.x）。\n\n## 锁定性一句话\n- 一句压秤的话。\n\n## 什么时候选它\n- 场景 A。\n"
)

NOTE_TEMPLATE = (
    "# 笔记\n\n## 它替 mini-agent 付掉了什么\n- TODO(笔记)：清单。\n\n## 它没替你付什么\n- TODO(笔记)：清单。\n\n"
    "## 最惊讶的一个机制\n- TODO(笔记)：机制。\n\n## 锁定性一句话\n- TODO(笔记)：一句话。\n\n"
    "## 什么时候选它\n- TODO(笔记)：场景。\n"
)

# ---- 给定件：发货态就绿 ----


def test_section_body_extracts_between_headings() -> None:
    body = section_body(NOTE_DONE, "锁定性一句话")
    assert body == "- 一句压秤的话。"
    assert section_body(NOTE_DONE, "不存在的小节") == ""


def test_section_body_stops_at_next_h2() -> None:
    text = "## 锁定性一句话\n第一句。\n还有第二行。\n\n## 什么时候选它\n别的节。"
    assert section_body(text, "锁定性一句话") == "第一句。\n还有第二行。"


def test_first_meaningful_line_strips_list_prefix() -> None:
    assert first_meaningful_line("- 一句压秤的话。") == "一句压秤的话。"
    assert first_meaningful_line("\n\n  直接一句。") == "直接一句。"
    assert first_meaningful_line("") == ""


def test_first_meaningful_line_joins_wrapped_paragraph() -> None:
    # 笔记源文件的换行只是排版：一个段落合成一句，到空行为止
    body = "原语层几乎无锁定，但默认值\n路径是它的私有默认。\n\n第二段不取。"
    assert first_meaningful_line(body) == "原语层几乎无锁定，但默认值 路径是它的私有默认。"


def test_render_final_table_renders_all_columns() -> None:
    rows = [
        DecisionRow("fake 1.0", "PASS", "3", "5", "一句话。"),
        DecisionRow("缺数据行", "—", "缺", "缺", MISSING_NOTE),
    ]
    table = render_final_table(rows)
    assert "| 框架 | contract 重验 | 依赖数（lock 包） | 手写总行数（装配+节点+胶水） | 锁定性一句话 |" in table
    assert "| fake 1.0 | PASS | 3 | 5 | 一句话。 |" in table
    assert f"| 缺数据行 | — | 缺 | 缺 | {MISSING_NOTE} |" in table


def test_notes_status_classifies_three_states() -> None:
    statuses = dict(notes_status({"mini-agent": NOTE_DONE, "openai-agents": NOTE_TEMPLATE}))
    assert statuses["mini-agent"] == "五节齐"
    assert statuses["openai-agents"] == "占位符未替换"
    assert dict(notes_status({}))["deepagents"] == "缺页"


# ---- aggregate：本里程碑唯一 TODO（发货态设计内红） ----


def test_aggregate_joins_three_sources_in_framework_order() -> None:
    bench_rows = [_bench("openai-agents", "PASS")]
    metric_rows = [_metric("openai-agents", 51, 29), _metric("mini-agent", 44, 86)]
    notes = {"mini-agent": NOTE_DONE, "openai-agents": NOTE_DONE}
    rows = aggregate(bench_rows, metric_rows, notes)
    assert [r.framework for r in rows] == [
        "mini-agent（Unit 2 对照组）",
        "openai-agents 0.22.2",
        "langgraph 1.2.11（L3.2 手装 + L3.4 prebuilt）",
        "deepagents 0.7.13",
        "google-adk 2.9.0",
    ]
    assert rows[0].bench == "—"  # 对照组没有 contract 重验
    assert rows[0].deps == "44" and rows[0].handwritten == "86"
    assert rows[0].lock_line == "一句压秤的话。"
    assert rows[1].bench == "PASS" and rows[1].deps == "51"


def test_aggregate_langgraph_merges_two_assemblies() -> None:
    bench_rows = [_bench("langgraph", "PASS"), _bench("langgraph", "PASS")]
    rows = aggregate(bench_rows, [_metric("langgraph", 54, 63), _metric("langgraph", 54, 28)], {})
    lang = rows[2]
    assert lang.bench == "PASS"
    assert lang.handwritten == "63 / 28"  # 手装在前、prebuilt 在后，按出现顺序并列
    mixed = aggregate([_bench("langgraph", "FAIL"), _bench("langgraph", "PASS")], [], {})
    assert mixed[2].bench == "FAIL"  # 两种装配任一 FAIL，框架行即 FAIL


def test_aggregate_placeholder_and_missing_note_degrade() -> None:
    rows = aggregate([], [], {"openai-agents": NOTE_TEMPLATE})  # 占位符未替换
    assert rows[1].lock_line == MISSING_NOTE
    assert PLACEHOLDER not in rows[1].lock_line
    empty = aggregate([], [], {})  # 整页缺失
    assert empty[1].lock_line == MISSING_NOTE and empty[1].deps == "缺"
