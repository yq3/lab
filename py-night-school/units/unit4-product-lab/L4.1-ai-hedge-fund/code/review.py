"""域模型——「报销初审层级投票」的三件套（对版 virattt/ai-hedge-fund@fc1bf25）。

产品的两个核心数据结构映射到报销初审域：

    Signal（hedge_fund/models.py）      -> Vote          一个检查员对一张报销单的一票
    CycleRecord（hedge_fund/pipeline/models.py）-> ReviewRecord  一张单的初审回执（全量真相）

Advice 沿用 Unit 3 四框架同题 demo 的统一输出契约（claim_id / decision / reason /
remaining_cents），金额一律整数「分」（宪法业务约定）。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from limits import ClampEvent

Decision = Literal["APPROVE", "REJECT", "ESCALATE"]


class Advice(BaseModel):
    """报销单初审结论（与 Unit 3 的 advice.py 同语义——明线延续）。"""

    claim_id: str = Field(description="报销单号，形如 CLM-2026-0001")
    decision: Decision = Field(description="APPROVE=建议通过；REJECT=建议拒绝；ESCALATE=转人工复核")
    reason: str = Field(description="枚举风格结论码：PASS / REJECT:<原因>（如 REJECT:INVOICE_INVALID）")
    remaining_cents: int = Field(ge=0, description="审查时点该部门剩余预算（分），快照的镜像")


class Vote(BaseModel):
    """一个检查员的一票——对版产品的 Signal（不设 extra="forbid"，与 Signal 同款宽容）。

    score 是带符号确信度：support 对应正、oppose 对应负、abstain 恒 0.0。
    metadata 承载审计四件：abstained（弃权标记——blend 剔除的依据）、
    prompt_key（缓存文件名）、claim_hash（快照内容哈希）、cached（本票是否来自缓存）。
    """

    checker: str = Field(description="检查员名，如 'compliance' / 'rules'（对版 Signal.model_name）")
    claim_id: str = Field(description="被审的报销单号（对版 Signal.ticker）")
    score: float = Field(ge=-1.0, le=1.0, description="确信度 [-1,1]（对版 Signal.value）")
    reasoning: str | None = Field(default=None, description="人类可读的投票理由——审计的主角")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewRecord(BaseModel):
    """一张报销单的初审回执——对版产品的 CycleRecord（「一个 tick 的完整真相」）。

    回执里每票带 reasoning 与 prompt_key（对版 StrategyRecord.signals 的留痕方式）、
    合成前后的金额（对版 target_weights / final_weights）、每一刀 clamp（对版 clamps）、
    最终建议。落盘这一份，事后就能回答「当时知道什么、谁投了什么、钱怎么被砍的」。
    """

    claim_id: str
    claim_hash: str = Field(description="快照内容哈希（对版 snapshot_hash）——回执与输入的绑定")
    votes: list[Vote] = Field(description="全部检查员的票（含弃权票）")
    conviction: float | None = Field(description="加权合成后的整体确信；None=没有任何有效票")
    amount_before_cents: int = Field(description="合成前金额：单据明细总额（分）")
    amount_after_cents: int = Field(description="clamp 后金额（分）——风控处置的结果")
    clamps: list[ClampEvent] = Field(default_factory=list, description="每一刀的审计事件")
    advice: Advice
