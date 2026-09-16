"""L3.5 同题 demo：deepagents（harness 形态）实现报销单审查 agent。

统一出口（五课契约）：`async run_review(claim_id) -> Advice`。
离线确定性：内部起 MockLLMEndpoint（test-key / mock-model），台词由
review_rules 预计算决策（script_for 的 expected），harness 特有的轮次
（子代理转交 / 审查底稿落盘 / 结构化收尾）在本模块编排。

deepagents 是 harness：create_deep_agent 默认自带一整套内置工具
（文件系统 ls/read_file/write_file/edit_file/delete/glob/grep + 子代理 task），
我们的 check_budget 以纯函数直接传入——langchain 从签名 + docstring
推断工具 schema（对照 L3.1 的 FunctionTool 包装：同一份工具代码，又一种包装）。

模型注入（以源码为准）：model 参数接受 BaseChatModel 实例或 "provider:model"
字符串；字符串会走各提供商的私有默认（openai: 前缀默认启用 Responses API），
要打 chat completions 兼容端点，传预初始化的 ChatOpenAI 实例最稳
（deepagents/_models.py 的 resolve_model）。
"""

from __future__ import annotations

from typing import Any

from deepagents import SubAgent, create_deep_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph
from pydantic import SecretStr

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

# 与 review_rules 规则表同源的 system 提示（真实端点模式下模型按它决策，两者同源）
SYSTEM_PROMPT = """你是报销单审查助手，按以下规则表出结论（先命中先停）：
1) 明细含非正数金额 → ESCALATE / REJECT:INVALID_AMOUNT（脏数据转人审）
2) 任一明细 > 5000 分 → REJECT / REJECT:ITEM_OVER_LIMIT
3) 关联发票校验未过 → REJECT / REJECT:INVOICE_INVALID
4) 总额 > 部门剩余预算 → REJECT / REJECT:BUDGET_EXCEEDED
5) 以上全不中 → APPROVE / PASS

工作流程：预算余额用 check_budget 查；发票复核必须转交 invoice-specialist
子代理（task 工具）；把审查底稿写入 /review/<单号>.md；最后调用 Advice
工具提交建议单（金额一律整数分）。"""

# 发票专员子代理：声明式 spec（deepagents 导出的 SubAgent TypedDict）——只给它发票校验工具
INVOICE_SPECIALIST: SubAgent = {
    "name": "invoice-specialist",
    "description": "发票校验专员：复核关联发票是否有效并报告结论",
    "system_prompt": "你是发票校验专员，只负责调用 verify_invoice 工具复核发票，并简短报告校验结论。",
    "tools": [mock_tools.verify_invoice],
}


def build_agent(model: BaseChatModel) -> CompiledStateGraph:
    """组装 deep agent（讲义与练习复用）：规则表 system 提示 + 发票专员子代理 + Advice 结构化收尾。"""
    return create_deep_agent(
        model=model,
        tools=[mock_tools.check_budget],
        system_prompt=SYSTEM_PROMPT,
        subagents=[INVOICE_SPECIALIST],
        response_format=Advice,
    )


def input_with_files(message: str, files: dict[str, dict[str, str]]) -> Any:
    """组装「消息 + 预置文件」的 ainvoke 输入。

    返回 Any 不是偷懒：预置 files 是 StateBackend 的**运行时**契约（其 docstring
    明写 invoke({"messages": ..., "files": ...})），但输入类型 InputAgentState 只
    声明了 messages 一个键——类型与运行时在这里有个缺口，Java 同学对照
    Map<String, Object> 传给强类型入口的场景（§5 坑位的远亲）。
    """
    return {"messages": [HumanMessage(content=message)], "files": files}


def _dossier(claim_id: str) -> tuple[str, str]:
    """预生成审查底稿的 (路径, 内容)——剧本里 write_file 轮的台词。

    只走 mock_tools 的纯读取（claim_view / budget_row / invoice_row），
    不污染 CALL_LOG；决策与 review_rules.decide 同源。
    """
    view = mock_tools.claim_view(claim_id)
    budget = mock_tools.budget_row(view["dept"])
    invoice = mock_tools.invoice_row(view["invoice_ids"][0])
    if budget is None or invoice is None:
        raise KeyError(f"mock 数据缺行: {claim_id}")
    expected = review_rules.decide(view, budget, invoice)
    remaining = budget["budget_cents"] - budget["spent_cents"]
    content = (
        f"# 审查底稿 {claim_id}\n"
        f"- 单据：{view['purpose']}；明细 {len(view['items_cents'])} 笔"
        f"共 {view['total_cents']} 分（部门 {view['dept']}）\n"
        f"- 预算：剩余 {remaining} 分\n"
        f"- 发票：{invoice['id']} {'有效' if invoice['valid'] else '无效'}（{invoice['reason']}）\n"
        f"- 结论：{expected.decision} / {expected.reason}\n"
    )
    return f"/review/{claim_id}.md", content


def _report(invoice: dict) -> str:
    """子代理最终报告台词（剧本第 3 轮）。"""
    verdict = "校验通过" if invoice["valid"] else "校验未过"
    return f"发票 {invoice['id']} {verdict}：{invoice['reason']}。"


async def run_review_with_trace(claim_id: str) -> tuple[Advice, dict]:
    """跑一轮完整审查，返回 (建议单, 取证 dict)。

    剧本五轮（模型实际被调用 5 次——对照 mini-agent 的手写循环）：
      R1 主代理：task（转交发票专员）+ check_budget 并行
      R2 子代理：verify_invoice
      R3 子代理：报告发票结论（task 工具的返回值）
      R4 主代理：write_file 写审查底稿（虚拟文件系统，state["files"]）
      R5 主代理：调用 Advice 结构化工具收尾（structured_response）

    取证 dict 含 requests（mock 端点收到的每个请求体）与 state（最终
    messages / files / structured_response）——讲义 Step 展示用。
    """
    mock_tools.CALL_LOG.clear()
    first_turn, _, expected = review_rules.script_for(claim_id)
    view = mock_tools.claim_view(claim_id)
    invoice = mock_tools.invoice_row(view["invoice_ids"][0])
    if invoice is None:  # script_for 已保证非 None，静态检查兜底
        raise KeyError(f"mock 数据缺发票: {claim_id}")
    dossier_path, dossier_content = _dossier(claim_id)

    with MockLLMEndpoint() as ep:
        model = ChatOpenAI(base_url=ep.url, api_key=SecretStr(ep.api_key), model=ep.model)
        agent = build_agent(model)
        ep.script_tool_calls(
            [
                {
                    "id": "call_task",
                    "name": "task",
                    "arguments": {
                        "description": f"复核报销单 {claim_id} 的关联发票 {view['invoice_ids'][0]}",
                        "subagent_type": "invoice-specialist",
                    },
                },
                first_turn[0],  # check_budget（script_for 预生成的第一条）
            ]
        )
        ep.script_tool_calls(
            [{"id": "call_invoice", "name": "verify_invoice", "arguments": {"invoice_id": view["invoice_ids"][0]}}]
        )
        ep.script_text(_report(invoice))
        ep.script_tool_calls(
            [
                {
                    "id": "call_write",
                    "name": "write_file",
                    "arguments": {"file_path": dossier_path, "content": dossier_content},
                }
            ]
        )
        ep.script_tool_calls([{"id": "call_advice", "name": "Advice", "arguments": expected.model_dump()}])
        result = await agent.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            f"请审查报销单 {claim_id}：{view['purpose']}，"
                            f"明细 {view['items_cents']} 分，部门 {view['dept']}。"
                        )
                    )
                ]
            }
        )
        trace = {"requests": list(ep.requests), "state": result}

    files = result.get("files") or {}
    if dossier_path not in files:  # 虚拟文件系统断言：底稿必须落盘
        raise AssertionError(f"审查底稿未落盘: {dossier_path}，实际 {sorted(files)}")
    structured = result.get("structured_response")
    if not isinstance(structured, Advice):  # 结构化收尾断言（L2.4 纪律的 harness 版）
        raise AssertionError(f"结构化收尾缺失: {structured!r}")
    return structured, trace


async def run_review(claim_id: str) -> Advice:
    """契约入口（五课字节相同的 test_contract 只认它）。"""
    advice, _ = await run_review_with_trace(claim_id)
    return advice
