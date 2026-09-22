# Agent 持久化专项（哪类数据、存成什么样、生命周期怎么管）

> **性质**：schema / 文件格式级的持久化专题深挖。核心问题：agent 系统运行时产生的各类数据（会话转录、执行状态、记忆、权限审批、审计成本、产物、配置凭据）分别被各家存成什么形态、用什么引擎、写入与读取路径、并发控制、生命周期（压缩 / 清理 / 迁移 / 容量）怎么管。
> **方法**：不做逐仓 profiles（两轮已覆盖），直接按「数据类别 × 六路」并行深挖 `dimensions/`，再综合 `report.md`。
> **上游**：`research/agent-framework/`（17 框架 × 15 维，维度 3 记忆 / 维度 10 持久化）、`research/agent-oss/`（18 仓解剖，各档案 §4 + 跨组专题三）。**本轮只补既有模式级结论之下的存储实现细节（DDL / JSON 行结构 / 目录布局 / 生命周期机制），模式级结论引用上游不重复。**

## 数据类别框架（七章）

| # | 类别 | 一句话 | 对应 dimensions |
|---|---|---|---|
| 1 | 会话转录 | append-only 事件 / 消息流，审计真相源 | 01 |
| 2 | 执行状态 / checkpoint | 断点续跑、HITL 挂起、pending writes | 02 |
| 3 | 记忆 | 跨会话长期记忆 / 决策日志 / few-shot 库 | 03 |
| 4 | 权限与审批 | 规则 / 授权 / 待审单 / 会话内规则 | 04 |
| 5 | 审计与成本 | LLM 留痕 / token 用量 / 哈希链账本 | 05 |
| 6 | 产物与大对象 | 用户可见产物、工具输出落盘指针 | 06 |
| 7 | 配置与凭据 | 工具目录、密文与引用键 | 04（带出） |

## 证据纪律（沿用两轮约定）

- 所有结论可溯源：`~/develop/opensource/<repo>/路径#符号`；证据等级【核心】/【示例】/【文档】/【还原源码】（仅 claude-code-sourcemap）。查不到标 ❌ 或 ⚠️，不臆测。
- 研究期间冻结仓库（不 `git pull`）；基线见下表（2026-09-20 全数核验，与两轮记录一致，无漂移）。
- **OpenHands 特例**：经典 Python 事件流架构锚定 git 历史 `e8249f00a`（detached；调研结束后恢复 HEAD `60877198a`）。
- 批次产物完成后做源码抽查复核（证据路径、关键断言），修正与存疑在 report.md 留痕。

## 对象与基线（git HEAD，2026-09-20 核验）

| 仓库 | HEAD | 本轮用于 |
|---|---|---|
| cline | cfe9cadab9 | 会话转录 / SQLite 分库 |
| codex | ee6814bfa4 | 会话转录 / 审批与 amendment / 成本风险持久化项 |
| gemini-cli | 9c1b0a6105 | 会话转录（全量重写反例）/ TOML 规则 / 落盘指针 |
| OpenHands | e8249f00a（经典锚点） | 事件文件 / 写时脱敏 / 产物存储 |
| claude-code-sourcemap | a8a678cb62 | JSONL 链 / settings 五落盘 / 快照旁挂【还原源码】 |
| opencode | 95daf90670 | SQLite 事件溯源三表 / saved 授权表 / 落盘指针 |
| langgraph | e539ac122f | checkpoint DDL / pending writes / BaseStore |
| deepagents | 9e7d62ff6 | backends 家族 / AGENTS.md 记忆 |
| agent-framework | 3c67070776 | WorkflowCheckpoint / 拓扑哈希 |
| adk-python | 7b246e0166 | DatabaseSessionService DDL / rewind |
| dify | 79effdd498 | workflow 表族 / offload / 标注 |
| crewAI | 894898f84c | LanceDB 记忆 / kickoff SQLite |
| agentscope | b82253ba | memory.md 文件记忆 |
| agentscope-java | c5db8f72db | AgentStateStore CAS / JDBC DDL |
| TradingAgents | be952b8ecc | trading_memory.md 决策日志 / per-ticker checkpoint |
| Vibe-Trading | f84b2977a5 | 跨会话记忆 / 哈希链账本 / mandate 与 halt |
| ai-hedge-fund | fc1bf250ea | PromptCache 审计即缓存 |
| supersonic | 6919ac50be | ChatMemoryDO / 记忆双审 / QueryStat |
| SQLBot | ba9aa5db66 | chat_log 双平面审计 |
| DB-GPT | 04559f9ccf | view message / catalog.json / CredentialStore |
| WrenAI | be1f9b57d2 | markdown 真相源 + 向量派生物 |
| data-formulator | 5477f0e236 | TokenStore 六级链 / Data Threads |
| browser-use | 50f205533f | secret 占位符协议 / AgentHistoryList |
| gpt-researcher | 6f998577d5 | 分步成本归集 / report_store |
| FinRobot | 6d6ccd3 | request_logs SQLite |

## 进度 checklist（分批可续）

- [x] Phase 0：基线核验（25 仓 HEAD 对两轮记录，无漂移）+ OpenHands 切锚点 e8249f00a（完成后已恢复 HEAD 60877198a）
- [x] Phase B1：dimensions/01 会话转录存储（cline / codex / gemini-cli / OpenHands / claude-code-sourcemap）——含修正：cline 现基线转录为 JSON 全量重写而非 JSONL
- [x] Phase B2：dimensions/02 执行状态与 checkpoint（langgraph / deepagents / agent-framework / crewAI / agentscope-java / dify / adk-python）
- [x] Phase B3：dimensions/03 记忆存储（crewAI / TradingAgents / Vibe-Trading / supersonic / langgraph / deepagents / agentscope / WrenAI / dify）——含修正：TradingAgents 记忆实际路径
- [x] Phase B4：dimensions/04 权限审批与凭据（codex / opencode / gemini-cli / claude-code-sourcemap / DB-GPT / data-formulator / browser-use / Vibe-Trading）
- [x] Phase B5：dimensions/05 审计与成本（codex / ai-hedge-fund / SQLBot / Vibe-Trading / supersonic / gpt-researcher / FinRobot / OpenHands）——含修正：Vibe chain 默认值文档与代码不一致
- [x] Phase B6：dimensions/06 产物与大对象（gemini-cli / opencode / DB-GPT / OpenHands / dify / data-formulator）
- [x] Phase C：抽查复核（10/10 命中，见 report.md §13）+ report.md + research/AGENTS.md 索引更新
- [x] Phase D：单对象深挖 profiles/opencode.md（存储层专项：19 表 DDL / 事件溯源写路径 / 生命周期 / 借鉴映射；三路深挖 + 8 条抽查复核；修正旧档案 2 处结论，见其 §12）
- [x] Phase E：单对象深挖扩展与审核——profiles/dify.md（五层介质全景 / 会话表族 / Redis key 清单 / 暂停恢复操作序列）、profiles/langgraph.md（PG 9 条迁移化石 / SQL 原文 / durability 写入时序 / conformance 契约）；opencode.md 经本机生产 DB 只读比对 + general subagent 独立审核（26+6+4 项抽查，有条件通过 → 6 处修订后定稿，见其 §13/§14）
- [x] Phase F：单对象深挖第三批（各含文末字段附录 + 抽查复核）——profiles/agentscope.md（Python 版 11 表「提升列+payload」模式 / 每 reply 全量快照 / 总线 run 锁 / 与 Java 版对照）、profiles/supersonic.md（33 表六域 / chat 运行时七步写入时序 / SqlInfo 四段 SQL 血统 / 死表与 trace_id 空串发现）、profiles/WrenAI.md（MCP-first 无状态边界 / markdown 真相源五子目录 / LanceDB 两表 / 维度守卫双闸门 / 凭据三律）

## 目录

- [report.md](./report.md) —— 综合报告（最终交付，先读这篇）
- [profiles/](./profiles/) —— 单对象深挖（正文=机制与借鉴，字段明细统一在文末附录）：[opencode.md](./profiles/opencode.md)（含本机 DB 比对与审核记录）、[dify.md](./profiles/dify.md)、[langgraph.md](./profiles/langgraph.md)、[agentscope.md](./profiles/agentscope.md)、[supersonic.md](./profiles/supersonic.md)、[WrenAI.md](./profiles/WrenAI.md)
- [dimensions/](./dimensions/) —— 六份类别深挖（过程）
