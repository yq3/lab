# 参考答案：ex1_contract_column（练习文件的完整解法——完成前别看）
"""tablegen 扩展：给决策表加一列「契约测试是否在位」（参考答案）。

对照要点：基准是「众数指纹」而不是「某一课钦定」——五课在宪法上平等（字节相同约定
没有钦定母本），谁偏离多数派谁就是 drift；并列时取字典序最小保证确定性。
"""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

CONTRACT_REL = "code/test_contract.py"


def _short_digest(data: bytes) -> str:
    """字节内容的 md5 指纹前 8 位（given：对版校验的「指纹」半边）。"""
    return hashlib.md5(data).hexdigest()[:8]


def contract_column(lesson_dirs: dict[str, Path]) -> dict[str, str]:
    """计算每课「契约测试是否在位」列的格子值（missing / in-place / drift）。"""
    digests: dict[str, str] = {}
    for key, lesson_dir in lesson_dirs.items():
        path = lesson_dir / CONTRACT_REL
        if path.is_file():
            digests[key] = _short_digest(path.read_bytes())
    column: dict[str, str] = {key: "missing" for key in lesson_dirs}
    if not digests:
        return column
    counts = Counter(digests.values())
    # 基准 = 众数指纹；并列取字典序最小（次数降序、指纹升序）——同一组输入永远同一列
    baseline = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    for key, digest in digests.items():
        column[key] = f"in-place({digest})" if digest == baseline else f"drift({digest})"
    return column
