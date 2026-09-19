# WrenAI 解剖档案

> 基线：~/develop/opensource/WrenAI @ be1f9b57 (2026-09-11)；canonical Canner/WrenAI。**状态备注：2026-05 大改版**——原 Docker 版「chat-first BI 产品」整体移到 `legacy/v1` 分支（"Wren GenBI Classic"），主仓库变成「GenBI **引擎** + CLI + SDK + agent skills」形态；原独立仓库 Canner/wren-engine（Rust）已并入 `core/`（README.md:24 公告）。当前 `wrenai` PyPI 0.14.0，活跃开发。许可为**按路径多许可**（`LICENSE` 文件）：`core/**`、`sdk/**`、`skills/**` = Apache-2.0；`docs/**` = CC-BY-4.0；仓库预置 AGPL-3.0 文本供"未来模块"使用（当前无 AGPL 路径）。

## 1. 产品定位与形态

- 定位：**开源生成式 BI（GenBI，generative BI）引擎**——「governed text-to-SQL + 语义层（MDL）+ AI 上下文层」，让 AI agent「生成、部署、治理」BI 产出（README.md:31-35）。卖点是可信：LLM 生成的 SQL 被语义层和策略引擎钳制（"correct instead of confidently wrong"）。
- **形态巨变**：v1 是 Docker 起的 Web ChatBI 产品（UI 已 legacy）；现行主分支**没有自带 chat UI / Web 服务**，而是：Python CLI（`pip install wrenai`，DuckDB 内置）、本地 MCP server（stdio/http）、Python SDK（`wren-langchain`/`wren-pydantic`）、agent skill 存根（`npx skills add Canner/WrenAI` 装进 Claude Code/Cursor/Cline/Codex）。
- 目标用户：**已经拥有编码 agent 的工程师**——"Works through *your* agents (Claude Code, Cursor, MCP…)"。Web UI/Slack/多用户/SSO 全部划给商业版（`docs/core/concepts/oss_vs_commercial.md` 特性对照表）。
- 三拍产品节奏：**Generate**（NL→受治理 SQL+图）→ **Deploy**（生成浏览器端 dashboard，wasm 引擎，一键部署 Vercel/Cloudflare）→ **Know**（业务知识沉淀为可 review 的 Git 文件）。

## 2. Agent 执行架构（★重点：编排外置 + 工具面设计）

**核心设计：LLM 编排完全外置。** WrenAI 主分支自己几乎不调 LLM（仅 memory embedding 与可选环节），NL→SQL 的「智能」交给用户已有的 agent；WrenAI 只提供四类被调用的能力【核心】：

1. **prompt 整形**：`wren ask "<q>" --guided|--direct`——`core/wren/src/wren/ask.py` 仅 33 行，把用户问题套进模板打印给 agent 消费，**不执行任何查询**。guided 模板（`ask_templates/guided.md.tmpl`）就是编排指令：
   ```
   A 数据问题: 1.wren context show  2.wren memory recall  3.用模型名写SQL
               4.wren dry-plan 校验  5.wren query  6.NL回答
   B 项目探索: wren skills list / get <name>，照 markdown 执行
   约束: 用模型名不臆造列名；永不在聊天里要凭据（走 .env）
   ```
2. **工作流指南即代码**：`skills_content/`（onboarding / enrich-context / genbi / generate-mdl / dlt-connector / usage）内置在 CLI 里按需输出——**产品逻辑做成 agent 可读的 markdown 流程，而非后端硬编码 pipeline**（"content always matches the installed version"）。
3. **治理执行引擎**：dry_plan / dry_run / query（见维度 6）。
4. **上下文检索**：memory recall、get_context（MDL 摘要+instructions+相似例句）。

- **MCP 工具面**（`core/wren/src/wren/mcp_server.py`，FastMCP【核心】）：三组工具——查询类 `run_sql`/`dry_run`/`dry_plan`/`query_cube`（cube 即指标查询，带 row_limit 探测）；上下文类 `get_mdl`/`list_models`/`describe_model`/`list_cubes`/`describe_cube`/`get_data_source`/`list_functions`；知识类 `get_instructions`/`recall_queries`/`get_context`/`describe_schema` + memory 写回工具。工具粒度即「检索上下文 / 校验 / 执行 / 记忆」四段，是 LLM 工具面划分的直接范本。
- **LangChain SDK**（`sdk/wren-langchain/src/wren_langchain/_toolkit.py`【核心】）：`WrenToolkit.get_tools()` 返回 runtime tools + memory tools（`wren_fetch_context`/`wren_recall_queries`/`wren_store_query`），system prompt 由 MDL+instructions 生成（`_prompt.py#build_system_prompt`）；memory 关闭时自动裁掉 memory 工具、`include_memory_write=False` 可只留只读记忆工具——**按能力开关裁剪工具面**。
- ❌ 无图编排/无多 agent/无主循环：编排责任全在宿主 agent（或用户）。无终止条件问题（不是对话系统）。

## 3. 技术底座

- **Rust + Python 双层**【核心】：
  - `core/wren-core`：Rust 语义引擎，基于 **Apache DataFusion**（logical_plan/analyze：model_analyze / access_control / model_generation / plan）；`transform_sql(analyzed_mdl, remote_functions, properties, sql)` 是核心入口（`core/src/mdl/mod.rs:465`）。
  - `core/wren-core-base`：MDL 数据结构（proc-macro 生成 struct，serde camelCase + 可选 pyo3 绑定，`manifest-macro/src/lib.rs`）。
  - `core/wren-core-py`：pyo3 Python 绑定（manifest/extractor/validation 模块）。
  - `core/wren-core-wasm`：浏览器端引擎（GenBI dashboard 在浏览器执行语义查询，不经服务端）。
  - `core/wren`：Python CLI/引擎门面（typer + **sqlglot**（>=29，SQL 解析/改写/方言）+ pyarrow + LanceDB（可选 extra）+ FastMCP）。
- agent 框架依赖：仅 `wren-langchain` SDK 适配 LangChain/LangChain 工具协议（交叉引用 `research/agent-framework/profiles/langchain.md`）；编排层零框架。
- 中文环境适配：pip 清华镜像、HF_ENDPOINT 镜像写进 README（README.md Quickstart）。

## 4. 状态与持久化

- **项目即文件（Git-friendly 是第一设计原则）**【核心】：一个 Wren project = MDL JSON（`core/wren-mdl/mdl.schema.json` JSON Schema 校验）+ `instructions.md`（业务定义）+ `queries.yml` + `knowledge/sql/*.md`（NL→SQL 例句，**source of truth**）+ `knowledge/rules/`（业务规则）。全部可 diff、可 PR review。
- **派生索引可丢弃**：`memory/store.py`——LanceDB 索引在 `.wren/memory/`（gitignored、可重建），两张表 `schema_items` + `query_history`；装不起 memory extra 时退化为**零依赖 grep 后端**直接搜 markdown（`docs/core/concepts/memory_system.md`："knowledge/ is the durable layer, the index is disposable"）。markdown 与索引双向同步有严格来源标记（`origin:markdown-sync` tag 防误删，store.py:47-55）。
- 全局态：`~/.wren/`（WREN_HOME 可覆盖）——连接 profiles、memory 索引。
- ❌ 无会话/checkpoint/执行状态持久化（无状态工具服务，每次调用独立）；❌ OSS 无审计日志（商业版特性，oss_vs_commercial.md 对照表 "audit log ❌"）。

## 5. HITL 与风控 ★重点

- **治理即代码（governance-as-code）**：没有运行时审批门，审批流=Git PR——定义（MDL/指令/例句/规则）全部是可 review 文件，"Reviewable. Git-friendly. Never locked inside someone else's UI"（README.md:47）。对财务口径管理这是最贴合合规审计的形态。
- **SQL 策略防火墙**（`core/wren/src/wren/policy.py`，560 行，本仓最值得精读的文件【核心】）三层：
  1. **只读强制（always-on，不依赖 strict mode）**：`validate_read_only_ast`——根节点 AST **白名单**（Select/SetOperation/Subquery/Values）+ **全树扫描**禁用节点（Insert/Update/Delete/Create/Drop/Alter/Grant/Merge/Truncate/Copy/Set/Use/Into/Block/Command…），双保险再叠 DDL/DML marker 类，专防：数据修改型 CTE（`WITH x AS (DELETE..)` 根也是 Select）、T-SQL `SELECT..INTO`、多语句注入 `SELECT 1; DROP TABLE t`、`FOR UPDATE` 锁意图（连非写但取写锁的都拦）。
  2. **strict mode（opt-in）**：表引用必须命中 MDL manifest（fail-closed：未定义表/表值函数一律拒，覆盖 FROM/JOIN/LATERAL 全路径）；**数据读取函数全 AST 位置封禁**（`_DATA_READER_NAMES` 40+：read_csv/parquet_scan/dblink/postgres_scan/pg_read_file/load_file…，注释明确防路径穿越/SSRF/跨库侧移，且报错**不回显参数**防泄露路径 DSN）；合成生成器（generate_series 等）默认禁（DoS 向量）可按名豁免；`denied_functions` 黑名单（含跨方言 canonical 化：sqlglot 同名函数在不同 dialect 落不同 AST 类，枚举 dialect probe 展开）。
  3. **planned SQL 复查**：`validate_planned_sql`——planning 会内联 view/ref_sql，"无懈可击的 SELECT 可能产出 mutating 语句"，翻译后**再验一次**；⚠️ 此层解析失败 fail-open（注释给出理由：输出非用户所写、误杀回归 > 漏放）。
- **RLAC/CLAC（行/列级访问控制，定义在 MDL 里，OSS 可用）**【核心】：`RowLevelAccessControl{name, requiredProperties[SessionProperty], condition}` 挂在 Model 上（`manifest-macro/src/lib.rs:433-440`）；condition 是可含 `@session属性` 引用的 SQL 表达式，**规划期**由 Rust `logical_plan/analyze/access_control.rs` 收集/注入（`collect_condition` 区分顶层列引用与子查询内属性）；缺 required property 时规划直接失败——**fail-closed 的行权限**。CLAC 挂在 Column（operator+threshold，Equals/GT/LT… 六则比较，`cls.rs#eval`）。注意（oss_vs_commercial.md）：**per-user RLS/CLS、按用户注入 session property、审计日志是商业版**；OSS 是"机制在、身份层不在"。
- 结构化错误：`WrenError{ErrorCode, ErrorPhase(SQL_POLICY_CHECK/SQL_PLANNING/SQL_EXECUTION…), metadata}`——错误带相位与方言 SQL，agent 可据此自纠（structured errors with hints 是其宣称的 correctness primitive）。

## 6. 工具与业务系统集成（★B 组重点：MDL 语义层与转换管线）

### 6.1 MDL 元模型（`mdl.schema.json` + manifest-macro【核心】）

| 概念 | 字段要点 |
|---|---|
| Model | name、refSql/baseObject/tableReference（物理指向三选一）、columns、primaryKey（单/复合）、cached/refreshTime（物化提示）、**rowLevelAccessControls[]**、dialect |
| Column | name、type、relationship（经关系取数）、isCalculated、**expression**（计算列）、notNull、isHidden（对 agent 隐藏）、**columnLevelAccessControl** |
| Relationship | name、models[]、joinType、condition——**join 只能走声明的关系**，LLM 无法自造 |
| View | name + statement（原生 SQL，引用 model） |
| Cube + Measure | measure：name/expression/type——**受批指标口径**（"approved, reusable definitions so 'revenue' means the same thing everywhere"，README.md:170） |
| enumDefinitions | 枚举值业务含义（status=3 → "已逾期"这类口径） |
| sessionProperty | name/required/defaultExpr——RLAC 参数通道 |

口径统一 = Cube/measure（指标）+ 计算列 expression + enumDefinitions（值级）+ relationship（join 级）+ `instructions.md`（自然语言定义，prompt 直用）+ `knowledge/sql/*.md`（确认过的 NL→SQL 例句）——六层全在 Git 里。

### 6.2 NL→SQL→执行管线（与 supersonic 对照）

智能在 agent，治理在引擎：

```
agent 写 SQL（用模型名，目标方言，例句来自 memory recall）
 → wren dry_plan（engine.py#_plan【核心】）:
    sqlglot parse（目标方言）→ validate_sql_policy（维度5三层）
    → extract_by 裁剪 manifest（只留引用到的模型）
    → Rust wren-core transform_sql（DataFusion SessionContext，Wren dialect 展开）
    → CTERewriter（cte_rewriter.py）：每个模型展开为 CTE 注回原句（view statement 原样注入）
    → validate_planned_sql 复查 → 目标方言输出
 → connector.query（pyarrow Table，带 row limit）
```

- 与 supersonic 同构：**LLM 写逻辑层（模型名），引擎负责物理展开（join/口径/方言）**；差异：中间表示不是独立 DSL（S2SQL）而是「直接引用模型名的目标方言 SQL」，靠 policy 强制落在 manifest 内；LLM 供应商也完全无关（不内置 LLM 调用）。
- `dry_plan` 可离线跑（无 DB 也行）——**校验与执行分离**，agent 可先 dry-plan 自纠再执行（guided 模板第 4 步即此）。

### 6.3 数据源与凭据

- 连接器 18 个 Python 实现（`connector/`：postgres/mysql/bigquery/snowflake/clickhouse/databricks/redshift/spark/trino/mssql/oracle/athena/canner/duckdb/datafusion…），pyproject extras 按源安装；对外宣称 22+（含 local_file/s3/minio/gcs 文件源）。
- 凭据：profiles 里 `${VAR}` 占位，连接期从环境/.env 解析（`profile.py`：变量名限 UPPER_SNAKE_CASE 防误展开；`load_dotenv(override=False)`）；guided 模板硬约束 "never ask for credentials in chat"。凭据不进 Git、不进 prompt。
- 只读隔离见维度 5；另 `run_sql` 工具带 limit 探测截断（`_query_with_limit_probe`），防止 agent 拖全表。

## 7. 部署与产品化

- **单机 CLI 优先**：pip 安装、DuckDB 内置、项目目录本地跑——反 v1 的 Docker 全家桶（v1 compose 在 legacy 分支）。
- 服务形态仅 `wren serve mcp --transport stdio|http`（`serve_cli.py:122-131`）：stdio 由 MCP client 拉起（默认）；http 打 `/mcp` 端点并打印 `claude mcp add --transport http wren <url>` 接入指引；`--allow-write` 显式开记忆写工具、`--no-connect` 可无 DB 起服务（纯规划）。⚠️ hosted REST API 是商业版。
- GenBI dashboard：`genbi/`（composer/verify/tokens）从项目上下文生成浏览器端 app，查询经 `wren-core-wasm` 在**浏览器内**执行（数据不出端），部署 Vercel/Cloudflare。
- 多租户/账号/SSO/审计：❌ 全在商业版（自托管企业版）。OSS 定位"一个工程师 + 他的 agents"。
- 评测：`evals/`（spodbtify_ab golden set）；`wren profile`（profile.py+profile_cli.py）做数据 profiling（正确性 primitive 之一）。
- 可观测：结构化 WrenError（code/phase/metadata）+ loguru；无分布式 tracing。

## 8. 对本项目的适用性（Java + 独立部署 API + 图编排 + 财务合规）

**可借鉴模式（→路径）**：

1. **治理即代码**：语义模型、业务指令、确认例句全部落 Git 可 review 文件，变更走 PR——财务「口径变更审批+留痕」的最佳形态；对照 supersonic 的 DB 元数据+Web 管理界面（改了不留 diff）。Java 实现可为「YAML/JSON 口径文件 + JSON Schema 校验 + Git 流水线」。
2. **SQL 策略防火墙三层**（`policy.py`）：只读 AST 白名单（根类型+全树节点+DDL/DML marker）→ strict mode 表封闭（只许命中语义层 manifest）→ 翻译后复查（防内联引入写）。Java 用 JSQLParser/Calcite validator 可同构实现；其「数据读取函数黑名单防 SSRF/路径穿越」「报错不回显参数」「fail-open 只限 planned-SQL 复查且注释论证」的工程细节直接照抄。
3. **RLAC session property 机制**：行级权限=模型上声明 condition + 必需会话属性，规划期注入、缺属性 fail-closed——财务多主体（法人/账套/币种）数据隔离的声明式模型；属性值由调用方（审批后的会话上下文）提供，LLM 不可见不可改。
4. **工具面四分法**：上下文检索 / dry-plan 校验 / 受治理执行 / 记忆写回 分成独立工具（MCP `mcp_server.py` 与 `_toolkit.py`），并按能力开关裁剪（memory 关→记忆工具自动消失）——自研 agent 服务暴露给业务侧 API 的接口划分范本。
5. **知识分层持久化**：markdown 为 source of truth、向量索引只是可重建派生物（`memory/store.py` + memory_system.md）——审计时以文件为准，索引损坏可重建，向量化结果永远不是合规事实源。
6. **dry-plan 离线校验**：规划不连库，agent 可先验后执——财务场景「生成→校验→（审批）→执行」链条的中间件。

**不可迁移点**：Rust/DataFusion 引擎栈（Java 对应物是 Calcite，supersonic 已示范）；「编排外置」假设用户自带强 agent——本项目要自持图编排，只能借鉴其工具面与治理层；无服务化多租户/身份/审计（商业闭源），企业化需自建。

**避坑**：① planned-SQL 复查 fail-open——财务场景应改 fail-closed（宁可误杀）；② 数据读取函数黑名单需随连接器生态持续维护（代码注释自认 blocklist 边界）；③ OSS/商业边界仔细核对（README 宣称的 RLS/审计/MCP hosted 均为商业特性，`docs/core/concepts/oss_vs_commercial.md`）；④ 项目 2026-05 刚经历形态巨变，旧资料（v1 Docker 架构文章）已失效，以本基线为准。

**交叉引用**：`research/agent-oss/profiles/supersonic.md`（Java 同题对照：S2SQL vs 模型名 SQL、DB 元数据 vs Git 文件、AOP 权限 vs RLAC）；`research/agent-framework/profiles/langchain.md`（wren-langchain 工具协议适配）；B 组横向见 `dimensions/`。
