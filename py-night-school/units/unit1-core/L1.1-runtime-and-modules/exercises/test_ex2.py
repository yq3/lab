"""练习 2 验收（不要改本文件——它就是你的判卷老师）。

以「模块方式」（python -m 包.模块）运行修好的入口，并顺便验证：
直接当脚本跑仍然会以那条著名的 ImportError 失败——证明你没有用
「把相对导入改成绝对导入」这种破坏包结构的修法绕过考点。
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=30, cwd=HERE)


def test_module_mode_runs_and_prints() -> None:
    proc = _run(["-m", "claimfix.runner"])
    assert proc.returncode == 0, f"stderr：\n{proc.stderr}"
    assert proc.stdout is not None
    assert "claimfix 审单：[1200, 3500] -> PASS" in proc.stdout


def test_module_mode_rejects_bad_claim() -> None:
    proc = _run(["-m", "claimfix.runner", "8800"])
    assert proc.returncode == 1
    assert proc.stdout is not None
    assert "REJECT:ITEM_OVER_LIMIT" in proc.stdout


def test_direct_run_still_fails_with_known_error() -> None:
    """直接当脚本跑必须仍然炸出 §5 陷阱的原句——证明你修的是启动方式，不是 import。"""
    proc = _run(["claimfix/runner.py"])
    assert proc.returncode != 0
    assert proc.stderr is not None
    assert "attempted relative import with no known parent package" in proc.stderr
