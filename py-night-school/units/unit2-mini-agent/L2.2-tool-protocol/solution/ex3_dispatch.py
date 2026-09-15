# 参考答案：ex3_dispatch（练习文件的完整解法——完成前别看）
"""分发执行 run_tool：注册表查表 → 解析校验 → 解包调用 → 字符串化。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

BUDGET_FILE = Path(__file__).resolve().parents[4] / "data" / "expense" / "budget_mock.json"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    func: Callable[..., str | int]


def error_result(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)


class PreapproveArgs(BaseModel):
    """与讲义同款：形状上只要求「非空整数列表」——负数留给业务规则判断。"""

    items_cents: list[int] = Field(min_length=1)


class NoArgs(BaseModel):
    """无参工具的参数模型：空模型（schema 只有 type: object）——工具不都带参数。"""


def _preapprove(items_cents: list[int]) -> str:
    if any(cents <= 0 for cents in items_cents):
        return "REJECT:INVALID_AMOUNT"
    if any(cents > 5000 for cents in items_cents):
        return "REJECT:ITEM_OVER_LIMIT"
    return "PASS"


def _claim_count() -> int:
    data = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    return len(data["expense_claims"])


def _always_boom() -> str:
    raise ValueError("模拟工具内部事故")


# 给定注册表：三个工具已手工登记（ex2 的 @tool 是自动版，这里手动版聚焦分发逻辑）
REGISTRY: dict[str, ToolSpec] = {
    "preapprove": ToolSpec("preapprove", "预审报销单明细。", PreapproveArgs, _preapprove),
    "claim_count": ToolSpec("claim_count", "统计报销单总数。", NoArgs, _claim_count),
    "always_boom": ToolSpec("always_boom", "必定抛异常的演示工具。", NoArgs, _always_boom),
}


def run_tool(name: str, arguments_json: str, registry: dict[str, ToolSpec] = REGISTRY) -> str:
    """分发执行一个 tool_call。三种失败返回 error JSON，不抛异常（错误要回喂给模型）。"""
    spec = registry.get(name)
    if spec is None:
        return error_result(f"unknown_tool: {name}（可用工具：{', '.join(sorted(registry))}）")
    try:
        args = spec.args_model.model_validate_json(arguments_json)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = first["loc"][0] if first["loc"] else "json"
        return error_result(f"invalid_arguments: {field}: {first['msg']}")
    try:
        result = spec.func(**args.model_dump())
    except Exception as exc:  # noqa: BLE001 —— 工具内部任何异常都转成回喂信息
        return error_result(f"tool_error: {type(exc).__name__}: {exc}")
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
