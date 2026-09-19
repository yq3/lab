"""pytest 共享配置：把 code/ 加进 sys.path——exercises/ 的练习与验收直接
import 共享模块（mock_tools / review_rules / advice / demo），与 code/ 内测试同源。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "code"))
