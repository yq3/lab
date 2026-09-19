"""L5.1 副本 + L5.3 事件层（对版纪律「合理差异就地注释」）。

L5.1 部分逐字保留：剧本生成器（legal_plan_text / dirty_plan_* / scripts_for）、
model_for_url、run_pipeline——demo_trace 与 L5.1 复制来的测试原样能跑（回归证据）。

L5.3 新增 run_audited：统一审计出口，把三层审计件接进同一张图——
事件表（run.started/intake/plan/tool/advice/submitted 事件 + 成本事件）、
决策缓存（planner/drafter 过 AuditedModel，同 prompt 第二遍零模型请求）、
图版本绑定（topology_signature → run_key → 续跑守门）。
离线确定性：时钟注入（默认固定演示钟），两次运行事件流逐字节可复现。

诚实边界（review_rules 的延续）：离线验收时 planner/drafter 的台词由剧本预计算——
被测对象是「图拓扑 + 校验门 + 确定性执行器 + 审计三层」这条管道，不是模型的质量；
真实端点（demo_trace --real / run_pipeline(model=...)）下决策由模型自己作出。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph
from pydantic import SecretStr

import audit_cache
import eventstore
import graph
import mock_tools
import review_rules
import versioning
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


# ---- L5.3：统一审计出口（三层审计件接进同一张图）----

# 装配器签名：(模型, 记录器, 决策缓存) -> 编译图——graph.build_graph 原生满足，
# 换图实验（demo_flow 第三幕）传 lambda 换个装配即可。
GraphBuilder = Callable[[Runnable, eventstore.RunRecorder | None, audit_cache.DecisionCache | None], CompiledStateGraph]

DEMO_CLOCK = "2026-09-16T21:00:00+00:00"  # 演示固定钟：两次运行的事件流逐字节可复现（时钟注入纪律）


async def run_audited(
    claim_id: str,
    db_path: str | Path,
    *,
    mode: str = "clean",
    clock: Callable[[], str] | None = None,
    graph_builder: GraphBuilder | None = None,
    aggregate: str | None = None,
) -> dict:
    """跑一单并落全审计：事件表 + 决策缓存 + 图版本绑定，返回审计回执。

    流程六步：①探测装配求拓扑签名（与正式装配同构——审计层不改变拓扑形状）
    ②run_key（单号+签名前 12 位；aggregate 显式给定时为「续跑旧聚合」模式）
    ③续跑守门：聚合已有 run.started 的 graph_version 与当前签名逐条核对，不符抛
    GraphVersionMismatch（版本变了就别续旧账）④run.started 落事件（事件 #0）
    ⑤正式装配（recorder + cache）跑图 ⑥返回 {"final", "run_key", "graph_version", "requests"}。

    同图同单第二遍：run_key 不变、llm_decisions 全命中（requests==0）、事件照常追加；
    换图（graph_builder 变体）：签名变、新 run_key、旧 aggregate 续跑被守门拒绝。
    """
    store = eventstore.EventStore.open(db_path, clock=clock)
    cache = audit_cache.DecisionCache(db_path, clock=clock)
    try:
        mock_tools.CALL_LOG.clear()
        planner_texts, drafter_text = scripts_for(claim_id, mode)
        with MockLLMEndpoint() as ep:
            for text in planner_texts:
                ep.script_text(text)
            ep.script_text(drafter_text)
            build = graph_builder or graph.build_graph
            probe = build(model_for_url(ep.url), None, None)  # 只为求签名（拓扑与正式装配同构）
            signature = versioning.topology_signature(probe)
            run_key = aggregate or versioning.run_key(claim_id, signature)
            for row in store.events_for(run_key, type="run.started"):
                versioning.assert_compatible(row["payload"]["graph_version"], signature)
            store.append(
                run_key,
                "run.started",
                {"claim_id": claim_id, "graph_version": signature, "run_key": run_key, "mode": mode},
            )
            recorder = eventstore.RunRecorder(store, run_key)
            compiled = build(model_for_url(ep.url), recorder, cache)
            final = await compiled.ainvoke(
                graph.initial_state(claim_id),
                config={"recursion_limit": graph.RECURSION_LIMIT, "configurable": {"thread_id": run_key}},
            )
            requests = len(ep.requests)
    finally:
        cache.close()
        store.close()
    return {"final": final, "run_key": run_key, "graph_version": signature, "requests": requests}
