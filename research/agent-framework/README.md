# 主流 Agent 开发框架多维度对比研究（源码级）

> **性质**：AI Agent 系统架构师视角的框架评估研究报告。
> **方法**：三阶段 —— Phase 1 逐仓库摸底（`profiles/`，每仓库一份档案）→ Phase 2 横向维度分析（`dimensions/`，15 个维度）→ Phase 3 综合报告（`report.md`）。
> **证据纪律**：所有结论可溯源到 `~/develop/opensource/<仓库>/路径#符号`；区分三种证据等级——【核心】核心代码实现 /【示例】examples 或 demo /【文档】文档宣称。不臆测，查不到标 ❌ 或 ⚠️待确认。
> **网络受限**：github.com 网页/raw 常超时；补充资料用 `gh api`。未本地克隆的框架（Agno / smolagents / Letta 等）不纳入源码结论，仅在报告中以「非源码结论」标注提及。

## 研究对象（17 个本地仓库，`~/develop/opensource/`）

| 生态 | 仓库 | 语言 |
|---|---|---|
| LangChain 系 | langchain、langgraph、langgraph4j、langchain4j（补充）、deepagents | Python / Java |
| Microsoft | agent-framework（AutoGen+SK 后继） | Python / .NET |
| Google ADK | adk-python、adk-java | Python / Java |
| OpenAI | openai-agents-python | Python |
| Anthropic | claude-agent-sdk-python | Python |
| 独立框架 | crewAI、dify（低代码平台）、llama_index | Python / TS / Go |
| 阿里系 | agentscope、agentscope-java、spring-ai-alibaba | Python / Java |
| Spring 生态 | spring-ai | Java |

## 评级图例（全研究统一）

| 符号 | 含义 |
|---|---|
| ✅ | 核心内置：主包内有正式抽象与实现 |
| 🟡 | 生态：官方独立包 / 官方插件 / 平台扩展点承载 |
| 🔶 | 示例级：examples 或 demo 有，核心无正式抽象 |
| ❌ | 未见：需用户自建 |
| ⚠️ | 待确认：证据不足或有争议 |

## 档案模板（profiles/ 统一格式）

```markdown
# <框架> 框架档案
> 基线：~/develop/opensource/<repo> @ <hash> <date>；版本 <tag / pyproject / pom>
## 1. 定位（3-5 句：解决什么问题、库还是平台、目标用户）
## 2. 仓库结构与核心包（构建配置证据：pyproject / maven 模块树）
## 3. 核心抽象清单（表格：符号 | 路径 | 一句话说明）
## 4. 15 维度评级总表（| # | 维度 | 评级 | 一句话 | 关键证据 仓库相对路径#符号 |）
## 5. 维度证据明细（逐维度 3-8 行：类/文件、行为要点、证据等级【核心】【示例】【文档】）
## 6. 设计决策要点（3-8 条这个框架独有的取舍）
## 7. 跨语言对齐（仅 langgraph4j / adk-java / agentscope-java：与 Python 版逐维度差异）
```

## 15 维度及定向检索关键词

| # | 维度 | 检索关键词 |
|---|---|---|
| 1 | 模型接入 | chat model / provider / router / fallback / streaming / retry / usage / cost / cache |
| 2 | 上下文工程 | prompt template / token limit / trim / summarize / message history / system prompt |
| 3 | 记忆 | memory / session / long_term / user profile / forget |
| 4 | RAG | retriever / vector store / rerank / citation / hybrid search / ingestion |
| 5 | 工具系统 | tool / function call / schema / sandbox / timeout / truncat / mcp / credential |
| 6 | Skill 机制 | skill / progressive disclosure / agent skills |
| 7 | 规划推理 | plan / reasoning / react / reflect / structured output / max steps / budget |
| 8 | 编排 | graph / workflow / state machine / branch / loop / parallel / subgraph / studio / visual |
| 9 | 多 Agent | supervisor / handoff / swarm / group chat / a2a / registry / orchestrator |
| 10 | 持久化 | checkpoint / session service / thread_id / resume / durable / store / postgres / redis |
| 11 | HITL | interrupt / human in the loop / approve / escalation / resume |
| 12 | 观测评估 | tracing / otel / telemetry / callback / metrics / eval / dataset |
| 13 | 安全治理 | guardrail / permission / sandbox / audit / content safety / pii |
| 14 | 部署运行时 | server / fastapi / dev server / cron / queue / temporal / docker / helm / ha |
| 15 | 管理平面 | console / dashboard / admin / tenant / billing / config center |

## 进度（分批执行，可续）

- [x] Phase 1a：profiles/ langchain、langgraph、langgraph4j、langchain4j、deepagents
- [x] Phase 1b：profiles/ agent-framework、adk-python、adk-java
- [x] Phase 1c：profiles/ openai-agents-python、claude-agent-sdk-python、crewAI、dify、llama_index
- [x] Phase 1d：profiles/ agentscope、agentscope-java、spring-ai-alibaba、spring-ai（共 17 份，评级表 15 维齐全）
- [x] Phase 2：dimensions/ 01~15（5 组：1-3 / 4-6 / 7-9 / 10-12 / 13-15；含对档案的 8 处二次核验勘误）
- [x] Phase 3：report.md（TL;DR / 总览矩阵 / 分维度深析 / 哲学与跨语言对齐 / 选型建议 / 附录基线与证据索引）

## 目录

- **[report.md](./report.md)** —— 综合报告（先读这篇）
- [profiles/](./profiles/) —— 17 份框架档案（逐仓库：定位/核心抽象/15 维评级/证据明细）
- [dimensions/](./dimensions/) —— 15 份维度分析（逐维度：17 框架矩阵/派系深析/跨语言对齐/趋势）

## 分析基线（git HEAD，2026-09-12 记录）

| 仓库 | HEAD | 日期 | 版本 |
|---|---|---|---|
| langchain | 348c9dc572 | 2026-09-11 | langchain_v1 1.4.0 / core 1.6.3 / classic 1.0.8 |
| langgraph | e539ac122 | 2026-09-09 | langgraph 1.2.11 / checkpoint 4.2.0 / prebuilt 1.1.0 |
| langgraph4j | c2cf2e33 | 2026-09-06 | 1.9.0-beta6 |
| langchain4j | 0028928ea | 2026-09-11 | 1.21.0-beta31-SNAPSHOT（父 pom 108 模块） |
| deepagents | 9e7d62ff6 | 2026-09-11 | deepagents 0.7.13 |
| agent-framework | 3c6707077 | 2026-09-11 | py 1.18.0 / dotnet 1.21.0 |
| adk-python | 7b246e01 | 2026-09-11 | 2.9.0（tag v1.32.0 落后 1611 commits） |
| adk-java | fda5a102 | 2026-09-10 | 1.9.1-SNAPSHOT（tag v1.9.0+25） |
| openai-agents-python | fbd2dbca | 2026-09-11 | 0.22.2 |
| claude-agent-sdk-python | f101a76 | 2026-09-11 | 0.2.152（捆绑 Claude Code CLI 2.1.269） |
| crewAI | 894898f84 | 2026-09-12 | 1.15.21+11 commits（scm versioning） |
| dify | 79effdd498 | 2026-09-12 | 1.17.1（graphon==0.7.0） |
| llama_index | 7169bcd0d | 2026-09-11 | core 0.14.24（workflows 外置 2.23.3） |
| agentscope | b82253ba | 2026-09-11 | 2.0.8 |
| agentscope-java | c5db8f72 | 2026-09-11 | 2.0.3-SNAPSHOT（tag v2.0.2+144） |
| spring-ai-alibaba | f82da0b50 | 2026-08-25 | 1.1.2.2 |
| spring-ai | b5eb0272f | 2026-09-11 | 2.0.2-SNAPSHOT |
