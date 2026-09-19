"""产品改造工作台的机制件层：跨课重验——子进程逐课重跑三课机制件的讲义区验收。

对 L4.1 / L4.2 / L4.3 三个课时（unit4-product-lab/ 下）各跑一次 ``uv run pytest code/``
（cwd=各课时目录），汇总成一张表：课时 / 产品（锚定 commit）/ 结果 / 耗时，并以退出码
收口（全 PASS=0）。这是里程碑两层判据里的**层①（自动可验收）**：三课 code/ 机制件的
三态就是「机制我真的跑过」的机器证据；**层②（产品真改造）** 在 notes/ 三份改造说明
里承载（本文件末尾的完成度报告只报状态，不判分）。

为什么只跑 ``code/`` 不跑 ``exercises/``：exercises/ 是各课自己的学员作答区（发货态
含设计内 TODO 红），不属于本里程碑的判据——里程碑验的是机制件层，不是替各课判毕业。

用法（学员命令，跨平台）：
    uv run python verify.py

新知识点（subprocess 的安全用法，给 Java 同学；对版 Unit 3 里程碑 bench.py）：
- ``subprocess.run(["uv", "run", ...], cwd=...)`` ≈ Java 的
  ``new ProcessBuilder("uv", "run", ...).directory(dir).start()``——参数以**列表**逐个
  传递，不经 shell 解析（对照 ``Runtime.exec(String)`` 按空格切词出过的事故：路径带
  空格就碎）。没有 shell=True，就没有 shell 注入。
- 子进程默认继承父进程环境变量（PATH 里的 uv 因此可见——脚本开头仍自查并给友好报错），
  但要摘掉 ``VIRTUAL_ENV``：本脚本常由 ``uv run`` 启动，父项目的 .venv 会写进它；
  兄弟课时的子 ``uv run`` 看到不匹配的值会告警（实测教训：告警走 stderr 且出现在
  pytest 汇总行之后，混进解析会误判失败）。
- 不叠加 ``-q``：各课 pyproject 的 addopts 已带 -q，叠成 -qq 会把汇总行也吞掉。

分层纪律（为什么 pytest 不真的去跑兄弟课时——宪法演进锚点 ⑧，Unit 3 先例）：
- 解析层（parse_pytest_summary / verdict / format_table / exit_code / notes_status）
  是纯函数，tests/test_verify_logic.py 只测它们 + 「课时目录缺失→SKIPPED」的降级分支；
- 执行层（run_lesson）是薄壳：一次 runner 调用 + 计时。**runner 可注入**——默认实现
  起真 subprocess，测试注入 fake runner 喂合成输出离线验收 PASS/FAIL/超时分支；
  毕业态镜像里没有兄弟课时目录，测试碰它们必红，真跑是学员命令。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

UNIT4_DIR = Path(__file__).resolve().parents[1]  # units/unit4-product-lab

PER_LESSON_TIMEOUT = 300.0  # 单课超时（秒）：首次 uv sync 重依赖（langgraph）也够用


@dataclass(frozen=True)
class LessonSpec:
    """一个待重验的课时：目录名 + 产品 key（notes/<key>.md 一一对应）+ 展示名（锚定 commit）。"""

    lesson: str
    product: str
    label: str


# 三课时：产品 key 与 notes/ 三份改造说明一一对应（tests/test_notes_meta.py 按它对页）。
LESSONS: tuple[LessonSpec, ...] = (
    LessonSpec("L4.1-ai-hedge-fund", "ai-hedge-fund", "ai-hedge-fund fc1bf25（层级投票）"),
    LessonSpec("L4.2-tradingagents-debate", "tradingagents", "TradingAgents be952b8（辩论-裁决）"),
    LessonSpec("L4.3-vibe-trading-governance", "vibe-trading", "Vibe-Trading f84b2977（治理合规）"),
)


@dataclass(frozen=True)
class LessonResult:
    """一次重验的结果（SKIPPED 时 passed/failed 为 0、seconds 为 0.0）。"""

    lesson: str
    product: str
    label: str
    status: str  # "PASS" / "FAIL" / "SKIPPED"
    passed: int
    failed: int  # pytest 口径的 failed+error 合计
    seconds: float  # 墙钟耗时（含 uv 启动）
    detail: str  # FAIL/SKIPPED 时的人类可读说明（输出尾部或原因）


# ---- 改造说明（notes/）的结构常量与解析（纯函数；tests/test_notes_meta.py 只测这里） ----

NOTES_DIR = Path(__file__).resolve().parent / "notes"

# 三个产品 key → 展示名（notes/<key>.md 一一对应）
PRODUCTS: dict[str, str] = {
    "ai-hedge-fund": "ai-hedge-fund（L4.1 层级投票）",
    "tradingagents": "TradingAgents（L4.2 辩论-裁决）",
    "vibe-trading": "Vibe-Trading（L4.3 治理合规）",
}

# 三份改造说明的固定小节（tests/test_notes_meta.py 按它把关；顺序即页面顺序）
NOTES_SECTIONS: tuple[str, ...] = ("改什么", "为什么", "最小 diff", "复现步骤", "证据")

PLACEHOLDER = "TODO(改造)"  # 模板占位符：出现在小节里 = 该节还没写


def section_body(note_text: str, heading: str) -> str:
    """给定说明全文与小节标题，返回该小节正文（到下一个 ``## `` 为止）——纯函数（给定）。

    小节标题匹配 ``## 标题`` 行（strip 后全等）；找不到返回空串。
    """
    lines = note_text.splitlines()
    body: list[str] = []
    collecting = False
    for line in lines:
        if line.startswith("## "):
            if collecting:
                break
            collecting = line[3:].strip() == heading
            continue
        if collecting:
            body.append(line)
    return "\n".join(body).strip()


def notes_status(notes: dict[str, str]) -> list[tuple[str, str]]:
    """三份改造说明的完成度检查（纯函数，给定）：五节齐 且 无占位符 =「完成」。"""
    statuses: list[tuple[str, str]] = []
    for key in PRODUCTS:
        text = notes.get(key, "")
        if not text:
            statuses.append((key, "缺页"))
            continue
        missing = [h for h in NOTES_SECTIONS if not section_body(text, h)]
        if missing:
            statuses.append((key, f"缺小节: {', '.join(missing)}"))
        elif PLACEHOLDER in text:
            statuses.append((key, "模板态：占位符未替换（对照 solution/notes 收口）"))
        else:
            statuses.append((key, "完成：五节齐、无占位符"))
    return statuses


# ---- 解析层（纯函数，tests 只测这里） ----


def parse_pytest_summary(pytest_stdout: str) -> tuple[int, int]:
    """从 pytest -q 的 stdout 里解析 (passed, failed+error)。

    只认 ``N passed`` / ``N failed`` / ``N error(s)`` 计数（如末尾汇总行
    ``19 passed in 6.40s`` / ``1 failed, 1 passed in 2s``）；找不到任何计数时返回
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
    """汇总表（课时/产品/结果/耗时）——纯排版，不做判定。"""
    lines = ["| 课时 | 产品（锚定 commit） | 结果 | 耗时 |", "|---|---|---|---|"]
    for r in results:
        seconds = f"{r.seconds:.1f}s" if r.status != "SKIPPED" else "-"
        lines.append(f"| {r.lesson} | {r.label} | {r.status} | {seconds} |")
    return "\n".join(lines)


def exit_code(results: list[LessonResult]) -> int:
    """全 PASS=0；任一 FAIL=1；一条都没跑成（全 SKIPPED）=2——别让「没跑」伪装成「全绿」。"""
    if all(r.status == "SKIPPED" for r in results):
        return 2
    return 0 if all(r.status == "PASS" for r in results) else 1


# ---- 执行层（薄壳：runner 调用 + 计时；pytest 用 fake runner 测它，不起真子进程） ----

# 可注入的执行器：参数 (命令列表, 工作目录, 环境变量, 超时秒)；默认实现起真 subprocess，
# tests/test_verify_logic.py 注入合成输出的 fake——执行与解析由此解耦。
Runner = Callable[[list[str], Path, dict[str, str], float], "subprocess.CompletedProcess[str]"]


def uv_runner(cmd: list[str], cwd: Path, env: dict[str, str], timeout: float) -> subprocess.CompletedProcess[str]:
    """默认执行器：真正的 subprocess 调用（≈ ProcessBuilder；学员命令路径）。"""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)


def _output_tail(text: str, lines: int = 6) -> str:
    return "\n".join(text.strip().splitlines()[-lines:]) if text.strip() else "(无输出)"


def run_lesson(unit4_dir: Path, spec: LessonSpec, runner: Runner = uv_runner) -> LessonResult:
    """对一个课时目录跑一次讲义区验收；目录缺失优雅降级为 SKIPPED（不起任何子进程）。"""
    lesson_dir = unit4_dir / spec.lesson
    if not lesson_dir.is_dir():
        return LessonResult(
            spec.lesson,
            spec.product,
            spec.label,
            "SKIPPED",
            0,
            0,
            0.0,
            f"课时目录不存在: {lesson_dir}",
        )
    uv = shutil.which("uv")  # 理论上 main 已自查；保留防御分支，供 run_lesson 被直接调用时兜底
    if uv is None:
        return LessonResult(
            spec.lesson,
            spec.product,
            spec.label,
            "SKIPPED",
            0,
            0,
            0.0,
            "PATH 里找不到 uv",
        )
    # 子进程环境继承父进程（≈ ProcessBuilder 默认继承），但摘掉 VIRTUAL_ENV（见模块 docstring）。
    child_env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    # 只跑 code/（讲义区），且不叠 -q（各课 addopts 已带，-qq 吞汇总行）——两条都是契约。
    cmd = [uv, "run", "pytest", "code/"]
    started = time.perf_counter()
    try:
        completed = runner(cmd, lesson_dir, child_env, PER_LESSON_TIMEOUT)
    except subprocess.TimeoutExpired:
        return LessonResult(
            spec.lesson,
            spec.product,
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
    detail = "" if status == "PASS" else _output_tail(completed.stdout + completed.stderr)
    return LessonResult(spec.lesson, spec.product, spec.label, status, passed, failed, seconds, detail)


def collect_results(unit4_dir: Path, runner: Runner = uv_runner) -> list[LessonResult]:
    """逐课执行（顺序跑：三次 uv 进程，结果可复现、日志可读）。"""
    return [run_lesson(unit4_dir, spec, runner) for spec in LESSONS]


def read_notes() -> dict[str, str]:
    """读 notes/ 三页（缺页时如实抛错——完成度报告在 main 里，别静默吞）。"""
    return {key: (NOTES_DIR / f"{key}.md").read_text(encoding="utf-8") for key in PRODUCTS}


def ensure_uv() -> str:
    """自查 uv 是否在 PATH（本脚本由 `uv run` 启动时通常天然可见）；缺失给友好报错。"""
    uv = shutil.which("uv")
    if uv is None:
        print("PATH 里找不到 uv——verify 要用 uv 逐课起子进程跑验收。")
        print("先回 L0.1 装好 uv，重开终端（Windows PowerShell 记得刷新 PATH）再试。")
        raise SystemExit(2)
    return uv


def main() -> int:
    ensure_uv()
    print("== Unit 4 里程碑 verify：三课机制件跨课重验（讲义区 code/ 三态） ==")
    results = collect_results(UNIT4_DIR)
    for r in results:
        mark = "ok" if r.status == "PASS" else "!!"
        counts = f"{r.passed} passed, {r.failed} failed" if r.status != "SKIPPED" else "跳过"
        print(f"[{mark}] {r.lesson:<30} {r.label:<32} {r.status:<7} ({counts}, {r.seconds:.1f}s)")
        if r.detail and r.status != "PASS":
            for line in r.detail.splitlines():
                print(f"       {line}")
    print()
    print(format_table(results))
    skipped = sum(1 for r in results if r.status == "SKIPPED")
    if skipped:
        print(f"\n注意：{skipped} 个课时被跳过（目录缺失）——在真实仓库的 unit4-product-lab/ 下跑才是完整重验。")
    print("\n改造说明完成度（只报状态不判分——退出码只看机制件层；结构把关在 pytest 的 meta 测试）：")
    for key, status in notes_status(read_notes()):
        print(f"  {key:<15} {status}")
    code = exit_code(results)
    print(f"\nverify 退出码: {code}（0=全绿；1=有 FAIL；2=全跳过）")
    return code


if __name__ == "__main__":
    sys.exit(main())
