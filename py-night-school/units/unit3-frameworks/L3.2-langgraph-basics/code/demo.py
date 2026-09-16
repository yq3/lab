"""L3.2 同题 demo：用 langgraph 的 StateGraph 装报销单审查 agent（Unit 3 统一出口 run_review）。

图结构（教学版手写装配，不用 prebuilt——L3.4 才读它）：

    START → reviewer ──(条件边：最后一条消息有 tool_calls？)──→ tools ──→ reviewer（回边成环）
                    └─────(无 tool_calls)──────────────────→ finalize → END

三条设计纪律（每条都对照 Unit 2 的 mini-agent）：
- 状态是节点间唯一的通信媒介：节点不共享局部变量，返回 dict 作为状态更新——
  L2.3 手写的 messages.append 在这里变成 messages 键上的 add_messages reducer；
- 合并 vs 覆盖由「类型注解」声明：messages/events 用 Annotated reducer 合并（append-only），
  advice 无 reducer（LastValue 覆盖语义，且只有 finalize 写它）；
- 离线确定性：模型客户端指向 MockLLMEndpoint（test-key / mock-model），
  review_rules.script_for 预生成两轮台词（第 1 轮并行调两工具、第 2 轮回 Advice JSON 文本）。
  模型调用轮数以 ep.requests 实测为准：每单恰好 2 次 HTTP 请求。
"""

from __future__ import annotations

import json
import operator
from collections.abc import Callable
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import SecretStr

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

# 与 review_rules 同源的审查规则（真实端点模式下它就是 system 提示；离线模式下是替身决策函数）
SYSTEM_PROMPT = """你是报销单审查助手。审查规则（先命中先停）：
1) 明细含非正数金额 → ESCALATE / REJECT:INVALID_AMOUNT
2) 任一明细 > 5000 分 → REJECT / REJECT:ITEM_OVER_LIMIT
3) 关联发票校验未过 → REJECT / REJECT:INVOICE_INVALID
4) 总额 > 部门剩余预算 → REJECT / REJECT:BUDGET_EXCEEDED
5) 以上全不中 → APPROVE / PASS
先用工具核实部门预算与发票校验，最后一条消息只输出建议单 JSON
（claim_id / decision / reason / remaining_cents 四字段，金额单位分）。"""

# 工具注册表：框架绑定只到这里——mock_tools 本体不 import 任何框架（四课对版）
TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "check_budget": mock_tools.check_budget,
    "verify_invoice": mock_tools.verify_invoice,
}

RECURSION_LIMIT = 8  # 硬终止预算（对照 L2.3 的 max_turns：宁可小了调大，不要大了调小）


class ClaimState(TypedDict):
    """图状态：节点间唯一的通信媒介（对照 L2.3 的 messages 局部变量 + AgentResult）。

    - messages / events 带 Annotated reducer：合并语义，多节点追加互不覆盖；
    - advice 无 reducer：覆盖语义（LastValue），全图只有 finalize 写它；
    - NotRequired：入口状态没有 advice 这个键——第一个写它的节点才让它出现。
    """

    messages: Annotated[list, add_messages]  # 消息史 append-only（add_messages 按 id 去重合并）
    events: Annotated[list[str], operator.add]  # 审计流水：每个节点登记自己的名字
    advice: NotRequired[Advice]  # 最终建议单（Pydantic 模型可以直接当状态字段类型，L1.3）


# ---- 节点：纯「读状态 → 返回更新」的函数，不碰任何共享变量 ----


def make_reviewer(model: Runnable):
    """reviewer 节点工厂：把当前消息史全量发给模型（无状态协议，L2.1 §2.2 的复习）。"""

    async def reviewer(state: ClaimState) -> dict:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response], "events": ["reviewer"]}

    return reviewer


async def tools_node(state: ClaimState) -> dict:
    """tools 节点（手写版）：遍历 tool_calls、分发到注册表、回喂 ToolMessage。

    对照 L2.2 的注册表分发：查不到的工具名回喂 error JSON 而不是 raise——
    错误是给模型的修复指令，这条纪律在图引擎里原样成立。
    """
    results: list[dict] = []
    for call in state["messages"][-1].tool_calls:
        func = TOOL_REGISTRY.get(call["name"])
        if func is None:
            content = json.dumps({"error": f"unknown_tool: {call['name']}"}, ensure_ascii=False)
        else:
            content = json.dumps(func(**call["args"]), ensure_ascii=False)  # 工具真实执行
        results.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    return {"messages": results, "events": ["tools"]}


def route_after_reviewer(state: ClaimState) -> Literal["tools", "finalize"]:
    """条件边函数：读最后一条消息，有 tool_calls 继续行动，没有就收束。

    返回值是下一个节点名——L2.3 循环里的 `if not tool_calls: return` 被替换成这张路由表。
    """
    return "tools" if state["messages"][-1].tool_calls else "finalize"


async def finalize(state: ClaimState) -> dict:
    """finalize 节点：解析最终回答为 Advice（边界上的 schema 由 Pydantic 把守，L2.4）。"""
    text = state["messages"][-1].content
    return {"advice": Advice.model_validate_json(text.strip()), "events": ["finalize"]}


def build_graph(model: Runnable) -> CompiledStateGraph:
    """装配整张图：节点 + 边 + 条件边 + START/END，compile 产出可执行单元。"""
    builder = StateGraph(ClaimState)
    builder.add_node("reviewer", make_reviewer(model))
    builder.add_node("tools", tools_node)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "reviewer")  # START 是哨兵节点名，不是字符串随意值
    builder.add_conditional_edges("reviewer", route_after_reviewer)  # 路由函数返回节点名
    builder.add_edge("tools", "reviewer")  # 回边成环：ReAct 循环的图形态
    builder.add_edge("finalize", END)
    return builder.compile()


def model_for_url(url: str, api_key: str = "test-key", model: str = "mock-model") -> Runnable:
    """模型客户端：bind_tools 把工具 schema 绑给模型（框架替你生成 JSON Schema，L2.2 手写的对照）。"""
    return ChatOpenAI(base_url=url, api_key=SecretStr(api_key), model=model, max_retries=0, timeout=10).bind_tools(
        list(TOOL_REGISTRY.values())
    )


def initial_messages(claim_id: str) -> list[dict]:
    """入口消息：system 规则 + user 单据摘要（与 review_rules 剧本生成器同源的单据视图）。"""
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


async def run_review(claim_id: str) -> Advice:
    """Unit 3 统一出口：离线确定性跑完整张图，返回结构化建议单。

    剧本来自 review_rules.script_for（第 1 轮并行调用两个工具、第 2 轮回 Advice JSON）；
    实测 ep.requests：每单恰好 2 次模型请求（reviewer 被执行两轮）。
    """
    mock_tools.CALL_LOG.clear()
    first_turn, advice_json, _expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        graph = build_graph(model_for_url(ep.url))
        result = await graph.ainvoke(
            {"messages": initial_messages(claim_id)},
            config={"recursion_limit": RECURSION_LIMIT},
        )
    final: Advice = result["advice"]
    return final
