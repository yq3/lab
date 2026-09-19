"""Plan JSON 的 Pydantic 强约束——「静态图 + 计划驱动」的计划半边（本课核心之一）。

设计出处：research/agent-oss/report.md §4.2（推荐架构：主形态=静态图+计划驱动 A23；
失败原因显式状态键回喂重规划 A29）；Java 原生蓝本 research/agent-oss/profiles/DataAgent.md
§2.2 的 PlanExecutorNode——工具名必须在白名单 `Set.of(...)`、每类步骤必填参数逐项检查。

三层结构（对照 Java 的 sealed interface + record + Jackson @JsonTypeInfo）：
- PlanStep 基类：共同字段 step_id / produces；
- 三个 record 式子类：tool 字段是 Literal tag（判别符），参数字段各自强类型声明；
- Plan：计划本体（steps 判别联合列表 + 重述的入口单据总额 + note 审计说明）。

validate_plan 全程「结构化错误不抛裸异常」：合法返回 Plan，非法返回 PlanRejection
（reason_code 枚举 + detail 人类可读）——拒绝原因是要回喂给 planner 的任务数据（A29），
不是要打断图的异常。
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic_core import ErrorDetails

# 工具白名单：校验门（本模块）与执行器（executor.TOOL_REGISTRY）共用同一份名单——
# Literal tag 在类型层枚举了合法工具，白名单在运行时再显式声明一层（纵深防御，§5 陷阱）。
TOOL_ALLOWLIST: frozenset[str] = frozenset({"fetch_claim", "check_budget", "verify_invoice"})

# 拒绝原因枚举（枚举风格纪律：结构化拒绝原因，对版 A29「失败原因显式状态键」）
ReasonCode = Literal[
    "not_json",  # 不是合法 JSON（模型输出了解释性文本等）
    "unknown_tool",  # 工具名不在白名单
    "missing_field",  # 步型必填参数缺失
    "bad_amount",  # 金额字段类型/取值非法（负数、带小数、带单位字符串——金额一律整数分）
    "empty_plan",  # steps 为空列表
    "bad_plan_shape",  # 其余结构不符（多余字段、类型错位等）
]


class PlanRejection(BaseModel):
    """计划被拒的结构化原因——进 state 的 plan_rejections（回喂给 planner 的任务数据）。"""

    reason_code: ReasonCode = Field(description="拒绝原因枚举码")
    detail: str = Field(description="人类可读细节（含出错位置），随原因一起回喂")


class PlanStep(BaseModel):
    """步基类：共同字段。子类用 tool 的 Literal tag 做判别联合的精确分派。"""

    model_config = ConfigDict(extra="forbid")  # 计划外字段一律拒收——计划是数据合同，不是杂货铺

    step_id: str = Field(min_length=1, description="步骤标识（审计与错误定位用）")
    produces: str = Field(min_length=1, description="本步产物写入 results 的键名")


class FetchClaimStep(PlanStep):
    """取单据步：executor 调 mock_tools.claim_view（纯读取，不记 CALL_LOG）。"""

    tool: Literal["fetch_claim"]
    claim_id: str = Field(min_length=1)


class FetchBudgetStep(PlanStep):
    """查预算步：executor 调 mock_tools.check_budget（记 CALL_LOG 取证）。"""

    tool: Literal["check_budget"]
    dept: str = Field(min_length=1)


class VerifyInvoiceStep(PlanStep):
    """发票校验步：executor 调 mock_tools.verify_invoice（记 CALL_LOG 取证）。"""

    tool: Literal["verify_invoice"]
    invoice_id: str = Field(min_length=1)


# 判别联合：Field(discriminator="tool") 让 Pydantic 按 tool 字段的 Literal tag 精确分派到
# 具体步型——对照 Jackson 的 @JsonTypeInfo(use=NAME) 多态反序列化。
StepUnion = Annotated[
    FetchClaimStep | FetchBudgetStep | VerifyInvoiceStep,
    Field(discriminator="tool"),
]

# 金额字段的命名约定（..._cents）——bad_amount 维度的判定依据：金额一律整数分
_AMOUNT_SUFFIX = "_cents"
# 数值约束类错误类型（Pydantic v2）——落在金额字段上即 bad_amount
_AMOUNT_ERROR_TYPES = frozenset(
    {"int_parsing", "int_from_float", "greater_than", "greater_than_equal", "less_than", "less_than_equal"}
)


class Plan(BaseModel):
    """计划本体：LLM 规划的全部产出。数字纪律——只允许重述入口已给的总额，不允许自己算新的。"""

    model_config = ConfigDict(extra="forbid")

    claim_total_cents: int = Field(
        description="重述入口单据的总额（分）——忠实重述：脏数据单据的负总额照实重述，"
        "它要在建议单层被规则 1 处置（ESCALATE），不该在计划层被拦；校验门只管「格式是整数分」"
    )
    steps: list[StepUnion] = Field(min_length=1, description="顺序执行的取数步骤（executor 按列表顺序步进）")
    note: str = Field(default="", description="计划说明（给审计读，executor 不消费）")


_PLAN_ADAPTER: TypeAdapter[Plan] = TypeAdapter(Plan)


def _reason_code_for(error: ErrorDetails) -> ReasonCode:
    """把单条 Pydantic 错误映射到拒绝原因枚举（映射顺序就是校验语义的分层）。"""
    error_type = error["type"]
    loc = error["loc"]
    field = next((part for part in reversed(loc) if isinstance(part, str)), "")
    if error_type in ("union_tag_invalid", "literal_error"):
        return "unknown_tool"
    if error_type == "missing":
        return "missing_field"
    if field.endswith(_AMOUNT_SUFFIX) and error_type in _AMOUNT_ERROR_TYPES:
        return "bad_amount"
    if error_type == "too_short" and field == "steps":
        return "empty_plan"
    return "bad_plan_shape"


def _rejection_from_validation(exc: ValidationError) -> PlanRejection:
    """ValidationError → PlanRejection：取首错（回喂的原因要短而准），保留出错位置。"""
    error = exc.errors()[0]
    loc = ".".join(str(part) for part in error["loc"]) or "<root>"
    return PlanRejection(reason_code=_reason_code_for(error), detail=f"{loc}: {error['msg']}")


def validate_plan(text: str) -> Plan | PlanRejection:
    """计划校验门：解析 → 判别联合分派 → 白名单 → 必填/金额校验。

    全程结构化错误不抛裸异常：任何失败都返回 PlanRejection（原因进 state、回喂 planner，
    A29 纪律——纠错回路靠显式状态键，不靠「错误文本扔给模型碰运气」）。
    """
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return PlanRejection(reason_code="not_json", detail=str(exc))
    try:
        candidate = _PLAN_ADAPTER.validate_python(obj)
    except ValidationError as exc:
        return _rejection_from_validation(exc)
    for index, step in enumerate(candidate.steps):
        if step.tool not in TOOL_ALLOWLIST:  # Literal tag 已保证不可达——纵深防御再查一层
            return PlanRejection(reason_code="unknown_tool", detail=f"steps[{index}].tool: {step.tool!r} 不在白名单")
    return candidate
