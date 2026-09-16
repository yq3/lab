"""pytest 路径配置：把 code/ 加进 sys.path——练习验收测试要 import 讲义区的共享模块。

（ex1 自包含；ex2 复用讲义区的 gate 模块；ex3 要读 code/JAVA-MAPPING.md——
不依赖 pytest 的目录收集顺序，显式声明。）
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
