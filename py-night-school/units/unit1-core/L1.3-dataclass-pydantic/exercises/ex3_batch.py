# 练习 3（单变量编辑约束：只改 TODO 标注的两处，其余不要动）
"""嵌套模型 + 替代构造——model_dump 的输出结构是最终判据。

场景：周报销汇总。WeeklyBatch.items 是 ClaimItem（嵌套模型）列表；
from_lines() 是替代构造（Java 静态工厂的对应物）：把 ["餐饮|3500", "交通|1200"]
这样的「类目|金额分」文本行解析成嵌套模型。

ClaimItem 已给全（含约束）。你要完成：
  TODO(ex3a)：report_id 的 pattern 约束（^RPT-\\d{4}-W\\d{2}$，如 RPT-2026-W37）；
  TODO(ex3b)：from_lines 的函数体——解析 + 转发给 cls(...) 构造。
      解析规则：每行按 "|" 拆两段（拆不出两段时让 split 解包的 ValueError 自然抛出即可）；
      金额段转 int；类目为空、金额非正数都不用手动判断——交给 ClaimItem 的约束在构造时拒。
完成后：uv run pytest exercises/test_ex3.py 全绿。
"""

from pydantic import BaseModel, Field


class ClaimItem(BaseModel):
    """单条明细：类目非空、金额为正整数分。"""

    category: str = Field(min_length=1)
    amount_cents: int = Field(gt=0)


class WeeklyBatch(BaseModel):
    """周报销汇总（嵌套模型）。"""

    report_id: str  # TODO(ex3a): 加 pattern 约束
    submitted_by: str = Field(min_length=1)
    items: list[ClaimItem] = Field(default_factory=list)

    @classmethod
    def from_lines(cls, report_id: str, submitted_by: str, lines: list[str]) -> "WeeklyBatch":
        """替代构造："餐饮|3500" 文本行 -> ClaimItem 列表 -> WeeklyBatch。

        TODO(ex3b): 实现函数体后删除 raise。
        """
        raise NotImplementedError("TODO(ex3b): 解析每行并转交给 cls(...) 构造")
