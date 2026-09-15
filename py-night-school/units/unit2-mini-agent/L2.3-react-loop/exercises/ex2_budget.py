# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体与所需的顶部 import，其余不要动）
"""轮数预算：硬终止护栏。

考察点：for-range 上限即预算（一次模型调用 = 一轮）；耗尽抛 BudgetExceeded 且
异常信息里带轮数；恰好跑满预算、一轮不多——确定性护栏与概率性终止的区别。

完成判据：uv run pytest exercises/test_ex2.py 全绿——
  执念模型在第 3 轮触发异常；模型恰好被调 3 次；历史恰好 3 个 assistant(tool_calls)。
提示：把「软终止」和「硬终止」写成两个出口：循环内 return，循环外 raise。
"""

from __future__ import annotations

from collections.abc import Sequence


class BudgetExceeded(Exception):
    """轮数预算耗尽。"""


def _preapprove(items_cents: list[int]) -> str:
    if any(cents <= 0 for cents in items_cents):
        return "REJECT:INVALID_AMOUNT"
    return "PASS"


class ObsessedModel:
    """执念模型：每轮都要再查一次工具，永远不会直接回答（软终止永不来）。"""

    def __init__(self) -> None:
        self.request_count = 0

    async def complete(self, messages: Sequence[dict]) -> dict:
        self.request_count += 1
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{self.request_count:03d}",
                    "type": "function",
                    "function": {"name": "preapprove", "arguments": '{"items_cents": [1200]}'},
                }
            ],
        }
        return {"choices": [{"index": 0, "message": message}]}


async def run_with_budget(model: ObsessedModel, user_message: str, max_turns: int) -> list[dict]:
    """带预算的循环：模型回答则返回完整历史；max_turns 轮耗尽抛 BudgetExceeded。

    每轮：请求模型 → assistant 入史 → tool_calls 逐个执行回喂（工具名固定 preapprove，
    参数 json.loads 后 ** 解包调用）。异常信息要包含轮数（运维第一眼要知道烧了几轮）。
    """
    # TODO(ex2): for 循环 range(1, max_turns + 1)；循环内处理软终止；循环外 raise
    raise NotImplementedError("TODO(ex2): 补全 run_with_budget")
