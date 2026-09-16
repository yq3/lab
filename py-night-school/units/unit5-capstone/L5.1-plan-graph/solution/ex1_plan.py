# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""validate_plan 补全：把 planner 产出的计划文本校验成 Plan，或结构化拒绝（PlanRejection）。

考察点：判别联合的精确分派（TypeAdapter 对带 discriminator 的 Plan 校验时按 tool 字段
一步分派到具体步型）、ValidationError 首错到拒绝原因码的映射、白名单的显式再查——
讲义 code/plan.py 是同构完整版（对版参照），先自己写，全绿后再去对照读。

完成判据：uv run pytest exercises/test_ex1.py 全绿——8 个测试：
  合法计划：三步各自分派到正确步型（FetchClaimStep / FetchBudgetStep / VerifyInvoiceStep）；
  脏数据单的忠实重述（负总额）也合法——校验门管格式，脏数据在建议单层处置；
  拒绝维度逐维参数化：not_json / unknown_tool / missing_field / bad_amount 各归各位；
  补充维度：empty_plan（steps=[]）与 bad_plan_shape（多余字段）；
  覆盖型 meta：全部脏样本的 reason_code 种类集恰好六种——把某维样本改成与另一维同码即红。
TODO 所需的顶部 import：
  from pydantic import TypeAdapter, ValidationError
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic_core import ErrorDetails

TOOL_ALLOWLIST: frozenset[str] = frozenset({"fetch_claim", "check_budget", "verify_invoice"})

ReasonCode = Literal[
    "not_json",
    "unknown_tool",
    "missing_field",
    "bad_amount",
    "empty_plan",
    "bad_plan_shape",
]


class PlanRejection(BaseModel):
    """计划被拒的结构化原因——它是要回喂给 planner 的任务数据（A29），不是异常文本。"""

    reason_code: ReasonCode = Field(description="拒绝原因枚举码")
    detail: str = Field(description="人类可读细节（含出错位置），随原因一起回喂")


class PlanStep(BaseModel):
    """步基类：共同字段；子类以 tool 的 Literal tag 作判别符。"""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    produces: str = Field(min_length=1)


class FetchClaimStep(PlanStep):
    tool: Literal["fetch_claim"]
    claim_id: str = Field(min_length=1)


class FetchBudgetStep(PlanStep):
    tool: Literal["check_budget"]
    dept: str = Field(min_length=1)


class VerifyInvoiceStep(PlanStep):
    tool: Literal["verify_invoice"]
    invoice_id: str = Field(min_length=1)


StepUnion = Annotated[
    FetchClaimStep | FetchBudgetStep | VerifyInvoiceStep,
    Field(discriminator="tool"),
]

_AMOUNT_SUFFIX = "_cents"
_AMOUNT_ERROR_TYPES = frozenset(
    {"int_parsing", "int_from_float", "greater_than", "greater_than_equal", "less_than", "less_than_equal"}
)


class Plan(BaseModel):
    """计划本体：claim_total_cents 只允许忠实重述（含脏数据单的负总额），格式必须是整数分。"""

    model_config = ConfigDict(extra="forbid")

    claim_total_cents: int = Field(description="重述入口单据的总额（分）")
    steps: list[StepUnion] = Field(min_length=1)
    note: str = Field(default="")


def _reason_code_for(error: ErrorDetails) -> ReasonCode:
    """（给定）单条 Pydantic 错误 → 拒绝原因枚举：判别失败=未知工具、缺字段、金额类型错、空计划。"""
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


def _not_json_rejection(exc: json.JSONDecodeError) -> PlanRejection:
    """（给定）not_json 分支：模型输出了解释性文本、markdown 围栏等不是 JSON 的东西。"""
    return PlanRejection(reason_code="not_json", detail=str(exc))


def validate_plan(text: str) -> Plan | PlanRejection:
    """计划校验门：解析 → 判别联合分派 → 白名单 → 必填/金额校验（全程结构化错误不抛裸异常）。"""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return _not_json_rejection(exc)
    try:
        candidate = TypeAdapter(Plan).validate_python(obj)  # 判别联合按 tool 字段一步分派
    except ValidationError as exc:
        error = exc.errors()[0]  # 首错优先——回喂原因要短而准
        loc = ".".join(str(part) for part in error["loc"]) or "<root>"
        return PlanRejection(reason_code=_reason_code_for(error), detail=f"{loc}: {error['msg']}")
    for index, step in enumerate(candidate.steps):
        if step.tool not in TOOL_ALLOWLIST:  # Literal 已保证不可达——纵深防御再查一层
            return PlanRejection(reason_code="unknown_tool", detail=f"steps[{index}].tool: {step.tool!r} 不在白名单")
    return candidate
