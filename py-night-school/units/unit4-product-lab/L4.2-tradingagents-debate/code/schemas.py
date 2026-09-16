"""L4.2 输出卫生：五档裁决 schema + 脏字段归一 + REVIEW 哨兵（产品两大「硬」保护的对版）。

对版 TauricResearch/TradingAgents@be952b8：
- agents/schemas.py#_coerce_optional_float（#1058/#1288）：LLM 会往可选数值字段里填
  占位串（"N/A"）、百分比（"15%"）、人写货币（"$1,234.50"）。产品的取向：百分比
  **绝不冒充绝对数额**（把 "15%" 读成 15 会给 600 美元的股票挂 15 美元止损）——与
  占位串一样丢弃为 null；带格式的价格折成数字；其余交给 pydantic。
- graph/signal_processing.py#process_signal（#1170）：解析失败的决策返回哨兵值 REVIEW
  而不是捏造一个 Hold——失败必须可见，绝不静默降级成「可执行的中性」。

本课对版差异（诚实声明）：产品是 float 价格字段，"$1,234.50" 折成 1234.5；本课业务约定
金额一律整数**分**（夜校宪法），带小数的货币串无法安全定单位（元还是分？）——与百分比
同样「不可抢救」丢弃为 None，只有整数形态（"12,345" / "¥12,345"）才折成整数分。

Java 对照：field_validator ≈ Spring 的 @JsonComponent 反序列化钩子 / Bean Validation
自定义 @Constraint；哨兵值 REVIEW ≈ 枚举里预留的 UNKNOWN 档——「解析失败」本身是
一等业务状态，不是异常路径。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

Verdict = Literal["APPROVE", "APPROVE_WITH_CAP", "ESCALATE", "REJECT", "REVIEW"]

# LLM 常见的占位串（对版 schemas.py#_NULLISH_FLOAT，大小写不敏感）
_NULLISH_CENTS = {"", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown", "不适用"}


def _coerce_optional_cents(value: object) -> object:
    """归一 LLM 填进整数分字段的脏值（对版 _coerce_optional_float 的整数分版）。

    四种形态：占位串 → None；百分比（"85%"）→ None——绝不冒充金额；带小数/货币符号的
    人写金额（"¥1,234.50"）→ None——整数分字段无法安全定单位，同属「不可抢救」；
    整数形态（"12,345" / "¥12,345" / " 4000 "）→ 折成 int；其余认不出的串（乱码）→
    None——宁可丢掉一个字段，绝不猜它是什么单位。非字符串值原样放行给 pydantic。
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.lower() in _NULLISH_CENTS or text.endswith("%"):
        return None
    cleaned = text.replace(",", "").lstrip("¥$€£").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None  # "1234.50" 这类带小数的货币串：无法安全定单位 → 丢弃为 None


class AppealRuling(BaseModel):
    """裁决官的结构化裁决（对版 ResearchManager 的 ResearchPlan：5 档 + rationale）。"""

    verdict: Verdict
    rationale: str
    capped_amount_cents: int | None = Field(default=None, description="封顶报销金额（整数分）")

    @field_validator("capped_amount_cents", mode="before")
    @classmethod
    def _dirty_cents_to_none(cls, v: object) -> object:
        return _coerce_optional_cents(v)


class FinalDecision(BaseModel):
    """终审官的最终决定（对版 PortfolioManager 的 PortfolioDecision）。"""

    verdict: Verdict
    summary: str
    capped_amount_cents: int | None = Field(default=None, description="终审封顶金额（整数分）")

    @field_validator("capped_amount_cents", mode="before")
    @classmethod
    def _dirty_cents_to_none(cls, v: object) -> object:
        return _coerce_optional_cents(v)


def parse_ruling(text: str) -> AppealRuling:
    """解析裁决官输出；**任何解析/校验失败都返回 REVIEW 哨兵，绝不捏造可执行结论**。

    对版 signal_processing.py：不可识别的决策 → REVIEW（进人工复核队列），而不是降级成
    REJECT/APPROVE 之类「看起来能执行」的档位。合法 JSON 里的脏字段由 _coerce 归一兜住，
    一个坏字段不毁整份裁决（产品同款取向：null 掉坏字段，保住整个结构化调用）。
    """
    try:
        return AppealRuling.model_validate_json(text.strip())
    except ValidationError as exc:
        return AppealRuling(verdict="REVIEW", rationale=f"裁决输出不可解析，转人工复核：{str(exc)[:120]}")


def parse_final_decision(text: str) -> FinalDecision:
    """终审输出的同款解析（哨兵纪律与 parse_ruling 完全一致）。"""
    try:
        return FinalDecision.model_validate_json(text.strip())
    except ValidationError as exc:
        return FinalDecision(verdict="REVIEW", summary=f"终审输出不可解析，转人工复核：{str(exc)[:120]}")
