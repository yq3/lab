# DataAgent（Spring AI Alibaba DataAgent）解剖档案

> 基线：~/develop/opensource/DataAgent @ 3fb7852 (2026-08-19)；canonical spring-ai-alibaba/DataAgent；版本 1.0.0-SNAPSHOT（父 pom `<revision>`），**1.0.0-RC 未 GA**。⚠️ 与本项目同栈（Java 17 + Spring Boot 3.4.8），架构参考价值直接，但 RC 阶段工程完成度有缺口（见维度 5/6/7 的 ❌ 项）。

## 1. 产品定位与形态

- **定位**：「企业级智能数据分析师」——超越 Text-to-SQL 工具，做 NL2SQL + Python 深度分析 + 多维图表报告生成（README.md）。本质是 ChatBI 产品形态加了一层「规划-执行」骨架。
- **目标用户**：企业数据分析场景，私有化部署（MySQL/Hive/达梦等 7 种库）+ 主流大模型（统一 OpenAI 接口协议接 Qwen/DeepSeek 等）。
- **交互形态**：① 自带 Web UI（`data-agent-frontend-nuxt/`，Nuxt 3 前端，独立进程）；② REST + SSE API（`/api/stream/search`）；③ **MCP Server**（`spring-ai-starter-mcp-server-webflux`，向 Claude Desktop 等暴露 `nl2sql`、`list_agents` 两个工具）。【核心】`controller/GraphController.java`、`service/mcp/McpServerService.java`
- **仓库结构**：单 Maven 模块 `data-agent-management`（303 个 Java 文件，单体 Spring Boot 应用）+ Nuxt 前端 + docker-file。**不是 Spring Boot starter 库，是一个完整的独立服务**——这正是它对本项目约束①的参考价值所在。

## 2. Agent 执行架构（★重点）

### 2.1 总体：单 StateGraph + 16 节点 + 计划驱动路由

全部编排是一个 `StateGraph` Bean（`config/DataAgentConfiguration.java#nl2sqlGraph`），节点是 Spring `@Component` 实现 SAA 的 `NodeAction` 接口，通过 `NodeBeanUtil.getNodeBeanAsync(XxxNode.class)` 从容器取 bean 包装成异步节点。边由 `Dispatcher`（`EdgeAction` 实现）做条件路由。固定拓扑：

```
START → 意图识别 →(需要分析?)→ 证据召回(RAG) → 查询增强 → Schema召回 → 表关系分析(可自旋重试)
      → 可行性评估 →(可行?)→ Planner → PlanExecutor(校验+步进) ⇄(修复回环, max 2)
PlanExecutor → 人工复核?(可选 interrupt) → SQL生成 → 语义一致性校验(失败回SQL生成) → SQL执行(失败回SQL生成)
            → 回 PlanExecutor 取下一步 → Python生成 → Python沙箱执行(失败回生成, max 5) → Python分析
            → 全部步骤完成 → 报告生成 → END
```

【核心】`workflow/node/`（16 节点）+ `workflow/dispatcher/`（11 个条件边）+ `config/DataAgentConfiguration.java:216-287`（建图代码）。图在启动时用 `stateGraph.getGraph(PLANTUML)` 打印自查。

### 2.2 「固定图 + 动态计划」混合编排（最值得借鉴的模式）

不是动态建图，也不是自由 ReAct：**图拓扑静态固定，LLM 规划产物（Plan JSON）作为状态变量驱动 dispatcher 路由**。

- `PlannerNode` 用 `BeanOutputConverter<Plan>` 的 format 约束 LLM 输出 `Plan{executionPlan:[{step, toolToUse, toolParameters:{instruction,...}}]}`（`dto/planner/Plan.java`、`ExecutionStep.java`）。
- `PlanExecutorNode`（`workflow/node/PlanExecutorNode.java`）：① 结构校验——工具名必须在白名单 `Set.of(SQL_GENERATE_NODE, PYTHON_GENERATE_NODE, REPORT_GENERATOR_NODE)`，每类步骤必填参数逐项检查（SQL/Python 步要有 `instruction`，报告步要有 `summary_and_recommendations`）；② 校验通过后读 `PLAN_CURRENT_STEP` 按步进调度，把下一步节点名写进 `PLAN_NEXT_NODE` 状态键。
- `PlanExecutorDispatcher` 读 `PLAN_NEXT_NODE` 路由——**LLM 只能从白名单里选「下一步做什么」，路由决策本身是确定性代码**。校验失败则带 `PLAN_VALIDATION_ERROR` 回 PlannerNode 重规划（`PLAN_REPAIR_COUNT` 计数，>2 终止），修复模式的 user prompt 显式包含「上一版计划 + 校验反馈」并声明这些是任务数据不得覆盖系统规则（`PlannerNode.java:110-138`，注入防护意识）。
- 步进游标：每个执行节点成功后写 `PLAN_CURRENT_STEP = current + 1`，全部步骤跑完后 PlanExecutor 路由到报告节点。

对比纯 ReAct：计划可被校验、可被人审批、可整体重生成；对比动态子图：不牺牲图的可静态审计性。**与财务场景「先出方案-审批-逐步执行」的合规形态天然对齐。**

### 2.3 节点内流式：LLM Flux 包装成图流

所有 LLM 节点不阻塞等完整响应：`FluxUtil.createStreamingGeneratorWithMessages(...)` 把 `Flux<ChatResponse>` 包成 `Flux<GraphResponse<StreamingOutput>>` 返回给图运行时，LLM token 边生成边经 `StreamingOutput` 事件流向 SSE，流结束时才把完整输出写回状态（`PlannerNode.java:59-67`）。节点输出 Map 的 value 可以是 generator（异步节点）。

`SqlExecuteNode` 进一步用「业务逻辑先行」模式：`Mono.fromCallable(执行SQL).subscribeOn(boundedElastic)` 先真实执行并落状态，再 concat 出给用户看的进度流（`SqlExecuteNode.java:130-168`）——执行结果的真实性与展示解耦。

### 2.4 质量闸门链（NL2SQL 路线的自我纠错回路）

- 生成前：意图识别（闲聊直接短路出 FINAL_ANSWER）→ 查询改写（多轮指代消解）→ Schema 召回（向量检索表/列文档）→ 表关系分析（外键+逻辑关系，失败自旋重试）→ 可行性评估（不可行直接礼貌终止，不硬答）。
- 生成后：`SemanticConsistencyNode` 双闸门——① **确定性结构校验**：Druid AST 解析强制「恰好一条语句 + 无未解析 `?` 占位符」（`util/SqlUtil.java#findGeneratedSqlValidationError`）；② **LLM 语义校验**：SQL vs 用户意图 vs schema 的一致性判断。任一失败把原因写 `SQL_REGENERATE_REASON` 回 SqlGenerateNode 重新生成（`max-sql-retry-count` 默认 10，`application.yml`）。
- 执行失败同样回 SQL 生成（`SqlExecuteNode` onErrorResume 写 `SqlRetryDto.sqlExecute(errorMessage)`）。

重试原因通过状态键在节点间显式传递、成为下一轮 prompt 的输入——「错误反馈即上下文」的实现干净，可复用。

## 3. 技术底座

- **语言/框架**：Java 17、Spring Boot 3.4.8（WebFlux：SSE + 响应式 Security）、MyBatis、Lombok。
- **agent 框架**：spring-ai-alibaba **1.1.2.2**——`spring-ai-alibaba-graph-core`（图运行时）+ `spring-ai-alibaba-sandbox`（Python 沙箱）+ `spring-ai-alibaba-dashscope`；模型接入统一走 Spring AI `spring-ai-openai`（OpenAI 协议兼容多厂商，根 pom 注释明示「统一openai接入以支持多厂商」）。【核心】`data-agent-management/pom.xml`
- **框架层能力直接引用上游档案**（不重复展开）：graph-core 的 StateGraph/CompiledGraph/OverAllState/KeyStrategy/CheckpointSaver 概念体系见 `agent-framework/profiles/spring-ai-alibaba.md`（第 3、4 节核心抽象清单）；Spring AI ChatMemory/BeanOutputConverter/@Tool/MCP 见 `agent-framework/profiles/spring-ai.md`。**本档案只关注 DataAgent 怎么组装这些件。**
- **组装方式要点**：① 节点/边全是 Spring bean，建图代码集中在配置类（非 DSL、非注解扫描）；② 状态键与 KeyStrategy 用常量类 `Constant` 统一管理，全部 `KeyStrategy.REPLACE`（无 Append 累积型状态）；③ 向量库可插拔——默认 `MetadataAwareSimpleVectorStore`（内存兜底），引 Milvus/ES starter 即换（`DataAgentConfiguration.java:345-358`，配 `application-{milvus,elasticsearch,h2}.yml`）；④ **模型热切换**：`AiModelRegistry` 持当前激活 Chat/Embedding 模型，`EmbeddingModel` bean 用 Spring AOP `TargetSource` 动态代理——每次调用从注册表取最新实例（`DataAgentConfiguration.java:403-443`），管理端切模型零重启。
- 观测：Langfuse（可选开关，OTel SDK）+ `NodeEntryLoggingAspect`（AOP 节点进出日志）+ `NodeTracingLifecycleListener`（挂进图 `CompileConfig.withLifecycleListener`，做节点级 span 与 token 汇总）。

## 4. 状态与持久化

- **双层 ID 模型**：`conversationId`（多轮对话，贯穿）与 `threadId`（单次图运行，每轮新建 UUID）分离；HITL 恢复时复用同一 threadId（`GraphServiceImpl#graphStreamProcess:95-123`，含对旧客户端的兼容处理）。**会话历史与执行状态解耦**是明确设计。
- **checkpoint**：`CompileConfig` 挂 saver——生产默认 `MysqlSaver`（`CREATE_IF_NOT_EXISTS` 自动建表），可切 `MemorySaver`（`DataAgentConfiguration.java:302-328`）。⚠️ **但 checkpoint 的用途只有 HITL 暂停**：`GraphServiceImpl` 在流完成/出错/客户端断开时主动 `checkpointSaver.release(config)` 删除检查点，仅 `checkpoint.getNextNodeId()==HUMAN_FEEDBACK_NODE`（等待人工反馈）时保留（`handleStreamComplete:319-323`、`isAwaitingHumanFeedback:442-455`）。**无故障恢复/断点续跑语义**——进程重启即丢运行中状态（多轮历史不受影响）。
- **多轮记忆**：`MultiTurnContextManager`——每轮把「用户问题 + Planner 流式输出的计划文本」作为一轮 User/Assistant 消息写入 Spring AI `ChatMemory`（JDBC repository，`MessageWindowChatMemory` 滑窗 `maxturnhistory*2` 条），下轮拼成字符串注入 `MULTI_TURN_CONTEXT` 状态键（`service/graph/Context/MultiTurnContextManager.java`）。注意存的是**计划**而非最终答案（轻量，但意味着后续轮看不到上轮数据结果，靠 `SQL_RESULT_LIST_MEMORY` 单轮内传递）。
- **展示层历史**：`chat_session`/`chat_message` 表（MyBatis），`ChatController` 提供 session CRUD；`SessionEventPublisher` 用 per-agent Sinks 推 session 标题等更新事件（SSE + 心跳）。
- **审计/回放**：❌ 无审计表、无「谁在何时批准了什么」记录、无执行回放。Langfuse trace 是唯一的过程留痕（观测用途，非合规用途）。
- 并发：`streamContextMap`（ConcurrentHashMap per threadId）+ 精心处理的双检清理（`context.isCleaned()` + synchronized 设 Disposable），注释明确标注竞态处理顺序（先 dispose 订阅再 release checkpoint，`stopStreamProcessing:130-152`）。

## 5. HITL 与风控（★重点）

- **唯一的 HITL 闸门：计划级人工复核**。运行时请求参数 `humanFeedback=true`（nl2sqlOnly 模式强制关闭）→ PlanExecutor 校验通过后路由 `HUMAN_FEEDBACK_NODE` → 该节点在 `CompileConfig.interruptBefore` 中注册，图在进入前暂停。【核心】`DataAgentConfiguration.java:320-328`、`PlanExecutorNode.java:79-83`
- **暂停-恢复协议**（对外 API 即 HTTP，本项目可直接参考的时序）：
  1. 流暂停时 `GraphServiceImpl` 检查 checkpoint 的 nextNodeId，向前端发 `HUMAN_FEEDBACK_REQUIRED` 协议事件并保留 checkpoint（`handleStreamComplete:335-346`）；
  2. 用户决策后**同一端点**再请求，带 `threadId + humanFeedbackContent + rejectedPlan` 布尔；
  3. 服务端 `compiledGraph.updateState(config, {HUMAN_FEEDBACK_DATA, MULTI_TURN_CONTEXT})` 写入反馈，再 `compiledGraph.stream(null, resumeConfig)` 从断点续跑（`handleHumanFeedback:199-243`，resumeConfig 带 `HUMAN_FEEDBACK_METADATA_KEY` metadata）；
  4. `HumanFeedbackNode` 读反馈：approve → `HUMAN_REVIEW_ENABLED=false` 回 PlanExecutor 继续执行；reject → 回 PlannerNode，反馈文本作为 `PLAN_VALIDATION_ERROR`（复用修复回路），重置步进游标、清空旧计划，`PLAN_REPAIR_COUNT` 计数 max 3 后终止（`HumanFeedbackNode.java:40-83`）。
  5. 无反馈数据时节点返回 `WAIT_FOR_FEEDBACK`，dispatcher 自环回本节点（resume 首次进入路径）。
- **风控缺口（财务场景视角）**：❌ 审批只盖「计划」，**SQL 真正执行前无人审**（语义校验是 LLM）；❌ 审批动作不落审计（无审批人身份、时间戳、决策记录——`HUMAN_FEEDBACK_DATA` 只活在图状态里，checkpoint 用完即删）；❌ 无危险操作分级（无 DML/DLL 拦截器，见维度 6）；❌ 无人工接管/纠错回滚（reject 只能重规划，不能手改计划——框架档案里 SAA 的 `HumanInTheLoopHook` 支持 EDITED 态，DataAgent 未用）；❌ 审批人身份无认证支撑（见下）。
- **API 鉴权**：WebFlux Security 只保护 `GET /api/stream/search` 一个端点，其余 `permitAll`；X-API-Key（或 Bearer）+ query 参数 `agentId` 定位 agent，`ApiKeyCredentialService` 用 DelegatingPasswordEncoder（bcrypt）存储 + 后 4 位明文提示（`security/` 四件套 + `WebFluxSecurityConfiguration.java`）。ARCHITECTURE.md 自己也承认「默认后端未对 X-API-Key 做鉴权拦截，生产需自行补充」（文档与代码有出入：代码已实现但只盖一个端点）。

## 6. 工具与业务系统集成（★重点）

### 6.1 数据源连接层：Accessor/Ddl/Pool 三件套 + 工厂

`connector/` 包的分层（借鉴 DB-GPT 风格）：

- **Accessor**（元数据+查询门面）：接口方法 `showDatabases/showSchemas/showTables/showColumns/showForeignKeys/sampleColumn/scanTable/executeSqlAndReturnObject`（`connector/accessor/Accessor.java`）；`AbstractAccessor` 用 `accessDb(dbConfig, method, param)` 字符串分发 + 每次调用 try-with-resources 借还连接。
- **Ddl**：per-dialect 元数据读取实现（MySQL/PostgreSQL/Oracle/SQLServer/H2/Hive/达梦 7 种，`connector/ddl/`+`connector/impls/`），供 Schema 召回节点用。
- **DBConnectionPool**：per-DB 连接池实现 + `ConnectionRetryPolicy`（`connector/pool/`）。
- 工厂路由：`AccessorFactory`/`DdlFactory`/`DBConnectionPoolFactory` 按 `DbConfigBO` 的 dialect 取实现；服务层另有 `DatasourceTypeHandlerRegistry`（handler 负责把「主机/端口/库」解析成 JDBC URL，`service/datasource/handler/`）。
- **agent↔数据源绑定**：`agent_datasource` 关联表，`DatabaseUtil.getAgentDbConfig(agentId)` 取「该 agent 当前激活的唯一数据源」凭证（`util/DatabaseUtil.java`）——**运行时按 agent 动态解析连接**，非全局数据源。

### 6.2 SQL 执行护栏

`connector/SqlExecutor.java`：`setMaxRows(1000)` + `setQueryTimeout(30s)` + `executeQuery(sql)`（隐式只读——非查询语句会抛异常，但**无显式 DML/DLL AST 拦截**）；per-dialect 切 schema（PG `set search_path`、MySQL `use \`db\``、Oracle `ALTER SESSION`、达梦 `SET SCHEMA`，达梦标识符做了引号转义防注入）。结构校验（单语句/无占位符）在生成侧由 Druid AST 完成（见 2.4）。

### 6.3 凭据与权限

- ⚠️ **数据源密码明文**：`datasource` 表 `password VARCHAR(255) COMMENT '密码（加密存储）'`——schema 注释宣称加密，但 `DatasourceServiceImpl.createDatasource/updateDatasource` 直接存原文，全仓 grep `encrypt|decrypt|AES|cipher` 零命中。【核心（缺失即证据）】**避坑点。**
- API Key 见维度 5；模型 key 存 `model_config` 表（`api_key` 字段）。

### 6.4 Python 代码执行（任务级沙箱）

「LLM 生成代码而非 LLM 直接算」路线在 Java 服务里的完整落地：`PythonGenerateNode`（生成带 **PEP 723** 头的脚本）→ `PythonExecuteNode` → `SaaSandboxPythonCodeExecutorService`（`service/code/sandbox/` 四个子包：dependency=PEP 723 解析+包规格策略白名单；execution=固定 bootstrap 脚本+JSON envelope 结果回传；runtime=SAA `SandboxService` 生命周期）。资源与隔离（`application.yml: code-executor.*`）：Docker 任务级容器**每次尝试新建、成败均销毁**；500MB 内存 / 1 CPU / 60s 代码超时 / 5 次重试；并发闸（max-concurrency 4 + 有界队列 10，`ThreadPoolExecutor`+`ArrayBlockingQueue`）；私有 PyPI index + 3min 依赖安装超时。**不回退宿主机执行**（ARCHITECTURE.md 明示边界）。失败时错误回喂 PythonGenerateNode 重生成。

### 6.5 对外工具化（MCP Server）

`McpServerService` 用 Spring AI `@Tool` 暴露 `nl2sql`（跑全图 IS_ONLY_NL2SQL=true 模式，同步 invoke + 用完即删 checkpoint）与 `list_agents` 两工具，经 `spring-ai-starter-mcp-server-webflux` 变成 MCP 端点——**同一服务同时是 Web API 和 MCP Tool Server**，是「agent 服务被别的 agent 系统集成」的最低成本路径。

## 7. 部署与产品化

- **形态**：单体 Spring Boot JAR（端口 8065）+ MySQL（管理库：agent/知识/语义模型/模型配置/session/checkpoint 表）+ Nuxt 前端（独立 dev 进程/nginx）+ Docker Engine（Python 沙箱依赖）。`docker-file/docker-compose.yml`（后端+MySQL，`Dockerfile-backend` 多阶段 mvn 构建）+ `docker-compose-datasource.yml`（演示用被分析库）。
- **与业务系统的边界**：被分析库通过管理端登记凭证（datasource 表），agent 服务直连业务库——**分析场景的合理边界**；但无「业务服务 API 作为工具」的集成形态（除 MCP 出站方向）。
- 多租户：❌ `chat_session.userId` 字段存在但无任何租户隔离/查询过滤逻辑；配额/成本：❌ 无。
- 可观测性：Langfuse（每请求根 span + 节点 span + token 汇总，断连时显式收尾防泄漏 span）+ OpenTelemetry + AOP 日志。无 metrics/告警。
- 知识管理产品化：语义模型（Excel 批量导入 `resources/excel` 模板）、业务知识/agent 知识两类 RAG 语料（事件驱动异步向量化 + 资源清理定时任务 `AgentKnowledgeResourceCleanerTask`）、prompt 配置库（`user_prompt_config`，报告生成节点按优先级拼「优化要求」，其余类型预留）。

## 8. 对本项目的适用性

对照四条硬约束（Java、独立部署+API、图编排、审批/审计/合规）：

### 可借鉴模式（按价值排序）

1. **「固定图 + 计划驱动路由」**（`PlanExecutorNode` + `PlanExecutorDispatcher` + Plan DTO）：静态可审计拓扑 × LLM 动态规划的结合点。财务 agent 的「分析方案→审批→逐步执行」可直接套：方案=Plan JSON（BeanOutputConverter 强约束 schema），执行器白名单校验后按步调度。→ `workflow/node/PlanExecutorNode.java`、`dto/planner/`
2. **HTTP 层 HITL 暂停-恢复协议**：`interruptBefore` + checkpoint.nextNodeId 判定 + `updateState(反馈)` + `stream(null, resumeConfig)` + 前端 `HUMAN_FEEDBACK_REQUIRED` 事件——纯 REST/SSE 即可实现，无 WebSocket 依赖。→ `GraphServiceImpl#handleHumanFeedback/isAwaitingHumanFeedback`、`GraphController`
3. **错误反馈状态键回路**：`SQL_REGENERATE_REASON`/`PLAN_VALIDATION_ERROR` 把失败原因显式写状态、驱动定向重生成（带 max retry 计数），配合「确定性结构校验（AST）在前、LLM 语义校验在后」的双闸门顺序。→ `SemanticConsistencyNode`、`SqlUtil`
4. **conversationId/threadId 双层 ID**：多轮会话与单次执行分离，HITL resume 靠 threadId 定位、历史靠 conversationId。→ `GraphServiceImpl#graphStreamProcess`
5. **连接层三件套工厂**（Accessor/Ddl/Pool per-dialect + `getAgentDbConfig(agentId)` 运行时解析）：多数据源 SaaS 形态的干净抽象，加只读强制即可用于财务库。→ `connector/`
6. **模型热切换注册表 + AOP TargetSource 动态代理**：管理端换模型零重启、EmbeddingModel bean 永远指向激活实例。→ `DataAgentConfiguration#embeddingModel`
7. **Python 沙箱工程化清单**：PEP 723 受控依赖 + 私有镜像 + 资源限额 + 有界并发队列 + 任务级容器即用即毁 + JSON envelope 结果协议。→ `service/code/sandbox/`
8. **双通道服务化**：同一服务 REST/SSE + MCP Server 双暴露。→ `McpServerService`

### 不可迁移点

- 全部状态键 `KeyStrategy.REPLACE` + 无 reducer：适合线性数据流，财务场景需要多方案权衡/并行分支时状态模型要扩。
- checkpoint 用完即弃：无故障恢复语义，长事务（如挂起多日的审批流）必须自己改造（保留 checkpoint 或把等待态外置到 DB/工作流引擎）。
- 无多租户/配额/审计——这三块正是本项目硬约束③，DataAgent 只提供了反面参照。

### 避坑

1. **数据源密码明文入库**（schema 注释还写着「加密存储」）——财务场景凭证必须 KMS/加密。
2. **审批不落审计**：HUMAN_FEEDBACK_DATA 只活在图状态，checkpoint 删除后无痕——合规场景必须补审批持久化表（审批人/时间/原计划/决策/理由）。
3. **鉴权只盖一个端点** + agentId 从 query 参数取（易枚举）——API 化时需要全端点认证 + 服务间身份。
4. SSE 用 GET + query 串（查询内容、反馈内容进 URL，会被网关/访问日志记录）——建议 POST+SSE。
5. nl2sql 模式 `compiledGraph.invoke` 同步阻塞 + UUID threadId——工具化调用无超时预算控制。
