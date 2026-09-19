# 改造说明：ai-hedge-fund（L4.1 层级投票）

**改造要求（任务卡）**

- [x] 改造 A · 改人格 prompt：`hedge_fund/signals/buffett.py` 的 system prompt 检查清单重排；
- [x] 改造 B · 改话语权：mandate YAML 的 `weight:` 调整；
- [x] env 四变量配齐（FINANCIAL_DATASETS_API_KEY / HEDGE_FUND_LLM_MODEL / OPENAI_API_KEY / OPENAI_API_BASE）；
- [x] 锚定 `virattt/ai-hedge-fund@fc1bf25`。

## 改什么

两个改造都在本地分支 `lab/persona-and-weights` 上做（克隆后 `git checkout fc1bf25` 起步）：

- 改造 A · 人格：`hedge_fund/signals/buffett.py` 的 system prompt——把「估值 / margin of
  safety」检查项挪到检查清单第一位，句尾加一句「先给估值结论，再谈其它」；
- 改造 B · 话语权：复制 `hedge_fund/strategies/deep-value.yaml` 为 `deep-value-lab.yaml`
  （mandate 是数据不是代码，复制改不动原文件），models 列表里 graham 的
  `weight: 2.0` 改 `weight: 4.0`，其余模型不动。

## 为什么

- 改造 A 验证「人格 = 一段 system prompt」（§2.1：LLM 人格 = name + 一段 prompt，
  机制全在 `LLMAgent` 基类）：只动 prompt 不动任何代码，Buffett 的 Signal reasoning
  应该改口风——估值结论出现在 reasoning 开头；
- 改造 B 验证「权重 = 话语权」（§2.2 加权合成，Step1 幕四的真产品版）：graham 话语权
  翻倍，同一组 signals 合成的 conviction 应向 graham 的方向偏移。

预期：A 只改单 agent 的 reasoning 文本；B 只改合成数值，不改变任何单 agent 输出
——两条预期正好把「意见层」与「合成层」切开。

## 最小 diff

（示意——YAML 字段层级以你克隆里的实际文件为准；prompt 是长文本，只贴动的那几行。）

```diff
--- a/hedge_fund/strategies/deep-value-lab.yaml
+++ b/hedge_fund/strategies/deep-value-lab.yaml
@@ models:
   - name: graham
-    weight: 2.0
+    weight: 4.0
   - name: buffett
   - name: munger
```

```diff
--- a/hedge_fund/signals/buffett.py
+++ b/hedge_fund/signals/buffett.py
@@ (system prompt 的检查清单段)
-1. 长期护城河与 ROE 检查…
+1. 估值先行：先给内在价值区间与安全边际结论…
+2. 长期护城河与 ROE 检查…
 (以下顺延)
```

## 复现步骤

1. `git clone https://github.com/virattt/ai-hedge-fund.git`——检查点：`git log --oneline -1`
   显示 fc1bf25（不是就 `git checkout fc1bf25`）；
2. `cd ai-hedge-fund`；
3. `git switch -c lab/persona-and-weights`——检查点：`git branch --show-current` 输出分支名；
4. `uv tool install . --force`——检查点：`aihf --help` 有输出；
5. 配 env 四变量（PowerShell 用 `$env:` 语法）；`HEDGE_FUND_LLM_MODEL` 选 registry 里
   provider=OpenAI 的 id（如 gpt-5.6）——检查点：`aihf` 非交互模式不报 provider 错；
6. 基线跑：`aihf ~/.hedge-fund/mandates/example.yaml --tickers AAPL,MSFT`——检查点：
   stdout 打出完整 CycleRecord（signals / clamps / final_weights 三块齐）；
7. 做改造 A+B（上面的 diff；mandate 换成 deep-value-lab.yaml 路径）；
8. 重跑第 6 步同命令，两跑对比 CycleRecord。

## 证据

（范本注：真产品证据需要你自己的行情 key 与模型端点真跑——本节用机制件输出做替身
示范「证据长什么样」，交作业时换成你自己的 CycleRecord 摘录。）

改造 B 的机制件替身（L4.1 `uv run python code/step1_blend.py` 幕四，同一组票只动
一个权重 0.5→3.0）：

```text
[四] 权重即话语权：同一组票，把 budget 的权重 0.5 抬到 3.0
  conviction = (0.8 + 3.0*(-0.6) + 0.9) / 5.5 = -0.0200  <- 反对票拿到了话语权
```

指认：conviction 从 +0.56 翻到 -0.02——「话语权」是算术事实。真产品版的变化点在
CycleRecord 的 `final_weights` 与合成 conviction：贴你两跑的各 3–5 行摘录，圈出
graham 的 weight 行与合成前后两个 conviction 值。改造 A 的证据形态：两跑的 buffett
Signal reasoning 各摘 2–3 行，圈出「估值结论提前」的那一句（对版机制件
`code/demo_trace.py` 幕② 里 compliance 检查员 reasoning 的「单餐超单笔上限」——
人格变了，第一句关注点就变）。
