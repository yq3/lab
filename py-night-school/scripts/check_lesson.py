#!/usr/bin/env python3
"""课时模板机器校验：六段式结构完整性（CURRICULUM §2/§6 的自动化落实）。

用法：
    python3 scripts/check_lesson.py                              # 扫描全部课时目录
    python3 scripts/check_lesson.py units/unit0-toolchain/L0.1-uv-toolchain

检查项：六段章节齐全 / 练习带 TODO + hints.py + pytest 验收 / solution 存在 /
延伸段源码路标锚定 commit（仓库@commit#路径）。仅用标准库。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = ["## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6."]
COMMIT_ANCHOR = re.compile(r"@[0-9a-f]{7,40}#")
BASH_FENCE = ("```bash", "```sh", "```shell")


def bash_block_concat_lines(text: str) -> list[int]:
    """返回 bash/sh/shell 围栏代码块内包含 && 的行号（学员命令块）。

    只查 bash 块——Java 对照代码里的逻辑与 a && b 不受影响。
    """
    violations: list[int] = []
    in_block = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not in_block and stripped.startswith(BASH_FENCE):
            in_block = True
            continue
        if in_block and stripped == "```":
            in_block = False
            continue
        if in_block and "&&" in line:
            violations.append(lineno)
    return violations


def check_lesson(lesson: Path) -> list[str]:
    problems: list[str] = []
    readme = lesson / "README.md"
    if not readme.is_file():
        return [f"缺少讲义 {readme}"]
    text = readme.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        if section not in text:
            problems.append(f"讲义缺少章节「{section}」")
    if not COMMIT_ANCHOR.search(text):
        problems.append("延伸段源码路标未锚定 commit（格式：仓库@commit#路径）")
    concat_lines = bash_block_concat_lines(text)
    if concat_lines:
        problems.append(
            f"bash 代码块内出现 && 串联命令（PowerShell 5.1 不支持，分行走）：第 {', '.join(map(str, concat_lines))} 行"
        )

    if not (lesson / "code").is_dir():
        problems.append("缺少 code/（讲义动手代码）")

    exercises = lesson / "exercises"
    if not exercises.is_dir():
        problems.append("缺少 exercises/")
    else:
        py_files = list(exercises.glob("*.py"))
        if not py_files:
            problems.append("exercises/ 没有练习文件")
        if not any("TODO(" in p.read_text(encoding="utf-8") for p in py_files):
            problems.append("练习缺少 TODO 挖空")
        if not (exercises / "hints.py").is_file():
            problems.append("缺少 exercises/hints.py（渐进提示）")
        if not list(exercises.glob("test_*.py")):
            problems.append("缺少 pytest 验收文件（test_*.py）")

    if not (lesson / "solution").is_dir():
        problems.append("缺少 solution/（参考答案）")
    if not (lesson / "pyproject.toml").is_file():
        problems.append("课时目录缺少 pyproject.toml（每课即独立 uv 项目）")

    return problems


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    targets = [root / arg for arg in sys.argv[1:]]
    if not targets:
        targets = sorted((root / "units").glob("unit*/L*"))
    if not targets:
        print("未发现课时目录")
        return 1

    failed = False
    for lesson in targets:
        problems = check_lesson(lesson)
        rel = lesson.relative_to(root)
        if problems:
            failed = True
            print(f"FAIL {rel}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"PASS {rel}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
