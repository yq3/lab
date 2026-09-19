# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""handoff 改造：把单 agent 审查升级为「审查员 + 人工复核专员」双 agent。

改造前：build_single_agent（given，能跑）——讲义 Step 1 单 agent 版的微缩；
你要做的三件事（三个 TODO 区）：
  A. build_agents：装配双 agent——复核专员 HumanSpecialist（无工具、output_type=Advice、
     带 handoff_description）；审查员在单 agent 版之上多挂 handoffs=[handoff(专员)]；
  B. script_rounds：排离线台词——非 ESCALATE 单与单 agent 版相同（工具轮 + 结论文本轮）；
     ESCALATE 单第 2 轮改为「转交」（script_tool_calls 点名 HANDOFF_TOOL_NAME，
     arguments={}），第 3 轮才是建议单文本（讲义 Step 3 有三轮的 wire 取证）；
  C. run_review：清 CALL_LOG → 起端点 → 造模型 → 排台词 → Runner.run(审查员, 消息) →
     返回 (result.final_output, result.last_agent.name, len(ep.requests))。

完成判据（exercises/test_ex1.py，5 个测试）：
  - 双 agent 结构：专员无工具且 output_type 是 Advice，审查员挂了 handoff；
  - ESCALATE 单（CLM-2026-0003）恰好 3 次模型请求、last_agent=HumanSpecialist——handoff 确实发生；
  - 其余三张单仍是 2 次请求、last_agent=Reviewer——handoff 不是必经之路；
  - 四张单的 decision/reason/remaining_cents 与用例表 expect_* 逐字段一致（契约决策不变）；
  - 每次运行 CALL_LOG 都真实记到 check_budget 与 verify_invoice。

提示：所需顶部 import 在各 TODO 注释里点名（agents 的 handoff/Runner、模型注入两件套）；
讲义 Step 1 的 demo.py 与 Step 3 的 demo_handoff.py 是同构实现，先读再写。
"""

from __future__ import annotations

from agents import Agent, function_tool
from agents.models.interface import Model

import mock_tools
from advice import Advice
from mock_endpoint import MockLLMEndpoint

# 框架从 agent.name 生成转交工具名：transfer_to_ + 名字全小写（驼峰不拆、只压平）——
# 离线剧本必须用这个名字点名，错一个字母就是 ModelBehaviorError: Tool ... not found。
HANDOFF_TOOL_NAME = "transfer_to_humanspecialist"

REVIEWER_INSTRUCTIONS = (
    "你是报销单审查员。先用 check_budget 查预算、verify_invoice 校验发票，"
    "发现明细含非正数金额（脏数据）时，转交人工复核专员。"
)
SPECIALIST_INSTRUCTIONS = "你是人工复核专员：对转来的报销单复核后给出 ESCALATE 建议单。"
SPECIALIST_DESCRIPTION = "处理脏数据等需要人工介入的报销单"


def _user_message(claim_id: str) -> str:
    view = mock_tools.claim_view(claim_id)
    return (
        f"请审查报销单 {view['id']}（提交人 {view['submitter']}，部门 {view['dept']}，"
        f"关联发票 {view['invoice_ids'][0]}，明细分：{view['items_cents']}）。"
    )


def build_single_agent(model: Model) -> Agent:
    """改造前：单 agent 审查员（Runner 串上两轮台词就能跑，demo.py 的微缩版）。"""
    return Agent(
        name="Reviewer",
        instructions=REVIEWER_INSTRUCTIONS,
        model=model,
        tools=[function_tool(mock_tools.check_budget), function_tool(mock_tools.verify_invoice)],
        output_type=Advice,
    )


def build_agents(model: Model) -> tuple[Agent, Agent]:
    """TODO A：双 agent 装配，返回 (审查员, 复核专员)。"""
    # TODO(ex1-A): 先造 HumanSpecialist（name/instructions/handoff_description/model/output_type，
    #   不挂 tools）；再造 Reviewer（单 agent 版的全部 + handoffs=[handoff(specialist)]）。
    #   需要的顶部 import：from agents import handoff
    raise NotImplementedError("TODO(ex1-A): 补全 build_agents")


def script_rounds(ep: MockLLMEndpoint, claim_id: str) -> None:
    """TODO B：排离线台词——按预期结论分支：ESCALATE 多一轮「转交」。"""
    # TODO(ex1-B): import review_rules；script_for(claim_id) 拿 (工具轮台词, 结论文本, 预期 Advice)；
    #   所有单：第 1 轮 ep.script_tool_calls(工具轮)；
    #   ESCALATE 单：第 2 轮 ep.script_tool_calls([{"id": "call_handoff", "name": HANDOFF_TOOL_NAME,
    #   "arguments": {}}])；最后 ep.script_text(结论文本)。
    raise NotImplementedError("TODO(ex1-B): 补全 script_rounds")


async def run_review(claim_id: str) -> tuple[Advice, str, int]:
    """TODO C：跑双 agent 审查，返回 (最终 Advice, last_agent 名字, 模型请求次数)。"""
    # TODO(ex1-C): mock_tools.CALL_LOG.clear() → with MockLLMEndpoint() as ep:
    #   造模型（讲义 Step 1 的 _build_model 同构：OpenAIChatCompletionsModel(model=ep.model,
    #   openai_client=AsyncOpenAI(base_url=ep.url, api_key=ep.api_key))）→ build_agents(model) →
    #   script_rounds(ep, claim_id) → result = await Runner.run(审查员, _user_message(claim_id)) →
    #   return (result.final_output, result.last_agent.name, len(ep.requests))
    #   需要的顶部 import：from agents import Runner；
    #   from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel；from openai import AsyncOpenAI
    raise NotImplementedError("TODO(ex1-C): 补全 run_review")
