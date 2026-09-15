# 参考答案：ex1_extract（练习文件的完整解法——完成前别看）
"""extract_json：把模型的「花式包裹」剥成 dict。"""

from __future__ import annotations

import json
import re

SAMPLES: list[tuple[str, str]] = [
    ("干净的 JSON", '{"claim_id": "CLM-2026-0001", "verdict": "PASS", "reason": "明细合规"}'),
    ("```json 围栏", '```json\n{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT"}\n```'),
    ("无语言围栏", '```\n{"claim_id": "CLM-2026-0003", "verdict": "REJECT:INVALID_AMOUNT"}\n```'),
    ("散文夹带", '决策如下：{"claim_id": "CLM-2026-0001", "verdict": "PASS"} 请查收。'),
    ("根本没有 JSON", "我认为这张单据符合规定，可以直接通过。"),
]


def extract_json(text: str) -> dict:
    """三层剥壳：```json 围栏 → 无语言围栏 → 首尾大括号；全失败抛 ValueError。"""
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
