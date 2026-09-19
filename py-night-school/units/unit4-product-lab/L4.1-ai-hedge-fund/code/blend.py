"""加权合成——把检查员的票算术地合成一个确信度（对版 hedge_fund/portfolio/construction.py#blend_signals）。

产品纪律逐条映射到单票据版：
- 纯函数、零 I/O：同样的票必然合成同样的确信——「共识靠算术，不靠对话」；
- 弃权票（metadata["abstained"] is True）从分子**和分母**同时剔除：
  「没意见」不能冒充「意见：中性」（对版 abstained signal 的失败契约）；
- 全弃权 / 权重全零 → conviction=None：显式边界，交给下游决定转人审（ESCALATE），
  绝不捏造一个 0.0 的「假中性」。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from review import Vote


class BlendResult(BaseModel):
    """一次合成的结果（对版 BlendResult 的单票据版）。"""

    conviction: float | None = Field(description="加权确信 [-1,1]；None=没有任何有效票")
    voters: list[str] = Field(description="投了票的检查员（进了分子分母）")
    abstained: list[str] = Field(description="弃权的检查员（分子分母同剔）")


def weighted_vote(votes: list[Vote], weights: dict[str, float]) -> BlendResult:
    """加权平均：conviction = sum(w_i * score_i) / sum(w_i)，只数投了票的检查员。

    weights 是检查员名 -> 合成权重（对版 StrategySpec.model_weights：mandate YAML 的一级字段，
    改权重=改话语权，不需要动任何代码）。
    """
    weighted_sum = 0.0
    weight_total = 0.0
    voters: list[str] = []
    abstained: list[str] = []
    for vote in votes:
        if vote.metadata.get("abstained") is True:
            abstained.append(vote.checker)  # 分子分母都不算它
            continue
        w = weights[vote.checker]
        weighted_sum += w * vote.score
        weight_total += w
        voters.append(vote.checker)
    conviction = weighted_sum / weight_total if weight_total > 0 else None
    return BlendResult(conviction=conviction, voters=voters, abstained=abstained)
