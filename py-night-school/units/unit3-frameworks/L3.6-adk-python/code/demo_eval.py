"""Step 5：eval 工具链的最小离线演示——全家桶里「测试属于框架」的那一层。

adk 的评估核心抽象只有一对（evaluation/eval_case.py）：
  actual Invocation   —— 真实跑出来的（user 消息 / 工具轨迹 / 最终回答）
  expected Invocation —— 人工标注的期望
指标（eval_metrics.py）分两族：
  确定性的：工具轨迹比对（EXACT / IN_ORDER / ANY_ORDER）、final_response_match——不需要 LLM；
  LLM-as-judge 的：轨迹质量、幻觉、rubric 评分——需要裁判模型（加餐，本课离线不跑）。

本 demo 用确定性的 TrajectoryEvaluator：真实离线跑一遍 agent，把事件流里的
工具调用收集成 actual，与 review_rules 预生成的期望比对打分——零 key、零裁判。

运行：uv run python code/demo_eval.py
"""

from __future__ import annotations

import asyncio

from google.adk.evaluation.eval_case import IntermediateData, Invocation
from google.adk.evaluation.eval_metrics import EvalMetric, ToolTrajectoryCriterion
from google.adk.evaluation.trajectory_evaluator import TrajectoryEvaluator
from google.genai import types as genai_types

import review_rules
from adk_review import ask, build_reviewer, build_runner, new_session
from demo import run_review
from mock_endpoint import MockLLMEndpoint

CLAIM_ID = "CLM-2026-0003"


async def collect_actual() -> Invocation:
    """离线真跑一遍 agent，把事件流折叠成一个 actual Invocation。"""
    first_turn, final_json, _expected = review_rules.script_for(CLAIM_ID)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(final_json)
        runner = build_runner(build_reviewer(ep))
        session_id = await new_session(runner)
        question = f"请审查报销单 {CLAIM_ID}"
        events = []
        async for event in ask(runner, session_id, question):
            events.append(event)
    tool_uses = []
    final_response = None
    for event in events:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.function_call:
                tool_uses.append(part.function_call)
        if event.is_final_response() and event.content.parts[0].text:
            final_response = event.content
    user_content = genai_types.Content(role="user", parts=[genai_types.Part(text=question)])
    return Invocation(
        user_content=user_content,
        final_response=final_response,
        intermediate_data=IntermediateData(tool_uses=tool_uses),
    )


def expected_invocation(question: str, first_turn: list[dict]) -> Invocation:
    """把剧本第 1 轮的工具调用包装成 expected Invocation（人工标注的角色）。"""
    return Invocation(
        user_content=genai_types.Content(role="user", parts=[genai_types.Part(text=question)]),
        intermediate_data=IntermediateData(
            tool_uses=[
                genai_types.FunctionCall(id=call["id"], name=call["name"], args=call["arguments"])
                for call in first_turn
            ]
        ),
    )


async def main() -> None:
    question = f"请审查报销单 {CLAIM_ID}"
    first_turn, _final_json, _expected = review_rules.script_for(CLAIM_ID)
    actual = await collect_actual()
    print("== actual 工具轨迹（真实跑出来的） ==")
    assert isinstance(actual.intermediate_data, IntermediateData)  # 收窄 Union（还有事件流形态）
    for call in actual.intermediate_data.tool_uses:
        print(f"  {call.name}({dict(call.args or {})})")

    metric = EvalMetric(
        metric_name="tool_trajectory",
        criterion=ToolTrajectoryCriterion(match_type=ToolTrajectoryCriterion.MatchType.ANY_ORDER, threshold=1.0),
    )
    evaluator = TrajectoryEvaluator(eval_metric=metric)

    result = evaluator.evaluate_invocations(
        actual_invocations=[actual],
        expected_invocations=[expected_invocation(question, first_turn)],
    )
    print(f"== 与剧本期望比对: score={result.overall_score} status={result.overall_eval_status}")

    # 反例：把期望的部门参数标错（本单实际属于 DEV，标成 SALES），同一 actual 应得 0 分
    wrong_turn = [dict(first_turn[0], arguments={"dept": "SALES"})]
    result_bad = evaluator.evaluate_invocations(
        actual_invocations=[actual],
        expected_invocations=[expected_invocation(question, wrong_turn)],
    )
    print(f"== 标错部门参数的期望: score={result_bad.overall_score} status={result_bad.overall_eval_status}")
    print()
    print("== 附：四题全量回归（test_contract 同款口径，但用 eval 的眼光看） ==")
    for claim in ("CLM-2026-0001", "CLM-2026-0002", "CLM-2026-0003", "CLM-2026-0004"):
        advice = await run_review(claim)
        print(f"  {claim} -> {advice.decision:8} {advice.reason}")
    print()
    print("诚实边界：完整的 `adk eval` 走 AgentEvaluator + .test.json eval set，")
    print("LLM-as-judge 指标还要裁判模型——那是加餐（README Step 5 的动手说明）。")


if __name__ == "__main__":
    asyncio.run(main())
