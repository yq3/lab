"""Step1 加权合成的权重语义（零模型调用）——手工票演示 blend.weighted_vote。

三幕各答一个问题：
1) 权重是什么：同样一组票，换一张权重表，合成结果就变（话语权表）；
2) 弃权怎么算：从分子**和分母**同时剔除——对照「把弃权当 0 分」的错误算法，
   看被捏造的中性稀释了多少确信；
3) 全弃权是什么：conviction=None（不是 0.0）——显式边界，下游据此转人审。
"""

from __future__ import annotations

from blend import weighted_vote
from review import Vote


def vote(checker: str, score: float, abstained: bool = False) -> Vote:
    """手工造一票（讲义用；metadata['abstained'] 是 blend 剔除的依据）。"""
    metadata = {"abstained": True} if abstained else {}
    return Vote(checker=checker, claim_id="CLM-STEP1", score=score, reasoning="手工票", metadata=metadata)


def main() -> None:
    print("== Step1 层级投票的权重语义（零模型调用） ==")
    votes = [
        vote("compliance", 0.8),
        vote("budget", -0.6),
        vote("invoice", 0.9),
        vote("rules", 0.0, abstained=True),
    ]
    weights = {"compliance": 1.0, "budget": 0.5, "invoice": 1.0, "rules": 1.5}

    print("[一] 加权合成：conviction = sum(w·score) / sum(w)，弃权票分子分母同剔")
    result = weighted_vote(votes, weights)
    print("  votes      : compliance +0.80 / budget -0.60 / invoice +0.90 / rules 弃权")
    print(f"  weights    : {weights}")
    print(f"  conviction = (1.0*0.8 + 0.5*(-0.6) + 1.0*0.9) / (1.0+0.5+1.0) = {result.conviction:.4f}")
    print(f"  voters={result.voters}  abstained={result.abstained}")

    print("[二] 对照错误算法：把弃权当 0 分计入分母（捏造中性）")
    wrong = (1.0 * 0.8 + 0.5 * -0.6 + 1.0 * 0.9 + 1.5 * 0.0) / 4.0
    print(f"  错误算法 conviction = {wrong:.4f} <- 一个没投票的检查员稀释了 0.16 的确信")

    print("[三] 全弃权：显式边界，不捏造中性")
    all_abstain = weighted_vote(
        [vote("compliance", 0.0, abstained=True), vote("budget", 0.0, abstained=True)],
        weights,
    )
    print(f"  conviction = {all_abstain.conviction}  <- None 而非 0.0：pipeline._decide 据此 ESCALATE 转人审")

    print("[四] 权重即话语权：同一组票，把 budget 的权重 0.5 抬到 3.0")
    heavy = weighted_vote(votes, {**weights, "budget": 3.0})
    print(f"  conviction = (0.8 + 3.0*(-0.6) + 0.9) / 5.0 = {heavy.conviction:.4f}  <- 反对票拿到了话语权")
    print("  产品对应物：mandate YAML 里的 model_weights（deep-value.yaml 给 graham 2.0 同款操作）")


if __name__ == "__main__":
    main()
