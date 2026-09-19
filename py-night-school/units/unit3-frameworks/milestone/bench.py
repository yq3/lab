"""选型工作台第一件：跨课重验——子进程逐课重跑四框架同题 demo 的共用验收脚本。

对 L3.1 / L3.2 / L3.4 / L3.5 / L3.6 五个课时（langgraph 由 L3.2 手装图与 L3.4 prebuilt
两种装配代表）各跑一次 `uv run pytest code/test_contract.py`（cwd=各课时目录；
各课 pyproject 的 addopts 已带 -q——不要再叠加，-qq 会把汇总行也吞掉），
汇总成一张表：课时 / 框架与装配 / 结果 / 耗时，并以退出码收口（全 PASS=0）。

用法（学员命令，跨平台）：
    uv run python bench.py

新知识点（subprocess 的安全用法，给 Java 同学）：
- `subprocess.run(["uv", "run", "pytest", ...], cwd=...)` ≈ Java 的
  `new ProcessBuilder("uv", "run", "pytest", ...).directory(dir).start()`——
  参数以**列表**逐个传递，不经 shell 解析（对照 `Runtime.exec(String)` 按空格切词
  出过的事故：路径带空格就碎）。没有 shell=True，就没有 shell 注入。
- capture_output=True + text=True ≈ 读子进程 stdout/stderr 并按文本解码；
- 子进程默认继承父进程环境变量（PATH 里的 uv 因此可见——脚本开头仍自查并给友好报错）。

分层纪律（为什么测试不真的去跑兄弟课时）：
- 解析层（parse_pytest_summary / verdict / format_table / exit_code）是**纯函数**，
  tests/test_bench_logic.py 只测它们 + 「课时目录缺失→SKIPPED」的降级分支；
- 执行层（run_lesson）是薄壳：一次 subprocess 调用 + 计时，不在 pytest 里跑——
  毕业态镜像里没有兄弟课时目录，测试碰它们必红。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

UNIT3_DIR = Path(__file__).resolve().parents[1]  # units/unit3-frameworks

PER_LESSON_TIMEOUT = 300.0  # 单课超时（秒）：首次 uv sync 重依赖也够用


@dataclass(frozen=True)
class LessonSpec:
    """一个待重验的课时：目录名 + 框架 key（summary 聚合用）+ 展示名（含装配方式）。"""

    lesson: str
    framework: str
    label: str


# 五课时：L3.2 与 L3.4 同属 langgraph（framework key 相同），装配方式不同——
# summary.py 聚合时合并为同一框架行（两种装配都 PASS 才算 langgraph PASS）。
LESSONS: tuple[LessonSpec, ...] = (
    LessonSpec("L3.1-openai-agents", "openai-agents", "openai-agents 0.22.2"),
    LessonSpec("L3.2-langgraph-basics", "langgraph", "langgraph 1.2.11（手装图）"),
    LessonSpec("L3.4-langgraph-fanout", "langgraph", "langgraph 1.2.11（prebuilt）"),
    LessonSpec("L3.5-deepagents", "deepagents", "deepagents 0.7.13"),
    LessonSpec("L3.6-adk-python", "adk-python", "google-adk 2.9.0"),
)


@dataclass(frozen=True)
class LessonResult:
    """一次重验的结果（SKIPPED 时 passed/failed 为 0、seconds 为 0.0）。"""

    lesson: str
    framework: str
    label: str
    status: str  # "PASS" / "FAIL" / "SKIPPED"
    passed: int
    failed: int  # pytest 口径的 failed+error 合计
    seconds: float  # 墙钟耗时（含 uv 启动）
    detail: str  # FAIL/SKIPPED 时的人类可读说明（输出尾部或原因）


# ---- 解析层（纯函数，tests 只测这里） ----


def parse_pytest_summary(pytest_stdout: str) -> tuple[int, int]:
    """从 pytest -q 的 stdout 里解析 (passed, failed+error)。

    只认 ``N passed`` / ``N failed`` / ``N error(s)`` 计数（如末尾汇总行
    ``2 passed in 1.23s`` / ``1 failed, 1 passed in 2s``）；找不到任何计数时返回
    (0, 1)——「没跑出结论」按失败处理（fail-closed）。注意只喂 stdout：
    stderr 里的工具告警（如 uv 的 VIRTUAL_ENV 提示）出现在汇总行之后，混进来会干扰。
    """
    passed = failed = 0
    seen = False
    for line in pytest_stdout.splitlines():
        for count, word in re.findall(r"(\d+) (passed|failed|error|errors)", line):
            seen = True
            if word == "passed":
                passed += int(count)
            else:
                failed += int(count)
    return (passed, failed) if seen else (0, 1)


def verdict(passed: int, failed: int) -> str:
    """判定单课结果：有失败=FAIL；无失败且确有测试通过=PASS；什么都没通过=FAIL。"""
    if failed == 0 and passed > 0:
        return "PASS"
    return "FAIL"


def format_table(results: list[LessonResult]) -> str:
    """汇总表（课时/框架与装配/结果/耗时）——纯排版，不做判定。"""
    lines = ["| 课时 | 框架与装配 | 结果 | 耗时 |", "|---|---|---|---|"]
    for r in results:
        seconds = f"{r.seconds:.1f}s" if r.status != "SKIPPED" else "-"
        lines.append(f"| {r.lesson} | {r.label} | {r.status} | {seconds} |")
    return "\n".join(lines)


def exit_code(results: list[LessonResult]) -> int:
    """全 PASS=0；任一 FAIL=1；一条都没跑成（全 SKIPPED）=2——别让「没跑」伪装成「全绿」。"""
    if all(r.status == "SKIPPED" for r in results):
        return 2
    return 0 if all(r.status == "PASS" for r in results) else 1


# ---- 执行层（薄壳：subprocess + 计时；pytest 不碰它） ----


def _output_tail(text: str, lines: int = 6) -> str:
    return "\n".join(text.strip().splitlines()[-lines:]) if text.strip() else "(无输出)"


def run_lesson(unit3_dir: Path, spec: LessonSpec) -> LessonResult:
    """对一个课时目录跑一次共用验收；目录缺失优雅降级为 SKIPPED（不 subprocess）。"""
    lesson_dir = unit3_dir / spec.lesson
    if not lesson_dir.is_dir():
        return LessonResult(
            spec.lesson,
            spec.framework,
            spec.label,
            "SKIPPED",
            0,
            0,
            0.0,
            f"课时目录不存在: {lesson_dir}",
        )
    uv = shutil.which("uv")
    if uv is None:  # 理论上 main 已自查；保留防御分支，供 collect_results 被直接调用时兜底
        return LessonResult(
            spec.lesson,
            spec.framework,
            spec.label,
            "SKIPPED",
            0,
            0,
            0.0,
            "PATH 里找不到 uv",
        )
    started = time.perf_counter()
    # 子进程环境继承父进程（≈ ProcessBuilder 默认继承），但要摘掉 VIRTUAL_ENV：
    # 本脚本常由 `uv run` 启动，它把父项目 .venv 写进 VIRTUAL_ENV；兄弟课时的
    # 子 `uv run` 看到不匹配的 VIRTUAL_ENV 会告警（实测教训：告警走 stderr 且
    # 出现在 pytest 汇总行之后，把它并进解析会误判失败）。
    child_env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    try:
        completed = subprocess.run(
            [uv, "run", "pytest", "code/test_contract.py"],  # 不再叠加 -q：各课 addopts 已有 -q，-qq 会吞掉汇总行
            cwd=lesson_dir,
            capture_output=True,
            text=True,
            timeout=PER_LESSON_TIMEOUT,
            env=child_env,
        )
        output = completed.stdout + completed.stderr
    except subprocess.TimeoutExpired:
        return LessonResult(
            spec.lesson,
            spec.framework,
            spec.label,
            "FAIL",
            0,
            1,
            time.perf_counter() - started,
            f"超时（>{PER_LESSON_TIMEOUT:.0f}s）",
        )
    seconds = time.perf_counter() - started
    passed, failed = parse_pytest_summary(completed.stdout)  # 汇总行只在 stdout，别混 stderr 噪声
    status = verdict(passed, failed)
    detail = "" if status == "PASS" else _output_tail(output)
    return LessonResult(spec.lesson, spec.framework, spec.label, status, passed, failed, seconds, detail)


def collect_results(unit3_dir: Path) -> list[LessonResult]:
    """逐课执行（顺序跑：五次 uv 进程，结果可复现、日志可读）。"""
    return [run_lesson(unit3_dir, spec) for spec in LESSONS]


def ensure_uv() -> str:
    """自查 uv 是否在 PATH（本脚本由 `uv run` 启动时通常天然可见）；缺失给友好报错。"""
    uv = shutil.which("uv")
    if uv is None:
        print("PATH 里找不到 uv——bench 要用 uv 逐课起子进程跑验收。")
        print("先回 L0.1 装好 uv，重开终端（Windows PowerShell 记得刷新 PATH）再试。")
        raise SystemExit(2)
    return uv


def main() -> int:
    ensure_uv()
    print("== Unit 3 里程碑 bench：四框架同题 demo 全量重验（共用验收 test_contract.py） ==")
    results = collect_results(UNIT3_DIR)
    for r in results:
        mark = "ok" if r.status == "PASS" else "!!"
        counts = f"{r.passed} passed, {r.failed} failed" if r.status != "SKIPPED" else "跳过"
        print(f"[{mark}] {r.lesson:<24} {r.label:<28} {r.status:<7} ({counts}, {r.seconds:.1f}s)")
        if r.detail and r.status != "PASS":
            for line in r.detail.splitlines():
                print(f"       {line}")
    print()
    print(format_table(results))
    skipped = sum(1 for r in results if r.status == "SKIPPED")
    if skipped:
        print(f"\n注意：{skipped} 个课时被跳过（目录缺失）——在真实仓库的 unit3-frameworks/ 下跑才是完整重验。")
    code = exit_code(results)
    print(f"\nbench 退出码: {code}（0=全绿；1=有 FAIL；2=全跳过）")
    return code


if __name__ == "__main__":
    sys.exit(main())
