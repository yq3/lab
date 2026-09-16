# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""guardrail 改造：给报销单审查入口加一道输入护栏，拦「不存在的单号」。

改造前：run_unguarded（given，能跑）——任何单号都原样发给模型，幻觉单号会换来
一本正经的编造结论；你要做的两件事（两个 TODO 区）：
  A. claim_id_guardrail：用 @input_guardrail 装饰的护栏函数——用 given 的
     _extract_claim_id 抽单号，不在 mock 用例表（或根本没写单号）→ tripwire_triggered=True；
     output_info 记 {"claim_id": 抽到的单号或 None, "known": 是否在表内}；
  B. run_guarded：与 run_unguarded 同构，但 Agent 多挂 input_guardrails=[你的护栏]，
     已知单号才预排台词（坏单号被拦在模型调用之前，台词用不上）。

完成判据（exercises/test_ex2.py，4 个测试）：
  - 好单号（CLM-2026-0002 的消息）：护栏放行，返回 (Advice, 2)——结论与用例表一致；
  - 坏单号 CLM-2026-9999 的消息：抛框架的 InputGuardrailTripwireTriggered，且
    异常的 guardrail_result.output.output_info == {"claim_id": "CLM-2026-9999", "known": False}；
  - 不带单号的消息同样绊线（output_info 的 claim_id 为 None）；
  - 护栏函数本体可脱机直调（InputGuardrail.guardrail_function）：
    好单号返回 tripwire_triggered=False 且 output_info 的 known 为 True。

提示：所需顶部 import 在 TODO 注释里点名；讲义 Step 4（demo_guardrail.py）是同构实现——
护栏语义（默认并行赛跑、只有第一个 agent 的输入护栏生效）讲义 §2 有源码路标。
"""

from __future__ import annotations

from typing import Any

from agents import Agent, Runner, function_tool
from agents.models.interface import Model
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

REVIEWER_INSTRUCTIONS = "你是报销单审查员。先用 check_budget 查预算、verify_invoice 校验发票，再按规则出建议单。"


def _extract_claim_id(text: str) -> str | None:
    """从消息里抠 CLM-xxxx-xxxx 单号（护栏的解析器，given——练习重心在护栏不在正则）。"""
    import re

    matched = re.search(r"CLM-\d{4}-\d{4}", text)
    return matched.group(0) if matched else None


def _user_message(text: str) -> str:
    """护栏练习的输入就是一条普通用户消息（单号可能合法、可能不存在）。"""
    return f"请处理这条报销请求：{text}"


def _build_model(ep: MockLLMEndpoint) -> Model:
    return OpenAIChatCompletionsModel(model=ep.model, openai_client=AsyncOpenAI(base_url=ep.url, api_key=ep.api_key))


def _script_if_known(ep: MockLLMEndpoint, message: str) -> None:
    """已知单号才预排台词（工具轮 + 结论文本轮）——坏单号走不到模型，不需要台词。"""
    claim_id = _extract_claim_id(message)
    if claim_id is not None and claim_id in {c["id"] for c in mock_tools.claims_table()}:
        first_turn, final_text, _expected = review_rules.script_for(claim_id)
        ep.script_tool_calls(first_turn)
        ep.script_text(final_text)


async def run_unguarded(message: str) -> tuple[Advice, int]:
    """改造前：没有护栏的入口（能跑）——坏单号也会原样发给模型。"""
    with MockLLMEndpoint() as ep:
        _script_if_known(ep, message)
        agent = Agent(
            name="Reviewer",
            instructions=REVIEWER_INSTRUCTIONS,
            model=_build_model(ep),
            tools=[function_tool(mock_tools.check_budget), function_tool(mock_tools.verify_invoice)],
            output_type=Advice,
        )
        result = await Runner.run(agent, message)
        return result.final_output, len(ep.requests)


def claim_id_guardrail(ctx: object, agent: object, input: str | list[Any]):
    """TODO A：输入护栏——单号必须存在于 mock 用例表（框架回调签名，参数名不能改）。"""
    # TODO(ex2-A): 在本函数上方加 @input_guardrail(name="claim_id_exists") 装饰器
    #   （需要的顶部 import：from agents import input_guardrail；
    #     from agents.guardrail import GuardrailFunctionOutput）。
    #   函数体（input 框架会给 str 或消息 list——str() 归一后抽单号）：
    #   known = 单号在 {c["id"] for c in mock_tools.claims_table()} 里；
    #   return GuardrailFunctionOutput(output_info={"claim_id": ..., "known": known},
    #                                  tripwire_triggered=not known)
    raise NotImplementedError("TODO(ex2-A): 补全 claim_id_guardrail")


async def run_guarded(message: str) -> tuple[Advice, int]:
    """TODO B：带护栏的入口——与 run_unguarded 同构，Agent 多挂 input_guardrails。"""
    # TODO(ex2-B): 与 run_unguarded 唯一的差异：Agent(..., input_guardrails=[claim_id_guardrail])。
    #   返回 (result.final_output, len(ep.requests))；坏单号时框架抛
    #   InputGuardrailTripwireTriggered——不要在这里捕获（上层决定拦下之后怎么办）。
    raise NotImplementedError("TODO(ex2-B): 补全 run_guarded")
