"""L5.1 demo 全程轨迹：四单分演三种形态 + 重规划单的 superstep 细迹（讲义 §3 的实跑产出）。

离线（默认）：MockLLMEndpoint + demo.scripts_for 剧本，行为确定性——events 审计流水、
plan_rejections 轨迹、CALL_LOG 每次完全一致。真实端点（--real）：读 .env 三变量，
同一张图零改动。langsmith 追踪：不设 LANGSMITH_* 环境变量即默认关闭、零外发。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import demo
import graph
import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint


def _brief(message) -> str:  # noqa: ANN001 -- langchain 消息对象，讲义脚本从简
    """把一条消息压成一行轨迹（role + 内容摘要）。"""
    role = type(message).__name__.removesuffix("Message").lower()
    text = str(message.content).replace("\n", " ")
    return f"{role}: {text[:52]}{'…' if len(text) > 52 else ''}"


async def _run_traced(claim_id: str, mode: str) -> tuple[dict, int]:
    """起图并逐 superstep 打印轨迹；返回 (最终 state, 模型请求数)。"""
    mock_tools.CALL_LOG.clear()
    planner_texts, drafter_text = demo.scripts_for(claim_id, mode)
    with MockLLMEndpoint() as ep:
        for text in planner_texts:
            ep.script_text(text)
        ep.script_text(drafter_text)
        compiled = graph.build_graph(demo.model_for_url(ep.url))
        print("== superstep 轨迹（stream_mode='values'，每步给全量状态） ==")
        final: dict = {}
        seen = 0
        async for state in compiled.astream(
            graph.initial_state(claim_id),
            config={"recursion_limit": graph.RECURSION_LIMIT},
            stream_mode="values",
        ):
            final = state
            if not state.get("events"):
                continue  # values 模式的首块是入口状态（还没执行任何节点）
            node = state["events"][-1]  # 审计流水末位 = 刚执行完的节点/事件
            if len(state["messages"]) > seen:
                for message in state["messages"][seen:]:
                    print(f"  [{node:>26}] + {_brief(message)}")
            else:
                print(f"  [{node:>26}] （不新增消息——纯代码节点，只读/只写状态键）")
            seen = len(state["messages"])
        requests = len(ep.requests)
    return final, requests


def _print_rejections(final: dict) -> None:
    rejections = final.get("plan_rejections") or []
    print(f"  plan_rejections 轨迹: {len(rejections)} 次")
    for i, rejection in enumerate(rejections, start=1):
        print(f"    {i}. {rejection.reason_code:<13} {rejection.detail[:58]}")


async def trace_claim(claim_id: str, mode: str) -> None:
    """单据细迹：superstep 逐行 + 拒绝轨迹 + 收口对照。"""
    print(f"== L5.1 固定图：{claim_id}（剧本 {mode}） ==")
    print("图: START → intake → planner → plan_gate ─(valid)→ executor → drafter → submit → END")
    print("                        ↑←─(invalid 未超限：原因回喂)─┘   └─(超限)→ escalate → END\n")
    final, requests = await _run_traced(claim_id, mode)
    _print_rejections(final)
    advice_out: Advice = final["advice"]
    print("\n== 收口 ==")
    if final.get("sent"):
        _expected = review_rules.script_for(claim_id)[2]
        print(f"  advice   : {advice_out.decision} / {advice_out.reason} / 剩余 {advice_out.remaining_cents} 分")
        print(f"  （剧本预期: {_expected.decision} / {_expected.reason} / 剩余 {_expected.remaining_cents} 分）")
    else:
        print(f"  advice   : {advice_out.decision} / {advice_out.reason}（收尾哨兵：未送审、转人工）")
    print(f"  sent     : {final.get('sent')}")
    print(f"  events   : {final['events']}")
    print(f"  CALL_LOG : {mock_tools.CALL_LOG}（check_budget/verify_invoice 真实执行的取证）")
    print(f"  模型请求 : {requests} 次")


async def summary_four() -> None:
    """四单总览：一屏看全三种形态（clean / 重规划 / 超限）。"""
    print("== L5.1 固定图四单总览（离线剧本） ==")
    print(f"剧本排片: {demo.CLAIM_MODES}\n")
    for claim in mock_tools.claims_table():
        claim_id = claim["id"]
        mode = demo.CLAIM_MODES[claim_id]
        final = await demo.run_pipeline(claim_id, mode=mode)
        advice_out: Advice = final["advice"]
        rejections = final.get("plan_rejections") or []
        planner_rounds = final["events"].count("planner")
        print(f"[{claim_id}] {mode:<13} advice={advice_out.decision}/{advice_out.reason}")
        print(f"    sent={final.get('sent')}  拒绝={len(rejections)} 次  planner={planner_rounds} 轮")
        print(f"    CALL_LOG={mock_tools.CALL_LOG}")
        if rejections:
            print(f"    拒绝码序列: {[r.reason_code for r in rejections]}")


def _load_env() -> dict[str, str]:
    """极简 .env 读取（L2.1 env_loader 的迷你版）：KEY=VALUE 行，忽略注释。"""
    env: dict[str, str] = {}
    path = Path(".env")
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.split(" #")[0].strip()
    return env


async def run_real(claim_id: str) -> None:
    """真实端点加餐：同一张图、同一套校验门——planner 台词由真模型自己产。"""
    from langchain_openai import ChatOpenAI  # 加餐路径局部导入，离线主线零感知
    from pydantic import SecretStr

    env = _load_env()
    missing = [k for k in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "MODEL_NAME") if not env.get(k)]
    if missing:
        print(f"缺 .env 变量: {missing}（先 cp .env.example .env 并填写）")
        return
    model = ChatOpenAI(
        base_url=env["OPENAI_BASE_URL"],
        api_key=SecretStr(env["OPENAI_API_KEY"]),
        model=env["MODEL_NAME"],
        max_retries=0,
        timeout=30,
    )
    print(f"== 真实端点（{env['MODEL_NAME']}）跑 {claim_id}：图零改动 ==")
    final = await demo.run_pipeline(claim_id, model=model)
    advice_out: Advice = final["advice"]
    print(f"  advice   : {advice_out.decision} / {advice_out.reason} / 剩余 {advice_out.remaining_cents} 分")
    print(f"  sent     : {final.get('sent')}")
    print(f"  events   : {final['events']}")
    print(f"  工具真实执行: {mock_tools.CALL_LOG}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--real" in sys.argv[1:]:
        asyncio.run(run_real(args[0] if args else "CLM-2026-0001"))
    elif args:
        asyncio.run(trace_claim(args[0], demo.CLAIM_MODES.get(args[0], "clean")))
    else:
        asyncio.run(summary_four())
        print()
        asyncio.run(trace_claim("CLM-2026-0002", "dirty_once"))  # 重规划环的细迹压轴


if __name__ == "__main__":
    main()
