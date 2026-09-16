# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体/区域与所需的顶部 import，其余不要动）
"""改造题 1：给 harness 加自定义工具 lookup_policy。

demo 的主代理只带了 check_budget（发票在子代理手里）。本题加第三个工具：
`lookup_policy(purpose_keyword)`——按报销用途关键词查政策话术。政策表是
**内联练习素材**（POLICY_TABLE，明线 data/ 之外的本课练习素材，金额口径
与 review_mock.json 同为整数分）。

TODO 两处：
  1) `lookup_policy` 函数体：按关键词子串匹配 POLICY_TABLE 的键（大小写不敏感）；
     命中→记 POLICY_LOG 并返回政策行；未命中→返回错误行 dict（不抛异常——
     L2.2 工具纪律：错误是给模型的修复指令，也是返回值）。对照 mock_tools.check_budget
     的 unknown_dept 分支：查无也不记 POLICY_LOG。
  2) `build_agent` 函数体：组装 agent，tools 同时注册 check_budget 与 lookup_policy，
     response_format=Advice（形状参考 demo.build_agent，tools 是本题的改造点）。
     **需要的顶部 import**：from deepagents import create_deep_agent（骨架没预置——
     给定部分用不到它，预置了会被 lint 判未使用）。

完成判据：uv run pytest exercises/test_ex1.py 全绿（两个测试）——
  新工具被框架真实执行（POLICY_LOG 与回喂内容取证）；未命中关键词走错误行不炸管道。
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph
from pydantic import SecretStr

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

SYSTEM = "你是报销单审查助手：先查政策与预算，再按规则表出结论（金额一律整数分）。"

# 练习素材（内联声明）：用途关键词 → 政策话术行
POLICY_TABLE: dict[str, dict] = {
    "宴请": {
        "keyword": "宴请",
        "policy": "工作餐人均不超过 150 元；项目验收宴请需部门总监事前批准",
        "limit_cents": 5000,
    },
    "交通": {
        "keyword": "交通",
        "policy": "市内交通实报实销；打车单程超过 200 元需说明事由",
        "limit_cents": 100000,
    },
    "物料": {
        "keyword": "物料",
        "policy": "展会物料采购需附三家比价记录",
        "limit_cents": 50000,
    },
}
POLICY_LOG: list[str] = []  # lookup_policy 真实执行的取证（对位 mock_tools.CALL_LOG）


def lookup_policy(purpose_keyword: str) -> dict:
    """按报销用途关键词查政策话术：返回政策行（含 policy 原文与限额，单位分）。"""
    # TODO(ex1-1): 子串匹配 POLICY_TABLE 的键（两边 lower 后用 in 判断）；
    # 命中→记一次取证（对位 mock_tools.CALL_LOG 的做法，工具名照旧）并返回该政策行的拷贝；
    # 未命中→返回带原词与固定错误码 policy_not_found 的错误 dict（键名对照 test_ex1 的断言）
    raise NotImplementedError("TODO(ex1-1): 补全 lookup_policy")


def build_agent(model: BaseChatModel) -> CompiledStateGraph:
    """组装本题的 agent：check_budget 与 lookup_policy 双工具 + Advice 结构化收尾。"""
    # TODO(ex1-2): 补顶部 import 后：create_deep_agent(model=model, tools=[...两个工具...],
    # system_prompt=SYSTEM, response_format=Advice)
    raise NotImplementedError("TODO(ex1-2): 补全 build_agent")


async def run_with_policy(claim_id: str, keyword: str) -> tuple[Advice, dict]:
    """given：剧本跑一轮「查政策 + 查预算 → 建议单」，返回 (建议单, 最终 state)。

    第 1 轮并行调用 lookup_policy(keyword) 与 check_budget(dept)，
    第 2 轮调用 Advice 结构化工具收尾——两个工具名都要求已在 build_agent 注册。
    """
    mock_tools.CALL_LOG.clear()
    POLICY_LOG.clear()
    _, _, expected = review_rules.script_for(claim_id)
    view = mock_tools.claim_view(claim_id)
    with MockLLMEndpoint() as ep:
        model = ChatOpenAI(base_url=ep.url, api_key=SecretStr(ep.api_key), model=ep.model)
        agent = build_agent(model)
        ep.script_tool_calls(
            [
                {"id": "call_policy", "name": "lookup_policy", "arguments": {"purpose_keyword": keyword}},
                {"id": "call_budget", "name": "check_budget", "arguments": {"dept": view["dept"]}},
            ]
        )
        ep.script_tool_calls([{"id": "call_advice", "name": "Advice", "arguments": expected.model_dump()}])
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=f"请审查报销单 {claim_id}：{view['purpose']}，部门 {view['dept']}。")]}
        )
    structured = result.get("structured_response")
    if not isinstance(structured, Advice):
        raise AssertionError(f"结构化收尾缺失: {structured!r}")
    return structured, dict(result)
