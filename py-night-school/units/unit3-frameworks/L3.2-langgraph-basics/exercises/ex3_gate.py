# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""subgraph 改造：模型 + 工具打包成子图，外层 precheck 拦非法单号直接短路。

考察点：编译好的图可以 add_node 直接挂进外层图（图即节点，对照 Java 工作流的子流程）；
条件边按 claim_id 是否在 mock 表里路由（review 子图 | deny 拒付）；
deny 短路不调模型——测试会断言 mock 端点的请求数为 0（剧本备好了却永远不被消费）。

完成判据：uv run pytest exercises/test_ex3.py 全绿——两个测试：
  合法单 CLM-2026-0004 走完整审查：Advice 与规则表预期全等 + 恰好 2 次模型请求 + 工具真实执行；
  非法单 CLM-2026-9999 被 precheck 拦截：ESCALATE / REJECT:CLAIM_NOT_FOUND + 0 次模型请求。
TODO 所需的顶部 import：
  from langgraph.graph import END, START, StateGraph
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import SecretStr

import demo
import mock_tools
from advice import Advice


class ReviewState(TypedDict):
    """子图状态：审查循环只关心消息史与最终建议单（刻意不含审计键——见讲义 Step5 的取舍说明）。"""

    messages: Annotated[list, add_messages]
    advice: NotRequired[Advice]


class GateState(TypedDict):
    """外层状态：claim_id 由入口带入，审查结论经 advice 流出。"""

    claim_id: str
    messages: Annotated[list, add_messages]
    advice: NotRequired[Advice]


# ---- 子图节点（与讲义 demo.py 同构，给定） ----


def make_reviewer(model: Runnable):
    async def reviewer(state: ReviewState) -> dict:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response]}

    return reviewer


async def tools_node(state: ReviewState) -> dict:
    tool_funcs: dict[str, Callable[..., dict]] = dict(demo.TOOL_REGISTRY)
    results: list[dict] = []
    for call in state["messages"][-1].tool_calls:
        func = tool_funcs.get(call["name"])
        if func is None:
            content = json.dumps({"error": f"unknown_tool: {call['name']}"}, ensure_ascii=False)
        else:
            content = json.dumps(func(**call["args"]), ensure_ascii=False)  # 工具真实执行
        results.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    return {"messages": results}


def route_after_reviewer(state: ReviewState) -> Literal["tools", "finalize"]:
    return "tools" if state["messages"][-1].tool_calls else "finalize"


async def finalize(state: ReviewState) -> dict:
    return {"advice": Advice.model_validate_json(state["messages"][-1].content.strip())}


# ---- 外层节点（给定）：precheck 纯函数、deny 短路拒付 ----


async def precheck(state: GateState) -> dict:
    """预检节点：纯函数、不写状态——「单号是否在册」的路由判断在条件边函数里（也是纯函数）。"""
    return {}  # 空更新是合法的：这个节点存在的意义是挂条件边的锚点（也可在这里写审计标志）


def route_after_precheck(state: GateState) -> Literal["review", "deny"]:
    known = any(claim["id"] == state["claim_id"] for claim in mock_tools.claims_table())
    return "review" if known else "deny"


async def deny(state: GateState) -> dict:
    """拒付路径：非法单号转人审，不调模型、不调工具。"""
    return {
        "advice": Advice(
            claim_id=state["claim_id"],
            decision="ESCALATE",
            reason="REJECT:CLAIM_NOT_FOUND",
            remaining_cents=0,
        )
    }


# ---- 模型与入口消息（给定） ----


def model_for(url: str) -> Runnable:
    """模型客户端指向 mock 端点（与讲义 demo.model_for_url 同款，收窄为只收 url）。"""
    return ChatOpenAI(
        base_url=url, api_key=SecretStr("test-key"), model="mock-model", max_retries=0, timeout=10
    ).bind_tools(list(demo.TOOL_REGISTRY.values()))


def initial_messages(claim_id: str) -> list[dict]:
    """入口消息：不查 mock 表——对任何单号（含非法单号）都成立。"""
    return [
        {"role": "system", "content": demo.SYSTEM_PROMPT},
        {"role": "user", "content": f"请审查报销单 {claim_id}。"},
    ]


# ---- 装配（你的 TODO） ----


def build_review_subgraph(model: Runnable) -> CompiledStateGraph:
    """把 reviewer/tools/finalize 打包成一个子图（与讲义 demo.build_graph 同构）。"""
    # TODO(ex3): StateGraph(ReviewState) → add_node 挂三个节点 → START 到 reviewer →
    #   reviewer 之后挂条件边（route_after_reviewer）→ tools 回 reviewer → finalize 到 END →
    #   compile() 返回（顶部 import 见文件 docstring）
    raise NotImplementedError("TODO(ex3): 装配子图")


def build_gate(model: Runnable) -> CompiledStateGraph:
    """外层闸门图：START → precheck →（条件边）→ review 子图 | deny → END。"""
    # TODO(ex3): StateGraph(GateState) → add_node 挂 precheck 与 deny；review 节点把
    #   build_review_subgraph(model) 的编译产物直接当第二个参数（图即节点）；precheck 之后挂
    #   条件边（route_after_precheck，返回 "review" / "deny" 两个节点名）；review 与 deny 都到 END
    raise NotImplementedError("TODO(ex3): 装配外层闸门图")
