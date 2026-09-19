# spring-ai 框架档案

> 基线：~/develop/opensource/spring-ai @ b5eb0272f 2026-09-11（main 分支）；版本 2.0.2-SNAPSHOT（父 `pom.xml` `<version>`，2.0.x 线）

## 1. 定位

Spring 官方的 AI 应用**库**（library，非平台）：把「模型调用」纳入 Spring 编程模型——`ChatClient` fluent API + Spring Boot starter 自动装配 + Micrometer 可观测。目标用户是 Spring/JVM 企业开发者，核心卖点是模型可移植性（同一 API 换 provider）与 Spring 生态（Security/Boot/Observability）无缝集成。定位刻意收敛在「单次会话 + 工具循环」级别：无 agent 编排引擎、无 graph/状态机、无 HITL 中断——官方立场（文档 `api/effective-agents.adoc`）是"用普通 Java 代码组合 workflow"，把编排复杂度留给应用或第三方（如 spring-ai-alibaba）。**注意：传闻中的 2.0 `spring-ai-agentic` 模块在本仓不存在**（全仓 rg `agentic` 仅命中 docs 的 4 个 .adoc）。

## 2. 仓库结构与核心包

Maven 多模块，父 pom 共 168 个 `<module>`（构建证据 `pom.xml`）。骨架分四层：

- **核心库（7 个）**：`spring-ai-commons`（Document/ETL 接口、模板渲染 SPI、tokenizer、观测约定）、`spring-ai-model`（ChatModel/Prompt/Message、ChatMemory、tool 体系、converter、observation）、`spring-ai-client-chat`（ChatClient + advisor 体系 + evaluation）、`spring-ai-rag`（模块化 RAG 管道）、`spring-ai-vector-store`（VectorStore SPI + 过滤表达式 DSL）、`spring-ai-retry`、`spring-ai-template-st`（StringTemplate 渲染器）
- **横切 advisor 模块（2 个）**：`advisors/spring-ai-vector-store-advisor`（QuestionAnswerAdvisor 等）、`advisors/spring-ai-tool-search-advisor`（工具发现）+ 独立 `spring-ai-tool-search-tool`
- **生态矩阵（按存储/provider 分仓）**：`models/` 15 个 provider 模块（openai/anthropic/google-genai(+embedding/image)/ollama/bedrock(+converse)/deepseek/mistral-ai/vertex-ai-embedding/transformers(本地 ONNX)/postgresml/stability-ai(图像)/elevenlabs(音频)）、`vector-stores/` 22 个（pgvector/redis/milvus/…/redis-semantic-cache）、`memory-repositories/` 5 个（jdbc/cassandra/mongodb/neo4j/redis）、`document-readers/` 4 个（jsoup/markdown/pdf/tika）
- **MCP 全家桶**：`mcp/common`（客户端桥接）、`mcp/mcp-annotations`（服务端注解）、`mcp/transport/{webflux,webmvc}`、5 个 client/server autoconfigure + 5 个 starter；另有 48 个 starter 总数（`grep -c '<module>starters/' pom.xml`）

vs 1.0.x（`git ls-tree origin/1.0.x`）：commons/model/client-chat/rag 拆分在 1.0 已完成（**非 2.0 重构**，纠正既有摘要）；2.0 的真实增量 = 工具循环上移 ChatClient 层、`memory/`→`memory-repositories/`、advisor 拆独立模块、新增 tool-search 系与 redis-semantic-cache、删除 `PromptChatMemoryAdvisor` 与 `spring-ai-spring-cloud-bindings`。

## 3. 核心抽象清单

| 符号 | 路径（相对仓库根） | 一句话说明 |
|---|---|---|
| `ChatClient` | spring-ai-client-chat/.../chat/client/ChatClient.java | fluent 门面：`.prompt().user().advisors().tools().call()/.stream()` |
| `ChatModel`/`ChatOptions` | spring-ai-model/.../chat/model/、chat/prompt/ | provider 无关的模型 SPI（call + stream） |
| `Advisor`/`CallAdvisor`/`StreamAdvisor` | spring-ai-client-chat/.../advisor/api/ | 2.0 横切抽象：按 call/stream 分型的方法拦截器链 |
| `ToolCallingAdvisor` | spring-ai-client-chat/.../advisor/ToolCallingAdvisor.java | **agent 循环本体**（do/while，@since 2.0.0） |
| `ToolCallingManager` | spring-ai-model/.../model/tool/ToolCallingManager.java | 工具解析+执行（`DefaultToolCallingManager` 含 40/150 限额） |
| `ToolCallback`/`@Tool` | spring-ai-model/.../tool/ToolCallback.java、tool/annotation/Tool.java | 工具 SPI（definition+metadata+call）与注解声明 |
| `ChatMemory`/`ChatMemoryRepository` | spring-ai-model/.../chat/memory/ | 会话记忆 4 方法 + 可插拔存储 |
| `MessageWindowChatMemory` | spring-ai-model/.../chat/memory/MessageWindowChatMemory.java | 按条数滑窗（保 SystemMessage，切齐到 UserMessage） |
| `BeanOutputConverter` 等 | spring-ai-model/.../converter/ | 结构化输出：JSON schema 生成 + 反序列化 |
| `VectorStore`/`SearchRequest` | spring-ai-vector-store/.../vectorstore/ | 向量库 SPI（22 个官方实现） |
| `QuestionAnswerAdvisor` | advisors/spring-ai-vector-store-advisor/.../vectorstore/QuestionAnswerAdvisor.java | RAG advisor（检索→拼 prompt） |
| `RetrievalAugmentationAdvisor` | spring-ai-rag/.../advisor/RetrievalAugmentationAdvisor.java | 全功能 RAG 管道 advisor（变换/扩展/检索/合并/增强） |
| `ToolSearchTool` | spring-ai-tool-search-tool/.../toolsearch/ToolSearchTool.java | 把"找工具"本身做成向量检索工具 |
| `Sync/AsyncMcpToolCallbackProvider` | mcp/common/.../SyncMcpToolCallbackProvider.java | MCP client 工具桥接 |
| `@McpTool`/`@McpElicitation` 等 | mcp/mcp-annotations/.../annotation/ | MCP server 端注解（tool/prompt/resource/sampling/elicitation） |
| `ChatModelObservationDocumentation` | spring-ai-model/.../chat/observation/ | gen_ai.* OTel semconv 观测约定 |
| `Evaluator`/`RelevancyEvaluator` | spring-ai-commons/.../evaluation/、spring-ai-client-chat/.../chat/evaluation/ | LLM-as-judge 评测 SPI |
| `SafeGuardAdvisor` | spring-ai-client-chat/.../advisor/SafeGuardAdvisor.java | 敏感词拦截 advisor |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | 15 官方 provider 模块 + Flux 流式 + 重试 + usage 元数据；无 router/fallback | `models/`（15 模块）；spring-ai-retry#RetryUtils；spring-ai-model/.../chat/metadata/Usage |
| 2 | 上下文工程 | ✅ | ST 模板 + defaultSystem + 条数/token 双层裁剪；无自动摘要 | spring-ai-model/.../chat/prompt/PromptTemplate；spring-ai-template-st#StTemplateRenderer；advisor/LastMaxTokenSizeContentPurger |
| 3 | 记忆 | ✅ | ChatMemory 极简接口 + 5 持久化后端 + 3 类 memory advisor；无长期画像/遗忘 | spring-ai-model/.../chat/memory/ChatMemory；`memory-repositories/`（5） |
| 4 | RAG | ✅ | 22 向量库 + 模块化 RAG 管道 + 2 个 RAG advisor + ETL；通用 rerank 缺位 | spring-ai-rag/（管道）；advisors/spring-ai-vector-store-advisor#QuestionAnswerAdvisor |
| 5 | 工具系统 | ✅ | @Tool→ToolCallback SPI + 循环限额 + MCP 双端 + ToolSearchTool；无 sandbox/timeout | spring-ai-model/.../tool/；`mcp/`；spring-ai-tool-search-tool#ToolSearchTool |
| 6 | Skill 机制 | ❌ | 无 skill/渐进披露抽象；最接近的 ToolSearchTool 只是工具发现 | spring-ai-tool-search-tool/.../ToolSearchTool.java（工具级，非 skill 级） |
| 7 | 规划推理 | 🔶 | 无 plan/ReAct/反思抽象，agentic 模式仅文档+外部示例；结构化输出与预算止损是核心 | spring-ai-docs/.../api/effective-agents.adoc【文档】 |
| 8 | 编排 | 🔶 | advisor 链是唯一管道抽象；chain/routing 等模式靠"手写 Java"（文档+外部 examples 仓） | spring-ai-docs/.../api/effective-agents.adoc【文档】 |
| 9 | 多 Agent | ❌ | 无 supervisor/handoff/swarm/a2a 任何抽象（核心包 rg 零命中） | 全仓 rg（spring-ai-model/client-chat/rag/advisors 无命中） |
| 10 | 持久化 | 🟡 | 会话记忆可持久化（5 后端）；无执行 checkpoint/resume；外部 spring-ai-session ⚠️ | spring-ai-model/.../chat/memory/ChatMemoryRepository；memory-repositories/（5） |
| 11 | HITL | ❌ | 无 interrupt/approve/resume；最接近 MCP 协议层 elicitation | mcp/mcp-annotations/.../annotation/McpElicitation.java（协议级，非流程级） |
| 12 | 观测评估 | ✅ | Micrometer 全链路观测（gen_ai.* OTel semconv）+ 轻量 LLM 评测 | spring-ai-model/.../chat/observation/ChatModelObservationDocumentation；.../chat/evaluation/RelevancyEvaluator |
| 13 | 安全治理 | 🟡 | SafeGuardAdvisor 敏感词 + 记忆 advisor 防注入转义；无 PII/审计/工具 RBAC/sandbox | advisor/SafeGuardAdvisor；advisors/.../vectorstore/VectorStoreChatMemoryAdvisor（Javadoc 安全注记） |
| 14 | 部署运行时 | 🟡 | 库形态：48 个 Spring Boot starter 即部署单元，无自带 server/queue/cron；可作 MCP server 暴露 | `starters/`（48 模块）；starters/spring-ai-starter-mcp-server-webmvc |
| 15 | 管理平面 | ❌ | 无 console/dashboard/租户/计费/配置中心 | 全仓无对应实现 |

## 5. 维度证据明细

### 1. 模型接入
- `models/` 15 个 provider 模块（pom `<modules>` 构建证据）：openai、anthropic、google-genai(+embedding/image)、ollama、bedrock(+bedrock-converse)、deepseek、mistral-ai、vertex-ai-embedding、transformers（本地 ONNX 嵌入）、postgresml、stability-ai（图像）、elevenlabs（TTS/转录）——覆盖 chat/embedding/image/audio。【核心】
- 流式：`ChatModel.stream(Prompt)` 返回 Reactor `Flux<ChatResponse>`；`ToolCallingAdvisor` 同时实现 `adviseCall`/`adviseStream`（流式聚合整轮后执行工具再回放，spring-ai-client-chat/.../advisor/ToolCallingAdvisor.java）。【核心】
- 重试：`spring-ai-retry` 模块 `RetryUtils`（spring-core RetryTemplate 指数退避），区分 `TransientAiException`/`NonTransientAiException`。【核心】
- usage/cost：`spring-ai-model/.../chat/metadata/`（Usage、RateLimit）；`UsageAccumulator` 跨工具轮累计 token（spring-ai-client-chat/.../advisor/UsageAccumulator.java）。【核心】
- 缓存：模型级 cache 无；chat 语义缓存为独立模块 `vector-stores/spring-ai-redis-semantic-cache`（`SemanticCacheAdvisor`，Redis 相似度命中直接返回）。【核心（独立模块）】
- **router/fallback 无**：核心包 rg `fallback|RouterChatModel` 零命中（需用户用 Spring `@Primary`/自建组合）。❌子项
- 证据等级：除标注外均【核心】。

### 2. 上下文工程
- 模板：`PromptTemplate`（spring-ai-model/.../chat/prompt/）默认渲染器为 StringTemplate（spring-ai-template-st#StTemplateRenderer，`{}` 单字符定界符，可配置）；`AssistantPromptTemplate`/`SystemPromptTemplate` 分消息类型。【核心】
- 系统提示：`ChatClient.Builder#defaultSystem(String|Resource|Consumer)`（ChatClient.java:517）+ 同型 `defaultUser`/`defaultAdvisors`/`defaultTools`（:501/:509/:564）。【核心】
- token 裁剪：`LastMaxTokenSizeContentPurger`（advisor 包，TokenCountEstimator 估算、保留尾部）；tokenizer 在 spring-ai-commons/.../tokenizer/（JTokkitTokenCountEstimator）。【核心】
- 条数裁剪：`MessageWindowChatMemory` maxMessages 滑窗——淘汰时保护 SystemMessage 并"向前对齐到 UserMessage"保持轮次完整（MessageWindowChatMemory.java:107-113）。【核心】
- **自动摘要压缩无**（summarization memory 无实现）。❌子项
- prompt 防注入：2.0 模板渲染带 `ValidationMode`（spring-ai-commons/.../template/TemplateRenderer.java）。【核心】

### 3. 记忆
- 接口极简：`ChatMemory` 仅 `add/add/get/clear` 4 方法 + `CONVERSATION_ID` context key（ChatMemory.java）；唯一策略实现 `MessageWindowChatMemory`（按条数，无 token/摘要策略）。【核心】
- 持久化 SPI：`ChatMemoryRepository` + `InMemoryChatMemoryRepository`；官方后端 5 个：`memory-repositories/spring-ai-model-chat-memory-repository-{jdbc,cassandra,mongodb,neo4j,redis}`，各配 starter。【核心】
- memory advisor 体系：`MessageChatMemoryAdvisor`（消息入 history，client-chat 内）+ `VectorStoreChatMemoryAdvisor`（长期记忆向量检索后注入 system text，advisors/ 模块）+ 2.0 新 api 型 `BaseChatMemoryAdvisor`/`MemoryAdvisor`（默认 order = HIGHEST+200，置于工具循环外侧）。【核心】
- `VectorStoreChatMemoryAdvisor` Javadoc 有整段安全设计说明：检索内容 XML 转义 + `<memory-entry>` 类型包裹，防 role-boundary 注入；并建议 agent 场景优先用 MessageChatMemoryAdvisor。【核心】
- **长期画像/user profile/遗忘（forget）语义无**（仅 `clear(conversationId)` 全清）。❌子项
- 变更：1.x 的 `PromptChatMemoryAdvisor` 在 2.0 树中已删除（对比 `origin/1.0.x` advisor 包）。【核心】

### 4. RAG
- 检索 advisor 两档：`QuestionAnswerAdvisor`（advisors/spring-ai-vector-store-advisor：similaritySearch → 默认模板拼 `{query}+context`，支持 filterExpression 透传、检索文档回填 advise context 键 `qa_retrieved_documents`）；`RetrievalAugmentationAdvisor`（spring-ai-rag：QueryTransformer×N → QueryExpander → DocumentRetriever → DocumentJoiner → QueryAugmenter → DocumentPostProcessor 全管道编排）。【核心】
- spring-ai-rag 内置件：`RewriteQueryTransformer`/`TranslationQueryTransformer`/`CompressionQueryTransformer`、`MultiQueryExpander`（LLM 生成多查询）、`VectorStoreDocumentRetriever`、`ConcatenationDocumentJoiner`、`ContextualQueryAugmenter`（含 allowEmptyContext 选项）。【核心】
- 向量库：`VectorStore` SPI + `SearchRequest` + antlr4 过滤表达式 DSL（spring-ai-vector-store/.../filter/）；22 个官方 store 模块（pgvector/redis/milvus/weaviate/pinecone/qdrant/chroma/elasticsearch/mongodb-atlas/neo4j/cassandra/oracle/opensearch/azure/couchbase/gemfire/mariadb/s3/typesense/coherence/bedrock-kb/weaviate…）。【核心】
- ETL：`DocumentReader/DocumentTransformer/DocumentWriter` 在 spring-ai-commons/.../document/；`TextSplitter`/`TokenTextSplitter`/`ContentFormatTransformer` + 4 个 reader 模块（jsoup/markdown/pdf/tika）+ `FileDocumentWriter`。【核心】
- **rerank 无通用抽象**：rg `rerank` 仅命中 `BedrockKnowledgeBaseVectorStore`（AWS 侧原生能力）。🔶子项
- citation：`QuestionAnswerAdvisor` 把文档放 context 供下游消费，但无引用定位/标注抽象。🔶子项

### 5. 工具系统
- 声明：`@Tool`/`@ToolParam` 注解（tool/annotation/）→ `MethodToolCallback(Provider)`（反射绑定，支持 ToolContext 注入）；函数式 `FunctionToolCallback`；底层 SPI `ToolCallback`（getToolDefinition/getToolMetadata/call(String,ToolContext)）。【核心】
- schema：`ToolDefinition`（name/description/inputSchema JSON Schema 自动生成）；`tool/augment/ToolInputSchemaAugmenter`（2.0：schema 运行时增强）。【核心】
- **agent 循环（2.0 核心变化）**：`ToolCallingAdvisor`（@since 2.0.0）实现 do/while——每轮 `doBeforeCall → ChatModel → doAfterCall → ToolExecutionEligibilityChecker.hasToolCalls() → ToolCallingManager.executeToolCalls`，直到无工具调用/returnDirect/超限（ToolCallingAdvisor.java:149-216）；1.x 的 ChatModel 内部执行（internalToolExecutionEnabled）被此 advisor 取代，`DefaultChatClientBuilder.java:105` 默认注入。循环在链内 → 其他 advisor 可拦截每一轮工具迭代。【核心】
- 防失控预算：`DefaultToolCallingManager` 默认**每工具 40 次**（:100 `DEFAULT_MAX_CALLS_PER_TOOL`）/**全局 150 次**（:107 `DEFAULT_MAX_TOTAL_TOOL_CALLS`）；按"当前 turn"（最后一条 UserMessage 起）计数；超限策略 `ToolCallLimitBehavior`：`THROW`（异常带已执行工具，中断）或 `RETURN_ERROR_RESPONSE`（跳过执行、把拒绝信息回喂模型）。【核心】
- 结果处理：`ToolCallResultConverter`（默认转 JSON 字符串）+ `ToolExecutionExceptionProcessor`（异常转文本回喂模型而非抛出）。【核心】
- 按名解析：`tool/resolution/`（ToolCallbackResolver/StaticToolCallbackResolver/DelegatingToolCallbackResolver）——运行时按名字找已注册工具。【核心】
- 规模化：`ToolSearchTool`（spring-ai-tool-search-tool）把工具清单做成向量索引，`toolSearchTool` 本身是个工具让模型自然语言检索；`ToolSearchToolCallingAdvisor`（advisors/ 模块）管理索引注入/会话级缓存（工具集指纹变更才重建索引）+ LRU/TTL 淘汰——海量工具防 prompt 膨胀。【核心】
- MCP：client 侧 `Sync/AsyncMcpToolCallback(Provider)` 桥接（名称前缀生成器防冲突、`McpToolsChangedEvent` 热更新、`McpToolFilter` 过滤）；server 侧 `mcp-annotations`：`@McpTool/@McpArg/@McpPrompt/@McpResource/@McpElicitation/@McpSampling/@McpProgress/@McpMeta`——Spring 应用可反向暴露为 MCP server（webmvc/webflux 双传输 + stateless 模式 customizer）。【核心】
- **缺位**：无沙箱、无 per-call timeout、无结果截断（超长工具结果直接回喂）；`ToolMetadata` 仅 returnDirect，无权限/危险等级字段。❌子项

### 6. Skill 机制
- 无 Claude 式 skill/progressive disclosure 抽象（rg `skill` 无核心命中）。最接近的形态是 ToolSearchTool 的"工具按需披露"，作用域是工具 schema 而非指令文件包。❌
- `effective-agents.adoc` 也未涉及 skill 概念。【文档】

### 7. 规划推理
- 无 plan/ReAct-loop（显式 Thought 步骤）/reflection/budget 权重的规划抽象——推理依赖模型原生 tool-calling 循环。【核心（缺失即证据）】
- 结构化输出是强项：`converter/`（BeanOutputConverter 生成 JSON Schema 并反序列化、List/MapOutputConverter、ThinkingTagCleaner 等 2.0 新清洁器）；2.0 新增 `StructuredOutputValidationAdvisor`：按 schema 校验响应、失败则把错误追加进 user message 重调模型（maxRepeatAttempts 次）——自纠错回路。【核心】
- agentic 模式仅文档级：`spring-ai-docs/.../api/effective-agents.adoc`（259 行）给出 chain/parallelization/routing/orchestrator-workers/evaluator-optimizer/autonomous-agent 五模式，实现代码在外部 `spring-ai-examples` 仓（本仓无）。【文档】+【示例（外部仓）】
- 预算止损：见维度 5 的 40/150 限额——这是框架对"agent 失控"的唯一内置治理。【核心】

### 8. 编排
- 唯一管道抽象是 advisor 链（`AdvisorChain`/`CallAdvisorChain`/`StreamAdvisorChain`，按 `Ordered` 排序、请求正穿/响应倒穿）；链尾固定挂 `ChatModelCallAdvisor`/`ChatModelStreamAdvisor`（DefaultChatClient.java:1196-1197）。【核心】
- 无 graph/workflow/state machine/subgraph/可视化——官方哲学"workflow 用代码组合"（effective-agents.adoc 明说企业场景优先预定义代码路径）。【文档】
- 并行：文档 parallelization 模式用 `CompletableFuture` 手写；框架无 parallel 节点抽象。【文档】
- 分支/循环：`ToolCallingAdvisor` 的 do/while 是唯一内置循环；条件分支无。【核心】

### 9. 多 Agent
- 核心 + advisor 模块 rg `supervisor|orchestrator|handoff|swarm|a2a|multi-agent` 零命中（仅测试文件误报）。完全留给应用层或 spring-ai-alibaba 等衍生框架。❌【核心（缺失即证据）】
- agent-as-tool 可用 `@Tool` 手工模拟，但无官方抽象。🔶手写可行

### 10. 持久化
- 会话记忆持久化：`ChatMemoryRepository` 5 后端（JDBC/Neo4j/Cassandra/MongoDB/Redis + InMemory 默认），conversationId 即 thread 标识，跨重启恢复对话。【核心】
- **执行级 checkpoint/resume 无**：无工具循环中断点保存、无 durable execution、无 thread 状态快照——长程 agent 崩溃即丢轮内进度（记忆 advisor 只在外侧存整轮）。❌子项
- ⚠️待确认：`ToolCallLimits` Javadoc 引用外部 `spring-ai-session` 项目的 Turn 定义（"matching the Turn definition used by the spring-ai-session project"），该模块不在本仓——Spring 侧或有独立会话管理子项目，本仓证据不足。

### 11. HITL
- 核心 rg `human.in.the.loop|interrupt|approval|escalation` 零命中。无审批流/中断恢复/升级机制。❌
- 最接近物：MCP 协议层 `@McpElicitation`（server 向 client 用户征询输入）与 `SafeGuardAdvisor`（前置拦截）——均非 agent 流程级 HITL。【核心】

### 12. 观测评估
- 观测全链路 Micrometer：ChatClient/ChatModel/Advisor/Tool/VectorStore/Embedding 各有 Observation 体系（spring-ai-model 各 `*/observation/` 包 + advisor/observation/ + vectorstore/observation/）。【核心】
- 语义约定对齐 OTel GenAI semconv：`AiObservationAttributes` 枚举 = `gen_ai.operation.name`/`gen_ai.system`/`gen_ai.request.model` 等（spring-ai-commons/.../observation/conventions/）；content/meter/completion 三类 ObservationHandler 可插；文档 observability/index.adoc 给 OpenTelemetry 桥接（micrometer-otel）。【核心】+【文档】
- 评测：`Evaluator` SPI（commons/evaluation/）+ `RelevancyEvaluator`（相关性 LLM 裁决 YES/NO）+ `FactCheckingEvaluator`（事实核查，需 WireMock 文档支撑）——轻量 LLM-as-judge，无 dataset/批量 harness/CI 集成。🔶子项（能力在但很薄）

### 13. 安全治理
- `SafeGuardAdvisor`：核心内置敏感词拦截（大小写不敏感、自定义 failureResponse），Javadoc 明言只是起点（不处理同形字/零宽字符）。【核心】
- 注入防御（约定级）：VectorStoreChatMemoryAdvisor 的 XML 转义 + 类型包裹（见维度 3）；`TemplateRenderer.ValidationMode`。【核心】
- 无 PII 检测、无审计日志策略、无工具 RBAC（ToolMetadata 无权限字段）、无沙箱——依赖 Spring Security 生态自行组合。❌子项
- 2.0 未新增 content safety advisor（如 Azure Content Safety 集成不在树内）。❌子项

### 14. 部署运行时
- 库形态：无自带 server/dev server/queue/cron——运行时即宿主 Spring Boot 应用；48 个 starter 是部署单元（模型/向量库/MCP/记忆各配齐）。【核心】
- MCP server starter 可把 Spring 应用整体暴露为 MCP 工具服务（webmvc/webflux + stateless 变体）——这是唯一的"服务化"出口。【核心】
- 辅助：`spring-ai-spring-boot-docker-compose`/`spring-boot-testcontainers` 模块管理本地依赖容器；GraalVM AOT 支持全仓成体系（aot/ 包、ToolRuntimeHints 等）。【核心】

### 15. 管理平面
- 无 console/dashboard/admin/租户/计费/配置中心（配置走 Spring Boot properties + BOM 版本治理）。观测数据交 Micrometer 后端（Prometheus 等）呈现。❌【核心（缺失即证据）】

## 6. 设计决策要点

1. **循环上移（2.0 灵魂改动）**：工具循环从 ChatModel 内部（1.x `internalToolExecutionEnabled` 黑盒）搬到 advisor 链内的 `ToolCallingAdvisor`——记忆/RAG/日志 advisor 因此能拦截**每一轮工具迭代**而非只拦首尾。这是"agent 循环可组合化"的教科书做法。
2. **Advisor = LLM 版 HandlerInterceptor**：横切关注点（记忆/检索/守卫/工具循环/结构化校验/观测）全部 advisor 化，call/stream 双链分型 + `Ordered` 排序，与 Spring MVC 拦截器心智完全同构——对 Java 企业开发者零学习成本。
3. **止损预算内置**：每工具 40/全局 150 + THROW/RETURN_ERROR_RESPONSE 双策略，按 turn 计数防记忆回放膨胀——17 个框架里少见的"默认防失控"设计。
4. **刻意不做编排**：无 graph/multi-agent/HITL，agentic 模式只给文档 + 外部示例仓。官方边界感清晰：做"AI 的 Spring Data"，编排复杂度留给 spring-ai-alibaba 等衍生或用户代码。
5. **ToolSearchTool 反转**：不解决"工具太多"（砍工具），而是把工具检索本身做成一个工具（向量索引 + LRU/TTL 淘汰 + 指纹缓存）——渐进披露思想落在工具层。
6. **接口极简 + 实现矩阵分仓**：ChatMemory 4 方法、ToolCallback 3 方法，随后端/provider 拆 100+ 小模块（memory-repositories/models/vector-stores/starters 各自成仓），核心零重量依赖、扩展按需引入——完全复刻 Spring Data/Spring Integration 的组织范式。
7. **OTel semconv 原生对齐**：观测属性直接采用 `gen_ai.*` 标准命名，Micrometer 一层桥接全兼容——企业 APM 集成开箱即用，而非常见的私有 span 格式。

## 7. 跨语言对齐

不适用：spring-ai 是原创 Java 框架（非移植）。其中国衍生框架 spring-ai-alibaba（基于 Spring AI 1.1.x 之上补齐 graph/多 agent/HITL/管理平面）另立档案，恰可视为"Spring AI 官方留白的反面验证"。
