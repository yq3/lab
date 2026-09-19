# Google ADK Java (adk-java) 框架档案

> 基线：~/develop/opensource/adk-java @ fda5a102 2026-09-10；版本 pom.xml `1.9.1-SNAPSHOT`（tag v1.9.0+25，Maven 多模块，Java 17）
> ⚠️ 分析时版本差：对照仓 adk-python 已是 **2.9.0**（`src/google/adk/version.py`），本仓为 1.x——第 7 节对齐结论中「Python 有 Java 无」的部分可能源于版本差而非平台定位差。

## 1. 定位

Google ADK 的 Java 版官方实现：与 Python ADK 同概念体系的「全代码 Agent 框架」，面向 Java/Spring 企业栈。核心库提供 Agent 树（LlmAgent + 三种 workflow agent）、RequestProcessor 管道式 LLM 流程、可插拔的 Session/Artifact/Memory 服务三件套与 OTel 观测；生态扩展（Spring AI / LangChain4j 模型桥、Firestore 持久化、Planners）与调试服务器（dev 模块，Spring Boot REST+WebSocket）拆在 contrib/dev 模块。目标用户是需要在 JVM 上构建与 Vertex AI 工具链（Agent Engine、Firestore、GCS、BigQuery）集成的企业团队。与 Python 版相比刻意保持概念对齐但能力面收窄（无 auth 框架、无通用 OpenAPI 工具、eval 为 stub、无通用 workflow 图）。

## 2. 仓库结构与核心包

构建：Maven 多模块（`pom.xml` 根 `1.9.1-SNAPSHOT`，`<java.version>17`），非 gradle。模块树（`pom.xml#<modules>`）：

| 模块 | 内容 |
|---|---|
| `core` | 主包 `com.google.adk`：agents / flows / sessions / artifacts / memory / models / tools / plugins / skills / summarizer / telemetry / codeexecutors / runner / events / apps |
| `contrib/spring-ai` | `SpringAI extends BaseLlm` 模型桥 + Spring Boot autoconfigure |
| `contrib/langchain4j` | `LangChain4j extends BaseLlm` 模型桥（单类） |
| `contrib/planners` | Planner 接口 + Sequential/Parallel/Loop/Supervisor/P2P 五种规划器 |
| `contrib/firestore-session-service` | Firestore Session/Memory 服务 + FirestoreDatabaseRunner |
| `contrib/samples`、`tutorials/*` | 示例（helloworld、mcpfilesystem、configagent、a2a_*、github 六件套、live-audio） |
| `dev` | Spring Boot 开发服务器（AdkWebServer，REST + WebSocket + deploy） |
| `a2a` | RemoteA2AAgent（消费侧）+ AgentExecutor（暴露侧，基于官方 io.a2a SDK） |
| `tokt` | 仅测试：Kotlin 互操作验证（无正式 Kotlin API，⚠️） |
| `maven_plugin` | `mvn google-adk:web`（WebMojo）启动 dev server + ConfigAgentWatcher |

## 3. 核心抽象清单

| 符号 | 路径 | 一句话说明 |
|---|---|---|
| `BaseAgent` | core/.../agents/BaseAgent.java | agent 树基类（唯一名校验、before/afterAgentCallback、runLiveImpl 直播流） |
| `LlmAgent` | core/.../agents/LlmAgent.java | LLM agent：model/instruction/tools/6 类回调（×Sync 变体）/input·outputSchema/maxSteps/fromConfig |
| `SequentialAgent` / `ParallelAgent` / `LoopAgent` | core/.../agents/*.java | 顺序/并行/循环 workflow agent（Loop 配 ExitLoopTool） |
| `BaseLlmFlow` / `SingleFlow` / `AutoFlow` | core/.../flows/llmflows/*.java | LLM 执行循环 + RequestProcessor 管道；AutoFlow=SingleFlow+AgentTransfer |
| `RequestProcessor`/`ResponseProcessor` | core/.../flows/llmflows/RequestProcessor.java | 请求/响应处理管道接口（Java 版独有架构形态） |
| `Runner` / `InMemoryRunner` | core/.../runner/Runner.java | appName + agent + 三服务的运行入口（Flowable\<Event\> 流式） |
| `InvocationContext` | core/.../agents/InvocationContext.java | 调用上下文：LLM 调用计数、resumable、endInvocation |
| `RunConfig` | core/.../agents/RunConfig.java | maxLlmCalls 默认 500 的硬护栏 |
| `State` | core/.../sessions/State.java | ConcurrentMap + delta 追踪 + `app:/user:/temp:` 前缀 + REMOVED 哨兵 |
| `BaseSessionService` 等 | core/.../sessions/BaseSessionService.java | 服务三件套接口（app/user/session 三元组多租户命名） |
| `Plugin` / `PluginManager` | core/.../plugins/Plugin.java | 单接口 14 个 default 钩子覆盖全部回调面 |
| `FunctionTool` | core/.../tools/FunctionTool.java | 反射式工具（`create(instance, Method)`，requireConfirmation 参数） |
| `McpToolset` | core/.../tools/mcp/McpToolset.java | MCP 消费：stdio/SSE/StreamableHttp 三种传输 |
| `SkillToolset` | core/.../tools/skills/SkillToolset.java | Agent Skills 渐进披露（list_skills/load_skill/load_skill_resource） |
| `LlmRegistry` | core/.../models/LlmRegistry.java | 模型名正则 → LlmFactory 注册表 |
| `Gemini` / `Claude` / `ApigeeLlm` | core/.../models/*.java | 三种原生模型接入 |
| `SpringAI` / `LangChain4j` | contrib/... | 生态模型桥（equals BaseLlm，接任意两家生态支持的模型） |
| `RemoteA2AAgent` / `AgentExecutor` | a2a/.../agent/RemoteA2AAgent.java、a2a/.../executor/AgentExecutor.java | A2A 消费（作子 agent/工具）与暴露（作 A2A server） |
| `EventCompactor` 系列 | core/.../summarizer/*.java | 滑窗/尾部保留/LLM 摘要三种事件压缩器 |
| `AdkWebServer` / `WebMojo` | dev/.../AdkWebServer.java、maven_plugin/.../WebMojo.java | dev server 及其 Maven 入口 |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | Gemini/Gemma/Apigee 原生 + Claude 直连 + SpringAI/LangChain4j 桥，全链路流式 | core/.../models/LlmRegistry.java#registerLlm；contrib/spring-ai/.../SpringAI.java#SpringAI |
| 2 | 上下文工程 | ✅ | 动态 Instruction、Instructions 变量注入、Compaction/Fencing、三种事件压缩器 | core/.../flows/llmflows/{Instructions,Compaction,Fencing}.java；summarizer/EventCompactor.java |
| 3 | 记忆 | 🟡 | MemoryService 抽象内置但实现仅 InMemory（+contrib Firestore），无 RAG 记忆库 | core/.../memory/InMemoryMemoryService.java；contrib/firestore-session-service/.../FirestoreMemoryService.java |
| 4 | RAG | 🔶 | 无 retriever/vector store 抽象，仅 VertexAiRagRetrieval 作工具 + LoadMemoryTool | core/.../tools/retrieval/VertexAiRagRetrieval.java |
| 5 | 工具系统 | ✅ | 反射 FunctionTool + AgentTool + MCP 三传输 + GCP 工具族 + 3 种代码执行器 | core/.../tools/FunctionTool.java#create；tools/mcp/McpToolset.java |
| 6 | Skill 机制 | ✅ | SkillSource（classpath/local/memory）+ SkillToolset 渐进披露，frontmatter 解析 | core/.../tools/skills/SkillToolset.java#getTools；skills/Frontmatter.java |
| 7 | 规划推理 | 🟡 | outputSchema/ExitLoopTool 在核心；LLM 动态规划器全在 contrib/planners | contrib/planners/.../SupervisorPlanner.java#askLlm；core/.../tools/ExitLoopTool.java |
| 8 | 编排 | ✅ | agent 树 + Sequential/Parallel/Loop；无 Python 版的通用 workflow 图 | core/.../agents/{SequentialAgent,ParallelAgent,LoopAgent}.java |
| 9 | 多 Agent | ✅ | transfer（AutoFlow 注入）+ AgentTool + A2A 双向（独立模块） | core/.../flows/llmflows/AgentTransfer.java；a2a/.../executor/AgentExecutor.java |
| 10 | 持久化 | 🟡 | 事件追加 + state_delta 溯源 + 可恢复执行；后端仅 InMemory/VertexAi(+Firestore)，无 JDBC | core/.../sessions/{InMemory,VertexAi}SessionService.java；agents/WorkflowAgentResumption.java |
| 11 | HITL | ✅ | `adk_request_confirmation` + 工具级 requireConfirmation + 长任务暂停恢复 | core/.../flows/llmflows/Functions.java#REQUEST_CONFIRMATION_FUNCTION_CALL_NAME |
| 12 | 观测评估 | ✅ | OTel span+7 指标、Plugin 体系、BigQuery 审计插件；eval 端点全为 stub（❌） | core/.../telemetry/{Instrumentation,Metrics}.java；dev/.../EvaluationController.java#runEval |
| 13 | 安全治理 | 🔶 | 无 guardrail 抽象；靠 10 类 callback/Plugin 自建；Docker 沙箱执行；BigQuery 审计 | core/.../plugins/agentanalytics/BigQueryAgentAnalyticsPlugin.java；codeexecutors/ContainerCodeExecutor.java |
| 14 | 部署运行时 | 🟡 | dev 模块 Spring Boot 服务器（`mvn google-adk:web`）+ Agent Engine 部署器；无 CLI 全家桶 | dev/.../AdkWebServer.java#main；maven_plugin/.../WebMojo.java；dev/.../deploy/AgentEngineDeployer.java |
| 15 | 管理平面 | 🔶 | dev server REST（agents/sessions/artifacts/graph/debug/execution）无 UI、无多租户管理 | dev/.../web/controller/（7 个 Controller）；GraphController.java 返回 DOT |

## 5. 维度证据明细

**1 模型接入**【核心】`LlmRegistry` 默认仅注册 3 个模式：`gemini-.*`、`gemma-.*` → Gemini，`apigee/.*` → ApigeeLlm（models/LlmRegistry.java:40-42，可 `registerLlm` 扩展）。`Claude extends BaseLlm` 直连官方 Anthropic Java SDK（models/Claude.java:56-96，构造器注入 AnthropicClient，**未进默认 registry**，需手动实例化）。`models/chat/` 是手写 Chat Completions HTTP 客户端，服务 Apigee 的 openai 端点（ApigeeLlm.java:92）。生态桥：`SpringAI extends BaseLlm` 包装 Spring AI ChatModel/StreamingChatModel（含 autoconfigure starter）、`LangChain4j extends BaseLlm` 单类桥——两者即 Java 版的 "LiteLlm 等价物"（接 Claude/OpenAI/本地模型等全靠桥）。流式全链路 Flowable\<Event\>（BaseLlmFlow.java:563 runLive）。无 fallback router / retry 抽象（models/ 下 rg 'fallback|retry' 无正式实现）。usage 经 google-genai 类型透传（LlmResponse）。
**2 上下文工程**【核心】`Instruction.Static/Provider` 支持运行时按 ReadonlyContext 动态生成（agents/Instruction.java；LlmAgent.java:683 canonicalInstruction）。`Instructions` 处理器注入 globalInstruction/instruction 与 `{state_var}` 替换；`Compaction` + summarizer 包：`SlidingWindowEventCompactor`/`TailRetentionEventCompactor`/`LlmEventSummarizer` 三策略（summarizer/）。`Fencing`：把其他 agent 上下文以 `<<<BEGIN_QUOTED_AGENT_CONTENT>>>` 引用块包裹并可 ELIDED（flows/llmflows/Fencing.java）。`includeContents=NONE` 可完全不带历史（LlmAgent.java:87）。
**3 记忆**【核心+示例】接口三方法（sessionToMemory/searchMemory）core 内仅 InMemoryMemoryService；contrib FirestoreMemoryService 补一个云后端。`LoadMemoryTool`/`preload` 思路的 LoadArtifactsTool 在 tools/。无 Python 的 VertexAiMemoryBank/VertexAiRag 记忆服务。
**4 RAG**【核心-工具级】`VertexAiRagRetrieval extends BaseRetrievalTool`（tools/retrieval/）与 `VertexAiSearchTool`、`UrlContextTool`、`GoogleSearchTool`（grounding）——全部是「作工具喂给 LLM」形态，框架级 retriever/ingestion 管道不存在。
**5 工具系统**【核心】`FunctionTool.create(instance, Method)` 反射生成 schema，参数注解 `@Annotations.Schema(name/description/optional)`（tools/Annotations.java），`requireConfirmation` 布尔参直接内置审批语义（FunctionTool.java:58）。MCP：`McpToolset` 支持 Sse/StreamableHttp/Stdio 连接参数（McpToolset.java:72/100/214），McpSessionManager 管会话。`ApplicationIntegrationToolset` 从 GCP Application Integration 拉取 OpenAPI spec 生成工具 + ConnectionsClient 管 OAuth 凭据（applicationintegrationtoolset/IntegrationClient.java:170 generateOpenApiSpec）——**通用 OpenAPI tool 不存在**，这是 GCP 专属替代。`LongRunningFunctionTool` + `SetModelResponseTool`（动态换模型响应）。代码执行 3 种：BuiltIn/Container(Docker, docker-java)/VertexAi。ComputerUse 工具族（computeruse/）。
**6 Skill**【核心】`SkillSource` 抽象（ClassPath/Local/InMemory）+ `Frontmatter` 解析；`SkillToolset` 注入默认系统指令要求模型先 `load_skill` 再执行——与 Anthropic Agent Skills 同款渐进披露三工具（tools/skills/ListSkillsTool、LoadSkillTool、LoadSkillResourceTool）。
**7 规划推理**【核心+contrib】核心有 outputSchema（SchemaUtils.validateOutputSchema 校验后入 state，LlmAgent.java:639）、inputSchema、ExitLoopTool、per-agent maxSteps。`LlmAgent.planning` 布尔字段在 core 定义但 core 内无消费点（仅 getter，LlmAgent.java:756；⚠️ 消费链路待确认，contrib PlannerAgent 自带规划循环 contrib/planners/.../PlannerAgent.java:102-109）。contrib/planners 提供 Planner 接口 + Sequential/Parallel/Loop/Supervisor（LLM 决定下一个子 agent）/P2P 五种。
**8 编排**【核心】Sequential/Parallel/Loop 为「agent 树子节点」而非图；dev GraphController 可输出 agent 树 DOT 图（GraphController.java:182 dotSourceOpt）。无 join/dynamic node/通用 DAG（Python workflow/ 包的对应物缺失）。
**9 多 Agent**【核心】transfer：AutoFlow 额外挂 AgentTransfer 处理器；`disallowTransferToParent/Peers` 且无子 agent 时自动降级 SingleFlow（LlmAgent.java:605 determineLlmFlow）。transfer 事件直接 `nextAgent.runAsync(context)` 接续流（BaseLlmFlow.java:488-504）。`AgentTool`（agent-as-tool）。A2A 双向在独立 `a2a` 模块：RemoteA2AAgent 消费远端、AgentExecutor 实现 io.a2a 的 agentexecution 接口把 Runner 暴露为 A2A server。
**10 持久化**【核心】Session = appName/userId/sessionId 三元组（多租户命名内置）；一切变更落 EventActions.state_delta（事件溯源，services 只需追加存储）。`State` 用 ConcurrentMap + delta + REMOVED 哨兵表达删除（sessions/State.java:31-40）。**无 JDBC/SQLite/Postgres 后端**（Python 有 DatabaseSessionService+migration；Java 仅 InMemory/VertexAi + contrib Firestore——对自托管企业场景是明显短板）。可恢复执行：`isResumable && Functions.hasPendingLongRunningCall(eventList)` 时暂停流程（BaseLlmFlow.java:541-547）+ `WorkflowAgentResumption` 从事件索引恢复子 agent 位置 + `PersistBarrier.awaitPersisted` 保证下一步请求不读到未持久化会话（Java 独有）。
**11 HITL**【核心】`adk_request_confirmation` 函数调用名（flows/llmflows/Functions.java:71）+ `events/ToolConfirmation`（结构化确认请求）+ `RequestConfirmationLlmRequestProcessor`（在历史中发现 pending 确认调用时接管请求）。工具级 `requireConfirmation` 构造参数。长任务暂停/恢复见维度 10。
**12 观测评估**【核心】OTel：`invoke_agent <name>` / `execute_tool <name>` span（telemetry/Instrumentation.java:185/255）；Metrics 7 个 histogram（agent/tool 时长、请求响应大小、workflow 步数，telemetry/Metrics.java:51-57）；dev 模块 OpenTelemetryConfig + ApiServerSpanExporter。Plugin 体系：单接口 14 钩子（plugins/Plugin.java:54-216：onUserMessage/before·afterRun/onEvent/onRunError/close + before·after·onError × agent/model/tool），内置 Logging/GlobalInstruction/ContextFilter/BigQueryAgentAnalytics（BigQuery+GCS 落审计）。**eval：dev EvaluationController 的 run-eval/getEvalResult/listEvalResults 全部返回 501/空并打 log.warn "not implemented"（EvaluationController.java:83-123）——仅 API 形状，无实现**。Callback 双体系（LlmAgent builder 回调 vs Plugin）功能重叠。
**13 安全治理**【核心-自建】无 guardrail/pii 抽象；治理靠 beforeToolCallback/Plugin（如 ContextFilterPlugin 过滤上下文）与 `NamedToolPredicate`（tools/NamedToolPredicate.java，工具集黑白名单）。沙箱：ContainerCodeExecutor 用 docker-java 起容器执行代码（减 capability）。审计：BigQueryAgentAnalyticsPlugin。
**14 部署运行时**【核心+dev】dev 模块 = Spring Boot 应用（AdkWebServer @SpringBootApplication），REST Controller 7 个（agent/session/artifact/debug/graph/execution/evaluation）+ LiveWebSocketHandler（直播音频）；入口 `mvn google-adk:web -Dagents=...`（WebMojo，@Mojo(name="web")，支持 ConfigAgentWatcher 热重载 YAML agent）。`dev/deploy/AgentEngineDeployer` 部署到 Vertex AI Agent Engine。无 Python 的 `adk run/eval/api_server` CLI 全家桶。
**15 管理平面**【示例级】dev server 的 REST 面即全部管理能力；无内置 Web UI（dev 模块无静态资源目录，⚠️ 是否有配套外部前端项目待确认）；GraphController 提供拓扑 DOT。无 tenant/billing/config center。

## 6. 设计决策要点

1. **RequestProcessor 管道而非巨型循环**：把 Instructions/OutputSchema/Compaction/Fencing/AgentTransfer/RequestConfirmation 做成可组合处理器（SingleFlow 7 个 + AutoFlow 加 1 个），agent 配置（disallowTransfer、无子 agent）决定 flow 形态（SingleFlow vs AutoFlow）——比 Python 版的流程内分支更「库化」，用户可自定义处理器插入管道。
2. **Sync + 异步双回调面**：每类回调提供 `XxxCallback`（Maybe 响应式）与 `XxxCallbackSync`（同步 Optional）两套，Java 用户写同步逻辑零 RxJava 心智负担（LlmAgent.Builder 两个重载）。
3. **Plugin 单接口 vs Callback 多挂点双轨**：Plugin 一个接口 14 个 default 方法可整体注册（PluginManager），与 LlmAgent 上的细粒度回调列表并存——前者便于「打包横切能力」（如 BigQuery 审计插件），后者便于单 agent 定制；两轨语义重叠是已知税。
4. **模型接入走「桥优先」**：核心只做 Gemini/Apigee/Claude 三原生实现，其他模型交给 SpringAI/LangChain4j contrib 桥——用 JVM 生态最厚的两个模型抽象换 LiteLlm 式广度。
5. **持久化后端「云优先，自托管留白」**：InMemory 之外只有 VertexAi 与 contrib Firestore，刻意不做 JDBC——与 Python（SQLite/SQLAlchemy/迁移框架）形成企业采购路径差异。
6. **YAML Config Agent + 热重载进核心**：`LlmAgent.fromConfig` + YamlPreprocessor + maven_plugin 的 ConfigAgentWatcher，YAML 定义 agent 树（含回调类名、工具、子 agent，contrib/samples/configagent 七种配置样例）——Java 侧无 CLI，用 Maven goal + YAML 提供「低代码调试」体验。
7. **持久化屏障保证读一致性**：PersistBarrier.awaitPersisted 在下一步 LLM 请求前等待本步事件落库（BaseLlmFlow.java:551-557），流式 + 事件溯源下的顺序一致性做成显式原语。

## 7. 跨语言对齐（vs ~/develop/opensource/adk-python @ 7b246e01，**版本 2.9.0 vs 本仓 1.9.1-SNAPSHOT，Python 领先一个大版本，下表「缺失」可能含版本差因素**）

| 维度/能力 | Python（2.9.0） | Java（1.9.1-SNAPSHOT） | 对齐度 |
|---|---|---|---|
| Agent 家族 | base_agent/llm_agent/sequential/parallel/loop + **langgraph_agent**、_managed_agent | BaseAgent/LlmAgent/Sequential/Parallel/Loop（无 LanggraphAgent） | **已对齐**（主家族） |
| Flows | llm_flows：single/auto flow、instructions/compaction/fencing/request_confirmation/identity/contents + **batch_tool_executor、nl_planning、context_cache、tool_call_rearranger、tool_error_handler、interactions、model_response_finalizer、audio_\*** | SingleFlow/AutoFlow + Instructions/Compaction/Fencing/RequestConfirmation/Identity/Contents/CodeExecution + **PersistBarrier（Java 独有）** | **部分**：核心管线对齐，Python 多 8+ 处理器 |
| Callbacks | before/after × agent/model/tool + on_error × model/tool，列表化（llm_agent.py:886 canonical_*） | 同 10 类 + 全部 Sync 变体 + Plugin 单接口体系（Python 亦有 plugins/ 但多 4 个内置：auto_tracing、reflect_retry、multimodal_tool_results、save_files_as_artifacts） | **已对齐**（Java 的 Sync 变体是加分项） |
| SessionService | InMemory/**SQLite**/**Database(SQLAlchemy+migration)**/VertexAi（4 后端） | InMemory/VertexAi + contrib Firestore（无 JDBC） | **部分**（后端 4:2+1，缺开源自托管 DB） |
| ArtifactService | InMemory/**File**/GCS（3） | InMemory/GCS（2，无本地 File） | **部分** |
| MemoryService | InMemory/**VertexAiMemoryBank**/**VertexAiRag**（3） | InMemory + contrib Firestore | **部分**（缺 RAG 记忆库） |
| 模型 | anthropic/**lite_llm**/gemma/google_llm/apigee/**fallback_model** | Gemini/Gemma/Apigee registry + Claude（未入 registry）+ SpringAI/LangChain4j 桥（🟡 等价广度） | **部分**（无 fallback router） |
| Auth 框架 | **auth/**：auth_schemes/auth_credential/credential_manager/exchanger/refresher/oauth2 + openapi_tool 挂 auth | **❌ 无 auth 包**（仅 AppIntegration 内 GCP Connections 凭据 helper） | **缺失** |
| OpenAPI 工具 | **openapi_tool**（通用 spec → tools，含 auth） | 仅 ApplicationIntegrationToolset（GCP 专属，从其 OpenAPI spec 生成） | **缺失**（通用形态） |
| MCP | mcp_tool/：消费（stdio/sse/streamablehttp）+ **_agent_to_mcp 反向暴露** + load_mcp_resource | McpToolset 消费三传输；无反向暴露为 MCP server | **部分** |
| A2A | core 内 a2a/（to_a2a、experimental） | 独立 a2a 模块（RemoteA2AAgent + AgentExecutor，官方 io.a2a SDK） | **已对齐**（模块位置不同） |
| Skills | tools/skill_toolset.py + skills 相关 | skills/ 包 + SkillToolset 三工具渐进披露 | **已对齐** |
| Planners | planners/（base/built_in/plan_re_act）接 LlmAgent.planner 字段 | contrib/planners 五种（Sequential/Parallel/Loop/Supervisor/P2P）+ PlannerAgent；core 仅 planning 布尔位（⚠️ 消费链路弱） | **部分**（位置与实现集不同） |
| 通用 workflow 图 | **workflow/** 包（graph/node/join/dynamic node/function node/retry config） | ❌（仅三 workflow agent） | **缺失** |
| eval | **evaluation/** 巨型模块（eval set/指标/llm_as_judge/safety/simulation/GCS+local 管理）+ CLI | dev server 端点全 stub（501） | **缺失** |
| code_executors | 6 种（+GKE、UnsafeLocal、AgentEngineSandbox） | 3 种（BuiltIn/Container/VertexAi） | **部分** |
| CLI/调试 | cli/：`adk web/run/eval/api_server` + browser UI | maven_plugin `mvn google-adk:web` + Spring Boot REST/WS（无 UI，⚠️） | **部分** |
| 部署 | platform/（Cloud Run、Agent Engine） | dev/deploy/AgentEngineDeployer（Agent Engine） | **部分** |
| prompt 优化 | **optimization/**（GEPA 采样/优化器） | ❌ | **缺失** |
| 流式/直播 | live/ 包 + LiveWebSocket 等价 | LiveRequestQueue/GeminiLiveTransport/GenAiLiveTransport/audio flows + dev LiveWebSocketHandler | **已对齐** |
| 观测 | telemetry/（OTel） | telemetry/（OTel span+metrics）+ BigQuery analytics 插件 | **已对齐** |

对齐度小结：概念骨架（agent 树 + flows 管道 + 三件套服务 + callbacks/skills/A2A/OTel）**已对齐**；外围生态（auth、通用 OpenAPI、eval、通用 workflow 图、DB 后端、CLI、prompt 优化）**缺失或部分**。Java 版独有贡献：PersistBarrier、Sync 回调变体、SpringAI/LangChain4j 双桥、Maven goal + YAML Config Agent 热重载、BigQuery 审计插件。

---

*证据等级说明：除标注【示例】（contrib/samples、tutorials）外均为【核心】源码证据；⚠️ 三处：dev server 无内置 UI 是否有外部前端、`LlmAgent.planning` 在 core 的消费链路、tokt 模块仅为 Kotlin 互操作测试。*
