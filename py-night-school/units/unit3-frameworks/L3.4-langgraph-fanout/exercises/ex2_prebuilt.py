# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""prebuilt 装配改造：用 create_react_agent 满足 Unit 3 统一出口 run_review。

考察点：create_react_agent 的三个参数（model / tools / prompt）——注意模型传「没绑过工具」
的裸 ChatOpenAI（框架内部自己 bind_tools）；出口纪律不变：最终消息文本用
Advice.model_validate_json 把关（L2.4，L3.2 finalize 的原样迁移）。

完成判据：uv run pytest exercises/test_ex2.py 全绿——三个测试：
  四张 mock 单逐单跑 run_review：Advice 四字段与 mock 表 expect_* 全等 + 工具真实执行（CALL_LOG）；
  轮数断言：装配产物跑单审恰好 2 次模型请求（第 1 轮并行选两工具、第 2 轮回 Advice JSON）；
  图节点断言：装配产物的节点恰好 __start__/agent/tools/__end__（官方命名的模型节点与工具节点）。
TODO 所需的顶部 import：
  from langgraph.prebuilt import create_react_agent
"""

from __future__ import annotations

import warnings

from langchain_openai import ChatOpenAI
from langgraph.warnings import LangGraphDeprecatedSinceV10
from pydantic import SecretStr

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

SYSTEM_PROMPT = """你是报销单审查助手。审查规则（先命中先停）：
1) 明细含非正数金额 → ESCALATE / REJECT:INVALID_AMOUNT
2) 任一明细 > 5000 分 → REJECT / REJECT:ITEM_OVER_LIMIT
3) 关联发票校验未过 → REJECT / REJECT:INVOICE_INVALID
4) 总额 > 部门剩余预算 → REJECT / REJECT:BUDGET_EXCEEDED
5) 以上全不中 → APPROVE / PASS
先用工具核实部门预算与发票校验，最后一条消息只输出建议单 JSON
（claim_id / decision / reason / remaining_cents 四字段，金额单位分）。"""

RECURSION_LIMIT = 8  # 实测 3 个 superstep：agent → tools×2（Send 扇出）→ agent


def model_for_url(url: str) -> ChatOpenAI:
    """模型客户端（given）：注意没有 .bind_tools——create_react_agent 内部会绑。"""
    return ChatOpenAI(base_url=url, api_key=SecretStr("test-key"), model="mock-model", max_retries=0, timeout=10)


def user_brief(claim_id: str) -> str:
    """入口 user 消息（given）：system 由 create_react_agent 的 prompt 参数负责。"""
    view = mock_tools.claim_view(claim_id)
    return (
        f"请审查报销单 {view['id']}（{view['submitter']}，{view['purpose']}）。\n"
        f"明细（分）：{view['items_cents']}，总额 {view['total_cents']} 分；"
        f"部门 {view['dept']}；关联发票 {view['invoice_ids']}。\n"
        "请先用工具核实预算与发票，再输出建议单 JSON。"
    )


def build_agent(model: ChatOpenAI):
    """prebuilt 装配（你的 TODO）：一个调用换掉 L3.2 的整张手装图。"""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=LangGraphDeprecatedSinceV10)
        # TODO(ex2): return create_react_agent(model, tools=..., prompt=...)
        #   tools 传两个裸函数（mock_tools.check_budget / verify_invoice）的列表；
        #   prompt 传 SYSTEM_PROMPT（改名单告警已被上一行过滤——讲义 Step1 有说明）
        raise NotImplementedError("TODO(ex2): 补 create_react_agent 装配")


async def run_review(claim_id: str) -> Advice:
    """Unit 3 统一出口（剧本编排 given，你补装配调用与出口解析）。"""
    mock_tools.CALL_LOG.clear()
    first_turn, advice_json, _expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        # TODO(ex2): agent = build_agent(model_for_url(ep.url))，
        #   然后 result = await agent.ainvoke({"messages": [{"role": "user", "content": user_brief(claim_id)}]},
        #   config={"recursion_limit": RECURSION_LIMIT})，取最终一条消息的 content，
        #   Advice.model_validate_json(...) 解析后返回
        raise NotImplementedError("TODO(ex2): 补 ainvoke 与出口解析")
