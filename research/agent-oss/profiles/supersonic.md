# supersonic 解剖档案

> 基线：~/develop/opensource/supersonic @ 6919ac50b (2026-09-08)；canonical tencentmusic/supersonic。**状态备注：维护模式**——正式 release 停在 2024-11 v0.9.8、近两年无发版、单人维保（master 持续小步提交但无版本化）；pom `revision=1.0.0-SNAPSHOT`。只作 ChatBI/语义层架构参考，不构成生产选型推荐。技术栈 Java 21 + Spring Boot 3.3.9，是本组唯一 Java 系样本，参考价值直接。

## 1. 产品定位与形态

- 定位：**Chat BI + Headless BI 二合一平台**（README.md:5 "unifies Chat BI (powered by LLM) and Headless BI (powered by semantic layer)"）。核心论点：LLM 直接生成物理 SQL 不可靠 → 把「业务口径」固化为语义层（semantic layer），LLM 只做 NL→语义查询（S2SQL），join/公式/聚合下推给确定性翻译层——「reduce hallucination + reduce complexity」（README.md Motivation）。
- 双界面：业务用户走 Chat BI（自然语言查询+可视化）；分析工程师走 Headless BI 建模界面（模型/维度/指标/术语管理）。交互形态为 Web（React 前端 + REST/Swagger），也提供 headless REST API 供程序化语义查询。
- 目标用户：企业内数据消费方 + 数据建模方；腾讯音乐内部产品同源。

## 2. Agent 执行架构（★重点：双层编排 + 显式状态机）

### 2.1 chat 层：parse / execute 两阶段 + 责任链

入口 `chat/server/.../service/impl/ChatQueryServiceImpl.java`【核心】：

- `parse(ChatParseReq)`：先 `chatManageService.createChatQuery` 落库拿到 queryId，然后遍历 `ChatQueryParser` 责任链（`parser.accept(ctx)` 过滤），再过 `ParseResultProcessor` 后处理链，最后 `batchAddParse` 持久化候选解析（:109-138）。
- `execute(ChatExecuteReq)`：按用户在前端选中的 (queryId, parseId) 取回 `SemanticParseInfo`，遍历 `ChatQueryExecutor` 链执行，再过 `ExecuteResultProcessor` 链（推荐维度/指标、环比计算、数据解读摘要），`saveQueryResult` 落库（:141-164）。
- 组件链通过 `chat/server/.../util/ComponentFactory.java` 加载，底层是 **SpringFactoriesLoader**（Spring 版 SPI，META-INF/spring.factories）——README 宣称的 "Java SPI" 实际载体【核心】。
- parser 链：`PlainTextParser` → `NL2PluginParser`（插件召回）→ `NL2SQLParser`（主路：调 headless 层）；executor 链：`PlainTextExecutor` / `PluginExecutor` / `SqlExecutor`【核心】。
- **parse 与 execute 分离 + 多候选让人选**：parse 产出多个 `SemanticParseInfo`（带 score/sqlWeight），前端展示候选，用户点选后才执行——这是 ChatBI 版的 HITL（见维度 5）。

### 2.2 headless 层：ChatWorkflowEngine 显式状态机（图编排的 Java 最小实现）

`headless/server/.../utils/ChatWorkflowEngine.java`【核心】——`while (state != FINISHED)` 的 switch 状态机，状态枚举 `ChatWorkflowState`：

```
MAPPING → PARSING → S2SQL_CORRECTING → TRANSLATING → PHYSICAL_SQL_CORRECTING → FINISHED
```

- **MAPPING**（Schema Mapper）：`CoreComponentFactory.getSchemaMappers()` 依次跑（`mapper/map(ctx)`）。映射器（`headless/chat/.../mapper/`）：`EmbeddingMapper`（向量召回）、`KeywordMapper`、`QueryFilterMapper`、`PartitionTimeMapper`、`TermDescMapper`、`AllFieldMapper`；匹配策略 `HanlpDictMatchStrategy`（HanLP 自定义词典）/`EmbeddingMatchStrategy`/`DatabaseMatchStrategy`。产出 `SchemaMapInfo`（queryText 命中了哪些数据集/指标/维度/维度值/术语）。映射为空 → 直接 FAILED 终态（:45-52）——**LLM 前置的受控词汇表闸门**。
- **PARSING**（Semantic Parser）：规则解析器（`parser/rule/`、`query/rule/`：metric/detail 等查询模式）+ `LLMSqlParser`（见 2.3）并行产出候选 `SemanticQuery`，空则 FAILED（:54-70）。
- **S2SQL_CORRECTING**：语义级修正器链（`corrector/`：Grammar/Schema/Time/Where/Having/GroupBy/Agg/Select + `LLMSqlCorrector`）修正 S2SQL。
- **TRANSLATING**：`semanticQuery.buildSemanticQueryReq()` → `SemanticLayerService.translate()`（进 2.4 翻译层）把 S2SQL→物理 SQL（:126-169）。
- **PHYSICAL_SQL_CORRECTING**：`LLMPhysicalSqlCorrector`（LLM 做 SQL **性能**优化，prompt 硬约束"不得增删字段、逻辑等价"，默认 `enable(false)`，:171-191）。

状态机由 `S2ChatLayerService.parse()` 驱动（`headless/server/.../facade/service/impl/S2ChatLayerService.java:67-77`）——若上游已带 MapInfo（如缓存/重试）可直接从 PARSING 进入。**这是手写状态机而非图框架**：无可视化编辑、无持久化 checkpoint、无回溯分支，但状态显式、可枚举、每步可插桩计时（`ParseResp.parseTimeCost` 分段记 mapTime/parseTime/sqlTime）。

### 2.3 LLM 调用层：LLMSqlParser + One-Pass Self-Consistency

- `headless/chat/.../parser/llm/LLMSqlParser.java`【核心】：`text2SQLType.enableLLM()` 开关 → `DataSetResolver`（HeuristicDataSetResolver 启发式选数据集）→ `LLMRequestService.runText2SQL` → 失败重试（`recallMaxRetries`，温度 0 时重试前抬到 0.5 增加随机性，:74-80）→ `getDeduplicationSqlResp` 去重 → 每条候选 `addParseInfo`（带 sqlWeight）。
- `OnePassSCSqlGenStrategy.java`【核心】：单次请求内做 self-consistency——prompt 模板 `INSTRUCTION`（#Role/#Task/#Rules/#Exemplars/#Query），规则第一条即 "**SQL columns and values must be mentioned in the `Schema`, DO NOT hallucinate**"；输出用 langchain4j `AiServices` 结构化抽取（`SemanticSql{thought, sql}`）。few-shot 由 `PromptHelper.getFewShotExemplars` 组装：动态召回（向量）+ 每条 self-consistency 路径 shuffle 不同 exemplar 子集（`PromptHelper.java:33-81`）。
- prompt 的「Schema」由 `PromptHelper.buildSchemaStr`（:105-160）从语义模型序列化：metric → `<name ALIAS '..' FORMAT '..' COMMENT '..' AGGREGATE 'SUM'>`，dimension → `<name ALIAS '..' DATATYPE '..' COMMENT '..'>`，外加 `buildSideInformation` 注入 CurrentDate/PriorKnowledge/**DomainTerms**（术语字典直译进 prompt）。**口径约束 = 元数据→prompt 的单向生成**，LLM 看不到物理表。
- 每个 LLM 环节是一个可注册开关的 "ChatApp"：`ChatAppManager.register(APP_KEY, ChatApp(prompt, enable))`（如 S2SQL_PARSER / MEMORY_REVIEW / PHYSICAL_SQL_CORRECTOR）——prompt 集中治理+运行时开关。

### 2.4 翻译与执行（确定性层）

- `headless/core/.../translator/DefaultSemanticTranslator.java`【核心】：QueryParser 责任链（`SqlQueryParser`/`StructQueryParser`/`MetricExpressionParser` 指标展开/`MetricRatioParser` 环比/`DimExpressionParser`/`OntologyQueryParser`）→ **Apache Calcite**（`translator/parser/calcite/`：`S2CalciteSchema`/`S2CalciteTable`/`SqlBuilder` 把逻辑模型织成带 join 的物理计划）→ QueryOptimizer 链改写 → 物理 SQL。本体（ontology）表合并用 `WITH table AS (模型SQL) 外层SQL`（:65-80）。
- 执行 `headless/core/.../executor/JdbcExecutor.java`【核心】：先过 `QueryAccelerator`（查询加速/缓存命中直接返回），再 `SqlUtils.init(database).queryInternal(sql)` 经 JDBC 执行。方言适配 `adaptor/db/DbAdaptorFactory`——14 个引擎 adaptor（ClickHouse/MySQL/PostgreSQL/Oracle/H2/Duckdb/Hanadb/Kyuubi/Presto/Starrocks/Trino…）【核心】。
- 执行结果回 chat 层过 `ExecuteResultProcessor`（`MetricRecommendProcessor`/`DimensionRecommendProcessor`/`MetricRatioCalcProcessor`/`DataInterpretProcessor` LLM 文本摘要）。

**多 agent 分工**：无。单一 agent 概念 `chat/server/.../agent/Agent.java` 只是**入口配置对象**（绑定可见数据集 DatasetTool、插件 PluginTool、可视化配置 VisualConfig、prompt），不是自治 agent；agent 间无通信。

## 3. 技术底座

- Java 21 + Spring Boot 3.3.9（parent pom）；Maven 五模块：`common` / `auth` / `chat`（api+server）/ `headless`（api+chat+core+server）/ `launchers`（standalone+chat+headless 三启动器）（pom.xml【核心】）。
- LLM 抽象：**langchain4j**（`dev.langchain4j` ChatLanguageModel / AiServices / PromptTemplate，见 OnePassSCSqlParser、MemoryReviewTask 等 import）——多 provider 路由 `ModelProvider` + Web 端 `ChatModelController` 动态配模型。交叉引用 `research/agent-framework/profiles/langchain4j.md`（本仓只把它当 LLM client + 结构化输出用，未用其 agent 抽象）。
- 向量库：langchain4j EmbeddingStore 多实现工厂（`common/src/main/java/dev/langchain4j/{chroma,milvus,opensearch,...}/spring/`）【核心】；docker-compose 默认 pgvector。
- NLP：HanLP portable 1.8.4（自定义词典做 schema/维度值匹配）；SQL 处理：jsqlparser 4.9 + Calcite；ORM：MyBatis(-plus) + PageHelper。
- **不用任何 agent 编排框架**（无 LangGraph4j/spring-ai）：编排=手写状态机+责任链。与 spring-ai 档案（`research/agent-framework/profiles/spring-ai.md`）的关系：supersonic 未走 spring-ai 路线，其 langchain4j 用法仅是传输层——与 ai-hedge-fund 对 langchain 的用法同构。

## 4. 状态与持久化

- 元数据库（MySQL 兼容；standalone 默认 H2、可切 postgres profile）：语义层表全在 `headless/server/.../persistence/dataobject/`——`ModelDO`/`DimensionDO`/`MetricDO`/`TermDO`/`DataSetDO`/`DomainDO`/`ModelRelaDO`/`DatabaseDO`/`QueryRuleDO`/`TagDO`/`DateInfoDO`/`DictConfDO`/`DictTaskDO`【核心】。
- 会话状态（chat 侧，`chat/server/.../persistence/dataobject/`）：`ChatDO`（会话）→ `ChatQueryDO`（每轮问题+最终结果 JSON）→ `ChatParseDO`（每次 parse 的候选）；`ChatContextDO` 存多轮上下文（指代消解/时间继承，`ChatContextService` 维护）；`StatisticsDO`/`QueryDO` 行为埋点【核心】。
- **查询审计**：`headless/server/.../dataobject/QueryStatDO.java`——traceId/queryUser/modelId/querySqlCmd+md5/querySql+md5/queryType/elapsed 等（每次语义查询全量留痕，含最终 SQL）【核心】。
- **Chat Memory（few-shot 例句库）**：`ChatMemoryDO`（question/sideInfo/dbSchema/s2sql/status/llmReviewRet/llmReviewCmt/humanReviewRet/humanReviewCmt）；`MemoryServiceImpl`：ENABLED 的记忆同步进向量库供 few-shot 召回，状态迁移时同步增删向量（`MemoryServiceImpl.java:44-100`）【核心】。
- 缓存：`headless/core/cache` + QueryAccelerator（SQL 结果加速）；词典任务 `DictTaskDO`（维度值词典定时重建）。
- ❌ 无执行 checkpoint/回放/中断恢复——查询型短事务，parse/execute 已落库本身即是恢复点（execute 按 parseId 重取）。

## 5. HITL 与风控 ★重点

- **无审批门**（纯查询场景无写操作），HITL 形态有三：
  1. **多候选人工选解**：parse 产出多候选 → 前端展示（含每条的 S2SQL/条件）→ 用户点选 parseId 才 execute；执行前还能改 filter/指标——`queryData` 里 `replaceFilters`/`replaceMetrics` 用 jsqlparser 重写 S2SQL 后**重新翻译再执行**（`ChatQueryServiceImpl.java:247-274`）【核心】。
  2. **记忆双审（LLM 预审 + 人工终审）**：`MemoryReviewTask`（@Scheduled）用 LLM 按固定格式 `opinion=(POSITIVE|NEGATIVE),comment=` 评审候选例句 → 人工在 MemoryController 复核 → ENABLED 才进向量库影响后续 prompt（`memory/MemoryReviewTask.java` + `MemoryServiceImpl`）【核心】——few-shot 知识的**合规准入流水线**。
  3. **解析反馈**：`needFeedback` 标记 + 前端点赞/纠错（落到 memory/统计）。
- **数据权限（三层，AOP 实现）**：`headless/server/.../aspect/S2DataPermissionAspect.java`【核心】，`@Around("@annotation(S2DataPermission)")` 织入查询服务：
  1. 模型 admin 直通；2. 模型可见性（VIEWER 校验，不可见抛 InvalidPermissionException）；3. **列权限**：`sensitiveLevel=HIGH` 的维度/指标（DimensionDO/MetricDO 字段）必须在用户授权资源集内，否则报"存在以下敏感资源…请联系管理员"（:127-149）；4. **行权限**：AuthGroup/AuthRule/DimensionFilter（`auth/api/.../authorization/pojo/`）表达为 SQL 片段，`SqlAddHelper.addWhere` 用 jsqlparser **改写 SQL 强制注入 WHERE**（OR 连接多组授权表达式）（:192-226）；5. **结果透明化**：`addHint` 在 SemanticQueryResp 里附 `QueryAuthorization`（"当前结果已经过行权限过滤，详细过滤条件如下…申请权限请联系管理员"，:322-350）【核心】——**权限过滤对用户可解释**，合规报告可直接引用。
- LLM 输出防幻觉：prompt 规则硬约束（"DO NOT hallucinate"）+ AiServices 结构化输出 + `S2ChatLayerService.validate`（SqlEvaluation 校验 SQL 合法性）+ 修正器链兜底。
- ⚠️ 用户体系单薄：`UserStrategy`（FakeUserStrategy / HttpHeaderUserStrategy）——默认可信 HTTP 头注入用户名，生产需置前于网关做认证。

## 6. 工具与业务系统集成（★B 组重点：语义层即工具层）

supersonic 没有通用 tool-calling；**「工具」= 语义层元数据 + 受限 DSL + 插件**。

### 6.1 语义层元模型（业务口径的固化载体）

分层（自下而上）【核心，`headless/api/.../pojo/` + dataobject】：

| 概念 | 载体 | 关键字段 |
|---|---|---|
| 数据源 | `DatabaseDO`（config JSON 含连接串，password AES 加密） | type/version/admin/viewer |
| 模型 Model | `ModelDO` + `ModelDetail.java` | sqlQuery/tableQuery（**建模 SQL/表，即受控视图**）、filterSql（固定行过滤）、identifiers/dimensions/measures/fields、sqlVariables |
| 维度 Dimension | `DimensionDO` | expr、dataType、semanticType、alias、defaultValues、dimValueMaps（**维度值→业务名映射**）、sensitiveLevel |
| 指标 Metric | `MetricDO` + `MetricDefineBy{Metric,Measure,Field}Params` | defineType 三类：**MEASURE（度量聚合）/ FIELD（字段表达式）/ METRIC（指标套指标——派生口径）**、typeParams.expr、defaultAgg、dataFormat（DECIMAL/PERCENT 格式化）、classifications、alias、sensitiveLevel、isPublish |
| 术语 Term | `TermDO` | name/description/alias/**relatedMetrics/relatedDimensions**（术语挂到指标/维度，进 prompt 的 DomainTerms） |
| 数据集 DataSet | `DataSetDO` | 跨模型逻辑视图 + QueryConfig（默认时间/聚合配置）+ 权限单元 |
| 主题域 Domain | `DomainDO` | 组织维度，Term 挂在 Domain 下 |

**口径统一机制（财务报表刚需）**：① 指标唯一定义处（含 expr+defaultAgg+格式），查询方只能引用不能改写——`MetricExpressionParser` 在翻译期统一展开，LLM 输出的 S2SQL 只写逻辑指标名；② `MetricDefineByMetricParams` 支持指标派生（毛利率=利润/收入 建成新指标而非查询时现算）；③ `dimValueMaps` 把 "华南"→"guangdong,guangxi" 这类值级口径固化；④ `TermDO` 术语字典把黑话（"营收"→相关指标）注入 prompt；⑤ 版本字段 createdAt/createdBy/updatedAt/updatedBy + isPublish 全元数据都有——**口径变更有留痕但无审批流**（发布开关是布尔，不是流程）。

### 6.2 NL→语义查询→SQL 的转换受控面

- LLM 产出 **S2SQL**（语义层方言：逻辑列名+指标名，无 join、无物理表、无方言函数）；join（ModelRelaDO 模型关系）、指标展开、方言适配全部在 Calcite/jsqlparser 确定性层完成——**LLM 的自由度被 DSL 边界钳住**。
- 词汇命中前置：SchemaMapper（HanLP 词典 + 向量）先把 queryText 映射到 SchemaElement，未命中词汇 LLM 也写不进合法 S2SQL（Schema 校验 corrector 兜底）。

### 6.3 插件（Chat Plugin）

`chat/server/.../plugin/`：ChatPlugin（type=webpage/webservice）+ PluginRecognizer（LLM/embedding 判断是否走插件）+ PluginExecutor——把第三方工具描述+示例问题交给 LLM 选择【核心】。这是唯一的 tool-selection 形态，但插件是查询旁路，不触碰主 SQL 管线。

### 6.4 数据源连接与隔离

- 凭据：`DatabaseResp.passwordDecrypt()` = `AESEncryptionUtil.aesDecryptECB(password)`（`headless/api/.../response/DatabaseResp.java:75-76`）【核心】——⚠️ **AES-ECB 模式**（无 IV、弱于 GCM），存 DB 的 config JSON 内；无 KMS/密管集成。
- 只读性：查询路径全为 SELECT；模型本身即"SQL 视图"（ModelDetail.sqlQuery + filterSql），物理表不直接暴露。❌ 无显式 JDBC readonly 标志、无 SQL 白名单校验器拦截非 SELECT（依赖上游查询构造不出写语句）。

## 7. 部署与产品化

- 启动器三选一（`launchers/`）：`standalone`（单进程 9080，默认 H2，`application-postgres.yaml` 切 PG）；`chat` 与 `headless` **可拆分部署**（各自 application.yaml，spring.application.name 分别为 chat/headless）——chat↔headless 走 facade 接口（同进程 @Autowired 或跨进程序列化，拆分粒度是模块级微服务）【核心】。
- docker-compose（`docker/docker-compose.yml`）：pgvector/pg17（元数据+向量一体）+ `supersonicbi/supersonic` 单容器（2CPU/2G），全栈一个 9080 端口【核心】。
- 前端 webapp：React monorepo（webapp/packages/chat-sdk）。REST 全 Swagger 暴露（springdoc）。
- 多租户：❌ 无租户隔离；用户/组织（auth 模块）+ 模型级 admin/viewer/group 授权。
- 可观测：`keyPipeline` 专用 logger（关键管线日志分离）+ QueryStat 统计表 + ParseTimeCost 分段计时；LLM 模型配置（`ChatModelController`）与 prompt（ChatAppManager）均 Web 端热配。
- 成本控制：temperature/prompt 长度（fewShotNumber/selfConsistencyNumber/exemplarRecallNumber 均参数化，`ParserConfig`）。

## 8. 对本项目的适用性（Java + 独立部署 API + 图编排 + 财务合规）

**可借鉴模式（→类/模块路径）**：

1. **语义层受控词汇表**（最高价值）：财务口径（科目/期间/币种/抵消规则）建成 Metric/Dimension/Term 元数据，prompt 由元数据单向生成（`PromptHelper.buildSchemaStr/buildSideInformation`），LLM 生成受限 S2SQL 而非直连物理库。财务"指标口径统一"的可运行答案。
2. **显式状态机编排**：`ChatWorkflowEngine` 的 while-switch 状态机 + 责任链，是 Java 图编排的最小可用实现——状态枚举可审计、每段计时、失败即终态。若上 LangGraph4j/spring-ai graph，这套状态划分（MAPPING/PARSING/CORRECTING/TRANSLATING）可直接映射为节点。
3. **AOP 数据权限 + 结果透明 hint**：`@S2DataPermission` 注解 + `S2DataPermissionAspect`（列敏感级/行级 WHERE 注入/QueryAuthorization 回执）——财务 agent 的"数据可见性合规"可直接抄结构：权限在执行边界强制注入而非依赖 prompt 约束，且**过滤行为对用户可解释**。
4. **记忆双审准入**：`MemoryReviewTask`（LLM 预审）→ 人工复核 → 才进向量库当 few-shot——财务场景知识/例句的生产准入流水线原型。
5. **ChatAppManager prompt 注册表**：每个 LLM 环节 = APP_KEY + prompt + enable 开关，Web 端热配——prompt 变更治理雏形（缺版本化，需补）。
6. **parse/execute 分离 + 候选可改写**：解析产物落库、人工选定、改 filter 后重建执行——天然适配"审批后再执行"的财务交互（把"人选候选"升级为"审批人签核"即成审批门）。
7. **SpringFactoriesLoader 组件化**：parser/corrector/processor 全部 spring.factories 插件化，扩展不动核心——Java 服务工程化模板。

**不可迁移点**：纯查询型无写入/审批流/长程任务；无多 agent 协作与 checkpoint；行权限依赖管理员手写 SQL 片段（DimensionFilter.expressions 是裸 SQL 字符串，注入面依赖信任边界）。

**避坑**：① AES-ECB 存凭据（应 KMS/GCM）；② 默认 H2/standalone 是 demo 形态，生产必须拆 chat/headless + 外置 PG；③ `LLMPhysicalSqlCorrector` 让 LLM 二次改写物理 SQL——语义漂移风险（其默认 enable(false) 正确，财务场景应禁用或加等价性校验）；④ 维护模式本体：借鉴模式，不引依赖。

**交叉引用**：`research/agent-framework/profiles/langchain4j.md`（LLM client 层用法）；`research/agent-framework/profiles/spring-ai.md`（本项目替代其 LLM 层的首选框架对照）；B 组横向见 `dimensions/`（ChatBI/NL2SQL 产品形态）。
