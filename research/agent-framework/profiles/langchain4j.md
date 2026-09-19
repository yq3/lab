# langchain4j 框架档案

> 基线：~/develop/opensource/langchain4j @ 0028928ea 2026-09-11；版本 1.21.0-beta31-SNAPSHOT（父 pom `pom.xml`）

## 1. 定位

Java 生态事实标准的 LLM 应用开发**库**（非平台）。核心理念是「声明式接口代理」：业务只写 Java interface + 注解，`AiServices` 用动态代理生成实现，把 prompt 组装、RAG、记忆、工具循环织进去。围绕它长出一个 108 模块的单体 Maven 仓库：core（零依赖抽象）+ 主模块（AiServices/ToolService）+ 约 30 个模型 provider + 约 20 个向量库 + 3 个代码执行引擎 + agentic 系列（多 agent 编排）。目标用户是 Java/Spring 企业开发者；Spring Boot / Quarkus / Helidon / Micronaut starter 在**独立官方仓库**（本仓库无 spring 依赖，`pom.xml` 全文无 spring 字样，已验证）。它受 LangChain(Python) 启发但非移植，是独立设计的 Java 原生 API。

## 2. 仓库结构与核心包

父 pom `pom.xml` 共 **108 个 `<module>`**（构建证据）。关键模块分层：

| 层 | 模块 | 内容 |
|---|---|---|
| 核心 | `langchain4j-core` | ChatModel/StreamingChatModel、ChatMemory、guardrail SPI、RAG 全管道、tool 注解、observability 事件 |
| 高层 | `langchain4j` | AiServices/DefaultAiServices、ToolService 推理循环、TokenStream、窗口记忆实现 |
| agentic | `langchain4j-agentic`（154 文件）+ `-a2a` + `-mcp` + `-patterns` | workflow/supervisor/scope/declarative/observability；A2A 客户端；GOAP/BDI/debate/voting/p2p/blackboard |
| skills | `langchain4j-skills` + `experimental/langchain4j-experimental-skills-shell` | Agent Skills（渐进披露）+ shell 技能 |
| provider | `langchain4j-{open-ai,anthropic,google-genai,vertex-ai,bedrock,ollama,mistral-ai,...}` | 模型接入（列举模式，未逐个精读） |
| 存储 | `langchain4j-{pgvector,milvus,qdrant,pinecone,chroma,elasticsearch,weaviat,...}` | 向量库集成 |
| 其他 | `langchain4j-mcp`(+docker)、`langchain4j-guardrails`、`langchain4j-observation`、`langchain4j-micrometer-metrics`、`langchain4j-reactive-streaming`、`langchain4j-kotlin`、code-execution-engines×3、web-search-engines×3、easy-rag | 周边能力 |

仓库内**无 examples 目录**（示例在独立仓库 langchain4j-examples），故本档案基本不出现【示例】级证据。

## 3. 核心抽象清单

| 符号 | 路径 | 一句话说明 |
|---|---|---|
| `ChatModel` | langchain4j-core/src/main/java/dev/langchain4j/model/chat/ChatModel.java | 统一聊天模型接口；default 方法织入 listener，`chatAsync`（1.20+ @Experimental）返回 CompletableFuture |
| `StreamingChatModel` | langchain4j-core/.../model/chat/StreamingChatModel.java | 流式模型接口（publisher 风格） |
| `AiServices` / `DefaultAiServices` | langchain4j/src/main/java/dev/langchain4j/service/{AiServices,DefaultAiServices}.java | 声明式代理工厂；`Proxy.newProxyInstance`（DefaultAiServices.java:141） |
| `ToolService` | langchain4j/src/main/java/dev/langchain4j/service/tool/ToolService.java | 模型↔工具推理循环（:599 `executeInferenceAndToolsLoop`，:637 `while(true)`，异步版 :730） |
| `@Tool` / `ToolExecutor` / `ToolProvider` | langchain4j-core/.../agent/tool/Tool.java；langchain4j/.../service/tool/ | 工具注解与执行 SPI；ToolProvider 支持按请求动态供工具 |
| `ChatMemory` / `ChatMemoryStore` / `ChatMemoryProvider` | langchain4j-core/.../memory/ChatMemory.java；langchain4j-core/.../store/memory/chat/；langchain4j/.../memory/chat/ChatMemoryProvider.java | 记忆三件套（接口在 core，窗口实现在主模块） |
| `RetrievalAugmentor` / `ContentRetriever` / `ContentAggregator` / `QueryRouter` | langchain4j-core/.../rag/ | RAG 管道全套（含重排与 RRF 融合） |
| `Agent` / `AgenticServices` | langchain4j-agentic/src/main/java/dev/langchain4j/agentic/{Agent.java,AgenticServices.java} | 方法级 agent 注解 + 编排入口工厂（sequence/parallel/loop/conditional/supervisor/planner/a2a builder） |
| `AgenticScope`(+`Persister`/`Store`/`Registry`) | langchain4j-agentic/.../agentic/scope/ | 多 agent 共享状态 + JSON 序列化 + SPI 持久化 |
| `HumanInTheLoop` | langchain4j-agentic/.../agentic/workflow/HumanInTheLoop.java | HITL 节点（responseProvider 注入） |
| `SupervisorAgent` / `SupervisorPlanner` | langchain4j-agentic/.../agentic/{declarative/SupervisorAgent.java,supervisor/SupervisorPlanner.java} | supervisor 注解与规划器 |
| `AgentListener` / `AgentMonitor` | langchain4j-agentic/.../agentic/observability/ | agent 级监听与 HTML 报告 |
| `Skill` / `Skills` | langchain4j-skills/src/main/java/dev/langchain4j/skills/{Skill.java,Skills.java} | Agent Skills 抽象（@Experimental） |
| `McpToolProvider` / `DefaultMcpClient` | langchain4j-mcp/src/main/java/dev/langchain4j/mcp/ | MCP 客户端（stdio/streamable-http/websocket 三传输） |
| `InputGuardrail` / `OutputGuardrail` | langchain4j-core/.../guardrail/{InputGuardrail,OutputGuardrail}.java | 护栏 SPI（core 内）+ `@InputGuardrails/@OutputGuardrails` 注解（service/guardrail/） |
| `ChatModelListener` | langchain4j-core/.../model/chat/listener/ChatModelListener.java | 模型级观测监听 |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 仓库相对路径#符号 |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | 统一 ChatModel/StreamingChatModel + 30 provider + provider 级重试；**无模型级 fallback/router** | langchain4j-core/src/main/java/dev/langchain4j/model/chat/ChatModel.java#ChatModel |
| 2 | 上下文工程 | ✅ | 动态 token 窗口、system message 特殊保留、supervisor 上下文摘要策略 | langchain4j/src/main/java/dev/langchain4j/memory/chat/TokenWindowChatMemory.java#TokenWindowChatMemory |
| 3 | 记忆 | ✅ | ChatMemory 双窗口实现 + ChatMemoryStore SPI；无跨会话长期记忆/用户画像 | langchain4j/src/main/java/dev/langchain4j/memory/chat/{MessageWindow,TokenWindow}ChatMemory.java |
| 4 | RAG | ✅ | core 内完整管道：transform/router/retriever/重排聚合/注入 + 20 向量库 | langchain4j-core/src/main/java/dev/langchain4j/rag/content/aggregator/ReRankingContentAggregator.java#ReRankingContentAggregator |
| 5 | 工具系统 | ✅ | @Tool+ToolExecutor+动态 ToolProvider、MCP 全实现、GraalVM 沙箱、工具补偿；无执行 timeout | langchain4j/src/main/java/dev/langchain4j/service/tool/ToolService.java#executeInferenceAndToolsLoop |
| 6 | Skill 机制 | ✅ | 官方 langchain4j-skills 模块：name/description 常显、activate 工具按需载入（渐进披露，@Experimental） | langchain4j-skills/src/main/java/dev/langchain4j/skills/Skill.java#Skill |
| 7 | 规划推理 | ✅ | supervisor 规划 + GOAP/BDI/debate patterns + 结构化输出 + 迭代上限护栏 | langchain4j-agentic/src/main/java/dev/langchain4j/agentic/supervisor/SupervisorPlanner.java#SupervisorPlanner |
| 8 | 编排 | ✅ | 五种 workflow（sequence/parallel/mapper/loop/conditional）+ 声明式注解；非自由图（无任意 DAG/边） | langchain4j-agentic/src/main/java/dev/langchain4j/agentic/AgenticServices.java#AgenticServices |
| 9 | 多 Agent | ✅ | supervisor+registry+响应评分、A2A 客户端、MCP server 即 agent、六种 pattern | langchain4j-agentic-a2a/src/main/java/dev/langchain4j/agentic/a2a/DefaultA2AService.java#DefaultA2AService |
| 10 | 持久化 | 🟡 | AgenticScope+JSON codec+SPI 齐备，但**仓库内无生产级 store 实现**（仅测试用 in-memory）⚠️ | langchain4j-agentic/src/main/java/dev/langchain4j/agentic/scope/AgenticScopeStore.java#AgenticScopeStore |
| 11 | HITL | ✅ | 双形态：responseProvider 同步注入 + 挂起异常检查点/恢复（支持嵌套挂起） | langchain4j-agentic/src/main/java/dev/langchain4j/agentic/scope/AgenticSystemSuspendedException.java#AgenticSystemSuspendedException |
| 12 | 观测评估 | ✅ | 三层 listener（模型/AiService 事件/agent）+ Micrometer Observation + OTel GenAI 指标 + HTML 报告；无 eval 框架 | langchain4j-agentic/src/main/java/dev/langchain4j/agentic/observability/AgentListener.java#AgentListener |
| 13 | 安全治理 | ✅ | core guardrail SPI + 提示注入/审核护栏 + GraalVM TRUSTED 沙箱；无工具权限/审批 | langchain4j-guardrails/src/main/java/dev/langchain4j/guardrails/PatternBasedPromptInjectionGuardrail.java |
| 14 | 部署运行时 | ❌ | 纯库：无 server/cron/queue；宿主框架集成在独立官方仓库（生态 🟡） | pom.xml（全文无 spring/quarkus 依赖） |
| 15 | 管理平面 | ❌ | 无 console/dashboard/租户/计费（A2A 有 tenantId 透传但非管理面） | langchain4j-agentic-a2a/.../a2a/A2ATenantId.java（仅协议字段） |

## 5. 维度证据明细

**1. 模型接入【核心】**
- `ChatModel#chat(ChatRequest, ChatRequestOptions)` default 方法统一织入 `ChatModelListener` 的 onRequest/onResponse/onError；`chatAsync`/`doChatAsync`（@since 1.20.0，@Experimental）提供真异步（无线程阻塞）。`StreamingChatModel` 独立接口。
- 旧 `ChatLanguageModel` 已从仓库移除（全仓 grep `interface ChatLanguageModel` 零命中）——1.x 改名激进，API 稳定性是企业引入的主要风险。
- provider 级重试：`langchain4j-open-ai/.../OpenAiChatModel.java:87` `maxRetries` 默认 2，走 core 的 `internal/RetryUtils.java`（指数退避 + jitter）。
- **模型级路由/降级 ❌**：全仓无 `FallbackChatModel`（grep 零命中）；`LanguageModelQueryRouter` 只路由 RAG 查询到 retriever，不是模型 fallback。
- 模块清单证据：父 pom 含 open-ai/anthropic/google-genai/vertex-ai×3/bedrock/ollama/mistral-ai/watsonx/jlama/gpu-llama3 等约 30 个模型模块。

**2. 上下文工程【核心】**
- `TokenWindowChatMemory`：`maxTokensProvider`（Function<Object,Integer>）运行时动态窗口；消息不可分割、放不下整条驱逐；SystemMessage 永久保留且唯一；驱逐含 ToolExecutionRequest 的 AiMessage 时自动连带驱逐孤儿 ToolExecutionResultMessage（OpenAI 兼容）。
- `AiServices` 提供 systemMessageProvider / userMessageProvider / systemMessageTransformer / chatRequestTransformer（AiServices.java:273-476）。
- supervisor 上下文策略 `SupervisorContextStrategy`：CHAT_MEMORY / SUMMARIZATION / CHAT_MEMORY_AND_SUMMARIZATION（SupervisorPlanner.java 内 `Context.ContextSummarizer` 实现摘要）。
- RAG 侧查询压缩：core `rag/query/transformer/CompressingQueryTransformer.java`（LLM 压缩查询）与 `ExpandingQueryTransformer`（多查询扩展）。

**3. 记忆【核心】**
- `ChatMemory`（core 接口）+ 窗口实现 `MessageWindowChatMemory`（按条数）/`TokenWindowChatMemory`（按 token）；状态存 `ChatMemoryStore`（默认 `SingleSlotChatMemoryStore`）。
- `ChatMemoryProvider`（memoryId→ChatMemory）支撑多会话；`service/memory/ChatMemoryAccess`、`ChatMemoryService` 供 supervisor 共享记忆访问。
- ChatMemory 接口无 remove/forget/clear API（grep 零命中）；无长期记忆/用户画像抽象——跨会话知识需走 RAG 路线。仓库内 ChatMemoryStore 仅 InMemory 实现，外部持久化靠社区模块。

**4. RAG【核心】**
- core `rag/` 全管道：`RetrievalAugmentor`(DefaultRetrievalAugmentor，支持 async 分阶段) → `QueryTransformer` → `QueryRouter`(Default/LanguageModel) → `ContentRetriever`(EmbeddingStore/WebSearch + Listener) → `ContentAggregator`(`ReRankingContentAggregator` 用 scoring model 重排、`ReciprocalRankFuser` RRF 融合) → `ContentInjector`。
- AiServices 挂接点：`AiServices.java:906-909` contentRetriever / retrievalAugmentor（互斥校验 :177-178）。
- 向量存储约 20 模块（pgvector/milvus×2/qdrant/pinecone/chroma/elasticsearch/weaviat/vespa/opensearch/mongodb-atlas/azure 系/国产 tablestore 等）+ `langchain4j-easy-rag` 一行式入门 + filter-parser(sql)。
- citation ❌：core+主模块 grep `citation` 零命中。

**5. 工具系统【核心】**
- `@Tool`/`@P`（core agent/tool）+ `ToolSpecification`（JSON schema 生成）+ `ToolExecutor#executeWithContext`（含 InvocationContext）+ `ToolProvider`（按请求动态供工具）。
- 循环护栏：`ToolService.java:133` `maxToolCallingRoundTrips=100` 默认；`executeToolsConcurrently`(:386) 并行执行多工具；`immediateReturnToolNames`(:172) 指定工具结果即时返回（终止循环）；`hallucinatedToolNameStrategy`(:774) 处理幻觉工具名。
- 补偿事务：core `agent/tool/CompensateFor.java` + agentic 跨 agent 逆序补偿（`@SupervisorAgent(compensateOnError=true)`，测试 `CrossAgentCompensationTest`）。
- MCP：`langchain4j-mcp` 完整客户端——stdio / streamable-http(SSE) / websocket 三传输、resources/prompts/roots/progress/logging、registry 客户端、resources-as-tools；`langchain4j-mcp-docker` 容器化拉起。
- 沙箱：`code-execution-engines` 三引擎，GraalVM 引擎 `GraalVmPythonExecutionEngine.java:37-38` 显式 `.sandbox(TRUSTED)` + `HostAccess.UNTRUSTED`（JVM 内进程级隔离）；Judge0 / Azure ACADS 远程执行。
- 工具执行 timeout ❌：service/tool 包 grep `timeout` 零命中（MCP 传输层有自己的超时，工具执行本身无统一超时参数）。

**6. Skill 机制【核心】（@Experimental）**
- `langchain4j-skills`（官方模块，非示例）：`Skill#name/description` 始终对 LLM 可见，`content()`（SKILL.md）与 `resources()`/`toolProviders()` 按需加载——javadoc 直接引用 agentskills.io 规范。
- 渐进披露实现：`ActivateSkillToolExecutor#executeWithContext` 返回 `skill.content()` 并置 `ACTIVATED_SKILL_ATTRIBUTE`；配套 `ReadResourceToolExecutor` 读技能资源；`FileSystemSkillLoader`/`ClassPathSkillLoader` 从文件系统/类路径发现技能。
- `experimental/langchain4j-experimental-skills-shell` 提供 shell 命令技能（RunShellCommandTool）。
- 注意：接口标注 `@Experimental`，属新近落地的正式抽象。

**7. 规划推理【核心】**
- supervisor：`SupervisorPlanner` LLM 规划「下一步调哪个子 agent」；`maxAgentsInvocations` 默认 10 防死循环（SupervisorPlanner.java:121 `loopCount++ >= maxAgentsInvocations` 终止）；`ResponseAgent`+`ResponseScore` 对子 agent 答案评分选优（SupervisorResponseStrategy: LAST/SUMMARY）。
- `langchain4j-agentic-patterns`：`goap/GoalOrientedPlanner`(+DependencyGraphSearch 目标分解)、`bdi/BDIPlanner`(+Desire)、`debate/DebatePlanner`(+ConvergenceStrategy)、`voting`、`blackboard`、`p2p`。
- 结构化输出：`service/output/ServiceOutputParser.java#parse`（按返回 Type 解析 JSON/枚举/POJO）。
- 无显式 ReAct prompt 类（工具循环即隐式 ReAct）；无 token budget 抽象（agentic 模块 grep `budget` 零命中）。

**8. 编排【核心】**
- `AgenticServices` 工厂：`sequenceBuilder/parallelBuilder/parallelMapperBuilder/loopBuilder/conditionalBuilder/supervisorBuilder/plannerBuilder/a2aBuilder`（AgenticServices.java:119-280）+ `createAgenticSystem`(:322) 从注解装配整套系统。
- 声明式：`declarative/` 下 `@SequenceAgent/@ParallelAgent/@LoopAgent/@ConditionalAgent/@SupervisorAgent/@PlannerAgent/@RegistryAgent/@McpClientAgent/@A2AClientAgent` + Supplier 参数注入（`SupplierParameterResolver`，静态方法供 ChatModel/ChatMemoryProvider/Tools 等）。
- LoopAgent `maxIterations` 上限 + `ExitCondition` 谓词退出；TypedKey 类型安全状态键。
- 形态是**固定拓扑的工作流组合**（嵌套组合任意深度），不是 LangGraph 式自由图（无 addNode/addEdge/条件边原语）——自由图需求由姊妹项目 langgraph4j 承接。
- 无可视化 studio/DSL（agentic 侧仅 `HtmlReportGenerator` 事后报告）。

**9. 多 Agent【核心】**
- supervisor 全家桶：`supervisor/{SupervisorAgent,SupervisorPlanner,SupervisorAgentService,ResponseAgent,ResponseScore}` + `planner/AgentsRegistry`；supervisor 上下文策略可带摘要。
- A2A：`langchain4j-agentic-a2a` 依赖 `a2a-java-sdk-client(+transport-jsonrpc)`（pom 证据），`DefaultA2AService` + `@A2AClientAgent` 把远端 A2A server 声明为本地 agent；含 tenantId/taskId/contextId 透传与 `A2ATaskInterruptedException`。
- MCP 即 agent：`langchain4j-agentic-mcp` `@McpClientAgent` 把 MCP server 包装成可编排 agent。
- patterns 模块六种协作拓扑（见维度 7）。

**10. 持久化【核心+⚠️】**
- `AgenticScope` 是编排级状态容器（writeState/readState/TypedKey），`AgenticScopeRegistry` 进程内 ConcurrentHashMap；`AgenticScopePersister`（ServiceLoader 加载 `AgenticScopeStore` SPI）+ `AgenticScopeJsonCodec/DefaultAgenticScopeJsonCodec`（Jackson 序列化）+ `AgenticScopeSerializer`。
- **⚠️**：全仓 `implements AgenticScopeStore` 仅测试类 `langchain4j-agentic/src/test/.../JsonInMemoryAgenticScopeStore.java`——生产级持久化（DB/Redis）留白给 SPI 实现，落地需自建。
- 会话记忆持久化同为 SPI（ChatMemoryStore 仅 InMemory 在仓）。无 thread_id/checkpoint 概念（对齐 LangGraph 的对应物是 scope+suspend）。

**11. HITL【核心】**
- 形态一（同步注入）：`HumanInTheLoop` record + `responseProvider(Function<AgenticScope,?>)`，builder 支持 async——非中断型，问答当场发生。
- 形态二（挂起恢复）：`AgenticSystemSuspendedException`（javadoc：系统状态已 checkpoint、线程释放）；恢复 = `AgenticScope#completePendingResponse(responseId, value)`（AgenticScope.java:191/204）后以相同 memoryId 重调 agent 方法；`internal/SuspendedResponse`/`PendingResponse` 支撑。
- 嵌套挂起有集成测试：`NestedSuspensionIT` / `SuspensionResumeIT` / `RecoverabilityIT`【示例级测试证据】。
- 观测联动：`AgentListener#onAgenticSystemSuspended`。

**12. 观测评估【核心】**
- 三层监听：① 模型层 `ChatModelListener`（core，onRequest/onResponse/onError，含线程模型 javadoc 说明）；② AiService 层 core `observability/api+event`（Started/Completed/Error/RequestIssued/ResponseReceived/ToolExecuted/**ToolCompensated**/GuardrailExecuted 全套事件 + `AiServiceListenerRegistrar`）；③ agent 层 `agentic/observability/AgentListener`（before/after invocation、scope 创建销毁、suspended、工具执行前后）+ `AgentMonitor` + `HtmlReportGenerator`（生成 HTML 运行报告）。
- 指标：`langchain4j-observation`（Micrometer Observation API，`ObservationChatModelListener`）+ `langchain4j-micrometer-metrics`（**OTel GenAI 语义约定**指标名/属性，OTelGenAi*.java）。
- eval ❌：无 evaluation/dataset 框架（`langchain4j-test` 是测试基建非评估）。

**13. 安全治理【核心】**
- core `guardrail/` 包：`InputGuardrail`/`OutputGuardrail` SPI + `GuardrailExecutor`（含 `StreamingToSynchronousChatExecutor` 流式护栏适配）；主模块 `service/guardrail/{InputGuardrails,OutputGuardrails}` 注解挂到 AiServices 方法。
- `langchain4j-guardrails` 内置三件：`PatternBasedPromptInjectionGuardrail`（正则提示注入检测）、`MessageModeratorInputGuardrail`（审核模型）、`JsonExtractorOutputGuardrail`。
- 代码沙箱见维度 5（GraalVM sandbox(TRUSTED)）。
- 工具权限/审批 ❌：无 permission/approval 抽象（靠 HITL 挂起手工实现）；审计 = listener 事件。

**14. 部署运行时【❌】**
- 纯库：无内置 server/dev server/cron/queue/temporal（仓库根无 server 相关模块）。
- 宿主集成 🟡：Spring Boot / Quarkus / Helidon / Micronaut starter 在独立官方仓库（langchain4j-spring 等）；本仓库 pom 无任何 spring/quarkus 依赖（已 grep 验证）。
- `internal/langchain4j-docu-chatbot-updater` 是文档站工具，非运行时。

**15. 管理平面【❌】**
- 无 console/dashboard/admin/租户/计费/配置中心。A2A 的 `A2ATenantId` 仅为协议字段透传，不构成管理面。

## 6. 设计决策要点

1. **接口即应用（declarative-first）**：`DefaultAiServices` 动态代理 + agentic 的 `createAgenticSystem`（注解扫描 + Supplier 静态注入），Java 用户几乎不写编排类，只声明 interface——与 Python 系框架「显式构造 chain/graph」路线根本不同。
2. **core 零花活 + 主模块织入**：core 只有接口与 utils（连窗口记忆实现都放主模块），provider 只依赖 core——依赖治理清晰，但代价是抽象改名直接波及全部 provider（1.x → 1.21 间 ChatLanguageModel→ChatModel 等大量重命名）。
3. **循环护栏内建**：`maxToolCallingRoundTrips=100`、`maxIterations`、`maxAgentsInvocations=10` 三层默认上限 + 幻觉工具名策略 + 工具补偿（@CompensateFor 逆序回滚）——把「生产事故面」当一等公民。
4. **挂起式 HITL 而非中断恢复型**：同步 responseProvider 简单场景 + `AgenticSystemSuspendedException` 检查点（无栈恢复，靠重放调用 + scope 状态），比 LangGraph 的 interruptBefore 模型粗但够用；持久层故意留 SPI 空白。
5. **固定拓扑 workflow 而非自由图**：agentic 只提供五种组合子 + supervisor，把图编排让给生态位（langgraph4j），自己保持声明式纯度——两框架互补而非竞争。
6. **官方模块海战术**：MCP/skills/guardrails/observation/patterns 全是同仓库小模块（同一 release train），企业可精确裁剪；但 agentic 系列迭代极快（a2a/patterns 均为新模块），beta 后缀 SNAPSHOT 常态化。
7. **Skill 直接对齐 agentskills.io 规范**：Java 系框架中少见的正式 Agent Skills 实现（渐进披露 + 文件系统发现），但标注 @Experimental。

## 7. 跨语言对齐

不适用（langchain4j 是 Java 原生独立设计，非任何 Python 框架的官方移植；与 Python LangChain 的关系仅是理念借鉴。Java 侧的 LangGraph 对应物为独立社区项目 langgraph4j，见其单独档案）。
