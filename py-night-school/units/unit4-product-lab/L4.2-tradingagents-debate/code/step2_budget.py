"""Step2 双预算轴实测：模型调用预算（本课改造二）vs superstep 预算（recursion_limit）。

四段演示（离线剧本，全程 mock 端点）：
1) 不限预算（max_llm_calls=None，默认）：全图 9 次调用，quick 7 + deep 2；
2) cap=9（恰好够）：照常完成，used=9——预算不咬人时零感知；
3) cap=5（中途烧穿）：BudgetExceeded 响亮抛出，used=5——烧在风险辩论段，
   已花的 5 次恰好等于 cap（预算检查在放行前，不超卖）；
4) 另一条轴：recursion_limit=4（其余不限）→ GraphRecursionError——数的是 superstep，
   「政策工具/清理上下文」这种不调模型的节点照样烧步数；两条轴各管各的，缺一不可。

对版：产品的 max_recur_limit=100（default_config.py）只有第 4 条轴；模型调用预算是
本课对照 L2.3 AgentBudgetExceeded 补上的第 2 条轴（讲义 §2.5）。
"""

from __future__ import annotations

import asyncio

from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from pydantic import SecretStr

import demo
import policy_tools
from budget import BudgetExceeded, LLMCallBudget
from config import AppealConfig
from graph import RECURSION_LIMIT, build_appeal_graph, initial_state
from mock_endpoint import MockLLMEndpoint


def _chat(url: str, model: str) -> ChatOpenAI:
    return ChatOpenAI(base_url=url, api_key=SecretStr("test-key"), model=model, max_retries=0, timeout=10)


async def run_with(cap: int | None, recursion_limit: int = RECURSION_LIMIT) -> tuple[dict, LLMCallBudget, int, int]:
    """起 quick/deep 两个 mock 端点跑全图，返回（终态, 预算, quick 请求数, deep 请求数）。"""
    cfg = AppealConfig(max_llm_calls=cap)
    budget = LLMCallBudget(cap)
    with (
        MockLLMEndpoint(model=cfg.quick_model) as ep_quick,
        MockLLMEndpoint(model=cfg.deep_model) as ep_deep,
    ):
        demo.script_endpoint(ep_quick, ep_deep)
        analyst = budget.wrap(_chat(ep_quick.url, cfg.quick_model).bind_tools([policy_tools.lookup_policy]))
        quick = budget.wrap(_chat(ep_quick.url, cfg.quick_model))
        deep = budget.wrap(_chat(ep_deep.url, cfg.deep_model))
        graph = build_appeal_graph(cfg, analyst, quick, deep)
        state = await graph.ainvoke(
            initial_state(demo.CLAIM_ID, demo.appeal_brief(demo.CLAIM_ID)),
            config={"recursion_limit": recursion_limit},
        )
        return state, budget, len(ep_quick.requests), len(ep_deep.requests)


async def main() -> None:
    print("== Step2 双预算轴：模型调用预算 vs superstep 预算 ==")

    print("[1] max_llm_calls=None（不限，默认配置）")
    state, budget, quick_n, deep_n = await run_with(None)
    print(f"  完成: verdict={state['final'].verdict}, cap={state['final'].capped_amount_cents} 分")
    print(f"  调用: quick {quick_n} + deep {deep_n} = {budget.used} 次（预算没咬人，零感知）")

    print("[2] cap=9（恰好够：2 分析师 + 2 辩论 + 3 风险 + 1 裁决 + 1 终审）")
    state, budget, _quick_n, _deep_n = await run_with(9)
    print(f"  完成: verdict={state['final'].verdict}；budget.used={budget.used}——不超卖也不预留")

    print("[3] cap=5（中途烧穿）")
    try:
        await run_with(5)
        print("  异常：竟然跑完了？")
    except BudgetExceeded as exc:
        print(f"  {type(exc).__name__}: {exc}")
        print("  烧穿点: 第 6 次调用（风险辩论第 1 方发言被拒）——预算检查在放行前，已花的恰好 = cap")

    print("[4] 另一条轴：recursion_limit=4（模型调用不限）")
    try:
        await run_with(None, recursion_limit=4)
        print("  异常：竟然跑完了？")
    except GraphRecursionError as exc:
        print(f"  {type(exc).__name__}: {str(exc).splitlines()[0]}")
        print("  口径差: superstep 数到 4 就停——「政策工具/清理上下文」不调模型也烧步数；")
        print("          这条轴防死环，模型调用预算防账单，两条轴缺一不可")


if __name__ == "__main__":
    asyncio.run(main())
