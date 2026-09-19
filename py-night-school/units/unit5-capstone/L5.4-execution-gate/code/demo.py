"""离线剧本、模型客户端与统一审计出口（L5.2+L5.3 副本 + L5.4 两段式驱动）。

L5.4 副本声明（对版纪律「合理差异就地注释」）：剧本生成器（legal/dirty 计划、
revised_advice_after_feedback、offline_run_scripts）、model_for_url、CLAIM_MODES 与
L5.2 字节相同；DEMO_CLOCK、GraphBuilder 协议与 L5.3 相同。差异两处——
- run_pipeline 复活（L5.2 曾删）：图的 submit 已是 interrupt 芯，「一口气跑完」不存在
  了——本函数内置一段**自动批准**（approve 恢复）把图推到终点，L5.1/L5.3 系的回归
  测试照旧可用；真实审批路径走 approvals.ApprovalService（demo_final 三链路）；
- run_audited 演进（L5.3 原型）：同样内置自动批准段；graph_builder 从三参协议扩为
  「三参 + 装配关键字」——检查点用进程内 InMemorySaver（审计出口是单进程演示，
  持久 checkpoint 是审批服务的职责）。

诚实边界（review_rules 的延续）：离线验收时 planner/drafter 的台词由剧本预计算——
被测对象是「图拓扑 + 校验门 + 确定性执行器 + 审批换芯 + 执行门 + 审计三层」这条管道，
不是模型的质量；真实端点（model=...）下决策由模型自己作出。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import SecretStr

import audit_cache
import eventstore
import gate
import graph
import mock_tools
import review_rules
import versioning
from advice import Advice
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


# ---- 统一出口（L5.4：图必停 submit——内置自动批准段把图推到终点）----


async def _drive_with_auto_approve(compiled: CompiledStateGraph, payload, cfg: RunnableConfig) -> dict:
    """跑图 + 自动批准：跑到 submit 暂停就替审批人按一次 approve（讲义区回归的驱动器）。

    自动批准的语义：模拟一个「见单必批」的审批人——门与审计层照常工作（gate.checked /
    payment.executed / gate.denied 事件照发）。真实审批路径（once/always/reject 回环）
    在 approvals.ApprovalService（demo_final 三链路）。
    """
    result = await compiled.ainvoke(payload, cfg)
    snapshot = await compiled.aget_state(cfg)
    if snapshot.interrupts and "submit" in snapshot.next:
        result = await compiled.ainvoke(Command(resume={"action": "approve"}), cfg)
    return result


async def run_pipeline(claim_id: str, model: Runnable | None = None, mode: str = "clean") -> dict:
    """统一出口：跑完整张固定图（含审批暂停→自动批准→过门付款），返回最终 state。

    model=None 走离线剧本（mode 决定 planner 台词）；传入 model（真实端点）直接起图——
    图一行不改，重规划环、审批暂停与执行门对真实模型同样生效（L5.1 原样的承诺）。
    """
    cfg = graph.run_config("pipeline")
    if model is not None:
        compiled = graph.build_graph(model, checkpointer=graph.memory_saver())
        return await _drive_with_auto_approve(compiled, graph.initial_state(claim_id), cfg)
    mock_tools.CALL_LOG.clear()
    planner_texts, drafter_text = scripts_for(claim_id, mode)
    with MockLLMEndpoint() as ep:
        for text in planner_texts:
            ep.script_text(text)
        ep.script_text(drafter_text)
        ep.script_text(revised_advice_after_feedback(claim_id))  # 超额供给：回环才消费（offline_run_scripts 纪律）
        compiled = graph.build_graph(model_for_url(ep.url), checkpointer=graph.memory_saver())
        return await _drive_with_auto_approve(compiled, graph.initial_state(claim_id), cfg)


# ---- L5.3 统一审计出口（L5.4 演进：两段式 + 执行门事件）----

# 装配器签名：(模型, 记录器, 缓存, **装配关键字) -> 编译图——graph.build_graph 原生满足；
# 换图实验（extra_stamp 变体）传 lambda m, recorder, cache, **kw: ... 在自己的关键字里加参数。
GraphBuilder = Callable[..., CompiledStateGraph]

DEMO_CLOCK = "2026-09-16T21:00:00+00:00"  # 演示固定钟：两次运行的事件流逐字节可复现（时钟注入纪律）


async def run_audited(
    claim_id: str,
    db_path: str | Path,
    *,
    mode: str = "clean",
    clock: Callable[[], str] | None = None,
    graph_builder: GraphBuilder | None = None,
    aggregate: str | None = None,
    policy: gate.Policy | None = None,
) -> dict:
    """跑一单并落全审计：事件表 + 决策缓存 + 图版本绑定 + 执行门事件，返回审计回执。

    流程七步：①探测装配求拓扑签名 ②run_key（aggregate 显式给定时为「续跑旧聚合」模式）
    ③续跑守门：聚合已有 run.started 的 graph_version 与当前签名逐条核对，不符抛
    GraphVersionMismatch（版本变了就别续旧账）④run.started 落事件（事件 #0）
    ⑤正式装配（recorder + cache + 门三件 + 进程内 checkpoint）⑥跑到 submit 暂停后
    自动批准一段（approve 恢复——门与审计照常工作）⑦返回 {"final", "run_key",
    "graph_version", "requests"}。

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
            ep.script_text(revised_advice_after_feedback(claim_id))
            build = graph_builder or graph.build_graph
            signature = versioning.topology_signature(build(model_for_url(ep.url)))
            run_key = aggregate or versioning.run_key(claim_id, signature)
            for row in store.events_for(run_key, type="run.started"):
                versioning.assert_compatible(row["payload"]["graph_version"], signature)
            store.append(
                run_key,
                "run.started",
                {"claim_id": claim_id, "graph_version": signature, "run_key": run_key, "mode": mode},
            )
            recorder = eventstore.RunRecorder(store, run_key)
            ledger = graph.PaymentLedger(store)
            compiled = build(
                model_for_url(ep.url),
                recorder,
                cache,
                checkpointer=graph.memory_saver(),
                policy=policy,
                ledger=ledger,
                today=graph.DEFAULT_TODAY,
            )
            cfg = RunnableConfig(recursion_limit=graph.RECURSION_LIMIT, configurable={"thread_id": run_key})
            final = await _drive_with_auto_approve(compiled, graph.initial_state(claim_id), cfg)
            requests = len(ep.requests)
    finally:
        cache.close()
        store.close()
    return {"final": final, "run_key": run_key, "graph_version": signature, "requests": requests}
