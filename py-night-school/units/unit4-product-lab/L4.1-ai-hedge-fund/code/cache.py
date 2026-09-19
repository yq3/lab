"""一决定一 JSON 文件——缓存 = 审计记录 = 调试踪迹，三合一（对版 hedge_fund/llm/cache.py）。

产品的 PromptCache 是本仓库最值得抄的设计：同一个文件同时是
  1. 缓存：同一张单子重审一遍，$0（第二次直接读盘）；
  2. 审计记录：每一票背后的精确 prompt + response + 快照哈希——回放免费；
  3. 调试踪迹：解析失败的原始响应也留盘（parse_error 字段），绝不静默丢弃。

与产品的差异（教学版纪律）：产品默认写用户主目录 ~/.hedge-fund/cache/llm/；
本课必须显式注入目录（测试用 tmp_path、演示用 TemporaryDirectory），
绝不写学员主目录——这是夜校对「克隆即学」的承诺。

key 算法与产品逐字对版：sha256(f"{checker}|{model}|{system}|{user}") 截前 24 位——
字符串拼接天然确定（§5 陷阱的「天然安全派」）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def decision_key(checker: str, model: str, system: str, user: str) -> str:
    """一个（检查员, 模型, system, user）组合的缓存 key（对版 prompt_key）。"""
    payload = f"{checker}|{model}|{system}|{user}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


class DecisionCache:
    """每决定一 JSON 文件（对版 PromptCache）。"""

    def __init__(self, cache_dir: Path | str) -> None:
        self._dir = Path(cache_dir)

    def get(self, key: str) -> dict | None:
        """读一条决策记录；文件不存在或损坏都当 miss（对版 get 的宽容语义）。"""
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None  # 损坏条目当 miss——下一次 put 会重写它

    def put(self, key: str, record: dict) -> None:
        """落一条决策记录，补上 created_at（对版 put——审计字段在这里加）。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        record = {**record, "created_at": datetime.now(UTC).isoformat()}
        path = self._dir / f"{key}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
