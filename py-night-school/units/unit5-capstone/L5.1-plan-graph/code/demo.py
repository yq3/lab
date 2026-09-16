"""L5.1 离线 demo：MockLLMEndpoint + 剧本跑通固定图的四单（与 L3.2 同款替身）。

剧本分「clean / dirty_once / always_dirty」三型，把图的三种形态各演一遍：
- clean：planner 一轮产合法计划 → 执行 → 建议单 → 送审；
- dirty_once：第 1 轮产脏计划（未知工具名）→ 拒绝原因回喂 → 第 2 轮合法（重规划环）；
- always_dirty：三轮各脏一种维度（未知工具/缺必填/金额非法）→ 重规划烧完 → escalate 哨兵。

诚实边界（review_rules 的延续）：离线验收时 planner/drafter 的台词由本模块预计算——
被测对象是「图拓扑 + 校验门 + 确定性执行器」这条管道，不是模型的质量；
真实端点（--real）下这些决策由模型自己读提示词后作出。
"""

from __future__ import annotations

import json

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

import graph
import mock_tools
import review_rules
from mock_endpoint import MockLLMEndpoint

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


async def run_pipeline(claim_id: str, model: Runnable | None = None, mode: str = "clean") -> dict:
    """统一出口：跑完整张固定图，返回最终 state（plan/plan_rejections/results/advice/events/sent）。

    model=None 走离线剧本（mode 决定 planner 台词）；传入 model（真实端点）直接起图——
    图一行不改，重规划环与超限哨兵对真实模型同样生效。
    """
    if model is not None:
        compiled = graph.build_graph(model)
        return await compiled.ainvoke(graph.initial_state(claim_id), config={"recursion_limit": graph.RECURSION_LIMIT})
    mock_tools.CALL_LOG.clear()
    planner_texts, drafter_text = scripts_for(claim_id, mode)
    with MockLLMEndpoint() as ep:
        for text in planner_texts:
            ep.script_text(text)
        ep.script_text(drafter_text)
        compiled = graph.build_graph(model_for_url(ep.url))
        result = await compiled.ainvoke(
            graph.initial_state(claim_id), config={"recursion_limit": graph.RECURSION_LIMIT}
        )
    return result
