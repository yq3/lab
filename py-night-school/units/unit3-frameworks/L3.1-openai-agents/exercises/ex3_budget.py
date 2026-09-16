# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""max_turns 预算改造：执念模型 × 小预算 → 框架的 MaxTurnsExceeded。

剧本（given 的 script_obsession）：模型每轮都要一次 check_budget、永不回答——
软终止（模型自己收敛）永远不会来，能停下来的只有你给的硬预算。

你要做的一件事（run_observed 的 TODO 区）：
  - 造只挂 check_budget 的 agent，排好执念剧本，Runner.run(..., max_turns=max_turns)；
  - 在 finally 里把「实际发生的模型请求数」append 进 REQUESTS（异常也要记账——
    mock_tools.CALL_LOG 的同款取证手法）；
  - 不要捕获 MaxTurnsExceeded——预算异常要让上层看见为什么停（L2.3 的纪律在框架课延续）。

完成判据（exercises/test_ex3.py，3 个测试）：
  - max_turns=3：抛 agents.exceptions.MaxTurnsExceeded、消息含 "Max turns (3) exceeded"、
    REQUESTS[-1] == 3；
  - max_turns=5：同样抛、REQUESTS[-1] == 5——预算多大停多大，一次不多；
  - 预算 3 的那次运行里 check_budget 被真实执行满 3 次（CALL_LOG 取证）。

对照：mini-agent 的 AgentBudgetExceeded（L2.3 的 for-range 预算）——openai-agents 把它
换成了 run 循环里的 current_turn > max_turns 检查（讲义 §6 有源码路标）。
"""

from __future__ import annotations

from mock_endpoint import MockLLMEndpoint

# 取证账本：每次运行 append 一个「模型请求数」（你的 TODO 在 finally 里记账）
REQUESTS: list[int] = []

OBSESSION_ROUNDS = 12  # 执念剧本的轮数上限（足够烧穿本题任何预算）
USER_MESSAGE = "请审查报销单 CLM-2026-0001（部门 SALES，关联发票 INV-2026-0001）。"
DEPT = "SALES"


def script_obsession(ep: MockLLMEndpoint, rounds: int = OBSESSION_ROUNDS) -> None:
    """执念剧本（given）：每轮回放一次「模型又要查预算」——永不给最终回答。"""
    for i in range(rounds):
        ep.script_tool_calls([{"id": f"call_loop_{i}", "name": "check_budget", "arguments": {"dept": DEPT}}])


async def run_observed(max_turns: int) -> int:
    """TODO：执念模型 × 显式小预算——记账并让框架异常原样上抛。

    返回值只在「模型神奇地收敛了」时使用（执念剧本下不会发生）：返回模型请求数。
    """
    # TODO(ex3): 需要的顶部 import（TODO 注释点名）：
    #   from agents import Agent, Runner, function_tool
    #   from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    #   from openai import AsyncOpenAI；import mock_tools
    # 流程：mock_tools.CALL_LOG.clear() → with MockLLMEndpoint() as ep:
    #   script_obsession(ep) → 造模型（指向 ep，讲义 Step 1 的 _build_model 同构）→
    #   造 agent（instructions 随意，tools 只挂 function_tool(mock_tools.check_budget)）→
    #   try: await Runner.run(agent, USER_MESSAGE, max_turns=max_turns); return len(ep.requests)
    #   finally: REQUESTS.append(len(ep.requests))
    #   ——预算耗尽时 Runner 抛 MaxTurnsExceeded，finally 记完账异常原样上抛（不要 except 吞掉）。
    raise NotImplementedError("TODO(ex3): 补全 run_observed")
