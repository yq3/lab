# 改造说明：TradingAgents（L4.2 辩论-裁决）

> 素材：L4.2 §3 Step 6 的真改造——把本课 ex2 的预算轴移植进真产品。两个改造：
> 轮次参数化（观察已有数据流）+ `max_debate_llm_calls` 预算封顶（加新代码）。
> 改造在**本地分支**完成，本页收口成可复现档案。固定五节
> （`tests/test_notes_meta.py` 按结构把关），`- TODO(改造)` 占位必须全部替换；
> 要求清单是任务卡，誊写结论时保留。

**改造要求（任务卡，写完保留）**

- 改造一 · 辩论轮次参数化：产品 `tradingagents/default_config.py` 的
  `max_debate_rounds`（env `TRADINGAGENTS_MAX_DEBATE_ROUNDS` 覆盖）流进
  `tradingagents/graph/conditional_logic.py` 的 `should_continue_debate`
  （`count >= 2 * max_debate_rounds` 计数终止）——配 rounds=1 / rounds=2 两态各跑
  一次，数 Bull/Bear 辩论段的模型调用次数（预期恰好 2N，§2.2「可预算」的实证）；
- 改造二 · 预算封顶（新代码）：给产品加 `max_debate_llm_calls`——在
  `default_config.py` 加配置项与 env 映射（`_ENV_OVERRIDES` 表加一行），贯穿到
  辩论节点或路由器（`conditional_logic.py` / `setup.py`），超限即停——本课 ex2
  `LLMCallBudget`（检查-放行-计数-委托）的真产品版；
- 跑通前提（env 最少四项）：`TRADINGAGENTS_LLM_PROVIDER=openai_compatible`、
  `TRADINGAGENTS_LLM_BACKEND_URL=<你的端点>`、`TRADINGAGENTS_DEEP_THINK_LLM`、
  `TRADINGAGENTS_QUICK_THINK_LLM`；
- 锚定 commit：`TauricResearch/TradingAgents@be952b8`；省 token 姿势：
  `TradingAgentsGraph(selected_analysts=("market",), debug=True, config=config)`；
- 两条纪律别踩：`max_recur_limit=100` 数 superstep 不数模型调用（§2.5 双预算轴，
  你的预算轴是新增不是替换）；改轮次/图形状会让旧 checkpoint 失效
  （`trading_graph.py#_run_signature`，#1089）——这是特性不是 bug，写进「为什么」。

## 改什么

改造一是**配置观察**（不改代码，配 env 两态跑）；改造二是**新代码**（写清：动哪
两个文件、加什么配置项、检查点放在路由器还是辩手节点、超限后路由到哪——对版
ex2 的「预算检查在放行前」）。两改造各一小段：路径 + 改点 + 前后值。

- TODO(改造)：改造一/二各一小段。

## 为什么

改造一验证「固定轮次 = 可预算可审计」（§2.2 的取向：路由器只数数，不问收敛）；
改造二补上产品的第二条成本轴——token 计费的世界里成本 ≈ 模型调用次数，
`max_recur_limit` 防死环、预算轴防账单，两条轴缺一不可（§2.5）。写清你的预期：
cap 恰好够 / 中途烧穿各是什么表现（对版 Step4 的 [2]/[3] 段）。

- TODO(改造)：每个改造一句动机 + 一句预期。

## 最小 diff

`git diff` 摘录（` ```diff ` 块）：改造二至少动 `default_config.py`（`_ENV_OVERRIDES`
加一行 + DEFAULT_CONFIG 加默认值）与 `conditional_logic.py`（或辩手节点）两处；
只贴动的那几行。

- TODO(改造)：贴 diff 摘录。

## 复现步骤

从干净克隆到两态对比的命令序列（bash 块分步走）：clone → `uv sync` → 配 env →
基线跑（rounds=1）→ 改 env 到 rounds=2 再跑 → 应用改造二的 diff → 配一个会烧穿
的 cap 再跑。每步一个检查点（如 debug 输出里 Bull/Bear 各发言几次）。

- TODO(改造)：编号步骤 1..N + 每步一个检查点。

## 证据

两态的辩论段调用计数（rounds=1 → 2 次、rounds=2 → 4 次）与烧穿表现
（`BudgetExceeded` 或路由提前终止的日志行），` ```text ` 块贴 3–5 行并圈出计数控；
截图另存 `notes/assets/`，贴不了图贴日志摘录。

- TODO(改造)：改造一/二各一段摘录 + 一句「变化在哪一行」。
