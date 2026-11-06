"""主 agent 本地工具（不跨进程的轻量能力）。

- lookup_taxpayer_profile：档案只读查询（与计税 agent 同款，主 agent 路由判断用）
- whoami：展示 context_schema —— 操作员身份来自平台注入的会话上下文，
  模型只能读、不能伪造
- save_calc_result：把计税结论写入 state 扩展字段（展示工具返回 Command 更新状态）
"""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from shared.config import DATA_DIR


@tool
def whoami(runtime: ToolRuntime) -> str:
    """查看当前会话的操作员与在办纳税人（来自平台注入的企业会话上下文）。

    当需要确认"现在是谁在操作、在办哪个纳税人"时调用，不要凭记忆猜测。
    """
    ctx = runtime.context or {}
    return json.dumps(
        {"operator": ctx.get("operator"), "taxpayer_id": ctx.get("taxpayer_id")},
        ensure_ascii=False,
    )


@tool
def lookup_taxpayer_profile(taxpayer_id: str) -> str:
    """查询纳税人年度档案（收入构成、已预缴税额、专项扣除明细）。

    仅用于路由判断与资料速览；正式计税请委派 delegate_to_tax_calc。

    Args:
        taxpayer_id: 纳税人编号，如 T2025-001。
    """
    with (DATA_DIR / "taxpayer_profiles.json").open(encoding="utf-8") as f:
        profiles = json.load(f)["profiles"]
    profile = next((p for p in profiles if p["taxpayer_id"] == taxpayer_id), None)
    if profile is None:
        return json.dumps({"error": f"纳税人 {taxpayer_id} 不存在，请核对编号"}, ensure_ascii=False)
    return json.dumps(profile, ensure_ascii=False)


@tool
def save_calc_result(result_json: str, runtime: ToolRuntime) -> Command:
    """把计税 agent 返回的结构化结论存入会话状态（后续申报委派直接引用）。

    每次拿到 delegate_to_tax_calc 的结论后调用一次；重复调用会覆盖旧结论。

    Args:
        result_json: 计税结论的 JSON 文本（原样传入，不要改写）。
    """
    # 展示点：工具返回 Command 更新 state_schema 扩展字段（不追加消息内容），
    # 同时手动补 ToolMessage 呼应本次 tool_call
    tool_call_id = getattr(runtime, "tool_call_id", "")
    return Command(
        update={
            "last_tax_result": result_json,
            "messages": [ToolMessage(content="计税结论已存档", tool_call_id=tool_call_id)],
        }
    )


def _profile_summary(taxpayer_id: str) -> str:
    with (DATA_DIR / "taxpayer_profiles.json").open(encoding="utf-8") as f:
        profiles: list[dict[str, Any]] = json.load(f)["profiles"]
    profile = next((p for p in profiles if p["taxpayer_id"] == taxpayer_id), None)
    if profile is None:
        return f"纳税人 {taxpayer_id} 不存在"
    deductions = "、".join(
        f"{item['type']} {item['amount']}元（材料{'齐' if item.get('evidence_complete') else '缺失'}）"
        for item in profile.get("special_extra_deductions", [])
    )
    return (
        f"{profile['name']}（{profile['taxpayer_id']}，{profile['year']} 年度）："
        f"工资 {profile['incomes'].get('wages', 0)} 元；已预缴 {profile.get('prepaid_tax', 0)} 元；"
        f"专项附加扣除：{deductions or '无'}"
    )


MAIN_TOOLS = [whoami, lookup_taxpayer_profile, save_calc_result]
