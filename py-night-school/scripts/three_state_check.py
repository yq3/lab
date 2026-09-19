#!/usr/bin/env python3
"""三态验证法（AGENTS.md §5）的自动化：发货态 / 毕业态 / 机器校验。

用法：
    python3 scripts/three_state_check.py units/unit2-mini-agent/L2.1-raw-api   # 单课（可多个）
    python3 scripts/three_state_check.py                                      # 全量：30 课时 + 5 里程碑

Windows 注意：python3 常是 Store 存根（退出码 49 打不开），换 python 或 py -3 调用本脚本。

对每个课时目录做三件事：
1. 发货态：原地跑三命令（pytest / ruff check / pyright）——只允许 exercises/ 的红
   （TODO 未填），code/ 讲义区必须绿；
2. 毕业态：把课时目录镜像到系统临时目录（保持仓库相对深度，data/ 一并镜像，
   这样引用共享素材的测试不断粮），用 solution/ex*.py 覆盖 exercises/ 后跑三命令
   + ruff format --check——全部通过；
3. 提醒 check_lesson.py 的结果（结构校验）。

仅用标准库 + 课时自身的 uv。exit 0 = 三态全过。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THREE_COMMANDS = ("pytest", "ruff check .", "pyright")


def run(cmd: str, cwd: Path) -> tuple[int, str]:
    completed = subprocess.run(f"uv run {cmd}", shell=True, cwd=cwd, capture_output=True, text=True)
    return completed.returncode, completed.stdout + completed.stderr


def is_designed_failure(output: str, lesson: Path) -> bool:
    """发货态的「精确红」：pytest 摘要里 FAILED 行全部落在学员作答区——课时是 exercises/，里程碑是 tests/。

    只认 FAILED（用例失败）这一种设计内红；「ERROR 」开头的集合错误行不计——
    集合错误意味着 import/骨架已损坏，不是 TODO 未填的预期形态，照常判 FAIL。
    """
    bad_lines = [
        line
        for line in output.splitlines()
        if line.startswith(("FAILED", "ERROR")) and not line.startswith("ERROR ")
    ]
    if not bad_lines:
        return False
    if (lesson / "exercises").is_dir():
        allowed = "exercises"
    elif (lesson / "tests").is_dir():
        allowed = "tests"
    else:
        return False
    return all(allowed in line for line in bad_lines)


def check_one(lesson: Path) -> bool:
    """对单个课时/里程碑目录跑三态，返回是否全过。"""
    failures: list[str] = []

    # ---- 1. 发货态 ----
    print(f"== 发货态 {lesson.relative_to(ROOT)} ==")
    for cmd in THREE_COMMANDS:
        code, output = run(cmd, lesson)
        if cmd.startswith("pytest"):
            ok = code == 0 or is_designed_failure(output, lesson)
            detail = "（练习区设计内红）" if code != 0 and ok else ""
            print(f"  uv run {cmd:<14} -> {'PASS' if ok else 'FAIL'} {detail}")
            if not ok:
                failures.append(f"发货态 {cmd} 出现设计外的红")
        else:
            print(f"  uv run {cmd:<14} -> {'PASS' if code == 0 else 'FAIL'}")
            if code != 0:
                failures.append(f"发货态 {cmd} 非绿")

    # ---- 2. 毕业态（临时目录镜像，保持仓库内相对深度） ----
    print("== 毕业态（solution 覆盖后的临时副本） ==")
    with tempfile.TemporaryDirectory(prefix="pns-grad-") as tmp:
        mirror_root = Path(tmp) / "mirror"
        # 相对深度：py-night-school/<unit>/<lesson> —— 镜像同样三层
        unit_dir = lesson.parent.relative_to(ROOT)
        dest = mirror_root / "py-night-school" / unit_dir / lesson.name
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            lesson,
            dest,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".venv", ".pytest_cache", ".ruff_cache", "__pycache__"),
        )
        # 共享素材：data/ 与课时目录同层数（parents[4] 的解析目标）
        shutil.copytree(ROOT / "data", mirror_root / "py-night-school" / "data")
        # solution 覆盖学员作答区：课时 -> exercises/，里程碑（无 exercises/）-> 目录根
        overlay = dest / "solution"
        if overlay.is_dir():
            target_dir = dest / "exercises" if (dest / "exercises").is_dir() else dest
            for solution_file in overlay.glob("*.py"):
                target = target_dir / solution_file.name
                if target.is_file():
                    shutil.copy2(solution_file, target)
        for cmd in (*THREE_COMMANDS, "ruff format --check ."):
            code, output = run(cmd, dest)
            print(f"  uv run {cmd:<24} -> {'PASS' if code == 0 else 'FAIL'}")
            if code != 0:
                tail = "\n".join(output.splitlines()[-12:])
                failures.append(f"毕业态 {cmd} 非绿：\n{tail}")

    # ---- 3. 结构校验（仅课时布局；里程碑无六段式讲义，不走 check_lesson） ----
    if (lesson / "exercises").is_dir():
        print("== 结构校验 check_lesson ==")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_lesson.py"), str(lesson)],
            capture_output=True,
            text=True,
        )
        print(result.stdout.strip())
        if result.returncode != 0:
            failures.append("check_lesson 未通过")
    else:
        print("== 结构校验 check_lesson ==")
        print("SKIP（里程碑布局，六段式结构校验不适用）")

    if failures:
        print("\n三态验证 FAIL：")
        for item in failures:
            print(f"  - {item}")
        return False
    print("\n三态验证 PASS")
    return True


def main() -> int:
    if sys.argv[1:]:
        lessons = [(ROOT / arg).resolve() for arg in sys.argv[1:]]
        missing = [str(lesson) for lesson in lessons if not lesson.is_dir()]
        if missing:
            print(f"目录不存在: {', '.join(missing)}")
            return 2
    else:
        lessons = sorted((ROOT / "units").glob("unit*/L*")) + sorted((ROOT / "units").glob("unit*/milestone"))
        if not lessons:
            print("未发现课时目录")
            return 1

    failed: list[Path] = []
    for lesson in lessons:
        try:
            ok = check_one(lesson)
        except (OSError, UnicodeDecodeError, shutil.Error) as exc:
            print(f"\n== {lesson.relative_to(ROOT)} 读取/镜像异常 ==")
            print(f"  {exc!r}")
            ok = False
        if not ok:
            failed.append(lesson)
    if failed:
        print(f"\n{len(failed)}/{len(lessons)} 个目录三态未过：")
        for lesson in failed:
            print(f"  - {lesson.relative_to(ROOT)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
