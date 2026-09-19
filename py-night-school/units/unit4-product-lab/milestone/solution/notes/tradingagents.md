# 改造说明：TradingAgents（L4.2 辩论-裁决）

**改造要求（任务卡）**

- [x] 改造一 · 轮次参数化两态观察（`max_debate_rounds`，零代码）；
- [x] 改造二 · `max_debate_llm_calls` 预算封顶（新代码，贯穿 default_config → conditional_logic）；
- [x] env 四项配齐（TRADINGAGENTS_LLM_PROVIDER / _LLM_BACKEND_URL / _DEEP_THINK_LLM / _QUICK_THINK_LLM）；
- [x] 锚定 `TauricResearch/TradingAgents@be952b8`。

## 改什么

本地分支 `lab/debate-budget`（克隆后 checkout be952b8 起步）：

- 改造一 · 配置观察（不改代码）：`TRADINGAGENTS_MAX_DEBATE_ROUNDS=1` 与 `=2` 两态各跑
  一次——产品 `default_config.py` 的 `max_debate_rounds` 经 `_ENV_OVERRIDES` 表流进
  `conditional_logic.py#should_continue_debate` 的 `count >= 2 * max_debate_rounds` 终止，
  这条数据流是现成的（ex1 的对版原件），这里只配 env 两态数调用；
- 改造二 · 新代码：加 `max_debate_llm_calls`——两处落点：
  1. `tradingagents/default_config.py`：`_ENV_OVERRIDES` 表加一行
     `"TRADINGAGENTS_MAX_DEBATE_LLM_CALLS": "max_debate_llm_calls"`，
     `DEFAULT_CONFIG` 加默认值 `None`（None = 不限，向后兼容）；
  2. `tradingagents/graph/conditional_logic.py#should_continue_debate`：轮次终止之后
     加预算终止——辩论 state 的 `count` 每次发言 +1（每次发言恰是一次模型调用），
     `count >= max_debate_llm_calls` 即提前路由到 Research Manager。

## 为什么

- 改造一验证「固定轮次 = 可预算可审计」（§2.2：路由器只数数不问收敛）——rounds=1/2
  两态的辩论段调用次数应恰好 2N（2 → 4）；
- 改造二补上产品缺的第二条成本轴（§2.5）：`max_recur_limit=100` 数 superstep（防死环），
  不数模型调用（防账单）——token 计费的世界里两条轴缺一不可。这是本课 ex2
  `LLMCallBudget`「检查在放行前、超卖为零」的真产品移植。

预期：cap 恰好够（=2N）时零感知跑完；cap 中途烧穿时辩论提前终止进裁决（产品里没有
异常路径——路由器直接改道，比机制件「抛 BudgetExceeded」更贴图引擎的语义）；改轮次
后旧 checkpoint 失效（`_run_signature` 把图形状折进 thread_id，#1089）——重开新
thread 跑，这是特性不是 bug。

## 最小 diff

（示意——以你克隆里的实际代码为准；产品实际代码的换行与注释有出入。）

```diff
--- a/tradingagents/default_config.py
+++ b/tradingagents/default_config.py
@@
     "TRADINGAGENTS_MAX_DEBATE_ROUNDS":    "max_debate_rounds",
+    "TRADINGAGENTS_MAX_DEBATE_LLM_CALLS": "max_debate_llm_calls",
@@
     "max_debate_rounds": 1,
+    "max_debate_llm_calls": None,  # None = 不限；设为正整数后辩论段超限即停
```

```diff
--- a/tradingagents/graph/conditional_logic.py
+++ b/tradingagents/graph/conditional_logic.py
@@ def should_continue_debate(self, state):
         if (
             state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
         ):
             return "Research Manager"
+        if (
+            self.max_debate_llm_calls is not None
+            and state["investment_debate_state"]["count"] >= self.max_debate_llm_calls
+        ):
+            return "Research Manager"  # 预算封顶：数的是模型调用（每次发言一调），超限即停
```

（setup.py 把 config 的轮次传进 ConditionalLogic 的地方同样要带 max_debate_llm_calls——
对照它现在怎么传 max_debate_rounds，照抄一行。）

## 复现步骤

1. `git clone git@github.com:TauricResearch/TradingAgents.git`——检查点：
   `git log --oneline -1` 显示 be952b8（不是就 `git checkout be952b8`）；
2. `cd TradingAgents`；
3. `uv sync`——检查点：`uv run python -c "import tradingagents"` 不报错；
4. 配 env 四项（provider=openai_compatible + backend_url + deep/quick 两个模型名）；
5. `git switch -c lab/debate-budget`；
6. 基线（rounds=1）：`TRADINGAGENTS_MAX_DEBATE_ROUNDS=1`，跑仓库自带 `main.py`
   （省 token 姿势：`TradingAgentsGraph(selected_analysts=("market",), debug=True,
   config=config)`）——检查点：debug 输出 Bull/Bear 各 1 次，辩论段共 2 次调用；
7. rounds=2 再跑——检查点：辩论段共 4 次（2N 可预算的实证）；
8. 应用改造二的 diff——检查点：`TRADINGAGENTS_MAX_DEBATE_LLM_CALLS=6` 跑，
   辩论在第 6 次发言后直接进 Research Manager；`=None` 或不设时行为与基线一致。

## 证据

（范本注：真产品 debug 日志需自己端点真跑——本节用机制件输出做替身，同一机制的
离线版；交作业时换成你自己两态运行的日志摘录。）

改造一（轮次两态）的机制件替身（L4.2 `uv run python code/step1_debate_loop.py`）：

```text
[rounds=1 真图轨迹（终止计数 = 2*1 = 2）]
  模型调用: 2 次 = 恰好 2*rounds(2)——辩论段可预算的实证
[rounds=2 真图轨迹（终止计数 = 2*2 = 4）]
  模型调用: 4 次 = 恰好 2*rounds(4)——辩论段可预算的实证
```

指认：两态的调用计数差 2 → 4——轮次是配置，预算是算术。

改造二（预算烧穿）的机制件替身（L4.2 `uv run python code/step2_budget.py` 段[3]）：

```text
[3] cap=5（中途烧穿）
  BudgetExceeded: LLM 调用预算耗尽：limit=5, 已调用 5 次
  烧穿点: 第 6 次调用（风险辩论第 1 方发言被拒）——预算检查在放行前，已花的恰好 = cap
```

指认：已花的恰好 = cap、第 6 次在放行前被拒——「检查-放行-计数」的顺序就是纪律；
真产品版因落在路由器上，表现是「第 6 次发言不再发生、直接裁决」——贴你
`TRADINGAGENTS_MAX_DEBATE_LLM_CALLS=6` 那跑的 debug 摘录 3–5 行，圈出发言计数行。
