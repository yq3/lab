"""pytest 路径配置：把 code/ 加进 sys.path——练习验收测试要 import 讲义区的共享模块。

（ex1 的骨架与测试用到 review.Vote；对版讲义的 blend/limits 是 solution 的参照。）
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
