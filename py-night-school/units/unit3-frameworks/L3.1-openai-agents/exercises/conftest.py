"""exercises/ 的 sys.path 引导：让练习文件能 import 讲义区 code/ 的共享模块。

单跑 exercises/ 时（uv run pytest exercises/），pytest 只会把 exercises/ 挂上 sys.path；
改造题要 import 讲义区的 mock_tools / advice / review_rules / demo——这里补上 code/ 路径。
（整目录跑 uv run pytest 时本文件是冗余保险。）
"""

from __future__ import annotations

import sys
from pathlib import Path

CODE_DIR = str(Path(__file__).resolve().parents[1] / "code")
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)
