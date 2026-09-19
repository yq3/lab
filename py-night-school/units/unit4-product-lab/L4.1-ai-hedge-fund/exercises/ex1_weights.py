# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体**与所需的顶部 import**，其余不要动）
"""blend 加权投票：把若干检查员的票合成为一个整体确信度。

对版产品 hedge_fund/portfolio/construction.py#blend_signals（单票据版）：

    conviction = sum(w_i * score_i) / sum(w_i)     只数「投了票」的检查员

考察点三件事：
- 加权合成的算术（权重表是话语权，纯 Python 数字进出）；
- 弃权票从分子**和分母**同时剔除：「没意见」不等于「意见：中性」；
- 全弃权 / 权重全零的显式边界：conviction 取 None，让下游转人审（ESCALATE）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——五个测试：
  加权平均的数学精确断言（含小数）；
  一票弃权时分子分母各少一项（弃权者的权重完全不参与）；
  全弃权 -> conviction 是 None（不是 0.0）；
  权重全零 -> 分母为零，同样是 None；
  meta：同一组票换权重表，结果必须改变。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from review import Vote


class BlendOutcome(BaseModel):
    """一次合成的结果（讲义 blend.BlendResult 的练习版同构体）。"""

    conviction: float | None = Field(description="加权确信 [-1,1]；None=没有任何有效票")
    voters: list[str] = Field(description="投了票的检查员（进了分子与分母）")
    abstained: list[str] = Field(description="弃权的检查员（分子分母同剔）")


def weighted_vote(votes: list[Vote], weights: dict[str, float]) -> BlendOutcome:
    """把一队检查员的票合成一个确信度（对版 blend_signals 的加权平均语义）。

    votes 里每票的 checker 是 weights 的 key；弃权标记在 vote.metadata["abstained"]。
    """
    # TODO(ex1): 逐票累加时分子加什么、分母加什么？弃权票在哪一步跳过——
    #   跳过它时分子分母各自少了什么？分母为零时 conviction 该取什么值，
    #   才能让下游「显式转人审」而不是「假装中性」？
    raise NotImplementedError("TODO(ex1): 补全加权合成")
