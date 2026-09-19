"""L4.2 模型调用预算：LLMCallBudget——包装模型客户端计数，超限抛 BudgetExceeded。

为什么需要它（讲义 §2.5 双预算轴）：
- langgraph 的 recursion_limit 数的是 **superstep**（图步数）——一个不调模型的节点也烧一步；
  产品的 max_recur_limit=100 就是这条轴（对版 default_config.py）。
- 但按 token 计费的世界里，成本 ≈ **模型调用次数**——一个 superstep 里可能藏一次贵模型调用。
  固定轮次辩论让调用次数可以先验算出来（辩论段恰好 2*N 次、风险段恰好 3*M 次），预算封顶
  才有意义——「可预算」与「可审计」是固定轮次拓扑的两大卖点（调研结论）。
- 对照 L2.3 的 AgentBudgetExceeded（手写循环的轮数预算）：同一条「确定性护栏」纪律，
  这次包在模型客户端外层，图结构一行不改。

Java 对照：≈ 线程池的 RejectedExecutionException——提交前先查容量，满了就响亮拒绝，
绝不默默排队超卖。wrap() 让一个预算对象罩住多个模型（quick/deep 共用一个计数器），
≈ 熔断器实例被多个客户端共享。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage


class BudgetExceeded(Exception):
    """模型调用预算耗尽——确定性硬终止（对照 L2.3 AgentBudgetExceeded / GraphRecursionError）。"""

    def __init__(self, limit: int, used: int) -> None:
        self.limit = limit
        self.used = used
        super().__init__(f"LLM 调用预算耗尽：limit={limit}, 已调用 {used} 次")


class LLMCallBudget:
    """模型调用预算：limit=None 不限；wrap() 可罩多个模型，共享同一个计数器。"""

    def __init__(self, limit: int | None = None) -> None:
        self.limit = limit
        self._used = 0

    @property
    def used(self) -> int:
        """已放行的模型调用次数。"""
        return self._used

    def wrap(self, model: Any) -> BudgetedModel:
        """把模型客户端包进本预算（quick/deep 各 wrap 一次，计数共享）。"""
        return BudgetedModel(model, self)

    def _try_acquire(self) -> None:
        """放行前查容量：满了响亮拒绝（对照线程池拒绝策略）。"""
        if self.limit is not None and self._used >= self.limit:
            raise BudgetExceeded(self.limit, self._used)

    def _record(self) -> None:
        self._used += 1


class BudgetedModel:
    """被预算罩住的模型客户端：ainvoke 前查预算、放行后计数，其余行为原样委托。"""

    def __init__(self, model: Any, budget: LLMCallBudget) -> None:
        self._model = model
        self._budget = budget

    async def ainvoke(self, messages: Sequence[object]) -> AIMessage:
        self._budget._try_acquire()
        result = await self._model.ainvoke(messages)
        self._budget._record()
        return result
