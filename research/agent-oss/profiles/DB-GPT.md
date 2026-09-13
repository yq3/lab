# DB-GPT 解剖档案

> 基线：~/develop/opensource/DB-GPT @ 04559f9c (2026-09-08)；canonical eosphoros-ai/DB-GPT；MIT。uv workspace Python 单仓（packages/dbgpt-core|ext|serve|app|sandbox|client|accelerator），eosphoros 系（与 Awesome-Text2SQL 同团队）。注意区分「框架能力」（自研 AWEL DAG + dbgpt.agent 框架 + 多模型管理）与「产品场景」（ChatData/ChatDashboard 场景链 + 新版 ReAct 数据 agent），本档案以后者为主、前者只作底座交代——AWEL/dbgpt.agent 不在 agent-framework 17 框架清单内，无交叉档案可引。

## 1. 产品定位与形态

- 定位：开源「agentic AI data assistant」——连数据源、自主写 SQL 与代码、跑 skill、出图表/看板/HTML 报告（README.md）。实质是两代产品共存：
  - **旧代 Chat 场景**（`packages/dbgpt-app/src/dbgpt_app/scene/`）：ChatScene 枚举分发 chat_db/auto_execute（NL2SQL 直答）、chat_dashboard（指标看板）、chat_data/chat_excel（Excel 分析）、chat_knowledge（RAG）、chat_normal——「ChatBI 产品形态」的直接参照。
  - **新代 ReAct 数据 agent**（`packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/agentic_data_api.py`，3962 行，`POST /v1/chat/react-agent` + SSE）：主 agent 持 8 类工具（sql_query/code_interpreter/shell_interpreter/knowledge_retrieve/load_skill/execute_skill_script_file/html_interpreter/load_tools）+ todowrite 任务板 + dispatch_parallel_tasks 并行子 agent，产出 Markdown 表、图、HTML 报告、skill 产物。
- 交互形态：Web（Next.js 静态资源随 FastAPI 分发，端口 5670）+ REST/SSE API；`dbgpt start webserver/apiserver/worker` CLI（model cluster 可分离部署）。
- 目标用户：数据分析/BI 用户与二次开发者（自研框架+平台双卖点）。

## 2. Agent 执行架构（★NL2SQL 管线）

### 旧代：场景模板 + AWEL operator 的固定管线（非自由 agent）

`BaseChat.stream_call/nostream_call`（`packages/dbgpt-app/src/dbgpt_app/scene/base_chat.py`）四段式，每场景一个子类只覆写三个钩子：

1. **schema 检索**（`ChatWithDbAutoExecute.generate_input_values`，`scene/chat_db/auto_execute/chat.py`）：`DBSummaryClient.get_db_summary(dbname, query, top_k)` 向量召回相关表（见维度 6）；失败兜底 `table_simple_info()` 全表简 schema、超 `schema_retrieve_top_k`/`schema_max_tokens` 直接**字符串截断**（TODO 注释承认未按 token 计数）。
2. **prompt 组装**（`scene/chat_db/auto_execute/prompt.py`）：方言 + 表结构 + 展示类型清单（`_generate_numbered_list` 里 9 种 antv 图表类型说明）+ JSON 响应格式 `{thoughts, direct_response, sql, display_type}`；约束里写死「最多返回 {top_k} 行」——**行数限制是 prompt 约束**。历史消息经 `AppChatComposerOperator`（AWEL operator，`scene/operators/app_operator.py`）+ BufferWindow memory 合成 ModelRequest。
3. **LLM 调用**：`build_cached_chat_operator`（可开模型缓存）流式产出。
4. **SQL 提取与执行**（`scene/chat_db/auto_execute/out_parser.py#DbChatOutputParser`）：`parse_prompt_response` 用 sqlparse 判纯 SQL 输出（兼容「社区纯 SQL 模型」）或解 JSON 成 `SqlAction(sql, thoughts, display, direct_response)`；`parse_view_response` 里 `df = data(sql)`（`data` 即 `RDBMSConnector.run_to_df`）→ 结果转 JSON 嵌进 `<chart-view content=...>` XML 标签（sql + 全量数据 + 图表类型）随前端渲染。执行异常 → 红字 ERROR + 空 err_param 仍以 view message 落库（`ContextAppException`）——**失败不自动重试纠错**（旧代无「把 DB 报错喂回 LLM 重写」的环；新代靠 ReAct 天然重试，见下）。

多 agent：旧代 chat_dashboard 有 data_loader（向 LLM 要图表配置）+ out_parser 两步，无 agent 间协作。

### 新代：ReAct 主循环 + 并行子 agent 分发

- **主循环**（`packages/dbgpt-core/src/dbgpt/agent/expand/react_agent.py#ReActAgent`，继承 ConversableAgent，`run_mode=LOOP`）：经典 ReAct 文本协议（Thought/Action Intention/Action/Action Input/Observation），`max_retry_count=30` 即步数预算；`ReActOutputParser.parse_current_step` 强校验「每轮恰好一个 action」，违规把纠错文案作为 observation 回喂；任务完成 `Action: terminate`；system prompt 注入 `task_progress` 已完成清单防重复动作。支持多层 context management（`init_context_management`，含 observation 落盘成 snapshot 后在 prompt 里只留路径 + 「Full detail available at: {snapshot_path}」——大结果集不撑爆上下文，`react_agent.py#read_memories`）。
- **并行子 agent**（`packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/subagent/dispatcher.py`，全文件是设计范本）：
  - 主 agent 工具 `dispatch_parallel_tasks(tasks)`：先 `todowrite` 建任务板再分批派发（prompt 里强制两段式，`DISPATCH_PROMPT_SECTION`）；单次并发上限 `max_parallel=3`，超额截断并明报「另有 N 个子任务未执行」。
  - **隔离模型**（模块 docstring「Isolation model (spec §4.5)」）：每个子 agent 独立 conv_id `{parent}__d{batch_id}_sub_{i}`（batch_id 防跨批次复用工作目录——注释明说这是修过的「真实跨批数据泄漏」）、独立 react_state、独立 GptsMemory（不入缓存）、独立工具集；**共享**只读资源（database_connector、knowledge、MCP 工具）。
  - 子 agent prompt 明写：不能看主对话历史、目标必须自包含、**不得递归再派发**、只读（写操作返回建议让主 agent 执行）；子 agent 超时 600s、步数预算 15。
  - 结果回流：产物（artifacts/图片/HTML）走 SSE `subagent.artifacts` 旁路事件给前端，**只有压缩后的文本结论进主 agent 上下文**（8000 字符摘要上限）——「产物走旁路、结论进上下文」的分层回传。
  - 失败契约：单子任务异常/超时只标记 status=failed/timeout，不炸整批（`asyncio.gather` 逐个 try）。
- **编排底座 AWEL**（`packages/dbgpt-core/src/dbgpt/core/awel/`）：自研 DAG 框架（DAG/DAGNode/StreamifyAbsOperator/MapOperator/JoinOperator + DAGManager 持久化工作流），旧代 chat 管线与模型调用均以 operator 组装；另有 `dbgpt_serve/flow` 可视化工作流产品（画布编排、DAG 存 MySQL）。新代 react-agent 链路基本绕开 DAG，是 FastAPI handler 里手工编排的 asyncio 流。

### SQL 失败怎么处理（新代）

`sql_query` 工具把执行异常包成 `{"chunks":[{"content":"SQL 执行失败: ..."}]}` 返回——错误文本成为 observation，主 agent 下一轮可自行改写 SQL 重试（ReAct 自纠错）；工具层无重试策略。

### 流式输出

SSE（`_sse_event`）；主 agent 事件流有 step/chunk/done 粒度，`step.confirm` 事件用于人工确认（维度 5）；子 agent agent.start/agent.step（含结构化 chunks：markdown 表/代码/图片 inline 渲染）/agent.done/elapsed_ms。

## 3. 技术底座

- Python 3.10+ / uv workspace monorepo；FastAPI + SQLAlchemy（元数据存储）+ pydantic。
- **自研全套**：AWEL（DAG 流式编排）、dbgpt.agent（ConversableAgent/AgentMemory/Resource-ToolPack 体系）、model cluster（WorkerManager 多模型管理/代理 OpenAI 等 20+ provider，configs/*.toml）。未使用 agent-framework 17 框架中任何一个，无交叉引用可做。
- 前端 Next.js 产物打进 `dbgpt_app/static/web`。
- 部署单进程 FastAPI（webserver）承载全部 serve 模块（conversation/datasource/flow/agent/rag/scheduled_task...），`packages/dbgpt-serve` 是「平台服务层」，`dbgpt-app` 是「场景层」。

## 4. 状态与持久化

- **会话**：`StorageConversation`（`packages/dbgpt-core/src/dbgpt/core/interface/message.py:1239`）双存储接口（conv_storage + message_storage，`StorageInterface` 默认 InMemory，serve 注入 SQLAlchemy 实现）；每轮 `end_current_round()` **增量保存**本轮新增消息（`_has_stored_message_index` 水位），消息独立成行。**view message 落库**是天然审计面：用户看到的每个 `<chart-view>`（含 SQL + 数据 + 图表类型）与 ERROR 视图都留痕。
- **agent 运行**：dbgpt_serve.agent 的 gpts_plans/gpts_messages 表（`MetaDbGptsMessageMemory`，子 agent 也走它），AWEL workflow 存 MySQL（DAGManager）。
- **schema 索引**：每库两个向量集合（`{db}_profile` 表级 / `{db}_profile_field` 字段级），并发索引用**每库线程锁**防 chroma 集合被并发删建（`db_summary_client.py` 的 `_DB_INDEX_LOCKS`，注释记录了真实踩坑）。
- **追踪**：root_tracer 贯穿（span metadata 含完整 payload/model_output/prompt_define_response），是「执行过程审计」的主要来源；无独立 audit log 表——**审计=trace+view message+gpts_messages，非专用合规审计**。
- ❌ 无 checkpoint/回放机制（工作流 serve 有 DAG 级重跑，会话级无）；并发靠 asyncio + 每 conv 工作目录隔离。

## 5. HITL 与风控（★软硬盘点）

**结论：存在真实的代码级确认门（asyncio.Event 阻塞工具执行），但覆盖面窄、三处工程缺陷使其达不到「硬审批」标准；SQL 写/DDL 在连接器层不加拦截。**

### 确认门（MCP 连接器写操作）

- 声明式目录：`packages/dbgpt-ext/src/dbgpt_ext/connector/catalog.json` 8 个连接器（飞书/钉钉/语雀/GitHub/Notion/Linear/Tavily/DeepWiki），每个 entry 带 `confirm_actions`（写操作清单，如 `notion_create_page`、`feishu_send_message`）与 `read_actions`——**读写分级是目录数据不是代码分支**（`packages/dbgpt-core/src/dbgpt/agent/resource/connector/catalog.py#ConnectorCatalogEntry`）。
- 拦截：`ConfirmationInterceptor.should_confirm(tool_name, args)`（`.../connector/confirmation.py`）——tool 名命中任一 entry 的 confirm_actions 即需确认；**`context.trigger_type=="scheduled"` 直接放行**（定时任务免确认，`confirmation.py:73-74`）。
- 门闩：`ConfirmationRegistry`（同文件）asyncio.Event + confirm_id，`execute_tool` 工具内 `await registry.wait_for(confirm_id, timeout=300)`（`agentic_data_api.py:1910-1930`），前端弹窗经 `GET /api/v1/connectors/pending-confirms` 拉取、`POST /api/v1/connectors/confirm` 回填 approved（`packages/dbgpt-serve/src/dbgpt_serve/connector/api/endpoints.py:169-194`）。**超时/拒绝 → `_approved=False` → 返回「用户拒绝了此操作，工具执行已取消」——fail-closed 语义正确**。
- 三个工程缺陷（对硬约束③是致命的）：
  1. 整个确认块包在 `try: ... except Exception: pass` 里（`agentic_data_api.py:1896-1949`）——拦截器装配异常时**静默放行（fail-open）**；
  2. `_PENDING_CONFIRMATIONS` 是模块级内存 dict——重启丢失、**多 worker/多副本部署直接失效**，且 resolve 端点无鉴权（任何能打到 API 的人可替人批准）；
  3. 只覆盖 catalog.json 里的 MCP 连接器工具；`sql_query`、code_interpreter、skill 脚本都不走此门。

### SQL 拦截（本任务重点）

- **agent 工具层**：`sql_query`（`packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/tools/sql_query.py:33-57`）用 `sql_upper.startswith(kw)` 前缀黑名单（INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/CREATE/GRANT/REVOKE）→ 纯字符串匹配，注释/CTE 前缀/多语句即可绕过——**软拦截**。
- **连接器层**：`RDBMSConnector.run`（`packages/dbgpt-core/src/dbgpt/datasource/rdbms/base.py:620-653`）sqlparse 分类后：非 SELECT 的 DML **直接 `_write()` 执行**、还把写 SQL 反转成 SELECT 展示「写后结果」（`convert_sql_write_to_select`）；DDL 分支日志写着「DDL execution determines whether to enable through configuration」**但没有任何配置检查，直接执行**。即连接器无只读保证——只读隔离实际依赖「用只读数据库账号」这一运维约定（连接器提供 `get_grants()` 供查看权限）。
- **行数/超时**：行数限制只在 prompt（top_k）；`query_ex`（`base.py:481-612`）有方言级超时（MySQL `MAX_EXECUTION_TIME`/PG `statement_timeout`/OceanBase/MSSQL/DuckDB 线程池兜底），但旧代 chat 走的 `run()` **不带超时**。
- **数据脱敏**：存在 `packages/dbgpt-core/src/dbgpt/model/proxy/data_privacy/`（sensitive_detection + masking，代理 LLM 场景），未接入 react-agent 主链 ⚠️待确认产品化程度。
- **人工接管/回滚**：❌ 无。

## 6. 工具与业务系统集成（★B 组重点）

### 数据源集成两代并存

- **DB 连接（元数据 JDBC 式）**：`ConnectConfigEntity`（`packages/dbgpt-serve/src/dbgpt_serve/datasource/manages/connect_config_db.py`）存 connect_config 表——`db_pwd` **明文 String(255)**；`get_db_list` 用 f-string 拼 user_id（SQL 注入面）；`to_response` 把 `db_pwd` **原样返回给 API 客户端**。ConnectorManager 管理活跃连接实例；RDBMSConnector 是 SQLAlchemy 包装（15+ 方言在 `packages/dbgpt-ext/src/dbgpt_ext/datasource/rdbms/`），带 include/ignore_tables、`get_table_info`（CREATE TABLE + 3 行样本 + 索引，注释引 Rajkumar et al 2022）、连接池参数。
- **MCP 连接器（新代）**：catalog.json 模板 + `CredentialStore`（`packages/dbgpt-core/src/dbgpt/agent/resource/connector/credential.py`）——Fernet 加盐加密凭据，master key 取 `dbgpt.app.global.encrypt_key`/env `ENCRYPT_KEY`，缺省回退**临时随机 key**（重启后解不开，降级可接受但日志告警）；`_summarize_args` 对 password/token/secret/api_key 等参数打码后才进确认弹窗。参数级凭据支持 `${env:VAR}` 环境变量插值（`RDBMSDatasourceParameters.password` 默认即 `${env:DBGPT_DB_PASSWORD}`，metadata 标 `tags:"privacy"` 供 UI 打码）。
- **schema 供给**：`DBSummaryClient`（`packages/dbgpt-serve/src/dbgpt_serve/datasource/service/db_summary_client.py`）——表级+字段级双向量库（`DBSchemaRetriever`，RDBTextSplitter 以 `--table-field-separator--` 切分），top_k 召回相关表结构再进 prompt；这是「schema linking」的产品化实现。

### 代码执行沙箱

- react 链路的 `code_interpreter`/`shell_interpreter`（`openapi/api_v1/tools/code_interpreter.py`）：`asyncio.create_subprocess_exec` 跑临时脚本，**cwd=按 conv_id 隔离的 `pilot/tmp/{conv_id}` 工作目录**、60s 超时、产物图片写回工作目录——是「每会话工作目录」级隔离，**不是容器沙箱**；真正的 Docker 沙箱在独立包 `packages/dbgpt-sandbox`（sandbox service + docker 镜像构建），主 chat 链未用 ⚠️。
- 读写隔离策略总结：**主 agent 可写（DDL/DML 连接器可达）、子 agent 只读（工具过滤）**；只读判定复用 catalog 的 confirm_actions 名单（`dispatcher.py#_filter_readonly_connector_tools`：拿不到 catalog 时 fail-safe 丢弃全部连接器工具——这个方向是对的）。

### skill 体系

`skills/`（仓库级）+ 用户上传 zip/GitHub 导入（`agentic_data_api.py#skill_import_from_github_v2`，含 zip 解包路径穿越防护 `_extract_skill_from_zip`）；skill = 目录 + 脚本，经 `execute_skill_script_file` 子进程执行。

## 7. 部署与产品化

- 形态：`docker-compose.yml` = mysql + webserver（`eosphorosai/dbgpt-openai` 镜像，`dbgpt start webserver --config configs/dbgpt-proxy-*.toml`）单容器全家桶；模型侧可 `dbgpt start worker` 分离成 model cluster。TOML 配置体系（22 个 configs 模板）。
- **多租户：名义的**。实体表带 sys_code/user_id/user_name 列、connector 列表按 user_id 过滤（空 user_id 视为共享），但认证是**显式 mock**——`get_user_from_headers`（`packages/dbgpt-serve/src/dbgpt_serve/utils/auth.py`）从 header 取 user_id 造 admin 用户，缺省「001/admin」；无登录、无 RBAC、API 无鉴权。
- **配额/成本**：❌ 无 token 计量与配额；控制成本的只有子 agent 步数预算（15/30）、并发上限（3）、各种字符截断（观察 2000/HTML 200k/SQL 输出 20k/摘要 8k）——「预算靠截断」。
- 可观测性：root_tracer 全链路 span（含 prompt/metadata）、`dbgpt` CLI 交易查询、AWEL DAG 可视化监控（serve/flow）、结构化日志。产品完成度高但安全边界停在「单机自用」水平。

## 8. 对本项目的适用性

硬约束对照：① 独立部署+API——✅ FastAPI 服务形态、webserver/worker 可拆，是两仓里最接近的；② 图编排——⚠️ AWEL DAG 存在且旧链在用，但新 agent 链是手工 asyncio 编排（证明「图引擎」与「agent 主循环」正在脱钩）；③ 硬审批/审计——❌ 确认门是雏形（fail-open/内存态/无鉴权），审计只有 trace+消息留痕。

### 可借鉴模式（按价值排序）

1. **声明式读写目录 + 统一确认门**：`catalog.json` 的 `confirm_actions/read_actions` 把「哪些动作是写」做成数据，确认拦截器、子 agent 只读过滤、确认弹窗三处消费同一份名单（`confirmation.py` + `dispatcher.py#_filter_readonly_connector_tools`）。对财务 agent：把「付款/过账/冲销」等动作在工具目录里声明为 confirm 级，审批门与权限过滤共用一源。**但要修掉三缺陷**：确认状态入持久层（可跨实例）、拦截 fail-closed、resolve 端点带操作者身份与审计记录。
2. **子 agent 隔离模型**（`dispatcher.py`）：conv_id 派生独立工作目录（含 batch_id 防跨批泄漏）、独立 memory、共享只读资源、产物走 SSE 旁路/结论进上下文、单失败不炸批。财务场景的「并行对账多科目」可直接套这个拓扑。
3. **schema 双向量检索 + 截断兜底**（`db_summary_client.py`）：表级/字段级两个集合做 schema linking，检索失败退化全表简 schema + 截断——两级降级保证管线不断。
4. **view message 审计面**（`StorageConversation`）：把「用户最终看到什么」（SQL+数据+图表类型）作为独立消息类型落库，天然形成「问答审计流水」，比只存 LLM 原始输出更贴近合规口径。
5. **大观察落盘 + 路径引用**（`react_agent.py#read_memories` 的 snapshot_path/persisted_path + Layer 1 compaction）：SQL 大结果集存文件、上下文只留预览与路径——财务报表场景控制上下文成本的现成做法。
6. **方言级查询超时**（`query_ex`）：按 MySQL/PG/OceanBase 语义 set session 超时而非线程 kill，注意要把它接到主执行路径（本仓 run() 没接是反例）。
7. **Fernet CredentialStore + `${env:}` 参数插值 + 确认弹窗参数打码**（`credential.py`/`parameter.py`/`_summarize_args`）：凭据加密存储、密钥走环境变量、敏感参数不进任何展示层。

### 不可迁移点

- AWEL/dbgpt.agent 自研栈与 Java 生态无对应（本体是 Python 框架产品，场景层才是可移植的知识）；旧代 scene 模板体系已被自家新链取代，不必学。
- mock 认证 + 明文 db_pwd + f-string SQL 的数据源 serve 不可照抄（见避坑）。
- 多模型管理（model cluster）与本项目「业务侧 LLM 网关」假设不符。

### 避坑

- `RDBMSConnector.run` 对 DML 写/DDL 无条件执行（`base.py:620-653`），且日志话术暗示有配置开关实际没有——「连接器层必须默认只读」是财务场景红线，应在连接器构造期校验 DB 账号权限（本仓只提供 get_grants 查询）而非事后拦截。
- 确认门 fail-open（try/except pass）与内存态 pending：分布式部署下审批门会静默失灵——审批状态机必须持久化并有唯一属主。
- `sql_query` 前缀黑名单可绕过（多语句/注释）；行数限制只写 prompt。正确做法：白名单 AST 校验（只放行单条 SELECT）+ 连接层 max_rows + 超时三件套。
- `to_response` 回传 db_pwd、DAO 层 f-string 拼接 user_id——数据源 API 的凭据卫生要专门 review。
- 旧链 `table_info` 超限「按字符截断」会把 CREATE TABLE 切半——schema 预算要按结构单位裁剪（整表丢弃）而非字节截断。
