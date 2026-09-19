# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""ex2 session.state 改造：单笔上限从硬编码改为「按会话注入」。

背景：review_rules 的规则表把单笔上限钉死在 mock_tools.ITEM_LIMIT_CENTS（5000 分）；
全家桶的卖点是「同一个 agent，不同会话不同策略」——上限作为会话状态在
create_session(state=...) 时注入，工具经 tool_context.state 读到（Step 3 已演示）。

data/ 用例推演（CLM-2026-0001，明细 [1200, 3500, 2400]，部门 SALES，剩余预算 10000 分）：
  注入 3000 → 3500 超限 → REJECT / REJECT:ITEM_OVER_LIMIT；
  注入 5000 → 无明细超限 → APPROVE / PASS。

完成判据：uv run pytest exercises/test_ex2.py 全绿——共 2 个测试（各含三组断言）：
  ① 注入 3000：decision==REJECT、reason==REJECT:ITEM_OVER_LIMIT、
     CALL_LOG 含 "limit_check:3000"（state 真的流到了工具）；
  ② 注入 5000：decision==APPROVE、reason==PASS、CALL_LOG 含 "limit_check:5000"。

所需的顶部 import（骨架未预置，自己加）：from adk_review import APP_NAME, USER_ID, ask, build_runner, final_text
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.tool_context import ToolContext

import mock_tools
from adk_review import APP_NAME, USER_ID, ask, build_runner, final_text
from advice import Advice
from mock_endpoint import MockLLMEndpoint

INSTRUCTION = (
    "你是报销单审查助手，本会话的单笔上限以工具 limit_check 的回喂为准。"
    "先调用 limit_check 审查明细，再输出结论，"
    "最终只输出一个 JSON 对象（字段 claim_id/decision/reason/remaining_cents）。"
)


def limit_check(items_cents: list[int], tool_context: ToolContext) -> dict:
    """按本会话的单笔上限审查明细：返回超限金额与所用的上限。

    Args:
        items_cents: 报销明细金额列表（分）
        tool_context: 框架注入的会话上下文，用来读 session.state 的单笔上限
    """
    limit = tool_context.state.get("item_limit_cents", mock_tools.ITEM_LIMIT_CENTS)
    mock_tools.CALL_LOG.append(f"limit_check:{limit}")  # 取证：state 一路流到了工具
    over = [cents for cents in items_cents if cents > limit]
    return {"limit_cents": limit, "over_limit_cents": over}


def build_agent(ep: MockLLMEndpoint) -> LlmAgent:
    """装配好就绪的 agent（given）：注意 tools 里只有 limit_check 一个。"""
    return LlmAgent(
        name="limit_reviewer",
        model=LiteLlm(model="openai/mock-model", api_base=ep.url, api_key=ep.api_key),
        instruction=INSTRUCTION,
        tools=[limit_check],
    )


def first_turn_for(claim_id: str) -> list[dict]:
    """剧本第 1 轮（given）：模型把整单明细交给 limit_check 审查。"""
    view = mock_tools.claim_view(claim_id)
    return [{"id": "call_limit", "name": "limit_check", "arguments": {"items_cents": view["items_cents"]}}]


def expected_advice(claim_id: str, item_limit_cents: int) -> Advice:
    """参数化版审查规则（given）：单笔上限是入参，不是常量——expected 剧本由它生成。"""
    view = mock_tools.claim_view(claim_id)
    budget = mock_tools.budget_row(view["dept"])
    assert budget is not None, f"mock 数据缺部门行: {claim_id}"
    if any(cents <= 0 for cents in view["items_cents"]):
        decision, reason = "ESCALATE", "REJECT:INVALID_AMOUNT"
    elif any(cents > item_limit_cents for cents in view["items_cents"]):
        decision, reason = "REJECT", "REJECT:ITEM_OVER_LIMIT"
    elif view["total_cents"] > budget["budget_cents"] - budget["spent_cents"]:
        decision, reason = "REJECT", "REJECT:BUDGET_EXCEEDED"
    else:
        decision, reason = "APPROVE", "PASS"
    return Advice(
        claim_id=view["id"],
        decision=decision,
        reason=reason,
        remaining_cents=budget["budget_cents"] - budget["spent_cents"],
    )


async def review_with_limit(ep: MockLLMEndpoint, claim_id: str, item_limit_cents: int) -> Advice:
    """离线跑一单：上限走会话状态注入，出口仍是 Advice（四课统一出口的参数化版）。

    TODO(ex2) 三步（对照 Step 1/Step 3 的讲义代码）：
      ① 预生成剧本喂 ep：script_tool_calls(first_turn_for(claim_id)) +
        script_text(expected_advice(claim_id, item_limit_cents).model_dump_json())；
      ② create_session 时注入 {"item_limit_cents": item_limit_cents}——
        这是本题的考点：策略挂在会话上，不挂在 agent 定义上；
      ③ 跑 runner（ask 收集事件）、final_text 取最终文本、Advice.model_validate_json 返回。
    跑完记得 mock_tools.CALL_LOG.clear() 放在入口（取证口径与 test_contract 一致）。
    """
    mock_tools.CALL_LOG.clear()
    ep.script_tool_calls(first_turn_for(claim_id))
    ep.script_text(expected_advice(claim_id, item_limit_cents).model_dump_json())
    runner = build_runner(build_agent(ep))
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, state={"item_limit_cents": item_limit_cents}
    )
    events = [event async for event in ask(runner, session.id, f"请审查报销单 {claim_id}")]
    return Advice.model_validate_json(final_text(events))
