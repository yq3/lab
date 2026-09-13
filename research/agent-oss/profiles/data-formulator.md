# data-formulator 解剖档案

> 基线：~/develop/opensource/data-formulator @ 5477f0e2 (2026-08-15)；canonical microsoft/data-formulator；版本 0.8.0b1（0.8 beta，README News 2026-08-15）。微软研究院项目（MIT），**研究工具性质**——维度 5/7 按约定精简，重点在维度 2（agent 循环）与维度 6（code-first 数据处理路线）。

## 1. 产品定位与形态

- **定位**：AI 驱动的数据可视化/探索工具——「用可视化探索数据，由 AI agent 驱动」。两个卖点（README）：① 数据连接器统一接入文件/数据库/数仓并维护「数据记忆」（数据源关系）；② Data Threads——分支探索多问题、对比路径不丢上下文。
- **形态**：本地 Python 包（`pip/uvx data_formulator`）= Flask 后端 + React/Vite 前端（`src/`）+ 可选桌面打包（`desktop.py`、CI 出 Windows/macOS 自包含应用）；也有 Docker 镜像。**单用户本地工具为主，非服务端多租户产品**。
- **技术栈**：Python 3.11 / Flask + flask-limiter / litellm（统一 OpenAI/Anthropic/Ollama 等多模型）/ pandas + DuckDB（大表）/ vl-convert（图表渲染）/ Flint 图表语言。**无 agent 框架——agent 循环纯手写**（见维度 2/3）。

## 2. Agent 执行架构（★重点）

### 2.1 AnalystAgent：vanilla tool-calling loop + skills 层（0.8 统一架构）

单一用户面 agent `AnalystAgent`（`py-src/data_formulator/analyst/agent.py`，2156 行，模块 docstring 自述架构）取代了旧版分离的 DataAgent + ReportGenAgent。核心设计是**把函数调用分成两类，共享同一条 tool-calling 通道**：

- **Inspection tools（检查工具，内部、并行安全、无副作用）**：`execute_python_script`（沙箱跑 Python、stdout 回喂，"not shown to the user"）、`inspect_source_data`（表 schema+统计+样本行）、`load_skill`（读 skill 文档）。一轮可任意多个。
- **Committing actions（提交动作，用户可见、每轮恰好一个）**：`visualize`（出图）、`ask_user`/`interact`（向用户提问并暂停）、`delegate`（转数据加载子流程）、`write_report`（报告技能解锁后）。动作也以 tool call 形式发出，执行结果封装为 **observation 字符串回填该 tool call 的 result**——与检查工具走同一车道，agent 读 observation 自主决定下一步。**「一动作一回合」由 shell 强制（cardinality guard）：多个动作只执行第一个**。【核心】`analyst/agent.py:175-258`（SYSTEM_PROMPT）、`_route_skill_events`、`_set_action_observation`

- **终止协议**：模型某轮不提交任何动作、只回纯文本 → 该文本即 run 的 completion。没有专门 stop/summary 动作。`ask_user` 是唯一例外：handler 返回 `None` observation（没有可观察结果），run 暂停等用户回复（前端拿到 trajectory + completed_step_count，回复时回传 resume）。【核心】`agent.py:583-593`、`routes/agents.py#analyst_streaming`（435-560 行注释完整描述协议）
- **预算双闸**：`max_iterations`（默认 5）是**提交动作级硬上限**（非 LLM 轮次）；另有 `hard_ceiling = max(max_iterations*3, 12)` 圈住非提交轮的失控探索；剩 1 次预算时向 trajectory 注入 `[SYSTEM] You have 1 action left...` 提示。【核心】`agent.py:468-470,596-620`

### 2.2 Skills：渐进披露（progressive disclosure）插件层

Claude/Anthropic Agent Skills 同构的两级披露（`analyst/skills/base.py` docstring 明示 "Mirrors Anthropic Agent Skills tier-1 disclosure"）：

- **tier-1 常驻**：SKILL.md frontmatter（name/description/when_to_use + 声明的 `tools:`/`actions:` 列表）进 system prompt 的 `{skills_block}`；
- **tier-2 按需**：agent 调 `load_skill("<name>")` → SKILL.md body 作为带 `[SKILL LOADED: <name>]` banner 的 user 消息进 trajectory，同时**解锁该 skill 声明的 gated actions**（未加载就调用 → `[GATED] ... call load_skill first` 的 observation，不执行）；
- **skill 是被动处理器**：不跑自己的循环，只贡献 tools + actions + `handle_tool/handle_action` 两个 handler；handler yield 事件（前端流）+ return observation（agent 回喂），两通道严格不交叉——"observation is LLM-facing trajectory text, never shown to the user"；
- **恢复一致性**：resume 时 `_rehydrate_loaded_skills` 用锚定消息首位的正则从持久化 trajectory 里扫 banner 重开技能门（防用户粘贴 banner 伪造——regex 锚定 position 0）。【核心】`agent.py:82-83,643-734`
- 现有 skills：`core`（always-on：explore/inspect 工具 + visualize/interact 动作）、`data-loading`（数据库加载向导）、`report`（write_report + 流式报告 + `inspect_chart` 私有工具）。

### 2.3 code-first 数据变换管线（本项目最关注路线）

「LLM 生成变换代码、代码做计算」的完整落地（对照 NL2SQL 路线）：

1. LLM 按 chart spec（类型+encodings）生成 pandas/duckdb Python 代码，声明产出 DataFrame 的变量名（`output_variable`）；
2. **零成本确定性补丁先行**：`ensure_output_variable_in_code` 用正则扫顶层赋值，若 JSON 声明的 output_variable 未赋值则追加别名行——"<1ms、0 token，避免一次昂贵的 LLM 修复往返"（`agents/agent_utils.py:750-793`）；
3. 沙箱执行（见 2.4）：wrapper 脚本断言 output_variable 是 DataFrame（不是则列出代码中所有 DataFrame 变量名给出**可修复**错误），序列化为 Parquet 回传宿主；
4. **结果契约校验**：chart encodings 里每个字段必须存在于输出 DataFrame 列，缺失 → `fieldsNotFound` 错误（带可用列清单）作为 observation 回喂 agent 自修复；空 DataFrame → `emptyDataframe` 错误；
5. 成功 → 服务端铸 `chart-<uuid12>` 稳定 chart_id、结果表写 workspace Parquet（后续图表/报告按 table_name/chart_id 引用）、行数截断（`max_display_rows` 默认 5000）；
6. **执行成功的代码经 HMAC-SHA256 签名**（`security/code_signing.py`，生产 key 从 Flask secret 派生、dev 模式固定 key）——签名随结果下发，作为「这段代码确实在服务端跑出过这个结果」的完整性凭证。【核心】`agent.py#_run_visualize_code`（1005-1170 行附近）

探索通道 `execute_python_script` 同理但更轻：stdout 捕获（8000 字符截断）、无落表。**LLM 永远不直接算数——所有计算都是生成代码在沙箱执行，结果可复算、代码可审计。**

### 2.4 双沙箱执行底座

- **Docker 模式**（`sandbox/docker_sandbox.py`）：`docker run --rm --memory 512m --cpus 1 --pids-limit 256`，workspace 目录 **只读挂载**（`-v ...:/sandbox/workdir:ro`），输出走独立 rw 挂载的 outputs 目录，脚本只读挂载；超时 120s；输出文件名做路径逃逸防御（`realpath` 前缀校验）；错误信息经 `sanitize_error_message` 脱敏后才回传。
- **本地模式**（`sandbox/local_sandbox.py`）：**常温 worker 池**（预热的 multiprocessing 子进程，pandas/numpy/duckdb 已 import），非 root 场景的默认；用 Python audit hook `block_mischief` 拦截危险操作——禁导入 `subprocess/shutil/socket/http` 等、禁文件写、禁网络；支持 namespace 保存/恢复（跨轮共享变量）。
- 选择：`--sandbox local|docker|not_a_sandbox`（后者明示无隔离）。对比 DataAgent 的 SAA 沙箱：data-formulator 用「只读挂载+受限输出目录」而非全生命周期托管，更轻但信任边界依赖挂载配置。【核心】

### 2.5 结构化计划与自由代码的双轨（数据加载侧）

数据加载不走自由代码：`data_operations/` 是**受限 DSL 计划**——`LoadQuery`（SPJQ 词汇：filters/columns/order_by/limit，frozen dataclass + 校验）+ `ConnectorQueryStep` 等 step 类型组成 DataOperation，经**状态机**推进：`DRAFT → AWAITING_SELECTION →(用户选计划)→ RUNNING → LOADED/PARTIALLY_LOADED/FAILED/CANCELLED/SUPERSEDED`，`DataOperationRepository` 按工作区 JSON 持久化、canonical SHA-256 hash 防冲突、`resolve_interaction_response` 处理用户对计划的选择回复。【核心】`data_operations/models.py:53-61`、`repository.py`、`routes/agents.py` analyst_streaming 里的 interaction_response 分支

**同一系统里并存两级控制粒度**：加载=结构化受控计划（可校验可审批的形态），分析=自由 Python 代码（表达力优先，靠沙箱+结果契约兜底）。

### 2.6 与图编排（本项目约束②）的关系

**不是图**——单 agent 循环 + 事件流（`workflows/` 目录只有 chart_semantics/create_vl_plots 等辅助）。条件分支（加载 vs 探索 vs 报告）靠 skills 门控与动作路由实现。可视为「动态性全部上收到 LLM 决策 + shell 只做合法性闸门」的路线；与 DataAgent 的「静态图+计划路由」恰成两个极端。

## 3. 技术底座

- **无框架**：不依赖任何 agent 框架（无 langchain/langgraph/autogen）——tool-calling 循环、流式、skills、observation 回喂全部手写（约 2k 行核心 shell）。模型接入 litellm（多 provider 统一），OpenAI SDK 兼容协议直连。
- Flask（同步 + 生成器流式 NDJSON）、flask-limiter 限流、flask-cors；前端 React 18 + Vite + TS，Flint 图表引擎。
- 上游框架档案不适用（Python 手写路线）；其 skills 渐进披露设计与 spring-ai-alibaba 的 SkillRegistry（`agent-framework/profiles/spring-ai-alibaba.md` 维度 6）同构，可对照。
- 桌面打包（desktop.py）、示例数据集（`example_datasets_config.py`）、知识库（`knowledge/store.py`，per-user 规则+知识注入 prompt，726 行）。

## 4. 状态与持久化（中等篇幅）

- **执行状态 = trajectory（消息列表），由前端持有**：`interact` 暂停事件把 `_strip_images(trajectory)` 与 `completed_step_count` 随事件发给前端，resume 请求原样回传（`routes/agents.py#analyst_streaming`）。**服务端不存 agent 执行状态**——研究工具/单机的取舍，服务化必须改服务端持久化（对照本项目：审批挂起流若走此模式，trajectory 含全部上下文反而易迁移到 DB）。
- **工作区即数据湖**：`datalake/` 抽象（WorkspaceManager、parquet 表注册、confined_scratch 受限草稿目录、ephemeral/azure_blob 两种 workspace、catalog 缓存刷新）；每个产出表是一份 Parquet + 元数据，天然可回放（代码+输入表+输出表都留痕）。
- **DataOperationRepository**：工作区 JSON 文件 + 文件锁（`_read_unlocked`），操作历史可查（含执行结果表 id、失败步骤）。
- 会话/工作区管理：`routes/sessions.py`（save/list/load/delete/export/import/migrate/cleanup-anonymous），按 identity 分目录。
- 可观测：`ReasoningLogger`（按 identity+session 落 JSONL reasoning 日志，含 session_start/context_built/action_execution/session_end 事件、token 估算）。

## 5. HITL 与风控（精简——研究工具）

- **HITL 形态 = 问答回合而非审批门**：`ask_user` 动作渲染问题 widget、暂停 run、用户回复后同 trajectory resume。数据加载的 `AWAITING_SELECTION`（LLM 提多份加载计划、用户选定才执行）是**最接近审批门的机制**——结构化计划 + 显式人工选择 + 状态机记录，这一小节对财务场景反而最有参考价值。
- 无危险操作分级、无权限体系（单用户工具）；沙箱 mischief 拦截 + Docker 资源限额 + 错误脱敏（`security/sanitize.py`、`log_sanitizer.py`、`url_allowlist.py`、`path_safety.py`）是主要风控。
- 代码 HMAC 签名（见 2.3）是完整性校验，不是审批。

## 6. 工具与业务系统集成（★重点）

### 6.1 数据连接器体系（DataConnector + ExternalDataLoader）

- **17+ 数据源 loader**（`data_loader/`）：MySQL/PostgreSQL/MSSQL/ClickHouse/MongoDB/Kusto/Databricks/BigQuery/Athena/S3/Azure Blob/CosmosDB/Superset/本地文件夹/示例数据集等，统一 `ExternalDataLoader` 抽象（`auth_mode()/list_params()/catalog_hierarchy()/get_schema()/get_data()` 等约定）。
- `data_connector.py`（2719 行）把任意 loader 类**自动生成 Flask Blueprint**（connect/disconnect/status、catalog 分页浏览、import/preview/refresh 端点）+ `DataConnector` 生命周期包装（per-identity loader 实例缓存）。前端表单由 loader 的参数声明**动态生成**，敏感参数（密码/token，`_is_sensitive_or_auth_param`）只出 masked 占位、值不回显。【核心】`data_connector.py:352-470`
- **两级连接器**：admin-pinned（管理员在配置里钉住凭据，用户只见表单剩余参数）vs user-owned（用户自建，spec 存 `connectors/<source_id>.json`，凭据进 vault）——「平台托管数据源」与「自带数据源」分离。

### 6.2 凭据管理（企业级设计，超出研究工具预期）

- `TokenStore` **六级凭据解析链**：`cached → refresh → sso_exchange → delegated → vault → none`（模块 docstring），session 缓存 + 刷新 + SSO 交换（kusto OAuth gateway、github gateway、OIDC）+ 服务代理 + 保险库。【核心】`auth/token_store.py`
- `LocalCredentialVault`：SQLite 存储 + encryption_key 加密（`auth/vault/local_vault.py`）；删除连接器时同步清 vault。
- 身份：`auth/identity.py` + providers（Azure EasyAuth / GitHub OAuth / OIDC）——云端部署时的企业身份对接已预留。

### 6.3 数据处理路线：code-first（与 NL2SQL 对照）

对数据库也是「加载进 DuckDB/pandas 后生成代码处理」，而非生成 SQL 直接下推（loader 的 `get_data` 拉数进工作区，后续全在本地 Parquet 上算）。大表靠 DuckDB；上下文用 `inspect_source_data`（预算内截断样本，`format_dataframe_sample_with_budget`）+ lightweight table context。**对本项目的启示见维度 8。**

## 7. 部署与产品化（精简——研究工具）

- `pip install data_formulator` 本地起 Flask（前端已构建进包）；`uvx` 免安装体验；Dockerfile 多阶段（node 构建前端 → python:3.11-slim，非 root `appuser`，`DATA_FORMULATOR_HOME` 数据目录）；桌面打包；docker-compose。
- 单进程文件存储（SQLite vault + JSON 仓库 + Parquet 工作区），按 identity 目录隔离——无水平扩展/队列/HA 设计；flask-limiter 限流是唯一容量治理。i18n（中英）。

## 8. 对本项目的适用性

对照四条硬约束：Java 栈（❌ Python，但**零框架依赖、协议清晰，是三个产品中最易按协议移植到 Java 的**）、独立部署+API（🔶 本地工具形态，但 Flask API + 前端持有 trajectory 的协议可直接服务化）、图编排（❌ 单循环路线，正好提供对照组）、审批/审计（⚠️ 无审批链，但 code signing + 结构化计划选择是可扩展的种子）。

### code-first 路线对财务表格处理的可借鉴点（本档案核心输出）

1. **「LLM 不算数，代码算」的完整协议**：chart spec/JSON 声明 → 生成代码 → output_variable 契约 → Parquet 回传 → 字段级结果校验 → observation 回喂自修复。财务报表合并/对账/勾稽场景同样适用：LLM 只负责「怎么算」的表达，计算本身确定性可复算、代码可留档审计。→ `agent.py#_run_visualize_code`
2. **确定性本地修复优先于 LLM 修复**：`ensure_output_variable_in_code` 用 <1ms 正则补丁消灭一类高频失败（省一次 LLM 往返）。财务 agent 的「金额格式/日期格式/表头对齐」类错误也应先建本地修复器。→ `agent_utils.py:750`
3. **可修复错误的结构化设计**：错误必须带「可用信息清单」（如 available columns）作为 observation 回喂，让下一轮生成直接可纠；错误分「可恢复（内部回喂，不上前端）」vs「致命（LLM API 等，直达用户）」两级。→ `_route_skill_events` 注释
4. **代码签名作为审计种子**：执行成功即 HMAC 签名，结果与代码绑定。扩展为「审批人签名已执行的代码/SQL」即财务合规审计链的雏形。→ `security/code_signing.py`
5. **结构化受限计划（SPJQ）与自由代码双轨**：高风险操作（取数）走可校验 DSL 计划 + 人工选择状态机（AWAITING_SELECTION），低风险探索走自由代码 + 沙箱兜底——与财务场景「取数计划审批、分析自由探索」的分级天然对应。→ `data_operations/`
6. **双通道工具分类 + 一动作一回合**：inspection（并行、内部）vs action（串行、用户可见）把「读操作随便做、写操作受控」的工具权限模型写进 prompt 契约与 shell 强制——比单纯 RBAC 更贴近 agent 行为模式。→ SYSTEM_PROMPT + cardinality guard
7. **inspection vs action 分离的权限语义**：直接对应财务场景「查账随便查、记账/付款必须逐笔提交」。

### 不可迁移点

- trajectory 前端持有：服务化多租户必须改服务端持久化（且 trajectory 含全部 prompt，落库需脱敏）。
- 本地沙箱常温进程：JVM 侧无直接等价物（Java 侧应对照 DataAgent 的 SAA/Docker 方案）。
- 单进程文件存储无并发/HA 设计。

### 避坑

- `not_a_sandbox` 模式存在（明示无隔离）——部署时必须锁死沙箱模式。
- 凭据六级链复杂度高，本地 vault 的 encryption_key 管理仍是单机水平。
- skills 目录新旧并存（`data-loading` 与 `data_loading` 双目录），0.8 beta 处于架构迁移中，引用时注意以 `analyst/` 为准（`agents/` 下是旧单轮 agent 群）。
