"""L4.2 配置对象：辩论轮次、风险轮次、模型调用预算、deep/quick 双模型名。

对版 tradingagents/default_config.py（TauricResearch/TradingAgents@be952b8）：
- 产品的 max_debate_rounds=1 / max_risk_discuss_rounds=1 / max_recur_limit=100 对应本课
  AppealConfig 的 max_debate_rounds / max_risk_rounds 与 graph.py 的 RECURSION_LIMIT；
- 产品还有第二层 TRADINGAGENTS_MAX_DEBATE_ROUNDS 等 env 覆盖（配置三层：默认 → env → CLI），
  本课教学版收敛成一层 dataclass——ex1 练的就是「轮次从配置对象流进路由器」这条路；
- 产品的 max_recur_limit 数的是 superstep（图步数），不数模型调用——所以本课新增
  max_llm_calls：模型调用预算（None=不限），与 recursion_limit 是两条独立的预算轴
  （讲义 §2.5，ex2 / step2_budget.py 实测两条轴各烧各的）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppealConfig:
    """报销争议上诉图的全部旋钮（Java 对照：≈ immutable config bean / record）。

    frozen=True：装配时一次定型、运行期不可改——改轮次请换一个 config 对象重建图，
    而不是变异现役配置（产品把轮次折进 checkpoint 的图形状签名，改了签名旧检查点
    自动失效，trading_graph.py#_run_signature——同一条「配置即图形状」的纪律）。
    """

    max_debate_rounds: int = 1  # 申辩人⇄合规官：每轮双方各发言一次，终止计数 = 2 * 该值
    max_risk_rounds: int = 1  # 宽松/严格/例外：每轮三方各发言一次，终止计数 = 3 * 该值
    max_llm_calls: int | None = None  # 模型调用预算（None = 不限）；超限抛 budget.BudgetExceeded
    quick_model: str = "mock-quick"  # 便宜模型：分析师/辩手/风险三方（产品 quick_think_llm）
    deep_model: str = "mock-deep"  # 贵模型：裁决官/终审官（产品 deep_think_llm——只花在裁决）
