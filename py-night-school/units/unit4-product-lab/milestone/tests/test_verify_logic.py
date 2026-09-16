"""verify.py 解析层、判定层与可注入执行层的离线测试（不碰兄弟课时——毕业态镜像里没有它们）。

不要改本文件。subprocess 路径（uv_runner）只在真实仓库由学员命令
`uv run python verify.py` 真跑——pytest 里通过给 run_lesson 注入 fake runner 喂
合成输出，验收 PASS/FAIL/超时分支，全程零子进程（目录缺失分支除外——它根本不起进程）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from verify import (
    LessonResult,
    LessonSpec,
    exit_code,
    format_table,
    parse_pytest_summary,
    run_lesson,
    verdict,
)


def _result(status: str, product: str = "ai-hedge-fund") -> LessonResult:
    return LessonResult("L4.1-ai-hedge-fund", product, "x", status, 19, 0, 1.5, "")


def _fake_runner(stdout: str, stderr: str = "", returncode: int = 0):
    """造一个可注入的假执行器：喂合成输出，记录它收到的 (cmd, cwd, env, timeout)。"""

    calls: list[tuple[list[str], Path, dict[str, str], float]] = []

    def _run(cmd: list[str], cwd: Path, env: dict[str, str], timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append((list(cmd), cwd, dict(env), timeout))
        return subprocess.CompletedProcess(args=list(cmd), returncode=returncode, stdout=stdout, stderr=stderr)

    return _run, calls


def _lesson_dir(tmp_path: Path) -> Path:
    """合成一个「课时目录存在」的 unit 目录（run_lesson 只查目录存在性，不进目录）。"""
    (tmp_path / "L4.1-ai-hedge-fund").mkdir()
    return tmp_path


# ---- parse_pytest_summary：只认末尾汇总行 ----


def test_parse_all_passed() -> None:
    assert parse_pytest_summary("...\n19 passed in 6.40s") == (19, 0)


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
    # 实测教训（VIRTUAL_ENV 告警）：汇总行后面还可能跟工具输出噪声
    assert parse_pytest_summary("19 passed in 6.40s\nwarning: VIRTUAL_ENV does not match") == (19, 0)


# ---- verdict / exit_code / format_table：判定与排版 ----


def test_verdict_needs_positive_pass() -> None:
    assert verdict(19, 0) == "PASS"
    assert verdict(19, 1) == "FAIL"
    assert verdict(0, 0) == "FAIL"  # 什么都没通过不算绿


def test_exit_code_three_states() -> None:
    assert exit_code([_result("PASS"), _result("PASS")]) == 0
    assert exit_code([_result("PASS"), _result("FAIL")]) == 1
    assert exit_code([_result("SKIPPED")]) == 2  # 全跳过：别让「没跑」伪装成「全绿」
    assert exit_code([]) == 2


def test_format_table_columns_and_skipped_dash() -> None:
    rows = [
        LessonResult(
            "L4.1-ai-hedge-fund", "ai-hedge-fund", "ai-hedge-fund fc1bf25（层级投票）", "PASS", 19, 0, 1.25, ""
        ),
        LessonResult(
            "L4.3-vibe-trading-governance",
            "vibe-trading",
            "Vibe-Trading f84b2977（治理合规）",
            "SKIPPED",
            0,
            0,
            0.0,
            "目录缺失",
        ),
    ]
    table = format_table(rows)
    assert "| 课时 | 产品（锚定 commit） | 结果 | 耗时 |" in table
    assert "| L4.1-ai-hedge-fund | ai-hedge-fund fc1bf25（层级投票） | PASS | 1.2s |" in table
    assert "| L4.3-vibe-trading-governance | Vibe-Trading f84b2977（治理合规） | SKIPPED | - |" in table  # 跳过不报耗时


# ---- 执行层：注入 fake runner 的离线验收（零子进程） ----


def test_run_lesson_missing_dir_degrades_to_skipped(tmp_path: Path) -> None:
    spec = LessonSpec("L9.9-no-such-lesson", "x", "x")
    runner, calls = _fake_runner("never called")
    result = run_lesson(tmp_path, spec, runner)
    assert result.status == "SKIPPED"
    assert "课时目录不存在" in result.detail
    assert calls == []  # 降级分支根本不起进程


def test_run_lesson_pass_branch_with_fake_runner(tmp_path: Path) -> None:
    spec = LessonSpec("L4.1-ai-hedge-fund", "ai-hedge-fund", "x")
    runner, calls = _fake_runner("19 passed in 6.40s")
    result = run_lesson(_lesson_dir(tmp_path), spec, runner)
    assert result.status == "PASS"
    assert result.passed == 19
    assert result.failed == 0
    assert result.detail == ""
    assert len(calls) == 1


def test_run_lesson_fail_branch_uses_stdout_only_and_cites_tail(tmp_path: Path) -> None:
    spec = LessonSpec("L4.1-ai-hedge-fund", "ai-hedge-fund", "x")
    # stderr 噪声在汇总行之后且不含计数——解析只认 stdout，混进来不许误判
    runner, _ = _fake_runner(
        "=== FAILURES ===\nboom\n1 failed, 1 passed in 2.05s",
        stderr="warning: VIRTUAL_ENV does not match",
        returncode=1,
    )
    result = run_lesson(_lesson_dir(tmp_path), spec, runner)
    assert result.status == "FAIL"
    assert (result.passed, result.failed) == (1, 1)
    assert "boom" in result.detail  # FAIL 时 detail 给输出尾部，供人读


def test_run_lesson_timeout_branch(tmp_path: Path) -> None:
    spec = LessonSpec("L4.1-ai-hedge-fund", "ai-hedge-fund", "x")

    def _timeout_runner(
        cmd: list[str], cwd: Path, env: dict[str, str], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=list(cmd), timeout=timeout)

    result = run_lesson(_lesson_dir(tmp_path), spec, _timeout_runner)
    assert result.status == "FAIL"
    assert "超时" in result.detail


def test_run_lesson_command_contract(tmp_path: Path) -> None:
    # 机制件层口径的契约：只跑讲义区 code/（不碰各课 exercises/），不叠 -q（各课
    # addopts 已带，-qq 吞汇总行），cwd=课时真实路径，子环境摘掉 VIRTUAL_ENV。
    spec = LessonSpec("L4.1-ai-hedge-fund", "ai-hedge-fund", "x")
    runner, calls = _fake_runner("19 passed in 6.40s")
    run_lesson(_lesson_dir(tmp_path), spec, runner)
    (cmd, cwd, env, timeout) = calls[0]
    assert cmd[1:] == ["run", "pytest", "code/"]  # cmd[0] 是 uv 的绝对路径（which 解析）
    assert "exercises" not in cmd
    assert cwd == tmp_path / "L4.1-ai-hedge-fund"
    assert "VIRTUAL_ENV" not in env
    assert timeout > 0
