"""tablegen.py 解析层的离线测试：tmp_path 合成夹具（假 uv.lock / 假 demo.py）。

不要改本文件。不碰真实兄弟课时——这里造的是「合成课时」：依赖数用 tomllib 数
自己写的 lock 文本，行数用 ast 数自己写的函数，期望值手算写死。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tablegen import LessonSpec, MetricRow, collect_row, count_lock_packages, count_target_loc, render_markdown

FAKE_LOCK = """\
version = 1
requires-python = ">=3.12"

[[package]]
name = "pydantic"
version = "2.0"

[[package]]
name = "pytest"
version = "9.0"

[[package]]
name = "typing-extensions"
version = "4.0"
"""

# 手算口径：docstring 行、空行、# 注释行不计；嵌套函数体计入、其 docstring 不计
FAKE_DEMO = '''\
"""模块 docstring——不计。"""
import os


def build_agent(name):
    """函数 docstring——不计。

    跨两行也不计。
    """
    # 注释行不计
    agent = {"name": name}          # 行内注释不影响：整行非空非注释行，计 1
    tools = [os.fspath(name)]

    def inner():
        """嵌套 docstring 不计。"""
        return tools

    return agent, inner()


async def run_review(claim_id: str) -> str:
    """docstring 不计。"""
    return claim_id
'''


def test_count_lock_packages_reads_toml(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    lock.write_text(FAKE_LOCK, encoding="utf-8")
    assert count_lock_packages(lock) == 3  # tomllib 口径：[[package]] 条目数


def test_count_target_loc_ast_discipline(tmp_path: Path) -> None:
    demo = tmp_path / "demo.py"
    demo.write_text(FAKE_DEMO, encoding="utf-8")
    assert count_target_loc(demo.read_text(encoding="utf-8"), "build_agent") == 6
    # def 行计入（与 L3.4 count_loc 同口径）：def / agent= / tools= / def inner: /
    # return tools / return agent, inner()
    assert count_target_loc(demo.read_text(encoding="utf-8"), "run_review") == 2  # def 行 + return 行


def test_count_target_loc_missing_target_raises(tmp_path: Path) -> None:
    demo = tmp_path / "demo.py"
    demo.write_text(FAKE_DEMO, encoding="utf-8")
    try:
        count_target_loc(demo.read_text(encoding="utf-8"), "no_such_func")
    except KeyError as exc:
        assert "no_such_func" in str(exc)
    else:  # 拿错目标必须响（对照 L3.4 count_loc 的 exit 1 纪律）
        raise AssertionError("expected KeyError")


def _write_fake_lesson(units: Path, lesson_rel: str, *, with_lock: bool = True, with_demo: bool = True) -> None:
    lesson = units / lesson_rel
    lesson.mkdir(parents=True)
    if with_lock:
        (lesson / "uv.lock").write_text(FAKE_LOCK, encoding="utf-8")
    if with_demo:
        (lesson / "code").mkdir()
        (lesson / "code" / "demo.py").write_text(FAKE_DEMO, encoding="utf-8")


def test_collect_row_full_lesson() -> None:
    spec = LessonSpec(
        "unit3-frameworks/L9.9-fake",
        "fake",
        "fake 1.0",
        ("code/demo.py::build_agent", "code/demo.py::run_review"),
        "合成课时口径",
    )
    with tempfile.TemporaryDirectory() as tmp:
        units = Path(tmp)
        _write_fake_lesson(units, spec.lesson)
        row = collect_row(spec, units)
    assert isinstance(row, MetricRow)
    assert row.deps == 3
    assert row.handwritten_loc == 8  # build_agent 6 + run_review 2
    assert row.detail == "合成课时口径"


def test_collect_row_missing_lesson_degrades(tmp_path: Path) -> None:
    spec = LessonSpec("unit3-frameworks/L9.9-absent", "fake", "fake 1.0", ("code/demo.py::build_agent",), "口径")
    row = collect_row(spec, tmp_path)
    assert row.deps is None
    assert row.handwritten_loc is None
    assert "数据缺失" in row.detail


def test_collect_row_prefers_solution_for_control_row(tmp_path: Path) -> None:
    """对照行（mini-agent）取 solution 口径：solution 里有目标文件时优先于学员件。"""
    spec = LessonSpec("unit2-fake/milestone", "mini-agent", "mini-agent", ("agent.py::run",), "对照")
    _write_fake_lesson(tmp_path, "unit2-fake/milestone")  # 根下有 code/demo.py 无关紧要
    (tmp_path / "unit2-fake" / "milestone" / "agent.py").write_text(
        'def run():\n    """学员件 docstring。"""\n    return 99\n', encoding="utf-8"
    )
    solution = tmp_path / "unit2-fake" / "milestone" / "solution"
    solution.mkdir()
    (solution / "agent.py").write_text(
        'def run():\n    """答案 docstring。"""\n    a = 1\n    b = 2\n    return a + b\n', encoding="utf-8"
    )
    row = collect_row(spec, tmp_path)
    assert row.handwritten_loc == 4  # solution 版：def / a=1 / b=2 / return 共 4 行（docstring 剔除）


def test_render_markdown_lists_metrics_and_targets() -> None:
    rows = [
        MetricRow("openai-agents", "openai-agents 0.22.2", 51, 29, ("code/demo.py::run_review",), "原语层"),
        MetricRow("fake", "fake 1.0", None, None, (), "缺数据"),
    ]
    page = render_markdown(rows)
    # 列名与 L3.8 决策表的「装配 loc」刻意不同名（防口径撞名：本列=装配+节点+胶水全量）
    assert "| 框架与装配 | 依赖数（uv.lock 包） | 手写总行数（装配+节点+胶水，ast 口径） |" in page
    assert "L3.8 决策表数据页" in page  # 数据页自带与 L3.8 拆列的恒等式说明
    assert "| openai-agents 0.22.2 | 51 | 29 |" in page
    assert "| fake 1.0 | 缺 | 缺 |" in page
    assert "`code/demo.py::run_review`" in page  # 口径明细可复现
