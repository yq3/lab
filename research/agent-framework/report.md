# 主流 Agent 开发框架多维度对比研究报告

> **方法**：源码级三阶段研究（17 份框架档案 → 15 份维度分析 → 本报告），全部结论可溯源到 `~/develop/opensource/<仓库>/路径#符号`，证据等级区分【核心】/【示例】/【文档】。分析基线见附录 A；逐框架证据见 [profiles/](./profiles/)，逐维度证据见 [dimensions/](./dimensions/)。Agno / smolagents / Letta 等未本地克隆的框架不纳入源码结论，本文不对其下判断。
> **快照**：2026-09-09 ~ 09-12 的各仓库 HEAD（详见附录 A）。

---

## 1. TL;DR

| 框架 | 一句话定位 |
|---|---|
| **langchain** | 组件库 + 装配器：1.x 的 agent = LangGraph 图上的中间件栈，引擎/持久化/HITL 全部透传 langgraph（`libs/langchain_v1/.../factory.py`） |
| **langgraph** | 图引擎的事实标准：Pregel/BSP 超步 + checkpoint 家族 + interrupt，生产 server 与 Studio 在闭源 Platform（`libs/cli/.../docker.py:262`） |
| **langgraph4j** | langgraph 的 Java 社区移植：灵魂能力（checkpoint/interrupt/HITL）对齐，无 Send 动态扇出、无跨线程 Store；意外地是 Java 侧最早内置 Skill 机制的框架 |
| **langchain4j** | Java 世界的「langchain 黄金时代」形态：AiServices 声明式代理 + core 内全 RAG 管道 + GOAP/BDI 等六种协作 pattern（补充研究对象） |
| **deepagents** | Anthropic「deep agents」理念的开源 harness：虚拟文件系统 + 子代理 + 五层上下文防御 + prompt cache 栈序设计 |
| **agent-framework (MS)** | AutoGen + Semantic Kernel 的合并继任（Python/.NET）：Pregel workflow + 编码 harness + Agent Skills（ADR-0037）+ 四层安全纵深，OTel 一等公民 |
| **adk-python** | Google 官方全栈 ADK（2.9.0）：2.x 把 agent 树与通用图统一（`BaseAgent(BaseNode)`），Vertex 深绑，全场最完整的开源 eval 工具链 |
| **adk-java** | ADK 的 Java 版（1.9.x，落后 Python 一个 major）：概念对齐、实现有硬缺口——无 auth 包、无 JDBC 会话后端、eval 端点全是 501 stub |
| **openai-agents-python** | 极简原语 + 重量内脏：handoff-as-tool + 三层 guardrail + 可序列化 RunState（HITL）+ 7 云厂商沙箱；注意 trace 默认外发 api.openai.com |
| **claude-agent-sdk-python** | Claude Code CLI 的进程内遥控器：运行时整体外置捆绑 CLI（2.1.269），权限规则文法/hooks/skills 生态最全，强绑 Claude 模型 |
| **crewai** | 角色扮演多 agent + 全场最强记忆系统（EncodingFlow 写入 / RecallFlow 召回 / 复合评分）：控制台与部署在付费 AMP，OSS 只有 TUI |
| **dify** | 低代码平台标杆：13 核心服务 docker-compose + 租户 RBAC + 工作流双版本化 + 知识库；编排引擎已外置为 graphon PyPI 包 |
| **llama_index** | RAG 帝国 + 轻量事件驱动 workflow：双引擎外置（workflows / instrumentation），RAG 指标与 eval 全家桶 core 内置 |
| **agentscope** | v2 重构最激进：单 Agent 类（3915 行）+ 权限引擎 + 分层上下文压缩；编排组合子整体删除，「编排过细生命周期短」的实证 |
| **agentscope-java** | 对齐 Python 版且服务化更重：三进程控制平面 + Helm + Nacos/higress 注册中心 + A2A server——治理异构框架的 agent |
| **spring-ai-alibaba** | spring-ai 的企业化补全：合规 fork langgraph4j 做图引擎 + SKILL.md 注册表 + Nacos 四注入器 + admin 可视化画布（可迁移 Dify DSL） |
| **spring-ai** | Spring 官方的「顾问链」哲学：advisor 链 + 工具循环上移 + 40/150 调用预算；刻意不做编排/多 agent/HITL，全部留给衍生层 |

**三个典型场景速配**（详细论证见 §5）：

1. **企业流程自动化（可视化 + 审批 + 多租户）** → 首选 **dify**；代码优先且要断点续跑选 **langgraph**；Java/Spring 栈选 **spring-ai-alibaba** 或 **agentscope-java**。
2. **Coding Agent / 深任务 harness** → **claude-agent-sdk**（能力最全、绑 Claude）或 **deepagents**（模型中立、上下文工程最深）；Azure 栈用 **agent-framework** 的 `create_harness_agent`。
3. **知识密集型问答 / 数据分析** → **llama_index**（RAG + eval 最全）；全押 OpenAI 生态用 **openai-agents-python**（7 云沙箱 + FileSearch）；Java 栈用 **langchain4j**。

---

## 2. 总览矩阵（17 框架 × 15 维度）

评级：✅ 核心内置 / 🟡 生态或官方扩展承载 / 🔶 示例级 / ❌ 未见（需自建）。跨语言对相邻排列。

| 框架 | 1 模型接入 | 2 上下文工程 | 3 记忆 | 4 RAG | 5 工具/MCP | 6 Skill | 7 规划推理 | 8 编排 | 9 多Agent | 10 持久化 | 11 HITL | 12 观测评估 | 13 安全治理 | 14 部署运行时 | 15 管理平面 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| langchain | ✅ | ✅ | 🟡 | ✅ | ✅ | ❌ | 🔶 | 🟡 | 🔶 | 🟡 | ✅ | ✅ | ✅ | ❌ | ❌ |
| **langgraph** | 🟡 | 🔶 | ✅ | 🔶 | ✅ | ❌ | ✅ | ✅ | 🟡 | ✅ | ✅ | 🟡 | ❌ | 🟡 | 🟡 |
| **langgraph4j** | 🟡 | 🟡 | 🔶 | 🔶 | ✅ | ✅ | 🔶 | ✅ | 🔶 | ✅ | ✅ | 🟡 | ❌ | 🟡 | ❌ |
| langchain4j | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ❌ | ❌ |
| deepagents | ✅ | ✅ | ✅ | 🔶 | ✅ | ✅ | 🔶 | 🟡 | ✅ | ✅ | ✅ | 🟡 | ✅ | 🟡 | 🔶 |
| agent-framework (MS) | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | 🟡 |
| **adk-python** | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | 🟡 |
| **adk-java** | ✅ | ✅ | 🟡 | 🔶 | ✅ | ✅ | 🟡 | ✅ | ✅ | 🟡 | ✅ | ✅ | 🔶 | 🟡 | 🔶 |
| openai-agents-python | ✅ | ✅ | ✅ | 🔶 | ✅ | 🔶 | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | 🔶 | ❌ |
| claude-agent-sdk-python | ✅ | ✅ | 🟡 | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | 🟡 | ✅ | ❌ | ❌ |
| crewai | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | 🟡 | 🟡 |
| dify | ✅ | ✅ | ✅* | ✅ | ✅ | ✅ | ✅ | ✅ | 🔶 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| llama_index | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | 🟡 | ✅ | ✅ | 🔶 | ❌ | ❌ |
| **agentscope** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| **agentscope-java** | ✅ | ✅ | 🟡 | 🟡 | ✅ | ✅ | ✅ | 🔶 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| spring-ai-alibaba | 🟡 | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | 🟡 | 🟡 |
| spring-ai | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 🔶 | 🔶 | ❌ | 🟡 | ❌ | ✅ | 🟡 | 🟡 | ❌ |

\* dify 记忆为会话级 + 标注回放，跨会话长期记忆 ❌。
\*\* 第 12 列为「观测+评估」合并评级：多数 ✅ 由 tracing/OTel 能力支撑，eval 普遍弱于观测——adk-java eval 端点全 501 stub、crewai 无开源 eval 工具链、langchain 的评估在 LangSmith（商业生态）。评估维度的真实格局以 §3.12 与 [dimensions/12](./dimensions/12-observability-eval.md) 为准。

**矩阵速读**（ standout 事实，逐条有源码证据，详见 §3 与 dimensions/）：

- **工具系统是唯一全 ✅ 的维度**（17/17），MCP 是 16/17 的标配——但这只说明「能用工具」是及格线，治理深度（超时/截断/沙箱/凭据）才是分水岭。
- **Skill 机制扩散最快**（12/17），且 Java 阵营罕见反超（langgraph4j / spring-ai-alibaba / agentscope-java / adk-java / langchain4j 全有，而 langgraph / spring-ai 没有）。
- **eval 是最大空白**：完整开源工具链只有 adk-python 与 llama_index；adk-java 的 eval 端点全是 501 stub。
- **管理平面几乎与开源互斥**：只有 dify 与 agentscope-java 把运营级控制台做进开源仓库。
- **引擎级安全的只有两家 ❌**（langgraph / langgraph4j）：图引擎刻意零安全抽象，安全留给上层库。
- **三家「拒绝编排」**（openai-agents / claude-sdk / spring-ai）与两家 Pregel 引擎（langgraph / MS）构成编排光谱两极。
- **两家默认遥测外发**（openai-agents → api.openai.com，crewai → telemetry.crewai.com:4319）——企业引入第一件事是关掉。

---

## 3. 分维度深析（每维度一段结论，完整证据见 dimensions/ 对应文件）

### 3.1 模型接入（[01](./dimensions/01-model-access.md)）
「统一接口 + 集成包矩阵」是主流（langchain 15 个 partners、llama_index 103 个 llms 集成包、langchain4j ~30 模块、spring-ai 15 模块），注册表/前缀路由是第二选择（adk `LLMRegistry` 正则、openai `MultiProvider` 前缀、crewai `LLM.__new__` 工厂内路由）。**真正的空白是模型级 fallback——17 家仅 6 家真实现**（adk-python `FallbackModel`、agentscope agent 层 fallback_model、langchain 中间件、saa 拦截器、claude 透传 CLI、dify 凭据池负载均衡），且位置分散：降级被视为编排问题而非接入问题。重试语义最讲究的是 agentscope（按各供应商声明的可重试异常重试）；prompt cache 已升格为框架管辖对象（openai cache key 生命周期、crewai provider 无关断点、deepagents 栈序、adk Gemini 显式内容缓存）；计价只有 4 家做（claude CLI / dify / crewai / dcode 外围）。Java 生态靠「桥」不靠「量」（langgraph4j 双集成、adk-java 双桥、saa 全托管 Spring AI）。

### 3.2 上下文工程（[02](./dimensions/02-context-engineering.md)）
窗口裁剪是及格线；水位比率 + 分层防御 + 非破坏性摘要是天花板（deepagents 五层防线、agentscope 三段水位 0.6/0.8/0.1、MS `group_messages` 工具调用成组保护）。三个范式级分歧：**非破坏性 vs 改写式**（deepagents 把摘要做成请求期投影、原始 messages 永留 state；adk 用 `EventCompaction` 事件让压缩可溯源）；**文件系统成为上下文二级存储**（deepagents 超大工具结果 offload 进虚拟文件系统、agentscope 图片 offload 到 workspace）；**prompt cache 断点意识**（5 家显式实现，claude 的 `exclude_dynamic_sections` 甚至把缓存命中从会话级提升到跨用户级）。服务端压缩外包（openai `responses.compact`、claude autocompact、adk Gemini compaction）是平台绑定框架的特权。

### 3.3 记忆（[03](./dimensions/03-memory.md)）
**短期记忆抽象正在消亡**：v2 重构的三家（agentscope 双语、crewai）都删掉了旧 Memory 类，会话记忆被 checkpoint/AgentState/Session 吸收；独立 ChatMemory 只在 Java 库系存续。**长期记忆三分天下**：文件自学习派（deepagents `MemoryMiddleware` 教模型用 edit_file 写 AGENTS.md、agentscope AgenticMemory）、托管服务派（adk VertexAiRag/MemoryBank，Java 侧无对应是硬缺口）、向量+LLM 分析派（crewai 统一 Memory 最重：EncodingFlow N 路并发抽取 + 0.85 合并阈值 + 30 天半衰期复合评分）。**遗忘与用户画像全线空白**（17 家 0 个显式 forget API、0 个画像抽象）——GDPR 式按策略删除只能自建。agentscope-java 的记忆 API 整包 `@Deprecated(forRemoval)`，且这只是其 v2 系统性大清洗的一角——hook 包全量（Hook + 17 个事件类）、RAG 四件套（Knowledge/RAGMode/GenericRAGHook/KnowledgeRetrievalTools）、LongTermMemory 系、SkillBox 类同样在列（`@Deprecated(forRemoval, since="2.0.0")`，官方 change-log Part B 明示 2.1 移除），而官方扩展仍挂旧 API，是跨语言倒挂的实证。

### 3.4 RAG（[04](./dimensions/04-rag.md)）
清晰光谱：**管道原生派**（llama_index 15+ 索引类型/18 种 query engine、langchain4j core 内 QueryTransformer→Aggregator 全管道、spring-ai 22 向量库模块）→ **平台产品派**（dify 异步索引任务系统 + hybrid 枚举级公民 + 18 字段引用元数据；agentscope KnowledgeBase + REST 服务）→ **抽象壳派**（langchain core 留 4 个稳定抽象、MS `@vector_store_model` 声明式）→ **云委托派**（adk 双语让位 Vertex，Java 连 llama_index 桥都没有）→ **反管线派**（deepagents 的 grep/glob/read_file agentic 检索）。横向切面：混合检索收敛于 RRF（`1/(k+rank)`，三家独立实现同一公式）；**citation 只有 2 家成体系**（llama_index 内容块级 CitationBlock、dify 元数据级 retriever_resources）；2025-26 世代的新 agent 框架核心全部零 RAG 抽象——RAG 正从「框架必备件」降级为「可插拔能力」。

### 3.5 工具系统与 MCP（[05](./dimensions/05-tools-mcp.md)）
17 家全 ✅，但治理深度分化：**错误回喂 LLM 已是共识**（7+ 家默认），**统一超时只有 5 家**（openai-agents 双策略、agentscope Bash 120/600s、agentscope-java 5min 默认、crewai 仅 MCP 60s、deepagents），**结果截断**分化最狠（deepagents 体系化 offload、MS `_EncodedSizeBudget` 逐字符计费防 DoS、多数框架直接回喂）。沙箱四梯队：多厂商矩阵（openai 7 云厂商 + agentscope 8 workspace）> 独立服务（dify landlock+PTY）> 单容器/JVM 内（langchain4j GraalVM、adk Container）> 委派外部。MCP 已成标配（16/17），stdio+SSE+streamable-http 三传输是基线（langchain4j 独有 websocket、dify HTTP-only 平台分工式解法），**elicitation 只有 4 家**且深度差三个量级（langchain 做到 interrupt-HITL 级、claude-sdk 显式拒绝）。**凭据托管基本是 Google 私产**（adk-python auth/ 全套 17 家唯一完整，adk-java 都没跟上）。

### 3.6 Skill 机制（[06](./dimensions/06-skills.md)）
落地仅一年已 12/17（多数诚实标注 experimental/@Experimental/ADR-proposed）。触发机制的设计空间已探满：专用工具（8 家）→ 通用 read_file（deepagents 四步教学、agentscope SkillViewer）→ **图状态迁移**（langgraph4j `SkillInjector`：技能激活是可 checkpoint 的状态迁移，正文永不落 state）→ 提及拉取（dify-agent 按提及 pull 归档）→ 规则文法开关（claude `Skill(name)`）。三家独立演化出「skill 携带工具授权」（MS allowed_tools / saa allowedTools / claude 规则文法）——skill 正从指令包变成**能力单元**（instructions + resources + scripts + tool grants）。版本管理只有 dify（不可变 SkillVersion + hash 审计）与 crewai（version pin）成体系；adk-java 存在指令引用不存在工具的「幽灵工具」（`run_skill_script`）。

### 3.7 规划推理（[07](./dimensions/07-planning-reasoning.md)）
ReAct 循环是免费日用品；**显式规划整体退潮**（deepagents 把 write_todos 移出默认栈「按模型训练偏好按需装配」、crewai 只做 kickoff 前一次性规划、openai/spring-ai 完全不做），反例是 Java 企业栈（langchain4j GOAP/BDI、adk-java contrib planners——企业仍要可审计的显式计划）。反思无一家做成核心抽象，四个正式实现：deepagents RubricMiddleware（完成度门槛）、agentscope GoalPipeline（执行者-验证者）、MS MagenticProgressLedger（AutoGen 血统）、spring-ai 校验自纠错 advisor。**超限行为三分**：异常派（langgraph `GraphRecursionError`、adk 硬停）vs 优雅收尾派（agentscope 强制总结、crewai 再调一次 LLM 拿终稿、MS 三轴预算 best-effort）vs 混合（openai handler 接管）。默认预算值从 10 到 10007 不等且无共识——「一轮」的定义本身不统一。claude 是唯一把**钱**做成一等预算的（max_budget_usd）。

### 3.8 编排（[08](./dimensions/08-orchestration.md)）
图范式是最大公约数但深度三档：**Pregel/BSP 引擎只有 2 家**（langgraph 三相超步 + channel 版本差分调度；MS `RunnerImpl` 每超步自动 checkpoint + 拓扑哈希校验）——只有它们免费获得任意步暂停/恢复/time-travel；拉取式引擎（langgraph4j Emitter 换流式简洁、dify graphon、saa fork 后补并行边）无 Send 动态扇出；agent 树（adk 2.x `BaseAgent(BaseNode)` 统一图与树、langchain4j 五种固定拓扑组合子）。事件流派（crewai Flow DSL、llama_index Workflow 六 @step）与「拒绝编排」派（spring-ai advisor 链是横切管道非编排、openai/claude 把 pattern 下沉 examples）构成对照组。**agentscope v2 删组合子是最有信息量的反面教训**：通用图编排的学习成本在 agent 框架层级不划算，要么下沉专职引擎要么上浮平台画布。可视化分裂为「画布（dify/saa admin）」与「调试器（adk web/devui/Studio）」两个市场。

### 3.9 多 Agent（[09](./dimensions/09-multi-agent.md)）
**handoff-as-tool 赢得最小公分母**（openai transfer_to_* + input_filter + nest_handoff_history、llama_index can_handoff_to 白名单、adk transfer 自动注入、deepagents/agentscope-java task 工具、claude Agent 工具）——零新概念、天然获得审批/观测/结构化参数。supervisor 只有两家当正经抽象（langchain4j SupervisorPlanner + ResponseScore 评分选优、MS Magentic 家族），langgraph 系拆独立生态包、crewai 是「委派工具」非调度器。group-chat 只剩 AutoGen 血统（MS orchestrations）与 dify 插件。**A2A 完整实现集中在 Java/企业阵营 + crewai**（agentscope-java 双向+starter、saa + Nacos 注册、crewai 双向 + 32 事件类型 + 反向出卡片），Google/MS 标 beta，研究型框架缺席。互操作三条通道：adapter（crewai agent_adapters）→ 协议（A2A/MCP 反向暴露）→ **引擎桥**（adk LangGraphAgent 连 checkpointer 语义都桥接、langgraph RemoteGraph 实现 PregelProtocol）。

### 3.10 持久化（[10](./dimensions/10-persistence.md)）
五个语义派系：图快照（langgraph 系 + MS：durability 三级 + pending writes + DeltaChannel 增量快照）、事件溯源（adk `state_delta` 免费获得审计/回放/rewind、dify 表族 + offload 二级表）、消息追加（spring-ai/langchain4j：无执行级 checkpoint，循环崩溃即丢轮内进度）、全量序列化（agentscope 双语 AgentState、openai RunState 版本化 1.0→1.13）、转录镜像（claude 本地 JSONL 真相源 + at-most-once 镜像协议）。**语义选择先于后端选择**：快照派免费 time-travel、溯源派免费审计、追加派两者都自建。**Java 阵营后端广度系统性反超**（langgraph4j 8 saver / saa 9+5 / agentscope-java 7 + CAS 乐观并发 vs langgraph 官方 3 个），但 langgraph 用「窄接口 + conformance 套件」把协议质量留在官方。恢复粒度谱系到 claude 的**任意消息点截断**（resume_session_at + 轮次归属校验）为最细。跨线程长期状态仍是洼地：只有 langgraph `BaseStore` 做成带语义检索的一等抽象。

### 3.11 HITL（[11](./dimensions/11-hitl.md)）
16/17 具备（唯 spring-ai 官方留白）。四种中断范式：异常式 interrupt（langgraph `PregelScratchpad` 顺序匹配 + 节点重放）、终态式（agentscope-java `PERMISSION_ASKING`、MS `IDLE_WITH_PENDING_REQUESTS`——把「等人」做成正常返回值，天然适配无状态 Web 服务）、事件往返（agentscope Require 事件族、llama_index wait_for_event、adk 确认工具 + function_response 回执）、回调审批（claude can_use_tool 反向 RPC，审批时可改输入 + 动态改权限规则）。两条强合流：**审批与持久化合流**（MS pending 请求进 checkpoint、openai RunState 含审批状态、agentscope parked、dify WorkflowPause——「等人」与「崩溃恢复」共享通道）；**粒度下沉到参数/路径语义级**（MS ToolApprovalRule 参数匹配、deepagents exact/bulk 路径语义 + 三类绕过防御、agentscope-java resume payload 防伪造校验）。粘性授权（always_approve / ToolApprovalState / PermissionUpdate 六种变更）成为差异化卖点。

### 3.12 观测评估（[12](./dimensions/12-observability-eval.md)）
OTel 赢下标准之争的一半（9 家直埋，agentscope 双语/spring-ai/langchain4j 对齐 gen_ai semconv；MS 的遥测是可剥离洋葱层 + feature usage 位图进 User-Agent）；另一半是商业生态绑定（LangChain 系自有 callback→LangSmith、openai 自有 trace 树→自家 ingest、claude 只透传 traceparent）。**默认外发是隐私硬事实**：仅 openai-agents（5s 批量送 api.openai.com）与 crewai（匿名 OTLP 送 telemetry.crewai.com:4319）默认开启，LangSmith 需 env+key 显式开启。span 粒度下沉到图节点/边（saa 唯一到 edge 级）。**eval 是全场最大空白**：完整开源工具链只有 adk-python（轨迹评估 + LlmAsJudge + 用户模拟器 + conformance CLI）与 llama_index（RAG 指标 core 内置）；多数热门框架零 eval。dev UI 三形态对应三条商业化路径（开源本地台拉新 / 嵌入式调试服务存量 / 闭源平台付费墙）。

### 3.13 安全治理（[13](./dimensions/13-security-governance.md)）
三层格局：**平台级纵深**（dify moderation + RBAC + 双沙箱含 Linux landlock；MS 内容标签 Integrity×Confidentiality + 参数级审批 + Purview；agentscope 双语权限引擎；openai 三层 guardrail + 7 云沙箱）> **切面留钉子**（adk callback 六切入点 + Model Armor 生态、crewai hooks、langchain 四个具体中间件）> **引擎零安全**（langgraph/langgraph4j 刻意不做）。**Claude Code 式「规则×模式×审批回调」三层权限引擎已被 4 家产品化**且都把审批决定做成可持久化语义。内容安全审查没有一家开源框架想做（只 dify 内置，MS 外推 Purview、Google 外推 Model Armor）。guardrail 的差异化在执行时机（openai 与模型调用 gather 并发 + tripwire 取消模型任务）与处置语义（工具输出三态）。**fail-closed 成为 harness 框架的显性卖点**（deepagents execute×权限直接 NotImplementedError、agentscope bypass 免疫 safety ASK）。

### 3.14 部署运行时（[14](./dimensions/14-deployment-runtime.md)）
四梯队：**全家桶平台**（dify 13 核心服务 compose——全量 docker-compose.yaml 定义 39 个 service，其余为约 20 个可选向量库/中间件——+ Celery 分级队列 + CFS 时间片；agentscope-java 三进程 + Helm + aistio）> **CLI + 云部署器**（adk-python 全家桶全开源含 deploy；langgraph 开源 cli 编排闭源 `langgraph-api` 镜像）> **服务工厂**（agentscope `create_app` 可 mount 的 FastAPI；adk-java Maven goal）> **纯库**（langchain/langchain4j/spring-ai/llama_index/openai/claude 完全外置）。**「部署」边界正从运行时移向编排面**——langgraph 生产 server、crewai deploy/triggers、MS durable 扩展（ADR-0032 已外置独立仓）都是商业/独立生命周期侧。定时任务是暗门槛：只有 dify（节点触发器 + beat）、agentscope 双语、saa、deepagents talon（实验）四家半有正式 cron 抽象，而「常驻/周期 agent」恰是 2026 的主形态。多副本 HA 共识 = 外部状态存储 + 无本地真相；agentscope-java 的 CAS 乐观并发是唯一把多节点写冲突提升为框架语义的。

### 3.15 管理平面（[15](./dimensions/15-management-plane.md)）
只有 dify 是满配玩家（Web 控制台全量 + tenant_id 贯穿业务表 + 工作流/Skill 双版本化不可变发布 + billing 模块 + DSL 导入导出）；agentscope-java 是第二家把管理台做进开源的（React 前端 + AgentRegistry/CommandPlane + 注册中心生态）。其余分层：企业付费控制台（crewai AMP / langgraph Studio / OpenAI 平台 / LlamaCloud）、本地开发台（adk web / MS devui / saa admin+studio）、纯库无管理面。**配置中心被 Java/中国生态垄断**（saa Nacos 四注入器、adk-java YAML 热重载、agentscope-java nacos/higress）——Spring/Nacos 栈里「运行时改配置不重启」是既定运维契约。多租户诚实分级：dify 数据模型级 > adk 命名空间语义 > claude docstring 建议。**成本看板全行业留白**（dify billing 调的还是外部计费 API）；版本管理两极：数据库双态（dify）vs git（代码框架）。

---

## 4. 架构哲学与跨语言对齐度

### 4.1 五条哲学断层线

1. **库 → harness → 服务 → 平台的能力栈分工**。纯库（langchain4j/spring-ai/llama_index）只给抽象；harness（deepagents/claude-sdk/MS harness）预装产品级中间件（文件系统/权限/压缩）；服务工厂（agentscope 双语）把企业能力做成可 mount 的进程；平台（dify）自带租户/计费/画布。**同一维度在不同层的实现者不同**：模型 fallback 在库层缺席、在 harness 层是中间件、在平台层是凭据池产品功能——「谁负责」比「有没有」更能预测演进方向。
2. **图抽象 vs agent 抽象 vs 拒绝抽象**。Pregel 引擎（langgraph/MS）用超步 + channel 差分换来 durable 的一切；事件流（crewai/llama_index）换来低门槛与天然流式；agent 树（adk）拒绝暴露图概念；openai-agents/claude-sdk/spring-ai 连编排都不做。2025-26 的裁判性证据是 agentscope v2 删组合子：**中间态的细粒度编排 API 生命周期最短**，要么下沉引擎、要么上浮平台。
3. **引擎外置成为分层常规**。dify→graphon、llama_index→llama-index-workflows（core 只剩 1 行 shim）、langchain→硬依赖 langgraph、MS durable→独立仓、saa→合规 fork langgraph4j（LICENSE 与 `jdbc:h2:mem:langgraph4j` 残留实锤同源）。编排引擎正变成可替换的独立资产。
4. **单 agent 深耕与多 agent 协作的分野**。handoff-as-tool 是最小公分母，但真正的深度在单 agent 内部：上下文压缩、权限、skills、预算——2026 年的竞争重心从「怎么编排多个 agent」移回「一个 agent 能跑多深」。A2A 反而是 Java 企业阵营（注册中心/服务治理诉求）领先 Python 研究阵营的少数维度。
5. **开源边界即商业模式**。「协议开源、实现闭源」（langgraph SDK 全有 server 闭源、crewai 连企业 API 契约文档都齐了就是不实现）vs「全开源换云导流」（adk deploy 全家桶、agentscope-java Helm 五件套）vs「观测面即商业化」（trace 默认外发的 openai、控制台付费墙的 AMP/LangSmith）。选型时看清 ⚠️ 闭源边界与遥测默认值，比功能清单更重要。

### 4.2 跨语言对齐度总评（三对）

| 对 | 版本 | 对齐度结论 | 关键差异（证据见各维度 §N.3） |
|---|---|---|---|
| **langgraph ↔ langgraph4j** | 1.2.11 ↔ 1.9.0-beta6 | **灵魂对齐、深度分叉**：checkpoint/interrupt/HITL/subgraph 实质对齐；引擎层缺 Pregel superstep、Send 动态扇出、DeltaChannel、跨线程 BaseStore（core 无任何 store 文件，实锤） | Java 反超：8 个官方 saver 后端（Python 官方 3 个）、interruptBeforeEdge 边粒度中断、core 内置 Skill 机制（Python 主仓 ❌、让给 deepagents）、AgentEx 预制审批节点 |
| **adk-python ↔ adk-java** | 2.9.0 ↔ 1.9.x | **概念对齐、实现代差（含一个 major 版本差）**：agent 树/transfer/MCP 三传输/Session 语义两侧同构 | Python 独有：通用 workflow 图引擎（`BaseAgent(BaseNode)`）、auth/ 凭据全套、LlamaIndex 桥、eval 全工具链（Java 三端点全 501 stub）、LlmRegistry 广度。Java 独有：PersistBarrier 读一致原语、BigQuery 审计插件、YAML Config Agent 热重载、Sync 回调变体。Java 最痛缺口：Session 无 JDBC 后端（自托管短板） |
| **agentscope ↔ agentscope-java** | 2.0.8 ↔ 2.0.2+ | **对齐度最高的一对，且双向超出**：ReAct 骨架/权限引擎 5 模式/MCP/事件流语义同构 | Python 先行：SOP 引擎/GoalPipeline/分层压缩水位/自主压缩工具/ClawHub 市场。Java 先行：服务化三进程 + Helm + a2a-server + 注册中心 + CAS 乐观并发 + elicitation + SkillBox 仓库矩阵。**唯一倒挂且是系统性 v2 清洗**：Java memory API 整包 @Deprecated(forRemoval)，且不止 memory——hook 包（17 个事件类）、RAG 四件套、LongTermMemory 系、SkillBox 同列弃用名单（change-log Part B，2.1 移除），而官方扩展仍依赖旧 API |

**跨语言共性规律**：接口与概念层一周内对齐，工程纵深（后端矩阵、eval、auth、UI）长期滞后甚至战略性放弃；Java 版的差异化贡献集中在「企业运维物」（注册中心/并发控制/审计/热重载），Python 版集中在「研究前沿物」（压缩算法/规划器/eval）。

---

## 5. 选型建议（五个场景）

### 5.1 企业流程自动化（审批流、跨系统集成、非开发人员维护）
- **首选 dify**：唯一把「可视化画布 + HITL 表单 + 多租户 RBAC + 版本化发布 + 定时触发」做成完整开源产品的框架（19 种节点、HUMAN_INPUT 表单含超时处置与权限矩阵、tenant_id 贯穿、Celery 分级队列）。代价：Python/TS 技术栈锁定、引擎外置 graphon 的自主可控需评估、 Helm 在社区仓。
- **代码优先且要求断点续跑/durable**：**langgraph**（Pregel + durability 三级 + pending writes 是最成熟的执行语义），但生产 API server 与 cron 在闭源 Platform——自托管需接受「开源引擎 + 自建 serving」。
- **Java/Spring 企业栈**：**spring-ai-alibaba**（fork langgraph4j 图引擎 + Nacos 配置热更 + A2A + admin 画布，还能吸收 Dify DSL 存量）或 **agentscope-java**（三进程控制平面 + Helm，唯一能治理异构框架 agent 的开源方案）。
- **Azure 栈**：**agent-framework**（每超步 checkpoint + request_info 与恢复同通道 + Purview 合规外评）。

### 5.2 Coding Agent / 深任务 harness
- **能力最全但绑 Claude**：**claude-agent-sdk**——权限规则文法/hooks/子代理/skills 生态 + 消息级 resume + USD 预算；模型锁定与 CLI 黑盒是代价。
- **模型中立的开源范本**：**deepagents**——虚拟文件系统 + 子代理状态白名单 + 五层上下文防御 + prompt cache 栈序；底层即 langgraph，可深度定制。
- **Azure/企业栈**：**MS agent-framework 的 `create_harness_agent`**（todo/mode/skills providers + 工具审批规则，Claude Code 式参考实现进核心库）。
- **Java 栈**：**spring-ai-alibaba graph-core**（SKILL.md 注册表 + TodoListInterceptor + TaskTool 子代理，Java 系最接近 coding-agent 形态）或 **agentscope-java harness**（19 个中间件组装）。
- 该场景硬指标：上下文工程（维度 2/3/6）+ 权限（13）+ 持久化（10）——这四项的头部实现恰是 claude-sdk/deepagents/MS/agentscope 四家。

### 5.3 客服（知识库问答、人工接管、会话量弹性）
- **首选 dify**：知识库（hybrid + rerank + 引用元数据）+ 标注回复（相似问直接回放人工答案）+ ask_human 与表单同轨 + 会话/消息全持久化 + 多渠道——客服所需能力它全有现成产品面。
- **云原生栈**：**adk-python**（SessionService 4 核心 + 2 集成后端 + Vertex RAG/MemoryBank 托管 + 全场唯一完整 eval 可持续调优客服质量），接受 GCP 绑定。
- **要最强的跨会话个性化记忆**：**crewai** 的统一 Memory（复合评分 + 半衰期）目前最精细，但 OSS 无服务端、控制台在付费 AMP——更适合嵌入式集成而非独立客服平台。

### 5.4 数据分析（Code Interpreter、RAG、可溯源）
- **首选 llama_index**：RAG 全管道（15+ 索引/混合检索/rerank/内容块级 citation）+ CodeActAgent（写并执行 Python）+ eval 指标全家桶 core 内置——分析型 agent 的「检索准 + 引用实 + 可评估」三件套最齐。
- **全押 OpenAI 生态**：**openai-agents-python**——CodeInterpreter + FileSearch 托管工具 + 7 云厂商沙箱（唯一把沙箱做成带 manifest/快照/挂载安全的子系统）；注意关掉默认 trace 外发。
- **Java 栈**：**langchain4j**（core 内全 RAG 管道 + ReRankingContentAggregator + GraalVM 沙箱）。

### 5.5 高合规（金融/医疗/政务：审计、PII、权限、私有化）
- **平台级合规**：**dify 私有化部署**（moderation 内置 + RBAC + 凭据加密 + 运行审计落库 + 13 核心服务全自托管）——注意部分审计导出在企业版。
- **代码级纵深**：**agent-framework**（内容标签信息流控制 + 参数级审批 + Purview 策略外评 + OTel 直埋）适合 Azure 合规体系；**agentscope 双语**（权限引擎 5 模式 + bypass 免疫 + fail-closed + 完全私有部署无 SaaS 依赖）适合自主可控优先。
- **Java 合规栈**：**spring-ai**（Micrometer/OTel gen_ai semconv 直连企业 APM + 语义缓存 + 模板注入防护）+ 自建 PII/审计（spring-ai 本体这些是 🟡）。
- **本场景要避开的坑**：默认遥测外发的 openai-agents/crewai（不关不能用）；引擎层零安全的 langgraph 必须搭配上层治理；无 JDBC 会话后端的 adk-java 在私有数据库要求下是硬伤；「遗忘/按用户删除」全行业空白——记忆系统合规必须自己在存储层实现。

---

## 6. 附录

### A. 分析基线（git HEAD，2026-09-12 记录）

| 仓库 | 语言 | HEAD | 日期 | 版本 |
|---|---|---|---|---|
| langchain | Python | 348c9dc572 | 2026-09-11 | langchain 1.4.0 / core 1.6.3（classic 1.0.8） |
| langgraph | Python | e539ac122 | 2026-09-09 | langgraph 1.2.11 / checkpoint 4.2.0 / prebuilt 1.1.0 |
| langgraph4j | Java | c2cf2e33 | 2026-09-06 | 1.9.0-beta6（Java 17；双集成 langchain4j 1.19 / Spring AI 2.0.1） |
| langchain4j | Java | 0028928ea | 2026-09-11 | 1.21.0-beta31-SNAPSHOT（父 pom 108 模块） |
| deepagents | Python | 9e7d62ff6 | 2026-09-11 | deepagents 0.7.13（monorepo 另含 code/acp/talon/evals） |
| agent-framework | Python/.NET | 3c6707077 | 2026-09-11 | py 1.18.0 / dotnet 1.21.0 |
| adk-python | Python | 7b246e01 | 2026-09-11 | 2.9.0（version.py；tag v1.32.0 落后 1611 commits，以包内为准） |
| adk-java | Java | fda5a102 | 2026-09-10 | 1.9.1-SNAPSHOT（tag v1.9.0+25） |
| openai-agents-python | Python | fbd2dbca | 2026-09-11 | 0.22.2 |
| claude-agent-sdk-python | Python | f101a76 | 2026-09-11 | 0.2.152（捆绑 Claude Code CLI 2.1.269） |
| crewAI | Python | 894898f84 | 2026-09-12 | 1.15.21+11 commits（scm versioning，git describe 实测；uv workspace 6 成员） |
| dify | Python/TS/Go | 79effdd498 | 2026-09-12 | 1.17.1（graphon==0.7.0） |
| llama_index | Python | 7169bcd0d | 2026-09-11 | core 0.14.24（workflows 外置包 2.23.3） |
| agentscope | Python | b82253ba | 2026-09-11 | 2.0.8 |
| agentscope-java | Java | c5db8f72 | 2026-09-11 | 2.0.3-SNAPSHOT（tag v2.0.2+144，Maven 7 模块） |
| spring-ai-alibaba | Java | f82da0b50 | 2026-08-25 | 1.1.2.2（基于 Spring AI 1.1.2） |
| spring-ai | Java | b5eb0272f | 2026-09-11 | 2.0.2-SNAPSHOT（168 模块） |

### B. 证据索引

- **逐框架档案**（定位/结构/核心抽象/15 维评级/证据明细/设计决策）：[profiles/](./profiles/) 17 份，文件名即仓库名。
- **逐维度分析**（17 框架全量矩阵/派系深析/跨语言对齐/趋势）：[dimensions/](./dimensions/) 15 份。
- 证据等级：【核心】= 主包正式实现；【示例】= examples/demo；【文档】= 文档或 docstring 宣称（如 claude-sdk 的 CLI 内行为）。
- **未纳入源码结论的框架**：Agno、smolagents、Letta、Pydantic AI、Mastra 等未本地克隆，本报告不下判断；Temporal 亦未克隆，正文仅将其作为 durable execution 参照系提及（§3.10/§3.14），不构成源码级对比。如需纳入可按 `~/develop/opensource/AGENTS.md` 的镜像规范克隆后补做档案。

### C. 二次核验修正记录（Phase 2 对 Phase 1 档案的勘误）

1. langgraph4j 档案宣称「fallback 由 langchain4j 生态承担」——证伪（langchain4j 全仓零命中，Java 双仓共同空白）。
2. langchain4j 档案「ChatMemoryStore 仅 InMemory」——证伪（实有 cassandra/oracle/coherence/tablestore/azure-cosmos 5 个生产实现）；真正留白的是 AgenticScopeStore。
3. claude-sdk conformance 契约数 13 → 修正为 14（源码自述）。
4. openai-agents 工具超时「3 策略」→ 修正为 2 策略（error_as_result / raise_exception）。
5. MS durable execution「仓内 🟡」→ 修正为已外置独立仓（ADR-0032）。
6. dify「A2A 支持」→ 证伪（全仓 rg 仅 uv.lock 哈希子串误报，真实零命中）。
7. crewai「devtools」→ 纠偏（内部文档工具非产品，OSS 调试面实为 TUI 三件）。
8. langgraph 引擎 recursion_limit 默认值传闻 25 → 实为 10007（25 是 langchain-core LCEL 路径默认）。

### D. Review 修正记录（2026-09-12 源码抽查复核）

对报告断言抽样 35 条直接对照 `~/develop/opensource` 源码复核，33 条精确命中（含 recursion_limit=10007、openai trace 外发端点、crewai telemetry.crewai.com:4319、adk-java eval 三端点 501、langgraph4j 8 saver/无 Store/SkillInjector、saa `jdbc:h2:mem:langgraph4j` 残留、agentscope `_agent.py` 恰 3915 行、adk-python tag 落后恰 1611 commits、llama_index 恰 103 个 llms 包、spring-ai 恰 15 models/22 vector-stores 模块、附录 A 版本基线 15 项全对）。修正如下：

1. langchain partners 16 → **15**（`libs/partners/` 实际 15 个包目录，另 2 项为 Makefile/README）。
2. 总览矩阵第 12 列增加口径脚注：该列为「观测+评估」合并评级，✅ 多由 tracing 支撑，eval 格局以 §3.12 为准（adk-java eval 全 501 stub、crewai 无开源 eval、langchain 评估在 LangSmith 商业生态）。
3. 统一 langgraph 官方后端计数口径为 **3 个**（InMemory 内置 + postgres/sqlite 两个外部模块），档案 §7 原文「两个」已同步。
4. adk-python SessionService 口径统一为「**4 核心实现 + 2 集成包**」（InMemory/SQLite/SQLAlchemy/VertexAi + Firestore/Redis 集成）。
5. dify compose 口径修正：核心服务 **13 个**（维度 14 自身枚举 api/api_websocket/worker/worker_beat/web/db/redis/sandbox/plugin_daemon/agent_backend/ssrf_proxy/nginx/local_sandbox），`docker-compose.yaml` 全量定义 **39 个 service**（含约 20 个可选向量库/中间件）。
6. crewAI 版本标注 1.15.21**+11 commits**（pyproject `version_provider="scm"`，git describe 实测）。
7. agentscope-java v2 弃用面补充：不止 memory——hook 包全量 17 个事件类、RAG 四件套、LongTermMemory 系、SkillBox 均 `@Deprecated(forRemoval, since="2.0.0")`（docs/v2/en/docs/change-log.md Part B，明示 2.1 移除）。
8. 附录 B 补 Temporal「提及但未纳入」说明；README 基线表与附录 A 全量同步（langchain4j 行补全、adk-java 1.9.1-SNAPSHOT、agentscope-java 2.0.3-SNAPSHOT、dify 语言标注补 Go——`dify-agent-runtime/go.mod` 实证）。
