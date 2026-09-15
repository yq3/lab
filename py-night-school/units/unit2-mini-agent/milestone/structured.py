"""结构化输出：把模型的自由文本变成带 schema 的对象。

三种失败各有各的拦法：
  围栏/杂物   → extract_json 三层剥壳（fence → fence-less → 首尾大括号）
  值域越界   → Literal verdict + Field 约束（ValidationError 拦在构造那一刻，L1.3）
  重试耗尽   → StructuredOutputError（fail-loud，别把半成品当结论用）

修复循环的形状：解析/校验失败 → 把「模型的坏产出 + 错误说明」都追加进历史再问一次——
错误信息是给模型的修复指令（L2.2 的纪律从工具层搬到输出层）。
端点中立说明：response_format=json_schema 这类「端点侧约束」各家支持不一，
本课用「prompt 声明 + 解析校验 + 回喂重试」的通用方案；端点侧约束见 §2.6 的对照表。
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from model import ModelClient

REJECT_REASONS = ("INVALID_AMOUNT", "ITEM_OVER_LIMIT", "TOTAL_OVER_LIMIT")
Verdict = Literal["PASS", "REJECT:INVALID_AMOUNT", "REJECT:ITEM_OVER_LIMIT", "REJECT:TOTAL_OVER_LIMIT"]

SYSTEM_DECISION = (
    "你是财务预审决策器。只输出一个 JSON 对象，不要围栏、不要解释：\n"
    '{"claim_id": "CLM-YYYY-NNNN", "verdict": "PASS 或 REJECT:<原因>", "reason": "一句话理由"}\n'
    "verdict 的合法值（共 4 个）：PASS、REJECT:INVALID_AMOUNT、"
    "REJECT:ITEM_OVER_LIMIT、REJECT:TOTAL_OVER_LIMIT。"
)


class PreapprovalDecision(BaseModel):
    """预审决策单：agent 的正式产出物（给下游程序消费，不是给人读的散文）。"""

    claim_id: str = Field(pattern=r"^CLM-\d{4}-\d{4}$")
    verdict: Verdict = Field(description="PASS 或 REJECT:<INVALID_AMOUNT|ITEM_OVER_LIMIT|TOTAL_OVER_LIMIT>")
    reason: str = Field(min_length=1, description="人话理由，给审计看")
    reviewer: str = "night-school-agent"  # 有默认值 → 不进 required（L2.2 讲过的漂移点）


class StructuredOutputError(Exception):
    """重试耗尽仍拿不到合法对象——半成品不许当结论用，fail-loud。"""


def extract_json(text: str) -> dict:
    """从模型输出里剥出 JSON 对象：三层剥壳，全失败抛 ValueError。

    第 1 层 ```json 围栏；第 2 层无语言标注的 ``` 围栏；第 3 层首尾大括号（夹在散文里也认）。
    """
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    candidate = fenced.group(1) if fenced else stripped
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"输出里找不到 JSON 对象: {text[:50]!r}")
    try:
        return json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 语法错误: {exc.msg} (第 {exc.lineno} 行第 {exc.colno} 列)") from exc


def feedback_message(error: Exception) -> dict:
    """把解析/校验错误翻译成给模型的修复指令（role=user）。"""
    if isinstance(error, ValidationError):
        details = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in error.errors())
    else:
        details = str(error)
    return {
        "role": "user",
        "content": (
            f"上一次输出不是合法的决策 JSON（{details}）。"
            "请重新输出：只一个 JSON 对象，不要围栏不要解释；"
            "字段 claim_id（形如 CLM-2026-0001）、verdict（合法值见 system）、"
            "reason（一句话理由）。"
        ),
    }


async def ask_structured(
    client: ModelClient,
    question: str,
    attempts: int = 3,
    system: str = SYSTEM_DECISION,
) -> tuple[PreapprovalDecision, list[dict]]:
    """问答并修复（T2）：直到拿到合法 PreapprovalDecision 或重试耗尽。

    返回 (决策对象, 完整消息史)——历史里能看到每一轮失败的产出与修复指令（审计价值）。
    """
    # TODO(t2): 组装初始 messages（system + user 两条件）
    # TODO(t2): for 循环 attempts 次——client.complete(messages, tools=[]) 取 content
    # TODO(t2): 模型产出先入史（好坏都入）；extract_json + model_validate，一个 except 接两种伤
    # TODO(t2): 失败 -> messages.append(feedback_message(exc))；耗尽 -> raise StructuredOutputError（带次数）
    raise NotImplementedError("TODO(t2): 补全 ask_structured")
