#!/usr/bin/env python3
"""课时模板机器校验：六段式结构完整性（CURRICULUM §2/§6 的自动化落实）。

用法：
    python3 scripts/check_lesson.py                              # 扫描全部课时目录
    python3 scripts/check_lesson.py units/unit0-toolchain/L0.1-uv-toolchain

Windows 注意：python3 常是 Store 存根（退出码 49 打不开），换 python 或 py -3 调用本脚本。

检查项：六段章节齐全 / 承接段（h1 与 §1 间的 blockquote）/ §2 含 Java 对照表 / 结尾段命名 /
练习带 TODO + hints.py + pytest 验收 / solution 存在 / 延伸段源码路标锚定 commit（仓库@commit#路径）/
工程件齐备（uv.lock、.env.example 三变量、.python-version、pyproject 的 extend-exclude）。仅用标准库。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = ["## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6."]
FINAL_SECTION = "## 离毕业又近的一块"
COMMIT_ANCHOR = re.compile(r"@[0-9a-f]{7,40}#")
BASH_FENCE = ("```bash", "```sh", "```shell")
ENV_VARS = ("OPENAI_BASE_URL", "OPENAI_API_KEY", "MODEL_NAME")


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


def section_text(text: str, header: str) -> str:
    """截取某个二级章节（## N. 开头到下一个 ## 标题或文末）的正文。"""
    capture = False
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if capture:
                break
            capture = line.startswith(header)
            continue
        if capture:
            out.append(line)
    return "\n".join(out)


def has_java_table(text: str) -> bool:
    """§2 概念讲解里是否有含 Java 的对照表（宪法特色 1 的机器化）。"""
    section2 = section_text(text, "## 2.")
    return any(line.strip().startswith("|") and "java" in line.lower() for line in section2.splitlines())


def has_bridge_blockquote(text: str) -> bool:
    """h1 与第一个二级标题之间是否有承接段（blockquote 形态，CURRICULUM §2 模板）。"""
    capture = False
    for line in text.splitlines():
        if line.startswith("# ") and not capture:
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture and line.startswith(">") and line.strip(">").strip():
            return True
    return False


def check_lesson(lesson: Path) -> list[str]:
    problems: list[str] = []
    readme = lesson / "README.md"
    if not readme.is_file():
        return [f"缺少讲义 {readme}"]
    text = readme.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        if section not in text:
            problems.append(f"讲义缺少章节「{section}」")
    if FINAL_SECTION not in text:
        problems.append(f"缺少或拼写不符结尾段「{FINAL_SECTION}」")
    if not has_bridge_blockquote(text):
        problems.append("h1 与 §1 之间缺少承接段（2–3 句 blockquote：昨晚产出 → 今晚新问题）")
    if not COMMIT_ANCHOR.search(section_text(text, "## 6.")):
        problems.append("§6 延伸段源码路标未锚定 commit（格式：仓库@commit#路径）")
    if not has_java_table(text):
        problems.append("§2 概念讲解缺少 Java↔Python 对照表（宪法特色 1：表格行需含 Java）")
    concat_lines = bash_block_concat_lines(text)
    if concat_lines:
        problems.append(
            f"bash 代码块内出现 && 串联命令（PowerShell 5.1 不支持，分步行走）：第 {', '.join(map(str, concat_lines))} 行"
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
    pyproject = lesson / "pyproject.toml"
    if not pyproject.is_file():
        problems.append("课时目录缺少 pyproject.toml（每课即独立 uv 项目）")
    else:
        if 'extend-exclude = ["*.md"]' not in pyproject.read_text(encoding="utf-8"):
            problems.append('pyproject.toml 缺 extend-exclude = ["*.md"]（防 ruff 重排讲义代码块）')

    if not (lesson / "uv.lock").is_file():
        problems.append("缺少 uv.lock（每课即独立 uv 项目，锁文件必须提交）")
    env_example = lesson / ".env.example"
    if not env_example.is_file():
        problems.append("缺少 .env.example（模型端点中立约定）")
    else:
        env_text = env_example.read_text(encoding="utf-8")
        missing = [v for v in ENV_VARS if v not in env_text]
        if missing:
            problems.append(f".env.example 缺三变量中的：{', '.join(missing)}")
    if not (lesson / ".python-version").is_file():
        problems.append("缺少 .python-version（解释器版本钉死）")

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
        try:
            problems = check_lesson(lesson)
        except (OSError, UnicodeDecodeError) as exc:
            problems = [f"读取异常（损坏目录/编码问题）：{exc!r}"]
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
