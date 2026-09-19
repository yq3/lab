# 练习 3（单变量编辑约束：只改本文件 TODO 标注区**与所需的顶部 import**，其余不要动）
"""哨兵 + 脏字段归一：补全 _coerce_optional_cents 与 parse_ruling——输出卫生的两道闸。

对版改造（产品仅有的两处「硬」保护）：
- tradingagents/agents/schemas.py#_coerce_optional_float（#1058/#1288）：LLM 会往可选数值
  字段里填占位串（"N/A"）、百分比（"15%"）、人写货币（"$1,234.50"）。产品取向：百分比
  **绝不冒充绝对数额**；本课是整数分字段——带小数的货币串同样无法安全定单位，同判不可
  抢救 → None；整数形态（"12,345"/"¥12,345"）才折成整数分；认不出的串宁可丢字段不猜单位。
- tradingagents/graph/signal_processing.py（#1170）：解析失败的决策返回哨兵值 REVIEW，
  绝不捏造一个「看起来能执行」的中性结论——失败必须可见。

完成判据：uv run pytest exercises/test_ex3.py 全绿——三个测试（参数化共 13 例断言）：
  脏字段归一 8 例：占位串 ×2 / 百分比 / 带小数货币串 / 乱码 → None；
                   逗号整数 / 带币符整数 / 纯数字串 → 整数分；
  parse_ruling 4 例：非 JSON / 坏 verdict 档 / 断裂 JSON / 乱码 → verdict == "REVIEW"；
  合法 JSON 1 例：脏金额字段被归一、裁决本体存活（一个坏字段不毁整份裁决）。
TODO 所需的顶部 import：
  from pydantic import ValidationError  # ex3-b 的 except 子句要用（骨架没预置，填完才用）
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

Verdict = Literal["APPROVE", "APPROVE_WITH_CAP", "ESCALATE", "REJECT", "REVIEW"]

# LLM 常见的占位串（对版 schemas.py#_NULLISH_FLOAT，大小写不敏感）
_NULLISH_CENTS = {"", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown", "不适用"}


def _coerce_optional_cents(value: object) -> object:
    # TODO(ex3-a): 四种形态各怎么处理——占位串？百分比（为什么必须丢）？带小数的货币串
    # （整数分字段定得了单位吗）？整数形态的串（"12,345"/"¥12,345"/" 4000 "）？
    # 认不出的串呢（宁可丢字段还是猜单位）？非字符串值放行即可。
    raise NotImplementedError("TODO(ex3-a): 补全脏字段归一")


class AppealRuling(BaseModel):
    """裁决 schema：verdict 五档（REVIEW 是哨兵档）+ rationale + 可选封顶金额（整数分）。"""

    verdict: Verdict
    rationale: str
    capped_amount_cents: int | None = None

    @field_validator("capped_amount_cents", mode="before")
    @classmethod
    def _dirty_cents_to_none(cls, v: object) -> object:
        return _coerce_optional_cents(v)


def parse_ruling(text: str) -> AppealRuling:
    # TODO(ex3-b): 成功时走哪条路（注意先 strip）？失败（校验异常——顶部的 docstring 点名了
    # 要补的 import）时返回什么——「绝不捏造」意味着 verdict 得是哪一档？哨兵裁决的
    # rationale 要让人工看得懂为什么进复核（验收对这段文字有断言）。
    raise NotImplementedError("TODO(ex3-b): 补全解析与哨兵回落")
