"""bench.py 解析层与降级分支的离线测试（不碰兄弟课时——毕业态镜像里没有它们）。

不要改本文件。执行层（run_lesson 的 subprocess 路径）只在真实仓库由学员命令
`uv run python bench.py` 真跑——pytest 里只测它「目录缺失→SKIPPED」的分支
（该分支不起任何子进程）。
"""

from __future__ import annotations

from pathlib import Path

from bench import (
    LessonResult,
    LessonSpec,
    exit_code,
    format_table,
    parse_pytest_summary,
    run_lesson,
    verdict,
)


def _result(status: str, framework: str = "openai-agents") -> LessonResult:
    return LessonResult("L3.1-openai-agents", framework, "x", status, 2, 0, 1.5, "")


# ---- parse_pytest_summary：只认末尾汇总行 ----


def test_parse_all_passed() -> None:
    assert parse_pytest_summary("...\n2 passed in 1.73s") == (2, 0)


def test_parse_failed_and_passed() -> None:
    assert parse_pytest_summary("=== FAILURES ===\n1 failed, 1 passed in 2.05s") == (1, 1)


def test_parse_errors_count_as_failed() -> None:
    # 课时环境坏掉时的形态：error 也算不绿
    assert parse_pytest_summary("1 error in 0.5s") == (0, 1)


def test_parse_skipped_and_passed() -> None:
    assert parse_pytest_summary("3 passed, 1 skipped in 0.8s") == (3, 0)  # skip 不算失败


def test_parse_no_summary_fail_closed() -> None:
    # 找不到汇总数字（如 uv 报错、超时截断）：fail-closed，按失败计
    assert parse_pytest_summary("uv: command not found") == (0, 1)
    assert parse_pytest_summary("") == (0, 1)


def test_parse_ignores_trailing_tool_noise() -> None:
    # 实测教训（bench 的 VIRTUAL_ENV 告警）：汇总行后面还可能跟工具输出噪声
    assert parse_pytest_summary("2 passed in 1.73s\nwarning: VIRTUAL_ENV does not match") == (2, 0)


# ---- verdict / exit_code / format_table：判定与排版 ----


def test_verdict_needs_positive_pass() -> None:
    assert verdict(2, 0) == "PASS"
    assert verdict(2, 1) == "FAIL"
    assert verdict(0, 0) == "FAIL"  # 什么都没通过不算绿


def test_exit_code_three_states() -> None:
    assert exit_code([_result("PASS"), _result("PASS")]) == 0
    assert exit_code([_result("PASS"), _result("FAIL")]) == 1
    assert exit_code([_result("SKIPPED")]) == 2  # 全跳过：别让「没跑」伪装成「全绿」
    assert exit_code([]) == 2


def test_format_table_columns_and_skipped_dash() -> None:
    rows = [
        LessonResult("L3.1-openai-agents", "openai-agents", "openai-agents 0.22.2", "PASS", 2, 0, 1.25, ""),
        LessonResult("L3.5-deepagents", "deepagents", "deepagents 0.7.13", "SKIPPED", 0, 0, 0.0, "目录缺失"),
    ]
    table = format_table(rows)
    assert "| 课时 | 框架与装配 | 结果 | 耗时 |" in table
    assert "| L3.1-openai-agents | openai-agents 0.22.2 | PASS | 1.2s |" in table
    assert "| L3.5-deepagents | deepagents 0.7.13 | SKIPPED | - |" in table  # 跳过不报耗时


# ---- 执行层唯一可离线测的分支：目录缺失优雅降级（不起子进程） ----


def test_run_lesson_missing_dir_degrades_to_skipped(tmp_path: Path) -> None:
    spec = LessonSpec("L9.9-no-such-lesson", "x", "x")
    result = run_lesson(tmp_path, spec)
    assert result.status == "SKIPPED"
    assert "课时目录不存在" in result.detail
