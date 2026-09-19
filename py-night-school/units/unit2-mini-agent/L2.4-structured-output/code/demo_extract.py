"""实验①：extract_json 五连测——模型的「花式包裹」全景。

全部离线：五个真实会遇到的输出形态，三层剥壳逐一过招。
"""

from __future__ import annotations

from structured import extract_json

SAMPLES: list[tuple[str, str]] = [
    ("干净的 JSON", '{"claim_id": "CLM-2026-0001", "verdict": "PASS", "reason": "明细合规"}'),
    (
        "```json 围栏",
        '```json\n{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT", "reason": "单笔超限"}\n```',
    ),
    ("无语言围栏", '```\n{"claim_id": "CLM-2026-0003", "verdict": "REJECT:INVALID_AMOUNT", "reason": "负数金额"}\n```'),
    (
        "散文夹带",
        '好的，这是我的决策：{"claim_id": "CLM-2026-0001", "verdict": "PASS", "reason": "三笔均合规"} 请查收。',
    ),
    ("根本没有 JSON", "我认为这张单据符合规定，可以直接通过。"),
]

if __name__ == "__main__":
    for label, text in SAMPLES:
        try:
            payload = extract_json(text)
            print(f"[{label}] -> claim_id={payload['claim_id']}  verdict={payload['verdict']}")
        except ValueError as exc:
            print(f"[{label}] -> ValueError: {exc}")
