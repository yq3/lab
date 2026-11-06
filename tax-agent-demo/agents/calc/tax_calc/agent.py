"""计税 agent 的 deepagents 装配。

本 agent 展示的 deepagents 特性（subagent 侧从简，全特性装配示范在主 agent）：
- create_deep_agent 基础装配（model / system_prompt / tools）
- response_format：结构化计税结论（最终 state 的 structured_response，
  经 A2A 适配层序列化为 artifact 文本返回给主 agent）
"""

from __future__ import annotations

from deepagents import create_deep_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from shared.llm import build_chat_model
from tax_calc.tools import CALC_TOOLS

SYSTEM_PROMPT = """你是企业税务系统的计税 agent（税务计算团队维护），只负责计算与校验，不负责申报。

工作规范：
1. 计税前先 lookup_taxpayer_profile 拿到档案，再 get_tax_brackets 确认税率表。
2. 收入额折算口径：工资薪金全额；劳务报酬 ×80%；稿酬 ×80%×70%。扣除合计 = 基本减除费用 60000
   + 三险一金 + 专项附加扣除（仅限佐证材料齐全的项）+ 其他扣除。
3. calculate_income_tax 只负责"应纳税所得额 → 应纳税额"这一步，收入折算和扣除汇总由你完成。
4. 金额一律整数元。
5. 若用户要求校验扣除材料，用 verify_special_deductions；存在材料缺失项时明确列出，
   并说明这些项在当前计税中未计入（补齐材料后可重新计算）。
6. 最终回复必须给出结构化结论（各项金额、适用级距、应补/应退），解释要简明。"""


class TaxCalcResult(BaseModel):
    """综合所得年度汇算计税结论。"""

    taxpayer_id: str = Field(description="纳税人编号")
    taxpayer_name: str = Field(description="纳税人姓名")
    year: int = Field(description="税务年度")
    income_amount: int = Field(description="收入额合计（折算后，整数元）")
    total_deduction: int = Field(description="扣除合计（整数元）")
    taxable_income: int = Field(description="应纳税所得额（整数元）")
    tax_amount: int = Field(description="应纳税额（整数元）")
    prepaid_tax: int = Field(description="已预缴税额（整数元）")
    payable_or_refund: int = Field(description="应补(退)税额：正数=应补，负数=应退（整数元）")
    bracket_level: int = Field(description="适用税率级（1-7）")
    explanation: str = Field(description="计算过程简要说明（含收入折算与扣除明细）")
    warnings: list[str] = Field(default_factory=list, description="警示信息（如扣除材料缺失项）")


def build_graph(model: BaseChatModel | None = None) -> CompiledStateGraph:
    """构建计税 agent 图；model 可注入（测试用 fake，生产走端点中立工厂）。"""
    return create_deep_agent(
        name="tax_calc_agent",
        model=model or build_chat_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=CALC_TOOLS,
        response_format=TaxCalcResult,
    )
