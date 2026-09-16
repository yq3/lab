"""L3.4 同题 demo：用 langgraph.prebuilt.create_react_agent 装报销单审查 agent（Unit 3 统一出口 run_review）。

装配对比（同一契约的第二种装配——题面不动，差异只在装配方式）：

    L3.2 手装：StateGraph(ClaimState) + 3 个 add_node + 4 条边 + 手写 bind_tools/finalize
               （demo.build_graph 约 10 行装配 + 约 40 行节点函数）
    L3.4 prebuilt：create_react_agent(model, tools, prompt) 一个调用——
               模型节点（"agent"）、工具节点（ToolNode）、条件边（should_continue）全在框架里。

三条设计纪律（每条都对照前课）：
- 模型不再手动 bind_tools：create_react_agent 内部对模型执行 bind_tools（源码导读 Step3 逐行看）；
- 工具传「裸函数」即可：ToolNode 自动把普通函数包成 StructuredTool（约定优于配置，§2.4）；
- 出口纪律不变：最终消息文本用 Advice.model_validate_json 把关（L2.4），剧本照旧
  review_rules.script_for 预生成；实测 ep.requests：每单恰好 2 次模型请求
  （第 1 轮并行选两工具、第 2 轮回 Advice JSON 文本）。

弃用说明（诚实边界）：prebuilt 1.1.0 里 create_react_agent 已标记弃用（官方迁名
langchain.agents.create_agent，骨架相同）——本课读的正是这个经典装配的源码，
build_agent 里用 warnings 过滤它的改名单，行为不受影响（讲义 Step1 有展开）。
"""

from __future__ import annotations

import warnings

from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.warnings import LangGraphDeprecatedSinceV10
from pydantic import SecretStr

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

# 与 review_rules 同源的审查规则（真实端点模式下它就是 system 提示；离线模式下是替身决策函数）
SYSTEM_PROMPT = """你是报销单审查助手。审查规则（先命中先停）：
1) 明细含非正数金额 → ESCALATE / REJECT:INVALID_AMOUNT
2) 任一明细 > 5000 分 → REJECT / REJECT:ITEM_OVER_LIMIT
3) 关联发票校验未过 → REJECT / REJECT:INVOICE_INVALID
4) 总额 > 部门剩余预算 → REJECT / REJECT:BUDGET_EXCEEDED
5) 以上全不中 → APPROVE / PASS
先用工具核实部门预算与发票校验，最后一条消息只输出建议单 JSON
（claim_id / decision / reason / remaining_cents 四字段，金额单位分）。"""

# 工具注册表：传给 create_react_agent 的是两个裸函数——框架自动包工具（对照 L3.2 手动 bind_tools）
TOOL_FUNCS = [mock_tools.check_budget, mock_tools.verify_invoice]

RECURSION_LIMIT = 8  # 硬终止预算（本图实测 3 个 superstep：agent → tools×2（Send 扇出）→ agent）


def build_agent(model: ChatOpenAI) -> CompiledStateGraph:
    """prebuilt 装配：一个调用换掉 L3.2 的整张手装图。

    prompt 传 str 时框架把它包成 SystemMessage 垫在消息史最前（每次请求都带）——
    所以入口消息只需要 user 一条（对照 L3.2 的 initial_messages 两件套）。
    """

    def agent() -> CompiledStateGraph:
        return create_react_agent(model, tools=TOOL_FUNCS, prompt=SYSTEM_PROMPT)

    # 官方改名单过滤：deprecated in LangGraph V1.0, to be removed in V2.0（docstring 里的弃用说明）
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=LangGraphDeprecatedSinceV10)
        return agent()


def model_for_url(url: str, api_key: str = "test-key", model: str = "mock-model") -> ChatOpenAI:
    """模型客户端：注意没有 .bind_tools——create_react_agent 内部会绑（讲义 Step3 有源码行号）。"""
    return ChatOpenAI(base_url=url, api_key=SecretStr(api_key), model=model, max_retries=0, timeout=10)


def user_brief(claim_id: str) -> str:
    """入口 user 消息：单据摘要（与 review_rules 剧本生成器同源的单据视图；system 由 prompt= 负责）。"""
    view = mock_tools.claim_view(claim_id)
    return (
        f"请审查报销单 {view['id']}（{view['submitter']}，{view['purpose']}）。\n"
        f"明细（分）：{view['items_cents']}，总额 {view['total_cents']} 分；"
        f"部门 {view['dept']}；关联发票 {view['invoice_ids']}。\n"
        "请先用工具核实预算与发票，再输出建议单 JSON。"
    )


async def run_review(claim_id: str) -> Advice:
    """Unit 3 统一出口：离线确定性跑完 prebuilt agent，返回结构化建议单。

    剧本来自 review_rules.script_for（第 1 轮并行调用两个工具、第 2 轮回 Advice JSON）；
    实测 ep.requests：每单恰好 2 次模型请求（"agent" 节点被执行两轮，中间夹一次 tools 扇出）。
    """
    mock_tools.CALL_LOG.clear()
    first_turn, advice_json, _expected = review_rules.script_for(claim_id)
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(advice_json)
        agent = build_agent(model_for_url(ep.url))
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_brief(claim_id)}]},
            config={"recursion_limit": RECURSION_LIMIT},
        )
    return Advice.model_validate_json(result["messages"][-1].content.strip())
