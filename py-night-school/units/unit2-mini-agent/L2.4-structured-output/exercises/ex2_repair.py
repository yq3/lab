# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体，其余不要动）
"""校验错误回喂重试：ask_structured 修复循环。

考察点：循环三步——模型产出先入史（好坏都入）、再解析校验、失败则回喂修复指令；
重试预算耗尽抛 DecisionError（fail-loud，别把半成品当结论）；
返回 (决策对象, 完整历史) 让审计能看到每一轮失败。

完成判据：uv run pytest exercises/test_ex2.py 全绿——
  第 2 次尝试拿到合法对象且历史 5 条角色序列精确；耗尽时恰好 attempts 次调用。
提示：except (ValueError, ValidationError) 一个口接两种伤；成功路径也要先入史再校验。
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

SYSTEM = (
    "你是财务预审决策器。只输出一个 JSON 对象（claim_id / verdict / reason），"
    "verdict 只能是 PASS 或 REJECT:INVALID_AMOUNT / REJECT:ITEM_OVER_LIMIT / REJECT:TOTAL_OVER_LIMIT。"
)


class Decision(BaseModel):
    """给定：决策模型（本题主角是循环，模型白给）。"""

    claim_id: str = Field(pattern=r"^CLM-\d{4}-\d{4}$")
    verdict: str = Field(pattern=r"^(PASS|REJECT:(INVALID_AMOUNT|ITEM_OVER_LIMIT|TOTAL_OVER_LIMIT))$")
    reason: str = Field(min_length=1)


class DecisionError(Exception):
    """重试耗尽。"""


def extract_json(text: str) -> dict:
    """给定：L2.4 讲义同款三层剥壳（ex1 你已写过一遍，这里白给）。"""
    import json
    import re

    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text.strip(), re.DOTALL)
    candidate = fenced.group(1) if fenced else text.strip()
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("输出里找不到 JSON 对象")
    return json.loads(candidate[start : end + 1])


class ScriptedLite:
    """给定：脚本模型（L2.3 的极简版，只出 content）。"""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.request_count = 0

    async def complete(self, messages: Sequence[dict]) -> str:
        self.request_count += 1
        return self._outputs.pop(0)


async def ask_structured(model: ScriptedLite, question: str, attempts: int = 3) -> tuple[Decision, list[dict]]:
    """修复循环：返回 (决策, 完整历史)；attempts 次耗尽抛 DecisionError。"""
    # TODO(ex2): for 循环 attempts 次——模型产出先入史，再 extract_json + model_validate
    # TODO(ex2): 失败：把错误翻译成修复指令（role=user，点名字段）追加进历史
    # TODO(ex2): 耗尽：raise DecisionError（信息里带 attempts 次数）
    raise NotImplementedError("TODO(ex2): 补全 ask_structured")
