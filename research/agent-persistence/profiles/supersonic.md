# supersonic 持久化深挖档案（表域全景 / chat 运行时 / 语义层 / 写入策略 / 借鉴意义）

> agent-persistence 轮 profiles 第 6 篇。基线：~/develop/opensource/supersonic @ 6919ac50be。Java 21 + Spring Boot 3.3.9 + MyBatis-Plus；建表 SQL 在 `launchers/standalone/src/main/resources/db/`（schema-mysql / schema-postgres / schema-h2 三方言，**33 表集完全同构**，实测 diff 为空）。前置：产品轮档案 `research/agent-oss/profiles/supersonic.md`（ChatWorkflowEngine 状态机、S2SQL、记忆双审不重复）；`dimensions/03 §7`（s2_chat_memory）、`dimensions/05 §5`（s2_query_stat_info）已核对一致（§9 留痕）。抽查复核见 §8，全表字段明细见文末附录 A/B/C。

## 1. 介质与表域全景

### 1.1 持久化介质清单（不止 MySQL）

| 介质 | 用途 | 证据 |
|---|---|---|
| 关系库（MySQL/PG/H2 三方言同构） | 全部元数据+会话+审计，33 表 | db/schema-mysql.sql（547 行全量 DDL） |
| 向量库（langchain4j EmbeddingStore 多后端：**PGVECTOR 默认**/Milvus/Chroma/OpenSearch/InMemory） | schema 映射召回 + few-shot 例句 | application-postgres.yaml `s2.embedding.store.provider: PGVECTOR`；后端工厂 `common/.../langchain4j/{chroma,milvus,opensearch,...}/spring/` |
| 本地文件①：InMemory 向量后端持久化 | `/tmp/InMemory.{collection}` 文件，每小时+停机落盘 | InMemoryEmbeddingStoreFactory.java:53-90 |
| 本地文件②：维度值词典 | `dic_value_{modelId}_{type}_{itemId}.txt`，latest/backup 双目录 | knowledge/file/LocalFileConfig.java:16-20；FileHandlerImpl.backupFile:41-59 |
| 类路径种子文件 | HanLP 核心词典、内置例句 s2-exemplar.json | resources/data/dictionary/ |
| 查询结果缓存 | 内存 QueryAccelerator（sql/result 两级，命中写审计列） | s2_query_stat_info 的 use_sql_cache/use_result_cache/sql_cache_key 列 |
| Redis / Lucene / 对象存储 | ❌ 均无（pom 与 yaml grep 零命中） | — |

向量 collection 清单（EmbeddingConfig.java:11-32）：`memory_{agentId}`（few-shot 记忆，per-agent）、`meta_collection`（指标/维度元数据）、`text2dsl_agent_collection`（内置例句）、`preset_query_collection`、`solved_query_collection`。

### 1.2 表域盘点（33 表 / 6 域）

| 域 | 表数 | 表 |
|---|---|---|
| chat 运行时 | 8 | **s2_chat / s2_chat_query / s2_chat_parse / s2_chat_context** / s2_chat_memory / s2_chat_model / s2_chat_config / s2_chat_statistics（遗留死表，§4.3） |
| 语义层 headless | 15 | **s2_domain / s2_model / s2_dimension / s2_metric / s2_term / s2_data_set / s2_model_rela / s2_database** / s2_available_date_info / s2_query_rule / s2_tag / s2_tag_object / s2_canvas / s2_metric_query_default_config / s2_app |
| agent & 插件 | 2 | s2_agent / s2_plugin |
| 字典 | 2 | s2_dictionary_conf / s2_dictionary_task |
| 系统 & 权限 | 5 | s2_user / s2_user_token / s2_system_config / s2_auth_groups / s2_collect |
| 统计 | 1 | s2_query_stat_info |

分域特征：**chat 域几乎不吃 created_by/updated_by 审计列**（用 user_name/create_time），语义层域则全表审计列——两套惯例并存（§5.3）。

## 2. chat 运行时表族：一轮 ChatBI 对话在 DB 里的落点（★本轮核心增量）

### 2.1 写入时序（对准 ChatWorkflowEngine 状态机）

状态机本身（MAPPING→PARSING→CORRECTING→TRANSLATING→PHYSICAL_SQL_CORRECTING）**不直接写库**；落库点全部在 chat 层编排与执行器：

| # | 时机（代码位置） | 表操作 |
|---|---|---|
| 1 | parse 入口、跑任何 mapper/parser **之前**：`createChatQuery`（ChatQueryServiceImpl.java:110-115【复核 ✔】→ ChatQueryRepositoryImpl.java:144-159） | **insert s2_chat_query**（query_state=1、query_result 占位 `'{}'`），拿回 question_id 作全程主键。insert 异常被 try-catch 吞掉仅 log |
| 2 | MAPPING→CORRECTING 全程 | 无 DB 写（SchemaMapInfo/候选全内存） |
| 3 | parse 链+后处理链跑完：`batchAddParse` + `updateParseCostTime`（ChatQueryServiceImpl.java:133-134） | **batch insert s2_chat_parse**（每候选一行，score 最高首行 is_candidate=0）；**update s2_chat_query.parse_time_cost**（分段计时 JSON：mapTime/parseTime/sqlTime） |
| 4 | execute：用户选定 parseId → SqlExecutor → headless `queryByReq` | finally 块 `statInfo2DbAsync(state)` 异步 insert s2_query_stat_info，成功/失败都写（含最终物理 SQL+md5） |
| 5 | SqlExecutor 内、执行 SQL 前后 | `chatContextService.updateContext` → **upsert s2_chat_context**（每 chat 一行，存上一轮 SemanticParseInfo 供多轮指代消解） |
| 6 | SqlExecutor 成功且 LLM 路（queryMode=LLM_SQL 且 SUCCESS）：`createMemory`（SqlExecutor.java:44-61） | **insert s2_chat_memory**（status=PENDING；exemplar 从 parseInfo.properties 取） |
| 7 | ExecuteResultProcessor 链跑完：`saveQueryResult` | **update s2_chat_query.query_result**（全量 JSON）+ query_state=1；**update s2_chat.last_question/last_time**（冗余最新一问，列表页免 join） |
| 8 | 用户反馈：`updateFeedback`（ChatManageServiceImpl.java:70-93） | update score/feedback；**score≥5 或 ≤1 时联动批量 enable/disable s2_chat_memory**（人工终审自动化入口，human_review='Reviewed as per user feedback'） |

删除语义：`deleteQuery` 置 query_state=0；`deleteChat` 置 is_delete=1 且限 creator。均软删。

### 2.2 S2SQL 存哪：不是列，是 parse_info JSON 里的 SqlInfo 四段【复核 ✔】

`s2_chat_parse.parse_info`（mediumtext）= `SemanticParseInfo` 全量 JSON，其中 `sqlInfo` 字段（SqlInfo.java:12-21）：

```
parsedS2SQL      // 语义解析器/LLM 原始产出
correctedS2SQL   // 修正器链（Grammar/Schema/Time/...）修正后的 S2SQL  ← 翻译层入口
querySQL         // Calcite 翻译出的最终物理 SQL
correctedQuerySQL// LLM 性能优化改写版（默认关闭）
```

即**一条候选的完整 SQL 血统（LLM 原文→修正→物理）都留在同一行 JSON 里**，可回放。物理 SQL 另有 s2_query_stat_info.query_sql 独立列+md5。

### 2.3 query_result 列内容（QueryResult.java:15-30）

queryId / queryMode / querySql / queryState / queryColumns（列 schema）/ **queryAuthorization（行权限过滤回执，含提示文案）** / chatContext / response / **queryResults（数据行 List<Map>，全量入库）** / textResult / textSummary（LLM 数据解读）/ queryTimeCost / recommendedDimensions / aggregateInfo / errorMsg。

## 3. 语义层表族：口径知识如何进 prompt

链路一句话：**s2_metric/s2_dimension 行 → MetaEmbeddingTask（启动+每 2h，MetaEmbeddingTask.java:61-78）灌进 meta_collection 向量库 → MAPPING 态 EmbeddingMapper 向量召回 + KeywordMapper 走 HanLP 词典 + TermDescMapper 术语 → SchemaMapInfo 命中集合 → PARSING 态 PromptHelper.buildSchemaStr 把命中 metric/dimension 序列化成 `AGGREGATE 'SUM' ALIAS '..'` 式 Schema 串，buildSideInformation 注入 CurrentDate/PriorKnowledge/DomainTerms（源头 s2_term）**。LLM 只见元数据单向生成的 Schema，看不到物理表；术语/口径的真相源是 s2_term/s2_metric/s2_dimension，向量库是可重灌的派生物。

逐表全字段见附录 B。要点：口径三件套 = s2_metric（defineType 三类派生 + is_publish 发布开关）、s2_dimension（dim_value_maps 值级口径 + sensitive_level）、s2_term（黑话→指标/维度挂接）；数据源凭据在 s2_database.config JSON（**AES-ECB 加密**，产品轮 §6.4 避坑项）。

## 4. agent / 插件 / 字典 / 统计

### 4.1 s2_agent

agent=入口配置对象非自治体（产品轮结论）。持久化侧关键字段：`examples`（few-shot 示例问题 JSON）、`tool_config`（绑定数据集/插件工具 JSON）、`llm_config`/`chat_model_config`（模型路由，指向 s2_chat_model.id）、`visual_config`、`enable_search`/`enable_feedback`、权限四列 admin/admin_org/viewer/view_org + is_open。写入方：AgentService Web CRUD。

### 4.2 s2_plugin

`type`（DASHBOARD/WIDGET/URL）、`pattern`（示例问题模式）、`parse_mode`+`parse_mode_config`（插件路由判定：LLM/embedding 配置）、`config`（跳转/接口配置 JSON）。插件召回与执行不落专表，走 chat_query 主链。

### 4.3 字典双表、统计表与死表

- `s2_dictionary_conf`：维度值词典配置（item_id 指向维度/模型、config JSON、status）。`s2_dictionary_task`：**词典构建任务流水**（status、elapsed_ms——任务级耗时留痕）。每日 0:00 @Scheduled 扫 ONLINE 配置重建词典文件（先 backup 再写 latest）。
- `s2_chat_statistics`：**遗留死表**【复核 ✔】——`StatisticsService.batchSaveStatistics` 在当前 HEAD 无任何调用方（全仓 grep 仅接口/实现/Mapper 三处自引用）。设计意图是 interface_name/cost 行为埋点，已被 s2_query_stat_info 取代。
- `s2_query_stat_info`：与 dimensions/05 §5 全部一致。**增量发现：trace_id 列存在但代码硬编码写空串**（StatUtils.java:102/:164 `String traceId = ""`【复核 ✔】）——分布式追踪链是断的，chat 侧 question_id 与 headless 侧 stat 行也无外键/ID 关联。

### 4.4 LLM 调用计量：❌ 无

chat 逐轮只有 parse_time_cost（耗时分解）；全仓无 token/cost/模型调用次数表。「可回放（SQL 血统全留）但不可计费」，与 dimensions/05 §9 公约数结论吻合。

## 5. 写入策略与迁移机制

### 5.1 批量写与事务边界

- 常规 CRUD 全走 MyBatis-Plus BaseMapper；手写 XML 只留给复杂批量：batchSaveParseInfo（foreach 多值 insert）、Metric/DimensionDOCustomMapper 的 batchInsert/batchUpdate/**batchUpdateStatus**/**batchPublish**——语义层的批量上下架/发布是显式 SQL 操作。
- **全仓仅 2 处 @Transactional**：ModelServiceImpl.createModel/updateModel（:89/:118）——model+dimension+metric 三表联动建模的原子性。chat 链路（query→parse→context→memory 多表写）**无事务包裹**：查询型短流程，行级失败容忍（parse 失败时 s2_chat_query 行保留即审计留痕）。
- 异步旁路：StatUtils 用 **TransmittableThreadLocal\<QueryStat\>**（:40-41）贯穿查询线程收集，finally 时 `CompletableFuture.runAsync` 异步落库、异常仅 warn——审计不占查询延迟，fail-open。

### 5.2 软删除约定（三套并存）

① chat 会话/查询用专用标记列（s2_chat.is_delete、s2_chat_query.query_state=0）；② 语义层用 status tinyint（0 正常 1 下架 + batchUpdateStatus）；③ memory 用字符串状态机（PENDING/ENABLED/DISABLED，迁移驱动向量库增删）。

### 5.3 审计列惯例

语义层/系统域：created_by/created_at/updated_by/updated_at 几乎全表（例外：s2_model_rela 无审计列）；chat 域：s2_chat_parse/s2_chat_query 用 user_name/create_time。s2_user.password 为 md5+salt（schema:387-388）。

### 5.4 迁移机制：纯手工，无版本框架

- **无 Flyway/Liquibase**（pom grep 零命中）。启动时 `spring.sql.init`（postgres profile `mode: always` + `continue-on-error: true`）执行幂等 DDL（全 `CREATE TABLE IF NOT EXISTS`）+ demo 数据。
- 升级靠两处手工资产：`db/schema-*.sql` 直接改全量建表脚本；`config.update/sql-update-mysql.sql` **手工累积的增量升级脚本**（36 条 ALTER/CREATE，日期注释分段），`config.update/data-update.txt` 甚至记录运维指令。无 baseline 校验、无回滚、跨版本升级全凭人肉。

## 6. 生命周期：清理、归档与兜底重灌

| 机制 | 内容 | 证据 |
|---|---|---|
| chat 数据清理/归档 | ❌ **无任何 retention/归档任务**（@Scheduled 全清单仅 5 个，无一清理 chat 表）。数据只增不减，query_result mediumtext 全量存数据行，库会持续膨胀 | grep @Scheduled 全量核对 |
| 向量库兜底①（记忆） | CommandLineRunner `loadSysExemplars` 启动重灌全部 ENABLED 记忆 | MemoryServiceImpl.java:223-241 |
| 向量库兜底②（元数据） | MetaEmbeddingTask 启动+每 2h 重灌 meta_collection；InMemory 后端每小时+@PreDestroy persistFile | MetaEmbeddingTask.java:55-90 |
| 词典兜底 | DictionaryReloadTask 启动+每 1min reload HanLP；维度值词典每日 0 点重建（backup 目录先行） | DictionaryReloadTask.java:35-44 |
| 记忆评审 | MemoryReviewTask 每 60s（dim 03 已挖） | MemoryReviewTask.java:63 |

## 7. 借鉴意义（企业级 agent：Java/Spring 服务端 + Web，同栈直接对码）

**照搬**：
1. **候选解析落库 + SQL 血统四段留痕**（SqlInfo：parsed→corrected→physical→llm-optimized）——LLM 中间产物全量持久化，事后审计/回归测试/坏例分析有据可查，且 parse/execute 分离使「解析产物」天然成为恢复点。
2. **TTL 收集 + 异步旁路审计**（StatUtils 模式）：TransmittableThreadLocal 贯穿请求线程 → finally 异步落库 fail-open——Java 服务加 LLM 审计/计量的最小侵入模板。
3. **真相源在 SQL、向量库可重灌**：元数据/记忆全部 SQL 表为真相源，向量索引启动+定时重建双兜底。
4. **created_by/updated_by + status 软删**的元数据表纪律（含 batchUpdateStatus 显式 SQL）。
5. **先插行拿主键再处理**（createChatQuery 在 parse 前落 query_state=1 占位行）——LLM 长流程的「请求已受理」留痕，失败也有尸检材料。

**改造**：
6. **query_result 全量 JSON 入 mediumtext**：数据行/列 schema/权限回执全塞一列——应裁剪为「结果摘要入库 + 明细对象存储/列存，query_result 存指针」。
7. **事务边界**：仅建模链有 @Transactional，chat 多表写无包裹；企业级应按聚合根（一轮问答）补事务或改事件驱动最终一致。
8. **手工迁移**：schema.sql + config.update 手写增量 → 换 Flyway（baseline 现有 schema 即可），`continue-on-error: true` 掩盖漂移要去掉。
9. 凭据加密 AES-ECB → KMS/AES-GCM；s2_user md5+salt → bcrypt/argon2。

**补缺**：
10. **LLM token/成本计量表完全没有**——需新增（参照 codex 六分类 token 公约数）。
11. **trace_id 列存而不用**（写死空串）且 chat.question_id ↔ stat 行无关联——补全后才能做「一次问答的端到端追踪」。
12. **chat 数据保留/归档**：无任何清理任务，需补 TTL/归档策略。
13. **s2_chat_statistics 死表与遗留 mapper**（ChatMapper.xml 引用已不存在的列）——迁移前应清死代码。

## 8. 抽查复核记录（2026-09-22）

6 条载荷最重证据全部命中：SqlInfo 四段字段（SqlInfo.java:12-21 逐一实存）、createChatQuery 先插行（ChatQueryServiceImpl.java:113）、batchSaveStatistics 死表（全仓 grep 仅接口/实现/Mapper 自引用，无调用方）、trace_id 空串（StatUtils.java:102/:164）、s2_chat_memory 与 s2_query_stat_info 对 dimensions/03·05 逐列核对一致、@Scheduled 清单核对（无 chat 清理任务）。

---

## 附录 A：chat 域逐表全字段（schema-mysql.sql 行号）

**s2_chat**（:52-63）：chat_id bigint PK AI / agent_id / chat_name varchar(300) / create_time / last_time / creator varchar(30) / last_question varchar(200)（冗余）/ is_delete tinyint（软删）/ is_top tinyint（置顶排序）。

**s2_chat_query**（:123-138）：question_id bigint PK AI（=全程 queryId）/ agent_id / create_time（ON UPDATE）/ **query_text mediumtext** / user_name varchar(150) / **query_state int**（1 有效/0 删除）/ chat_id / **query_result mediumtext**（QueryResult 全量 JSON，见 §2.3）/ score int（点赞点踩）/ feedback varchar(1024) / similar_queries varchar(1024)（相似问召回 JSON）/ parse_time_cost varchar(1024)（mapTime/parseTime/sqlTime 分段计时 JSON）。

**s2_chat_parse**（:110-120）：question_id（FK s2_chat_query）/ chat_id / **parse_id**（候选序号，与 question_id 组成业务键）/ create_time / query_text varchar(500)（冗余）/ user_name / **parse_info mediumtext NOT NULL**（SemanticParseInfo 全量 JSON：SqlInfo 四段 + metrics/dimensions/dimensionFilters/dateInfo/score/elementMatches/sqlEvaluation）/ is_candidate int（1 候选/0 默认选中）；KEY commonIndex(question_id)。

**s2_chat_context**（:100-108）：chat_id PK（每会话一行）/ modified_at（ON UPDATE）/ query_user / query_text（上一问）/ **semantic_parse text**（上一轮 SemanticParseInfo JSON，多轮上下文）/ ext_data。写入：insertOrUpdate upsert。

**s2_chat_memory**（:80-98）：全字段已挖于 dimensions/03 §7（id/question varchar(655)/side_info/query_id/agent_id/db_schema/s2_sql/status/llm_review/llm_comment/human_review/human_comment/审计四列），核对一致，不重抄。

**s2_chat_model**（:153-166）：id PK / name / description / **config text NOT NULL**（ChatModelConfig JSON：provider/baseUrl/apiKey/temperature…）/ 审计四列 / admin/viewer varchar(500) / is_open。Web 端热配 LLM。

**s2_chat_config**（:65-78）：id / model_id（指向语义模型）/ chat_detail_config / chat_agg_config（明细/聚合模式展示配置 mediumtext）/ recommended_questions / llm_examples / status tinyint（0 删除 1 生效）/ 审计四列。

**s2_chat_statistics**（:141-151）：question_id（KEY）/ chat_id / user_name / query_text varchar(200) / interface_name / cost int(6) / type / create_time——**死表无写入方**（§4.3）。

## 附录 B：语义层核心表逐表全字段（口径知识真相源）

**s2_domain**（:238-255）：id PK / name / biz_name / parent_id（主题域树）/ status / 审计四列 / admin/admin_org/viewer/view_org varchar(3000)（四列权限）/ is_open / **entity varchar(500)**（主题域实体 JSON）。

**s2_model**（:286-313）：id PK / name / biz_name / domain_id / alias / status / description / viewer/view_org/admin/admin_org varchar(500) / is_open / 审计四列 / **entity text** / drill_down_dimensions TEXT / database_id（→s2_database）/ **model_detail text NOT NULL**（ModelDetail JSON：sqlQuery/tableQuery 受控视图、identifiers/dimensions/measures/fields、sqlVariables）/ source_type / depends / **filter_sql varchar(1000)**（固定行过滤）/ tag_object_id / ext。

**s2_model_rela**（:403-411）：id PK / domain_id / from_model_id / to_model_id / join_type / **join_condition text**（join 表达式，Calcite 织 join 用）；无审计列、无 status。

**s2_dimension**（:213-236）：id PK / model_id / name / biz_name（物理字段名）/ description / status（0 正常 1 下架）/ **sensitive_level int**（列权限判据）/ type（categorical/time）/ type_params / data_type（varchar/array）/ **expr text NOT NULL** / 审计四列 / **semantic_type**（DATE/ID/CATEGORY）/ alias varchar(500) / default_values / **dim_value_maps varchar(5000)**（维度值→业务名映射，值级口径）/ is_tag / ext。

**s2_metric**（:258-283）：id PK / model_id / name / biz_name / description / status / **sensitive_level tinyint NOT NULL** / type / **type_params text NOT NULL**（MetricDefineParams JSON：MEASURE 聚合/FIELD 表达式/METRIC 派生）/ 审计四列 / data_format_type（DECIMAL/PERCENT）/ data_format / alias / classifications / relate_dimensions / ext / **define_type**（MEASURE|FIELD|METRIC）/ **is_publish**（发布开关）。

**s2_term**（:518-531）：id PK / domain_id / name / description / **alias varchar(1000)** / **related_metrics varchar(1000)** / **related_dimensions varchar(1000)**（术语→口径挂接，进 prompt 的 DomainTerms）/ 审计四列。

**s2_data_set**（:450-467）：id PK / domain_id / name / biz_name / description / status / alias / **data_set_detail text**（跨模型逻辑视图：metricIds/dimensionIds）/ 审计四列 / **query_config varchar(3000)**（默认时间/聚合配置）/ admin/admin_org varchar(3000)。LLM 选域与权限的最小单元。

**s2_database**（:168-183）：id PK / name / description / version / type（mysql/clickhouse/…14 引擎）/ **config text NOT NULL**（JDBC 连接 JSON，password AES-ECB 加密存储）/ 审计四列 / admin/viewer / is_open。

## 附录 C：其余域表名+用途清单

| 表 | 行号 | 用途 |
|---|---|---|
| s2_agent / s2_plugin | :1-24 / :315-330 | 见 §4.1/4.2 |
| s2_dictionary_conf / s2_dictionary_task | :185-195 / :198-210 | 维度值词典配置 / 构建任务流水（status+elapsed_ms） |
| s2_user / s2_user_token | :382-394 / :533-547 | 用户（md5+salt 密码）/ API 令牌（expire_time+expire_date_time 双过期） |
| s2_system_config | :396-401 | 系统管理员 + parameters（全局配置 JSON） |
| s2_auth_groups | :26-30 | 行权限组（config varchar(2048)，AuthGroup/AuthRule JSON 载体） |
| s2_collect | :413-420 | 用户收藏（type+collect_id 通用收藏） |
| s2_available_date_info | :33-49 | 维度可用时间窗（date_format/period/start/end/unavailable_date），时间修正器数据源 |
| s2_query_rule | :499-516 | 查询规则（rule_type/priority/rule JSON/action JSON），翻译期改写 |
| s2_tag / s2_tag_object | :469-479 / :481-497 | 标签 / 标签对象（半成品态） |
| s2_canvas | :369-380 | 建模画布配置（domain_id+type+config） |
| s2_metric_query_default_config | :422-431 | 每用户每指标默认查询配置 |
| s2_app | :433-448 | headless OpenAPI 应用（app_secret/qps/end_date） |
| s2_query_stat_info | :332-367 | 已挖于 dimensions/05 §5，核对一致；增量：trace_id 实写空串 |
