# dify 持久化深挖档案（介质全景 / 会话表族 / 写入策略 / Redis / 借鉴意义）

> agent-persistence 轮补充深挖（单对象）。基线：~/develop/opensource/dify @ 79effdd498（1.17.1，2026-09-12），只读。与 `dimensions/02-执行状态与checkpoint.md` §6（workflow 表族 DDL/offload/暂停恢复）和 `dimensions/03-记忆存储.md` §9（标注三表）互补：那两篇已覆盖的结论本文只引用不重述，本文补齐**会话表族、Message 写入策略、Redis key 全景、暂停恢复完整操作序列、租户/软删/迁移/清理、本地存储布局**。引擎本体已外置 graphon==0.7.0，事件/领域实体以 dify 侧导入面为证据。证据格式：`api/相对路径:行号`。

## 1. 持久化面全景：五层介质

| 介质 | 存什么 | 关键模块入口 | 备注 |
|---|---|---|---|
| **SQL 数据库**（PG/MySQL，compose 默认 postgres） | 全部业务真相源：apps/conversations/messages（无 tenant_id）、workflow 族（有 tenant_id）、标注、HITL 表单、RBAC、dataset 元数据 | `api/models/`（model.py 2750 行、workflow.py、dataset.py、tools.py…）；写入经 repository 层 `api/repositories/` + `api/core/repositories/` | 表族间租户策略不一致（§6） |
| **Redis**（默认 db0） | 命令通道/停止标志、SSE pubsub 事件总线、凭据与 embedding 缓存、滑窗限流、分布式锁、任务归属校验 | `api/extensions/ext_redis.py`（全部 key 统一加 `REDIS_KEY_PREFIX:` 前缀，redis_names.py）；清单见 §4 | **无 Redis 持久化数据——全部可丢可重建** |
| **对象存储**（STORAGE_TYPE，默认 opendal/fs） | 上传文件、节点执行 offload JSON、**workflow 暂停状态 blob**、租户 RSA 私钥（key provider）、（SaaS）run 归档 bundle | `api/extensions/ext_storage.py`（13 种后端）；`api/extensions/storage/opendal_storage.py:29-40`（fs root 默认 `storage`，RetryLayer 3 次） | 布局见 §6.4 |
| **向量库**（VECTOR_STORE 可配，10+ 后端） | 知识库文档向量、标注问答向量（复用同一工厂）、摘要索引 | `api/core/rag/datasource/vdb/vector_factory.py` | 真相源在 SQL（dataset/segment/annotation 表），向量可重建（dimensions/03 §9） |
| **Celery**（broker=Redis db1，`docker/.env.example:121`） | 异步落库（workflow_storage 队列）、保留清理（retention 队列）、会话级联删除（conversation 队列）、归档导出（workflow_archive 队列）、异步 workflow（professional/team 双队列） | `api/extensions/ext_celery.py:168-300`（imports+beat）；`api/tasks/`、`api/schedule/` | `task_ignore_result=True`（ext_celery.py:141），结果后端形同虚设 |

## 2. 会话表族：DDL 与写入策略

### 2.1 conversations（api/models/model.py:1124-1199）【核心】

| 列 | 类型 | 默认/可空 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| app_id / app_model_config_id | StringUUID | 不可空 / 可空 | **无 tenant_id**，租户经 app 解析（model.py:74-90 `_resolve_app_tenant_id`） |
| agent_workspace_binding_id | StringUUID | 可空 | 逻辑指针非 FK（Binding 可先于会话被回收，docstring :1125-1129） |
| model_provider / model_id / override_model_configs(LongText) | | 可空 | override=调试态配置快照（`in_debug_mode` = 非 NULL，:1432） |
| mode | EnumText(AppMode) | | |
| name / summary(LongText) / introduction / system_instruction / system_instruction_tokens(Int) | | | summary 供记忆注入 |
| inputs | sa.JSON（property setter 把 File 对象 model_dump，:1205-1215） | | 会话级变量入参 |
| status | EnumText(ConversationStatus) | normal（唯一取值，enums.py:104-108） | |
| invoke_from / from_source / from_end_user_id / from_account_id | EnumText | | api/console + end_user/account 二元归属 |
| read_at / read_account_id / dialogue_count | | | 未读计数 |
| **is_deleted** | Boolean | false | 软删标志；索引见附录 A-0（1 普通 + 3 PG 部分索引，:1135-1153） |

### 2.2 messages（api/models/model.py:1463-1520）【核心】

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| app_id / conversation_id(FK→conversations) | StringUUID | | PK + 7 个二级索引（见附录 A-0） |
| model_provider / model_id / override_model_configs | | 可空 | |
| inputs | sa.JSON | | |
| query / answer | LongText | 不可空 | |
| message | sa.JSON | 不可空 | **发给模型的完整 prompt 存档**（`prompt_messages_to_prompt_for_saving`） |
| **token 计量 8 列** | message_tokens(Int)/message_unit_price(Numeric 10,4)/message_price_unit(Numeric 10,7 默认 0.001) + answer_* 三列对称 + total_price(Numeric 10,7)/currency(String) | tokens 默认 0 | prompt 侧与 completion 侧**分列计价**，币种随行 |
| provider_response_latency | Float | 0 | |
| parent_message_id | StringUUID | 可空 | 消息树：重答/再生成为同一 parent 下插新行（无 FK，应用层维护） |
| status | EnumText(MessageStatus) server_default 'normal' | normal | **状态机仅 3 值：normal/paused/error**（enums.py:41-48） |
| error | LongText | 可空 | 错误描述文本 |
| message_metadata | LongText(JSON) | 可空 | usage、retriever_resources、annotation_reply 等聚合 metadata |
| invoke_from / from_source / from_end_user_id / from_account_id / app_mode / agent_based(Bool 默认 false) / workflow_run_id(可空) / created_at / updated_at | | | workflow_run_id 把消息挂到 workflow_runs |

**伴生表**：`message_files`（model.py:1909-1934：message_id/type/transfer_method/created_by_role/created_by/belongs_to(user|assistant)/url/upload_file_id——**上传文件只存指针，实体在 upload_files+对象存储**）；`message_feedbacks`（:1859，rating like/dislike + content）；`saved_messages`（models/web.py:14-39，终端用户收藏）；`message_agent_thoughts`（model.py:2477，position 排序的 ReAct 思维链）；`message_chains`。

### 2.3 Message 写入策略：两阶段，终态一次落库【核心】

1. **预创建（生成前）**：`_init_generate_record` 先 INSERT conversation（新会话时）+ Message（answer=''、message=''、tokens=0、currency='USD'）+ 用户侧 MessageFile，一次 commit（api/core/app/apps/message_based_app_generator.py:173-248）。行存在但内容全空——流式期间客户端以 task_id 订阅，不读该行。
2. **流式期间零 UPDATE**：chunk 只在内存累积（`_task_state.llm_result.message.content`，easy_ui_based_generate_task_pipeline.py:376-378；advanced chat 为 `_task_state.answer`）。**没有逐 chunk 写库**。
3. **终态一次回填**：`QueueStopEvent|QueueMessageEndEvent` → `_save_message`（easy_ui…pipeline.py:425-499）：answer（去模板变量）、token 8 列、total_price/currency、latency、message（prompt 存档）、message_metadata（含 usage）全部此刻 UPDATE。stopped-by-user 路径先用本地 token 估算 calc_response_usage（:501-529）；被停 Agent run 若 provider 已回填 usage 则 `preserve_existing_usage=True` 不覆盖（:321-332）。
4. **错误路径**：`QueueErrorEvent` → `handle_error`：`message.status=ERROR; message.error=描述`（based_generate_task_pipeline.py:50-75），不写 answer。
5. **advanced chat（chatflow）变体**（api/core/app/apps/advanced_chat/generate_task_pipeline.py:1063-1120）：暂停时提前 save 且 `status=PAUSED`（:738-743），恢复续跑后下次 save 把 PAUSED 翻回 NORMAL（:1068-1069）；usage 取自 `graph_runtime_state.llm_usage`（引擎跨节点累加器，:1078-1088）；流式指标 ttft/ttg 写进 metadata.usage（:1094-1099）；assistant 产出文件此刻批量插 MessageFile（:1103-1120）。

## 3. Workflow 运行表族：写入时机与计量链

DDL（workflow_runs / workflow_node_executions / offload / pauses / conversation_variables）已在 dimensions/02 §6.1 列全，此处补**写入时序与状态机全集**【核心】：

| 事件（graphon GraphEngineEvent） | 落库动作 | 证据 |
|---|---|---|
| GraphRunStartedEvent | run 行 status=RUNNING、graph 全量快照、inputs（sys.* 拼入、剔除 conversation_id 保持可复用）；**恢复(resumption)时重载既有节点执行进内存 cache 并续 index 序号** | core/app/workflow/layers/persistence.py:152-169, 342-354 |
| NodeRunStartedEvent | 节点执行行 status=RUNNING（**只有 index/node_id/title，无 inputs/outputs**）；默认走 Celery 异步队列 `workflow_storage`，仅 Agent v2 节点同步落库 | persistence.py:226-264；tasks/workflow_node_execution_tasks.py:27（queue="workflow_storage"，max_retries=3 指数退避） |
| NodeRunRetryEvent | status=RETRY + 重试历史追加进 process_data 的 `__retry_history__` 键 | persistence.py:266-277, 370-398 |
| NodeRunSucceeded/Failed/Exception | 终态回填 outputs（按节点类型投影）/error/elapsed_time/finished_at；EXCEPTION 是独立于 FAILED 的状态 | persistence.py:279-321 |
| NodeRunPauseRequestedEvent | status=PAUSED，**不写 outputs** | persistence.py:323-331 |
| GraphRunFailed/Aborted | run.status=FAILED/STOPPED + `_fail_running_node_executions` 把 cache 中所有 RUNNING 节点批量置 FAILED | persistence.py:192-213, 466-474 |
| GraphRunPaused | run.status=PAUSED + outputs，`update_finished=False`（不写 finished_at） | persistence.py:215-221 |

- **run 状态机全集**：RUNNING / SUCCEEDED / PARTIAL_SUCCEEDED / FAILED / STOPPED / PAUSED（model.py:1375-1382）；**节点状态机**：RUNNING / RETRY / SUCCEEDED / FAILED / EXCEPTION / PAUSED。
- **total_tokens 计量链**：引擎侧 `graph_runtime_state.total_tokens`（graphon 累加）→ 终态 `_populate_completion_statistics` 一次性拷入 run.total_tokens；total_steps=node_run_steps、exceptions_count=max(已有, runtime_state.exceptions_count)（persistence.py:415-422）；消息侧 usage 另取 `graph_runtime_state.llm_usage`——**run 与 message 各存一份计量，来源同一 runtime state**。
- **写入双通道**：`CeleryWorkflowNodeExecutionRepository.save`→celery task（领域实体 pydantic 序列化跨进程传 dict）；`SQLAlchemyWorkflowNodeExecutionRepository.save` 同步 upsert + tenacity 重复键重试（regenerate UUID）+ process_data 合并保留 agent binding（core/repositories/sqlalchemy_workflow_node_execution_repository.py:319-416）。offload 触发/阈值见 dimensions/02 §6.2。
- 旁表：`workflow_app_logs`（workflow.py:1326，运行日志索引）；`workflow_archive_logs`（:1416，归档后替代 run 的快照行）；`workflow_run_archive_bundles`（:1485，**对象存储 R2 manifest 的查询索引**，行可由 manifest 重建——"index is disposable" 再次出现）。

## 4. Redis key 全景清单【核心】

全局：所有 key 经 `serialize_redis_name` 加 `REDIS_KEY_PREFIX`（redis_names.py）；Celery broker 用 `global_keyprefix` 同前缀（ext_celery.py:99-111）。

| key 模式 | 类型/TTL | 用途 | 证据 |
|---|---|---|---|
| `workflow:{task_id}:commands` | list（pending 标记约 1h） | GraphEngine 命令通道（stop/abort/resume） | core/app/apps/execution_coordinator.py:24-26, 49-80 |
| `generate_task_stopped:{task_id}` | setex **600s** | 旧式停止标志；恢复前必删 | execution_coordinator.py:29-38；base_app_queue_manager.py:253-259 |
| `generate_task_belong:{task_id}` | setex **1800s** = `{account|end-user}-{user_id}` | 停止操作的**属主校验**（只有发起者能停） | base_app_queue_manager.py:60-62, 188-203 |
| `channel:{app_mode}:{workflow_run_id}` | pubsub topic（或 streams，XTRIM 保留 **600s**） | **SSE 流式事件总线**：worker 侧 publish、API 侧 subscribe（异步任务与 API 跨进程） | message_based_app_generator.py:306-336；streaming_utils.py:16-56；redis_pubsub_config.py（PUBSUB_MODE pubsub|streams） |
| `{provider}_{model}_{text_hash}` | setex **600s** | embedding 结果缓存（base64 向量） | core/rag/embedding/cached_embedding.py:199-228 |
| `{type}_credentials:v2:tenant_id:{tid}:id:{id}` | setex **86400s** | 模型/工具凭据缓存 | core/helper/model_provider_cache.py:17, 44 |
| `plugin_service:latest_plugin:{id}` / `plugin_model_providers:tenant_id:…` | setex | 插件元数据/模型清单缓存 | core/plugin/plugin_service.py:101-103 |
| `model_lb_index:{tenant}:{provider}:{type}:{model}` | expire **3600s** | 负载均衡轮询游标（incr） | core/model_manager.py:1042-1056；冷却标志（:1122） |
| `rl:{scopes}+:{key}` | zset 滑窗，expire=window×2 | 登录/验证码/OpenAPI 限流 | libs/rate_limit.py:87-100 |
| `dataset_metadata_lock_{id}` / `document_metadata_lock_{id}` | set ex **3600s** | 元数据编辑互斥锁 | services/metadata_service.py:369-377 |
| `retention:clean_messages` 等 / `db_upgrade_lock` | redis lock（自动续期） | 清理任务防重入；**迁移互斥锁** | schedule/clean_messages.py:35-37；commands/system.py:138-146 |
| `document_{id}_is_paused|_indexing`、`segment_{id}_indexing` | setex **600s** | 索引任务进行中标记（防重） | services/dataset_service.py:2135-2219 |
| `tenant_privkey:{sha3(path)}` | setex **120s** | 租户 RSA 私钥短期缓存 | libs/rsa.py:69-77 |
| `vector_indexing_{collection}` | — | 建索引去重，建完即删 | core/rag/datasource/vdb/vector_factory.py:283-284 |
| `annotation_import_rate_limit:{tenant}:1min/1hour` 等 | zset/str | 批量导入限流与作业进度 | controllers/console/wraps.py:451-469 |
| `oauth_provider:{client_id}:{code|access|refresh}_token` | setex | OAuth 授权码/令牌（Dify 作 IdP） | repositories/oauth_server_repository.py:30-32 |
| `{prefix}active_requests` | hset+expire 1d | app 并发请求上限 | core/app/features/rate_limiting/rate_limit.py:54-87 |
| Celery broker（db1） | — | 任务队列本体 | docker/.env.example:121 |

**无 conversation 变量缓存**——会话变量直接落 `workflow_conversation_variables` 表（dimensions/02 §6.1），Redis 不参与。

## 5. 暂停恢复完整存储操作序列【核心】

表结构前提（dimensions/02 §6.1）：`workflow_pauses`（workflow_run_id UNIQUE 1:1、state_object_key、resumed_at 软删）+ `workflow_pause_reasons`（HITL/scheduling 原因）。

**① 暂停（HITL 节点触发 pause）**
1. 引擎发 `GraphRunPausedEvent` → `WorkflowPersistenceLayer`：run.status=PAUSED（不写 finished_at）。
2. `PauseStatePersistenceLayer.on_event`：`WorkflowResumptionContext{version, generate_entity, serialized_graph_runtime_state, serialized_response_stream_filter_state}` pydantic `model_dump_json`（core/app/layers/pause_state_persist_layer.py:39-57）。
3. `create_workflow_pause` 单事务（repositories/sqlalchemy_api_workflow_run_repository.py:1032-1113）：旧 pause 若存在先删（含 storage.delete）→ **对象存储 save `workflow-state-{uuid}.json`（storage 根目录裸 key）** → INSERT pause 行 + reasons 行 → run.status=PAUSED。**执行态在 blob，DB 只存指针+原因**。
4. advanced chat 消息侧：`_save_message` + status=PAUSED；队列监听 `stop_listen(PAUSED)` 终止本段监听（workflow/app_queue_manager.py:37-38）。

**② 恢复点击（表单提交）**
1. `submit_form_by_token`：校验 form_token → `mark_submitted`（HumanInputForm 状态机）→ `enqueue_resume` 仅投 Celery `resume_app_execution`（services/human_input_service.py:195-231, 265-287）。
2. Celery `resume_workflow_execution`（tasks/async_workflow_tasks.py:203-296）：`get_workflow_pause` → 读对象存储 blob → `WorkflowResumptionContext.loads` 还原 generate_entity / `GraphRuntimeState.from_snapshot` / response_stream_filter；补载 Workflow/App/user。
3. **`clear_app_task_cancellation_signals(task_id)`（tasks/app_generate/workflow_execute_task.py:566）**：DELETE `generate_task_stopped:{task_id}` + 排空并 DELETE `workflow:{task_id}:commands`——**恢复复用暂停 run 的 task_id，陈旧停止信号不清理会在启动瞬间自杀**（execution_coordinator.py:49-80 注释）。
4. `resume_workflow_pause` 事务：pause.resumed_at=now + run.status=RUNNING（repo:1237-1303，幂等护栏：非 PAUSED / 已 resumed 均拒绝）。
5. `generator.resume(...)` 带快照续跑；事件继续发到 `channel:{app_mode}:{workflow_run_id}`，客户端经 `workflow_events`「resume 后取流」接口重订阅读剩余事件（controllers/console/human_input_form.py:157-166）。
6. 终态后 `delete_workflow_pause`：storage.delete(blob)（best-effort，失败仍删行——行不删会因 UNIQUE 阻塞下次暂停，repo:1335-1352）。

**③ GC**：`prune_pauses`（created_at 超期 OR resumed_at 超期，批量 limit，repo:1355-1426）。

## 6. 租户 / 软删除 / 迁移 / 清理 / 本地存储

### 6.1 tenant_id 覆盖（grep `tenant_id: Mapped` 统计）

| 有 tenant_id | 无 tenant_id |
|---|---|
| workflow 全族（workflow.py ×8）、dataset ×15、tools ×8、agent ×9、provider ×9、trigger ×7、model.py ×14（apps/end_users/upload_files/annotations…）、account ×4 | **conversations / messages / message_files / message_feedbacks / message_annotations / saved_messages / pinned_conversations / message_agent_thoughts（web.py ×0）** |

无租户列的会话族靠 `app_id → App.tenant_id` 间接解析（model.py:74-90），越权防护在应用层而非行级。

### 6.2 软删除与物理级联

- 软删仅 `conversations.is_deleted`（Boolean + PG 部分索引）；API 删除=置位 + 立即投递 Celery `delete_conversation_related_data`，**兜底 sweeper 定期重投漏派发的软删会话**（tasks/delete_conversation_task.py:138-158）。
- 物理级联清单（:60-118）：message_agent_thoughts/chains/files/saved/annotations/feedbacks → messages → conversation_variables（含 tool 版）→ HITL 表单四表 → conversation 本体；tool_files 连同**对象存储实体**逐个删除。其余表无软删直接批量删。
- `created_by_role` 枚举仅 2 值 `account|end_user`（models/enums.py:11-13），遍布 workflow_runs/节点执行/message_files——区分控制台操作者与终端用户。

### 6.3 迁移机制

- Alembic：`api/migrations/versions` **218 个版本文件**；`flask upgrade-db` 内建 **Redis 锁 `db_upgrade_lock`（自动续期）防多副本并发迁移**（commands/system.py:137-160）；容器入口 `api/docker/entrypoint.sh:13` 启动即执行 → **启动自动迁移**。

### 6.4 保留/清理/归档（beat 全表：ext_celery.py:184-300）

| 任务 | 队列/周期 | 保留参数 |
|---|---|---|
| clean_workflow_runlogs_precise | retention，每日 02:00 | `WORKFLOW_LOG_RETENTION_DAYS` 默认 **30 天**（feature/__init__.py:1624）；按 (created_at,id) 游标批删 + message 全级联 + 3 次重试退避（schedule/clean_workflow_runlogs_precise.py:44-107） |
| clean_workflow_runs_task | retention，每日 00:00，SaaS/sandbox 租户 | redis 锁防重入 |
| clean_messages | retention（crontab 04:00） | 分批物理删 messages |
| conversation_cleanup_sweeper | conversation，interval 可配 | 软删会话兜底重投 |
| clean_embedding_cache / clean_unused_datasets / clean_oauth_tokens | 各自周期 | DB 侧缓存表、孤儿 dataset、过期 token |
| human_input_form_timeout | interval | HITL 超时自动恢复 |
| 归档（SaaS） | workflow_archive 队列 | run → R2 bundle（`workflow_run_archive_bundles` 为 manifest 查询索引）+ 按需打包下载缓存 |

**日志表**：`operation_logs`（model.py:2077，控制台操作审计）、`workflow_app_logs`、`workflow_archive_logs`；无独立运行日志表——运行日志即 workflow_runs/node_executions 本体。

### 6.5 本地 ./storage 布局（STORAGE_TYPE=opendal，scheme=fs，root=storage）

| 路径 | 内容 | 证据 |
|---|---|---|
| `upload_files/{tenant_id}/{uuid}.{ext}` | 所有上传文件 + 节点 offload JSON（同一上传通道，DB 留 upload_files 行+sha3_256 hash） | services/file_service.py:91-120 |
| `workflow-state-{uuid}.json`（**根目录裸 key**） | 暂停恢复状态 blob | sqlalchemy_api_workflow_run_repository.py:1054-1055 |
| 租户 RSA 私钥 | key provider=local 时（加密 provider 凭据），Redis 只做 120s 缓存 | configs/middleware/__init__.py:95-103；libs/rsa.py |
| `tools/…` | 工具产出 ToolFile 实体 | models/tools.py:482 |

## 7. 对企业级 agent（分布式服务端 + Web）的借鉴意义

**照搬清单**
1. **Message「预创建空行 + 终态一次 UPDATE」**：流式期间零写库，answer/tokens/usage/error 在 stop/end/error 三个终态事件各写一次——把 OLTP 写放大与生成时长解耦，是最稳的会话转录写入模型（§2.3）。
2. **停止三件套**：`generate_task_belong`（属主校验）+ `generate_task_stopped`（600s 标志）+ 命令通道，跨副本停流式任务（§4）；**恢复前清理陈旧取消信号**的注释级教训（§5-②3）直接抄。
3. **暂停 = 对象存储存执行态 + DB 存指针/原因/UNIQUE 1:1 + resumed_at 软删 + prune GC**：HITL 挂起的一等持久对象全套生命周期（§5），配合「复用 task_id + 事件总线 topic 按 run_id 寻址」使恢复后 SSE 无缝续流。
4. **大字段三级策略**：行内截断 → offload 指针表（UNIQUE(node_execution_id,type)）→ 对象存储 JSON；inputs/outputs 分行保住节点开始时的可观测性（dimensions/02 §6.1 已证）。
5. **迁移启动自动 + Redis 锁防多副本并发 upgrade**（§6.3）；Celery 队列按域拆分（storage/retention/conversation/archive）+ beat 全配置化开关。

**改造清单**
1. **会话族缺 tenant_id**：靠 app_id 间接解析在单库归属清晰时可行，但行级隔离、跨租户清理、分库分表都需要真列——企业级第一件事是把 tenant_id 下沉到 messages/conversations。
2. **节点执行默认异步落库（Celery）**：崩溃窗口内 RUNNING 行永远悬空（靠 GraphRunFailed 批量兜翻 FAILED，但进程死亡无人发事件）；需要「启动时扫描孤儿 RUNNING 行」的 watchdog 或改同步写关键节点。
3. **状态机取值**：Message 仅 normal/paused/error，没有 queued/running/streaming——Web 端要展示「生成中」只能靠内存/Redis；企业级若要断线重连后看到中间态，需给 message 加执行态列或事件表。
4. **Redis 事件总线 pubsub 模式不持久**：切 streams 模式（600s 保留）才有断线补拉；两模式并存但默认 pubsub，按 SLA 显式选型。
5. **run 行内 graph 快照（每 run 全量 LongText）体积大**：可改为引用 workflow 版本表 + 增量。

**补缺清单**
1. **无 per-message 事件/增量持久层**：answer 只在终态落库，中途崩溃则该轮回答丢失——高价值场景补「chunk 周期性 checkpoint answer」或事件流表（对照 opencode 逐 part 即时写，两者是写频谱的两端，见 report §3）。
2. **usage 双份存储**（message 列 + run.total_tokens）无对账机制，stop 路径本地估算与 provider 上报混用；企业计费需单一事实源 + 对账任务。
3. **清理任务全是「删」，无冷热分层导出**（归档仅 SaaS 路径，社区版 30 天硬删）；企业审计需自带 archive-to-object-storage 管道。
4. **Redis 全量可丢但无降级策略说明**：停止标志/属主缓存失效即拒绝停止或放行，行为依赖 Redis 可用性；多可用区部署需明确 Redis 故障时的语义。
5. **parent_message_id 消息树无 FK 无约束**：重答分叉纯应用层约定，删消息不清理子链引用；若做「基于消息树回滚重放」需先补完整性。

## 附录 A：全表字段明细（21 表，@79effdd498 逐列对码）

> 通用约定：`StringUUID`=UUID 字符串列；`EnumText(E)`=枚举文本列；`LongText`=TEXT；`DefaultFieldsDCMixin` 自动提供 `id`(PK, uuidv7)/`created_at`/`updated_at`（api/models/base.py:60-90）。`CreatorUserRole` 仅 `account|end_user`（enums.py:11-13）。

### A-0. conversations / messages 核对结果（§2.1/2.2 已有全字段）

- **conversations** 逐列核对一致，无遗漏。补两点：`mode` 取 AppMode 现 **8 值**：`completion/workflow/chat/advanced-chat/agent-chat/agent/channel/rag-pipeline`（model.py:374-385）；索引实为 **4 个**：`conversation_app_from_user_idx`（非 partial）+ 3 个 partial（`app_id,created_at DESC WHERE is_deleted IS false` / `app_id,updated_at DESC WHERE is_deleted IS false` / `is_deleted,updated_at WHERE is_deleted IS true`，model.py:1135-1153）。
- **messages** 逐列核对一致（32 列全覆盖）。索引实为 **1 PK + 7 个二级**（model.py:1465-1474）：`message_pkey`、`message_app_id_idx(app_id,created_at)`、`message_conversation_id_idx`、`message_end_user_idx`、`message_account_idx`、`message_workflow_run_id_idx(conversation_id,workflow_run_id)`、`message_app_mode_idx`、`message_created_at_id_idx`。

### A-1. message_files（消息↔文件关联：文件指针行；写入=消息预创建时用户文件 + chatflow 终态 assistant 文件）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| message_id | StringUUID | 不可空 | 属主消息 |
| type | EnumText(FileType) | 不可空 | 文件种类（枚举在外部包 graphon.file） |
| transfer_method | EnumText(FileTransferMethod) | 不可空 | `local_file/remote_url/tool_file/datasource_file`（model.py:1730-1773 match） |
| created_by_role | EnumText(CreatorUserRole) | 不可空 | |
| created_by | StringUUID | 不可空 | 按 role 指向 Account/EndUser |
| belongs_to | EnumText | 可空/None | `user|assistant`（enums.py:298-302）——用户上传还是模型产出 |
| url | LongText | 可空/None | remote_url 的原始 URL；tool_file 时为签名 URL |
| upload_file_id | StringUUID | 可空/None | → upload_files.id（本地文件实体指针） |
| created_at | DateTime | 不可空 | |

索引：`message_file_pkey`；`message_file_message_idx(message_id)`；`message_file_created_by_idx(created_by)`（model.py:1911-1915）。

### A-2. message_feedbacks（消息点赞/点踩+文字反馈）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| app_id / conversation_id / message_id | StringUUID | 不可空 | 被评价消息 |
| rating | EnumText | 不可空 | `like|dislike`（enums.py:173-177） |
| from_source | EnumText | 不可空 | `user|admin`（enums.py:157-161） |
| content | LongText | 可空/None | 反馈文字 |
| from_end_user_id / from_account_id | StringUUID | 可空/None | 二元归属其一非空 |
| created_at / updated_at | DateTime | 不可空 | |

索引：pkey；`(app_id)`；`(message_id,from_source)`；`(conversation_id,from_source,rating)`（model.py:1861-1866）。

### A-3. saved_messages（终端用户收藏；写入=saved_message_service.py:59-68 幂等插入）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| app_id / message_id | StringUUID | 不可空 | 被收藏消息 |
| created_by_role | EnumText | 不可空/server_default 'end_user' | |
| created_by | StringUUID | 不可空 | |
| created_at | DateTime | 不可空 | |

索引：pkey；`(app_id,message_id,created_by_role,created_by)`；`(message_id)`（models/web.py:16-20）。

### A-4. pinned_conversations（会话置顶标记，按用户粒度；unpin=删行）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| app_id | StringUUID | 不可空 | |
| conversation_id | StringUUID | 可空 | 被置顶会话 |
| created_by_role | EnumText | 不可空/server_default 'end_user' | |
| created_by | StringUUID | 不可空 | |
| created_at | DateTime | 不可空 | |

索引：pkey；`(app_id,conversation_id,created_by_role,created_by)`（web.py:44-47）。

### A-5. message_agent_thoughts（legacy Agent 每步 ReAct 思维链/工具调用/计量快照；写入=base_agent_runner.py:225-258，每工具步一行）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| message_id | StringUUID | 不可空 | |
| position | Integer | 不可空 | 步序号（读取按升序） |
| created_by_role / created_by | | 不可空 | |
| message_chain_id | StringUUID | 可空/None | 现固定 None（base_agent_runner.py:236） |
| thought | LongText | 可空/None | 思维文本 |
| tool | LongText | 可空/None | 工具名，分号分隔多个（:2530-2531） |
| tool_labels_str / tool_meta_str | LongText | 不可空/'{}' | 工具标签/元数据 JSON |
| tool_input / observation / tool_process_data | LongText | 可空/None | 入参/输出/过程 JSON |
| message | LongText | 可空/None | 本步 prompt 存档 |
| message_token / answer_token / tokens | Integer | 可空/None | 计量（prompt/completion/合计） |
| message_unit_price / answer_unit_price / total_price | Numeric | 可空/None | 价格 |
| message_price_unit / answer_price_unit | Numeric(10,7) | 不可空/0.001 | 计价单位 |
| message_files | LongText | 可空/None | 本步涉及文件 id JSON |
| answer | LongText | 可空/None | 本步回答 |
| currency | String(255) | 可空/None | |
| latency | Float | 可空/None | 本步耗时 |
| created_at | DateTime | 不可空 | |

索引：pkey；`(message_id)`；`(message_chain_id)`（model.py:2479-2483）。

### A-6. message_chains（**遗留表，当前无生产写入方**——仅清理/删除代码引用）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| message_id | StringUUID | 不可空 | |
| type | EnumText | 不可空 | 枚举仅 `system` 一值（enums.py:338-341） |
| input / output | LongText | 可空/None | 链输入/输出 |
| created_at | DateTime | 不可空 | |

索引：pkey；`(message_id)`（model.py:2460-2463）。

### A-7. workflow_runs（一次执行的顶层运行行：状态机/图快照/计量汇总；写入=core/app/workflow/layers/persistence.py）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | run id，SSE 频道按它寻址 |
| tenant_id / app_id / workflow_id | StringUUID | 不可空 | |
| type | EnumText(WorkflowType) | 不可空 | `workflow|chat|rag-pipeline|snippet`（workflow.py:116-124） |
| triggered_from | EnumText | 不可空 | `debugging|app-run|rag-pipeline-run|rag-pipeline-debugging|webhook|schedule|plugin`（enums.py:24-31） |
| version | String(255) | 不可空 | workflow 版本号 |
| graph | LongText | 可空 | **运行时图全量 JSON 快照（每 run 一份）** |
| inputs | LongText | 可空 | 输入 JSON（剔除 conversation_id 保持可复用） |
| status | EnumText | 不可空 | RUNNING/SUCCEEDED/PARTIAL_SUCCEEDED/FAILED/STOPPED/PAUSED |
| outputs | LongText | 可空/'{}' | 输出 JSON |
| error | LongText | 可空 | 失败原因 |
| elapsed_time | Float | 不可空/0 | 耗时秒 |
| total_tokens | BigInteger | server_default 0 | 终态从 graph_runtime_state 一次拷入（persistence.py:415-422） |
| total_steps | Integer | 可空/0 | 节点步数 |
| created_by_role / created_by | | 不可空 | 触发者 |
| created_at | DateTime | 不可空 | |
| finished_at | DateTime | 可空 | PAUSED 时不写 |
| exceptions_count | Integer | 可空/0 | 异常节点计数 |

索引：pkey；`(tenant_id,app_id,triggered_from)`；`(created_at,id)`（保留清理批删游标）（workflow.py:829-833）。

### A-8. workflow_node_executions（单节点执行行；默认经 Celery workflow_storage 队列异步落库）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| tenant_id / app_id / workflow_id | StringUUID | 不可空 | |
| triggered_from | EnumText | 不可空 | `single-step|workflow-run|rag-pipeline-run`（workflow.py:959-966） |
| workflow_run_id | StringUUID | 可空 | 单步调试为 NULL |
| index | Integer | 不可空 | 执行序号，恢复时续号（persistence.py:342-354） |
| predecessor_node_id | String(255) | 可空 | 前驱节点（执行路径展示） |
| node_execution_id | String(255) | 可空 | 外部执行标识（对齐 graphon） |
| node_id / node_type / title | String(255) | 不可空 | 节点标识/类型/标题 |
| agent_workspace_binding_id | StringUUID | 可空 | |
| inputs / process_data / outputs | LongText | 可空 | 大字段；超阈值截断转 offload（:1172-1185） |
| status | EnumText | 不可空 | RUNNING/RETRY/SUCCEEDED/FAILED/EXCEPTION/PAUSED |
| error | LongText | 可空 | |
| elapsed_time | Float | server_default 0 | |
| execution_metadata | LongText | 可空 | total_tokens/total_price/currency 聚合 JSON（:998-1004） |
| created_at | DateTime | server_default now | |
| created_by_role / created_by | | 不可空 | |
| finished_at | DateTime | 可空 | |

索引：pkey；`(workflow_run_id)`；`(tenant_id,app_id,workflow_id,triggered_from,node_id)`；`(tenant_id,app_id,workflow_id,triggered_from,node_execution_id)`；匿名 `(tenant_id,workflow_id,node_id,created_at DESC)`（workflow.py:1019-1048）。

### A-9. workflow_node_execution_offload（大字段外置指针行）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuidv7 | |
| created_at | DateTime | default now | |
| tenant_id / app_id | StringUUID | 不可空 | |
| node_execution_id | StringUUID | 可空/None | **NULL=无主记录，待 GC**（:1249-1252） |
| type | EnumText，列名 `type` | 不可空 | `inputs|process_data|outputs`（enums.py:51-54） |
| file_id | StringUUID | 不可空 | → upload_files.id，JSON 实体在对象存储 |

约束：`UNIQUE(node_execution_id, type)`（无名字；依赖 PG14 NULL-distinct 允许多行 NULL）（workflow.py:1219-1233）。

### A-10. workflow_conversation_variables（chatflow 会话级变量，跨轮持久；写入=conversation_variable_persist_layer.py:22-45，仅落 `conversation.*` 前缀变量）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID | **复合 PK 第一列** | 变量实体 id |
| conversation_id | StringUUID | **复合 PK 第二列**, index | |
| app_id | StringUUID | index | |
| data | LongText | 不可空 | 变量 pydantic model_dump_json |
| created_at | DateTime | index | |
| updated_at | DateTime | onupdate | |

（`workflow_conversation_variable_tools` 表在本版本不存在，grep 零命中。）

### A-11. workflow_pauses（HITL 暂停一等持久对象）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuidv7 | |
| workflow_id | StringUUID | 不可空 | 恢复时定位 workflow 版本（:2133-2138） |
| workflow_run_id | StringUUID | 不可空, **UNIQUE** | 与 run 1:1（:2126-2129） |
| state_object_key | String(255) | 不可空 | 对象存储 key：`workflow-state-{uuid}.json` |
| resumed_at | DateTime | 可空/None | 非 NULL=已恢复（软删语义，:2156-2160） |
| created_at / updated_at | DateTime | 不可空 | |

### A-12. workflow_pause_reasons（暂停原因行，一次暂停可多条；与 pauses 同事务写入）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuidv7 | |
| pause_id | StringUUID | 不可空, index | → workflow_pauses.id |
| type | EnumText | 不可空 | HITL_REQUIRED / LEGACY_HUMAN_INPUT_REQUIRED / SCHEDULED_PAUSE（workflow.py:2237-2267） |
| form_id | String(36) | 不可空/'' | 仅 HITL 类原因非空（:2189） |
| message | String(255) | 不可空/'' | 描述文本 |
| node_id | String(255) | 不可空/'' | 引发暂停的节点；空=非节点原因（:2207-2209） |
| created_at / updated_at | DateTime | 不可空 | |

### A-13. workflow_app_logs（「已发布 app 运行」日志索引，不含调试；写入=run 结束时 + 触发器路径）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| tenant_id / app_id / workflow_id | StringUUID | 不可空 | |
| workflow_run_id | StringUUID | 不可空 | → workflow_runs.id |
| created_from | EnumText | 不可空 | `service-api|web-app|installed-app|openapi`（workflow.py:1290-1298） |
| created_by_role / created_by | | 不可空 | |
| created_at | DateTime | 不可空 | |

索引：pkey；`(tenant_id,app_id)`；`(workflow_run_id)`（workflow.py:1356-1360）。

### A-14. workflow_archive_logs（run 归档后的替代快照行；写入=SaaS 归档任务 create_archive_logs）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuidv7 | |
| tenant_id / app_id / workflow_id / workflow_run_id | StringUUID | 不可空 | |
| created_by_role / created_by | | 不可空 | 取自 run |
| log_id / log_created_at / log_created_from | | 可空 | 关联 app log（无 app log 的 run 为 NULL） |
| run_version / run_status / run_triggered_from | | 不可空 | run 快照 |
| run_error | LongText | 可空 | |
| run_elapsed_time | Float | 不可空/0 | |
| run_total_tokens | BigInteger | server_default 0 | |
| run_total_steps | Integer | 可空/0 | |
| run_created_at | DateTime | 不可空 | |
| run_finished_at | DateTime | 可空 | |
| run_exceptions_count | Integer | 可空/0 | |
| trigger_metadata | LongText | 可空 | 触发日志快照 |
| archived_at | DateTime | 不可空/current_timestamp | |

索引：pkey；`(tenant_id,app_id)`；`(workflow_run_id)`；`(run_created_at)`（workflow.py:1429-1435）。

### A-15. upload_files（上传文件登记表：实体在对象存储，本表存元数据+指针；也被节点 offload JSON 复用）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4（应用层生成，:2354-2360） | |
| tenant_id | StringUUID | 不可空 | |
| storage_type | EnumText(StorageType) | 不可空 | **13 值**：aliyun-oss/azure-blob/baidu-obs/clickzetta-volume/google-storage/huawei-obs/local/oci-storage/opendal/s3/tencent-cos/volcengine-tos/supabase（storage_type.py:4-17） |
| key | String(255) | 不可空 | 对象存储 key（`upload_files/{tenant_id}/{uuid}.{ext}`） |
| name | String(255) | 不可空 | 原始文件名 |
| size | Integer | 不可空 | 字节 |
| extension | String(255) | 不可空 | 扩展名 |
| mime_type | String(255) | 可空 | |
| created_by / created_by_role | | 不可空 | 按 role 指向 Account/EndUser（:2368-2372） |
| created_at | DateTime | 不可空 | |
| used / used_by / used_at | Boolean/StringUUID/DateTime | 可空 | 「是否被使用」维护不一致勿依赖（注释 :2375-2383） |
| hash | String(255) | 可空 | 内容哈希（本地布局 sha3_256） |
| source_url | LongText | default '' | 签名访问 URL |

索引：pkey；`(tenant_id)`（model.py:2349-2352）。

### A-16. message_annotations（问答标注：console 手工/CSV 导入/API 三路写入，annotation_service.py:139/153/302）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| app_id | StringUUID | 不可空 | |
| question / content | LongText | 不可空 | 标注问题/答案 |
| hit_count | Integer | 不可空/server_default 0 | 命中计数 |
| account_id | StringUUID | 不可空 | 创建者 |
| conversation_id | StringUUID | 可空, FK→conversations | 从会话标注回链 |
| message_id | StringUUID | 可空 | 从消息标注回链 |
| created_at / updated_at | DateTime | 不可空 | |

索引：pkey；`(app_id)`；`(conversation_id)`；`(message_id)`（model.py:1939-1944）。

### A-17. app_annotation_settings（app 级标注回复开关：阈值+向量集合绑定）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| app_id | StringUUID | 不可空 | 一 app 一行 |
| score_threshold | Float | 不可空/server_default 0 | 命中阈值（运行时 `or 1` 兜底默认 1.0） |
| collection_binding_id | StringUUID | 不可空 | → dataset_collection_bindings |
| created_user_id / updated_user_id | StringUUID | 不可空 | |
| created_at / updated_at | DateTime | 不可空 | |

索引：pkey；`(app_id)`（model.py:2021-2024）。

### A-18. app_annotation_hit_histories（标注命中流水：score + 标注快照）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| app_id / annotation_id / message_id / account_id | StringUUID | 不可空 | |
| source | LongText | 不可空 | 命中来源（api|console） |
| question | LongText | 不可空 | 命中时的用户问题 |
| score | Float | 不可空/0 | 相似度分 |
| annotation_question / annotation_content | LongText | 不可空 | **标注快照（防后续改写失真）** |
| created_at | DateTime | 不可空 | |

索引：pkey；`(app_id)`；`(account_id)`；`(annotation_id)`；`(message_id)`（model.py:1984-1990）。

### A-19. operation_logs（控制台操作审计——**当前版本无生产写入方**，全库 grep 仅 models 定义与清理任务引用，预留/遗留表）

| 列 | 类型 | 可空/默认 | 说明 |
|---|---|---|---|
| id | StringUUID PK | uuid4 | |
| tenant_id / account_id | StringUUID | 不可空 | 操作者 |
| action | String(255) | 不可空 | 动作名 |
| content | JSON | 可空 | 操作内容快照 |
| created_ip | String(255) | 不可空 | 来源 IP |
| created_at / updated_at | DateTime | 不可空 | |

索引：pkey；`(tenant_id,account_id,action)`（model.py:2079-2082）。
