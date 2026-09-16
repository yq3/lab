# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""execute_plan 补全：确定性步进执行——白名单分发 + produces 写回 + 未知工具结构化失败。

考察点：executor 是纯 dispatcher——游标由代码掌握（for step in plan.steps），
执行顺序与计划顺序严格一致（CALL_LOG 是取证）；同一个计划双跑全等；
「计划外工具 / produces 冲突」必须可见不静默（PlanExecutionError，fail-closed）。
讲义 code/executor.py 是同构完整版（对版参照），先自己写，全绿后再去对照读。

完成判据：uv run pytest exercises/test_ex2.py 全绿——4 个测试：
  执行顺序与计划一致（正排/倒排两份计划，CALL_LOG 跟着变）+ 产物内容来自真实工具；
  同计划双跑全等（确定性）；
  绕过校验门夹带的未知工具：结构化失败（step_id/tool 可读），且什么都没被执行；
  produces 冲突：结构化失败（duplicate_produces），不静默覆盖。
TODO 所需的顶部 import：
  from plan import TOOL_ALLOWLIST
"""

from __future__ import annotations

from collections.abc import Callable

import mock_tools
from plan import Plan

# 执行注册表（given）：工具名 → 可调用对象；与 plan.TOOL_ALLOWLIST 同源
TOOL_FUNCS: dict[str, Callable[..., dict]] = {
    "fetch_claim": mock_tools.claim_view,
    "check_budget": mock_tools.check_budget,
    "verify_invoice": mock_tools.verify_invoice,
}

# 步模型中的非参数字段（given）：分发时排除——剩下的字段才是工具入参
_COMMON_FIELDS = frozenset({"step_id", "tool", "produces"})


class PlanExecutionError(RuntimeError):
    """计划执行的结构化失败（given）：step_id / tool / reason 三件套——失败可见，不静默。"""

    def __init__(self, step_id: str, tool: str, reason: str) -> None:
        self.step_id = step_id
        self.tool = tool
        self.reason = reason
        super().__init__(f"step {step_id!r} tool {tool!r}: {reason}")


def execute_plan(candidate: Plan) -> dict[str, dict]:
    """按计划顺序步进执行：查白名单 → 调真实工具 → 结果写 results[step.produces]。"""
    results: dict[str, dict] = {}
    for step in candidate.steps:
        # TODO(ex2): 每步三问——
        #   1) step.tool 在白名单吗（不在：失败怎么才「可见不静默」——PlanExecutionError 的构造参数）？
        #   2) step.produces 要写的键已被占了吗（不查会发生什么：第二个写把第一个静默顶掉）？
        #   3) 工具的真实入参是 step 的哪些字段（哪些字段是步的元数据、不该传给工具）？
        # 提示：step.model_dump() 给完整字段 dict；白名单是 plan.TOOL_ALLOWLIST（顶部 import 见 docstring）。
        raise NotImplementedError(f"TODO(ex2): 补全步 {step.step_id} 的执行")
    return results
