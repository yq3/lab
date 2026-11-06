"""mock 电子税务局：申报受理与状态查询（进程内存态，重启即清空）。

演示两个 tool-design 军规：
- 幂等键：同 idempotency_key 重复提交返回同一回执，不重复受理
- 异步任务语义：受理需 2 秒（模拟远端 job），提交后先"受理中"再"已受理"
"""

from __future__ import annotations

import time
import uuid
from typing import Any

# receipt_no -> submission
_SUBMISSIONS: dict[str, dict[str, Any]] = {}
# idempotency_key -> receipt_no
_IDEMPOTENT_INDEX: dict[str, str] = {}

SIMULATED_ACCEPT_DELAY_SECONDS = 2.0


def submit_return(return_data: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    """提交申报表。同幂等键重复提交返回既有回执（幂等）。"""
    existing_receipt = _IDEMPOTENT_INDEX.get(idempotency_key)
    if existing_receipt is not None:
        return {
            "duplicate": True,
            "receipt_no": existing_receipt,
            "message": f"该幂等键已受理过（回执 {existing_receipt}），未重复提交",
        }

    time.sleep(SIMULATED_ACCEPT_DELAY_SECONDS)  # 模拟远端受理耗时
    receipt_no = f"RCP-{uuid.uuid4().hex[:12].upper()}"
    _SUBMISSIONS[receipt_no] = {
        "receipt_no": receipt_no,
        "idempotency_key": idempotency_key,
        "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "已受理",
        "return_data": return_data,
    }
    _IDEMPOTENT_INDEX[idempotency_key] = receipt_no
    return {"duplicate": False, "receipt_no": receipt_no, "message": "申报提交成功，已受理"}


def query_submission(receipt_no: str) -> dict[str, Any] | None:
    """按回执号查询申报状态。"""
    submission = _SUBMISSIONS.get(receipt_no)
    if submission is None:
        return None
    return {k: v for k, v in submission.items() if k != "return_data"}


def reset() -> None:
    """清空全部受理记录（测试隔离用）。"""
    _SUBMISSIONS.clear()
    _IDEMPOTENT_INDEX.clear()
