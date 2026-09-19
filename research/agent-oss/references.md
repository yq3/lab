# 学术与基准参照系（references）

> 资料类，不克隆、不纳入 18 仓库解剖。2026-09-13 `gh api` 核验（star / 最近 push）。用法：概念框架 / 技术 taxonomy / 评估基准；论文链接随用随补。
> 网络受限：仓库内容在线读用 `gh api repos/{owner}/{repo}/readme`（base64）。

## A. Data Agent 概念与分类（B 组概念框架）

| 资料 | 论文 | star / 最近 push | 用法 |
|---|---|---|---|
| [HKUSTDial/awesome-data-agents](https://github.com/HKUSTDial/awesome-data-agents) | A Survey of Data Agents: Emerging Paradigm or Overstated Hype? (arXiv 2510.23587)，配 SIGMOD'26 tutorial | 739 / 2026-08 | 「Data Agent」学术定义与分类锚点；B 组维度分析的概念框架 |

## B. Text-to-SQL / NL2SQL 技术脉络（B 组引用来源）

| 资料 | 论文 | star / 最近 push | 用法 |
|---|---|---|---|
| [HKUSTDial/NL2SQL_Handbook](https://github.com/HKUSTDial/NL2SQL_Handbook) | TKDE'25 + VLDB'24/'25 survey 系列 | 1591 / 2026-08 | schema linking、分解、执行评估的引用来源 |
| [eosphoros-ai/Awesome-Text2SQL](https://github.com/eosphoros-ai/Awesome-Text2SQL) | arXiv 2406.11434（DB-GPT 团队），中英双语 | 3754 / 2026-01 | 工程视角更重，与 Handbook 互补 |
| [DEEP-PolyU/Awesome-LLM-based-Text2SQL](https://github.com/DEEP-Polyu/Awesome-LLM-based-Text2SQL) | TKDE'25 survey 配套 | 1366 / 2026-08 | 与 Handbook 重复度高，二选一深读即可 |

## C. 数据 agent 基准（能力地图 + 第三方横评）

| 资料 | 论文 | star / 最近 push | 用法 |
|---|---|---|---|
| [ucbepic/DataAgentBench](https://github.com/ucbepic/DataAgentBench)（DAB） | arXiv 2603.20576（UC Berkeley × Hasura PromptQL），[线上 leaderboard](https://ucbepic.github.io/DataAgentBench/) | 160 / 2026-09 | ① 任务/评分维度＝能力地图；② leaderboard 提供各 agent 产品第三方横评，支撑 report 选型结论。仓库 2.1GB（数据集），只看网站+论文 |
| [ByteDance-Seed/DAComp](https://github.com/ByteDance-Seed/DAComp) | ICLR'26，数据智能全生命周期 agent 基准 | 441 / 2026-07 | 工业界视角的能力维度拆解，B 组分析参照 |

## D. 财务 agent 基准群（报告「评估与安全」小节素材）

| 资料 | 是什么 | star / 最近 push | 用法 |
|---|---|---|---|
| [open-compass/CNFinBench](https://github.com/open-compass/CNFinBench) | 中文高风险金融，29 子任务、端到端 agent 执行链（需求解析→路径规划→工具调用→结果验证） | 20 / 2026-06 | 高风险场景任务分解参照 |
| [aifinlab/FinVault](https://github.com/aifinlab/FinVault) | 财务 agent 安全执行评估（execution-grounded） | 18 / 2026-06 | **执行安全评估口径与维度 5（HITL 与风控）直接相关** |
| [QF-Bench/QuantitativeFinance-Bench](https://github.com/QF-Bench/QuantitativeFinance-Bench) | state-aware 金融 agent 基准 | 58 / 2026-09 | A 组评估参照 |
| [HiThink-Research/FinMTM](https://github.com/HiThink-Research/FinMTM) | 同花顺，多轮多模态财务推理与 agent 评估 | 32 / 2026-07 | 多轮交互评估维度 |
| [OpenFinArena/OpenFinArena](https://github.com/OpenFinArena/OpenFinArena) | 严格金融分析与预测基准 | 28 / 2026-08 | 分析/预测能力维度 |

## 两条观察（report 可直接引用）

1. **财务 agent 基准全部 star<60 且高度碎片化**（实测 2026-09-13：20/18/58/32/28）——佐证「企业财务运营侧无成熟开源 agent，评估标准远未收敛」。
2. **港科大 OSDial 组是该领域学术枢纽**（NL2SQL_Handbook + awesome-data-agents 均出自该组）——盯一个组即覆盖学术面。
