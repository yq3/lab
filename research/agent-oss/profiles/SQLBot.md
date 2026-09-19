# SQLBot 解剖档案

> 基线：~/develop/opensource/SQLBot @ ba9aa5db (2026-09-11)；canonical dataease/SQLBot；**许可 NOASSERTION**（GitHub 显示无声明文件——DataEase 系惯常为 GPLv3+附加条款，商用集成前必须核验官方许可原文，下文适用性按此风险标注）。fit2cloud（飞致云）商业公司开源的 ChatBI 产品，闭源扩展包 `sqlbot-xpack`（pyproject 从私有 index 安装）承载许可证校验、行列权限、部分加密与登录——**「细粒度数据权限」等 README 卖点的实现不在本仓库**，引用时注意区分。

## 1. 产品定位与形态

- 定位：基于 LLM + RAG 的「智能问数系统」（ChatBI）——自然语言提问 → 生成 SQL → 执行 → 图表 → 智能分析/预测（README.md、`backend/apps/chat/`）。
- 交互形态：Web（Vue 前端 + FastAPI 后端 8000/8001）、MCP 协议对外（`backend/apps/mcp/mcp.py`，供 Dify/MaxKB/n8n 调用）、Web/弹窗嵌入与 assistant API（外部应用携带 `X-SQLBOT-ASSISTANT-CERTIFICATE` 证书头动态接入数据源，`backend/common/core/deps.py#get_current_assistant`）。
- 目标用户：企业数据分析消费者；产品形态是「只读问答 SaaS」，**没有任何写数据源的操作面**——这决定了它的风控设计（见维度 5）。

## 2. Agent 执行架构（★NL2SQL 管线）

### 多段 LLM 流水线（非 agent、非图编排）

核心 1979 行的 `LLMService.run_task`（`backend/apps/chat/task/llm.py:1236`），一次问答按序经过最多 6 次 LLM 调用，全部流式：

1. **选数据源**（`select_datasource`）：未绑定数据源时 LLM 从工作空间数据源清单里选（清单先经 embedding 相似度过滤 `get_ds_embedding`）；单数据源跳过。
2. **RAG 上下文准备**（构造期+`filter_*_template`）：术语库（`get_terminology_template` 按问题词匹配）、SQL 示例库（data_training few-shot）、自定义 prompt（xpack）。
3. **消息装配**（`init_messages`）：**伪对话 priming**——每块知识（规则/schema/术语/示例/自定义）都作为 Human 消息注入、紧跟一条固定的 AI 确认消息（「我已掌握所有规则……我会严格遵守」），把长上下文知识固化成"已确认对话"（`llm.py:289-305`）；历史轮次按 `chat.context_record_count` 截取且剔除系统注入消息（`sqlbot_system` 标志）。
4. **生成 SQL**（`generate_sql`）：M-Schema 格式表结构 + `<error-msg>`（**上次执行失败的错误信息跨轮回喂**，`get_last_execute_sql_error` → `chat_question.error_msg`）+ 数据量限制 XML 规则（默认 1000 条，「零容忍」措辞）+ 标识符严格保真规则（防繁简/大小写转换）。输出 JSON `{success, sql, tables, chart-type, brief}`。
5. **权限重写**：普通用户（id≠1）触发 `generate_filter`——**又一次 LLM 调用**把行权限过滤条件（xpack 的 `get_row_permission_filters`）拼进 SQL，重写后的 SQL 再次过 `check_sql`（`llm.py:1348-1368`）。
6. **执行**（`execute_sql` → `apps/db/db.py#exec_sql:763`）：先过 `check_sql_read` 硬校验（见维度 5）再执行；结果保存时 **1000 行后置截断**（`save_sql_data`，`llm.py:1164-1177`）。
7. **生成图表**（`generate_chart`）：第二次独立 LLM 会话，只喂「本次用到的表」的 schema + 上一步查询结果字段，产出 AntV 图表配置 JSON；`check_save_chart` 解析校验。
8. **渲染图片**（`request_picture`）：调 **g2-ssr**（独立 Node.js 服务，`g2-ssr/`，AntV G2 + pm2）出 PNG。
9. 可选后续动作：`/analysis` 智能分析、`/predict_data` 预测、推荐问题（各自独立 run，`run_analysis_or_predict_task`）。

### 表 schema 供给（schema linking）

- 数据源注册时同步全部表/字段到 `CoreTable/CoreField`，管理员**勾选**（`checked` 标志）暴露给 AI 的子集；列权限在读取时再过滤（`get_column_permission_fields`，xpack）。
- 表选择：表 embedding **预计算存库**（`CoreTable.embedding`），查询时 cosine 相似度排序取 top `TABLE_EMBEDDING_COUNT`（`backend/apps/datasource/embedding/table_embedding.py#calc_table_embedding:43`）——比 DB-GPT 的实时向量库轻。
- 表关系图补全：命中表后按 `ds.table_relation` 把关联表 schema 一并补进 prompt（防 JOIN 缺表，`crud/datasource.py#get_table_schema:577-607`）。

### 流式与并发

- 生产者-消费者：`ThreadPoolExecutor(max_workers=200)` 跑 run_task，chunk 暂存 `chunk_list`，`await_result` 生成器按 SSE 拉取（`llm.py:61,1204-1229`）。
- SSE 事件按阶段打 type：id/question/datasource-result/sql-result/sql/sql-data/chart-result/chart/brief/finish/error——前端能精确渲染每个中间产物。
- 失败契约：异常分类（`SingleMessageError`/`SQLBotDBConnectionError`/`SQLBotDBError`）→ `save_error_message` 落库 + error SSE；**错误信息进入下一轮 prompt 的 `<error-msg>`**，形成跨轮自纠错（轮内不重试）。

## 3. 技术底座

- Python 3.12 + FastAPI + SQLModel/SQLAlchemy；元数据库 PostgreSQL（docker-compose 内置）+ alembic 迁移。
- **langchain 仅作 LLM 传输层**（`BaseChatModel.stream`，`LLMFactory` 拼 provider 配置），无 chain/agent 机制——框架层交叉引用 agent-framework/profiles/langchain.md，此处借用极浅。
- **sqlglot 是安全关键依赖**（AST 解析校验 SQL）+ sqlparse（格式化）；orjson/pandas。
- 依赖闭源包 `sqlbot-xpack>=0.0.5.36`（permissions/SecureEncryption/license/custom_prompt/audit 资源查询）。
- 无 agent 框架、无 DAG——编排就是**一个方法里的顺序调用链**，确定性极高、可预测性极高。

## 4. 状态与持久化

- 三层记录表（`backend/apps/chat/models/chat_model.py`）：
  - `chat`（会话：oid 工作空间、绑定数据源、引擎类型、摘要、origin 标记 web/mcp/assistant）；
  - `chat_record`（每问一条：question/sql/sql_answer/chart/执行数据/错误消息/brief/起止时间）；
  - **`chat_log`（执行审计核心）**：每次 LLM/本地操作一行，`OperationEnum` 14 种操作（GENERATE_SQL/GENERATE_SQL_WITH_PERMISSIONS/GENERATE_DYNAMIC_SQL/CHOOSE_DATASOURCE/CHOOSE_TABLE/FILTER_TERMS/FILTER_SQL_EXAMPLE/EXECUTE_SQL/GENERATE_CHART/GENERATE_PICTURE/ANALYSIS/PREDICT_DATA/…），`messages` JSONB 存**完整 prompt 数组**、`reasoning_content` 存思考链、`token_usage` JSONB、起止时间、error 标志（`chat_model.py:35-85`、`llm.py` 各步骤的 `start_log/end_log`）——**每个 LLM 调用可完整回放**。
- 管理面审计另有一套：`SystemLog` + `@system_log` 装饰器（见维度 5）。
- 连接池：`ConnectionPoolManager` LRU 上限 500 池（`db.py:1153`）+ 驱动级池；scoped_session 线程绑定。
- ❌ 无 checkpoint/工作流回放；支持 `/regenerate` 从指定 record 重放（pid 过滤历史，`init_messages` 的 regenerate_record_id 分支）。

## 5. HITL 与风控（★本仓最硬的部分）

**结论：只读硬校验是代码级、AST 级、执行前置的（硬）；但行权限注入靠 LLM 重写（软），无人工审批门（产品无写面，天然不需要）。审计是两仓中最接近合规口径的双平面实现（硬）。**

### SQL 只读硬校验（`backend/apps/db/db.py#check_sql_read:1072`，exec_sql 前置强制调用）

四层递进，失败抛错拒执行：
1. **首关键词白名单/黑名单**：白名单 SELECT/WITH（配置 `SQLBOT_ALLOW_METADATA_QUERIES` 可加 SHOW/DESCRIBE/EXPLAIN）；黑名单 INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/TRUNCATE/MERGE/COPY/REPLACE/GRANT/REVOKE/USE/SET/CALL。
2. **危险模式正则**：INTO OUTFILE/INTO DUMPFILE/EXEC(/COPY TO PROGRAM（`DANGEROUS_PATTERNS`）。
3. **sqlglot AST 写类型检查**：Insert/Update/Delete/Create/Drop/Alter/Merge/Copy 任一节点即拒。
4. **方言敏感危险函数清单**：通用 + 按库（MySQL LOAD_FILE、PG pg_read_file/lo_import、SQLServer xp_cmdshell/sp_executesql、Oracle UTL_FILE/DBMS_LOCK、Hive ADD JAR 等，`COMMON_DANGEROUS_FUNCTIONS`/`DS_SPECIFIC_DANGEROUS_FUNCTIONS:1030`）。
- **表名白名单**（`llm.py#extract_tables_from_sql:71` + run_task:1333-1346）：sqlglot 解析**真实 SQL**（排除 CTE 别名）提取表名，与用户可见表清单比对，越权表直接拒——**不信任 LLM 自报的 tables 字段**，注释明写这是安全检查。

### 权限体系

- **表/字段暴露**：checked 勾选 + 列权限过滤（开源部分）。
- **行权限**：`DsPermission/DsRules/transFilterTree` 全在 xpack 闭包包内（`crud/permission.py` 仅 import 与调用点）；且注入方式是 **LLM 重写 SQL**（`generate_filter`）——过滤条件正确性依赖模型，prompt 注入可诱导丢失行过滤（表级白名单与后续只读校验兜不住行级语义）⚠️。
- 数据量：LIMIT 由 prompt 规则强制 LLM 添加 + 结果保存 1000 行后置截断（`enable_sql_row_limit` 工作空间参数 `chat.limit_rows` 可关）——**无程序化 LIMIT 注入/校验**，截断发生在数据已全量拉回之后。

### 审计（双平面）

- **执行面**：`chat_log` 逐操作完整 prompt/reasoning/token/时长/错误（见维度 4）——LLM 决策审计。
- **管理面**：`@system_log(LogConfig)` 装饰器（`backend/common/audit/schemas/logger_decorator.py:489`）——声明式挂 API 端点，记录 operation_type（LOGIN/CREATE/UPDATE/DELETE，CREATE_OR_UPDATE 自动区分）、用户/oid、IP（多级代理头解析含 RFC 7239 forwarded）、UA、耗时、错误、请求参数（headers **排除 authorization/cookie**）、resource_id/name 关联表；**DELETE 前先补录资源名**（`get_resource_name_by_id_and_module`）防删后无从审计。审计写入失败只 print 不阻断业务。
- ❌ 无审批门/人工确认（产品只读）；❌ 无数据脱敏。

### 失败与纠错

错误分类落库 + `<error-msg>` 跨轮回喂（维度 2）；连接失败专门 `SQLBotDBConnectionError` 提示。

## 6. 工具与业务系统集成（★B 组重点）

- **数据源连接管理**：`CoreDatasource.configuration` 列 AES 加密存储——但实现是 `backend/common/utils/aes_crypto.py`：**key 硬编码 `SQLBot1234567890` + AES-ECB**，等于装饰性加密（源码即密钥）；xpack 的 `SecureEncryption`（SECRET_KEY 派生）用于登录密码等另一条路径。连接池 LRU 500。
- **方言覆盖**：18+ 类型（MySQL/PG/Oracle/SQLServer/**达梦 dm**/**人大金仓 kingbase**/Doris/StarRocks/Hive/ES/Redshift/SQLite/Excel…，`db.py` 分支），国产库支持是卖点；sqlglot dialect 映射（`get_sqlglot_dialect`）。
- **只读隔离三件套**：prompt 规则（「只能生成查询 SQL」）+ `check_sql_read` AST 硬校验 + 表名白名单；**无查询超时**（sqlalchemy 路径无 timeout 设置，仅 dm 驱动透传 conf.timeout）⚠️、无 max_rows 下推。
- **外部动态数据源**（assistant type 1/3）：第三方传入临时表定义，生成 SQL 后把 `sqlbot_dynamic_temp_table_<表名>` 占位替换回真实子查询再执行（`llm.py:1384-1391`）。
- **MCP 对外**：`apps/mcp/mcp.py` 以 token 换用户身份，暴露数据源清单/问答/模型选择——把整个 ChatBI 封成工具给他家 agent 用。
- 无文件/代码执行面（对比 DB-GPT 的 code_interpreter/sandbox——本仓刻意不提供）。

## 7. 部署与产品化

- 单容器 `docker-compose.yaml`（`dataease/sqlbot`，**privileged: true**），内置 PostgreSQL 与 g2-ssr；`SECRET_KEY` 强制 env 注入；一键安装脚本。前端构建产物随容器。
- **多租户是真实的**：工作空间 oid 贯穿——chat/datasource/术语/模型全按 oid 过滤；构造期双重校验（chat.oid ∈ 用户可见 ws 列表、datasource.oid == chat.oid，`llm.py:145-168`）——「越权访问在服务构造期即拒」。
- 认证：JWT（OAuth2 password flow + `TokenMiddleware` 解码挂 `request.state.current_user`，`backend/apps/system/middleware/auth.py`）；嵌入场景用 assistant 证书头。
- 配额/成本：❌ 无配额；token_usage 只记录（`GET /record/{id}/usage` 可查）不限额。
- 可观测：结构化日志 + 双审计表；❌ 无 tracing/metrics。

## 8. 对本项目的适用性

硬约束对照：① 独立部署+API——✅ 单服务 + MCP/assistant API，形态可直接对标；② 图编排——❌ 顺序流水线无图引擎，但其「把 NL2SQL 压成确定性多段管线」正是财务场景需要的可预测性（与 DB-GPT 的自由 agent 互为反例）；③ 硬审批/审计——审批不需要（只读），**审计双平面是 18 仓中最成熟的参照**。

### 可借鉴模式（按价值排序）

1. **`check_sql_read` 四层只读校验**（`db.py:1072-1137`）：首关键词白名单→危险模式正则→AST 写类型→**方言敏感危险函数清单**（xp_cmdshell/UTL_FILE/lo_import 这类「函数级逃逸面」清单极少有项目做全）。Java 侧用 JSqlParser 复刻这四层 + 维护方言函数黑名单，是财务 agent SQL 出口的最低标准。
2. **AST 表名白名单、不信任 LLM 自报**（`llm.py#extract_tables_from_sql` + run_task 安全检查块）：解析真实 SQL 提表名（排 CTE 别名）与用户可见资源比对。对财务：表级权限应在执行前由代码校验，LLM 输出的任何元数据不作准。
3. **审计双平面**：执行面 `chat_log`（每次 LLM 调用的完整 prompt/reasoning/token/时长/错误 + 14 种操作枚举）与管理面 `@system_log` 声明式装饰器（含代理链 IP 解析、敏感 header 排除、DELETE 前资源名补录）。财务合规要的「AI 决策可回放 + 管理操作可追责」两条线都有现成 schema 参照。
4. **伪对话 priming + `<error-msg>` 跨轮纠错**（`init_messages`、`get_last_execute_sql_error`）：长知识块逐段注入并要求模型确认；上次 SQL 错误进下轮 prompt——比轮内重试更贴合多轮问答节奏。
5. **M-Schema + 表关系图补全 + 预计算表 embedding**：schema 供给的三件套（格式化 schema、JOIN 关联表自动补全、离线 embedding 选表），Java 侧可用等价轻实现。
6. **构造期租户校验**（`llm.py:145-168`）：会话/数据源/工作空间归属在服务构造时校验，越权请求进不了管线。

### 不可迁移点

- **xpack 闭源**：行列权限、加密、license 皆不在开源代码——「细粒度权限」只能借鉴接口形状（调用点在 `crud/permission.py`），实现需自研；且 **GPLv3+ 附加条款风险**（NOASSERTION），商用集成（尤其与自有 Java 服务同发布）前必须法务核验，保守做法是只借鉴模式不引入代码。
- 行权限靠 LLM 重写 SQL 的路线**不可照抄**：正确性依赖模型输出，合规场景应改为确定性 SQL 改写（如包一层视图/RULE 或 AST 注入 where）。
- 无图编排（硬约束②），需自行叠加工作流引擎；无查询超时与 LIMIT 下推，需补。
- Python/FastAPI 栈本身不可迁移（本项目 Java）。

### 避坑

- `aes_crypto.py` 硬编码 key + ECB：加密形同虚设——密钥必须走 KMS/env 且用 AEAD（GCM）；「有加密」≠「加密有效」。
- 1000 行限制是**保存后截断**：全量数据已从 DB 拉到应用层（大结果会打爆内存/带宽），LIMIT 只靠 prompt 约束——应该在 AST 层强制注入/校验 LIMIT 并设查询超时。
- docker `privileged: true` 与默认弱口令（compose 里 `Password123@pg`、`DEFAULT_PWD`）——交付安全基线弱。
- `generate_filter` 的权限重写结果没有再做行级语义校验（只重过 check_sql）——权限相关 SQL 变换必须有确定性验证器。
- ThreadPoolExecutor(200) + 每线程独立 DB session 的模型在并发大时是资源风险（本仓无配额兜底）。
