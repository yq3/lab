"""L4.2 同题 demo：TradingAgents 辩论-裁决拓扑的报销争议上诉版（统一出口 run_appeal）。

明线（dimensions/A §2 官方映射）：报销争议/异常调查 = 固定轮次辩论 + deep 裁决。
争议单 CLM-2026-0004（初审 REJECT:INVOICE_INVALID，素材唯一来源 data/expense/
review_mock.json）：钱工主张发票连号重开、支出真实，对驳回提起上诉——申辩人 vs
合规官围绕 POL-7.2 红线与 POL-9.1 例外对抗，deep 裁决官出 AppealRuling，三方
政策视角（宽松/严格/例外）再辩一轮，deep 终审官出 FinalDecision。

离线确定性（L2.3 服役至今的 mock 端点，本课 quick/deep 各起一个）：
- 剧本脚本表 = SCRIPT_* 常量（离线确定）：quick 端点 9 份（工具轮 1 + 政策归纳 1 +
  申辩/合规各 2 + 风险三方 3，默认轮次只消费前 7 份）、deep 端点 2 份（裁决 + 终审）；
- 模型调用次数以 ep.requests 实测为准：默认配置恰好 quick 7 + deep 2 = 9 次
  （辩论段恰好 2*max_debate_rounds，风险段恰好 3*max_risk_rounds——「可预算」的实证）；
- 预算封顶走 budget.LLMCallBudget： AppealConfig.max_llm_calls 不为 None 时，
  quick/deep 共用一个计数器，超限抛 BudgetExceeded（ex2 / step2_budget.py）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

import policy_tools
from budget import LLMCallBudget
from config import AppealConfig
from graph import RECURSION_LIMIT, build_appeal_graph, initial_state
from mock_endpoint import MockLLMEndpoint

REVIEW_FILE = Path(__file__).resolve().parents[4] / "data" / "expense" / "review_mock.json"

CLAIM_ID = "CLM-2026-0004"  # 明线争议单：发票校验未过（INV-2026-0005 已作废，连号重开）

# ---- 离线剧本脚本表（离线确定：辩论台词、政策归纳、两份裁决 JSON 都是定值） ----

ANALYST_TOOL_CALLS: list[dict] = [
    {"id": "call_pol_1", "name": "lookup_policy", "arguments": {"article_id": "POL-7.2"}},
    {"id": "call_pol_2", "name": "lookup_policy", "arguments": {"article_id": "POL-9.1"}},
]
POLICY_REPORT = (
    "政策归纳：POL-7.2 规定无有效发票整单驳回——本单 INV-2026-0005 已作废，初审即据此；"
    "POL-9.1 规定连号重开情形凭重开新票与情况说明，可按原始金额的 80% 报销"
    "（APPROVE_WITH_CAP，需留档备查）。两条的适用冲突是本次上诉的争议焦点。"
)
APPLICANT_TURN_1 = (
    "申辩要点：INV-2026-0005 因供应商连号重开而作废，重开新票已取得；货物已验收投入使用，"
    "支出真实。按 POL-9.1 属补开情形，请求按原始 5000 分的 80% 即 4000 分报销。"
)
OFFICER_TURN_1 = (
    "质证要点：随单发票确已作废属实；但重开新票与验收单未随单提交，单据链不完整，"
    "POL-9.1 的要件不满足；例外条款不应架空 POL-7.2 的红线。维持整单驳回。"
)
APPLICANT_TURN_2 = (
    "补充：重开新票号与验收单已随上诉材料补交财务留档（第 3 页），单据链已闭合；"
    "POL-9.1 的立法本意正是为真实支出的凭证瑕疵兜底。"
)
OFFICER_TURN_2 = (
    "让步：若留档属实，单据链异议撤回；但 POL-9.1 明确按 80% 封顶且需留档备查——请在整单放行与封顶报销之间权衡。"
)
RULING_JSON = (
    '{"verdict":"APPROVE_WITH_CAP","rationale":"连号重开情形成立且单据链已闭合，'
    '按 POL-9.1 折中：不整单放行，也不维持驳回","capped_amount_cents":4000}'
)
LENIENT_TURN = "宽松解释：POL-9.1 的立法本意是解决真实支出的凭证瑕疵，本案要件齐备，支持按 4000 分封顶报销。"
STRICT_TURN = "严格合规：例外是例外、红线是红线；留档材料未经人工核验前不应由系统放行，建议维持驳回或转人工。"
EXCEPTION_TURN = "例外处理：走例外流程——人工核验留档后放行，金额 clamp 到 4000 分，台账备注「连号重开、按 80% 封顶」。"
FINAL_JSON = (
    '{"verdict":"APPROVE_WITH_CAP","summary":"终审维持初裁：补开情形成立，'
    '按 POL-9.1 以 4000 分封顶报销并留档备查","capped_amount_cents":4000}'
)

# 剧本预期（test_demo 的对表依据；金额口径：整数分）
EXPECTED_VERDICT = "APPROVE_WITH_CAP"
EXPECTED_CAP_CENTS = 4000


@dataclass
class AppealOutcome:
    """run_appeal 的取证收口：终态 + 两个端点的请求体（次数与内容都留证）。"""

    state: dict
    quick_calls: int
    deep_calls: int
    quick_requests: list[dict]
    deep_requests: list[dict]

    @property
    def llm_calls(self) -> int:
        return self.quick_calls + self.deep_calls


def claim_view(claim_id: str) -> dict:
    """读明线素材（唯一来源 data/expense/review_mock.json）拼争议单视图。"""
    table = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))["claims"]
    for claim in table:
        if claim["id"] == claim_id:
            return {**claim, "total_cents": sum(claim["items_cents"])}
    raise KeyError(f"查无此报销单: {claim_id}")


def appeal_brief(claim_id: str) -> str:
    """入口 user 消息：争议单摘要（对照 L3.2 initial_messages 的单据视图）。"""
    view = claim_view(claim_id)
    return (
        f"报销争议上诉 {view['id']}：{view['submitter']}对初审驳回（REJECT:INVOICE_INVALID）提起上诉。\n"
        f"事由：{view['purpose']}；明细（分）：{view['items_cents']}，总额 {view['total_cents']} 分；"
        f"部门 {view['dept']}；关联发票 {view['invoice_ids']}（校验未过：已作废，连号重开）。\n"
        "请先用工具查 POL-7.2 与 POL-9.1 两条政策，再归纳政策结论。"
    )


def script_endpoint(ep_quick: MockLLMEndpoint, ep_deep: MockLLMEndpoint) -> None:
    """把剧本脚本表按消费顺序入队（顺序即图的确定性执行顺序）。

    quick 队列 9 份：工具轮 → 政策归纳 → 申辩/合规各两轮台词 → 风险三方
    （默认 rounds=1 只消费前 7 份，rounds=2 消费到第 9 份——辩论段恰好 2*rounds 次）；
    deep 队列 2 份：裁决 JSON → 终审 JSON。
    """
    ep_quick.script_tool_calls(ANALYST_TOOL_CALLS)
    for text in (POLICY_REPORT, APPLICANT_TURN_1, OFFICER_TURN_1, APPLICANT_TURN_2, OFFICER_TURN_2):
        ep_quick.script_text(text)
    for text in (LENIENT_TURN, STRICT_TURN, EXCEPTION_TURN):
        ep_quick.script_text(text)
    ep_deep.script_text(RULING_JSON)
    ep_deep.script_text(FINAL_JSON)


def _chat(url: str, model: str) -> ChatOpenAI:
    return ChatOpenAI(base_url=url, api_key=SecretStr("test-key"), model=model, max_retries=0, timeout=10)


async def run_appeal(config: AppealConfig | None = None) -> AppealOutcome:
    """统一出口：离线确定性跑完整张上诉图，返回终态与请求取证。

    实测请求次数（默认配置）：quick 7 次（分析师 2 + 辩论 2 + 风险 3）、deep 2 次
    （裁决 + 终审）；辩论段恰好 2*max_debate_rounds、风险段恰好 3*max_risk_rounds。
    """
    cfg = config or AppealConfig()
    policy_tools.CALL_LOG.clear()
    budget = LLMCallBudget(cfg.max_llm_calls)
    with (
        MockLLMEndpoint(model=cfg.quick_model) as ep_quick,
        MockLLMEndpoint(model=cfg.deep_model) as ep_deep,
    ):
        script_endpoint(ep_quick, ep_deep)
        analyst_model = budget.wrap(_chat(ep_quick.url, cfg.quick_model).bind_tools([policy_tools.lookup_policy]))
        quick_model = budget.wrap(_chat(ep_quick.url, cfg.quick_model))
        deep_model = budget.wrap(_chat(ep_deep.url, cfg.deep_model))
        graph = build_appeal_graph(cfg, analyst_model, quick_model, deep_model)
        state = await graph.ainvoke(
            initial_state(CLAIM_ID, appeal_brief(CLAIM_ID)),
            config={"recursion_limit": RECURSION_LIMIT},
        )
        outcome = AppealOutcome(
            state=state,
            quick_calls=len(ep_quick.requests),
            deep_calls=len(ep_deep.requests),
            quick_requests=list(ep_quick.requests),
            deep_requests=list(ep_deep.requests),
        )
    return outcome
