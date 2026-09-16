"""实验②：trace 默认外发的证据与两个开关（本课第一件事的「为什么」）。

三个实验回答三个问题：
  1. 默认配置下 SDK 到底产不产 trace？——挂一个自己的 TracingProcessor 数 span；
  2. 默认的 trace 去哪？——BackendSpanExporter 的端点硬编码 api.openai.com（源码证据）；
  3. set_tracing_disabled(True) 关的是什么？——全局开关，连自定义 processor 一起静默。

注意：本脚本为了实验要短暂打开 tracing（demo.py 模块级已关），结束前恢复关闭，
不把全局状态留给同进程的后续代码——这也是生产纪律（谁开的谁关）。
"""

from __future__ import annotations

import asyncio

from agents import Agent, Runner, flush_traces, function_tool, set_trace_processors, set_tracing_disabled
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.tracing import TracingProcessor
from openai import AsyncOpenAI

import mock_tools
import review_rules
from mock_endpoint import MockLLMEndpoint

set_tracing_disabled(True)  # 与 demo.py 相同的默认姿态


class CountingProcessor(TracingProcessor):
    """离线 span 计数器：on_*_end 时记一笔——证明「每次 run 都在产 span」。"""

    def __init__(self) -> None:
        self.events: list[str] = []

    def on_trace_start(self, trace) -> None:  # noqa: ANN001 —— SDK 回调签名
        self.events.append(f"trace_start:{trace.name}")

    def on_trace_end(self, trace) -> None:  # noqa: ANN001
        self.events.append("trace_end")

    def on_span_start(self, span) -> None:  # noqa: ANN001
        pass  # 只在 end 记账：start/end 成对，数 end 就够

    def on_span_end(self, span) -> None:  # noqa: ANN001
        self.events.append(f"span:{span.span_data.type}")

    def shutdown(self) -> None:
        pass

    def force_flush(self) -> None:
        pass


async def one_review_run() -> None:
    """跑一次与 demo.run_review 同构的迷你 run（单工具轮，足够产 span）。"""
    with MockLLMEndpoint() as ep:
        first_turn, final_text, _expected = review_rules.script_for("CLM-2026-0001")
        ep.script_tool_calls(first_turn)
        ep.script_text(final_text)
        model = OpenAIChatCompletionsModel(
            model=ep.model, openai_client=AsyncOpenAI(base_url=ep.url, api_key=ep.api_key)
        )
        agent = Agent(
            name="Reviewer",
            instructions="你是报销单审查员。",
            model=model,
            tools=[function_tool(mock_tools.check_budget), function_tool(mock_tools.verify_invoice)],
        )
        await Runner.run(agent, "请审查报销单 CLM-2026-0001。")


def experiment_1_default_produces_spans(processor: CountingProcessor) -> None:
    print("== 实验 1：tracing 打开 + 自定义 processor，跑一次 run ==")
    set_tracing_disabled(False)
    set_trace_processors([processor])
    asyncio.run(one_review_run())
    flush_traces()
    span_counts: dict[str, int] = {}
    for event in processor.events:
        if event.startswith("span:"):
            span_counts[event] = span_counts.get(event, 0) + 1
    print(f"processor 收到的事件（{len(processor.events)} 条）:")
    for name, count in span_counts.items():
        print(f"    {name} ×{count}")
    print("结论：一次 run 产了一整棵 span 树（agent/turn/generation/function...）——")
    print("      这些数据默认交给 BatchTraceProcessor → BackendSpanExporter。")


def experiment_2_default_destination() -> None:
    print("\n== 实验 2：默认 exporter 发去哪（源码证据，不发真请求） ==")
    from agents.tracing.processors import BackendSpanExporter

    print(f"端点常量: {BackendSpanExporter._OPENAI_TRACING_INGEST_ENDPOINT}")  # noqa: SLF001 —— 教学取证
    print("含义：只要 OPENAI_API_KEY 在环境里（配过 .env 的同学都有），")
    print("      即使你的模型端点是 GLM/DeepSeek/本地 vLLM，会话 trace 仍会发往 OpenAI。")
    print("      没配 key 时不发送、只打 warning——离线验收因此不被它打扰，但生产会意外外发。")


def experiment_3_disabled_kills_everything(processor: CountingProcessor) -> None:
    print("\n== 实验 3：set_tracing_disabled(True) 后再跑一次 ==")
    before = len(processor.events)
    set_tracing_disabled(True)
    set_trace_processors([processor])
    asyncio.run(one_review_run())
    flush_traces()
    after = len(processor.events)
    print(f"processor 新收到事件: {after - before} 条")
    print("结论：全局开关连自定义 processor 一起静默——想留本地链路追踪就别关，")
    print("      只想把默认外发换成自己的后端时，用 set_trace_processors 替换而不是关。")


def main() -> None:
    processor = CountingProcessor()
    try:
        experiment_1_default_produces_spans(processor)
        experiment_2_default_destination()
        experiment_3_disabled_kills_everything(processor)
    finally:
        set_tracing_disabled(True)  # 恢复本课默认姿态
        flush_traces()


if __name__ == "__main__":
    main()
