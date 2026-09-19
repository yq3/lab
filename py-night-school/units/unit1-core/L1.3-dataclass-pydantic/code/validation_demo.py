"""故意喂非法数据，读懂 ValidationError 的完整报错。

运行：uv run python code/validation_demo.py
输出与讲义 §3 Step 4 的解读一一对应：每条错误 = 位置（loc）+ 类型（type）+ 原因（msg）+ 原始输入（input）。
"""

from pydantic import ValidationError

from claims import ClaimBatch

# 第二张单留了三处伤：单号格式错、金额为负、提交人为空串
bad_batch = {
    "batch_id": "BATCH-2026-09",
    "claims": [
        {"claim_id": "CLM-2026-0001", "items_cents": [1200, 3500], "submitter": "王工"},
        {"claim_id": "bad-id", "items_cents": [8800, -1], "submitter": ""},
    ],
}

try:
    ClaimBatch.model_validate(bad_batch)
except ValidationError as exc:
    # exc 本身就是「错误清单」：exc.errors() 是 list[dict]，print(exc) 是排好版的多行报告
    print(exc)
    print(f"共 {exc.error_count()} 处错误（上面每一行小标题都是一处）")
