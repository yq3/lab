"""离线剧本与模型客户端（L5.1 副本 + L5.2 审批回环扩展）。

L5.2 副本声明（对版纪律「合理差异就地注释」）：legal/dirty 计划剧本、scripts_for、
model_for_url 与 L5.1 字节相同；差异有两处——
- run_pipeline 删除：submit 已换 interrupt 芯，「一口气跑完图」不再存在，统一出口改为
  由审批服务（approvals.ApprovalService）驱动的「跑到暂停 / 回复后恢复」两段式；
- 新增 revised_advice_after_feedback / offline_run_scripts：审批驳回回环的 drafter 修订版
  台词与「一次 run 的完整剧本清单」（服务在每次 invoke 前布置、消费后扣减）。

剧本分「clean / dirty_once / always_dirty」三型（L5.1 原样）。

诚实边界（review_rules 的延续）：离线验收时 planner/drafter 的台词由本模块预计算——
被测对象是「图拓扑 + 校验门 + 确定性执行器 + 审批 API」这条管道，不是模型的质量。
"""

from __future__ import annotations

import json

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

import mock_tools
import review_rules
from advice import Advice

# demo_trace 的默认排片：四单分演三种形态（0001/0004 走干净路、0002 演重规划、0003 演超限）
CLAIM_MODES: dict[str, str] = {
    "CLM-2026-0001": "clean",
    "CLM-2026-0002": "dirty_once",
    "CLM-2026-0003": "always_dirty",
    "CLM-2026-0004": "clean",
}


def legal_plan_text(claim_id: str) -> str:
    """剧本：合法计划——取单据/查预算/验发票三步，总额原样重述（数字纪律）。"""
    view = mock_tools.claim_view(claim_id)
    plan = {
        "claim_total_cents": view["total_cents"],
        "steps": [
            {"step_id": "s1", "tool": "fetch_claim", "claim_id": view["id"], "produces": "claim"},
            {"step_id": "s2", "tool": "check_budget", "dept": view["dept"], "produces": "budget"},
            {"step_id": "s3", "tool": "verify_invoice", "invoice_id": view["invoice_ids"][0], "produces": "invoice"},
        ],
        "note": "取单据视图、部门预算、发票校验三路证据",
    }
    return json.dumps(plan, ensure_ascii=False)


def dirty_plan_unknown_tool(claim_id: str) -> str:
    """剧本：脏计划（未知工具名）——planner 幻觉出一个白名单外的「查总账」。"""
    view = mock_tools.claim_view(claim_id)
    plan = json.loads(legal_plan_text(claim_id))
    plan["steps"][1] = {"step_id": "s2", "tool": "query_erp_balance", "dept": view["dept"], "produces": "budget"}
    return json.dumps(plan, ensure_ascii=False)


def dirty_plan_missing_field(claim_id: str) -> str:
    """剧本：脏计划（缺必填）——预算步漏了 dept 参数。"""
    plan = json.loads(legal_plan_text(claim_id))
    plan["steps"][1] = {"step_id": "s2", "tool": "check_budget", "produces": "budget"}
    return json.dumps(plan, ensure_ascii=False)


def dirty_plan_bad_amount(claim_id: str) -> str:
    """剧本：脏计划（金额非法）——重述总额写成了带单位的字符串（金额一律整数分）。"""
    plan = json.loads(legal_plan_text(claim_id))
    plan["claim_total_cents"] = f"{plan['claim_total_cents']}元"
    return json.dumps(plan, ensure_ascii=False)


def scripts_for(claim_id: str, mode: str = "clean") -> tuple[list[str], str]:
    """按剧本型生成 planner 各轮台词与 drafter 台词（drafter 与 review_rules 预期同源）。"""
    if mode == "clean":
        planner_texts = [legal_plan_text(claim_id)]
    elif mode == "dirty_once":
        planner_texts = [dirty_plan_unknown_tool(claim_id), legal_plan_text(claim_id)]
    elif mode == "always_dirty":
        planner_texts = [
            dirty_plan_unknown_tool(claim_id),
            dirty_plan_missing_field(claim_id),
            dirty_plan_bad_amount(claim_id),
        ]
    else:
        raise ValueError(f"unknown mode: {mode}")
    _first_turn, advice_json, _expected = review_rules.script_for(claim_id)
    return planner_texts, advice_json


def model_for_url(url: str, api_key: str = "test-key", model: str = "mock-model") -> Runnable:
    """模型客户端——注意没有 bind_tools（对照 L3.2）：planner 的工具选择写在计划 JSON 里，
    不走 function calling 协议；计划是数据，先过校验门再谈执行。"""
    return ChatOpenAI(base_url=url, api_key=SecretStr(api_key), model=model, max_retries=0, timeout=10)


def revised_advice_after_feedback(claim_id: str) -> str:
    """L5.2 剧本：审批驳回后的修订版建议单——转人工复核（回环重生成的第二版 drafter 台词）。

    剧情约定：审批人驳回留言要求「补充材料后再审」，drafter 收到反馈后把 decision 改为
    ESCALATE（reason 枚举风格 REJECT:APPROVAL_FEEDBACK）——内容一变，content_hash 跟着变，
    新版本走一张新审批单（A6 内容绑定的体感）。remaining_cents 仍是 check_budget 的镜像。
    """
    view = mock_tools.claim_view(claim_id)
    budget = mock_tools.budget_row(view["dept"])
    assert budget is not None, f"mock 数据缺预算行: {claim_id}"
    revised = Advice(
        claim_id=view["id"],
        decision="ESCALATE",
        reason="REJECT:APPROVAL_FEEDBACK",
        remaining_cents=budget["budget_cents"] - budget["spent_cents"],
    )
    return revised.model_dump_json()


def offline_run_scripts(claim_id: str) -> list[str]:
    """一次 run 的完整模型剧本清单（审批服务在每次 invoke 前整单布置，消费后扣减）：

    [planner 合法计划, drafter 首版建议单, drafter 修订版建议单（仅驳回回环才消费）]。

    剧本**超额供给**：once/always 路径只消费前两条，reject 回环才消费第三条——
    MockLLMEndpoint 的 FIFO 队列多给不炸（少给才 500），一次布置全程受用；
    每段 invoke 用的是全新端点实例（L3.3 的纪律：恢复侧剧本要重布，历史来自 checkpoint）。
    """
    planner_texts, drafter_text = scripts_for(claim_id, "clean")
    return [*planner_texts, drafter_text, revised_advice_after_feedback(claim_id)]
