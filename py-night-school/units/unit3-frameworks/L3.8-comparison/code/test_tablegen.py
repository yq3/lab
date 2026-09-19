"""tablegen 的单元验收（不要改本文件）：只测解析/统计逻辑，用 tmp_path 造合成课时夹具。

设计约定（讲义 §3 Step1 与宪法纪律）：三态验证的毕业态镜像里没有兄弟课时目录，
所以这里**不真读兄弟课时**——真读兄弟课时的完整运行是讲义演示（本机发货态跑通）。
夹具全部合成：uv.lock 用 tomllib 可解析的最小 TOML，demo.py 用最小函数体。
"""

from __future__ import annotations

import re

import pytest

import tablegen as tg

CITATION = re.compile(r"(L3\.[1-7]|milestone|Unit 2|mini-agent)")

# ---- 合成素材（最小可解析形态） ----

SYNTHETIC_LOCK = """\
version = 1

[[package]]
name = "anyio"
version = "4.6.0"

[[package]]
name = "httpx"
version = "0.28.0"

[[package]]
name = "l38-comparison"
version = "0.1.0"
"""

SYNTHETIC_DEMO = '''\
"""Synthetic demo for tablegen tests."""


def _build_tools():
    """工具装配。

    多行 docstring——两行都不该计入 loc。
    """
    # 注释行也不计
    return [1, 2]


def _build_model():
    return "model"


def _build_agent():
    return ("agent", _build_tools(), _build_model())
'''

SYNTHETIC_AGENT = '''\
"""Synthetic mini-agent."""


class ReActAgent:
    def run(self):
        """循环本体（docstring 不计）。"""
        # TODO(t1)
        raise NotImplementedError("TODO(t1)")
'''


def make_lesson(root, lesson_rel: str) -> None:
    """在 root 下造一个合成课时：uv.lock + code/demo.py（合成内容与 COST_ROWS 的 L3.1 目标对齐）。"""
    lesson = root / lesson_rel
    demo = lesson / "code" / "demo.py"
    demo.parent.mkdir(parents=True, exist_ok=True)
    (lesson / "uv.lock").write_text(SYNTHETIC_LOCK, encoding="utf-8")
    demo.write_text(SYNTHETIC_DEMO, encoding="utf-8")


# ---- 依赖数：tomllib 口径 ----


def test_count_packages_counts_toml_array_of_tables(tmp_path):
    lock = tmp_path / "uv.lock"
    lock.write_text(SYNTHETIC_LOCK, encoding="utf-8")
    assert tg.count_packages(lock) == 3  # [[package]] 条目数（含本项目自身）


def test_count_packages_missing_lock_raises(tmp_path):
    with pytest.raises(LookupError):
        tg.count_packages(tmp_path / "nope.lock")


# ---- ast 行数口径 ----


def test_def_loc_excludes_docstring_blank_comment(tmp_path):
    demo = tmp_path / "demo.py"
    demo.write_text(SYNTHETIC_DEMO, encoding="utf-8")
    assert tg.def_loc(demo, "_build_tools") == 2  # def 行 + return 行；docstring/注释/空行不计
    assert tg.def_loc(demo, "_build_agent") == 2


def test_def_loc_nested_docstrings_all_excluded(tmp_path):
    demo = tmp_path / "demo.py"
    demo.write_text(
        'def outer():\n    """outer"""\n    def inner():\n        """inner"""\n        return 1\n    return inner\n',
        encoding="utf-8",
    )
    assert tg.def_loc(demo, "outer") == 4  # def outer + def inner + 两个 return——两级 docstring 都剔除


def test_def_loc_nested_qualname_and_missing_target(tmp_path):
    agent = tmp_path / "agent.py"
    agent.write_text(SYNTHETIC_AGENT, encoding="utf-8")
    assert tg.def_loc(agent, "ReActAgent.run") == 2  # def 行 + raise 行（TODO 桩也如实数）
    with pytest.raises(LookupError):
        tg.def_loc(agent, "ReActAgent.no_such")


def test_targets_loc_missing_lesson_dir_returns_none(tmp_path):
    assert tg.targets_loc(tmp_path / "no-such-lesson", (("code/demo.py", "build_graph"),)) is None


def test_targets_loc_sums_multiple_targets(tmp_path):
    demo = tmp_path / "demo.py"
    demo.write_text(SYNTHETIC_DEMO, encoding="utf-8")
    targets = (("demo.py", "_build_tools"), ("demo.py", "_build_model"), ("demo.py", "_build_agent"))
    assert tg.targets_loc(tmp_path, targets) == 6


# ---- 渲染：合成课时全量行 + 缺失降级 ----


def test_render_cost_table_synthetic_lesson_computes_cells(tmp_path):
    make_lesson(tmp_path, "units/unit3-frameworks/L3.1-openai-agents")
    page, missing = tg.render_cost_table(tmp_path)
    row = next(line for line in page.splitlines() if line.startswith("| openai-agents"))
    assert "| 3 | 6 | 0 | 2 |" in row  # 依赖 3 + 装配 6（ast 实测）+ 节点 0 + 轮数 2（静态）
    assert "openai-agents（L3.1）" not in missing  # 造齐的行不算缺失
    assert "mini-agent（milestone）" in missing  # 其余行缺失也被点名（本测试只造了 L3.1）


def test_render_cost_table_all_missing(tmp_path):
    page, missing = tg.render_cost_table(tmp_path)
    assert len(missing) == len(tg.COST_ROWS)
    assert page.count("missing") >= len(tg.COST_ROWS)  # 每行依赖格都降级，而不是崩溃
    assert "模型轮数" in page  # 静态列不受兄弟课时缺失影响，照常输出


def test_render_data_page_contains_three_tables(tmp_path):
    page = tg.render_data_page(tmp_path)
    assert "成本表" in page and "能力表" in page and "锁定性表" in page
    assert page.count("\n| ") >= 3  # 成本表的表头/分隔/表体（markdown 表）
    for framework in tg.CAPABILITY:  # 能力/锁定性表逐框架块状输出：框架名 + 每格一行
        assert f"\n[{framework}]" in page


# ---- 静态事实表完整性：每格必须有出处课次 ----


@pytest.mark.parametrize("table,facets", [(tg.CAPABILITY, tg.CAPABILITY_FACETS), (tg.LOCKIN, tg.LOCKIN_FACETS)])
def test_static_tables_cite_lessons_everywhere(table, facets):
    for framework, cells in table.items():
        assert set(cells) == set(facets), framework  # 维度齐全，无缺列
        for facet, fact in cells.items():
            assert fact.strip(), (framework, facet)  # 无空格
            assert CITATION.search(fact), (framework, facet, fact)  # 无出处的事实不准进表


def test_static_tables_cover_six_frameworks_including_platform():
    keys = set(tg.CAPABILITY)
    assert keys == set(tg.LOCKIN)
    assert {"mini-agent", "openai-agents", "langgraph", "deepagents", "adk"} <= keys
    assert any("dify" in k for k in keys)  # 平台形态一行（能力/锁定性有它，成本定量没有——平台不进依赖清单）


def test_cost_rows_cover_six_assembly_representatives():
    rels = {row.lesson_rel for row in tg.COST_ROWS}
    assert len(rels) == 6
    assert "units/unit2-mini-agent/milestone" in rels
    assert sum(1 for r in tg.COST_ROWS if "L3.2" in r.lesson_rel or "langgraph-basics" in r.lesson_rel) == 1
    assert all(row.turns_source.strip() for row in tg.COST_ROWS)  # 轮数静态数字全部带出处


# ---- 仓库根定位 ----


def test_find_repo_root_by_markers(tmp_path):
    (tmp_path / "units").mkdir()
    (tmp_path / "CURRICULUM.md").write_text("# curriculum\n", encoding="utf-8")
    nested = tmp_path / "units" / "unit3-frameworks" / "L3.8-comparison"
    nested.mkdir(parents=True)
    assert tg.find_repo_root(nested) == tmp_path


def test_find_repo_root_raises_without_markers(tmp_path):
    with pytest.raises(LookupError):
        tg.find_repo_root(tmp_path)
