# Agent 持久化专项调研报告——七类运行时数据的存储实现全景

> **问题**：一个 agent 系统运行时产生的各类数据（会话转录、执行状态、记忆、权限审批、审计成本、产物、配置凭据）分别被各家存成什么形态、用什么引擎、写入与读取路径怎么走、并发与生命周期怎么管。
> **方法**：不做逐仓 profiles（两轮已覆盖），按数据类别 × 六路并行深挖 `dimensions/`（01-06），本报告为综合交付。schema/DDL/文件格式级证据 200+ 条，全部可溯源到 `~/develop/opensource/<repo>/路径#符号`。
> **上游**：`research/agent-framework/`（17 框架，维度 3 记忆 / 维度 10 持久化）、`research/agent-oss/`（18 仓，各档案 §4 + 跨组专题三）。模式级结论引用上游不重复；本轮补的是它下面的存储实现层。
> **对象**：25 仓，基线 2026-09-20 全数核验与两轮记录一致（表见 README）。证据等级沿用【核心】/【还原源码】（claude-code-sourcemap）。

## 0. TL;DR

1. **七类数据各有主导形态，没有「一张表存一切」的成功案例**：会话转录 → append-only 事件流（JSONL/事件表）；执行状态 → checkpoint（快照 blob 或事件投影）；记忆 → markdown 文件真相源 + 可丢弃索引；审批 → 三元组唯一索引表 + 事件流；审计/成本 → 一等持久化事件类型或独立账本；产物 → 落盘文件 + 引用外键；凭据 → vault 存真值 + 引用键流转。
2. **「真相源 vs 派生物」的分界是被反复独立发明的第一设计决策**：摘要、向量索引、快照、缓存全部可丢可重建（cline hash 校验旁挂 / WrenAI index is disposable / langgraph 版本化 blob / ai-hedge-fund 内容寻址缓存）；append-only 原文链（会话事件、哈希链账本、consent 回执）才是不可变的合规事实。
3. **主存选型结论**（服务端多会话）：事件表 + 聚合序列唯一索引（opencode event 三表）> 带锁 JSONL（codex flock+ordinal）> 全量重写（gemini-cli logs.json / cline messages 正文，并发反例）；SQLite 适合单机，PG 才有「按通道版本寻址的旁表」这类体积优化（langgraph checkpoint_blobs）。
4. **三个普遍缺口**：待审单持久化（opencode/DB-GPT/codex 全在内存，重启即丢）、产物生命周期（六仓仅两家有清理）、记忆遗忘（无一家有策略化删除，只有降权/归档/合并）。
5. **三条普适写纪律**：原子写（tmp+fsync+rename）是文件类存储的最低门槛；恢复必须校验衔接点（前缀 hash / ordinal 连续性 / parentUuid 链）；fork = 复制重写 + 重播种旁挂记录（漏种 = 缓存击穿/静默错续，三家注释里各有一款真实事故）。

## 1. 数据分类框架：七类数据 × 存储特性

| # | 类别 | 谁写谁读 | 丢失代价 | 变更模式 | 合规等级 | 深挖 |
|---|---|---|---|---|---|---|
| 1 | 会话转录 | 每事件追加；resume/审计读 | 审计事实丢失，不可恢复 | append-only | ★★★ | dimensions/01 |
| 2 | 执行状态 checkpoint | 每超步/每轮；崩溃恢复读 | 断点重跑（可容忍但贵） | 快照覆盖/事件投影 | ★ | dimensions/02 |
| 3 | 记忆 | 低频写入；每次 prompt 前检索 | 长期学习丢失 | append+合并+衰减 | ★★ | dimensions/03 |
| 4 | 权限与审批 | 审批时写；每次工具调用前读 | 授权语义漂移/审批单丢失 | 低频读写 | ★★★ | dimensions/04 |
| 5 | 审计与成本 | 旁路写（每次 LLM 调用/动作）；对账/归档读 | 合规举证失败 | append-only | ★★★ | dimensions/05 |
| 6 | 产物与大对象 | 工具/节点产出时写；用户/模型按需读 | 用户可见成果丢失 | 一次写入多次读 | ★★ | dimensions/06 |
| 7 | 配置与凭据 | 人/运维写；运行时读 | 密钥泄漏或服务不可用 | 极低频 | ★★★（凭据） | dimensions/04 |

## 2. 总览矩阵：每类数据谁用什么形态

| 类别 | 文件/JSONL | SQLite | 关系库（PG/MySQL） | 向量库 | 对象存储 |
|---|---|---|---|---|---|
| 会话转录 | codex/claude-code/gemini-cli；cline（JSON 全量重写） | opencode（event 三表）；cline（sessions.db） | dify（Conversation/Message）；SQLBot（chat 表） | — | OpenHands（每事件一 JSON） |
| 执行状态 | agent-framework（单文件 checkpoint） | crewAI/TradingAgents（kickoff/checkpoint 分库） | langgraph PG（三表+blobs）；adk（sessions/events）；agentscope-java（CAS）；dify（runs/executions/pauses） | — | dify（暂停态 blob） |
| 记忆 | TradingAgents（单 md）；Vibe（md+frontmatter）；deepagents（AGENTS.md）；agentscope（md 目录）；WrenAI（md 真相源） | Vibe（FTS5 派生索引）；supersonic（s2_chat_memory） | supersonic/dify（真相源表） | crewAI（LanceDB）；langgraph（pgvector 双表）；WrenAI（LanceDB 派生）；supersonic/dify（双写） | — |
| 权限审批 | gemini（TOML 五层）；codex（Starlark .rules）；Vibe（mandate/consent/HALT 文件树）；claude-code（settings JSON 多源） | opencode（permission 三元组表）；cline（tasks.db revision 列） | — | — | — |
| 审计成本 | codex（TokenUsage/RiskScore 入 rollout）；Vibe（audit.jsonl+哈希链）；ai-hedge-fund（内容寻址单 JSON） | FinRobot（request_logs） | SQLBot（chat_log+sys_logs 双平面）；supersonic（s2_query_stat_info） | — | — |
| 产物大对象 | gemini/opencode/DB-GPT（落盘指针目录） | — | DB-GPT（view message 入库）；dify（offload 表） | — | dify（14 后端，upload_files）；OpenHands（FileStore）；data-formulator（workspace parquet） |
| 配置凭据 | data-formulator（credentials.db+vault）；browser-use（内存+占位符） | data-formulator（vault） | DB-GPT（connector_instance 密文列） | — | — |

## 3. 会话转录：append-only 是审计正解，工程差距在读路径与恢复校验

**形态谱系**（详见 dimensions/01）：五仓四路线——JSONL append-only（codex/claude-code、gemini 新层）、JSON 全量重写（cline 现基线、gemini 旧层）、每事件一文件 + 页缓存（OpenHands）、SQLite 事件溯源（opencode，本轮从 01 篇结论沿用 + agent-oss 轮已挖）。

**本轮新增的关键实现细节**：

- **codex 是工程完备度标杆**：行 = `{timestamp, ordinal, item}`，item 12 大类（SessionMeta/ResponseItem 18 变体/TokenUsageRecord/SecurityRiskScore/CompactedItem/TurnContext…）；`~/.codex/thread-writer-locks/{threadId}.lock` advisory flock 串行写；fork/revert 双 id 文件名 + `forked_from_id` 血统；resume 用 `ReverseJsonlScanner` 倒序寻址不全量加载；7 天冷压缩 .zst。
- **claude-code（还原源码）细节最重**：21 类 entry 联合，`isChainParticipant` 是链成员单一真相源（progress 纯 UI 不入链——#14373 事故）；旁挂 entry 家族（summary/title/content-replacement/file-history-snapshot/attribution-snapshot）都是「可丢可重生成」的附属记录；墓碑删除 64KB 尾部字节搜索 + ftruncate；64KB head/tail lite 读 + 5MB 压缩边界跳读 + 50MB 硬上限三层读防御；fork 必须重播种 contentReplacement（漏种 = prompt cache 击穿，注释详述真实事故）。
- **cline 现基线是「JSON 全量重写」而非档案旧说的 JSONL**（本轮修正）：`.messages.json` pretty JSON、每 turn 重写；但旁挂体系（compaction sidecar sha256 前缀校验、只 hash 语义字段不 hash id/ts）与 SQLite 分库（agenda_tasks 的 revision/approved_revision、单活跃 run 部分唯一索引）是审批-版本绑定的唯一文件级实现。checkpoint 干脆不是文件而是 git 对象（私有 index + stash create 镜像）。
- **OpenHands 页缓存**是对象存储读放大专解：25 条/页 `event_cache/{start}-{end}.json`，`search_events` 按页对齐批量读；事件 JSON >1MB 仅 warn ⚠️。

**设计结论**：① append-only 主转录 + 可丢弃旁挂状态；② 恢复必须校验衔接点（前缀 hash / ordinal 连续性 / parentUuid 链——「旁挂 + 无校验」= 静默错续）；③ fork 是复制重写 + 重播种；④ 大文件读路径决定产品上限；⑤ 写并发按部署形态选型（进程内队列 → flock → DB 唯一索引/CAS）。

## 4. 执行状态：快照派与事件派的存储层差异，以及 checkpoint 必须装什么

**快照派 vs 事件派落到表结构**（详见 dimensions/02）：一行的含义不同（完整执行态 vs 不可变 delta）、消息位置不同（channel_values blob vs event_data 单 JSON 列）、恢复方式不同（差分重放 vs 全量投影）、改史方式不同（新 checkpoint 分支 vs 补偿事件）。三个存储层分水岭：**大对象行内还是旁表**（langgraph PG checkpoint_blobs 按 (channel, version) 寻址、跨 checkpoint 去重、DO NOTHING upsert——SQLite 版无此表是清晰对照组）、**serde 自描述标签还是裸 JSON**（langgraph msgpack ext code 表：pydantic=5/numpy=6/DeltaSnapshot=7）、**并发控制是否下推 SQL**（agentscope-java `UPDATE ... WHERE version=?` CAS 原文 vs langgraph 幂等 upsert）。

**checkpoint 元素清单**（八仓横向，谁有谁没有）：消息历史全有；调度版本表只有 langgraph；pending writes 只有 langgraph（checkpoint_writes 表）与事件派（天然即 delta）；HITL 挂起正在收敛为一等持久对象（MS pending_request_info_events 入 checkpoint 本体、crewAI pending_feedback 独立表、dify workflow_pauses+reasons + Redis 命令通道）；**拓扑哈希只有 agent-framework**（graph_signature_hash，17 家唯一）；图定义快照只有 dify（graph 列每 run 全量）。

**代表性实现**：adk v0→v1 的迁移方向（十几个 pickle 列收拢为 event_data 单 JSON 列 + RestrictedUnpickler）；dify 的「执行态在对象存储、DB 只存指针」（workflow_pauses.state_object_key）+ offload 二级表；agentscope-java 列表状态一元素一行 + hash 辅助键判定增量追加。

## 5. 记忆：markdown 真相源 + 可丢弃索引是被反复独立发明的同构

**介质谱系**（详见 dimensions/03）：单文件 markdown（TradingAgents，`<!-- ENTRY_END -->` 硬分隔符 + tag 行七段结构 + pending→resolved 生命周期 + temp/replace 原子改写）→ markdown frontmatter 体系 + FTS5/BM25 双 SQLite 派生索引（Vibe，14 字段 frontmatter、艾宾浩斯 14 天半衰期、Tier 1 只归档不删除）→ markdown 目录 + LLM 选择器检索（agentscope，description 定义为「检索触发器」而非摘要、幻觉文件名过滤）→ LanceDB 单表（crewAI，importance/scope 一等列、consolidation 原地改写）→ pgvector 双表（langgraph，store + store_vectors 按 (doc, field) 一行、DISTINCT ON 去重、TTL）→ SQL 表 + 向量库双写（supersonic 状态机驱动增删、启动重灌兜底；dify celery 异步 + collection binding）→ markdown 真相源 + LanceDB 可丢弃索引（WrenAI，origin 标记防误删、维度不一致启动即拒）。

**五条结论**：① markdown 为真相源、索引可丢弃（四仓独立收敛）；② 原子写是文件记忆最低门槛；③ 结构化元数据放 tag 行/frontmatter 顶行、正文自由文本；④ 双写一致性靠状态机/标记位（失步谁赢、删错怎么防，三家三种可抄答案）；⑤ 向量 schema 三流派（doc 内向量列 / 字段级索引表 / metadata JSON 陪跑），按「是否需要对同一文档不同片段分别检索」决策。

## 6. 权限与审批：规则收敛为三元组表，待审单持久化是全员缺口

**规则落盘形态谱系**（详见 dimensions/04）：内存 Map（人人都有）→ 结构化文件（gemini TOML 五层带 + AndSave 串行队列/原子写/损坏恢复三件套；claude-code settings JSON 五源 + PermissionUpdate 六操作×五目的地；codex Starlark `.rules` 追加式修订 + flock + ArcSwap 热生效，但文件不记批准人）→ **数据库表（opencode `permission(project_id, action, resource)` 唯一索引——最小完备 schema，save/source 上下文留在事件流）**。

**待审单**：DB-GPT 模块级内存 dict（反例四连：重启丢/多副本互不可见/resolve 无鉴权/fail-open）；opencode location 级内存 Map + finalizer 全置拒（半正例：审批面外化做全了、底不持久）；codex ApprovalStore 内存 + 审批事件入 rollout（正例：事件即审计）；对照正例 cline hub（pendingApprovals 重订阅重放）。

**凭据六级谱系的存储实现**（补齐上游谱系的右端）：DB-GPT Fernet + env `ENCRYPT_KEY` + connector_instance 密文列 + `${env:VAR}` 插值；data-formulator 六级解析链（Flask session cookie→refresh→sso→delegated→**SQLite vault**（credentials.db BLOB + `.vault_key`）→none）+ admin/user 连接器存储分离 + 删除成对清理；browser-use 纯内存 + `<secret>` 占位符 + 域限定替换层；**Vibe-Trading 的两个物理约定**：kill switch 只认哨兵文件存在（payload 损坏仍触发）+ mandate 写入「证据先于授权」（先 consent 后 mandate，consent_token_sha256 绑死）。

## 7. 审计与成本：一等持久化类型、六分类 token、审计即缓存

**一次 LLM 调用的留痕字段公约数**（详见 dimensions/05 公约数表）：时间 + 时长 + 归属 ID 三家以上都有；prompt 原文、token 分类、模型标识各只有 1-2 家全记——**「可回放」与「可计费」在开源界普遍是二选一**。成本字段谱系 L0-L4：codex 六分类 token × 三级累计（response/turn/thread）居顶，supersonic/FinRobot 只记毫秒居底。

**代表实现**：codex TokenUsageRecord 是 rollout 无条件持久化变体 + CompactedItem 内嵌快照（resume 免远扫）；ai-hedge-fund PromptCache = `sha256(agent|model|system|user)[:24]` 内容寻址单 JSON，缓存/审计/调试三合一，回测重跑 $0；SQLBot 双平面（chat_log 14 操作枚举逐 LLM 调用 + sys_logs 声明式管理面含 IP 代理链/DELETE 补录）；Vibe 哈希链（seq+prev_record_hash+canonical JSON、append 前验链断链拒写、被拒与 halt 是一等记录、64MiB 轮转封存永不删、离线自证 envelope）；OpenHands `<secret_hidden>` 写时脱敏在持久化唯一入口收口 + secrets.json 单文件。

**五条结论**：成本进一等持久化类型而非日志；六分类 token 是最细公约；审计即缓存是零成本起步；token 与金额双记才闭合（价目独立维护）；审计写入旁路 fail-open、防篡改环节 fail-closed（分界线画在「追加新记录」vs「在被污染历史上追加」）。

## 8. 产物与大对象：占位三件套 + 引用外键化 + 两层预算

三类答案（详见 dimensions/06）：工具输出落盘指针（gemini 40K 字符 / opencode 50KB+2000 行双限 / DB-GPT 新代三层防线）、结构化产物入库 + offload（DB-GPT view message `pass_to_model=False` / dify offload 表→upload_files 外键）、工作区即数据湖（OpenHands 沙箱 / data-formulator parquet + tableId 引用）。

**五条结论**：占位三件套（尺寸声明+稳定指针+取回指引）是行业最小公约数；引用要外键化而非裸路径（opencode part.outputPaths 字段 / dify 三跳外键 + sha3_256 去重）；防循环与降级路径必须显式（read_file 阈值 pin inf / 写盘失败回落截断）；两层预算优于单阈值（单结果 + 单轮聚合，阈值随模型窗口缩放）；生命周期普遍欠账（仅 opencode 7 天 TTL 与 data-formulator TTL+LRU 有真清理）。

## 9. 横切议题（跨七类的存储级规律）

### 9.1 真相源与派生物的分界清单

| 数据 | 真相源（不可变） | 派生物（可丢可重建） |
|---|---|---|
| 会话 | 事件流原文（JSONL/event 表/事件文件） | 压缩摘要（旁挂+hash 校验）、标题、session 列表索引（SQLite threads 表） |
| 执行状态 | 事件派的事件流 / 快照派以最后 checkpoint 为准 | checkpoint blobs（同版本去重）、dify offload 文件 |
| 记忆 | markdown 文件 / SQL 业务表 | 向量索引（启动重灌/CLI 重建）、FTS5、BM25 关系链 |
| 审计 | 哈希链账本、consent 回执、rollout | Metrics 汇总、report JSON、日志聚合 |
| 产物 | 落盘文件/对象存储本体 | 上下文内 preview、part.outputPaths 引用、缩略图 |

判据只有一条：**派生物坏了，能不能从真相源 + 确定性代码重建**。设计任何新存储件时先回答它属于哪边。

### 9.2 原子写纪律（文件类存储的最低门槛）

tmp(pid/uuid 后缀) → write → fsync → rename →（目录 fsync），失败清理 tmp：agent-framework checkpoint、cline writeFileAtomic、gemini AndSave（wx 独占 + EXDEV 回退）、TradingAgents memory.md、gpt-researcher report_store、Vibe mandate/HALT/ledger 全部同构。全量重写路径（读-改-写）必须配原子替换，否则崩溃即损坏唯一真相源。

### 9.3 并发控制谱系（按部署形态）

进程内队列（claude-code writeQueues）→ advisory flock（codex writer_lock + coordination + maintenance 三级；Vibe ledger flock）→ 应用层乐观锁（cline statusLock OCC + withOccRetry；adk update_time 微秒 marker）→ **SQL 下推（agentscope-java CAS WHERE version=?；opencode 唯一索引 + ON CONFLICT；cline 部分唯一索引保证单活跃 run）**。多副本服务端是最后一级的分界线：凡未到 SQL 级的方案都隐含单写者假设。

### 9.4 脱敏位置

四个合法位置（沿上游结论，本轮补实现）：生成侧占位符（browser-use `<secret>` 域限定替换在 execute_action 校验后、动作执行前）；**持久化适配器写时脱敏（OpenHands `_replace_secrets` 在 add_event 唯一入口，内存订阅者也只见脱敏版）**；进 sink 前脱敏（Vibe redact_payload 在进任何审计 sink 前）；展示层打码（DB-GPT `_summarize_args` HIDDEN 键集合）。反例群仍是 B 组装饰性加密四连。

### 9.5 容量与生命周期治理

压缩：codex 7 天冷压缩 .zst、langgraph DeltaChannel（O(N²)→O(N)）、dify offload、claude-code 压缩边界跳读。清理：claude-code 30 天、gemini retention maxAge/maxCount、opencode tool-output 7 天、data-formulator TTL+LRU；**其余普遍无限累积**。轮转：Vibe 账本 64MiB 封存永不删（跨段续链可检整段删除）、TradingAgents 条数上限（只删 resolved、pending 永存）。判据：会话/审计数据按保留期删，账本类只封存不删，派生索引随时重建。

## 10. 持久化模式清单（可直接照抄，★ = Java/Spring 映射最直接）

| # | 模式 | 出处（细节见 dimensions） |
|---|---|---|
| P1 ★ | 事件溯源主存：event(aggregate_id, seq) 唯一索引 + 会话/消息/part 规范化三表 | opencode（01/02 篇） |
| P2 ★ | 成本/风险作为一等持久化事件类型（TokenUsageRecord 六分类 × 三级累计） | codex（05 篇） |
| P3 ★ | 审计即缓存：内容寻址单 JSON（prompt/response/snapshot_hash），零表结构起步 | ai-hedge-fund（05 篇） |
| P4 ★ | 持久授权三元组表 (scope, action, resource) + ON CONFLICT 幂等 | opencode（04 篇） |
| P5 ★ | 「批准并记住」写文件三件套：串行队列 + 原子写 + 损坏恢复 | gemini-cli（04 篇） |
| P6 ★ | markdown 记忆真相源 + 派生索引可重建（状态机/标记位管双写一致性） | WrenAI/supersonic/dify（03 篇） |
| P7 | 压缩旁挂 + 前缀 hash 校验后才投影（canonical 原文永不被摘要覆盖；只 hash 语义字段） | cline（01 篇） |
| P8 | fork = 复制重写 + 重播种旁挂记录（血统 id 记 SessionMeta） | codex/claude-code（01 篇） |
| P9 ★ | checkpoint 按通道版本寻址旁表（跨快照去重）+ 拓扑哈希进 checkpoint | langgraph + agent-framework（02 篇） |
| P10 ★ | CAS 乐观并发下推 SQL（读版本不反序列化 payload） | agentscope-java（02 篇） |
| P11 | HITL 挂起一等持久对象（pending 表/事件 + 原因表 + 命令通道清理） | crewAI/dify/MS（02 篇） |
| P12 ★ | 哈希链账本（append 前验链、被拒/halt 入账、轮转封存、离线自证 envelope） | Vibe-Trading（05 篇） |
| P13 ★ | kill switch 文件哨兵（存在性即权威、损坏仍触发）+ 授权「证据先于授权」双文件 | Vibe-Trading（04 篇） |
| P14 ★ | 工具输出落盘指针：占位三件套 + part 字段化引用 + 两层预算 + 7 天 TTL | opencode/gemini/DB-GPT（06 篇） |
| P15 ★ | 大字段 offload 二级表（NULL=无主 GC 候选）+ 对象存储 + 内容哈希去重 | dify（02/06 篇） |
| P16 ★ | 决策日志 pending→resolved markdown（tag 行硬分隔符 + resolution_date 时点过滤 + pending 永不删） | TradingAgents（03 篇） |
| P17 ★ | vault 存凭据真值 + 引用键流转 + 删除成对清理 | data-formulator/browser-use（04 篇） |
| P18 | 写时脱敏收口在持久化唯一入口（`<secret_hidden>`） | OpenHands（05 篇） |

## 11. 反模式清单（含代码级病灶）

1. **待审单存内存**（DB-GPT `_PENDING_CONFIRMATIONS` 模块级 dict：重启丢/多副本失效/resolve 无鉴权/fail-open try-pass 四连）——审批链路上任何一环异常必须拒绝执行，状态必须持久化，resolve 必须带操作者身份。
2. **全量读改写做主存**（gemini-cli logs.json 每条读全文件重算 id 再整写；cline messages 正文普通 write）——并发弱、丢更新窗口大，只适合单写者桌面；正文写至少补原子 rename。
3. **规则文件不记批准人**（codex amendment 追加 prefix_rule 无 who/when）——「批这版 + 以后自动过」必须是可审计修订事件（批准人/时间/前缀/consent 引用四列）。
4. **旁挂状态无校验恢复**（三家真实事故：cline v1 hash 含 id/ts 导致校验永假、claude-code fork 漏种 contentReplacement 缓存击穿、progress 混入链的 #14373）——新增旁挂类型时 fork/resume 重播种路径要同步设计。
5. **产物无限累积**（gemini tool-outputs / DB-GPT persisted_results 无清理）——产物存储第一天就带 owner + 保留期 + 无主标记。
6. **checkpoint 用完即删**（DataAgent，上游轮结论）+ **审批数据不落库**——HITL 暂停-恢复协议正确但持久化缺位。
7. **向量索引当真相源**（crewAI LanceDB 整表即全部、reset = drop）——索引坏了记忆就没了，违反 9.1 判据。

## 12. 与既有调研的关系及本轮修正

- 本报告是 `agent-framework/dimensions/{03-memory,10-persistence}.md` 与 `agent-oss/dimensions/{C-编码agent组.md §4, 跨组专题.md §3}` 的**下钻层**：模式级/评级级结论引用上游，本轮新增 200+ 条 schema/DDL/文件格式级证据（见 dimensions/01-06）。
- **修正 1**：cline 现基线（cfe9cadab9）会话转录是 pretty JSON 全量重写（`.messages.json`，`buildMessagesFilePayload`），不是旧资料所说的 JSONL——引用 cline 存储细节时以 dimensions/01 §1 为准。
- **修正 2**：TradingAgents 记忆路径实际为 `tradingagents/agents/utils/memory.py`（档案写 `agents/utils/memory.py`，差一级目录）。
- **修正 3**：Vibe-Trading audit.py docstring 称 chain 默认 False，实际签名 `chain: bool = True`——文档与代码不一致，以代码为准。

## 13. 抽查复核记录（2026-09-20）

批次产物完成后按研究纪律做源码抽查，10 条载荷最重的证据全部命中：cline messages.json 命名与 payload 构建、codex `thread-writer-locks` 常量、langgraph `checkpoint_blobs` DDL（channel 列 + PK 四元组）、opencode `permission_project_action_resource_idx` 唯一索引、TradingAgents `<!-- ENTRY_END -->` 分隔符（memory.py:13）、gemini-cli `40_000` 阈值（config.ts:478）、Vibe HALT 哨兵（halt.py）、ai-hedge-fund `sha256[:24]`（cache.py:28）、adk `event_data` 单 JSON 列（v1.py:199-201）、agentscope-java CAS SQL（SessionStateDialect.java:105 `AND item_index = ? AND version = ?`，首次 grep 因路径差异未中、定向复查命中）。存疑项：agentscope Mem0 适配器的 mem0 包内部配置为接口透传推断（dimensions/03 已标 ⚠️）。

## 附录：基线与目录

- 25 仓基线表见 [README.md](./README.md)（2026-09-20 全数核验，与两轮记录一致；OpenHands 经典架构锚定 e8249f00a）。
- 过程文档：[dimensions/01-会话转录](./dimensions/01-会话转录.md)、[02-执行状态与checkpoint](./dimensions/02-执行状态与checkpoint.md)、[03-记忆存储](./dimensions/03-记忆存储.md)、[04-权限审批与凭据](./dimensions/04-权限审批与凭据.md)、[05-审计与成本](./dimensions/05-审计与成本.md)、[06-产物与大对象](./dimensions/06-产物与大对象.md)。
