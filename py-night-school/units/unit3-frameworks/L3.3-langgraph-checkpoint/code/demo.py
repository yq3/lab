"""L3.3 同题 demo：给 L3.2 的审查图装上 checkpointer（记忆）与 interrupt（人审门）。

图结构（在 L3.2 的图上加一个 human_gate 节点，回边也回到 reviewer）：

    START → reviewer ──(条件边：最后一条消息)──→ tools ──→ reviewer（回边成环）
                    ├─(ESCALATE 建议单)→ human_gate ──→ reviewer（人工决策作为新消息回场）
                    └─(其他建议单)─────────────────→ finalize → END

两条新能力（本课全部内容）：
- checkpointer：compile(checkpointer=AsyncSqliteSaver(...))，同一个 thread_id 的两次
  invoke 共享一份状态——状态存在 sqlite 文件里，进程死活无关（暂停→杀进程→恢复的底座）；
- interrupt：human_gate 节点里 interrupt(payload) 第一次被调时「抛-捕-暂停」——
  GraphInterrupt 被 pregel 捕获、中断信息连同图状态一起落盘；恢复时同一节点从头重执行，
  interrupt() 不再抛、而是返回 Command(resume=...) 带来的人工决策。

输出模型是本课对共享 Advice 的扩展：ReviewOutcome(Advice) 加 human 字段
（Pydantic 模型继承——Java 的子类继承 + Bean 扩展）：
- 非 ESCALATE 单不暂停，直达 finalize，human="skipped"；
- ESCALATE 单在 human_gate 暂停，人工 approve→APPROVE/PASS、deny→REJECT/REJECT:HUMAN_DENIED。
"""

from __future__ import annotations

import json
import operator
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal, NotRequired, TypedDict

import aiosqlite
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from pydantic import SecretStr

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

# 与 review_rules 同源的审查规则（真实端点模式下它就是 system 提示；离线模式下是替身决策函数）
SYSTEM_PROMPT = """你是报销单审查助手。审查规则（先命中先停）：
1) 明细含非正数金额 → ESCALATE / REJECT:INVALID_AMOUNT（脏数据转人审）
2) 任一明细 > 5000 分 → REJECT / REJECT:ITEM_OVER_LIMIT
3) 关联发票校验未过 → REJECT / REJECT:INVOICE_INVALID
4) 总额 > 部门剩余预算 → REJECT / REJECT:BUDGET_EXCEEDED
5) 以上全不中 → APPROVE / PASS
先用工具核实部门预算与发票校验，再输出建议单 JSON
（claim_id / decision / reason / remaining_cents 四字段，金额单位分）。
decision 为 ESCALATE 时系统会暂停图等人工审批，审批结果会以新的 user 消息送达：
那时按「approve→APPROVE/PASS；deny→REJECT/REJECT:HUMAN_DENIED」输出最终建议单 JSON。"""

# 工具注册表：框架绑定只到这里——mock_tools 本体不 import 任何框架（四课对版）
TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "check_budget": mock_tools.check_budget,
    "verify_invoice": mock_tools.verify_invoice,
}

RECURSION_LIMIT = 12  # 硬终止预算：ESCALATE 全程 6 个 superstep（对照 L3.2 的 8/4）

HumanDecision = Literal["approve", "deny", "skipped"]


class ReviewOutcome(Advice):
    """L3.3 在共享 Advice 上的本课扩展：人审决策字段（Pydantic 模型继承）。

    继承自四课共用的 Advice——父类四字段原样可用，子类只加一个 human：
    skipped=未过人审门（非 ESCALATE 单零暂停）；approve/deny=人工放行/拒绝。
    Java 对照：extends 一个 Bean 加字段；但 Pydantic 的校验、序列化、JSON Schema
    全部自动继承——共用验收脚本认 Advice 的地方，ReviewOutcome 都能顶上（子类多一字段）。
    """

    human: HumanDecision


class ClaimState(TypedDict):
    """图状态：L3.2 的 ClaimState 加一个人审键（其余三个键原样延续）。

    - messages / events 带 Annotated reducer：合并语义——恢复后流水从暂停点继续追加；
    - advice 无 reducer：覆盖语义，全图只有 finalize 写它（值是 ReviewOutcome）；
    - human_decision 无 reducer：只有 human_gate 写它——恢复重执行时幂等重写同一个值。
    """

    messages: Annotated[list, add_messages]  # 消息史 append-only（add_messages 按 id 去重合并）
    events: Annotated[list[str], operator.add]  # 审计流水：每个节点登记自己的名字
    advice: NotRequired[ReviewOutcome]  # 最终建议单（入口状态没有这个键，finalize 才让它出现）
    human_decision: NotRequired[HumanDecision]  # 人工决策：human_gate 才写（NotRequired 复习 L3.2）


# ---- 节点：纯「读状态 → 返回更新」的函数，不碰任何共享变量 ----


def parse_advice_text(text: str) -> Advice | None:
    """把一段文本解析成 Advice；解析不了返回 None（恢复侧脚本也用它从暂停点反推单据）。"""
    try:
        return Advice.model_validate_json(text.strip())
    except ValueError:
        return None


def parse_last_advice(state: ClaimState) -> Advice | None:
    """把最后一条 AI 消息解析成 Advice；解析不了返回 None（路由与 finalize 共用）。"""
    return parse_advice_text(state["messages"][-1].content)


def make_reviewer(model: Runnable):
    """reviewer 节点工厂：把当前消息史全量发给模型（无状态协议——恢复后重进也一样全量重发）。"""

    async def reviewer(state: ClaimState) -> dict:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response], "events": ["reviewer"]}

    return reviewer


async def tools_node(state: ClaimState) -> dict:
    """tools 节点：遍历 tool_calls、分发到注册表、回喂 ToolMessage（L3.2 原样延续）。"""
    results: list[dict] = []
    for call in state["messages"][-1].tool_calls:
        func = TOOL_REGISTRY.get(call["name"])
        if func is None:
            content = json.dumps({"error": f"unknown_tool: {call['name']}"}, ensure_ascii=False)
        else:
            content = json.dumps(func(**call["args"]), ensure_ascii=False)  # 工具真实执行
        results.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    return {"messages": results, "events": ["tools"]}


def route_after_reviewer(state: ClaimState) -> Literal["tools", "human_gate", "finalize"]:
    """条件边函数（L3.2 的两路扩成三路）：

    有 tool_calls 继续行动；给出 ESCALATE 建议单就送人审门；其他建议单直接收束。
    """
    if state["messages"][-1].tool_calls:
        return "tools"
    advice = parse_last_advice(state)
    if advice is not None and advice.decision == "ESCALATE":
        return "human_gate"
    return "finalize"


async def human_gate(state: ClaimState) -> dict:
    """人审门：本课的核心节点——interrupt() 在这里把图摁停。

    第一次执行：interrupt(payload) 抛 GraphInterrupt → pregel 捕获 → 图暂停、
    payload 连同状态落盘 → 本节点到此为止（下面的 return 一行都没跑到）。
    恢复重执行：同一节点从头再跑，interrupt() 不再抛、返回 Command(resume=) 的值
    → 人工决策写进状态、以 user 消息回喂模型 → 回边进 reviewer 出最终建议单。
    """
    advice = parse_last_advice(state)
    if advice is None:
        raise ValueError("human_gate 只应在 reviewer 给出 ESCALATE 建议单后到达")
    decision = interrupt({"claim_id": advice.claim_id, "reason": advice.reason})
    return {
        "messages": [
            {
                "role": "user",
                "content": (f"人工审批结果：{decision}（approve=放行，deny=拒绝）。请按系统提示输出最终建议单 JSON。"),
            }
        ],
        "events": ["human_gate"],
        "human_decision": decision,
    }


async def finalize(state: ClaimState) -> dict:
    """finalize 节点：解析最终回答 + 合并人工决策，出口是 ReviewOutcome（边界 schema）。"""
    advice = parse_last_advice(state)
    if advice is None:
        raise ValueError(f"finalize 收到无法解析的最终回答: {state['messages'][-1].content[:60]!r}")
    human: HumanDecision = state.get("human_decision", "skipped")
    return {"advice": ReviewOutcome(**advice.model_dump(), human=human), "events": ["finalize"]}


def build_graph(model: Runnable, checkpointer: BaseCheckpointSaver[str] | None = None) -> CompiledStateGraph:
    """装配整张图：L3.2 的 7 行装配 + human_gate 一节点一回边 + compile(checkpointer=...)。"""
    builder = StateGraph(ClaimState)
    builder.add_node("reviewer", make_reviewer(model))
    builder.add_node("tools", tools_node)
    builder.add_node("human_gate", human_gate)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "reviewer")
    builder.add_conditional_edges("reviewer", route_after_reviewer)  # 三路：tools | human_gate | finalize
    builder.add_edge("tools", "reviewer")  # 回边成环：ReAct 循环的图形态（L3.2）
    builder.add_edge("human_gate", "reviewer")  # 回边成环：人工决策回场，模型重新收束
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)  # <-- 今晚的第一行新代码：图从此有记忆


def model_for_url(url: str, api_key: str = "test-key", model: str = "mock-model") -> Runnable:
    """模型客户端：bind_tools 把工具 schema 绑给模型（L3.2 原样延续）。"""
    return ChatOpenAI(base_url=url, api_key=SecretStr(api_key), model=model, max_retries=0, timeout=10).bind_tools(
        list(TOOL_REGISTRY.values())
    )


@asynccontextmanager
async def open_saver(db_path: str) -> AsyncIterator[AsyncSqliteSaver]:
    """打开（或创建）checkpoint 数据库——@asynccontextmanager 是 L1.7 的 with 语义复课。

    两个进程各自 open 同一个文件，就是「共享记忆」的全部秘密；连接用完自动关
    （aiosqlite 连接不关，进程会挂住不退出——AsyncSqliteSaver 文档的原文警告）。

    serde 白名单：状态里的 advice 键是 Pydantic 对象（ReviewOutcome），会被整只序列化进
    db、恢复时再 import 回来——默认放行但每次反序列化告警；显式登记类型是生产纪律
    （对照 Java 反序列化白名单：跨进程读回来的对象类型要锁死，防 schema 漂移与注入）。
    """
    async with aiosqlite.connect(db_path) as conn:
        yield AsyncSqliteSaver(conn, serde=JsonPlusSerializer(allowed_msgpack_modules=[Advice, ReviewOutcome]))


def initial_messages(claim_id: str) -> list[dict]:
    """入口消息：system 规则 + user 单据摘要（L3.2 原样延续）。"""
    view = mock_tools.claim_view(claim_id)
    brief = (
        f"请审查报销单 {view['id']}（{view['submitter']}，{view['purpose']}）。\n"
        f"明细（分）：{view['items_cents']}，总额 {view['total_cents']} 分；"
        f"部门 {view['dept']}；关联发票 {view['invoice_ids']}。\n"
        "请先用工具核实预算与发票，再输出建议单 JSON。"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": brief},
    ]


def post_human_advice(expected: Advice, human: Literal["approve", "deny"]) -> Advice:
    """人审后的最终建议单（离线剧本的第三轮台词生成器；真实端点下这轮由模型自己出）。

    approve→APPROVE/PASS；deny→REJECT/REJECT:HUMAN_DENIED（REJECT:<原因> 枚举风格纪律）。
    remaining_cents 仍是 check_budget 的镜像（预算不因人工否决而变化）。
    """
    if human == "deny":
        return Advice(
            claim_id=expected.claim_id,
            decision="REJECT",
            reason="REJECT:HUMAN_DENIED",
            remaining_cents=expected.remaining_cents,
        )
    return Advice(
        claim_id=expected.claim_id,
        decision="APPROVE",
        reason="PASS",
        remaining_cents=expected.remaining_cents,
    )


def thread_config(thread_id: str) -> RunnableConfig:
    """checkpointer 的取货凭证：thread_id 是唯一要带的钥匙（recursion_limit 照旧兜底）。"""
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}


async def run_review(claim_id: str, human: Literal["approve", "deny"] = "approve") -> ReviewOutcome:
    """本课统一出口：非 ESCALATE 单一跑到底（human="skipped"）；ESCALATE 单在人审门
    暂停后，按 human 代行人工恢复（真实的人工恢复在 demo_resume.py 的第二个进程里）。

    剧本：ESCALATE 单三份（两轮审查 + 一轮人审后收束），非 ESCALATE 单两份；
    实测 ep.requests：ESCALATE 单恰好 3 次、非 ESCALATE 单恰好 2 次。
    """
    mock_tools.CALL_LOG.clear()
    first_turn, advice_json, expected = review_rules.script_for(claim_id)
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "checkpoint.sqlite3")
        with MockLLMEndpoint() as ep:
            ep.script_tool_calls(first_turn)
            ep.script_text(advice_json)
            if expected.decision == "ESCALATE":
                ep.script_text(post_human_advice(expected, human).model_dump_json())
            async with open_saver(db) as saver:
                graph = build_graph(model_for_url(ep.url), checkpointer=saver)
                cfg = thread_config(f"review-{claim_id}")
                result: dict = await graph.ainvoke({"messages": initial_messages(claim_id)}, cfg)
                if "advice" not in result:  # 图在人审门暂停——结果里还没有 advice 键
                    result = await graph.ainvoke(Command(resume=human), cfg)  # 人工决策注入
    final: ReviewOutcome = result["advice"]
    return final
