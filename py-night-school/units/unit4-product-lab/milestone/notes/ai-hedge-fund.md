# 改造说明：ai-hedge-fund（L4.1 层级投票）

> 素材：L4.1 §3 Step 6 的可选加餐——在你自己的克隆上真跑产品，做两个观察改造。
> 改造在**本地分支**完成（如 `git switch -c lab/persona-and-weights`），本页把它收口成
> 可复现档案。固定五节（`tests/test_notes_meta.py` 按结构把关），`- TODO(改造)` 占位
> 必须全部替换；下面的要求清单是任务卡，誊写结论时保留。

**改造要求（任务卡，写完保留）**

- 改造 A · 改人格 prompt：编辑 `hedge_fund/signals/buffett.py` 的 system prompt
  （例如把「估值」检查项挪到检查清单第一位），重跑对比 buffett 的 Signal reasoning
  变不变——「人格 = 一段 prompt」的直接证据（L4.1 §2.1）；
- 改造 B · 改话语权：编辑 mandate YAML 里某个 model 的 `weight:`（参照
  `hedge_fund/strategies/deep-value.yaml` 给 graham 2.0 的写法），重跑看合成 conviction
  怎么动——Step1 第 [四] 幕（权重 0.5→3.0 翻转结论）的真产品版；
- 跑通前提（env 四变量，PowerShell 用 `$env:` 语法）：`FINANCIAL_DATASETS_API_KEY`
  （行情数据）、`HEDGE_FUND_LLM_MODEL`（选 registry 里 provider=OpenAI 的 id，如
  gpt-5.6——未登记的 id 默认走 Anthropic 传输）、`OPENAI_API_KEY`、`OPENAI_API_BASE`
  （覆盖传输地址，`llm/client.py` 只在这一处读它）；
- 锚定 commit：`virattt/ai-hedge-fund@fc1bf25`（与讲义 §6 源码路标同源）；
- 观察载体：带 mandate 参数跑非交互单周期，完整 `CycleRecord` JSON 打到 stdout——
  对着本课 ReviewRecord 的五个字段读 signals / clamps / final_weights 的对版位置。

## 改什么

写清动了哪个文件的哪一段，改前改后各是什么值。两句话的形状：`文件路径` + 字段/段落
+ `旧值 → 新值`。别贴整文件，别贴整段 prompt——只点名动的那几行。

- TODO(改造)：改造 A 与 B 各一小段（路径 + 改点 + 前后值）。

## 为什么

每个改造回答一个讲义里的主张：A 验证「人格即 prompt」（§2.1 的 LLM 人格 = name +
一段 system prompt）；B 验证「权重即话语权」（弃权从分子分母同剔的加权合成，§2.2）。
写清你想观察什么、预期怎么变——预期错了也要如实写，那是观察的起点。

- TODO(改造)：每个改造一句动机 + 一句预期。

## 最小 diff

`git diff` 的摘录：只贴你动的那几行 + 上下文两三行，` ```diff ` 代码块；YAML 缩进
原样保留。prompt 是长文本时只贴动的那几行。

- TODO(改造)：贴两个改造的 diff 摘录。

## 复现步骤

从干净克隆到看见变化的命令序列，每步一行（bash 块分步走，不串联）；含分支名、
env 变量怎么配、跑哪条命令（如 `aihf ~/.hedge-fund/mandates/<你的 mandate>.yaml
--tickers AAPL,MSFT`）。自查法：换一台机器照着走，每一步都有「这步成了」的检查点。

- TODO(改造)：编号步骤 1..N + 每步一个检查点。

## 证据

重跑后的观察摘录：改造 A 看 buffett 的 Signal reasoning 是否改口风；改造 B 看合成
前后的 final_weights 与 conviction。日志/输出摘录用 ` ```text ` 块贴 3–5 行并圈出
变化那一行；截图建议另存 `notes/assets/`（自建目录），md 里引相对路径——贴不了图
就贴日志摘录，两者等价。

- TODO(改造)：改造 A/B 各一段摘录 + 一句「变化在哪一行」。
