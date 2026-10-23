# agentscope（Python 版）持久化深挖档案（介质全景 / DDL / 写入策略 / Java 对照 / 借鉴意义）

> agent-persistence 轮 profiles 第 5 篇。基线：~/develop/opensource/agentscope @ b82253ba（Python v2.0.8，2026-09-11）。框架轮档案见 `research/agent-framework/profiles/agentscope.md`（15 维评级），本文只做存储实现层下钻：介质全景、SQL DDL 全字段、AgentState 序列化/时机/并发、MessageBus/S3 边界、与 Java 版对照。记忆文件（AgenticMemoryMiddleware）细节引用 `dimensions/03-记忆存储.md` §6 不重复。抽查复核见 §9，全表字段明细见文末附录。

## 1. 持久化面全景

核心分层：**库层**（AgentState 可序列化，无自己的存储）+ **app 服务层**（Storage 持久 / MessageBus 传输，二者刻意解耦，`app/_app.py:131-137` docstring 明示「SQL 存储 + Redis 总线是常规生产形态」）。

| 介质 | 存什么 | 入口模块 | 持久性 |
|---|---|---|---|
| SQL（SQLite/PG/MySQL） | 11 张表：session（含全量 AgentState）、message、agent、credential、schedule、team、KB、KB 文档（含租约）、MCP、skill、channel | `app/storage/_sql/_storage.py:85`（AsyncSQLAlchemyStorage） | 持久 |
| Redis（storage 角色） | 同一组 record 的 KV 镜像（String 存 JSON + Set/Hash 索引），可选滑动 TTL | `app/storage/_redis_storage.py:44` | 持久（可设 TTL） |
| Redis（bus 角色） | 会话事件回放 Stream、inbox 队列、run 分布式锁、wakeup 队列、cancel 频道、BG task registry、channel 心跳 | `app/message_bus/_redis_message_bus.py:60`、key 表 `_keys.py:19` | 易失/活动态（回放 log cap 1000） |
| S3 / 本地 blob | KB 原始文档（key=`kb/{kb_id}/{doc_id}`） | `app/rag/blob_store/_s3.py:57`、`_local.py:27` | 持久 |
| 记忆文件 | `{workdir}/Memory/` topic md + `MEMORY.md` 索引 | `middleware/_longterm_memory/_agentic_memory/_middleware.py:359` | 持久（引用 dim 03 §6） |
| schedules 表 + APScheduler 内存 | cron 记录入表；jobstore 内存态，启动 `list_all_schedules` 重建（`_scheduler_manager.py:37-90`，:46 注释「每个节点都会触发」） | `app/_manager/_scheduler/` | 表持久 / 触发器易失 |
| workspace 目录 | `.mcp` 声明、`data/` 多模态 offload、`skills/` 分区、`sessions/` 会话 offload | `workspace/_base.py:36-59` | 持久 |
| 日志 | stderr（可选 FileHandler，无默认文件） | `_logging.py:15-40` | ❌ 默认不落盘 |

粒度总览：**无独立 checkpoint 概念**——执行状态 = sessions 行内嵌 AgentState 快照；消息 = messages 独立表（转录与状态分离双写）；HITL 挂起不建表，从 context 尾部 tool_call 状态推导（§3.4）。

## 2. SQL storage：DDL 与写路径

### 2.1 表设计统一模式【核心】【复核 ✔】

所有 record 表共享「**提升列 + payload JSON**」模式（`_sql/_tables.py:58-105`、`_sql/_mappers.py:1-27`）：`id` PK(String 255) + `created_at`/`updated_at`（DateTime，带索引）+ `payload`(JSON NOT NULL)；写时 `record.model_dump(mode="json")` 后把信封字段与 `_indexed_fields` 弹出到列、剩余进 payload，读时列并回 payload 走 `model_validate`（经 record 的 before-validator 兼容旧形状）。可移植性约束（`_tables.py:14-26`）：只用 plain JSON 不用 JSONB、无 generated column、无 `FOR UPDATE`。

### 2.2 alembic 迁移链（3 版）

| 版本 | 日期 | 内容 |
|---|---|---|
| `0001_initial` | 2026-07-20 | 9 表冻结快照——刻意不委托 `metadata.create_all`，防新库重复建表（`versions/0001_initial.py:8-15`） |
| `0002_mcps_skills` | 2026-08-01 | mcps + skills 两表，`(user_id,name)` UNIQUE（workspace 按 name join） |
| `0003_channels` | 2026-08-21 | channels 表，`platform_bot_id` 全局 UNIQUE；时间戳 MySQL 方言提精度 `DATETIME(fsp=6)`——`updated_at` 即配置版本，秒级会被同秒两次编辑撞掉（`0003:38-44`） |

启动供表：`create_tables=True`（默认，dev/测试）与 `auto_migrate=False`（默认；生产应作为独立部署步骤——:134-137 注释明说**多副本竞态不安全**）。SQLite 连接逐个开 `PRAGMA foreign_keys=ON`（:184-191）。

### 2.3 写路径【核心】

- **方言原生原子 upsert**：PG/SQLite `INSERT ... ON CONFLICT DO UPDATE`、MySQL `ON DUPLICATE KEY UPDATE`，Oracle/MSSQL 直接 NotImplementedError（`_storage.py:264-330`）；conflict 时只覆盖 `updated_at + payload + 提升列`，保留原 `created_at`。动机：把 insert-or-update 决策放进 DB，消灭 read-then-write 竞态窗口——但**这是 last-write-wins，不是 CAS**（无 version 刂参与）。
- **session 写**：`upsert_session`（存在则整 record 覆盖）；`update_session_state` 热路径 = GET 行 → 反序列化 → 换 state → 写回 payload（:1126-1145，read-modify-write，正确性靠 §3.3 的 run 锁）；`set_session_team_id` 单列 UPDATE。
- **message 写**：`upsert_message` = 复合键 `(session_id, msg_id)` 原子 upsert，同 id 替换 payload 保 created_at（:1518-1554）【复核 ✔】；`list_messages` 用 `(created_at, msg_id)` 全序做 keyset 分页（拼写开比较让所有方言可规划，:1610-1665）。Redis 版语义：LINDEX 尾部同 id 才 LSET 替换，否则 RPUSH（`_redis_storage.py:1434-1450`）。
- **级联删除**：公开方法单事务提交保证原子（:407-418）；session 删除清 messages；KB 文档靠 DB `ON DELETE CASCADE` 原生级联。
- **KB 文档租约（全库唯一真 CAS）**【复核 ✔】：acquire = 条件 UPDATE `WHERE processing_node IS NULL OR lease_expires_at < now`（:1934-1940），`rowcount>0` 即抢到；renew/release 限定 holder 匹配（:1947-2004）；sweeper 扫过期租约 + pending 孤儿（:2006-2049）。多节点 index worker 安全的根基。

## 3. AgentState：序列化、保存时机、并发、resume

### 3.1 字段全集（`state/_state.py:209-296`）

| 字段 | 类型 | 内容 |
|---|---|---|
| session_id | str | 默认 `_generate_id` |
| summary | str \| list[TextBlock/DataBlock] | 压缩摘要（注入 context 头部） |
| context | list[Msg] | 未压缩完整对话 |
| reply_context | ReplyContext(:182-206) | reply_id / cur_iter / structured_schema（序列化为 JSON Schema dict）/ structured_output |
| permission_context | PermissionContext | 权限模式与累积决议 |
| tool_context | ToolContext(:32-44) | read_file_cache（LRU：100 文件/25000KB，**缓存整文件行内容——state 体积大户**）+ activated_groups |
| tasks_context | TaskContext(:175-179) | Task 列表（subject/state/blocks/blocked_by） |
| middle_context | dict[str,Any] | 中间件跨 reply 存取（任意 JSON） |

旧格式迁移 validator：顶层 `reply_id`/`cur_iter` 折进 `reply_context`（:226-241）。

### 3.2 序列化格式与保存时机【核心】

- Msg 序列化 = pydantic `model_dump(mode="json")`（`_storage.py:1534`）；Msg 字段：name/content(block 列表)/role/id/metadata/created_at/**usage(4 类 token)**/finished_at/finished_reason/structured_output/error（`message/_base.py:71-118`）。SessionRecord = `user_id/agent_id/origin(tagged union)/team_id/config(模型、workspace、KB 绑定)/state`，整体进 sessions.payload 单列。
- **保存时机 = 每 reply 结束，不是每工具调用**：`_chat.py:1411-1460` `_persist()`——逐个 `upsert_message(reply_msgs)` → `update_session_state(agent.state)` 全量；整个协程 `asyncio.shield` 抗取消，且**必须在释放 session 锁前完成**（:1406-1410 注释：否则下一个 worker 会读到陈旧 state）。用户输入消息在 reply 开始前先落库（:1208-1213）。**全量快照、无增量、无历史版本（只有最新一版，无 time-travel）**。
- 兼容策略三件套：AgentState before-validator、SessionRecord `_fold_legacy_source`（旧平铺 source_* 折成 origin，落库即新形状）、payload 单列 JSON。

### 3.3 并发控制：锁在总线，不在存储

存储层无锁无版本；**串行化靠 MessageBus 分布式 run 锁**：`SET key token NX EX 600` 抢锁 → 每 ttl/2 心跳 `EXPIRE` 续期 → 释放时 GET 比对 token 再 DEL（防误删他人锁；`_redis_message_bus.py:627-700`）【复核 ✔】。chat run 全程 `async with acquire_lock(session_lock)`（`_chat.py:783-786`），record 只在持锁后加载。InMemory 版退化为 `asyncio.Lock`——单进程语义同构。

### 3.4 resume 读路径（对应 Java resumeAgent）

1. run 在锁内 `get_session` → `Agent(state=session_record.state)`（`_chat.py:817-829`）；
2. HITL/外执恢复走 **Case B continuation**：按 `state.reply_id` 从 messages 表取回持久化 reply msg → `append_event(Result事件)` → `agent.reply_stream(inputs=event)`（:1253-1337）；恢复入口是总线 wakeup 队列 `WAKEUP_KIND_RESUME` 条目（session 运行中则 re-queue 直到锁释放）；
3. **parked 状态不入库**：`derive_parked_status` 从 context 尾 assistant 消息的 tool_call.state（ASKING→AWAITING_PERMISSION，SUBMITTED 无结果→AWAITING_EXTERNAL_RESULT）反推四态枚举（`_service/_session.py:92-95, 211-250`）；RUNNING 优先查 run 锁（worker 崩溃后租约到期自动翻出 RUNNING）。

## 4. MessageBus 与 S3 blob

### 4.1 MessageBus：传输 vs 持久化的边界

基类 5 类原语（`message_bus/_base.py:53`）：queue / log / pub-sub / lock / registry。Redis 实现：queue 与 log 都是 **Stream**，区别在 drain 语义——queue 用 Lua 脚本原子 `XRANGE+XDEL`，log 用 `XADD MAXLEN ~N` 封顶 + `XRANGE` 游标读 + `XTRIM MINID`；pub/sub 原生；registry 用 Hash。

业务 key 全表（`_keys.py`）：

| key | 类型/参数 | 用途 |
|---|---|---|
| `agentscope:session:events:{sid}` | Stream，cap 1000 | 会话事件回放 log + 实时 pub/sub 双用 |
| `agentscope:session:lock:{sid}` | String NX EX 600 | chat run 分布式锁 |
| `agentscope:inbox:{sid}` + `inbox:lock`(30s) + `inbox:consumer` | Stream + lock + Hash | 跨 session 投递收件箱与消费登记 |
| `agentscope:wakeups` / `wakeup_signal` | Stream / pubsub | run 触发队列（wake/resume/message 三种 kind） |
| `session:cancel` / `task:cancel` / `session:interrupt` | pubsub | 跨进程取消/中断广播 |
| `agentscope:bg_tasks:{sid}` | Hash，TTL 24h | 后台任务登记 |
| `agentscope:index:tasks` + `:wake` | Stream + pubsub | KB 索引任务队列（离线 worker 消费） |
| `schedule:lifecycle` / `channel:lifecycle` / `channel:liveness:{cid}` 等 | pubsub/Hash | 调度与渠道协调态 |
| `agentscope:session:projection:{sid}` | Hash | 跨会话 UI 卡片投影（子 agent HITL 投影到 leader） |

边界结论：bus 只承载**可丢失/可重建的活动态**（回放 log 是断线重连的 1000 条缓冲，非审计）；一切要跨重启的都在 storage。持久（SQL）+ 传输（Redis 总线）可独立选型。

### 4.2 S3 / Local blob store

`BlobStoreBase`：`write_stream(key)`/`open(uri)`/`delete`/`size`/`exists`。唯一写入方 = KB 文档上传，key 硬编码 `kb/{kb_id}/{doc_id}`，记录写库失败即删 blob 防孤儿（`_service/_knowledge_base.py:432-436`）。Local 版 `local://{key}`、拒绝 `..` 逃逸；S3 版 aioboto3。**不存沙箱快照/执行状态**（对比 Java 版 `snapshot:` 前缀）。

## 5. 记忆文件布局（引用 dim 03 §6，不重复）

AgenticMemoryMiddleware：`{workdir}/Memory/` + `MEMORY.md` 索引（`memory_max_tokens=4000` 截断注入）+ topic 文件（frontmatter 3 字段）+ LLM 选择器检索（manifest→≤5 文件）+ grep 兜底；Mem0（托管向量库+SQLite 历史）/ReMe（内嵌服务）介质差异见 `dimensions/03-记忆存储.md` §6。

## 6. 目录布局与配置

- workspace 标准布局（`workspace/_base.py:36-59`）：`{workdir}/.mcp`（仅偏离 default 时落盘）+ `data/`（图片等 offload）+ `skills/`（`.seed` 模板 + per-agent 分区）+ `sessions/`（每会话 offload 文件）。
- 日志默认仅 stderr；观测走 OTel 不落本地。无全局配置文件——一切经 `create_app` 注入。

## 7. 与 agentscope-java 对照（Java 结论见 dimensions/02 §5）

| 维度 | Python @b82253ba | Java（extensions-jdbc/redis） |
|---|---|---|
| 行键 | sessions 单行整 payload；messages 复合 PK | `(session_id, state_key, item_index)` 三列 PK，**列表一元素一行** + hash 辅助键 |
| 并发控制 | 无 version 列；方言 upsert last-write-wins + 总线 run 锁 + KB 租约条件 UPDATE | **SQL 级 CAS**（`WHERE version=?`），readVersion 不反序列化 payload |
| 增量 | 全量快照（每 reply 重写整个 state） | 列表 hash 比对，未变只追加尾部增量行 |
| 分布式锁 | Redis 总线锁（token+heartbeat+compare-DEL） | `agentscope_distributed_locks` 表 + 退避；Redis `guard:` 沙箱锁 |
| 后端矩阵 | SQL（3 方言）+ Redis + S3/local blob | JDBC 4 方言 + Redis×2 + mongo + oss + cos + JPA 等 8+ |
| 迁移 | alembic 3 版链 + create_all 双轨 | 无 alembic（CREATE TABLE IF NOT EXISTS） |
| HITL 恢复 | wakeup 队列 resume + Case B continuation + parked 从 context 推导（零额外存储） | resumeAgent 显式 API |
| 传输层 | **MessageBus 独立抽象**（事件回放/inbox/wakeup/cancel/projection），Java 无对应物 | — |
| 独有 | 消息 keyset 分页、KB 文档租约+sweeper、channel 表微秒版本戳 | workspace 文件 KV（`store:`）、沙箱快照（`snapshot:`） |

一句话：**Java 把成熟度花在存储层（CAS/增量/锁表），Python 把成熟度花在服务层（总线/调度/渠道/KB 管道）**；两侧对「执行状态本体」的答案一致——都是 JSON 全量可序列化快照。

## 8. 借鉴意义（面向企业级分布式服务端 + Web）

**照搬清单**：
1. 提升列 + payload JSON 的 record 表模式——索引字段可查询、payload 承载演进，schema 变更大多免迁移。
2. 复合 PK `(session_id, msg_id)` 消息表 + `(created_at, msg_id)` 全序 keyset 分页。
3. KB 文档租约：状态/租约字段提升为列 + 复合索引 + 条件 UPDATE CAS + 过期 sweeper——多节点后台 worker 的教科书方案。
4. run 锁三件套：NX+token、ttl/2 心跳、compare-and-DEL 释放；「**先落库后放锁**」+ `asyncio.shield` 的收尾纪律。
5. alembic 初始迁移冻结快照（不委托 metadata），`auto_migrate` 默认关并注明多副本竞态。
6. park 状态零存储设计：从持久化 context 尾部 tool_call 状态推导四态。

**改造清单**：
1. `update_session_state` 的 read-modify-write → 借 Java 加 version 列 CAS；目前正确性完全押在 run 锁上，跨服务旁路写（运营改 session）无保护。
2. 事件回放 log（bus 上 cap 1000）是活动缓冲非审计——企业审计/成本台账应另建持久 append 表（usage 已在 Msg.usage，只差聚合落库）。
3. `tool_context.read_file_cache` 缓存整文件内容随 state 全量重写——大会话每 reply 重写整个 payload，可剥离到旁表。
4. channels 的「updated_at=版本戳」隐式约定 → 显式 version 列更稳。
5. `create_all` 与 alembic 双轨并存，dev 库会绕过迁移链——统一走 alembic。

**补缺清单**：
1. 无任何 checkpoint 历史/time-travel（仅最新快照；出错即覆盖）——对照 langgraph checkpoint 链、dify pauses。
2. 无 tenant/billing/配额维度（user_id 单层）。
3. 无大 payload offload 机制（对照 dify offload 表 + 对象存储指针）。
4. 沙箱快照/workspace 文件 KV 持久化缺位（Java `snapshot:`/`store:` 有），Python 沙箱会话迁移能力弱一档。
5. 多副本安全迁移（init 容器/Job 化）需自建。

## 9. 抽查复核记录（2026-09-22）

6 条载荷最重证据全部命中：提升列+payload 模式（`_mappers.py:8-18` docstring 明述）、KB 租约条件 UPDATE（`_storage.py:1934-1940` `lease_expires_at.is_(None)/< now`）、run 锁 TTL 体系（`_redis_message_bus.py` ttl_secs/expire 体系）、messages 复合 PK（`_tables.py:404-409` 设计注释原文）、保存时机每 reply（`_chat.py:1411-1460`）、方言原生 upsert 分流（`_storage.py:264-330`）。

---

## 附录：每表用途 + 全字段明细

以下均出自 `app/storage/_sql/_tables.py`（迁移原文 `versions/0001-0003`）。信封三列所有 record 表共享：`id` String(255) PK、`created_at` DateTime NOT NULL 单列索引、`updated_at` 同；`payload` JSON NOT NULL。

| 表 | 迁移 | 用途 | 写入方 | 提升列（indexed fields） | 特殊约束 |
|---|---|---|---|---|---|
| agents | 0001 | 注册的 agent 实体/配置 | upsert_agent | user_id、source（均索引） | 复合 `ix_agents_user_source` |
| credentials | 0001 | 用户凭证记录 | credential 服务 | user_id（索引） | payload 含类型与密文数据 |
| **sessions** | 0001 | **核心表：会话配置 + 全量 AgentState** | upsert_session / update_session_state | user_id/agent_id/source(16)/team_id?/source_schedule_id?（各带索引）+ 复合 `ix_sessions_user_agent` | `_index_paths` 从嵌套 `origin.type`/`origin.schedule_id` 喂列（`:185-188`，列名不变免迁移）；payload = config + state 全量 JSON |
| **messages** | 0001 | 会话转录（一 Msg 一行） | upsert_message | — | **复合 PK (session_id, msg_id)**；`ix_messages_session_created(session_id,created_at)`；设计注释 `:399-411`：Msg.id 仅会话内唯一，复合键让「同 (session,msg_id)→替换」由 DB 强制【复核 ✔】 |
| schedules | 0001 | cron 任务 | scheduler manager | user_id、agent_id | payload 含 cron 表达式/prompt/激活态 |
| teams | 0001 | team 记录 | team 服务 | user_id（索引）、session_id（leader 会话，无索引） | payload 含 roster |
| knowledge_bases | 0001 | KB 元数据 | KB 服务 | user_id（索引） | payload 含 embedding 模型配置（维度钉死）、collection_name |
| knowledge_documents | 0001 | KB 文档 + **索引租约**（唯一带外键的表） | acquire/renew/release + sweeper | user_id、knowledge_base_id（**FK→knowledge_bases.id ON DELETE CASCADE**）、processing_node(128, nullable, 无索引)、status(16, 索引)、lease_expires_at(nullable) | 复合 `ix_kd_status_lease(status,lease_expires_at)`（sweep 专用）+ `ix_kd_user_kb`；设计注释 `:242-253`：提升列让 sweeper **不反序列化 payload** 即可过滤 |
| mcps / skills | 0002 | 用户安装的 MCP/技能库 | workspace 同步 | user_id（索引）、name(255) | **UNIQUE (user_id,name)**（workspace 按 name join，重名即错误而非覆盖） |
| channels | 0003 | 钉钉/飞书/Discord 渠道绑定 | channel 服务 | user_id（索引）、platform_bot_id(255) | **全局 UNIQUE**（`uq_channels_bot`）；created_at/updated_at 覆写为 MySQL `DATETIME(fsp=6)` 微秒精度（updated_at 兼作配置版本戳，`:359-380`） |
