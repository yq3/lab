"""Step 全程轨迹：离线跑 CLM-2026-0004 争议全程，按四个段落打印 superstep 轨迹（讲义 §3 产出）。

离线（默认）：quick/deep 两个 MockLLMEndpoint + demo 的剧本脚本表，行为确定性——
节点序列、调用次数、裁决结论每次完全一致。真实端点（--real）：读 .env 三变量，
quick/deep 都用 MODEL_NAME（生产应给 deep 配更强的模型——对版 deep/quick 双模型）。

langsmith 追踪：不设 LANGSMITH_* 环境变量即默认关闭、零外发（L3.2 §2.5 同款纪律）。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

import demo
import policy_tools
from budget import LLMCallBudget
from config import AppealConfig
from graph import RECURSION_LIMIT, build_appeal_graph, initial_state
from mock_endpoint import MockLLMEndpoint
from schemas import AppealRuling, FinalDecision

SEGMENTS = [  # 四个段落的标题与起止节点（demo_trace 的切分依据）
    ("段落① 政策分析师（工具循环）", ("政策分析师", "政策工具", "清理上下文")),
    ("段落② 申辩人 ⇄ 合规官（计数终止）", ("申辩人", "合规官")),
    ("段落③ 裁决官（deep 模型）", ("裁决官",)),
    ("段落④ 风险三方 + 终审（deep）", ("宽松解释", "严格合规", "例外处理", "终审官")),
]


def _brief_message(message) -> str:  # noqa: ANN001 -- langchain 消息对象或 dict，讲义脚本从简
    """把一条消息压成一行轨迹（role + 内容摘要）。"""
    if isinstance(message, dict):  # tools 节点回喂的 ToolMessage dict
        text = str(message.get("content", "")).replace("\n", " ")
        return f"tool({str(message.get('tool_call_id', '?'))[-6:]}): {text[:38]}{'…' if len(text) > 38 else ''}"
    role = type(message).__name__.removesuffix("Message").lower()
    if getattr(message, "tool_calls", None):
        names = ", ".join(c["name"] for c in message.tool_calls)
        return f"{role}: [并行选了工具: {names}]"
    text = str(message.content).replace("\n", " ")
    return f"{role}: {text[:40]}{'…' if len(text) > 40 else ''}"


def _segment_of(node: str) -> str | None:
    for title, nodes in SEGMENTS:
        if node in nodes:
            return title
    return None


def _client(url: str, model: str, timeout: int = 10) -> ChatOpenAI:
    """离线客户端（指向 mock 端点）。"""
    return ChatOpenAI(base_url=url, api_key=SecretStr("test-key"), model=model, max_retries=0, timeout=timeout)


async def run_offline() -> None:
    cfg = AppealConfig()
    budget = LLMCallBudget(cfg.max_llm_calls)
    print(
        f"== L4.2 辩论-裁决上诉图：{demo.CLAIM_ID}（离线剧本，rounds={cfg.max_debate_rounds}/{cfg.max_risk_rounds}） =="
    )
    print(
        "图: START → 政策分析师 ⇄ 政策工具 → 清理上下文 → 申辩人 ⇄ 合规官"
        "（2*rounds 计数终止）→ 裁决官 → 宽松→严格→例外（3*rounds）→ 终审官 → END\n"
    )
    with (
        MockLLMEndpoint(model=cfg.quick_model) as ep_quick,
        MockLLMEndpoint(model=cfg.deep_model) as ep_deep,
    ):
        demo.script_endpoint(ep_quick, ep_deep)
        analyst = budget.wrap(_client(ep_quick.url, cfg.quick_model).bind_tools([policy_tools.lookup_policy]))
        quick = budget.wrap(_client(ep_quick.url, cfg.quick_model))
        deep = budget.wrap(_client(ep_deep.url, cfg.deep_model))
        graph = build_appeal_graph(cfg, analyst, quick, deep)
        current_segment: str | None = None
        ruling_out: AppealRuling | None = None
        final_out: FinalDecision | None = None
        async for chunk in graph.astream(
            initial_state(demo.CLAIM_ID, demo.appeal_brief(demo.CLAIM_ID)),
            config={"recursion_limit": RECURSION_LIMIT},
            stream_mode="updates",
        ):
            for node, update in chunk.items():
                segment = _segment_of(node)
                if segment != current_segment:
                    print(f"\n== {segment} ==")
                    current_segment = segment
                _print_update(node, update)
                if "ruling" in update:
                    ruling_out = update["ruling"]
                if "final" in update:
                    final_out = update["final"]
        quick_n, deep_n = len(ep_quick.requests), len(ep_deep.requests)
        tools_in_first = [t["function"]["name"] for t in ep_quick.requests[0].get("tools", [])]
    print("\n== 收口 ==")
    assert ruling_out is not None and final_out is not None  # 裁决官/终审官必然已跑（剧本图形状）
    print(f"  ruling : {cfg.deep_model} → {ruling_out.verdict} / 封顶 {ruling_out.capped_amount_cents} 分")
    print(f"  final  : {cfg.deep_model} → {final_out.verdict} / 封顶 {final_out.capped_amount_cents} 分（终审维持）")
    print(f"  模型调用: quick {quick_n} 次 + deep {deep_n} 次 = {quick_n + deep_n} 次")
    print(
        f"    其中辩论段恰好 2*rounds={2 * cfg.max_debate_rounds} 次、"
        f"风险段恰好 3*rounds={3 * cfg.max_risk_rounds} 次——固定轮次=可预算"
    )
    print(f"  工具白名单: 分析师首请求绑定 {tools_in_first}；辩论段请求不带 tools 字段（对版「工具按角色静态划分」）")


def _print_update(node: str, update: dict) -> None:
    """打印一个节点的状态更新（消息增删 / 嵌套计数 / 裁决字段）。"""
    if "messages" in update:
        for message in update["messages"]:
            kind = type(message).__name__
            if kind == "RemoveMessage":
                continue  # 删除指令不单行打印，聚合成下面那行
            print(f"  [{node}] + {_brief_message(message)}")
        removals = sum(1 for m in update["messages"] if type(m).__name__ == "RemoveMessage")
        if removals:
            print(f"  [{node}] - RemoveMessage ×{removals}（清空消息史，换 1 条锚定占位——阶段裁剪）")
    if "debate" in update:
        debate = update["debate"]
        print(f"  [{node}] debate.count {debate['count'] - 1}→{debate['count']}（不写 messages——走嵌套 state）")
    if "risk" in update:
        risk = update["risk"]
        print(f"  [{node}] risk.count {risk['count'] - 1}→{risk['count']}")
    if "ruling" in update:
        print(f"  [{node}] ruling: {update['ruling'].verdict} / 封顶 {update['ruling'].capped_amount_cents} 分")
    if "final" in update:
        print(f"  [{node}] final : {update['final'].verdict} / 封顶 {update['final'].capped_amount_cents} 分")


def _load_env() -> dict[str, str]:
    """极简 .env 读取（L3.2 同款）：KEY=VALUE 行，忽略注释。"""
    env: dict[str, str] = {}
    path = Path(".env")
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.split(" #")[0].strip()
    return env


async def run_real() -> None:
    env = _load_env()
    missing = [k for k in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "MODEL_NAME") if not env.get(k)]
    if missing:
        print(f"缺 .env 变量: {missing}（先 cp .env.example .env 并填写）")
        return
    cfg = AppealConfig(quick_model=env["MODEL_NAME"], deep_model=env["MODEL_NAME"])

    def client() -> ChatOpenAI:
        return ChatOpenAI(
            base_url=env["OPENAI_BASE_URL"],
            api_key=SecretStr(env["OPENAI_API_KEY"]),
            model=env["MODEL_NAME"],
            max_retries=0,
            timeout=60,
        )

    analyst = client().bind_tools([policy_tools.lookup_policy])
    plain = client()
    graph = build_appeal_graph(cfg, analyst, plain, plain)
    state = await graph.ainvoke(
        initial_state(demo.CLAIM_ID, demo.appeal_brief(demo.CLAIM_ID)),
        config={"recursion_limit": RECURSION_LIMIT},
    )
    print(f"== 真实端点（{env['MODEL_NAME']}）上诉 {demo.CLAIM_ID} ==")
    print(f"  ruling: {state['ruling'].verdict} / {state['ruling'].rationale[:60]}")
    print(f"  final : {state['final'].verdict} / {state['final'].summary[:60]}")
    print(f"  工具真实执行: {sorted(set(policy_tools.CALL_LOG))}")


def main() -> None:
    if "--real" in sys.argv[1:]:
        asyncio.run(run_real())
    else:
        asyncio.run(run_offline())


if __name__ == "__main__":
    main()
