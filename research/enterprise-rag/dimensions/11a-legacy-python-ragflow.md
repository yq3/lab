# 11a. 遗产 Python 版 RAGFlow 源码档案（与 Go 现版逐项对照）

- 调研对象：`/tmp/wt-ragflow-py`（git worktree，锚点提交 **2508c46c8**，2026-03-04，Go 代码引入前的最后一个纯 Python 完整状态；仓库时间线：2026-03-06 首个 Go 代码 `81fd1811b` 进主干，Python 与 Go 并存至 2026-09-28 `670e68872` 删除 Python 源码）
- Go 对照基线：`~/develop/opensource/ragflow` @ `deb1235be`（2026-10-12），对照证据以 `internal/...` 标注
- 方法：worktree 只读取证 + 主仓 git log 考古；证据分级【核心】= 精读源码 /【示例】= 抽样代码 /【文档】= 注释或配置声明

## 1. Python 版架构总览（与 Go 版对照表）

【核心】Python 版进程拓扑（`docker/entrypoint.sh:216-272`）：**同一镜像内多进程 + 重启循环**，角色由 `ENABLE_*` 环境变量开关：

| 角色 | Python（2508c46c8） | Go（deb1235be） |
|---|---|---|
| API | `api/ragflow_server.py`（**Quart** 异步框架 + nginx 前置，`api/apps/__init__.py:20` 动态 spec_from_file_location 挂载路由模块） | `--api` 单二进制 gin |
| 摄入 | `rag/svr/task_executor.py`×N 进程（jemalloc LD_PRELOAD，entrypoint `task_exe()`） | `--ingestor` |
| 管理 | `admin/server/admin_server.py` | `--admin` |
| 同步 | `rag/svr/sync_data_source.py` | `--syncer` |
| 其他 | MCP server（`mcp/`，独立脚本）、`discord_svr.py`、`cache_file_svr.py` | `internal/mcp` 并入单二进制 |

**结论修正**：Go 版"单二进制 4 角色"并非新增架构，而是 Python 四角色进程拓扑（webservice/taskexecutor/admin/datasync）的合并移植；差异在进程模型（多进程重启循环 vs 单二进制模式开关）。

任务队列与执行语义【核心】：

| 机制 | Python | Go |
|---|---|---|
| 队列 | **Redis Stream 消费者组**（`rag/utils/redis_conn.py:399` `queue_consumer`→XREADGROUP，`xack` 确认；compose 用 `valkey/valkey:8`） | NATS JetStream（compose `nats:2.14.2`）+ MySQL 任务表 poll/notify 混合 |
| 断点续跑 | `get_unacked_iterator`（task_executor.py:184）优先重放 pending 消息 | 任务表游标续跑 |
| 心跳/租约 | Redis zset 心跳（task_executor.py:1282-1338），`WORKER_HEARTBEAT_TIMEOUT=120s`，持 `RedisDistributedLock` 清理超时 worker（准租约接管）；页面级断点 `from_page/to_page` | 心跳/租约/断点（Go 版调研结论 1） |
| 任务取消 | `has_canceled` 轮询 MySQL 任务状态（task_executor.py:218 附近） | 同 |
| 进度上报 | `TaskService.update_progress` 写 MySQL | 同（MySQL 任务表） |

存储依赖清单【核心】（`common/settings.py:69-129` + `docker/docker-compose-base.yml`）：
- 元数据 DB：MySQL（`DB_TYPE=mysql` 默认，peewee ORM，`api/db/db_models.py`）
- 文档引擎：DOC_ENGINE 可选 **elasticsearch / opensearch / infinity / oceanbase(+seekdb)**（`rag/utils/` 下各有 conn；`common/doc_store/` 仅 *_base/*_pool）
- 对象存储：MinIO / AWS S3（`STORAGE_IMPL`）
- 队列/锁/缓存：Redis(valkey)
- 可选 sidecar：TEI embedding、sandbox-executor-manager
- Go 版新增：serenedb、vastbase、silo、kvrocks（替代 valkey）、jaeger 链路追踪；**队列依赖从 Redis 换成 NATS** 是两版最大的部署面差异

## 2. 逐项对照（10 个问题）

### 2.1 检索融合公式与权重 —— 大体一致，三处实质差异

【核心】`rag/nlp/query.py:174-198` `FulltextQueryer.hybrid_similarity` / `token_similarity`：
- `sim = sims[0]*vtweight + tksim*tkweight` —— 融合公式与 Go 结论 2 形态一致
- token 相似度 `to_dict()`：unigram `d[t] += c*0.4`，bigram `d[t+_t] += max(c,_c)*0.6` —— **unigram×0.4+bigram×0.6 确认**，这就是 Go `tokensToDict` 的 Python 原型（term_weight.Dealer 提供权重）
- 字段 boost：`rag/nlp/search.py:322` `tks = content_ltks + title_tks*2 + important_kwd*5 + question_tks*6` —— **与 Go 结论完全一致**
- `retrieval()` 默认参数（search.py:364-380）：`similarity_threshold=0.2`、`vector_similarity_weight=0.3`、`top=1024`、`RERANK_LIMIT = max(30, ceil(64/page_size)*page_size)` —— Go 结论 9 的 0.2/64/1024 成立（Python 多一个 max(30,·) 下限细节）；另有 `post_threshold = 0 if vw<=0 else threshold`（search.py:440）

**差异一【核心】：ES 召回融合权重不是 "0.001,1" 而是 "0.05,0.95"**。`rag/nlp/search.py:127` `FusionExpr("weighted_sum", topk, {"weights": "0.05,0.95"})`（文本 0.05/向量 0.95）；`rag/utils/es_conn.py:160-199` 把第二个权重取出设 `bool_query.boost = 1-0.95=0.05`，knn 走原生打分。Go 版 `internal/service/nlp/retrieval.go:645` `const esFusionWeights = "0.001,1"`，注释自称 "Matches rag/nlp/search.py:331"——**锚点 Python 从未有过 "0.001,1"**（`git log -S'"0.001,1"'` 在 search.py 历史零命中；"0.05,0.95" 自 2025-07-29 `342a04ec8` 起就在）。复核修正（2026-10-15）：锚点 search.py 共 709 行，`:331` 行号本身存在，但内容是 `hybrid_similarity` 应用层融合调用（:327-331），与引擎侧 FusionExpr 权重无关——Go 注释引用的行号与它写死的常量对不上锚点版本，指向的是 2026-09 过渡期 Python（见 §5 存疑）。

**差异二【核心】：min_match 逻辑不同**。锚点 Python 固定 `min_match=0.3`、空结果重试 `0.1`（search.py:114,141）；Go `retrieval.go:651` `minMatch()` 按 `vector_similarity_weight<0.8` 条件取 0/0.3——git 考古证实该条件式 2026-09-20 才出现在 `47a444039`（"fix(go): align retrieval..."）当月的过渡期 search.py:773，纯 Python 时代没有。

**差异三【核心】：rerank 模型路径两处偏离**。
- 输入文本：Python `rerank_by_model`（search.py:352）把**分词后的 token 串**（`remove_redundant_spaces(" ".join(tks))`）喂给 reranker；Go `reranker.go:140-160` 改喂**自然文本**（`extractNaturalText`），注释自陈是防 cross-encoder 给分词文本打低分——有意改进，但不是"镜像"。
- 归一化：Python 只在个别 provider 内做 min-max（`rag/llm/rerank_model.py:40` `Base._normalize_rank`，line 140/227 两处调用）；Go `NormalizeRerankScores`（reranker.go:206-240）**集中式**对全部 provider 归一到 [0,1]。语义近似，机制不同。
- 附带发现：Python 在 Infinity 引擎上**跳过 rerank 直接用引擎融合分**（search.py:416-421），且融合权重固定 0.05/0.95、用户 `vector_similarity_weight` 在该路径不生效；Go `buildInfinityFusionExpr` 把用户权重（默认 0.3）注入融合表达式——行为修正型偏离。

### 2.2 引用溯源 —— 双机制 Python 已有，agentic 形态是 Go 新增

【核心】`rag/nlp/search.py:177-267` `insert_citations`：
- 句子切分（含阿拉伯文标点正则）、`thr=0.63`、`thr *= 0.8` 循环到 0.3、每句 `[:4]` chunk、输出 ` [ID:n]` —— **Go 结论 3 的 0.63/×0.8/4 与 Python 逐项一致**；默认权重 tkweight=0.1/vtweight=0.9（调用处 dialog_service.py:652 传对话级 vector weight）
- 调用方 `api/db/services/dialog_service.py:648-663` `decorate_answer`：先查 `CITATION_MARKER_PATTERN = re.compile(r"\[(?:ID:)?(\d+...)\]")`（**dialog_service.py:381，含阿拉伯-印度数字集**）——若 LLM 已吐 `[N]`/`[ID:N]` 标记则**正则确定性提取索引、跳过 embedding 归因**。即 Go "agentic 确定性 chunk_id 正则提取"的**直系祖先在 Python 聊天管线里已存在**，只是未命名为 agentic、未独立成包
- Python **无 `agentic` 命名的模块/目录**（全仓 grep 零命中）；Go `internal/agentic_rag/`（citations.go `ExtractCitedChunkIDs`/`InsertCitationMarkers`、evidence_registry、grep/bm25/locate/web_search 等 40+ 工具文件）是把该机制泛化成工具调用型 agent 的**Go 独有重写**。Python 最接近物是 `rag/advanced_rag/`：仅 145 行的 `TreeStructuredQueryDecompositionRetrieval`（别名 DeepResearcher，LLM 树状分解子查询递归检索，深度 3，dialog_service.py:544 挂接）——形态与 Go agentic_rag 完全不同

### 2.3 chunk 模板 —— Python 15 模块，Go 丢了 resume 和 tag

【核心】`rag/svr/task_executor.py:84-101` `FACTORY` 16 键 → 15 个模块（`rag/app/`）：naive(=general，另有 "general" 别名)、paper、book、presentation、manual、laws、qa、table、**resume（2740 行简历结构化解析器）**、picture、one、audio、email、**tag（160 行，Excel/CSV 内容→标签对，写入 tag_kwd 供 rank_feature）**、kg(→naive)。分发是**硬编码 dict → Python 模块**（每模板一个 .py，类继承 naive 等）。
Go：`internal/ingestion/pipeline/template/` 恰 12 个 JSON DSL（audio/book/email/general/laws/manual/one/paper/picture/presentation/qa/table），`builtin_registry.go:141` 唯一别名 `naive→general`；`internal/entity/dataset.go` ParserType 枚举 14 值（含 knowledge_graph）**无 resume、无 tag**。
→ **回归项：resume、tag 两种 chunk 模板在 Go 版消失**（连带 tag 模板支撑的 tag_kwd 自动标注→检索 rank_feature 加分链路）。Go 结论 4"12 种模板已是 JSON DSL"对，但"12=全集"不成立。

### 2.4 deepdoc —— 同族模型换运行时；somark/monkeyocr 是 Go 新增

【核心】`rag/app/naive.py:251-258` `PARSERS`：`deepdoc / mineru / docling / "tcadp parser" / paddleocr / plaintext` 共 **6 种 PDF parse_method**，其中 4 种外挂桥在 `deepdoc/parser/`（mineru_parser.py、docling_parser.py、paddleocr_parser.py、tcadp_parser.py；docling 经 entrypoint `ensure_docling` uv 动态安装 pin 2.71.0；mineru/paddleocr 走 **LLMBundle OCR 模型即服务**，naive.py:102-229 `TenantLLMService.ensure_mineru_from_env`）。原生管线：onnxruntime `.onnx`（ocr.py:32-128）+ layout（layout_recognizer.py:265 `InferSession`），模型运行时下载（download_deps.py）。
Go：`.ort` 原生内嵌 + 七种外挂（mineru/docling/paddleocr/somark/tcadp/monkeyocr）。锚点 Python **无 somark、无 monkeyocr**（全仓 grep 零命中）——这两个是 Go 时代新增；"tcadp parser" 的 PARSERS 键名带空格（历史怪癖）。**结论：外挂桥是 Python 遗产且 Python 已有 4 种，Go 在其上做加法**。

### 2.5 模型工厂 —— 反射注册表 + LiteLLM 兜底，不是 lazy-load

【核心】`rag/llm/__init__.py:140-180`：import 时 `importlib.import_module` 7 个模型类型模块（chat/cv/embedding/rerank/sequence2txt/tts/ocr），再 `inspect.getmembers` 扫描所有带 `_FACTORY_NAME` 类属性的 Base 子类注册进 dict；`chat_model.py` 1660 行 18 个 provider 类 + **`LiteLLMBase`（line 1108）经 litellm 统一代理 15+ 家**（`SupportedLiteLLMProvider` 枚举）。用户可见模型目录在 `conf/llm_factories.json`（57 个 factory 条目）+ DB tenant_llm。
判定：**"社区流传的 lazy-load 模型工厂"表述不准确**——是"导入期反射类注册表"，SDK（litellm/openai 等）在模块顶层 eager import；真正的动态性在（a）新增 provider 只需在 7 个文件加类，（b）LiteLLM 兜底使大量厂商零代码接入。Go：`internal/entity/models/factory.go` 编译期 switch + 183 个文件（实测 `ls | wc -l` =183，含 _test）——结论 6 成立，但需加注"Python 侧真正的等价物一半是 LiteLLM 依赖，Go 没有 litellm 兜底层，靠逐家写 driver 补齐"。

### 2.6 use_kg / GraphRAG —— Python 双入口全实现；Go 一半实现一半回归

【核心】Python `rag/graphrag/`（search.py `KGSearch(Dealer)`：query_rewrite→实体/关系检索（ty2ents 过滤、sim_thr 0.3）→社区报告 `_community_retrieval_`；general/ 下 extractor/graph_extractor/leiden/mind_map/community_reports 等约 2463 行）+ 双消费入口：
- 聊天：dialog_service.py:605-610 `settings.kg_retriever.retrieval(...)` 结果 `insert(0, ck)` 合成 chunk
- 检索 API：`api/apps/chunk_app.py:434-441` 同样调用并插入头部（settings.py:341 `kg_retriever = KGSearch(docStoreConn)`）

Go：`internal/service/graph/pipeline.go` **已实现** KGSearch 移植（"Matches Python: rag/graphrag/search.py::KGSearch"，默认参数对齐 sim_thr 0.3/topk 1024），由 `chat_pipeline.go:1005` 与 `deep_researcher.go:392` 消费；但 `internal/service/dataset/search.go:324` 和 `internal/service/chunk/chunk.go:434` 仍是 `Warn "use_kg is not yet implemented in Go - skipping KG retrieval"`。
→ **修正主报告结论：Go 的 use_kg 不是"未实现"，而是"聊天路径已移植、dataset/chunk 检索 API 路径未实现"**——后者相对 Python chunk_app.py 是明确回归。

### 2.7 权限 —— Python 是简单租户模型，Go 策略引擎是增强

【核心】Python：KB 表 `permission = "me"|"team"`（api/db/db_models.py:850），无 per-user 共享表、无策略引擎；可见性规则 `knowledgebase_service.py:165-180`：`(tenant ∈ joined_tenant_ids AND permission=='team') OR tenant==user`；检索 API 前置鉴权 chunk_app.py:387-398：逐 kb_id 校验用户所属租户持有该 KB，否则 403。SDK 仅 private/team 字段（sdk/dataset.py:96）。
Go：`internal/permission/policy_ce.go` communityPolicy（Subject/Scope/TenantRequirement 评估）+ 检索入口 CheckAccess。→ **Go 权限模型比 Python 粒度更细（policy 引擎 vs 字段判断），属增强而非镜像**。

### 2.8 agent/canvas —— 形态同源，Python 多一个运行时插件管理器

【核心】Python `agent/canvas.py`（844 行，Canvas(Graph) DSL 图执行 + memory）+ `agent/component/` 22 个组件 + `agent/tools/` 23 个检索/外部工具（retrieval、tavily、arxiv、exesql、code_exec 等）+ `agent/plugin/plugin_manager.py`（`load_plugins()` 运行时插件加载，ragflow_server.py:132 启动时调用）+ templates + sandbox。Go：`internal/agent/`（canvas runner、component、tool）同构移植。→ 差异：Python 有运行时插件机制（plugin_manager + api/apps/plugin_app.py），Go 未见等价物（编译期固化）。

### 2.9 服务形态小结
见 §1 表。补充：Python `update_progress` 周期任务由 ragflow_server 内 Redis 锁选主执行（ragflow_server.py:51-67），Go 由 --admin 承担。

### 2.10 parity 测试
【核心】Go `internal/ingestion/component/chunker/golden_parity_test.go:19-58`：以 Python 为参考实现，golden 文件由 `tool-py/capture_golden.py` 采集——**对拍基础设施真实存在，但仅覆盖 chunker**；检索/融合/rerank 无 golden 对拍（retrieval_test.go 是纯 Go 断言）。golden 采集自哪个 Python 版本（锚点 or 过渡期）无记录，⚠️。

## 3. Go 版回归项清单（Python 有、Go 丢）

1. **resume chunk 模板**（rag/app/resume.py，2740 行）——Go 12 模板/ParserType 枚举均无
2. **tag chunk 模板**（rag/app/tag.py）及 tag_kwd 自动标注 → 检索 rank_feature 加分链（search.py:269-294 `_rank_feature_scores` 的 Python 端数据来源之一）
3. **检索 API 的 use_kg**（chunk_app.py:434）——Go dataset/chunk 路径 Warn 跳过（聊天路径已有）
4. **运行时 agent 插件管理器**（agent/plugin/）——Go 编译期固化
5. （弱化项）**LiteLLM 兜底接入层**——Go 逐家手写 driver 替代，覆盖面靠 183 文件硬补，新增小众厂商成本高于 Python
6. （语义变化）ES 召回融合权重 0.05/0.95 → 0.001/1：文本腿在召回窗口选择中的影响力缩小 50 倍，极端 case 下 top-N 候选集与 Python 不同

## 4. Go 版新增项（Python 锚点没有）

1. somark、monkeyocr 两种 PDF parse_method 外挂
2. `internal/agentic_rag/` 工具调用型 agent（grep/bm25/locate/todo_write/web_search 工具族 + EvidenceRegistry + 确定性 citation 解析的独立成包）
3. 集中式 rerank 分归一化（NormalizeRerankScores）、reranker 喂自然文本
4. Infinity 融合权重响应用户 vector_similarity_weight（Python 该路径忽略用户权重）
5. 条件式 min_match（vw<0.8）
6. 权限策略引擎（policy_ce：private/tenant/shared + 按用户/租户共享）
7. 部署面：serenedb/vastbase/silo 引擎支持、kvrocks、jaeger、NATS JetStream 队列、单二进制 4 角色
8. deep_researcher（internal/service/deep_researcher.go）作为独立服务形态扩展（Python 是 dialog 内 145 行子查询分解）

## 5. 对主报告（report.md）既有结论的影响评估

1. **§2 时效性警报需加注**：Go 注释自称镜像的 "rag/nlp/search.py:331/773" 是 2026-09 过渡期 Python（与 Go 并存、被 `47a444039` 等提交同步改写），非 2026-03 纯 Python 锚点——"Go 镜像旧 Python"的说法应改为"Go 镜像过渡期 Python，且对锚点 Python 存在若干已知偏离（融合权重、min_match、rerank 输入）"
2. **dim04（检索）**：融合公式/字段 boost/默认参数结论稳固；"ES 融合表达式固定权重 0.001,1（注释自称 Matches search.py:331）"应改写为"Python 实为 0.05,0.95，Go 的 0.001,1 是自定值，注释引用失实"
3. **dim05（GraphRAG）**：若主报告写了"use_kg 未实现"，需改为"chat 路径已实现（internal/service/graph），检索 API 路径未实现"
4. **dim06（agentic）**：确定性 [ID:N] 正则提取的祖先在 Python dialog_service.py:381 已存在，agentic_rag 是 Go 的泛化重写而非凭空新增；rerank 归一化契约源自 Python rerank_model.py `_normalize_rank`
5. **dim02（解析）**：12 模板清单需补注 Python 原有 15 模块、resume/tag 为 Go 回归项；somark/monkeyocr 为 Go 新增
6. **dim07（治理/权限）**：Go 策略引擎是相对 Python(me|team) 的增强，不是移植
7. **模型工厂**：删除/改写"Python 是 lazy-load 模型工厂"的表述 → "导入期反射注册表 + LiteLLM 兜底"

## 6. 证据与存疑清单

证据（Python 一律相对 /tmp/wt-ragflow-py，锚点 2508c46c8）：
- rag/nlp/search.py:127（FusionExpr "0.05,0.95"）、:177-267（insert_citations 0.63/×0.8/[:4]）、:322（字段 boost）、:364-380（默认参数）、:440（post_threshold）
- rag/nlp/query.py:174-198（hybrid/token similarity 0.4/0.6）、:31-39（query_fields boost title^10/important^30/question^20/content^2）
- rag/utils/es_conn.py:160-199（ES 融合实现）、rag/utils/infinity_conn.py:213-217（atan 归一）
- rag/llm/__init__.py:140-180（反射注册）、rag/llm/rerank_model.py:40（_normalize_rank）
- rag/svr/task_executor.py:84（FACTORY）、:180-195（unacked/消费）、:1282-1338（心跳/清退）
- rag/graphrag/search.py:35+（KGSearch）、api/apps/chunk_app.py:363/434（检索 API use_kg）
- api/db/db_models.py:850（me|team）、api/db/services/knowledgebase_service.py:165（可见性规则）、api/db/services/dialog_service.py:381（CITATION_MARKER_PATTERN）/605/648
- rag/app/naive.py:251（PARSERS）、deepdoc/parser/（4 个外挂桥）、docker/entrypoint.sh:216-272（角色拓扑）
- Go：internal/service/nlp/retrieval.go:645/651、internal/service/nlp/reranker.go:92-240、internal/service/graph/pipeline.go、internal/service/dataset/search.go:324、internal/service/chunk/chunk.go:434、internal/agentic_rag/citations.go、internal/ingestion/pipeline/builtin_registry.go:141、internal/ingestion/component/chunker/golden_parity_test.go
- git 考古：`git -S'"0.001,1"'`（search.py 历史零命中）；`47a444039`（2026-09-20，过渡期 search.py:773 条件 min_match 与 Go 注释互证）；`81fd1811b`（2026-03-06 首 Go 提交）；`670e68872`（2026-09-28 删 Python）

存疑（❌/⚠️）：
- ⚠️ Go golden_parity_test 的 golden 文件采集自哪个 Python 版本不可考（脚本 `tool-py/capture_golden.py` 在 Go 树内，非锚点 Python 原物），对拍结论只对 chunker 成立
- ⚠️ "搜索增强链路"：Python search_app/meta_data_filter（chunk_app.py:372-386 auto/semi_auto 元数据过滤）与 Go search.go 的对应实现只做了存在性对照，未逐行对拍
- ❌ Python 侧未发现 per-user KB 共享机制的任何痕迹（无 share 表/API）；Go 的 "shared+按用户共享" 若主报告称其镜像 Python，应更正为新增
- ⚠️ resume/tag 是否被官方以其他形态（如 web 前端禁用、文档删除公告）主动废弃，未查 release notes；"回归"判定基于代码存在性
- ⚠️ Python `rag/benchmark.py`、`memory/`（会话记忆任务，task_executor 支持 memory task type）与 Go internal/service/memory.go 仅做目录级对照，未逐项
