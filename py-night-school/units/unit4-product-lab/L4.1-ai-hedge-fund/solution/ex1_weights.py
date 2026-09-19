# 参考答案：ex1_weights（练习文件的完整解法——完成前别看）
"""blend 加权投票：把若干检查员的票合成为一个整体确信度。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from review import Vote


class BlendOutcome(BaseModel):
    """一次合成的结果（讲义 blend.BlendResult 的练习版同构体）。"""

    conviction: float | None = Field(description="加权确信 [-1,1]；None=没有任何有效票")
    voters: list[str] = Field(description="投了票的检查员（进了分子与分母）")
    abstained: list[str] = Field(description="弃权的检查员（分子分母同剔）")


def weighted_vote(votes: list[Vote], weights: dict[str, float]) -> BlendOutcome:
    """把一队检查员的票合成一个确信度（对版 blend_signals 的加权平均语义）。"""
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
    return BlendOutcome(conviction=conviction, voters=voters, abstained=abstained)
