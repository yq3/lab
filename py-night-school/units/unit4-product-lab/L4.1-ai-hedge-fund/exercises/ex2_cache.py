# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体**与所需的顶部 import**，其余不要动）
"""DecisionCache：一决定一 JSON 文件——缓存 = 审计记录 = 调试踪迹。

对版产品 hedge_fund/llm/cache.py（PromptCache，48 行）：key 是四元组
（checker, model, system, user）的内容寻址哈希；每决定落一个 JSON 文件；
get 对损坏文件宽容（当 miss）；put 补 created_at 后写盘。

考察点三件事：
- key 算法：四字段怎么拼、怎么哈希、截多长（与讲义 cache.decision_key 同式）；
- get/put 的文件读写：一决定一文件、目录不存在谁建、created_at 谁加；
- 失败留盘：MiniChecker 解析失败时把原始响应与 parse_error 一起 put 进盘。

完成判据：uv run pytest exercises/test_ex2.py 全绿——五个测试：
  同一（检查员, prompt）第二次 review 零模型调用（client.calls 断言）；
  key 确定性：同输入同 key、任一输入变了 key 必变；
  put/get 往返：created_at 由 put 补上；
  parse_error 的留盘文件里有原始响应原文；
  损坏缓存条目当 miss（get 返回 None 不炸）。

TODO 所需的顶部 import：hashlib / json / datetime（按你的写法自行补）。
"""

from __future__ import annotations

import json
from pathlib import Path


def decision_key(checker: str, model: str, system: str, user: str) -> str:
    """缓存 key：四个字段 -> 确定性字符串 -> sha256 十六进制截前 24 位（对版 prompt_key）。"""
    # TODO(ex2): 四个字段按什么分隔符拼成一个 payload？哈希后从第几位截到第几位？
    raise NotImplementedError("TODO(ex2): 补全 key 算法")


class DecisionCache:
    """一决定一 JSON 文件（对版 PromptCache）。"""

    def __init__(self, cache_dir: Path | str) -> None:
        self._dir = Path(cache_dir)

    def get(self, key: str) -> dict | None:
        """读一条决策记录。"""
        # TODO(ex2): 文件不存在返回什么？文件存在但坏了（解析失败/读失败）返回什么？
        raise NotImplementedError("TODO(ex2): 补全 get")

    def put(self, key: str, record: dict) -> None:
        """落一条决策记录。"""
        # TODO(ex2): 目录不存在谁建？created_at 在哪一步加进 record？文件名长什么样？
        raise NotImplementedError("TODO(ex2): 补全 put")


# ---- given 基础设施（不要改）：让缓存「被真的用起来」的迷你检查员与计数客户端 ----


class ScriptClient:
    """离线模型替身：按剧本依次回文本，并数自己被调了几次（讲义 MockLLMEndpoint 的迷你版）。"""

    def __init__(self, replies: list[str]) -> None:
        self.model = "mock-model"
        self._replies = list(replies)
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self._replies.pop(0)


class MiniChecker:
    """讲义 reviewers.LLMCheckerBase 的缩影（given，不要改）：
    命中缓存直接用 parsed；miss 才调 client；解析失败也把原始响应 put 留盘。
    """

    SYSTEM = "你是测试用检查员"

    def __init__(self, name: str, client: ScriptClient, cache: DecisionCache) -> None:
        self._name = name
        self._client = client
        self._cache = cache

    def review(self, user: str) -> dict:
        key = decision_key(self._name, self._client.model, self.SYSTEM, user)
        cached = self._cache.get(key)
        if cached is not None and "parsed" in cached:
            return cached["parsed"]
        response = self._client.complete(self.SYSTEM, user)
        record = {
            "checker": self._name,
            "model": self._client.model,
            "system": self.SYSTEM,
            "user": user,
            "response": response,
        }
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as exc:
            self._cache.put(key, {**record, "parse_error": str(exc)})
            return {"abstained": True, "parse_error": str(exc)}
        self._cache.put(key, {**record, "parsed": parsed})
        return parsed
