"""实验④：InputGuardrail 输入护栏——拦截「幻觉单号」。

场景：有人（或上游系统）把单号写错了——CLM-2026-9999 不存在。没有护栏时，这个单号
会一路发给模型，模型可能一本正经地编一个结论（LLM 幻觉的典型入口）。
护栏是确定性代码：单号不在 mock 用例表 → tripwire 触发 → 框架抛
InputGuardrailTripwireTriggered，模型一次都不用调。

两个框架语义要记牢（§2 展开，源码都在路标里）：
  1. 默认 run_in_parallel=True：护栏与第一轮模型调用**并行赛跑**，护栏赢了就取消模型
     任务——本实验实测模型请求数为 0，但这是赛跑结果不是合同；要「绝不发出模型调用」
     的硬保证，构造护栏时传 run_in_parallel=False（先跑护栏再起 agent）。
  2. 护栏函数只是普通函数（同步异步都行）——它当然也可以是一次模型调用（官方文档的
     guardrail agent 模式），成本观与 Servlet Filter 完全不同（§5 坑位的入口）。
"""

from __future__ import annotations

import asyncio

from agents import Agent, Runner, function_tool, input_guardrail, set_tracing_disabled
from agents.exceptions import InputGuardrailTripwireTriggered
from agents.guardrail import GuardrailFunctionOutput
from agents.items import TResponseInputItem
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

import mock_tools
import review_rules
from advice import Advice
from demo import INSTRUCTIONS, _user_message
from mock_endpoint import MockLLMEndpoint

set_tracing_disabled(True)
BAD_CLAIM_ID = "CLM-2026-9999"  # 形如真单号、但不在用例表里——幻觉单号


def extract_claim_id(text: str) -> str | None:
    """从 user 消息里抠出 CLM-xxxx-xxxx 单号（护栏的解析器，与框架无关）。"""
    import re

    matched = re.search(r"CLM-\d{4}-\d{4}", text)
    return matched.group(0) if matched else None


@input_guardrail(name="claim_id_exists")
def claim_id_exists_guardrail(
    ctx: object,
    agent: object,
    input: str | list[TResponseInputItem],  # 框架回调签名
) -> GuardrailFunctionOutput:
    """输入护栏：单号必须存在于 mock 用例表，否则绊线。"""
    text = input if isinstance(input, str) else str(input)
    claim_id = extract_claim_id(text)
    known_ids = {c["id"] for c in mock_tools.claims_table()}
    tripwire = claim_id is None or claim_id not in known_ids
    return GuardrailFunctionOutput(
        output_info={"claim_id": claim_id, "known": not tripwire},
        tripwire_triggered=tripwire,
    )


def _build_agent(ep: MockLLMEndpoint) -> Agent[None]:
    model = OpenAIChatCompletionsModel(model=ep.model, openai_client=AsyncOpenAI(base_url=ep.url, api_key=ep.api_key))
    return Agent(
        name="Reviewer",
        instructions=INSTRUCTIONS,
        model=model,
        tools=[function_tool(mock_tools.check_budget), function_tool(mock_tools.verify_invoice)],
        output_type=Advice,
        input_guardrails=[claim_id_exists_guardrail],  # 只在链路第一个 agent 上生效
    )


async def _run(ep: MockLLMEndpoint, message: str) -> tuple[Advice, int]:
    """好单号路径：预排工具轮+结论轮台词再跑（坏单号走不到模型，无需台词）。"""
    claim_id = extract_claim_id(message)
    assert claim_id is not None
    first_turn, final_text, _expected = review_rules.script_for(claim_id)
    ep.script_tool_calls(first_turn)
    ep.script_text(final_text)
    result = await Runner.run(_build_agent(ep), message)
    return result.final_output, len(ep.requests)


def main() -> None:
    print(f"== 坏单号 {BAD_CLAIM_ID}（护栏应拦） ==")
    with MockLLMEndpoint() as ep:
        ep.script_text("不应被消费")  # 护栏赢了这行台词就用不上
        try:
            bad_message = f"请审查报销单 {BAD_CLAIM_ID}（部门 SALES，关联发票 INV-2026-0001）。"
            asyncio.run(Runner.run(_build_agent(ep), bad_message))
            print("异常：护栏没拦住！")
        except InputGuardrailTripwireTriggered as exc:
            info = exc.guardrail_result.output.output_info
            print(f"InputGuardrailTripwireTriggered: tripwire={info}")
            print(f"模型请求数: {len(ep.requests)}（护栏与模型并行赛跑，护栏先到即取消模型任务）")

    print("\n== 好单号 CLM-2026-0001（护栏放行，正常审查） ==")
    with MockLLMEndpoint() as ep:
        mock_tools.CALL_LOG.clear()
        advice, requests = asyncio.run(_run(ep, _user_message("CLM-2026-0001")))
        print(f"{advice.decision} / {advice.reason}（模型请求 {requests} 次，工具 {mock_tools.CALL_LOG}）")

    print("\n== 不带单号的消息（护栏同样绊线——宁拒收不猜） ==")
    with MockLLMEndpoint() as ep:
        ep.script_text("不应被消费")
        try:
            asyncio.run(Runner.run(_build_agent(ep), "帮我把昨天的报销都过一遍。"))
            print("异常：护栏没拦住！")
        except InputGuardrailTripwireTriggered as exc:
            print(f"InputGuardrailTripwireTriggered: output_info={exc.guardrail_result.output.output_info}")


if __name__ == "__main__":
    main()
