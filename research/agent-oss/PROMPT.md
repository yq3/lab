# 角色

你是资深 AI Agent 应用架构师，擅长解剖开源 agent 产品的架构设计，为自研系统提炼可落地的参考模式。

# 背景与目标

我们正在基于 **Java 技术栈**自研**财务领域**企业级 agent，硬约束：① agent 服务独立部署，与业务服务通过 API 通信；② 图编排工作流；③ 硬性审批/审计/合规要求。本任务对 `~/develop/opensource/` 下 18 个新增 agent 开源项目做**应用架构解剖**（不是框架能力对比），最终产出面向上述约束的参考架构模式清单。

已有研究：`research/agent-framework/`（17 个 agent 开发框架的 15 维度源码级对比，含档案与维度分析）。新项目若构建在这些框架之上，**直接引用已有结论并注明，不重做框架层分析**。

# 分析对象（18 个新增仓库，按与财务场景的相关度分组）

- **A 金融/交易**（决策与风控模式最直接）：ai-hedge-fund、FinRobot、TradingAgents、Vibe-Trading
- **B BI/数据智能**（财务数据问答/报表的产品形态）：DB-GPT、SQLBot、supersonic、WrenAI、DataAgent、data-formulator
- **C 编码 agent**（harness 工程成熟度最高，看横切设计不看产品功能）：cline、codex、gemini-cli、opencode、OpenHands、**claude-code-sourcemap**
- **D 研究/浏览器自动化**：gpt-researcher、browser-use

优先级 A > B > C > D：A/B 组全维度深剖；C 组重点解剖权限/审批/上下文管理/会话恢复等横切工程；D 组快扫（架构与工具设计即可）。

**对象状态标注（2026-09-13 gh api 核验，写入各档案时保留）**：supersonic 处于**维护模式**（正式 release 停在 2024-11 v0.9.8，近两年无发版、单人维保）——只作 ChatBI/语义层架构参考，不构成生产选型推荐；SQLBot 许可非标准（NOASSERTION，DataEase 系惯常 GPLv3+附加条款），商用需注意；DataAgent 尚在 1.0.0-RC 未 GA；opencode/goose/OpenHands 2026 年均已迁移 org（canonical 分别为 anomalyco/opencode、aaif-goose/goose、OpenHands/OpenHands），引用地址以克隆目录的 remote URL 为准。

**claude-code-sourcemap 特殊说明**：该仓库是从 sourcemap 还原的 Claude Code CLI 内部实现（npm 包 v2.1.88，`restored-src/`），非官方开源。分析定位＝生产级 harness 内部解剖，重点挖：权限规则引擎、工具审批流（can_use_tool）、上下文自动压缩（autocompact）、JSONL 会话持久化与 resume、subagent/hooks/skills 机制。注意四点：

1. 还原代码可能不完整/符号名失真，证据等级标**【还原源码】**以区别于【核心】；
2. 版本对齐——还原的是 2.1.88，而 claude-agent-sdk-python 档案捆绑的是 CLI 2.1.269，结论需注明所据版本；
3. 与 `research/agent-framework/profiles/claude-agent-sdk-python.md` 交叉引用（SDK 是该 CLI 的进程内遥控器，两侧互证）；
4. 仅供内部研究参考设计模式，不逐字复用代码（Anthropic 专有代码）。

# 补充资料：学术与基准参照系（资料类，2026-09-13 核验；不克隆、不纳入 18 仓库解剖对象）

用途分三类——概念框架 / 技术 taxonomy / 评估基准。使用方式：`gh api` 在线读 README 或收录论文链接，统一沉淀到 `references.md`；其中两个 survey 配套仓体积大（PDF/slides 撑的），更不要克隆。

| 资料 | 是什么 | 在本任务中的用法 |
|---|---|---|
| [HKUSTDial/awesome-data-agents](https://github.com/HKUSTDial/awesome-data-agents) | "A Survey of Data Agents"（arXiv 2510.23587）官方仓 + SIGMOD'26 tutorial | 「Data Agent」概念的学术定义与分类锚点；B 组维度分析的概念框架 |
| [HKUSTDial/NL2SQL_Handbook](https://github.com/HKUSTDial/NL2SQL_Handbook) | Text-to-SQL 权威 survey 系列（TKDE'25 + VLDB'24/'25）官方仓 | B 组 NL2SQL 技术脉络（schema linking、分解、执行评估）的引用来源 |
| [eosphoros-ai/Awesome-Text2SQL](https://github.com/eosphoros-ai/Awesome-Text2SQL) | DB-GPT 团队维护，配 survey（arXiv 2406.11434），中英双语 | 同上，工程视角更重，与 Handbook 互补 |
| [DEEP-PolyU/Awesome-LLM-based-Text2SQL](https://github.com/DEEP-PolyU/Awesome-LLM-based-Text2SQL) | 理大 TKDE'25 survey 配套清单 | 与 Handbook 重复度高，二选一深读即可 |
| [ucbepic/DataAgentBench](https://github.com/ucbepic/DataAgentBench)（DAB） | UC Berkeley × Hasura PromptQL 的数据 agent 基准，带[线上 leaderboard](https://ucbepic.github.io/DataAgentBench/)，论文 arXiv 2603.20576 | ① 任务/评分维度＝数据 agent 能力地图；② leaderboard 提供各 agent 产品第三方横评，可直接支撑 report 选型结论。仓库 2.1GB（数据集），只看网站+论文 |
| [ByteDance-Seed/DAComp](https://github.com/ByteDance-Seed/DAComp) | ICLR'26，数据智能全生命周期 agent 基准 | 工业界视角的能力维度拆解，B 组分析参照 |
| 财务 agent 基准群 | [CNFinBench](https://github.com/open-compass/CNFinBench)（open-compass，中文高风险金融）、[FinVault](https://github.com/aifinlab/FinVault)（财务 agent 安全执行评估）、[QF-Bench](https://github.com/QF-Bench/QuantitativeFinance-Bench)、[FinMTM](https://github.com/HiThink-Research/FinMTM)（同花顺）、[OpenFinArena](https://github.com/OpenFinArena/OpenFinArena) | 报告「评估与安全」小节引用素材；FinVault 的执行安全评估口径与维度 5（HITL 与风控）直接相关 |

两条观察（写 report 时可直接作为结论）：① 财务 agent 基准全部 star<60 且高度碎片化——佐证「企业财务运营侧无成熟开源 agent，评估标准远未收敛」；② 港科大 OSDial 组（NL2SQL_Handbook + awesome-data-agents 均出自该组）是该领域学术枢纽，盯一个组即覆盖学术面。

# 解剖维度（每个项目 8 项）

1. **产品定位与形态**：解决什么问题、目标用户、交互形态（CLI / Web / IDE 插件 / 独立服务）
2. **Agent 执行架构**：主循环怎么实现（自研 loop 还是框架驱动）、编排模式（图 / 流水线 / 自由循环 / 多 agent 拓扑）、多 agent 如何分工与通信（重点：A 组的辩论/评审/风控拓扑）
3. **技术底座**：语言、服务/web 框架、用了哪个 agent 框架（交叉引用已有档案）及选型理由
4. **状态与持久化**：会话/执行状态怎么存、有无 checkpoint / 审计轨迹 / 回放、多副本与并发处理
5. **HITL 与风控**：审批/确认门、危险操作拦截、人工接管、回滚与纠错——**本项目最关注维度，逐项深挖**
6. **工具与业务系统集成**：工具如何封装（HTTP client？DB 直连？MCP？）、凭据管理、权限边界、读写隔离
7. **部署与产品化**：部署形态、多租户隔离、配额/成本控制、可观测性
8. **对本项目的适用性**：对照四约束（Java、独立部署+API、图编排、财务合规）逐条给出——可借鉴模式（具体到类/模块路径）、不可迁移点（语言/生态差异）、避坑

# 方法与质量要求

- **三阶段执行**：Phase 1 逐仓库解剖档案 → Phase 2 分组横向 + 跨组专题提炼 → Phase 3 综合报告；18 个仓库工作量大，按 A→B→C→D 分批，每批产物落盘可续
- **源码优先**：每仓库先 `git log -1 --format='%h %ad' --date=short` 记录基线；结论标注证据 `仓库/路径#符号`，区分【核心】/【示例】/【文档】/【还原源码】四个证据等级
- **大仓库禁止通读**（OpenHands/cline/codex/restored-src 均不小）：README → 目录结构 → 构建配置 → 定向检索（loop、orchestrat、approve、audit、checkpoint、session、tenant、permission、credential、sandbox 等关键词）→ 精读命中处
- 区分「产品宣称」与「代码实现」，marketing README 不可作为能力证据
- **交叉引用纪律**：项目用到旧 17 框架的（如 langgraph/langchain），引用 `research/agent-framework/profiles/` 已有结论，把分析精力放在「它怎么用」而非「框架有什么」
- 网络受限：github.com 网页/raw 常超时，补充资料用 `gh api`（用法见仓库根 AGENTS.md）；优先本地源码与 docs/ 目录

# 基线与引用纪律（遵循 research/AGENTS.md）

- **研究期间冻结已分析仓库**：不 `git pull`，基线以启动时记录的 HEAD 为准
- 引用写全 `owner/repo` 防撞名（如 `openai/codex`），仓库克隆目录名可能与 owner 不一致时以 remote URL 为准
- 本目录只放文字结论，不放源码副本、大文件

# 产出物（落盘到 research/agent-oss/，遵循 research/AGENTS.md 模板）

1. `PROMPT.md`：本提示词全文（方法留档）
2. `README.md`：入口——研究说明、对象清单（18 仓库 + 基线 HEAD）、进度 checklist（分批可续）、目录导航；证据等级在标准三级【核心/示例/文档】外增加【还原源码】（仅 claude-code-sourcemap 用）
3. `profiles/` 18 份解剖档案（统一模板：基线 + 8 维度 + 适用性结论）
4. `dimensions/` 分组分析：A/B/C/D 各一份（组内共性、分化点）+ 一份跨组专题（多 agent 拓扑、审批与风控、状态与审计、工具与系统集成四个专题的模式对比）
5. `report.md` 综合报告：
   - **模式清单（pattern catalog）**：按「直接可用 / 需改造 / 仅参考」三级分类，每条注明来源项目、证据路径、迁移到 Java + 图编排时的注意点
   - **反模式与避坑**（含各项目的工程债与设计教训）
   - **面向财务 agent 的架构建议**：对照四约束收敛出的推荐架构（可含 ASCII 图）
6. `references.md`：学术与基准参照清单——上表所列 survey/benchmark 论文（arXiv 号）、DAB leaderboard 及财务基准群链接，随用随补

全程中文，术语首现附英文原文。
