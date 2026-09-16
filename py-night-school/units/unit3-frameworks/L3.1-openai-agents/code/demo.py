"""L3.1 同题 demo 主入口：openai-agents 的 Agent + Runner 跑报销单审查。

统一契约（unit3-frameworks/README.md）：本模块暴露 async run_review(claim_id) -> Advice，
四课对版的共用验收脚本 code/test_contract.py 只认这个入口——差异只在框架，不在题面。

本课第一件事是模块级 set_tracing_disabled(True)：openai-agents 默认把会话 trace
外发到 api.openai.com（讲义 Step 2 有源码证据），端点中立与离线验收都要求先关掉。

离线确定性怎么来的：MockLLMEndpoint（L2.3 服役至今的协议级替身）在 127.0.0.1 起真
HTTP 服务；review_rules.script_for(claim_id) 预生成台词——第 1 轮并行调用
check_budget + verify_invoice，第 2 轮回建议单 JSON 文本。被测对象是框架的管道
（工具分发、消息回喂、output_type 校验），不是模型的质量。

实测口径（0.22.2，冒烟脚本数过 ep.requests）：output_type 走 chat-completions 路径
不会多调一轮模型——每个请求带 response_format=json_schema，最终文本在客户端过
Pydantic 校验（讲义 Step 1 有 wire 证据）。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from agents import Agent, Runner, function_tool, set_tracing_disabled
from agents.models.interface import Model
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

import mock_tools
import review_rules
from advice import Advice
from mock_endpoint import MockLLMEndpoint

set_tracing_disabled(True)  # 模块级第一件事：关 trace 外发（Step 2 讲为什么）
# 真实端点模式下规则表就是 system 提示里的审查规则（与 review_rules.py 同源——
# 离线模式它是替身模型的决策函数，真实模式它是模型自己读的规则）。
INSTRUCTIONS = (
    "你是报销单审查员。先用 check_budget 查申请部门的预算余额，再用 verify_invoice 校验关联发票，"
    "拿到两个工具结果后按规则表出建议单（output_type 已约束为 Advice 的 JSON）。\n"
    "审查规则（先命中先停）：\n"
    "  1) 明细含非正数金额 → ESCALATE / REJECT:INVALID_AMOUNT（脏数据转人审）\n"
    "  2) 任一明细 > 5000 分 → REJECT / REJECT:ITEM_OVER_LIMIT\n"
    "  3) 关联发票校验未过 → REJECT / REJECT:INVOICE_INVALID\n"
    "  4) 总额 > 部门剩余预算 → REJECT / REJECT:BUDGET_EXCEEDED\n"
    "  5) 以上全不中 → APPROVE / PASS"
)


def _build_tools() -> list[Any]:
    """原生直包 mock 工具：签名 → params JSON Schema、docstring → 工具描述。

    对照 L2.2：mini-agent 的注册表要手写 schema；这里 function_tool 在**装饰时**从
    函数签名与 docstring 生成 schema（tool.py 的 function_schema 路径，Step 1 细讲）。
    注意 mock_tools 返回 dict——SDK 对非字符串返回值只做 str()，wire 上是 Python repr
    而不是 JSON（Step 1 的 wire 证据 + L2.2「工具边界收敛」纪律的延续）。
    """
    return [function_tool(mock_tools.check_budget), function_tool(mock_tools.verify_invoice)]


def _build_model(ep: MockLLMEndpoint) -> OpenAIChatCompletionsModel:
    """让 Agent 走 chat-completions 协议并指向 mock 端点——本课关键注入点。

    Agent 的 model 默认走 OpenAI Responses API；换成 OpenAIChatCompletionsModel 后
    请求走 /v1/chat/completions（与 mock 端点、L2.1 的手写 client 同协议）。
    """
    return OpenAIChatCompletionsModel(
        model=ep.model,
        openai_client=AsyncOpenAI(base_url=ep.url, api_key=ep.api_key),
    )


def _build_agent(model: Model | str) -> Agent[None]:
    """极简原语：一个 dataclass 实例，全是运行时普通值（§5 坑位的根源）。"""
    return Agent(
        name="Reviewer",
        instructions=INSTRUCTIONS,
        model=model,
        tools=_build_tools(),
        output_type=Advice,  # 结构化输出：chat-completions 路径用 response_format 约束
    )


def _user_message(claim_id: str) -> str:
    view = mock_tools.claim_view(claim_id)
    return (
        f"请审查报销单 {view['id']}（提交人 {view['submitter']}，部门 {view['dept']}，"
        f"关联发票 {view['invoice_ids'][0]}，明细分：{view['items_cents']}）。"
    )


async def run_review(claim_id: str) -> Advice:
    """同题 demo 统一入口：离线、确定性、零 key——Runner 跑完返回校验过的 Advice。"""
    mock_tools.CALL_LOG.clear()  # 契约定制：入口清取证日志，验收脚本断言工具真实执行
    with MockLLMEndpoint() as ep:
        first_turn, final_text, _expected = review_rules.script_for(claim_id)
        ep.script_tool_calls(first_turn)  # 第 1 轮：并行要两个工具
        ep.script_text(final_text)  # 第 2 轮：建议单 JSON 文本（output_type 校验）
        result = await Runner.run(_build_agent(_build_model(ep)), _user_message(claim_id))
        return result.final_output


def _wire_report(claim_id: str) -> dict:
    """多跑一遍并返回 wire 取证（请求数、每轮角色/工具、tool 回喂原文）——main 打印用。"""
    mock_tools.CALL_LOG.clear()
    with MockLLMEndpoint() as ep:
        first_turn, final_text, _expected = review_rules.script_for(claim_id)
        ep.script_tool_calls(first_turn)
        ep.script_text(final_text)
        result = asyncio.run(Runner.run(_build_agent(_build_model(ep)), _user_message(claim_id)))
        report: dict[str, Any] = {
            "requests": [
                {
                    "roles": [m["role"] for m in req["messages"]],
                    "tools": [t["function"]["name"] for t in req.get("tools", [])],
                    "json_schema": "response_format" in req,
                }
                for req in ep.requests
            ],
            "tool_contents": [m["content"] for req in ep.requests for m in req["messages"] if m["role"] == "tool"],
            "final": result.final_output,
        }
        return report


def _real_config() -> dict[str, str]:
    """读 .env 三变量（端点中立约定；解析逻辑与 L2.3 env_loader 同思路的十行精简版）。"""
    values: dict[str, str] = {}
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.is_file():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.split(" #", 1)[0].strip()
    for key in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "MODEL_NAME"):
        values.setdefault(key, os.environ.get(key, ""))
    missing = [k for k in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "MODEL_NAME") if not values[k]]
    if missing:
        print(f"缺 .env 变量: {missing}（先 cp .env.example .env 再填）")
        raise SystemExit(1)
    return values


async def _run_real(claim_id: str) -> None:
    """可选加餐：真实端点。台词不预生成——调用顺序与结论由模型自己决定。"""
    cfg = _real_config()
    model = OpenAIChatCompletionsModel(
        model=cfg["MODEL_NAME"],
        openai_client=AsyncOpenAI(base_url=cfg["OPENAI_BASE_URL"], api_key=cfg["OPENAI_API_KEY"]),
    )
    print(f"== 真实端点（{cfg['OPENAI_BASE_URL']} / {cfg['MODEL_NAME']}）==")
    result = await Runner.run(_build_agent(model), _user_message(claim_id))
    print(f"最终 Advice: {result.final_output}")
    print(f"工具执行: {mock_tools.CALL_LOG}（max_turns 默认 10 兜底）")


def main() -> None:
    args = sys.argv[1:]
    if "--real" in args:
        claim_id = next((a for a in args if a.startswith("CLM-")), "CLM-2026-0003")
        asyncio.run(_run_real(claim_id))
        return

    print("== L3.1 openai-agents 同题 demo：四张单各跑一遍（离线，零 key） ==")
    for claim in mock_tools.claims_table():
        advice = asyncio.run(run_review(claim["id"]))
        assert isinstance(advice, Advice)  # output_type 校验后的实例，不是 str
        print(
            f"{claim['id']}  requests=2  tools={mock_tools.CALL_LOG}  "
            f"-> {advice.decision} / {advice.reason}（剩余预算 {advice.remaining_cents} 分）"
        )

    print("\n== 第 1 单的 wire 细节（CLM-2026-0001）==")
    report = _wire_report("CLM-2026-0001")
    for i, req in enumerate(report["requests"], start=1):
        print(
            f"request {i}: roles={req['roles']}  tools={req['tools']}  response_format=json_schema={req['json_schema']}"
        )
    print("tool 回喂原文（注意：dict 返回值被 str()，单引号 repr 而非 JSON）：")
    for content in report["tool_contents"]:
        print(f"    {content}")
    final = report["final"]
    print(f"final_output: {final!r}")
    print(f"final_output 类型: {type(final).__module__}.{type(final).__name__}")


if __name__ == "__main__":
    main()
