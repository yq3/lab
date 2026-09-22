# WrenAI 持久化深挖档案（MCP-first 形态：真相源/派生索引/凭据/无状态边界 / 借鉴意义）

> agent-persistence 轮 profiles 第 7 篇。基线：~/develop/opensource/WrenAI @ be1f9b57d2（2026-09-11）。历史注记：v1「wren-ui + Docker 全家桶」形态（凭据存 UI 管理的 PG、服务端会话表）整体在 `legacy/v1` 分支，现役主分支已无 wren-ui/PG——**2026-05 形态巨变的实证**（agent-oss 轮元教训②）。本稿全部以现役 MCP-first 代码为准。前置：产品轮档案 `research/agent-oss/profiles/WrenAI.md`；`dimensions/03 §8`（memory markdown→LanceDB）已核对并补全两表逐列（附录 A）。抽查复核见 §10。

## 1. 持久化介质全景

现役 WrenAI 的持久化分四层：**项目内 Git 文件（真相源）→ 编译产物 → 派生索引（可丢弃）→ 全局家目录（连接/凭据/配置）**。权威目录树见 `docs/core/internals/project-layout-v5.md:34-69`。

| 介质 | 位置 | 内容 | 性质 | 证据 |
|---|---|---|---|---|
| MDL 源文件 | `<project>/models\|views\|cubes/*/metadata.yml`、`relationships.yml` | 语义层（模型/列/关系/指标） | ✅ 提交 Git | context.py:549-811 |
| knowledge/ 真相源 | `<project>/knowledge/{rules,glossary,metrics,caveats,sql}/` + `knowledge.yml` | 业务规则、术语、NL→SQL 例句 | ✅ 提交 Git | context.py:473-476, 1726-1753 |
| queries.yml | `<project>/queries.yml` | 旧版 NL→SQL（过渡期，导入时打 `source:legacy`） | legacy | memory/cli.py:287-306 |
| instructions.md / AGENTS.md | 项目根 | 旧版规则（并入 rules/）/ agent 指南 | 提交 | context.py:814-823, 20-72 |
| MDL manifest（编译产物） | `<project>/target/mdl.json` | 全量语义层 JSON（camelCase，盖 layoutVersion） | 派生，gitignore | context.py:17-18, 926-943 |
| LanceDB 索引 | `<project>/.wren/memory/`（无项目上下文时退 `~/.wren/memory/`） | schema_items + query_history 两表 | 派生，可 reset 重建 | memory/cli.py:74-81；store.py:25 |
| GenBI app 注册表/本体 | `<project>/.wren/apps.yml` + `apps/<name>/`（index.html + mdl.json + *.parquet/*.duckdb） | 生成式 dashboard 状态机与自包含前端 | 运行态/生成产物 | genbi/index.py:18-21, 80-97 |
| 全局配置 | `~/.wren/config.yml`（default_project 指针）、`~/.wren/config.json`（strict_mode 策略） | 全局 | — | context.py:372-377；config.py:37-98 |
| 连接 profiles | `~/.wren/profiles.yml`（0600，原子写【复核 ✔】） | 多数据源连接模板，`${VAR}` 占位 | 全局，凭据不出此文件 | profile.py:21-22, 181-197 |
| 明文凭据 | `.env`（cwd → 项目根 → `~/.wren/.env`，`override=False`） | `${VAR}` 的真值 | 不进 Git | profile.py:45-91 |
| 旧版连接文件 | `~/.wren/connection_info.json`（扁平 JSON，**明文 password**） | 过渡期兜底 | legacy | cli.py:80-127, 390-400 |
| 云凭据 | `~/.wren/cloud.yml`（0600）+ git 全局 config credential helper | Wren Cloud API key；git token 短 TTL **从不落盘** | 全局 | cloud.py:41-42, 1-27 |

**wren engine 查询历史**：❌ 引擎侧无任何查询历史落盘——`WrenEngine.query()` 只 dry_plan→connector.query 返回 Arrow（engine.py:117-138）。唯一的"查询历史"是 query_history 表，且**只在 agent/人显式 `store_query`（确认后的 NL→SQL 对）时写入**，不是自动审计日志。

## 2. LanceDB 两表（`memory/store.py`）

- 落点：CLI 默认 `<project>/.wren/memory`，MCP server 固定 `ctx.project/.wren/memory`，类默认 `~/.wren/memory`。
- **建表/替换**：`index_schema(manifest, replace=True, seed_queries=True)`——extract → 批量 embed → `drop_table` 后 `create_table`（store.py:240-247）。seed 查询是**先算好嵌入再 delete `tags='source:seed'` 旧行 + add 新行**，不动 user 行（:266-288）。逐行删除无原生支持时整表重写：`forget_queries_by_ids` 读全表→pandas 丢弃→`create_table(mode="overwrite")`【复核 ✔】（:481-503）。
- **维度守卫（模型不一致 fail-closed）双闸门**【复核 ✔】：
  1. 启动期 `_resolve_dim`：读两表现有 vector 列 FixedSizeList 长度，不一致 → `ValueError "Mixed-dimension memory store"`（:152-184）；
  2. 每次写入前 `_validate_and_set_dim`：新向量维度 ≠ 任一现存表 → `ValueError "New vector dim X does not match existing table"`，报错文案点名 `WREN_EMBEDDING_MODEL` 换模型是成因、`reset` 是出路（:186-200）。
- **双 backend 同向量**：`onnx`（torch-free，复刻 tokenize+mean pooling+L2 归一）与 `sentence-transformers` 产出一致向量，旧表不失效（embeddings.py:1-14, 305-431）。
- 行级 provenance：tags 列空格分词，`source:user|seed|view|legacy` + `origin:markdown-sync`（同步写的行专属标记，forget 只删自己写的行，store.py:30-59, 686-719）。

两表逐列明细见附录 A。

## 3. knowledge/ markdown 真相源（`memory/markdown.py`）

- 零依赖（仅 yaml）：markdown 是真相源，LanceDB 只是派生物——"mirroring how `wren context build` compiles YAML into target/mdl.json"（markdown.py:1-19）。
- **文件名 slug 规则**：NL → lower → 非 `[a-z0-9]` 连串替换为 `-` → 截 60 字符；空 fallback `"query"`。同 NL 复用同文件（原位更新、保留正文注释），不同 NL 撞 slug 加 `-2`/`-3` 后缀（:29, 32-37, 96-109, 157）。
- **frontmatter 全字段**见附录 B。frontmatter 之下为自由正文 `_body`，更新时**原样保留用户注释**。
- **子目录不止 sql/**：骨架为 `rules/`（业务规则，吸收 legacy instructions.md）、`glossary/<term>.md`、`metrics/`、`caveats/`、`sql/`，空目录放 `.gitkeep`，配置在 `knowledge/knowledge.yml`（仅 `schema_version: 1`，与 MDL 版本轴**解耦**）。rules 读取：按名排序拼接 + legacy instructions.md 兜底（context.py:825-855）。
- **watch/同步机制**：`wren memory watch` 轮询（默认 5s）`target/mdl.json` + `knowledge/sql/*.md`，指纹 = 相对路径+size+mtime_ns 的 sha256（不读正文，poll 便宜）（watch.py:30-31, 54-86）；指纹变了→等价 `memory index` 全量重建；**reindex 失败不推进指纹**，变更保持 pending 下轮重试，"update 永不被静默丢弃"（:101-138）。
- **drift 检测**：`wren memory check` 比对 markdown NL 集合 vs 同步行集合，报 not-indexed / stale 两向偏差（memory/cli.py:569-627）。

## 4. MDL manifest（`target/mdl.json`）

- 生成：`wren context build` = `build_manifest()`（snake_case 聚合）→ `build_json()` 递归转 camelCase 并盖 `layoutVersion` → 写 `<project>/target/mdl.json`（indent=2）（context.py:891-943）。
- 消费：MCP 工具 `get_mdl`/`describe_model` **不直接读 mdl.json 而是每次 `build_json(ctx.project)` 重编译**（mcp_server.py:214-282）——manifest 文件主要喂引擎与 `memory index`；serve 启动时比对源文件 mtime 提示 stale（serve_cli.py:25-42）。引擎内 manifest 以 **base64 字符串**流转，规划时 `extract_by` 按引用表裁剪（engine.py:219-220）。
- 结构逐块见附录 C。要点：Column 挂 `columnLevelAccessControl`；Model 挂 `rowLevelAccessControls[]{requiredProperties[sessionProperty]}`；cube 含 measures/dimensions/timeDimensions/hierarchies。
- **csp/UDF/UDM 存哪**：现役 manifest **无** csp/UDF/UDM 块（v1 时代概念）。函数面 = Rust 引擎按 DataSource 内置注册的 remote functions（`list_functions` 无需连库）；可选 `function_path`（CSV 自定义函数）仅作为引擎参数存在，现役调用链**未传值**。自然语言口径在 `knowledge/rules/`。

## 5. 连接与凭据

| 层 | 存法 | 证据 |
|---|---|---|
| profiles.yml | `{active: name, profiles: {name: {datasource, ...}}}`；tempfile+`os.replace` 原子写 + `chmod 0600` | profile.py:181-197【复核 ✔】 |
| 占位符纪律 | profile 值里 `${VAR}` **只在连接期展开**（`expand_profile_secrets`），存盘/`profile debug` 永远是占位符；变量名限 UPPER_SNAKE，小写 `${foo}` 视为字面量不误展开 | profile.py:3-7, 30-35, 122-131 |
| .env 发现 | cwd/.env → 项目根 .env → `~/.wren/.env`；`load_dotenv(override=False)`（shell 导出优先） | profile.py:45-91 |
| debug 掩码 | 字段注册表 SecretStr 全集 + 名称启发式（password/credentials/token/...）递归掩码为 `***` | profile.py:325-421 |
| 项目→profile 绑定 | `wren_project.yml` 的 `profile:` 字段 > 全局 active；pin 了不存在的 profile **fail-loud SystemExit** | profile.py:220-267 |
| 旧路径 | `~/.wren/connection_info.json` 扁平 JSON（含 password 明文）仍是显式 flag 缺席时兜底 | cli.py:80-127 |
| genbi 部署 token | env → .env → 交互提示；**拒绝 `--token` CLI 旗标**（防进 shell history/进程列表） | genbi/tokens.py:1-46 |
| MCP 时代差异 | wren-ui 时代凭据在服务端 DB/环境；现役凭据只在本地文件+env，guided 模板硬约束 "never ask for credentials in chat" | — |

## 6. 检索管线存储侧

- **embedding**：默认 `paraphrase-multilingual-MiniLM-L12-v2`（384 维，多语），`WREN_EMBEDDING_MODEL` 可换；backend onnx 优先；HF 本地缓存优先、batch=32（embeddings.py:27-34, 141-171）。
- **recall_queries（LanceDB）**：`table.search(query_vec)` → 可选标量过滤 `q.where("datasource = '...'")`（SQL 式字符串，字面量单引号翻倍转义）→ `.limit(k).to_list()`，结果弹掉 vector 列（store.py:414-436）。k 默认 3。schema 检索同法支持 `mdl_hash/item_type/model_name` 三条件 AND。
- **全文策略**：schema 描述 ≤30000 字符直接全量返回（`SCHEMA_DESCRIBE_THRESHOLD=30_000` ≈8K token，注释论证"小 schema 全量优于碎片检索"；CJK 更早切检索=保守方向）（schema_indexer.py:60-70）。
- **grep 降级路径**（无 memory extra）：`GrepIndex` 每次查询实时读 markdown——"markdown 就是索引"；打分 = 查询 token（≥2 字符）∩ NL/SQL token 数 + NL 整句子串命中 +5；backend 解析 `WREN_MEMORY_BACKEND=grep|lancedb` 显式覆盖，否则 lancedb 可导入即用、否则降级 grep（index_backend.py:26-30, 73-107, 153-186）。
- **seed 生成**：manifest 模板化造规范对（`List all X` / `Total <数值列> in X` / join 对），排除 raw layer、PK/关系键/`*_id` 类标识列防无意义聚合（seed_queries.py:28-137）。

## 7. CLI 落盘物与 `~/.wren/` 清单

| 命令 | 落盘 |
|---|---|
| `wren memory index` | 重建两表 + `sync_markdown_queries`（+ 旧 queries.yml 打 `source:legacy` 导入）；grep 后端为 no-op |
| `wren memory store` | **必写** `knowledge/sql/<slug>.md`；memory extra 可用时 best-effort 进 LanceDB，失败仅提示 |
| `wren memory recall/fetch/status/check/dump` | 只读/删索引，不写 markdown |
| `wren memory reset` | drop 两表；markdown 保留 |
| `wren memory export` | 一次性迁移：LanceDB→markdown（带 created_at/source），索引原样留待验证后 reset |
| `wren memory watch` | 无新落盘，触发 index |
| `wren context init/build` | 项目骨架（五 knowledge 子目录 + AGENTS.md + `.gitignore(target/)`）/ `target/mdl.json` |
| `wren genbi register/build/deploy` | `apps/<name>/` + `.wren/apps.yml`（状态机 scaffolded→built→deployed） |
| `wren profile add/switch/remove`、`wren cloud auth` | `~/.wren/profiles.yml`、`~/.wren/cloud.yml` + git credential helper |

**`~/.wren/` 完整清单**：`config.yml` / `config.json` / `profiles.yml`(0600) / `.env` / `cloud.yml` / `connection_info.json`(legacy 明文) / `memory/`（仅无项目上下文时的兜底落点）/ `project/`（init 默认项目）。`WREN_HOME` 可整体重定向。

## 8. 无状态边界（对照其他仓 session 表）

- ❌ **无任何会话/对话/执行状态持久化**：MCP server 全部工具为无状态纯函数式调用；`ServeContext` 仅在进程启动时捕获一次 `{project, engine, allow_write, no_connect}`，不含会话对象（mcp_server.py:27-34）。进程内长存的只有 `WrenEngine` 持开的 connector 连接（连接缓存，不是状态）。
- **会话状态由谁持有**：由 MCP client（Claude Code/Cursor/Codex）持有；WrenAI 的"记忆"显式降格为**跨会话、可 review 的项目文件**（store_query 写 markdown）而非服务端 transcript。HTTP transport 同样无会话粘性；多实例水平扩展无共享状态问题。
- ❌ OSS 无审计日志（oss_vs_commercial.md:33 "RLS/CLS per user, session properties, audit log ❌"）；审计等价物 = Git 历史对 knowledge/ 与 MDL 的 diff。

## 9. 借鉴意义（企业级 agent：分布式服务端 + Web）

**照搬清单**：
1. markdown 真相源 + Git/PR 治理 + `origin:` 溯源 tag 限定删除范围——双写一致性的可抄答案（supersonic 用状态机、dify 用 celery，本仓用 provenance tag，三家三种）。
2. 可丢弃索引 + `reset`/`index`/`check` 三命令闭环 + watch 指纹（失败不推进基线）——"索引坏了就重建"的完整工程化。
3. 维度守卫双闸门（启动混维检测 + 每写校验），报错文案自带成因与修复路径——换 embedding 模型静默污染索引是企业向量库最常见事故。
4. 凭据三律：占位符只在连接期展开、debug 输出永不展开、注册表驱动掩码；外加"拒绝 --token 旗标"（防 shell history 泄漏）。
5. 会话外置：服务端零会话状态，记忆=可 PR 的文件——分布式部署免共享 session 存储。

**改造清单**：
1. `forget_queries_by_ids` 的"全表读入 pandas→整表 overwrite"在小数据量成立，服务端多租户需换原生 delete 或分区表。
2. LanceDB 单机目录 → 服务端换 pgvector/milvus 时保留两表语义（schema_items 的 `mdl_hash` 全行守卫、query_history 的 tags 溯源）即可平移。
3. `mdl_hash` 只在 `schema_is_current`/检索过滤用，MCP `get_context` 未做 staleness 前置校验——服务化应把"索引过期即拒绝/自动重建"做成中间件。
4. grep 降级打分器（token 交集+子串）可作为服务端向量库故障时的降级路径整体移植。
5. watch 轮询指纹可换 inotify/fsnotify，但"reindex 失败保持 pending 重试"语义必须保留。

**补缺清单（OSS 明确没有，服务化需自建）**：
1. 多用户/身份层：profiles.yml 单机单用户，无 per-user session property 注入（RLAC 机制在、身份不在）→ 服务端要做 session property ↔ 用户上下文绑定与校验。
2. 审计：无 query 审计表——建议在 store_query 之外加服务端 append-only 审计流（记录谁在何时 dry_plan/run_sql 了什么），与 markdown 记忆分离。
3. 并发写：`MemoryStore` 仅进程内双锁（store.py:131-133），无跨进程锁（对比 crewAI 命名锁+退避）→ 多副本需外部锁或单写者。
4. 密钥管理：.env/profiles.yml 是单机方案 → 服务端接 Vault/KMS；`connection_info.json` legacy 明文路径应随迁移关闭。
5. 索引租户化：项目目录以单用户假设要打破（多租户只读挂载 + 每租户索引命名空间）。

## 10. 抽查复核记录（2026-09-22）

6 条载荷最重证据全部命中：维度守卫（store.py:177 "Mixed-dimension memory store"）、profiles 0600 原子写（profile.py:182-197 chmod 0600 + os.replace）、mdl_hash 列与 schema_is_current（store.py:78/:304）、forget 整表重写（store.py:495-501 mode="overwrite"）、watch 失败不推进指纹（watch.py:101-138）、知识五子目录（context.py:1726-1753 + examples/v5-jaffle 实测）。

---

## 附录：每存储件用途 + 全字段明细

### A. LanceDB 两表逐列（store.py:67-95；记录构造 schema_indexer.py:366-608 / store.py:394-402, 587-597）

**表 1 `schema_items`**（MDL 抽取项；item_type ∈ model/column/relationship/view/cube/measure/cube_dimension/time_dimension）：

| 列 | Arrow 类型 | 用途 |
|---|---|---|
| text | utf8 | 合成描述（嵌入对象），如 `Column 'x' (int) in model 'orders': …` |
| vector | list\<float32\> × dim(384) | text 的嵌入 |
| item_type | utf8 | 检索过滤（`item_type = 'model'`） |
| model_name | utf8 | 归属模型（relationship 取左端；cube 取 baseObject） |
| item_name | utf8 | 元素名 |
| data_type | utf8 | 列/度量类型（model/relationship/view 行为 null） |
| expression | utf8 | 计算列/度量/关系 condition/view statement 原文（非计算为 null） |
| is_calculated | bool | 计算列/measure=true |
| mdl_hash | utf8 | manifest SHA-256 前 16 hex（全行一致=索引未过期；`schema_is_current` 守卫）【复核 ✔】 |
| indexed_at | timestamp\<us, UTC\> | 写入时间 |

**表 2 `query_history`**（NL→SQL 对；text=nl_query 的嵌入）：

| 列 | Arrow 类型 | 用途 |
|---|---|---|
| text | utf8 | = nl_query（冗余存嵌入原文） |
| vector | list\<float32\> × dim | nl_query 嵌入 |
| nl_query | utf8 | 自然语言问题（upsert 去重键） |
| sql_query | utf8 | 确认的 SQL |
| datasource | utf8 | 数据源过滤键（缺省 ""） |
| created_at | timestamp\<us, UTC\> | 写入时间 |
| tags | utf8 | 空格分词：`source:user\|seed\|view\|legacy` + `origin:markdown-sync` + 调用方自由标签 |

### B. knowledge/sql frontmatter 逐字段（markdown.py:112-139, 69-93）

| 字段 | 类型 | 必填 | 写入方 | 去向（同步进 query_history 时） |
|---|---|---|---|---|
| nl | string | ✅ | store/store_query/export | nl_query、text、嵌入源、slug 来源、upsert 键 |
| sql | string(block) | ✅ | 同上 | sql_query |
| source | string（默认 user） | — | 同上（seed/view/legacy 为系统值） | tags 的 `source:` token |
| datasource | string | ❌ | 调用方传 | datasource 列 |
| tags | list[str] | ❌ | 调用方传 | 合并进 tags token |
| created_at | string(ISO) | ❌ | 仅 export 迁移写 | dump/load 往返保留 |
| `_body`（正文） | markdown | — | 人写，机器原样保留 | 不进索引 |

### C. target/mdl.json 结构逐块（mdl.schema.json + context.py:912-934）

顶层：`$schema` / `layoutVersion`(int) / `catalog`✅ / `schema`✅ / `description` / `properties` / `sampleDataFolder` / `dataSource` / `models[]` / `relationships[]` / `cubes[]` / `views[]` / `enumDefinitions[]`（✅=required）。

| 块 | 字段 |
|---|---|
| **models[]** | name；refSql / baseObject / tableReference{catalog,schema,table}（物理指向三选一）；columns[]；primaryKey（str 或复合 list）；uniqueKeys[]；cached(bool)；refreshTime；**rowLevelAccessControls[]{name, requiredProperties[sessionProperty], condition}**；properties{} |
| **columns[]** | name；type；relationship（经关系取数）；isCalculated；notNull；expression（计算列）；isHidden（对 agent 隐藏）；**columnLevelAccessControl{name, operator, requiredProperties, threshold}**；properties{} |
| **relationships[]** | name；models[2]；joinType；condition（SQL 表达式）；properties{} |
| **cubes[]** | name；baseObject；measures[]/dimensions[]/timeDimensions[]（各 name/expression/type/description/properties）；hierarchies{name→levels[]} |
| **views[]** | name；statement（原生 SQL）；properties{} |
| **enumDefinitions[]**（WIP） | name；values[]{name, value}；properties{} |
| **sessionProperty**（$defs） | name；required(bool)；defaultExpr(nullable) |

### D. 其余存储件摘要

| 件 | 字段/格式 |
|---|---|
| wren_project.yml | schema_version(1-5)/name/version/catalog/schema/data_source/profile（顺序固定回写） |
| knowledge/knowledge.yml | `schema_version: 1`（独立版本轴） |
| `.wren/apps.yml` | `{apps: {name: {source, status(scaffolded→built→deployed), created_at, data_mode}}}` |
| `~/.wren/profiles.yml` | `{active: name?, profiles: {name: {datasource, …连接字段含 ${VAR}}}}`（0600） |
| `~/.wren/config.json` | `{strict_mode: bool, denied_functions: [str], allowed_source_functions: [str]}` |
| `~/.wren/config.yml` | `{default_project: path}` |
| `~/.wren/cloud.yml` | API key，按 git host+project id 键控（0600） |
| queries.yml（legacy） | `{version: 1, exported_at, pairs: [{nl, sql, source, datasource?, created_at?}]}` |
