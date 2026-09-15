"""练习 1 验收（不要改本文件——它就是你的判卷老师）。

双模式验证：
  - import 方式（进程内调函数）；
  - subprocess 方式（真·直接运行一次，验证 __main__ 分支与退出码）。
"""

import subprocess
import sys
from pathlib import Path

import pytest

from ex1_guard import format_daily_report, main


def test_import_mode_provides_function() -> None:
    assert format_daily_report("CLM-2026-0001", "PASS") == "CLM-2026-0001 -> PASS"


def test_main_prints_and_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    assert "CLM-2026-0001 -> PASS" in capsys.readouterr().out


def test_direct_run_mode() -> None:
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "ex1_guard.py")],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"直接运行应以退出码 0 结束，stderr：\n{proc.stderr}"
    # subprocess 的 stdout 类型是 str | None——先断言非空再使用（类型收窄，L1.2 详讲）
    assert proc.stdout is not None
    assert "CLM-2026-0001 -> PASS" in proc.stdout
