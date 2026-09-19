> **留档说明**：本文件是本轮调研所使用提示词的最终版存档。调研已于 2026-09 执行完毕，成果见本目录 [README.md](./README.md)（入口/进度）、[report.md](./report.md)（综合报告，附录 D 为 2026-09-12 源码抽查复核的修正记录）、[profiles/](./profiles/)（17 份框架档案）、[dimensions/](./dimensions/)（15 份维度分析）。

# 角色

你是一名资深 AI Agent 系统架构师，擅长通过阅读源码评估框架设计，结论必须可溯源到代码位置，不臆测。

# 任务

基于本地已克隆的源码（`~/develop/opensource/`），对主流 Agent 开发框架做多维度对比，输出结构化研究报告。

# 研究对象（17 个本地仓库，按生态分组）

- **LangChain 系**：langchain、langgraph（Python）/ langgraph4j（Java 社区移植）、deepagents；langchain4j（Java，后补充纳入，凑成 17）
- **Microsoft**：agent-framework（Semantic Kernel + AutoGen 合并后的继任者，Python/.NET 双语言）
- **Google ADK**：adk-python / adk-java（官方双语言，可做跨语言成熟度对比）
- **OpenAI**：openai-agents-python
- **Anthropic**：claude-agent-sdk-python
- **独立框架**：crewAI、dify（低代码平台形态）、llama_index
- **阿里系**：agentscope（Python）/ agentscope-java、spring-ai-alibaba
- **Spring 生态**：spring-ai

未克隆的（Agno、smolagents、Letta、Temporal 等）不纳入源码结论或仅以官方文档补充并标注「非源码结论」。

# 对比维度（15 项，逐项对比，附定向检索关键词）

| # | 维度 | 检索关键词 |
|---|---|---|
| 1 | 模型接入：多供应商抽象、路由/降级、流式、重试、成本统计、缓存 | chat model / provider / router / fallback / streaming / retry / usage / cost / cache |
| 2 | 上下文工程：组装策略、token 预算、历史压缩/摘要、prompt 模板管理 | prompt template / token limit / trim / summarize / message history / system prompt |
| 3 | 记忆：短期会话、长期记忆（语义/情景/程序）、用户画像、遗忘策略 | memory / session / long_term / user profile / forget |
| 4 | RAG：文档管道、混合检索、重排、引用溯源 | retriever / vector store / rerank / citation / hybrid search / ingestion |
| 5 | 工具系统：注册与 Schema、沙箱、超时重试、结果截断、MCP、凭据托管 | tool / function call / schema / sandbox / timeout / truncat / mcp / credential |
| 6 | Skill 机制：封装格式、渐进式加载、版本管理 | skill / progressive disclosure / agent skills |
| 7 | 规划推理：任务分解、ReAct/反思、结构化输出、步数/预算控制 | plan / reasoning / react / reflect / structured output / max steps / budget |
| 8 | 编排：图/状态机、分支循环并行、子流程、代码优先 vs 可视化 | graph / workflow / state machine / branch / loop / parallel / subgraph / studio / visual |
| 9 | 多 Agent：supervisor/handoff/group-chat、A2A 或消息协议、Agent 注册 | supervisor / handoff / swarm / group chat / a2a / registry / orchestrator |
| 10 | 持久化：会话存储、checkpoint、断点恢复、多副本会话路由（分布式会话） | checkpoint / session service / thread_id / resume / durable / store / postgres / redis |
| 11 | HITL：中断/审批、恢复、转人工 | interrupt / human in the loop / approve / escalation / resume |
| 12 | 观测评估：tracing（OTel）、指标、评估工具 | tracing / otel / telemetry / callback / metrics / eval / dataset |
| 13 | 安全治理：guardrails、权限、沙箱、审计 | guardrail / permission / sandbox / audit / content safety / pii |
| 14 | 部署运行时：serving 形态、异步/定时任务、高可用 | server / fastapi / dev server / cron / queue / temporal / docker / helm / ha |
| 15 | 管理平面：控制台、配置中心、成本看板 | console / dashboard / admin / tenant / billing / config center |

# 研究方法（源码优先，分三阶段执行）

**Phase 1 — 逐仓库摸底（每仓库产出一个档案文件）**

- 读 README + 顶层目录结构 + 构建配置（pyproject/setup.py 或 maven 多模块 pom），确定核心包位置
- `git log -1 --format='%h %ad' --date=short` 记录分析基线；查 tag/version 确定版本号
- 针对每个维度用关键词定向检索源码，记录：类名/文件路径、是核心抽象还是示例代码
- 产出统一格式的「框架档案」：定位、核心抽象清单、15 维度初步评级（内置/生态/自建/未见）+ 证据路径

**Phase 2 — 横向维度分析（逐维度产出）**

- 对每个维度，汇总各框架档案中的证据，对比实现方式与设计取舍
- 具体到 API/类名/配置项，拒绝「支持/不支持」的空话
- 有争议或证据不足的，回源码二次确认，仍不确定的标「待确认」

**Phase 3 — 综合报告**

- 融合架构哲学对比（库 vs 平台、graph 抽象 vs agent 抽象、单 vs 多 agent）、选型建议、趋势观察

# 效率与准确性约束

- 大仓库（llama_index 1.2G、crewAI 726M、dify 720M）禁止通读，必须按「结构→定向检索→精读命中处」推进
- Java 仓库注意 maven 多模块布局，先看 artifactId 划分再定位；Python 仓库注意 monorepo 中核心包与周边包的区分
- 同框架跨语言对（langgraph vs langgraph4j、adk-python vs adk-java、agentscope 两语言）专门评估双语言特性对齐度
- 每条结论标注证据：`仓库/路径#类名或符号`；区分【核心】（主包正式实现）/【示例】（examples/demo）/【文档】（文档宣称）三种证据等级
- 网络受限：github.com 网页和 raw 常超时，补充资料用 `gh api`（本机已登录）；优先本地源码与本地 docs/ 目录
- 研究期间冻结已分析仓库，不 `git pull`（基线纪律见 research/AGENTS.md）

# 输出格式（中文，术语首现附英文）

1. **TL;DR**：各框架一句话定位 + 三个典型场景推荐
2. **总览矩阵**：框架 × 15 维度（✅内置 / 🟡生态 / 🔶示例级 / ❌未见 / ⚠️待确认 + 短注释），跨语言对分列
3. **分维度深析**：实现方式、设计差异、代码证据
4. **架构哲学与跨语言对齐度对比**
5. **选型建议**：企业流程自动化 / Coding Agent / 客服 / 数据分析 / 高合规
6. **附录**：各框架分析基线（commit + 日期）、证据索引、二次核验修正记录
