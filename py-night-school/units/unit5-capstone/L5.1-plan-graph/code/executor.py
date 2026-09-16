"""确定性执行器——「静态图 + 计划驱动」的执行半边（本课核心之一）。

executor 是**纯 dispatcher**：步进游标由代码掌握（`for step in plan.steps`），
LLM 零参与——同一个计划永远同一个结果（数字代码算，对照 L4.1「LLM 影响力终止于建议」）。
对照 DataAgent 的 PlanExecutorDispatcher：LLM 只能在白名单里选「做什么」，
「怎么执行」是确定性代码。

纪律：
- 白名单：执行前查 TOOL_ALLOWLIST——校验门（plan.validate_plan）已保证合法，
  这里防御性再查一层（纵深防御，对照 L4.3 fail-closed：不可达 ≠ 不设防）；
- 失败可见不静默：未知工具 / produces 冲突抛 PlanExecutionError（结构化错误：
  step_id + tool + reason），绝不静默跳过、绝不静默覆盖；
- CALL_LOG 取证：check_budget / verify_invoice 的每次真实执行都被 mock_tools 记账
  （fetch_claim 走 claim_view 纯读取通道，不记 CALL_LOG——它是「载单」不是「查询」）。
"""

from __future__ import annotations

from collections.abc import Callable

import mock_tools
from plan import TOOL_ALLOWLIST, Plan

# 执行注册表：与 plan.TOOL_ALLOWLIST 同源（test_plan 有 meta 断言两边相等——
# 白名单与注册表谁漂移了，验收当场红）。
TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "fetch_claim": mock_tools.claim_view,
    "check_budget": mock_tools.check_budget,
    "verify_invoice": mock_tools.verify_invoice,
}

# 步模型中的非参数字段：executor 分发时排除——参数 = 其余字段按名传给工具
_COMMON_FIELDS = frozenset({"step_id", "tool", "produces"})


class PlanExecutionError(RuntimeError):
    """计划执行的结构化失败（fail-closed）：未知工具 / produces 冲突。

    正常流程不可达（校验门在前），它是执行层的防御性防线——所以选择「响亮地抛」
    而不是「结构化降级」：能走到这里说明上游有 bug，静默降级等于把 bug 藏进业务结果。
    """

    def __init__(self, step_id: str, tool: str, reason: str) -> None:
        self.step_id = step_id
        self.tool = tool
        self.reason = reason
        super().__init__(f"step {step_id!r} tool {tool!r}: {reason}")


def execute_plan(candidate: Plan) -> dict[str, dict]:
    """按计划顺序步进执行：查白名单 → 调真实工具 → 结果写 results[step.produces]。

    确定性：同计划同结果（工具全是纯读取）；执行顺序与计划顺序严格一致（CALL_LOG 可证）。
    """
    results: dict[str, dict] = {}
    for step in candidate.steps:
        if step.tool not in TOOL_ALLOWLIST:  # 防御性再查（不可达路径的纵深防御）
            raise PlanExecutionError(step.step_id, step.tool, "unknown_tool")
        if step.produces in results:  # 产物键冲突：第二个写会静默覆盖第一个——必须可见
            raise PlanExecutionError(step.step_id, step.tool, f"duplicate_produces: {step.produces}")
        func = TOOL_REGISTRY[step.tool]
        payload = {key: value for key, value in step.model_dump().items() if key not in _COMMON_FIELDS}
        results[step.produces] = func(**payload)  # 工具真实执行（check/verify 记 CALL_LOG）
    return results
