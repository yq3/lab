# 02 执行状态与 Checkpoint 存储（langgraph / deepagents / agent-framework / crewAI / agentscope-java / dify / adk-python）

> agent-persistence 轮第 2 路。定位：本文是 `research/agent-framework/dimensions/10-persistence.md` 的下钻层——不复述该篇的派系划分与评级，只回答「落库时长什么样」：DDL 全字段、序列化格式、blob 结构、写入 SQL、恢复读路径。7 仓基线：langgraph@e539ac122f / deepagents@9e7d62ff6 / agent-framework@3c67070776 / crewAI@894898f84c / agentscope-java@c5db8f72db / dify@79effdd498 / adk-python@7b246e0166。

## 0. 综述：快照派 vs 事件派在存储层的本质差异

| 维度 | 快照派（langgraph / MS agent-framework） | 事件派（adk / dify） | 混合（crewAI / agentscope-java） |
|---|---|---|---|
| 一行的含义 | 某一超步末的**完整执行态**（版本表+通道值） | 一次**不可变的状态变更**（delta） | 一个任务的最终输出 / 一个会话的最后快照 |
| 消息在哪 | checkpoint 的 channel_values 内（langgraph 按 channel 拆 blob） | 事件流的 content 字段（adk `event_data` JSON 单列） | AgentState.context 列表 / 任务 output JSON 列 |
| 恢复 = | 读最近快照 + 重放差分条件 | 从头重放全部事件投影 state | 读最后一行覆盖 |
| 改史 = | 插入新 checkpoint（fork 分支） | 只能追加补偿事件（rewind 是一条新事件） | UPDATE 覆盖（无历史） |
| 表数量 | 3-4 张（checkpoints/writes/blobs + migrations） | 2-5 张（sessions/events 或 runs/executions） | 1-2 张 |

存储层真正的设计分水岭有三处：**(a) 大对象放行内还是旁表**（langgraph PG 拆 blobs vs SQLite 全内联；dify offload 二级表）、**(b) serde 是自描述类型标签还是裸 JSON**（langgraph msgpack ext code vs 全员 JSON）、**(c) 并发控制下推到 SQL 还是不做**（agentscope-java CAS vs langgraph DO NOTHING upsert）。

## 1. langgraph：三表 + 版本化 blob 的范式定义者

### 1.1 DDL 全字段【核心】

**SqliteSaver**（`libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py:139-163`，`PRAGMA journal_mode=WAL` :141）：

```sql
CREATE TABLE IF NOT EXISTS checkpoints (
  thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL DEFAULT '',
  checkpoint_id TEXT NOT NULL, parent_checkpoint_id TEXT,
  type TEXT, checkpoint BLOB, metadata BLOB,
  PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id));
CREATE TABLE IF NOT EXISTS writes (
  thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL DEFAULT '',
  checkpoint_id TEXT NOT NULL, task_id TEXT NOT NULL, idx INTEGER NOT NULL,
  channel TEXT NOT NULL, type TEXT, value BLOB,
  PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx));
```
**无 blob 表**：channel_values 内联在 checkpoint blob 里（`_delta.py:6-8` 明言 "No separate blob table — channel_values lives inline"）。put = 整个 checkpoint dict `serde.dumps_typed` 后 `INSERT OR REPLACE`（`__init__.py:420-436`）；metadata 是 `json.dumps(...).encode()` 的 JSON 字节（:421-423），读回 `json.loads`（:368）。

**PostgresSaver**（`libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py:43-91`，9 条迁移 + `checkpoint_migrations(v)` 版本表）：

| 表 | 字段 | 备注 |
|---|---|---|
| checkpoints | thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, **checkpoint JSONB**, **metadata JSONB DEFAULT '{}'** | PG 主键同 SQLite；大值不在行内 |
| checkpoint_blobs | thread_id, checkpoint_ns, **channel, version**, type, blob BYTEA | PK(thread_id, checkpoint_ns, channel, version)——**按通道版本寻址**，跨 checkpoint 去重 |
| checkpoint_writes | thread_id, checkpoint_ns, checkpoint_id, task_id, **task_path**(迁移9新增), idx, channel, type, blob BYTEA | PK(...task_id, idx) |

### 1.2 blob serde 与拆分规则【核心】

- put 时按值类型分流（`postgres/__init__.py:309-319`）：`None/str/int/float/bool` 留在 JSONB `channel_values` 行内；**`_DeltaSnapshot` 哨兵弹出存 blobs、行内以 `True` 占位**（:313-315）；其余复杂对象全部弹入 `checkpoint_blobs`，key = (channel, **new_version**)，`UPSERT ... ON CONFLICT DO NOTHING`（`base.py:131-135`）——同版本重写幂等跳过。
- 读回靠 join 重装配（`base.py:93-118`）：`jsonb_each_text(checkpoint->'channel_versions')` inner join `checkpoint_blobs on channel=key and version=value`，旁路子查询聚合 `pending_writes`（按 task_id, idx 排序）；`__pregel_tasks` 通道（sends）单独用 `SELECT_PENDING_SENDS_SQL` 按 (task_path, task_id, idx) 聚合（:120-129）。
- serde 是 **tuple[str, bytes] 类型标签协议**（`serde/base.py:24`）：`JsonPlusSerializer.dumps_typed` → `("msgpack", ormsgpack打包)`，失败且 `pickle_fallback=True` 则 `("pickle", pickle.dumps)`；另有 null/bytes/bytearray/json 标签（`jsonplus.py:258-290`）。ormsgpack **ext code 表**：pydantic v2=5、numpy array=6、**`_DeltaSnapshot`=7**（:295-302）——Delta 哨兵在持久层的表示就是 msgpack ext 7；旧 "json" 格式 checkpoint 靠 langchain reviver 兼容读（:60-70）。
- checkpoint dict 本体（`checkpoint/base/__init__.py:93-124`）：`v=1`、`id`（单调可排序）、`ts`、`channel_values`、`channel_versions`（channel→版本串）、`versions_seen`（**node→{channel→version} 调度版本表**）、`updated_channels`、`pending_sends`。metadata 含 source(input/loop/update/fork)/step/parents/run_id/`counters_since_delta_snapshot`（channel→(updates, supersteps) 二元组，JSON 里存 2 元 list，:64-87）。

### 1.3 BaseStore（跨线程长期状态）

- PostgresStore DDL（`store/postgres/base.py:63-134`）：`store(prefix text, key text, value jsonb, created_at, updated_at, expires_at, ttl_minutes, PK(prefix,key))` + btree `text_pattern_ops` 前缀索引 + `expires_at` 部分索引；向量独立表 `store_vectors(prefix, key, field_name, embedding vector_type(dims), ..., FK→store ON DELETE CASCADE)`，ANN 索引类型/ops 由 `ann_index_config` 参数化（hnsw/ivfflat）。search 三算子映射：`<->`(L2)/`<#>`(内积)/`<=>`(cosine→`1-distance`)（:1442-1450）；put 时按 `index_config.fields` 对 value 的**指定 JSON 字段逐个 embedding** 成多行（:343-421）。InMemoryStore 为 dict + 可选向量检索（`store/memory/__init__.py:136-152`），无 DDL。
- 写入时机与并发：SQLite 单连接 + 进程锁 `self.lock` 串行（`sqlite/__init__.py:181`）；PG 用 pipeline 事务批量 executemany（`postgres/__init__.py:321-344`）；无 CAS——靠 `ON CONFLICT DO NOTHING`（blobs）+ `DO UPDATE`（checkpoints/writes，`base.py:137-153`）幂等。

## 2. deepagents：backend 家族——文件系统的六种介质

| Backend | 介质 | 目录/格式 | 与 checkpoint 关系 |
|---|---|---|---|
| StateBackend | LangGraph state 的 `files` 键 | dict[path→FileData{content,encoding,created_at,modified_at}] | **走 checkpointer**（随超步落盘） |
| FilesystemBackend | 宿主真实 FS | root_dir 虚拟根 + 路径穿越阻断（virtual_mode 默认 True）；时间戳取自 stat（`filesystem.py:139-180,341`） | 不走（进程外副作用） |
| StoreBackend | langgraph BaseStore | namespace 元组（factory 按用户等）；value=`{content, encoding, created_at, modified_at}` JSON；legacy `list[str]` 内容 `\n`.join 兼容读（`store.py:170-228`）；ls/glob = `store.search` 分页全扫（:230-304） | 不走（跨线程） |
| CompositeBackend | 路由器 | `routes={"/memories/": backend}` 最长前缀匹配、剥离前缀转发；`artifacts_root` 供消息卸载（`composite.py:255-291`） | 按路由分流 |
| ContextHubBackend | LangSmith Hub agent repo（`context_hub.py:1`） | 云端 repo 文件 | 不走 |
| Sandbox 家族×6 | modal/runloop/daytona/vercel/quickjs（`libs/partners/`）+ LocalShell（本地子进程） | BaseSandbox 只要求实现 `execute()`+`upload_files()`，ls/grep/glob/read 全部用 **shell 命令模板**派生（`sandbox.py:1-13`）；edit 小载荷内联、大载荷传临时文件跑 replace 脚本（:8-9） | 不走 |

StateBackend 的读写经 Pregel 内部 `CONFIG_KEY_SEND/READ` 通道（`state.py:45-47, 94-119`）：同超步 read-your-writes（`fresh=True` 应用 pending writes）、节点边界提交；删除以 `None` 值作删除标记由 dict-merge reducer 解释（:250-274）。checkpoint 侧：`DeepAgentState.messages` 挂 `DeltaChannel(snapshot_frequency=50)`（`graph.py:73-76`），即消息走增量快照、文件走全量 reducer——**同一份状态里两种体积策略并存**。二进制内容 base64 存 `encoding` 字段（`state.py:322-347`）。

## 3. agent-framework：单文件 JSON+pickle 混合编码

### 3.1 WorkflowCheckpoint 字段全集【核心】

`python/packages/core/agent_framework/_workflows/_checkpoint.py:82-99`：

```python
workflow_name: str; graph_signature_hash: str          # 拓扑哈希，恢复时校验
checkpoint_id: str(uuid4); previous_checkpoint_id: str|None  # checkpoint 链
timestamp: str(ISO-UTC)
messages: dict[str, list[WorkflowMessage]]              # executor 间消息
state: dict[str, Any]   # 含保留键 '_executor_state'、'_edge_state'(fan-in 半满缓冲)
pending_request_info_events: dict[str, WorkflowEvent]  # HITL 待答请求入档
iteration_count: int; metadata: dict; version: str = "1.0"
```
三个细节：checkpoint **不含工作流实例 ID**，可跨实例共享恢复（:37-41）；`iteration_count` 不唯一——HITL 流程在同一超步 K 会落两个 checkpoint（暂停点 + 响应进入点），**排序只认 previous_checkpoint_id 链 + timestamp**（:63-73）；state 只装已提交态（:55-59）。

### 3.2 序列化与文件布局【核心】

- 混合编码（`_checkpoint_encoding.py:1-15, 82-91`）：JSON 骨架保持人读，非 JSON 原生类型（超出 str/int/float/bool/None）pickle 后 base64、以 `{"__pickled__": ...}` 标记嵌入；解码端 `RestrictedUnpickler` 白名单 = 内建安全类型 + `agent_framework.*` + `openai.types.*`，应用类型经 `register_checkpoint_type("module:qualname")` 注册（:17-45）——文档明言这是**纵深防御而非安全边界**，checkpoint 存储必须当可信源访问控制。
- 文件布局：`<storage_path>/<checkpoint_id>.json`，原子写 `.json.tmp` + `os.replace`（`_checkpoint.py:330-336`）；checkpoint_id 做路径校验防目录逃逸（:295-313）；`get_latest` = 全目录 glob + `max(timestamp)`（:425-439，**无索引文件，O(n) 全扫**）。core 内仅 InMemory/File 两存储；Cosmos beta 在独立包 ⚠️。

## 4. crewAI：两张 SQLite 表吃下三种恢复语义

`memory/storage/kickoff_task_outputs_storage.py:44-57`，库文件 `db_storage_path()/latest_kickoff_task_outputs.db`（:26）：

```sql
CREATE TABLE IF NOT EXISTS latest_kickoff_task_outputs (
  task_id TEXT PRIMARY KEY, expected_output TEXT, output JSON,
  task_index INTEGER, inputs JSON, was_replayed BOOLEAN,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);  -- PRAGMA journal_mode=WAL
```
写入：`INSERT OR REPLACE`，output/inputs 经 `CrewJSONEncoder` json.dumps（:94-106）；跨进程锁 = `store_lock(f"sqlite:{realpath}")` + `BEGIN TRANSACTION`（:42-43, 90）。

- **replay(task_id) 读路径**（`crew.py:2034-2072`）：`load()` 按 task_index 排序全读 → 定位起始任务 → 复用存储的 `inputs` 做插值 → 把起始点之前的存量 output 重建为 `TaskOutput` 对象挂回 tasks（供后续任务做 context）→ `_execute_tasks(start_index, was_replayed=True)`。
- **断点续跑**：`_get_execution_start_index` 返回第一个 `task.output is None` 的下标（`crew.py:1553-1559`）。
- **Flow @persist**（`flow/persistence/sqlite.py:78-112`）：`flow_states(id AUTOINCREMENT, flow_uuid, method_name, timestamp, state_json TEXT)`（pydantic `model_dump` 后 json.dumps，每次方法完成追加一行，load 取 `ORDER BY id DESC LIMIT 1`）+ **HITL 专用表 `pending_feedback(flow_uuid UNIQUE, context_json, state_json, created_at)`**——挂起时 INSERT OR REPLACE 上下文+状态，恢复 `from_pending` 后 DELETE（:229-244, 280-296）。

## 5. agentscope-java：CAS 乐观并发 + 列表增量追加

### 5.1 DDL 与 SQL 原文【核心】

`agentscope-extensions/agentscope-extensions-jdbc`（默认前缀 `agentscope_`），PG 方言（`jdbc/dialect/vendor/PostgresDialect.java:102-119`）：

```sql
CREATE TABLE IF NOT EXISTS agentscope_sessions (
  session_id VARCHAR(255) NOT NULL, state_key VARCHAR(255) NOT NULL,
  item_index INT NOT NULL DEFAULT 0, state_data TEXT NOT NULL,
  version BIGINT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (session_id, state_key, item_index));
CREATE INDEX IF NOT EXISTS ..._session_idx ON ... (session_id);
```
行键 = `(userId:sessionId, state_key, item_index)`（slotId 拼接见 `JdbcAgentStateStore.java:556-561`）；**列表状态一元素一行**，`<key>:_hash` 辅助键存列表整体 hash——save 时 `ListHashUtil.needsFullRewrite(hash, count)` 判定全量重写 or **只追加尾部增量**（:159-195）。

**CAS SQL 原文**（`dialect/table/SessionStateDialect.java:81-112`，JdbcAgentStateStore.java:252-297 调用；抽查复核命中 :105 `AND item_index = ? AND version = ?`）：

```sql
-- expectedVersion==0（创建）：
INSERT INTO sessions (session_id, state_key, item_index, state_data, version) VALUES (?,?,?, ?, 1)
-- 主键冲突 → 映射为 UNVERSIONED（isDuplicateKey 兼容 SQLite errorCode=19，:536-548）
-- expectedVersion>0（更新）：
UPDATE sessions SET state_data = ?, version = ?          -- ? = expectedVersion+1
WHERE session_id = ? AND state_key = ? AND item_index = ? AND version = ?
```
普通 upsert（PG）：`INSERT ... VALUES(...,1) ON CONFLICT (...) DO UPDATE SET state_data=EXCLUDED.state_data, version=version+1`（PostgresDialect.java:123-139）。`getVersioned` 只 SELECT state_data+version；**readVersion 永不反序列化 payload**（:236-249）。

### 5.2 序列化、后端矩阵与分布式

- AgentState 序列化 = **Jackson JSON**（`JsonUtils.getJsonCodec().toJson`，JdbcAgentStateStore.java:138）；字段序：session_id/user_id/summary/context(Msg 列表)/reply_id/cur_iter/shutdown_interrupted/permission_context/tool_context/tasks_context/plan_mode_context（`core/state/AgentState.java:46-58`）；interruptControl `transient` 永不落盘（:73-79）。
- 后端：jdbc（SPI 自动探测 4 方言 PG/MySQL/SQLite/H2）+ redis（Jedis/Redisson 双实现）+ mysql + postgresql + mongodb + oss + cos，另有 core InMemory/JsonFile 与 service 层 JPA。
- **RedisDistributedStore 存什么**（`RedisDistributedStore.java:87-108`）：一个门面按 key 前缀装配四件套——`session:`(AgentStateStore)、`store:`(workspace 文件 KV)、`snapshot:`(沙箱快照)、`guard:`(沙箱并发锁)。JDBC 侧的分布式锁兜底是 `agentscope_distributed_locks(lock_name PK)` 表：INSERT 抢锁 / DELETE 释放，50ms→1s 指数退避（`AbstractJdbcDialect.java:249-312`）。

## 6. dify：平台级表族 + 对象存储 offload + Redis 命令通道

### 6.1 表 DDL 要点（api/models/workflow.py）【核心】

| 表 | 关键字段 | 证据 |
|---|---|---|
| workflow_runs | id/tenant_id/app_id/workflow_id/type/triggered_from/version/**graph(LongText)**/**inputs(LongText)**/status/outputs(LongText default '{}')/error/elapsed_time(Float)/total_tokens(BigInteger)/total_steps/created_by_role/created_by/created_at/finished_at/exceptions_count；索引(tenant,app,triggered_from)+(created_at,id) | :828-858 |
| workflow_node_executions | id/tenant/app/workflow_id/triggered_from/workflow_run_id/**index**/predecessor_node_id/node_execution_id/node_id/node_type/title/**inputs/process_data/outputs 三 LongText**/status/error/elapsed_time/execution_metadata/created_at/created_by_role/created_by/finished_at；5 组索引 | :1050-1075 |
| workflow_node_execution_offload | id PK/created_at/tenant_id/app_id/**node_execution_id(nullable，NULL=待 GC)**/**type(inputs\|process_data\|outputs)**/**file_id→UploadFile**；UNIQUE(node_execution_id,type) 依赖 PG NULLs-distinct；inputs/outputs 分开两行是为保住「节点开始时 inputs 可见」的实时可观测性（设计注释 :1255-1268） | :1217-1287 |
| workflow_conversation_variables | id+conversation_id 复合 PK/app_id/**data LongText**(pydantic `model_dump_json`)/created_at/updated_at | :1521-1547 |
| workflow_pauses | id/**workflow_id**(定位版本)/**workflow_run_id UNIQUE**(1:1 用唯一约束而非给大表加列，迁移规避注释 :2126-2129)/**state_object_key String(255)**/resumed_at(软删，恢复后 GC 期再物理删) | :2124-2165 |
| workflow_pause_reasons | pause_id/type_/form_id(HITL 变体非空)/message/node_id | :2180-2211 |

### 6.2 offload 触发与暂停恢复

- **触发条件**（`configs/feature/__init__.py:870-883`）：`WORKFLOW_VARIABLE_TRUNCATION_MAX_SIZE=1024_000` 字节（1000KiB）/`STRING_LENGTH=100000` 字符/`ARRAY_LENGTH=1000` 元素，任一命中 → 全量 JSON 上传为 UploadFile（`node_execution_{id}_{type}.json`），主表保留截断版，offload 表存 file_id 指针（`core/repositories/sqlalchemy_workflow_node_execution_repository.py:277-299`）；读路径 `preload_offload_data` selectinload 重装配（models 侧 :1085-1101）。
- **暂停时 DB 与对象存储各存什么**：`PauseStatePersistenceLayer.on_event` 捕获 `GraphRunPausedEvent`，把 `WorkflowResumptionContext{version:"1", generate_entity, serialized_graph_runtime_state, serialized_response_stream_filter_state}`（pydantic model_dump_json）经 `storage.save(state_obj_key, ...)` 写**对象存储**（`core/app/layers/pause_state_persist_layer.py:39-57, 130-153`；repo :1055-1062）——**执行态在 blob 存储，DB 只存指针与原因**。
- **恢复时 Redis 与 DB 分工**（`core/app/apps/execution_coordinator.py:24-80, 215`）：Redis 承载**命令通道**（`GraphEngineManager(redis_client).send_stop_command`，key=`app_task_command_channel_key(task_id)`）与停止标志（`setex 600s`）；恢复的执行**复用暂停 run 的 task_id**，故 resume 前必须丢弃陈旧命令并删停止标志（:52-80 注释）；DB 侧 `resume_workflow_pause` 置 `resumed_at` 后删 blob（repo :1284-1338）。

## 7. adk-python：事件单列 JSON + 纯追加式 rewind

### 7.1 DDL 与存储形态【核心】

v1 schema（SQLAlchemy 任意 DBAPI，`sessions/schemas/v1.py`）：

| 表 | 字段 | 证据 |
|---|---|---|
| sessions | app_name+user_id+id 三列 PK、**state(MutableDict+DynamicJSON)**、create_time、update_time(PreciseTimestamp) | :72-98 |
| events | id+app_name+user_id+session_id 四列 PK、invocation_id、timestamp、**event_data(单 DynamicJSON 列)**；FK→sessions ON DELETE CASCADE + idx(app,user,session,ts desc) | :177-223 |
| app_states / user_states | 按 state 前缀分表存 `app:`/`user:` 作用域 | :257-274 |
| adk_internal_metadata | key/value（存 schema_version） | :57-69 |

- **state_delta / artifact_delta 的存储形态**：整个 Event `model_dump(exclude_none=True, mode="json")` 塞进 `event_data` **一列 JSON**（v1.py:225-236，抽查复核命中 :199-201）——delta 只是 JSON 内 `actions` 子对象里的两个字段，**无独立列、无 blob**。`DynamicJSON` = PG 上 JSONB、其他方言 TEXT+json.dumps（`schemas/shared.py:51-73`）。v0 遗留 schema 是逐字段列（author/content/grounding_metadata/... + `actions DynamicPickleType` **pickle 列**，`schemas/v0.py:260-310`）——v0→v1 的本质是 pickle 列收拢为 JSON 单列。
- **事件与 artifact 分表吗**：事件与 session 分表（FK 级联删）；**artifact 不进 DB**——`artifact_delta` 只记 filename→version 映射，实体 part 在 BaseArtifactService（GCS 等外部件）。
- SqliteSessionService（原生 SQL 版）4 表同构，`event_data TEXT`；state 合并用自写 `json_group_object UNION` SQL 而非 `json_patch`——刻意保证 **delta 键全胜（含 null）**、避免 json_patch 的深合并与 null 删键语义（`sqlite_session_service.py:51-118`）。
- **写入并发**：进程内 per-session asyncio/threading 双锁串行 append（`database_session_service.py:413-468`）+ 跨副本乐观并发——`_storage_update_marker`（update_time 微秒 ISO）与库内值比对，不一致即并发冲突路径（:949-969）。
- **rewind_session 存储操作序列**（`_rewind_utils.py:149-204`）：定位目标 invocation 的事件下标 → 反向重放其后事件的 state_delta 构造**补偿 delta**（新值回写 + 多余键置 None，:40-72）→ 构造 `Event(author="user", actions={rewind_before_invocation_id, state_delta, artifact_delta})` → **一次 append_event**。全程零删行——rewind 本身是一条事件。
- **migration 机制**：无 alembic——版本戳在 `adk_internal_metadata`，`MIGRATIONS = {v0_pickle: (v1_json, migrate)}` 链式映射；迁移是 source→dest 拷贝（禁止原地），多步迁移中间态落临时 SQLite；legacy pickle 用 RestrictedUnpickler（`migration/migration_runner.py:34-100`、`_restricted_pickle.py`）。建表走 `metadata.create_all`（`database_session_service.py:247`）。

## 8. checkpoint 必须装什么：元素清单与横向对比

| 元素 | langgraph | agent-framework | adk-python | dify | crewAI | agentscope-java | deepagents |
|---|---|---|---|---|---|---|---|
| 消息历史 | ✅ channel_values（PG 拆 blob） | ✅ messages | ✅ 事件 content | ⚠️ 节点 outputs（非对话语义） | ✅ 任务 output | ✅ context 列表 | ✅ DeltaChannel 增量 |
| 版本/调度表 | ✅ channel_versions+versions_seen | ❌（无调度差分） | ❌（无版本概念） | ❌ | ❌ | ✅ version 列（CAS 用） | 继承 langgraph |
| pending writes | ✅ checkpoint_writes 表 | ⚠️ 只装已提交态 | ✅ 事件天然即 delta | ✅ 节点 started 状态行 | ❌ | ⚠️ resumeAgent 走 pending 工具调用 | 继承 langgraph |
| HITL 挂起 | ⚠️ interrupt 存 `__interrupt__` 通道值 | ✅ pending_request_info_events | ✅ 长事件+表单事件 | ✅ workflow_pauses+reasons | ✅ pending_feedback 表 | ✅ permission/tasks_context | 继承 langgraph |
| 执行游标 | ✅ metadata.step + parent 链 | ✅ iteration_count（不可作序） | ✅ timestamp+invocation_id | ✅ index/predecessor_node_id | ✅ task_index | ✅ cur_iter | 继承 langgraph |
| 拓扑哈希 | ❌ | ✅ graph_signature_hash（唯一） | ❌ | ⚠️ run 内存 graph 快照 | ❌ | ❌ | ❌ |
| 图定义快照 | ❌ | ❌ | ❌ | ✅ graph 列（每 run 全量） | ❌ | ❌ | ❌ |
| 并发控制 | upsert 幂等（无 CAS） | 无 | update_marker 乐观检查 | 唯一约束+UUIDv7 重生成 | 文件锁+事务 | ✅ SQL 级 CAS | 继承 langgraph |

**五条设计结论**：

1. **「按通道版本寻址的旁表」是快照派体积控制的存储根基**：langgraph `checkpoint_blobs(channel, version)` 使未变通道零拷贝跨 checkpoint 复用（DO NOTHING upsert），DeltaChannel 哨兵（msgpack ext 7 / PG 行内 `True` 占位）再把「值本体的重复」压成「祖先写入重放」——SQLite 版无 blob 表是清晰的对照组，证明该优化必须以表结构为前提。
2. **事件派把 schema 冻结压进一个 JSON 列**：adk v0（十几个 pickle 列）→v1（`event_data` 单 JSON 列）的迁移方向说明，事件载荷的字段演进成本远高于快照，单列 JSON + `exclude_none` dump 是当前最优解；dify 的 offload 表进一步表明：当 JSON 列大到伤主表时，指针表 + 对象存储是平台级标配。
3. **恢复语义的粒度由「行键」决定，不由 API 决定**：`(thread_id, checkpoint_ns, checkpoint_id)` 给出超步级+子图命名空间；`(session_id, state_key, item_index)` 给出键级 CAS；`task_index` 给出任务级重放；`previous_checkpoint_id` 链给出 HITL 双 checkpoint 排序——先设计行键，恢复 API 只是它的投影。
4. **并发控制是否下推 SQL 是成熟度分水岭**：agentscope-java 把 CAS 写进 `WHERE version=?` 原文（连「读版本不反序列化 payload」都照顾到），adk 用 update_time 微秒 marker 做应用层乐观锁，langgraph/agent-framework 基本依赖单写者假设（upsert 幂等 / 文件原子替换）——多副本部署前必须先回答这一题。
5. **HITL 挂起正在收敛为「一等持久对象」**：MS `pending_request_info_events` 入 checkpoint 本体、crewAI 独立 `pending_feedback` 表、dify `workflow_pauses`(状态指针)+`workflow_pause_reasons`(原因表) + Redis 命令通道——共同点是挂起不再是对话状态的附属品，而是带独立生命周期（软删/GC/复用 task_id 的通道清理）的存储实体。
