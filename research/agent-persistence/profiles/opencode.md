# opencode 存储层深挖档案（表设计 / 写入策略 / 生命周期 / 借鉴意义）

> agent-persistence 轮补充深挖（单对象）。基线：~/develop/opensource/opencode @ 95daf90670（与两轮记录一致）。方法：三路并行源码深挖（DB schema 与写入策略 / 文件层与目录布局 / 生命周期与多租户）+ 8 条载荷证据抽查复核 + 本机生产 DB 只读比对 + general subagent 独立审核（§13/§14）。上游：`agent-oss/profiles/opencode.md`（模式级结论）、本轮 `dimensions/04/06`（跨仓对照；01/02 未含 opencode）。本文补齐它们之下的实现层，并修正旧档案两处结论（§12）。
> **比对前提**：本机运行版本比克隆基线新（存在 `opencode.db.after-crash.db` 崩溃恢复重命名副本，基线源码无此机制）——本机 DB 证据的 DDL 层与基线一致（已逐表比对），行为级细节可能领先基线。
>
> **一句话总评**：opencode 的存储 = **进程级全局单库 SQLite（WAL + 单连接信号量串行）+ 事件溯源双轨（durable 事件 + 事务内联投影）+ 五类文件旁路（git 对象/工具输出/密钥/进程协调/缓存）**。它是「事件溯源 + 规范化投影」混合形态的最完整单机实现：事件表是同步与审计通道，投影表是权威读模型，两者同事务原子提交。

## 1. 存储介质全景

| 介质 | 内容 | 声明位置 |
|---|---|---|
| SQLite 单库 | 会话/消息/part/事件/输入/纪元/todo/授权/凭据/账号/项目 19 张表 | `core/src/database/database.ts` |
| git 对象库（影子仓） | 文件快照（revert/unrevert 的物理基础） | `opencode/src/snapshot/index.ts` |
| 平面文件 | 工具输出全文、auth.json×2、daemon password、日志、plan 产物 | `core/src/tool-output-store.ts` 等 |
| 纯内存（不持久化） | 待审单 pending Map、background-job、非 durable 事件（token delta）、执行态协调器 | 见 §10 |
| 远端（可选） | opncd.ai/enterprise 分享云（S3/R2 对象存储 JSON） | `enterprise/src/core/storage.ts` |

## 2. 磁盘目录布局

`core/src/global.ts:10-43`：XDG 四目录（data/config/cache/state）+ tmp，模块加载时同步 mkdir。projectID 语义 = **仓库身份而非路径身份**（git remote URL 哈希 → commonDirectory 缓存 → 根 commit → 目录名；`core/src/project.ts:73-122`），仓库搬家 ID 不变。

| 目录 | 子项 | 内容 | 证据 |
|---|---|---|---|
| **data** | `opencode.db`(+wal/shm) | 主库；按安装渠道分库 `opencode-<channel>.db`；`OPENCODE_DB` 可覆盖（支持 :memory:） | database.ts:43-57 |
| | `auth.json` / `mcp-auth.json` | provider / MCP OAuth 凭据（0600；mcp 版带 flock） | opencode/src/auth/index.ts:10；mcp/auth.ts:37 |
| | `storage/` | v1 JSON 活化石（现役仅 `session_diff/*.json` + 迁移水位文件） | opencode/src/storage/storage.ts:224 |
| | `tool-output/tool_<id>` | 超限工具输出全文（2000 行/50KB 双限，7 天 TTL 每小时清理） | core/src/tool-output-store.ts:17,129 |
| | `snapshot/<projectID>/<sha1(worktree)>/` | 影子 git 仓（文件快照） | snapshot/index.ts:71 |
| | `worktree/` `repos/` `plans/` `log/` | git worktree / 引用仓库浅克隆 / plan 产物（非 git 项目）/ 日志+heap 快照 | worktree/index.ts:208 等 |
| **config** | `opencode.json[c]` 三叠加 / `plugin/` / `themes/` | 全局配置（legacy TOML 自动转 JSON 删除） | opencode/src/config/config.ts:140-290 |
| **cache** | `bin/`（rg、LSP 二进制）、`models.json`（5min TTL）、`skills/` | 可弃缓存 | ripgrep/binary.ts:56 等 |
| **state** | `server.json`（daemon 注册）、`password`（0600+tmp/rename）、`model.json`、`locks/<sha1>.lock` | 进程协调与易失状态 | cli/src/services/daemon.ts:40-58；util/flock.ts |

配置合并顺序（后者胜）：远程 well-known → 全局（config.json→opencode.json→jsonc）→ OPENCODE_CONFIG → 项目级（worktree 根向目录浅→深）→ .opencode 目录族（config/config.ts:328-479）。

## 3. SQLite 打开参数与连接模型【抽查复核 ✔】

```
PRAGMA journal_mode=WAL; synchronous=NORMAL; busy_timeout=5000;
cache_size=-64000(64MB); foreign_keys=ON; wal_checkpoint(PASSIVE)（开库即做一次）
```
（database.ts:27-33，复核命中）。**单连接 + Semaphore(1) 串行**：native 连接唯一，普通语句经信号量排队，无连接池（sqlite.bun.ts:121、sqlite.node.ts:115）。事务经 effect-drizzle 桥：无外层事务 `BEGIN deferred`，嵌套自动降级 **SAVEPOINT**（BEGIN/savepoint 分岔在 `packages/effect-drizzle-sqlite/src/effect-sqlite/session.ts:145` 起，savepoint 逻辑 :145-172）；事务期间独占唯一连接（连接占用 sqlite.bun.ts:123-130）。**这是用「全局串行化」换并发正确性的激进选择**——单机成立，多副本不成立（借鉴意义 §11）。

## 4. 全部 19 张表目录（schema.gen.ts 生成的 SQL DDL，:8-238；逐表逐字段明细见文末附录 A/B）

| 表 | 用途 | 写入方 | 关键约束 |
|---|---|---|---|
| `event` | durable 事件流（溯源/同步/审计通道） | `event.ts#commitDurableEvent` | UNIQUE(aggregate_id,seq) + INDEX(aggregate_id,type,seq)；FK→event_sequence CASCADE |
| `event_sequence` | 每聚合 seq 单调序列 + **owner_id**（同步所有权） | 同上；`claim()` 交接 | PK(aggregate_id) |
| `session` | 会话主表（成本/revert/权限快照/分享） | projector | FK project_id CASCADE；parent_id 子会话树 |
| `message` / `part` | v1 消息/part 投影（data JSON 列） | projector upsert | FK 级联；part.session_id 冗余无 FK |
| `session_message` | **v2 事件化消息投影**（seq 对齐事件流） | projector insert/update | UNIQUE(session_id,seq) + 3 索引 |
| `session_input` | 输入收件箱（admitted→promoted 两阶段） | projector | UNIQUE(session_id,admitted_seq) + UNIQUE(session_id,promoted_seq)（NULL 不冲突） |
| `session_context_epoch` | 系统上下文纪元（baseline/snapshot/baseline_seq） | context-epoch.ts | PK(session_id)，整行替换 |
| `todo` | 任务板 | todo.ts 整板 DELETE+INSERT | PK(session_id,position) |
| `permission` | 持久授权（always） | permission/saved.ts | UNIQUE(project_id,action,resource)，add onConflictDoNothing |
| `session_share` | 分享元数据 | share-next.ts | PK(session_id) |
| `project` / `project_directory` | 项目注册表 / 项目↔目录多对多 | session.ts / project/directories.ts | (project_id,directory) 复合 PK，type=main/root/git_worktree |
| `workspace` | 工作区（分支维度，会话归组） | control-plane/workspace.ts | FK project CASCADE |
| `credential` | integration 凭据（API key/OAuth） | credential.ts（先 DELETE 同 integration 再 INSERT 单事务） | **value JSON 明文，无加密** |
| `account` / `account_state` / `control_account` | 控制面账号 / 活跃指针 / legacy | account/repo.ts | token 明文列 |
| `data_migration` | 数据搬迁水位（**建表但无写入方，预留**） | — | — |
| `migration`（运行时建） | schema 迁移日志 | migration.ts | — |

要点：**没有** blob/background_job/installation/stats 表——大对象走文件（tool-output-store）、后台任务纯内存（§10）、遥测不落盘。

## 5. 事件溯源机制（本文最核心一节）

### 5.1 durable 判定：哪些事件入库

`schema/src/durable-event-manifest.ts`：v1 durable 7 种（session.created/updated/deleted、message.updated/removed、message.part.updated/removed）+ v2 durable 28 种（agent/model.switched、moved、prompted、prompt.admitted、context.updated、step.started/ended/failed、text.started/ended、tool.input.started/ended、tool.called/progress/success/failed、reasoning.started/ended、shell.started/ended、synthetic、retried、compaction.started/ended、revert.staged/cleared/committed）。**delta 类（text.delta/tool.input.delta/compaction.delta）与 todo.updated、permission.v2.* 不入 durable**——流式 token 增量不落库，审批事件只走 PubSub/SSE（dimensions/04 已点名的审计缺口）。

### 5.2 seq 分配与事务（单事件单事务）【抽查复核 ✔】

`commitDurableEvent`（event.ts:205-367）在 `BEGIN IMMEDIATE` 事务内顺序执行：

```
1. SELECT seq, owner_id FROM event_sequence WHERE aggregate_id=?   -- 读 latest（缺省 -1）
2. replay 场景三重校验：owner 匹配 / 同 id 同内容幂等吞 / seq 必须恰好 latest+1（:262-315）
3. seq = latest + 1
4. projector 先执行（投影表与事件同事务原子，:320-322）+ options.commit hook（:323）
5. INSERT INTO event_sequence ... ON CONFLICT(aggregate_id) DO UPDATE SET seq=<新seq>（drizzle onConflictDoUpdate set {seq, ...owner 条件}，:324-335）
6. INSERT INTO event(id, aggregate_id, seq, versionedType, data)（:336-348）
```

type 存带版本后缀字符串（**点号连接**：`versionedType = \`${type}.${version}\``，schema/src/event.ts:94，如 `session.next.step.started.2`；本机 DB 实测 `session.updated.1`）——**事件 schema 版本化进存储**。`IMMEDIATE` 立即取写锁防并发 seq 竞争；配合进程内 Semaphore(1) 实际完全串行。

### 5.3 projector 事务内联：事件与投影原子

projectors（`events.project` 注册）在**事件 INSERT 之前、同一事务内**执行——投影器崩溃不留脏投影、不留无投影事件。`options.commit(seq)` 是其通用化：context-epoch 用它把快照推进与 ContextUpdated 事件绑成原子（context-epoch.ts:72-76）。**这是整个设计里最值得照抄的一条**。

### 5.4 发布顺序保证

先落库（含投影）→ 提交 → 唤醒 durable wake → notify listeners/typed/all（event.ts:354-417）。**订阅者见到的 durable 事件必然已提交**；非 durable 事件直接 notify（纯内存）。

### 5.5 多端同步协议（sync 单写入者）

`event_sequence.owner_id` 记聚合所有权；远端 workspace SSE 长连 + `syncHistory` 差量（本地各聚合 seq 快照 POST，对端返回差量事件）→ `events.replay({publish:true, ownerID})` 严格序号校验重放（event.ts:441-512）；会话迁移 `/sync/steal` 交接所有权。**replay 的三重校验是「多写者收敛到单写者」的完整协议样本**。

## 6. 写入策略详解

### 6.1 消息/part：流式逐事件即时写，upsert 同一行

每个状态变化（pending→running→输出→completed）都 publish 一次 durable `message.part.updated`（opencode/src/session/session.ts#updatePart:635 及 processor.ts ~20 处调用点），**每次一个独立事务**（事件+投影原子）。part 落库 = `INSERT ... ON CONFLICT(id) DO UPDATE SET data=...`（projector.ts:317-322）——同一 part 行原地更新，`time_updated` 由 drizzle `$onUpdate` 自动刷。崩溃恢复粒度 = 单 part 状态。

### 6.2 成本列：每 step 增量结算

`PartUpdated` 投影识别 `part.type==="step-finish"`（带 cost/tokens），**先减旧行值再加新行值**的原子 SQL 自增：`SET cost = cost + ?, tokens_input = tokens_input + ? ...`（projector.ts#applyUsage:89-109）；消息/part 删除时反向减（sign=-1）。非轮末汇总——每 step 一次。

### 6.3 双轨投影（迁移过渡态）

同一事件流两套投影并行写：v1 `message`/`part`（旧 REST 读模型，message-v2.ts#hydrate）+ v2 `session_message`（seq 对齐事件流，runner 上下文装配读它，session/history.ts）。开发期迁移 `20260622170816_reset_v2_session_state` 曾整清**六表**（event/event_sequence/session_message/session_input/session_context_epoch/workspace）并置空 session.workspace_id——**连事件流本体也一并清**，事件溯源在开发期「不保真」的真实代价样本。

### 6.4 迁移机制

自研 TS 迁移数组（38 个 migration/*.ts，静态 import 清单）替代 drizzle journal；空库 → 单事务跑全量 DDL + 全部标记完成（不重放历史）；已有库 → `applyOnly` 增量 + 接管旧 `__drizzle_migrations`（时间戳前缀匹配，对不上 die）；每迁移独立事务原子（migration.ts:18-106）。v1 JSON 文件自迁移是另一条线（惰性、水位文件、失败逐条重试，storage.ts:213-243），与 DB 无关。

### 6.5 删除与维护

会话删除：递归子会话 → `session.deleted` 事件 → projector DELETE session 行（FK CASCADE 波及全部附属表）→ `events.remove(sessionID)` 显式双删 event_sequence+event（否则事件成孤儿）。**维护任务：无**——全仓无 VACUUM/optimize/GC 定时任务，唯一空间回收是开库 wal_checkpoint + SQLite 默认 autocheckpoint；snapshot 影子仓有 `git gc --prune=7.days`（每小时）但那是 git 侧。

## 7. 会话生命周期时序

- **创建即落库（非懒建行）**：`POST /api/session` → `create()` 发 durable `Session.Created` 事件，session 行在事件事务内 INSERT（core/src/session.ts:208-262；projector.ts:214-233）。TUI 交互层「首次提交才 create」只是客户端行为。
- **resume = 即续，重启零加载**：启动只做 open+PRAGMA+migration，无会话预热；读直接打 SQLite 无缓存层（session/store.ts:35-58）。对既有 sessionID 再发 prompt 即恢复。历史读取一次 `SELECT ... ORDER BY seq ASC`（条件 `seq >= 最新 compaction.seq` 且 system 类须 `seq > baseline_seq`，session/history.ts:24-53）。
- **崩溃自愈**：每次 `runner.run` 入口 `failInterruptedTools`——把上一进程遗留的 pending/running tool part 补发 `Tool.Failed` 事件让投影自愈（runner/llm.ts:119-139）；执行态（协调器/active set）纯内存，重启即丢靠 wake 重建。
- **revert 三步**（存储层视角）：`stage` = 影子 git 快照（内容寻址 tree hash，幂等）→ 回滚文件 → `RevertEvent.Staged` → projector 写 `session.revert` 列（messageID+snapshot+diff）；`clear` = 从原快照 restore 撤销回滚 → revert 列置 NULL；`commit`（projector.ts:413-451）= 定位边界 seq → `DELETE session_message WHERE seq > 边界` → `DELETE session_input WHERE admitted/promoted_seq > 边界` → revert=NULL。**⚠️ event 表不删**——事件流保留完整历史但投影已删，且 projector 无启动重放机制：**事件流与投影会分歧，重放≠重建投影**。这是「投影即权威读模型、事件流退化为同步/审计通道」的现实定位（借鉴意义 §11.3）。
- **输入收件箱（session_input）**：admitted_seq = PromptAdmitted 事件 seq（与事件同事务 INSERT）；promoted_seq = 被提升为正式 prompt 时的 Prompted 事件 seq（UPDATE WHERE promoted_seq IS NULL）。delivery=steer（运行中插话，并入当前 turn）/queue（turn 间逐条消费）。**排队输入崩溃不丢**——已在库，重启 `hasPending` 驱动续跑。
- **上下文纪元（session_context_epoch）**：baseline（agent system+skills 合成文本）+ snapshot（结构化）+ baseline_seq（基线确立时聚合 seq）。配置漂移 → reconcile → ReplacementReady 则换基线+新 seq；读侧用 baseline_seq 过滤旧基线的 system 消息。**「系统提示的版本纪元」是会话持久化里少见的精细设计**。

## 8. 事件 fanout 与恢复

- 全局 `GET /api/event`：`allBounded(256)` dropping 队列 + 15s 心跳，**不从 DB 重放、无 last-event-id**——断线即丢，客户端靠会话级接口补。
- 会话级 `GET /api/session/:id/event?after=N`：`events.durable({aggregateID, after})` = **先读 event 表历史（seq>after）再拼 live 流**——after 即 last-event-id 等价物，断点续传只做了会话粒度。
- 修正旧档案：WebSocketTracker 是 graceful-shutdown 连接注册表（关停时 1s 强关），**不是事件通道**。

## 9. 文件类存储三件深挖

### 9.1 snapshot 影子 git（文件快照的工程化解法）

gitdir = `data/snapshot/<projectID>/<sha1(worktree)>`，`--git-dir --work-tree` 旁路不污染用户仓。**seed 优化**（snapshot/index.ts:198-233）：把用户仓 objects 写进影子仓 `objects/info/alternates` 共享对象库 + 复制用户仓 index——chromium 级仓库首次快照从分钟级降到秒级【抽查复核 ✔】。track 存 **tree 不 commit**：diff-files + ls-files --others → 复用用户仓 check-ignore 规则 → >2MB 未跟踪文件进 exclude → `add --sparse` → `write-tree`。blob 内容寻址天然增量去重。revert 按消息时间序展平、每文件取最早快照、批量 checkout ≤100；restore = read-tree + checkout-index 整仓恢复（unrevert 用）。gc --prune=7.days 每小时。

### 9.2 附件图片：base64 内联（反面对照）

FilePart.url = data URL；photon WASM 缩放（≤2000×2000、base64 ≤5MB，逐级 ×0.75 + PNG/JPEG 质量梯度，image/image.ts:96-151）。**5MB 级 base64 直接进 part 行进上下文，无 offload**——与 tool-output 的落盘指针策略形成同一代码库内的对照实验。企业场景勿学此路（见 §11.2）。

### 9.3 凭据：明文 + 文件权限兜底

credential 表 value 为 JSON 明文（无加密/keychain，credential/sql.ts + credential.ts:101-119；account token 同）；auth.json/mcp-auth.json 0600 + mcp 版 flock；daemon password 唯一 tmp+rename。**凭据安全完全依赖 OS 文件权限**——单机可接受，服务端不可（§11.2）。

## 10. 刻意不持久化的东西（同样值得记录）

| 件 | 处理 | 后果 |
|---|---|---|
| 待审单 pending | location 级内存 Map + Deferred；实例关闭 finalizer 全置拒 | 重启丢审批单（dimensions/04 B6 已点名） |
| background-job | 纯内存注册表，注释明示 "intentionally not durable"【抽查复核 ✔】 | 重启丢运行中后台任务状态 |
| 非 durable 事件（token delta、todo.updated、permission.v2.*） | 只走 PubSub/SSE | 全局 SSE dropping 队列断线即丢 |
| 执行态（RunCoordinator/active set） | 纯内存 | 重启靠 failInterruptedTools 自愈投影 |

## 11. 对「企业级 agent / 分布式服务端 / Web 客户端」的借鉴意义

### 11.1 照搬清单（逻辑层，与介质无关）

1. **★事件表三件套 DDL**：`event(aggregate_id, seq, type带版本后缀, data)` + UNIQUE(aggregate_id,seq) + 每聚合序列表——审计/同步/补发三用。type 的 `.version` 点号后缀（schema/src/event.ts:94）是 schema 演进不破坏旧流的现成方案。
2. **★projector 事务内联**（事件 INSERT 前同事务执行投影 + commit hook）：事件与读模型原子，崩溃零脏数据。JPA 里 = 同一 @Transactional 内先写投影表再插事件行。
3. **★durable manifest 显式清单**：28+7 种入库、delta/todo/permission 不入——「什么值得持久化」是声明而非约定，新事件类型必须显式决策。
4. **★session_input 两阶段收件箱**（admitted_seq/promoted_seq 双唯一索引 + steer/queue 语义）：用户排队输入崩溃不丢，Web 多端发消息天然支持。
5. **★成本列增量结算**（step-finish 先减旧再加新、删除反向减）：会话主表实时成本，无需聚合查询。
6. **★session_context_epoch 纪元**：系统提示基线版本化，旧基线消息按 baseline_seq 过滤——多轮升级 system prompt 后历史不污染。
7. **★revert 三步状态机**（stage 快照→人工确认→commit 删投影；revert 状态列存 JSON）：草稿/冲正的完整状态机样本。
8. **★崩溃自愈模式**：runner 入口把遗留 pending tool 补发 Failed 事件——投影自愈比启动重放轻量得多。
9. **★seq 分配的三重校验**（owner/幂等/恰好+1）：多实例同步收敛协议，配 event_sequence.owner_id 所有权交接。
10. **snapshot alternates seed**（如果做文件快照类功能）：共享对象库 + 复制 index，大规模仓库快照秒级。

### 11.2 必须改造清单（单机→分布式的断层）

| opencode 现状 | 断层 | 企业改造 |
|---|---|---|
| 单连接 Semaphore(1) 全局串行 | 多副本失效 | PG MVCC；seq 分配改 `SELECT ... FOR UPDATE` / per-aggregate advisory lock / 保留 event_sequence 行锁模式 |
| SQLite WAL + 无 GC | 无保留策略、无 VACUUM | PG 分区/归档 + 保留期任务（会话/事件按 tenant+time） |
| credential/token 明文 | 服务端不可接受 | vault/KMS + 引用键（dimensions/04 谱系右端） |
| 图片 base64 内联 part | DB 膨胀、上下文浪费 | artifact 表 + 对象存储 + part 持引用（dimensions/06 P15） |
| 全局 SSE dropping 队列、无全局 last-event-id | Web 断线丢事件 | 全局事件接口补 after= 游标从库重放（它自己会话级已做，全局没做） |
| project_id 单层隔离 | 无租户维度 | tenant_id 全局维度 + 行级权限或分 schema |
| background-job 内存 | 重启丢 | 持久表（对齐 crewAI/dify 先例） |

### 11.3 必须补缺清单（opencode 自己没有的）

1. **待审单持久表**（内存 Map + finalizer 全拒——企业审批工作台不可接受；补 (谁,何时,批了什么版本,理由) 四要素，resolve 带鉴权）。
2. **审批事件入 durable manifest**（permission.v2.* 现在不落库——审计断链）。
3. **投影可重建纪律**：它的现实是「投影即权威、事件流与投影会分歧（revert commit 删投影不删事件、无启动重放、v2 曾整体 reset）」。企业若以事件流为审计真相，必须二选一：要么 projector 幂等 + 启动重放校验，要么明确投影表即真相、事件流只是传输通道——**不能像它一样悬在中间**。这是本次深挖最重要的反面教训。
4. **脱敏层**：持久化前无 secret 替换（对照 OpenHands `_replace_secrets` 收口模式）。

### 11.4 一张映射表（opencode 表 → 你的 PG）

```
event/event_sequence ──照搬（+tenant_id，seq 分配改行锁）
session ────────────照搬（成本五列 + revert JSON 列 + time_compacting 都值得保留）
session_message ────照搬（v2 投影；放弃 v1 message/part 双轨，一步到位）
session_input ──────照搬（双唯一索引原样）
session_context_epoch 照搬（系统提示纪元）
permission ─────────照搬（project_id→tenant+project）
todo ──────────────照搬（整板覆盖简单够用）
credential ────────改 vault 引用
project/project_directory → tenant 内的项目注册（可选）
+ 你要新增：approval_request 持久表、artifact 表、审计哈希链（视合规等级）
```

## 12. 对旧档案的修正（复核留痕）

1. agent-oss/profiles/opencode.md §4.5「WebSocket 通道（WebSocketTracker）」→ 实为 graceful-shutdown 连接注册表，非事件分发通道。
2. 同档案 §7「enterprise/control-plane 包」→ 本基线已无 control-plane 包；enterprise 是纯 S3/R2 对象存储的分享云（share_snapshot 单文件全量快照 + sync 增量合并），无策略下发持久化。
3. 补充澄清 §4.1：事件流 append-only 但 revert commit 只删投影行——「事件表权威性」限于 sync replay 通道。

## 13. 抽查复核与本机 DB 比对记录（2026-09-22）

**源码抽查（主审）**：8 条载荷最重证据全部命中：PRAGMA 六条（database.ts:27-33）、`behavior:"immediate"`（event.ts:351）、schema.gen.ts 19 张 CREATE TABLE（生成 SQL 非 drizzle 调用，初次 grep 未中系预期差异）、credential value 明文 JSON（credential/sql.ts）、projector 事务内联（event.ts:236/323/617-620）、snapshot alternates（snapshot/index.ts:209-216）、background-job "intentionally not durable"（background-job.ts:114）、session_input 双唯一索引（session/sql.ts:163-164）。

**本机生产 DB 只读比对**（`~/.local/share/opencode/opencode.db`，`file:...?mode=ro`）：

| 比对项 | 结果 |
|---|---|
| 表清单 | 20 表 = 报告 19 业务表 + migration 日志表，逐名吻合 ✔ |
| journal_mode | `wal`（且 -wal/-shm 文件在）✔ |
| event/event_sequence DDL | 与 schema.gen 逐字一致（aggregate_id PK + owner_id；event FK CASCADE）✔ |
| 五条关键唯一索引 | event_aggregate_seq_idx、permission_project_action_resource_idx、session_input 双唯一、session_message_session_seq_idx 全部实存 ✔ |
| session 成本列 | cost REAL + tokens_{input,output,reasoning,cache_read,cache_write} 五列实存 ✔ |
| event type 形态 | `session.updated.1` 等点号后缀（佐证 §5.2 修正）✔ |
| 不变式 | event_sequence 行数 = session 行数（一聚合=一会话）✔ |
| 版本差观察 | 本机 event 以 v1 风格类型为主、session_message 仅 2 行 vs message 20376 行（本机以 v1 引擎路径为主）；permission/credential/session_input 0 行；存在 after-crash 副本（基线无此机制，见篇首前提）|

## 14. 独立审核记录（general subagent，2026-09-22）

审核范围：证据抽查 26 项（源码）+ 本机 DB 补验 6 项 + 交叉引用 4 份。**结论：有条件通过 → 修订后定稿**。26/27 项完全命中（多数行号精确到个位）；「投影与事件流分歧」（§11.3-3）论证链经逐环验证成立。审核揪出并已修订 6 处：①`@version` 分隔符错误（实为点号，§5.2/§11.1 两处，源码+本机 DB 双重铁证）；②补「本机运行版本领先克隆基线」比对前提（篇首）；③上游交叉引用收敛为 dimensions/04/06（篇首）；④seq upsert 伪 SQL 改 `SET seq=<新seq>`（§5.2）；⑤「整清五表」改六表含事件流两表（§6.3，顺带强化 §11.3-3）；⑥SAVEPOINT 代码路径补全（§3）。

## 附录 A：全表字段明细（19 表；DDL 以本机生产库 sqlite_master 实测为准，与 schema.gen.ts 一致）

**事件溯源组**

`event`（durable 事件流；写入方 `event.ts#commitDurableEvent`）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | text | PK | 事件 ID |
| aggregate_id | text | NOT NULL, FK→event_sequence ON DELETE CASCADE | 聚合根 = sessionID |
| seq | integer | NOT NULL | 聚合内单调序号 |
| type | text | NOT NULL | 类型 + `.` + 版本后缀（如 `message.part.updated.1`） |
| data | text | NOT NULL | JSON 载荷 |

`event_sequence`（每聚合序列 + 同步所有权；写入方同上，`claim()` 交接 owner）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| aggregate_id | text | PK | 聚合 ID |
| seq | integer | NOT NULL | 该聚合最新 seq（分配起点） |
| owner_id | text | 可空 | 同步协议的所有权持有者（/sync/steal 交接） |

**会话投影组**

`session`（会话主表；写入方 projector）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | text | PK | `ses_` 前缀时间倒序随机 ID（字典序=新→旧） |
| project_id | text | NOT NULL, FK→project CASCADE | 归属项目（隔离键） |
| workspace_id | text | 可空 | 归属工作区（分支维度） |
| parent_id | text | 可空 | 父会话（子会话树） |
| slug | text | NOT NULL | 创建时 `Slug.create()` 生成（core/src/session.ts:222） |
| directory | text | NOT NULL | 规范化绝对路径（Windows `/` 归一化 customType，database/path.ts:27-75） |
| path | text | 可空 | 路径列（DatabasePath） |
| title | text | NOT NULL | 标题 |
| version | text | NOT NULL | 会话信息版本（projector 拷贝 info.version，projector.ts:55） |
| share_url | text | 可空 | 分享 URL 冗余列 |
| summary_additions / summary_deletions / summary_files | integer | 可空 | revert diff 聚合统计 |
| summary_diffs | text | 可空 | diff 明细 JSON（v1 迁移拆出 session_diff 文件后的聚合列） |
| metadata | text | 可空 | JSON 元数据 |
| cost | real | NOT NULL DEFAULT 0 | 成本合计（每 step 增量维护，§6.2） |
| tokens_input / tokens_output / tokens_reasoning / tokens_cache_read / tokens_cache_write | integer | NOT NULL DEFAULT 0 | 五分类 token 合计（同上） |
| revert | text | 可空 | revert stage 状态 JSON（messageID+snapshot+diff+files） |
| permission | text | 可空 | v1 会话级 ruleset JSON |
| agent | text | 可空 | 当前 agent 画像 |
| model | text | 可空 | 当前模型 JSON `{id,providerID,variant}` |
| time_created / time_updated | integer | NOT NULL | 时间戳（ms） |
| time_compacting | integer | 可空 | 最近压缩时间 |
| time_archived | integer | 可空 | 归档时间 |

`message`（v1 消息投影）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | text | PK | 消息 ID |
| session_id | text | NOT NULL, FK→session CASCADE | |
| time_created / time_updated | integer | NOT NULL | updated 由 drizzle `$onUpdate` 自动刷新 |
| data | text | NOT NULL | 去 id/sessionID 后的消息对象 JSON（`messageData()`，projector.ts:84-87） |

`part`（v1 part 投影，流式 upsert 同行更新）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | text | PK | part ID |
| message_id | text | NOT NULL, FK→message CASCADE | |
| session_id | text | NOT NULL（**冗余列，无 FK**） | 供按会话直查 |
| time_created / time_updated | integer | NOT NULL | |
| data | text | NOT NULL | part 对象 JSON（`{"type":"text","text":...}`，本机 DB 实测） |

`session_message`（v2 事件化消息投影，seq 对齐事件流）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | text | PK | 消息 ID |
| session_id | text | NOT NULL, FK→session CASCADE | |
| type | text | NOT NULL | 消息类型 |
| seq | integer | NOT NULL, **UNIQUE(session_id,seq)** | 与事件流 seq 对齐——投影顺序即事件顺序 |
| time_created / time_updated | integer | NOT NULL | |
| data | text | NOT NULL | 消息对象 JSON |

`session_input`（输入收件箱，两阶段 admitted→promoted）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | text | PK | |
| session_id | text | NOT NULL, FK→session CASCADE | |
| prompt | text | NOT NULL | 提示词 JSON |
| delivery | text | NOT NULL | `steer`（运行中插话）/ `queue`（排队） |
| admitted_seq | integer | NOT NULL, **UNIQUE(session_id,admitted_seq)** | = PromptAdmitted 事件 seq（与事件同事务 INSERT） |
| promoted_seq | integer | 可空, **UNIQUE(session_id,promoted_seq)**（NULL 不冲突） | = Prompted 事件 seq，NULL=仍在队列 |
| time_created | integer | NOT NULL | |

`session_context_epoch`（系统上下文纪元，每会话一行整行替换）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| session_id | text | PK, FK→session CASCADE | |
| baseline | text | NOT NULL | 基线文本（agent system+skills+guidance 合成，作 LLM system prompt） |
| snapshot | text | NOT NULL | SystemContext 结构化 JSON |
| baseline_seq | integer | NOT NULL | 基线确立时的聚合 seq（读侧过滤旧基线 system 消息） |

`todo`（任务板，整板 DELETE+INSERT）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| session_id | text | 复合 PK 第一列, FK→session CASCADE | |
| position | integer | 复合 PK 第二列 | 排序位 |
| content | text | NOT NULL | 内容 |
| status | text | NOT NULL | 状态 |
| priority | text | NOT NULL | 优先级 |
| time_created / time_updated | integer | NOT NULL | |

**授权与分享组**

`permission`（持久授权 "always" 规则；写入方 permission/saved.ts，`onConflictDoNothing` 幂等）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | text | PK | `psv_` + 单调序列 |
| project_id | text | NOT NULL, FK→project CASCADE | 授权作用域 |
| action | text | NOT NULL | 动作（工具名），**UNIQUE(project_id,action,resource)** |
| resource | text | NOT NULL | 资源 pattern |
| time_created / time_updated | integer | NOT NULL | effect 隐含 allow，不入库 |

`session_share`（分享元数据）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| session_id | text | PK, FK→session CASCADE | |
| id | text | NOT NULL | 远端分享 ID |
| secret | text | NOT NULL | 鉴权凭证 |
| url | text | NOT NULL | 分享 URL |
| time_created / time_updated | integer | NOT NULL | |

**项目与工作区组**

`project`（项目注册表，仓库身份；写入方 core/src/session.ts:214、project/project.ts）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | text | PK | 仓库身份 ID（git remote 哈希→commonDirectory→根 commit→目录名） |
| worktree | text | NOT NULL | 主工作树绝对路径 |
| vcs | text | 可空 | 版本控制系统 |
| name | text | 可空 | 显示名 |
| icon_url / icon_url_override / icon_color | text | 可空 | 图标 |
| time_created / time_updated | integer | NOT NULL | |
| time_initialized | integer | 可空 | 初始化完成时间 |
| sandboxes | text | NOT NULL | 沙箱配置 JSON 数组 |
| commands | text | 可空 | 命令配置 JSON |

`project_directory`（项目↔目录多对多）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| project_id | text | 复合 PK 第一列, FK→project CASCADE | |
| directory | text | 复合 PK 第二列 | 目录路径 |
| type | text | 可空 | `main|root|git_worktree` |
| strategy | text | 可空 | 目录注册策略（project/directories.ts:14 可选字符串） |
| time_created | integer | NOT NULL | |

`workspace`（工作区，分支维度会话归组；写入方 control-plane/workspace.ts）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | text | PK | |
| type | text | NOT NULL | 工作区类型 |
| name | text | NOT NULL DEFAULT '' | |
| branch | text | 可空 | 分支 |
| directory | text | 可空 | 目录 |
| extra | text | 可空 | JSON 附加信息 |
| project_id | text | NOT NULL, FK→project CASCADE | |
| time_used | integer | NOT NULL | 最近使用（projector touch，projector.ts:224-231） |

**账号与凭据组**

`credential`（integration 凭据；写入方 credential.ts——单事务先 DELETE 同 integration 再 INSERT）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | text | PK | |
| integration_id | text | 可空 | 一 integration 一凭据（替换语义） |
| label | text | NOT NULL | |
| value | text | NOT NULL | **明文 JSON**（API key 字符串或 OAuth token 对 tagged union） |
| connector_id | text | 可空 | 连接器 |
| method_id | text | 可空 | 认证方式 |
| active | integer | 可空 | bool |
| time_created / time_updated | integer | NOT NULL | |

`account`（控制面账号）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | text | PK | |
| email / url | text | NOT NULL | |
| access_token / refresh_token | text | NOT NULL | **明文** |
| token_expiry | integer | 可空 | |
| time_created / time_updated | integer | NOT NULL | |

`account_state`（活跃账号指针，单行）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | integer | PK | 恒为 1（单行） |
| active_account_id | text | 可空, FK→account ON DELETE SET NULL | 活跃账号指针 |
| active_org_id | text | 可空 | 活跃组织 |

`control_account`（**LEGACY** 旧账号表，仅存量）：

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| email + url | text | **复合 PK** | |
| access_token / refresh_token | text | NOT NULL | 明文 |
| token_expiry | integer | 可空 | |
| active | integer | NOT NULL | |
| time_created / time_updated | integer | NOT NULL | |

**迁移组**

`data_migration`（数据搬迁水位，建表但无写入方）：`name text PK` + `time_completed integer NOT NULL`。
`migration`（运行时建，schema 迁移日志）：`id TEXT PK` + `time_completed INTEGER NOT NULL`。

## 附录 B：索引全清单（本机实测 18 条）

| 表 | 索引 | 类型 |
|---|---|---|
| event | (aggregate_id, seq) | UNIQUE |
| event | (aggregate_id, type, seq) | 普通 |
| session | (project_id) / (workspace_id) / (parent_id) | 普通 ×3 |
| message | (session_id, time_created, id) | 普通 |
| part | (message_id, id) / (session_id) | 普通 ×2 |
| session_message | (session_id, seq) | UNIQUE |
| session_message | (session_id, type, seq) / (session_id, time_created, id) / (time_created) | 普通 ×3 |
| session_input | (session_id, admitted_seq) / (session_id, promoted_seq) | UNIQUE ×2 |
| session_input | (session_id, promoted_seq, delivery, admitted_seq) | 普通（pending 查询） |
| permission | (project_id, action, resource) | UNIQUE |
| todo | (session_id) | 普通 |
