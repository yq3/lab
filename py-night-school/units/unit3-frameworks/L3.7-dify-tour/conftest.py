"""pytest 收集配置：把 code/ 与 exercises/ 加进 sys.path（课时即独立 uv 项目，L3.6 同款）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "code"))
sys.path.insert(0, str(Path(__file__).parent / "exercises"))
