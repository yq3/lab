"""L4.2 辩手与裁决节点：申辩人/合规官（对版 bull/bear researcher）+ 风险三方 + 两裁决官。

对版 TauricResearch/TradingAgents@be952b8：
- agents/researchers/bull_researcher.py#bull_node——每节点恰好 1 次模型调用，然后**手工
  回填嵌套 state 的全部键**（history 拼接、专属 history 拼接、current_response 换成
  「Bull Analyst: <论点>」、count+1）。嵌套 dict 无 reducer、整体替换——漏一个键就是
  静默丢数据（§5 陷阱）。本课申辩人/合规官/风险三方原样保留这条纪律。
- agents/utils/agent_utils.py#opponent_argument_or_opening（#1176）：先手辩手拿到的对手
  论点是空串——直接插进「请驳斥对方论点」的提示词会让模型**虚构对方立场**；换成显式的
  「对方尚未发言」标记，让它亮出自己的开场论点。
- managers/research_manager.py / portfolio_manager.py：deep 模型只花在裁决（default_config
  的 deep_think_llm 仅这两处使用）；本课裁决官/终审官接 deep 模型，其余全是 quick。
- analysts/market_analyst.py：工具轮不写报告（report=""），收束轮才把 content 写进
  market_report——本课政策分析师同款。

角色映射（金融 → 报销争议上诉）：
- Bull Researcher → 申辩人（申请人立场：主张适用 POL-9.1 例外）
- Bear Researcher → 合规官（合规立场：主张 POL-7.2 红线）
- Aggressive/Conservative/Neutral 风险辩手 → 宽松解释/严格合规/例外处理（三种政策视角，
  dimensions/A §2 的官方映射）
- Research Manager → 裁决官（deep，AppealRuling）；Portfolio Manager → 终审官（deep，
  FinalDecision）。产品的 Trader 环节（交易员）在上诉场景无对应物，教学版裁掉——
  图形状差异在 README §2 的映射表里逐行标注。
"""

from __future__ import annotations

from typing import Any

from conditional import (
    APPLICANT_ADVOCATE,
    COMPLIANCE_OFFICER,
    EXCEPTION_HANDLER,
    LENIENT_INTERPRETER,
    STRICT_COMPLIANCE,
)
from schemas import AppealRuling, FinalDecision, parse_final_decision, parse_ruling
from states import AppealState

APPLICANT_PERSONA = (
    "你是报销申请人钱工的申辩代理。立场：主张争议单适用 POL-9.1 补开发票例外条款"
    "（连号重开、支出真实、新票已取得），请求按原始金额 80% 报销。"
    "用证据说话：货物验收、票据时间线、政策条文。对合规官的质疑逐条回应。"
)

OFFICER_PERSONA = (
    "你是财务合规官。立场：POL-7.2 是红线——报销单附的是已作废发票，且重开发票与"
    "验收单未随单提交，单据链不完整，维持整单驳回。警惕例外条款被滥用架空常态规则。"
    "对申辩代理的主张逐条质疑。"
)

RISK_PERSONAS: dict[str, str] = {
    LENIENT_INTERPRETER: (
        "你是政策宽松解释方：从立法本意看 POL-9.1 正是为真实支出的凭证瑕疵兜底，本案完全符合要件，支持按 80% 封顶报销。"
    ),
    STRICT_COMPLIANCE: (
        "你是严格合规方：无有效发票附单就是红线，例外条款不能架空 POL-7.2；除非单据链补齐，否则应维持驳回。"
    ),
    EXCEPTION_HANDLER: (
        "你是例外处理方：走例外流程——要求补充重开发票与验收单后放行，金额 clamp 到政策封顶，并留档备查。"
    ),
}

RULING_SYSTEM = """你是报销争议裁决官。基于政策结论与双方辩论史给出结构化裁决，只输出 JSON：
{"verdict": "...", "rationale": "...", "capped_amount_cents": ...}
verdict 五档：APPROVE / APPROVE_WITH_CAP / ESCALATE / REJECT / REVIEW。
capped_amount_cents 是封顶报销金额（整数分），无则省略该字段。"""

FINAL_SYSTEM = """你是报销争议终审官（最后防线）。基于裁决与三方风险意见给出终审决定，只输出 JSON：
{"verdict": "...", "summary": "...", "capped_amount_cents": ...}
verdict 五档同裁决官；你只在三方意见分歧或裁决依据不足时改判，否则维持。"""


def opponent_argument_or_opening(text: str, opponent: str) -> str:
    """对方最新论点；空串换成显式的「尚未发言」开场标记（对版 #1176，防虚构对方立场）。"""
    text = (text or "").strip()
    if text:
        return text
    return f"（{opponent}尚未发言——请亮出你的开场论点。）"


def _full_history(history: str, turn: str) -> str:
    return (history + "\n" + turn).strip("\n")


def create_policy_analyst(model: Any):
    """政策分析师节点工厂（对版 market_analyst）：bind_tools 过的模型 + ReAct 工具循环。"""

    async def policy_analyst(state: AppealState) -> dict:
        result = await model.ainvoke(state["messages"])
        report = "" if result.tool_calls else result.content  # 工具轮不写报告（产品同款）
        return {"messages": [result], "policy_report": report}

    return policy_analyst


def create_applicant_advocate(model: Any):
    """申辩人节点（bull 位）：1 次模型调用 + 手工回填 debate 全部 5 键。"""

    async def applicant_node(state: AppealState) -> dict:
        debate = state["debate"]
        history = debate.get("history", "")
        opponent = opponent_argument_or_opening(debate.get("current_speaker", ""), "合规官")
        response = await model.ainvoke(
            [
                {"role": "system", "content": APPLICANT_PERSONA},
                {
                    "role": "user",
                    "content": (
                        f"争议单 {state['claim_id']}（发票已作废，连号重开）。\n"
                        f"政策结论：{state['policy_report']}\n辩论史：\n{history}\n"
                        f"对方最新论点：{opponent}\n请给出你的本轮申辩。"
                    ),
                },
            ]
        )
        turn = f"{APPLICANT_ADVOCATE}（钱工代理）：{response.content}"
        return {
            "debate": {  # 嵌套 dict 无 reducer：必须回填全部键，漏一个就静默丢（§5）
                "history": _full_history(history, turn),
                "applicant_history": _full_history(debate.get("applicant_history", ""), turn),
                "office_history": debate.get("office_history", ""),
                "current_speaker": turn,
                "count": debate["count"] + 1,
            }
        }

    return applicant_node


def create_compliance_officer(model: Any):
    """合规官节点（bear 位）：与申辩人逐行同构——1 次调用 + 回填全部 5 键。"""

    async def officer_node(state: AppealState) -> dict:
        debate = state["debate"]
        history = debate.get("history", "")
        opponent = opponent_argument_or_opening(debate.get("current_speaker", ""), "申辩人")
        response = await model.ainvoke(
            [
                {"role": "system", "content": OFFICER_PERSONA},
                {
                    "role": "user",
                    "content": (
                        f"争议单 {state['claim_id']}（发票已作废，连号重开）。\n"
                        f"政策结论：{state['policy_report']}\n辩论史：\n{history}\n"
                        f"对方最新论点：{opponent}\n请给出你的本轮质证。"
                    ),
                },
            ]
        )
        turn = f"{COMPLIANCE_OFFICER}：{response.content}"
        return {
            "debate": {
                "history": _full_history(history, turn),
                "applicant_history": debate.get("applicant_history", ""),
                "office_history": _full_history(debate.get("office_history", ""), turn),
                "current_speaker": turn,
                "count": debate["count"] + 1,
            }
        }

    return officer_node


def create_risk_debater(model: Any, speaker: str):
    """风险三方节点工厂（对版 aggressive/conservative/neutral_debator）：1 次调用 + 回填 3 键。"""

    async def risk_node(state: AppealState) -> dict:
        risk = state["risk"]
        history = risk.get("history", "")
        ruling = state.get("ruling")  # NotRequired 键用 .get（缺席键直接下标是运行时炸弹）
        ruling_json = ruling.model_dump_json() if ruling is not None else "（初裁缺席）"
        response = await model.ainvoke(
            [
                {"role": "system", "content": RISK_PERSONAS[speaker]},
                {
                    "role": "user",
                    "content": (
                        f"裁决官初裁：{ruling_json}\n三方意见史：\n{history}\n请给出你（{speaker}）的本轮意见。"
                    ),
                },
            ]
        )
        turn = f"{speaker}：{response.content}"
        return {
            "risk": {  # 同一条手工回填纪律（键少一些，坑一样深）
                "history": _full_history(history, turn),
                "latest_speaker": turn,
                "count": risk["count"] + 1,
            }
        }

    return risk_node


def create_ruling_official(model: Any):
    """裁决官节点（deep 模型）：辩论史 → AppealRuling（解析失败回落 REVIEW 哨兵）。"""

    async def ruling_node(state: AppealState) -> dict:
        response = await model.ainvoke(
            [
                {"role": "system", "content": RULING_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"政策结论：{state['policy_report']}\n辩论史：\n{state['debate']['history']}\n请输出裁决 JSON。"
                    ),
                },
            ]
        )
        ruling: AppealRuling = parse_ruling(str(response.content))
        return {"ruling": ruling}

    return ruling_node


def create_final_judge(model: Any):
    """终审官节点（deep 模型）：初裁 + 三方意见 → FinalDecision（同款哨兵纪律）。"""

    async def final_node(state: AppealState) -> dict:
        response = await model.ainvoke(
            [
                {"role": "system", "content": FINAL_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"初裁：{_ruling_json(state)}\n三方风险意见：\n{state['risk']['history']}\n请输出终审 JSON。"
                    ),
                },
            ]
        )
        final: FinalDecision = parse_final_decision(str(response.content))
        return {"final": final}

    return final_node


def _ruling_json(state: AppealState) -> str:
    """初裁的 JSON 文本（NotRequired 键 .get 取，对版 pyright 纪律）。"""
    ruling = state.get("ruling")
    return ruling.model_dump_json() if ruling is not None else "（初裁缺席）"
