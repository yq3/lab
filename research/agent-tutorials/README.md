# agent-tutorials — Agent 开源教程调研（教程轮）

> **任务**：为 [py-night-school](../../py-night-school/README.md)（Python 夜校：写给 Java 工程师的 Python Agent 开发晚课）的教程设计做竞品调研——现有 agent 教程长什么样、怎么教、借鉴什么、补什么空档。
> **系列**：继 `agent-framework/`（框架轮）、`agent-oss/`（产品轮）之后的教程轮；被调研仓库克隆在 `~/develop/opensource/`（克隆规范见该目录 AGENTS.md）。
> **状态**：已完成（2026-09-14 ~ 09-15）。

## 方法：两阶段

| 阶段 | 时间 | 手段 | 产出 |
|---|---|---|---|
| Phase 1 市场扫描 | 09-14 | WebSearch + `gh api`（README/元数据级，规避 github 网页超时） | [landscape.md](./landscape.md)：竞品总表、重点对象深析、借鉴决策清单（13 条采纳 + 6 条明确不借鉴）、差异化结论 |
| Phase 2 课时解剖 | 09-15 | 本地克隆逐仓精读（代表性课时全文，四路并行产出） | [profiles/](./profiles/) ×8 + [report.md](./report.md)（教学机制横向综合） |

## 对象清单

8 仓，四组（基线 HEAD 与磁盘占用见 landscape.md §6 本地克隆登记）：

| 组 | 仓库 | 语言 |
|---|---|---|
| 微软系 | ai-agents-for-beginners（18 课）、mcp-for-beginners（六语言） | EN |
| 课程式 | hello-agents（Datawhale 中文标杆，78.9k★）、huggingface/agents-course | 中文 / EN |
| notebook 式 | NirDiamant/GenAI_Agents（50+ 模式卡）、langchain-academy | EN |
| 厂商课程与示例集 | anthropics/courses、openai/openai-cookbook | EN |

刻意未纳入（理由见 landscape.md §6 末）：generative-ai-for-beginners（GenAI 通用课）、self-llm（模型部署侧）、rustlings（仅借鉴练习机制概念）、DeepLearning.AI（视频平台无仓库）。

## 目录导航

- **先读 [report.md](./report.md)**（最终交付）：横向对比矩阵（8 仓 × 8 个教学维度）+ 八个机制专题（练习验收/对照组教学法/贯穿叙事线/失败模式命名学/文档路标/notebook 锚点/素材复用/结业机制）+ 对 py-night-school 的设计更新清单。
- [landscape.md](./landscape.md)：市场扫描与借鉴决策（Phase 1，README/元数据级）。
- [profiles/](./profiles/)：逐仓解剖档案 ×8，统一六段模板（定位/结构/单课解剖/教学机制拆解/可借鉴点/局限反例），证据区分【核心】/【推断】/⚠️ 并溯源到本地克隆路径。

## 进度 checklist

- [x] Phase 1 市场扫描与借鉴决策（landscape.md）
- [x] 8 仓本地克隆与基线登记（gh-proxy 403 窗口 + ghfast 断流处置，经验沉淀至 `~/develop/opensource/AGENTS.md`）
- [x] Phase 2 逐仓课时解剖（profiles/ ×8，代表性课时全文精读）
- [x] 综合报告与设计回灌（report.md → py-night-school/CURRICULUM.md §2/§3/§4/§6）

## 特殊说明

- 本轮结论直接服务于教程项目 py-night-school（其 CURRICULUM/README 多处引用本目录）；**拆仓开源时教程正文须自包含**，本目录是创作输入而非发布物（原则见 landscape.md §5）。
- 证据纪律沿用 [research/AGENTS.md](../AGENTS.md)：结论可溯源、区分证据等级、不臆测；「单课解剖」为抽样深读（每仓 1–2 个代表性课时），引用具体做法前先查档案内的证据路径。
