"""pytest 路径配置：把 code/ 加进 sys.path——练习与验收要 import 讲义区的共享模块。

（ex1 用 mandate；ex3 用 gate/broker/enforcement/halt/mandate/pending 的完整件——
改造题的「改造对象」就是它们；不依赖 pytest 的目录收集顺序，显式声明。）
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
