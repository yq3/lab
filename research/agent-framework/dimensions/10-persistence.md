# 维度 10：持久化（Persistence）

> 本维度回答：**会话/执行状态在进程外活多久、怎么存、断了从哪续**。17 个框架大致分成五个语义派系——图执行快照（checkpoint snapshot）、事件溯源（event sourcing）、消息追加（chat log）、全量状态序列化（state serialization）、CLI 转录镜像（transcript mirror）——语义选择直接决定 time-travel、审计、断点恢复粒度是"免费获得"还是"自建补齐"。格局上：LangGraph 系（langgraph/langgraph4j/spring-ai-alibaba）与微软 agent-framework 把持久化做成引擎一级公民（每超步落盘、可恢复可回放）；ADK/dify 走事件溯源；agentscope 双语、openai-agents、claude-sdk 走状态快照/转录；langchain/langchain4j/spring-ai 三个"组件层"框架只给会话存储抽象、不做执行级 checkpoint；Java 阵营在后端广度上普遍反超 Python 官方实现。

## 10.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| langchain | 🟡 | checkpointer/store/cache 参数与类型全透传 langgraph，本仓零存储实现 | libs/langchain_v1/langchain/agents/factory.py#checkpointer（`from langgraph.cache.base import BaseCache` :87） |
| langgraph | ✅ | BaseCheckpointSaver 6 方法 + durability 三级 + pending writes + DeltaChannel 增量快照 + conformance 套件 | libs/checkpoint/langgraph/checkpoint/base/__init__.py#BaseCheckpointSaver(:177)；libs/langgraph/langgraph/pregel/_loop.py#_put_checkpoint(:1081) |
| langgraph4j | ✅ | checkpoint SPI + 内存/文件内置 + 8 个外部 saver（超 Python 官方）；无跨线程 Store | langgraph4j-core/.../checkpoint/BaseCheckpointSaver.java；langgraph4j-{postgres,sqlite,oracle,mysql,redis,dynamodb,cockroachdb,hazelcast}-saver/（8 模块已核实） |
| langchain4j | 🟡 | AgenticScope+SPI+JSON codec 齐备但仓库内无生产级 ScopeStore（仅测试 in-memory）；会话侧 ChatMemoryStore 实有 cassandra/oracle/coherence 等生产后端 | langchain4j-agentic/src/main/java/dev/langchain4j/agentic/scope/AgenticScopeStore.java；langchain4j-oracle/.../chat/oracle/OracleChatMemoryStore.java（MERGE SQL 已核实） |
| deepagents | ✅ | checkpoint 继承 langgraph + 自研 backend 家族（State/Filesystem/Store/Composite/沙箱×6）+ 双 DeltaChannel 控膨胀 | libs/deepagents/deepagents/graph.py#DeepAgentState(:73，`DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)` 已核实)；backends/state.py#StateBackend(:38) |
| agent-framework | ✅ | 每超步自动 checkpoint + graph_signature_hash 拓扑校验 + checkpoint 链 + pending HITL 请求入档 | python/packages/core/agent_framework/_workflows/_checkpoint.py#WorkflowCheckpoint(:31，pending_request_info_events :92 已核实)；_runner.py(:168) |
| adk-python | ✅ | SessionService 4 核心实现 + 2 集成包（InMemory/SQLite/SQLAlchemy 任意 SQL/VertexAi + Firestore/Redis 集成）+ 事件溯源 state + rewind | sessions/database_session_service.py(:285，sqlalchemy 导入已核实)；events/event_actions.py#state_delta(:94)；sessions/_rewind_utils.py#rewind_session(:149) |
| adk-java | 🟡 | 事件追加 + state_delta 溯源 + PersistBarrier 读一致 + 长任务暂停恢复；后端仅 InMemory/VertexAi(+contrib Firestore)，无 JDBC | core/.../sessions/{InMemory,VertexAi}SessionService.java；core/.../flows/llmflows/BaseLlmFlow.java(:548 `PersistBarrier.awaitPersisted` 已核实)；agents/WorkflowAgentResumption.java |
| openai-agents-python | ✅ | Session 多后端 + RunState 版本化可序列化快照（1.0→1.13，暂停/审批/沙箱载荷）；无自动逐轮 checkpoint | src/agents/run_state.py#RunState(:764)；src/agents/memory/session.py#Session(:43)；extensions/memory/（Redis/Mongo/SQLAlchemy/Dapr/加密） |
| claude-agent-sdk-python | ✅ | 本地 JSONL 真相源 + SessionStore 外部镜像协议（at-most-once）+ fork/任意消息点截断恢复 + conformance 套件（14 项） | types.py#SessionStore；_internal/session_mutations.py#fork_session；types.py#resume_session_at(:2174)/#resume_drops_turn(:2186，已核实)；testing/session_store_conformance.py（14 contracts 已核实） |
| crewai | ✅ | Crew checkpoint 断点续跑 + replay(task_id) 按 SQLite 执行日志重放 + Flow @persist | lib/crewai/src/crewai/crew.py#replay(:2034，已核实)；memory/storage/kickoff_task_outputs_storage.py(:18)；flow/persistence/decorators.py#persist(:147) |
| dify | ✅ | models/ 表族：草稿/发布双态 + 运行/节点执行（大字段 offload 二级表）+ WorkflowPause + Redis 命令通道恢复 | api/models/workflow.py#WorkflowPause(:2112，已核实)；#WorkflowNodeExecutionOffload(:1217)；api/core/app/layers/pause_state_persist_layer.py |
| llama_index | 🟡 | 索引存储（docstore/index_store/kvstore/chat_store）core 内置；workflow checkpoint 由外部 llama-index-workflows 包承载，本仓仅 shim | llama-index-core/llama_index/core/workflow/context_serializers.py（1 行 shim）；docs/examples/workflow/checkpointing_workflows.ipynb【示例】；引擎源码不在本地 ⚠️ |
| agentscope | ✅ | AgentState 全量 pydantic 可序列化 + app 层 Storage（SQL/Redis/S3）+ MessageBus；无增量 checkpoint/time-travel | src/agentscope/state/_state.py#AgentState(:209)；src/agentscope/app/storage/_base.py#StorageBase(:29)；app/_service/_session.py#SessionService(:98) |
| agentscope-java | ✅ | AgentStateStore 三元组 + getVersioned/saveIfVersion CAS 乐观并发 + 7 官方存储后端 + 每轮持久化/resumeAgent | agentscope-core/.../state/AgentStateStore.java#saveIfVersion(:131，CAS 注释已核实)；extensions/agentscope-extensions-jdbc/state/JdbcAgentStateStore.java |
| spring-ai-alibaba | ✅ | CheckpointSaver 9 后端（Memory/VersionedMemory/FileSystem/H2/Mysql/Postgres/Oracle/Mongo/Redis + AbstractJdbc）+ Store 家族 5 后端 + withResume | spring-ai-alibaba-graph-core/.../checkpoint/savers/（已核实目录）；store/stores/{Base,Database,FileSystem,Memory,Mongo,Redis}Store.java；RunnableConfig.java#withResume(:235) |
| spring-ai | 🟡 | ChatMemoryRepository 5 官方后端（jdbc/cassandra/mongodb/neo4j/redis）跨重启续对话；无执行级 checkpoint/resume | spring-ai-model/.../chat/memory/ChatMemoryRepository.java；memory-repositories/（5 模块）；ToolCallingAdvisor Javadoc 提及外部 spring-ai-session 项目 ⚠️ |

评级说明：与档案一致者直接沿用；langchain4j 的 🟡 维持，但理由修正——档案称"仓库内 ChatMemoryStore 仅 InMemory"，二次核验证伪：`rg "implements ChatMemoryStore"` 命中 cassandra/oracle/coherence/tablestore/azure-cosmos-nosql 五个 main 下生产实现（OracleChatMemoryStore 为完整 MERGE SQL 实现）。真正留白的是 AgenticScopeStore（多 agent 编排状态）：`implements AgenticScopeStore` 仍仅测试类 JsonInMemoryAgenticScopeStore 命中。claude-sdk 档案"13 项契约"修正为 **14 项**（session_store_conformance.py:4/:59 自述 "14 behavioral contracts"）。

## 10.2 实现方式深析

### 派系 A：图执行快照（checkpoint snapshot）——把"执行到哪了"当一等数据

**langgraph（范式定义者）**：`BaseCheckpointSaver`（checkpoint/base/__init__.py:177）只暴露 6 方法（get/get_tuple/list/put/put_writes/delete_thread）+ get_delta_channel_history(:583)。三件独到设计：
1. **调度即版本差分**：`prepare_next_tasks`（pregel/_algo.py:349）按 channel 版本 vs `versions_seen` 判定激活节点，恢复 = 从最近 checkpoint 读版本表继续差分，天然幂等；
2. **durability 三级**（types.py:89）：`sync`（每超步同步落盘）/`async`（不阻塞执行）/`exit`（仅退出时落盘，_loop.py:1134 `exiting or durability != "exit"` 门控）——一致性-延迟权衡交给调用点；
3. **pending writes**（_loop.py:424-434）：节点执行中途的写入按 task_id 单独持久化，崩溃后重放不丢已完成工作。
体积控制是当前演进焦点：`DeltaChannel`（channels/delta.py:25，beta）在 checkpoint 里只存哨兵、经祖先写入重放归并，`counters_since_delta_snapshot`（checkpoint/base:64，触发条件 = updates ≥ snapshot_frequency **或** supersteps 达系统上限——两条件取 OR，base/__init__.py:79 注释）驱动何时写全量快照；默认 snapshot_frequency=1000（delta.py:74）。存储治理用"窄接口 + 合规套件"：libs/checkpoint-conformance（test_put/test_list/test_delete_thread/test_delta_channel_history）。官方后端仅 InMemory/Sqlite/Postgres（含 async 双形态）；Redis saver 在独立仓 langgraph-checkpoint-redis ⚠️未本地验证。跨线程长期状态是另一个一等抽象：`BaseStore`（store/base/__init__.py:708）namespace+key 文档模型，`search(query=)` 自然语言检索、`put(index=)` 字段级向量索引。

**langgraph4j（Java 社区移植）**：同一 SPI 概念（BaseCheckpointSaver/MemorySaver/getStateHistory/updateState），但**后端广度反超**：postgres/sqlite（各有 V2 代 + Dashboard 查询 API）、oracle、mysql、redis、dynamodb、cockroachdb、hazelcast 共 8 个外部模块（已核实目录）。子图存档经 `SubGraphSaver` 嵌套类。缺口：无跨线程 Store 等价物（Python BaseStore 语义缺失）、无 DeltaChannel 增量快照。

**spring-ai-alibaba（langgraph4j 企业化 fork）**：在 fork 之上加厚——saver 扩到 9 个具体后端（新增 H2/Mongo/VersionedMemory，AbstractJdbcCheckpointSaver 统一 JDBC 方言）；补上 Python 有的跨线程 `Store` 家族（Memory/FileSystem/Redis/Mongo/Database 5 后端）；resume 语义有 javadoc 明确（CompiledGraph.java:646-663：`invoke(Map.of(), config.withResume())` 从最近 checkpoint 的 next node 续跑）；`updateState(config, values, asNode)`(:310-338) 支持改史重放。残留痕迹：H2Saver.java:111 默认 URL 仍是 `jdbc:h2:mem:langgraph4j`。

**agent-framework（微软，Pregel 同源不同实现）**：`Runner` 每个超步结束自动落 checkpoint（_runner.py:168）。两个独有设计：
1. **graph_signature_hash**（_checkpoint.py）：checkpoint 内含图拓扑哈希，恢复时校验，防"改图后恢复旧 checkpoint"的静默错误——17 框架中唯一把拓扑兼容做成显式校验的；
2. **pending_request_info_events**（_checkpoint.py:92，已核实）：HITL 待答请求随 checkpoint 持久化，人机协同暂停与崩溃恢复走同一条通道（`run(checkpoint_id=...)` 与 `run(responses=...)` 可组合，_workflow.py:746 起）。
存储：core InMemory/File + Cosmos（beta）+ Foundry 托管态。dotnet 侧 CheckpointManager.cs/ExternalRequest.cs 对应。

**llama_index（引擎外置的特例）**：core 侧持久化=数据层（docstore/index_store/kvstore/chat_store + storage_context），执行级 checkpoint 是外部 llama-index-workflows 包能力（ctx.to_checkpoint + JsonPickleSerializer），本仓只有 1 行 shim；引擎内部机制（多 worker、快照粒度）无法本地回源 ⚠️——按 uv.lock 锁定 2.23.3。

### 派系 B：事件溯源（event sourcing）——append-only，状态是投影

**adk-python / adk-java（同构）**：一切状态变更落为事件增量——`EventActions.state_delta`（event_actions.py:94）+ `artifact_delta`(:118)，`BaseSessionService.append_event` 是唯一写路径，服务实现只需追加存储。由此免费获得：审计轨迹、回放（`ReplayManager.scan_workflow_events` 重建执行态）、rewind（`sessions/_rewind_utils.py#rewind_session`，按事件差量回退 state/artifact）、压缩可溯源（`EventCompaction` 事件动作）。State 本身带三层作用域前缀 `app:/user:/temp:`（state.py:64-66）——**会话状态与用户级状态的分层内建在 key 命名里**。Java 版独有 `PersistBarrier.awaitPersisted`（BaseLlmFlow.java:548）：下一步 LLM 请求前等待本步事件落库，流式+事件溯源下的读一致性做成显式原语。两版后端面差异显著：Python InMemory/SQLite/Database(SQLAlchemy 任意 DBAPI)/VertexAi + Firestore/Redis 集成；Java 仅 InMemory/VertexAi + contrib Firestore，**刻意不做 JDBC**（企业自托管场景短板，对齐表详见 10.3）。

**dify（平台形态的事件溯源）**：持久化=数据库表族：`Workflow` 草稿/发布双态（version='draft' 单副本 + 发布版本号单调递增，models/workflow.py:186-259）、`WorkflowRun`(:790)/`WorkflowNodeExecutionModel`(:969) 运行明细、`WorkflowNodeExecutionOffload`(:1217) 把大字段卸载二级表防主表膨胀。暂停/恢复：`WorkflowPause`(:2112) + `PauseStatePersistenceLayer`（含 `ResponseStreamFilter` 流位置持久化）+ Redis 命令通道（GraphEngineManager 经 execution_coordinator 发 stop）。触发器（webhook/schedule）与 `ConversationVariable`(:1521) 同样落表。多副本会话路由靠外部化状态：postgres + redis + Celery 分级队列，api 无本地状态可水平扩展。

**crewai（事件日志式，介于 B/C 之间）**：每次 kickoff 落 SQLite 执行日志（WAL，`KickoffTaskOutputsSQLiteStorage` 记录 task_id/expected_output/output/inputs/was_replayed），`replay(task_id)` 从任意中间任务重放（crew.py:2034）；checkpoint 自动断点续跑（`_get_execution_start_index` 找第一个 output 为 None 的任务）；Flow 侧 `@persist` 装饰器 + FlowPersistence ABC（SQLite 实现）。三种恢复语义共享"输出先落盘"的单一事实。无 Postgres/Redis 后端（❌，量级定位使然）。

### 派系 C：消息追加（chat log）——只存对话，不存执行

**spring-ai**：`ChatMemory` 仅 add/add/get/clear 4 方法，`ChatMemoryRepository` 官方 5 后端（jdbc/cassandra/mongodb/neo4j/redis），conversationId 即 thread 标识；**无执行级 checkpoint**——工具循环崩溃即丢轮内进度（循环在 advisor 链内不落盘）。ToolCallLimits Javadoc 引用外部 `spring-ai-session` 项目的 Turn 定义，该模块不在本仓 ⚠️（Spring 侧或有独立会话子项目，证据不足）。
**langchain4j**：会话侧 ChatMemoryStore 实有生产后端（cassandra/oracle/coherence/tablestore/azure-cosmos-nosql + core InMemory——二次核验修正）；但 agentic 编排状态（AgenticScope）的 `AgenticScopeStore` SPI 仓库内只有测试实现，ServiceLoader 加载留给用户/生态。无 thread_id/checkpoint 概念，LangGraph 对应物是 scope+suspend（挂起快照而非图快照）。
**langchain**：完全透传——create_agent 的 checkpointer/store 参数类型都来自 langgraph，连 `BaseCache` 都 import langgraph（factory.py:87）；core 侧仅 `langchain_core/stores.py` 轻量 KV 抽象。

### 派系 D：全量状态序列化（state serialization）——快照即对象

**agentscope（Python）**：`AgentState`（state/_state.py:209）一个 pydantic 对象装下 session_id/summary/context/reply_context/permission_context/tool_context/tasks_context，含旧格式迁移 validator；无增量 checkpoint、无 time-travel——恢复 = 整对象存取。app 层 `StorageBase`（SQL：aiosqlite/asyncpg/aiomysql + alembic / Redis / S3 blob）与 `MessageBus`（in-memory/Redis）解耦：持久化可用 SQL、传输用 Redis（create_app docstring 明示设计意图）。
**agentscope-java**：对应物 `AgentStateStore`，独有贡献是 **CAS 乐观并发**：`getVersioned`/`saveIfVersion`（AgentStateStore.java:104/:131）版本化写入，冲突抛 ConcurrentSessionModificationException + ConflictPolicy 策略，不支持版本的后端退化为无条件写——多节点会话写冲突不用分布式锁。后端矩阵 7 个（jdbc/redis/mysql/postgresql/mongodb/oss/cos）+ RedisDistributedStore/JdbcDistributedStore 分布式协调。恢复粒度到工具调用：`saveStateToSession`(:475) 每轮持久化，`resumeAgent` 从 pending 工具调用续跑；LegacyStateLoader 兼容 v1。
**openai-agents-python**：双轨——Session 是消息追加（4 方法协议），`RunState`（run_state.py:764）是**显式导出**的版本化快照（格式 1.0→1.13 带 changelog 与迁移表，`_PROGRAMMATIC_TOOL_CALLING_MIN_SCHEMA_VERSION = "1.13"`），含 context/usage/pending approvals/sandbox resume payload/prompt cache key；恢复安全语义：防同 Session 并发恢复 + pending session write 确认（run_state.py:767-776）。注意它是**手动导出**（result.to_state()）而非自动逐轮 checkpoint；Temporal durable 仅 examples 级。

### 派系 E：转录镜像（transcript mirror）——真相源在别处，持久层是副本

**claude-agent-sdk-python**：真相源是 CLI 写的本地 JSONL（`~/.claude/projects/<sanitized-cwd>/<session-uuid>.jsonl`，路径 sanitize 复刻 CLI 的 djb2 base36 hash）。SDK 在其上加两层：
1. **SessionStore 镜像协议**：CLI 加 `--session-mirror` 后每条转录行镜像给 SDK，`TranscriptMirrorBatcher` batched（500 条/1MiB/每 turn）/eager 刷写，append 失败重试 3 次降级为 MirrorErrorMessage 系统消息**不中断会话**（at-most-once 投递）；
2. **离线会话操作**：`fork_session`（重写全链 UUID+parentUuid、O_EXCL 0o600 建文件）、rename/tag/delete 纯 Python 直改磁盘格式——绕过 CLI 但与其格式隐式耦合。
恢复粒度全场最细：`resume_session_at`（截断到任意消息，types.py:2174）+ `resume_drops_turn`（校验被丢弃轮次归属，拒绝时抛含 "Resume rejected by --resume-drops-turn:" 的 ProcessError）——**消息级任意点截断恢复**。resume-from-store 用临时 CLAUDE_CONFIG_DIR 物化（含凭据复制重写）。配套 `run_session_store_conformance` 14 项契约套件随包发行（修正档案的 13 项），参考适配器 S3/Redis/PG 在 examples（明示非生产维护）。

### 横切对比

**后端矩阵**（生产可用，按各家声明）：

| 框架 | memory | sqlite/file | postgres/SQL | redis | mongo | 其他 |
|---|---|---|---|---|---|---|
| langgraph | ✅ | ✅ | ✅ | ⚠️独立仓 | ❌ | conformance 套件 |
| langgraph4j | ✅ | ✅(V2) | ✅(V2) | ✅ | ❌ | oracle/mysql/dynamodb/cockroachdb/hazelcast |
| spring-ai-alibaba | ✅(+Versioned) | ✅(H2) | ✅ | ✅ | ✅ | oracle/mysql(JDBC 抽象)+Store 家族 5 |
| agent-framework | ✅ | ✅(File) | ❌ | ❌ | ❌ | Cosmos(beta)/Foundry 托管 |
| adk-python | ✅ | ✅ | ✅(SQLAlchemy 任意 DBAPI) | ✅(集成包) | ❌ | VertexAi/Firestore(集成包)/GCS artifacts |
| adk-java | ✅ | ❌ | ❌ | ❌ | ❌ | VertexAi+contrib Firestore（无 JDBC） |
| openai-agents | ✅ | ✅ | ✅(SQLAlchemy) | ✅ | ✅ | Dapr/OpenAI Conversations/加密装饰器 |
| agentscope | ✅ | ✅(aiosqlite) | ✅(asyncpg/aiomysql) | ✅ | ❌ | S3 blob |
| agentscope-java | ✅ | ✅(JsonFile) | ✅ | ✅ | ✅ | oss/cos/mysql/JDBC 抽象 |
| crewai | ✅ | ✅ | ❌ | ❌ | ❌ | LanceDB(记忆)/Qdrant |
| dify | ❌(服务化) | ❌ | ✅(mysql 可选) | ✅ | ❌ | 对象存储扩展/10+ 向量库 |
| claude-sdk | ✅ | ✅(JSONL 本地) | 示例适配器 | 示例适配器 | ❌ | S3 示例；SessionStore SPI |
| spring-ai | ✅ | ❌ | ✅(jdbc) | ✅ | ✅ | cassandra/neo4j |
| langchain4j | ✅ | ❌ | ❌ | ❌ | ❌ | cassandra/oracle/coherence/tablestore/azure-cosmos |

**恢复粒度谱系**（由粗到细）：超步级（agent-framework、langgraph durability=sync）→ 图节点级（langgraph/langgraph4j/saa 的 checkpoint + next node）→ 任务级（crewai replay(task_id)）→ 工具调用/pending 级（agentscope-java resumeAgent、MS pending_request_info_events、langgraph pending writes）→ **消息级任意点**（claude-sdk resume_session_at+resume_drops_turn，唯一）。

**time-travel/分支**：langgraph `get_state_history`+`update_state` 改史重放（checkpoint id 单调）；langgraph4j/saa 同款 API 对齐；adk-python rewind 按事件差量回退；claude-sdk fork_session 重写 UUID 链离线分支；MS 仅 checkpoint 链（previous_checkpoint_id）+ 拓扑哈希校验，无改史 API；事件溯源派（dify/adk）回放天然、改史靠 rewind/replay 重建。

**体积控制**：langgraph DeltaChannel+双阈值计数（updates/supersteps OR 触发全量）；deepagents 把 messages 与 files 双双挂 DeltaChannel(snapshot_frequency=50)（graph.py:76 已核实，文档明言 O(N²)→O(N)）；dify 大字段 offload 二级表；adk EventsCompaction（压缩本身是事件、可恢复）；claude-sdk 增量摘要侧车（fold_session_summary）；crewai/langchain4j 无专门机制。

**跨线程长期状态**（用户级记忆的存储底座）：langgraph `BaseStore`（namespace+key+search 语义检索+字段级 index）是唯一带语义检索的一等抽象；saa Store 家族是纯 KV（无 search）；adk 用 state 前缀 `app:/user:/temp:` 在 Session 内分层（user state 跨 session 共享但无检索）；deepagents 用 CompositeBackend 把 `/memories/` 路由到 StoreBackend（复用 langgraph BaseStore）；agentscope/crewai 的长期记忆走记忆中间件/LanceDB（维度 3 范畴）；其余框架无。

## 10.3 跨语言对齐

| 对 | Python 侧 | Java 侧 | 差异判断 |
|---|---|---|---|
| langgraph ↔ langgraph4j | saver 官方 3 后端（InMemory 内置 + postgres/sqlite 两个外部模块）；DeltaChannel 增量快照（beta）；BaseStore 跨线程语义检索；durability 三级；pending writes；conformance 套件 | 8 外部 saver（广度反超）；无 DeltaChannel、无 Store、无 durability 分级、无 conformance 套件；V2 saver 线 + Dashboard 查询 API 演进中 | **广度 Java 胜、深度 Python 胜**：增量快照与跨线程记忆是语义代差，saver 数量是工程覆盖差 |
| adk-python(2.9) ↔ adk-java(1.9) | SessionService 4+2 后端（含 SQLAlchemy 任意 SQL+migration）；rewind 工具（_rewind_utils）；ReplayManager；ResumabilityConfig | InMemory/VertexAi+Firestore，**无 JDBC/SQLite**；WorkflowAgentResumption 从事件索引恢复；PersistBarrier 读一致原语（Java 独有） | **Python 全面领先（含版本差因素）**：开源自托管 DB 后端缺失是 Java 最痛缺口；Java 独有的 PersistBarrier 是流式一致性的加分项 |
| agentscope ↔ agentscope-java | AgentState 全量序列化 + app Storage（SQL/Redis/S3）+ MessageBus（Redis）；无版本控制写 | AgentStateStore + **CAS 乐观并发（saveIfVersion）** + 7 后端 + 分布式协调 Store + LegacyStateLoader + 沙箱远端快照 | **Java 工程化超出**：并发控制与后端矩阵更重；Python 侧 S3 blob 与 bus/storage 解耦设计更清晰 |

## 10.4 取舍与趋势

1. **语义选择先于后端选择**：快照派免费获得 time-travel 与节点级恢复（langgraph 系、MS），事件溯源派免费获得审计与回放（adk、dify、crewai），消息追加派两者都要自建（spring-ai、langchain4j 的会话层）——"支持几种数据库"是浅层对比，"状态变更如何被记录"才是分水岭。
2. **增量快照成为新战场**：checkpoint 体积随对话长度平方膨胀是长程 agent 的头号存储成本。langgraph DeltaChannel（beta，双阈值计数）、deepagents 双通道 snapshot_frequency=50、dify offload 二级表、adk 事件压缩、claude 摘要侧车——五种独立演化路径指向同一问题。
3. **Java 阵营后端广度系统性反超，Python 官方走窄接口+合规套件**：langgraph4j 8 saver / saa 9+5 / agentscope-java 7 vs langgraph 官方 3 个；但 langgraph 用 checkpoint-conformance 把"过套件即可插拔"做成协议质量工程（claude-sdk 的 14 项 SessionStore 契约同款思路）——广度交给社区、契约留在官方。
4. **恢复粒度持续下沉**：从图节点（checkpoint+next node）到工具调用 pending（agentscope-java、MS、langgraph pending writes），再到 claude-sdk 的任意消息点截断（resume_session_at+resume_drops_turn 带轮次归属校验）——粒度越细，对"执行可重放性"的假设越强。
5. **多副本一致性开始被显式处理**：agentscope-java 的 CAS 乐观并发（ConflictPolicy 显式化）、adk-java 的 PersistBarrier、MS 的每超步落盘 + checkpoint 拓扑哈希、dify 的全外部化状态（postgres/redis/Celery）——框架从"单进程库"走向"多副本服务"时，会话粘性/写冲突是必答题；langgraph 平台侧靠闭源 langgraph-api 的队列+Postgres 承担。
6. **跨线程长期状态仍是普遍洼地**：17 家中只有 langgraph BaseStore 做成带语义检索的一等存储抽象，saa Store 是无检索 KV、adk 是 state 前缀分层、deepagents 借道 CompositeBackend 复用 BaseStore——多数框架把"用户级记忆"推给维度 3 的记忆中间件或生态（mem0 等）。
