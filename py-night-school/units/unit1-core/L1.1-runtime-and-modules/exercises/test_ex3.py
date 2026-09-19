"""练习 3 验收（不要改本文件——它就是你的判卷老师）。

重放 ex3_predictions.py 里写明的三个命令，把你预测的输出与真实 stdout 逐行比对。
"""

import subprocess
import sys
from pathlib import Path

from ex3_predictions import PREDICTED_OUTPUTS

HERE = Path(__file__).parent

COMMANDS: dict[str, list[str]] = {
    "A_run_probe_a_directly": ["probe_a.py"],
    "B_import_probe_b": ["-c", "import probe_b"],
    "C_run_probe_c_directly": ["probe_c.py"],
}


def _stdout_lines(args: list[str]) -> list[str]:
    proc = subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=30, cwd=HERE)
    assert proc.returncode == 0, f"命令执行失败：{args}\nstderr：{proc.stderr}"
    # subprocess 的 stdout 类型是 str | None——先断言非空再使用（类型收窄，L1.2 详讲）
    assert proc.stdout is not None
    return proc.stdout.splitlines()


def test_predictions_match_reality() -> None:
    for key, args in COMMANDS.items():
        expected = PREDICTED_OUTPUTS[key]
        assert expected != ["??"], f"{key}：还是占位符——先写下你的预测再跑"
        actual = _stdout_lines(args)
        # 故意不在失败信息里贴实际输出：亲手重放那三个命令再核对，才是本题的学法
        assert actual == expected, f"{key}：预测与实际不符——亲手重放命令，逐行找差异"
