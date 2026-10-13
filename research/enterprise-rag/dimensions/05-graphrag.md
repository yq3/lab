# 维度 05：GraphRAG 与知识图谱增强检索

> 对象：`microsoft/graphrag`（v3.3.0，基线 5faaaf4f）、`HKUDS/LightRAG`（基线 4d0afc1bc）、参照 `Cinnamon/kotaemon`（基线 9ad3e4e4）的集成方式。
> 问题意识：向量检索答不了「全局性问题」（如"这批文档的主要主题是什么"）与多跳关联问题；GraphRAG 用"实体图 + 社区层级摘要"补这个洞，代价是索引成本数量级上升。本文对码回答：管线各阶段在哪、查询怎么走、增量怎么做、钱花在哪、和普通向量 RAG 怎么混用。

## 1. 总表

| 维度 | graphrag（微软，v3.3.0） | LightRAG（HKU） |
|---|---|---|
| 定位 | 社区检测 + 层级摘要的重索引型 GraphRAG | 轻量双层检索 KG-RAG，无社区 |
| 索引管线 | 9 个标准 workflow：切块→LLM 抽图→Leiden 聚类→社区报告→嵌入；另有 Fast（NLP 免 LLM 抽取）模式 | 入队去重→切块→LLM 抽取→阈值式合并摘要；**无聚类、无社区报告** |
| 社区检测 | hierarchical Leiden（graspologic_native 原生库），max_cluster_size=10 | ❌ 无（用查询时图邻域 + 向量混合替代） |
| 查询模式 | local / global / drift / basic（纯向量） | naive / local / global / hybrid / mix（默认 mix） |
| 存储抽象 | 表：parquet/csv/cosmos；向量：lancedb/azure_ai_search/cosmosdb；文件：本地/azure_blob | KV：Json/Redis/PG/Mongo/OpenSearch；图：NetworkX/Neo4j/PG/PGTable/Mongo/Memgraph/OpenSearch；向量：NanoVectorDB/Milvus/PGVector/Faiss/Qdrant/Mongo/OpenSearch；doc_status：Json/Redis/PG/Mongo/OpenSearch |
| 增量更新 | `update` 命令：delta 子索引 + 表拼接合并（实体按 title 合并，社区**不重聚类**只拼接） | 文档级 append + 内容哈希去重 + LLM 结果缓存复用；删除按 doc 重建受影响实体（用缓存，不重调 LLM） |
| 成本机制 | 每次调用记 token + litellm 价格表算美元（ModelCostRegistry），metrics 落盘 | UsageTracker 记调用数/token，无美元换算；省成本靠"免社区报告 + 阈值式摘要 + 缓存"结构性减少调用量 |
| 许可 | MIT | MIT |

## 2. graphrag 管线解剖（monorepo，packages/graphrag 为主）

v3.3.0 已拆成 8 个包：graphrag（主流程）、graphrag-llm（模型/指标/成本）、graphrag-storage、graphrag-vectors、graphrag-chunking 等。标准索引 workflow 顺序【核心】`packages/graphrag/graphrag/index/workflows/factory.py#_standard_workflows`：

```
load_input_documents → create_base_text_units → create_final_documents
→ extract_graph → finalize_graph → extract_covariates(可选)
→ create_communities → create_final_text_units → create_community_reports
→ generate_text_embeddings
```

**切块**：token chunker，默认 size=1200 / overlap=100【核心】`packages/graphrag-chunking/graphrag_chunking/chunking_config.py#27-31`。中间产物是 pandas DataFrame，逐阶段写入表存储（默认 parquet），数据形态 = `entities / relationships / communities / community_reports / text_units / documents / covariates` 若干张表。

**实体抽取（extract_graph）**【核心】`packages/graphrag/graphrag/index/workflows/extract_graph.py#run_workflow`：每个 text unit 发一次 LLM 调用，prompt 是 `graphrag/prompts/index/extract_graph.py#GRAPH_EXTRACTION_PROMPT`（`("entity"<|>名<|>类型<|>描述)` 分隔符格式，few-shot 两例），实体类型默认列表在 `config/defaults.py#147`，`max_gleanings=1`（追问补抽一轮）。随后 `summarize_descriptions` 对同名实体/同边的关系描述做 LLM 摘要合并——这是抽图之外的第二类大额调用。LLM 封装在 graphrag-llm 包的 `create_completion`，带结果缓存（context.cache.child）。

**社区检测（create_communities）**【核心】`packages/graphrag/graphrag/index/workflows/create_communities.py` + `graphs/hierarchical_leiden.py#hierarchical_leiden`：Leiden 由 `graspologic_native`（Rust 原生扩展）实现，不是 python-igraph/leidenalg；输出多层社区（level/parent/children），`max_cluster_size=10`、`use_lcc=True`（先取最大连通分量），社区表带 `period/size` 字段供增量追踪。

**社区报告（create_community_reports）**【核心】`packages/graphrag/graphrag/index/workflows/create_community_reports.py`：`explode_communities` 展开社区成员 → `build_local_context` 组装该社区的节点详情/边详情/claims 详情（token 截断）→ 按层级 summarize（`operations/summarize_communities/`），prompt 在 `prompts/index/community_report.py`。每个社区每个层级一次 LLM 调用，是抽图之后最大的成本项。层级数取决于 Leiden 结果（通常 2-4 层）。

**嵌入（generate_text_embeddings）**【核心】`packages/graphrag/graphrag/index/workflows/generate_text_embeddings.py#EMBEDDING_FIELDS`：固定三类嵌入——text_units.text、entities.title_description（行变换拼接）、community_reports.full_content，各写一个向量库 collection（默认 lancedb，`config/defaults.py#338` db_uri=output/lancedb）。

**查询四模式**（`packages/graphrag/graphrag/query/structured_search/`）：
- **local**【核心】：`context_builder/entity_extraction.py#map_query_to_entities` 把 query 嵌入后与**实体描述嵌入**做相似检索（k=10，2 倍过采样），`find_nearest_neighbors_by_entity_rank` 沿边扩邻域；`local_search/mixed_context.py#LocalSearchMixedContext.build_context` 按 text_unit 50%/community 25%/实体关系与协变量拼上下文，最终一次 LLM 生成（`local_search/search.py#LocalSearch.search`）。
- **global**【核心】`global_search/search.py#GlobalSearch.stream_search`：按社区报告 level 取 context chunks → 每批并发（semaphore=32）跑 map prompt（JSON 打分）→ reduce prompt 汇总。map/reduce prompt 在 `prompts/query/global_search_map_system_prompt.py` 等。这是"全局主题问题"的正解，但每问一次要 1+N 次 LLM 调用。
- **drift**【核心】`drift_search/search.py#DRIFTSearch`：`primer.py#DRIFTPrimer` 先用社区报告分 fold（`primer_folds`）做全局分解生成中间答案+follow-up 查询；`action.py#DriftAction` 每个动作跑一次内置 LocalSearch 产出新 follow-ups，按 `compute_score` 排序迭代至 `drift_k_followups` 预算。即"global 播种 + local 迭代扩散"的混合体，查询成本高于 local/global。
- **basic**：text_units 向量检索 + 生成，等于普通向量 RAG（`basic_search/search.py`），说明 graphrag 官方也保留纯向量兜底。

**成本机制**【核心】`packages/graphrag-llm/graphrag_llm/metrics/default_metrics_processor.py#_process_lm_chat_completion`：每次调用记 prompt/completion tokens，`model_cost_registry/model_cost_registry.py#ModelCostRegistry` 底层数据来自 `litellm.model_cost`，可注册自定义模型价格；`metrics_aggregator.py` 派生 cost_per_response 等指标，索引结束落 metrics 报表。**索引前无预算预估器**，只有事后统计（老版本的 `--dryrun` 估算在本版未见，⚠️ 未找到 dryrun/estimate 代码）。

**增量更新（update）**【核心】`cli/index.py#update_cli`（is_update_run）→ `index/run/run_pipeline.py#54-80` 建时间戳目录（previous/delta 两套 table provider）→ `index/update/incremental_index.py#get_delta_docs` 按**文档 title** 算新增/删除集合 → 对 delta 跑完整标准 workflow（delta 上重新抽图+Leiden+社区报告）→ `update_*` 系列合并：
- 实体按 title 分组解析（`update/entities.py#_group_and_resolve_entities`），描述拼接、frequency 重算、产出 delta→old 的 id 映射；
- 关系按 source/target 合并（`update/relationships.py`）；
- 社区**只做 id 平移拼接**（`update/communities.py#_update_and_merge_communities`），旧社区原样保留、不与新文档实体重新聚类；
- 社区报告旧报告保留，只为 delta 社区生成新报告（`workflows/update_community_reports.py`）。

⚠️ 结论：graphrag 增量是"delta 重索引 + 表级拼接"，**不是**"只重建受影响社区"；图结构演化（旧社区吸收新实体）不会发生，长期增量后社区边界会退化，官方隐含建议是定期全量重建。

## 3. LightRAG 管线解剖

核心三文件：`lightrag/lightrag.py`（8.4k 行，编排）、`lightrag/operate.py`（7.1k 行，抽取与检索算子）、`lightrag/base.py`（存储抽象）。

**索引**：`ainsert` 入队 → doc_status 按**内容哈希**去重（重复文档直接跳过）→ `chunker.chunking_by_token_size`（默认 1200 token）→ `operate.py#extract_entities`：每 chunk 一次抽取调用（prompt `lightrag/prompt.py#entity_extraction_system_prompt`，默认 text 模式，`ENTITY_EXTRACTION_USE_JSON=1` 切 JSON 模式质量更好但更贵），`DEFAULT_MAX_GLEANING=1`（`constants.py#17`）→ `_merge_nodes_then_upsert / _merge_edges_then_upsert` 合入共享图。**关键成本设计**【核心】`operate.py#_handle_entity_relation_summary`：同名实体/同边多份描述合并时，只有当描述数 ≥ `FORCE_LLM_SUMMARY_ON_MERGE`（默认 8）或总 token 超 `SUMMARY_CONTEXT_SIZE`（默认 12000）才调 LLM 做 map-reduce 摘要，否则直接拼接——对比 graphrag 的"每实体必摘要"，这是结构性省调用。

**没有社区**：全库 grep 无 leiden/community 实现 ❌，LightRAG 用"查询时图邻域扩展 + 双层向量检索"替代"预计算社区摘要"来答全局问题，这是与微软版最核心的架构差异（README#242-248 明示）。

**查询五模式**【核心】`lightrag/base.py#QueryParam`（默认 `mix`）+ `operate.py#_perform_kg_search`：
1. 先 `get_keywords_from_query` 一次 LLM 抽出**双组关键词**：ll（低层=具体实体名）与 hl（高层=主题/概念）；
2. **local**：ll 关键词嵌入 → `entities_vdb` 相似检索（`_get_node_data`）→ `_find_most_related_edges_from_entities` 沿实体扩边 + 取关联 chunk；
3. **global**：hl 关键词嵌入 → `relationships_vdb` 相似检索（`_get_edge_data`）→ `_find_most_related_entities_from_relations` 反查实体；
4. **hybrid**：两者都做，实体/关系**轮询交错合并**（round-robin，`_perform_kg_search#5432-5486`）；
5. **mix**（默认）：hybrid 基础上再并一路**原始 query 对 chunks_vdb 的纯向量检索**——KG-RAG 与向量 RAG 在同一上下文预算内融合，统一受 `max_total_tokens/max_entity_tokens/max_relation_tokens` 配额控制后拼 prompt 生成；
6. **naive**：只走向量（`naive_query`）。

注意 LightRAG 的 "global" 与微软语义不同：不是社区报告 map-reduce，而是"用高层主题关键词检索关系边"，全局感来自关系描述的跨文档性，没有预聚合层。

**存储抽象与清单**【核心】`lightrag/kg/__init__.py#STORAGE_IMPLEMENTATIONS`：KV（Json/Redis/PG/Mongo/OpenSearch）、图（NetworkX/Neo4j/PG-ApacheAGE/PGTable/Mongo/Memgraph/OpenSearch）、向量（NanoVectorDB/Milvus/PGVector/Faiss/Qdrant/Mongo/OpenSearch + Noop）、doc_status（Json/Redis/PG/Mongo/OpenSearch）。默认全家桶 = JsonKV + NanoVectorDB + NetworkX + JsonDocStatus，全在 working_dir 文件里；`kg/factory.py#get_storage_class` 按名懒加载。生产组合建议（README/env.example）：PG 全家桶或 Neo4j + Qdrant/Milvus。

**增量与删除**：文档级 append（见上）；删除 `lightrag.py#adelete_by_doc_id`（6727 行起）带管线级互斥：删 chunk 后，受波及的实体/关系用 `operate.py#rebuild_knowledge_from_chunks` 从**幸存 chunk 的 LLM 抽取缓存**重建（不重新调 LLM，除非缓存被显式删除）。自定义 chunk 还有带 journal/resume 的 patch 模式（`ainsert_custom_chunks`，lightrag.py#2540 起）。另有 `tools/kg_integrity_repair.py` 等修复工具。

**成本对比的实现依据**：README#248 宣称"不依赖社区报告与多跳推理，大幅降低索引与查询期 LLM 调用"【文档】。对码可验证的三条结构性依据：① 免去社区报告生成阶段（graphrag 每社区每层一次调用）；② 描述合并阈值门控（默认 <8 份描述不调 LLM）；③ 抽取结果缓存跨查询/重建复用（`llm_response_cache`，`operate.py#_get_cached_extraction_results`）。token 计量有 `utils.py#UsageTracker`（6868 行，call_count/tokens），但**无美元成本表**（对比 graphrag 的 litellm 价格注册表）❌。README 早期版本的"查询 token 成本数字对比表"在本基线 README 已移除，无法源码级复核 ⚠️。

## 4. kotaemon 的集成接线（参照系）

kotaemon 把 KG-RAG 做成**独立可选项索引类型**，与普通向量 FileIndex 并列【核心】`flowsettings.py#356-369`：`USE_MS_GRAPHRAG=True`、`USE_LIGHTRAG=True`（默认开）、`USE_NANO_GRAPHRAG=False`，各自注入 `KH_INDEX_TYPES`。用户在 UI 里给某个 Collection 建 GraphRAG/LightRAG 类型索引，file_id→graph_id 映射存 DB（relation_type="graph"），图数据落 `KH_FILESTORAGE_PATH/{lightrag|graphrag}/<graph_id>/`。

- **LightRAG 侧**【核心】`libs/ktem/ktem/index/file/graph/lightrag_pipelines.py`：进程内调库。LLM/嵌入用 kotaemon 自己的模型管理器包装（`get_llm_func`：tenacity 重试 + hashing_kv 结果缓存）；索引按批 4 文档调 `insert()`；`USE_GLOBAL_GRAPHRAG=True`（默认）时整 collection 共享一张图。检索器下拉 local/global/hybrid，`only_need_context=True` 只取上下文，把实体/关系/来源格式化成 markdown 表 + networkx 可视化图塞回 kotaemon 的 chat 流。依赖锁 `lightrag-hku<=1.3.0`【核心】`libs/kotaemon/pyproject.toml#113`（比本调研基线旧一个大版本，接线用的是旧 API：直接 import `operate._find_most_related_*`）。
- **微软侧**【核心】`libs/ktem/ktem/index/file/graph/pipelines.py`：索引用 subprocess 调 `python -m graphrag.index --root <dir> --init` 外部进程；检索器读的是 **v0/v1 时代的 parquet 表名**（`create_final_nodes/create_final_relationships/...`，pipelines.py#209-215），且每次查询把实体描述重嵌入进内存态 LanceDB（先 rmtree）。⚠️ 这套 import 路径（`graphrag.vector_stores.lancedb`）在 graphrag v2+ 已不存在——kotaemon 的微软 GraphRAG 通道实际只能配老版 graphrag，是"集成停留在旧 API"的典型样本。
- **与向量 RAG 混用**：kotaemon 不做索引级混合，而是在 chat 侧让用户多选索引/检索器，把 KG 检索器和向量检索器的返回文档合并进同一上下文——编排层混合。

## 5. 与普通向量 RAG 的混合路径（企业视角）

1. **LightRAG mix 模式（产品级，最省事）**：一次索引同时产出 KG + chunk 向量，查询时 KG 上下文与纯向量 chunk 按 token 配额轮询融合【核心】`operate.py#_perform_kg_search#5411-5419`。等于"免费获得一路向量 RAG 兜底"，实体命中失败时向量结果仍在场。
2. **graphrag basic + local/global 并行（官方形态）**：graphrag 本身就建了 text_units 向量索引，basic 是纯向量查询；四种模式按问题类型路由（local 问具体、global 问主题、drift 问复杂多跳、basic 问精确段落）。路由可由前置 LLM 分类器做（kotaemon 把选择权交给用户 UI，是产品化折中）。
3. **编排层混合（kotaemon 模式）**：普通向量 RAG 主索引 + KG 副索引并存，检索结果合流。代价是两套索引两份成本，收益是可灰度、可回退——落地风险最低。
4. **不建议**：把 GraphRAG 当唯一检索层。两者的失败模式不同（向量：全局问题失焦；KG：实体抽取噪声、冷启动贵），互补而非替代。

## 6. 企业值不值得上 GraphRAG：判断框架

**先算账（粗算，基于默认 1200-token 切块，1MB 英文 ≈ 25 万 token ≈ 208 chunk）**：
- LightRAG：约 208 次抽取调用（gleaning 默认 1 次追问 ≈ ×2 上限）+ 少量阈值触发的合并摘要 ≈ **每 MB 210~450 次 LLM 调用**；查询每次 1 次关键词抽取 + 1 次生成 + 若干嵌入。
- graphrag standard：208 次抽取 + 每实体/关系一次描述摘要（实体数百~数千）+ 社区报告（社区数 × 层级，千级文档轻松数百社区）≈ **每 MB 500~1500+ 次调用**，官方老 FAQ 也承认比 LightRAG 贵数倍（token 统计有据、倍数无官方数字 ⚠️）。Fast 模式（`extract_graph_nlp` 免 LLM 抽取 + `create_community_reports_text` 模板报告）可把成本打到接近纯向量，但图质量降级。
- **更新文档的代价**：graphrag update 只对 delta 跑管线（省钱）但社区不重聚类（质量债，需定期全量重建）；LightRAG 增量即日常操作，删除靠缓存重建，日常运营模型明显更顺。

**判断框架（四问）**：
1. **问题分布**：用户是否真有"全局主题/多跳关联"类问题（占比 >10~20%）？只有点状事实查询就别上，向量 + rerank 够。
2. **语料规模与稳定性**：语料是否相对稳定（报告库、规范库、案例库）？频繁改写的 wiki 类语料会让 graphrag 社区退化、成本失控；LightRAG 对此宽容得多。
3. **预算与模型**：能否接受索引成本 3~10 倍于纯向量（graphrag）或 2~4 倍（LightRAG）？抽取模型可用便宜非推理模型（LightRAG README 明确推荐 Haiku/mini 档【文档】）。
4. **运维栈**：要 Neo4j/PG 图数据库运维吗？LightRAG 可全 PG 一把梭；graphrag 是 parquet+lancedb 文件形态，企业共享/并发场景要上 cosmos/azure 全家桶。

**倾向性结论**：全局问答需求明确 + 语料稳定 + 预算充足 → 微软 graphrag（global/drift 模式是社区摘要独有优势）；想低成本拿到"实体关联增强 + 一路向量兜底" → LightRAG mix 模式，且它是从现有向量 RAG 渐进升级的最平滑路径（同一存储栈 PG、查询侧可逐步放量）。两者许可都是 MIT，商用无障碍；kotaemon（Apache-2.0）作为集成参照的价值大于直接采用价值。

## 7. 证据与存疑清单

**关键证据（均【核心】除标注外）**：
- graphrag workflow 顺序：`~/develop/opensource/graphrag/packages/graphrag/graphrag/index/workflows/factory.py#_standard_workflows`
- 抽图 prompt：`packages/graphrag/graphrag/prompts/index/extract_graph.py#GRAPH_EXTRACTION_PROMPT`；gleaning 默认 1：`graphrag/config/defaults.py#137`
- Leiden：`packages/graphrag/graphrag/graphs/hierarchical_leiden.py#hierarchical_leiden`（graspologic_native）
- 社区报告：`packages/graphrag/graphrag/index/workflows/create_community_reports.py#run_workflow`
- 三类嵌入：`packages/graphrag/graphrag/index/workflows/generate_text_embeddings.py#EMBEDDING_FIELDS`
- local/global/drift：`query/structured_search/{local_search/mixed_context.py#LocalSearchMixedContext, global_search/search.py#GlobalSearch, drift_search/search.py#DRIFTSearch}`；实体映射 `query/context_builder/entity_extraction.py#map_query_to_entities`
- 存储：表 `packages/graphrag-storage/graphrag_storage/tables/`（parquet/csv/cosmos）；向量 `packages/graphrag-vectors/graphrag_vectors/`（lancedb/azure_ai_search/cosmosdb）
- 成本：`packages/graphrag-llm/graphrag_llm/metrics/default_metrics_processor.py`、`model_cost_registry/model_cost_registry.py`（litellm.model_cost）
- 增量：`packages/graphrag/graphrag/index/update/incremental_index.py#get_delta_docs`、`update/entities.py#_group_and_resolve_entities`、`update/communities.py#_update_and_merge_communities`
- LightRAG 双层检索：`~/develop/opensource/LightRAG/lightrag/operate.py#_perform_kg_search`（local=entities_vdb/global=relationships_vdb，round-robin 合并）；模式定义 `lightrag/base.py#QueryParam`
- 阈值摘要：`lightrag/operate.py#_handle_entity_relation_summary`；常量 `lightrag/constants.py#30-36`（FORCE_LLM_SUMMARY_ON_MERGE=8 / SUMMARY_MAX_TOKENS=1200 / SUMMARY_CONTEXT_SIZE=12000）
- 存储清单：`lightrag/kg/__init__.py#STORAGE_IMPLEMENTATIONS`；删除重建 `lightrag/operate.py#rebuild_knowledge_from_chunks`
- kotaemon：`flowsettings.py#356-369`、`libs/ktem/ktem/index/file/graph/lightrag_pipelines.py`、`.../graph/pipelines.py#109-165,209-249`、`libs/kotaemon/pyproject.toml#113`

**存疑**：
1. ⚠️ graphrag v3.3.0 未见索引前成本预估器（老版 `--dryrun` 式估算未找到），只有事后 metrics；"每 MB 调用数"为本报告按默认切块粗算，非官方数字。
2. ⚠️ LightRAG README 宣称的查询成本优势（早期版本有对微软的 token 对比数字表）在当前基线 README 已删表，只余定性宣称，源码级仅能验证三条结构性省调用设计。
3. ⚠️ kotaemon 的微软 GraphRAG 通道绑定旧版 parquet 表名与已删除的模块路径，配 graphrag v3.x 预期不可用（未实测，基于 import 路径比对）。
4. ⚠️ graphrag 社区报告的准确层级数/社区数随语料而变，"每 MB 500~1500+ 调用"区间来自结构推算（208 抽取 + 实体摘要 + 社区×层级），未见官方 benchmark 数字在仓库内。
5. ⚠️ LightRAG 基线（2026 版）相对 kotaemon 所锁 v1.3.0 已大幅演化（多模态、role-LLM、修复工具链），本文 LightRAG 结论以新基线为准，kotaemon 集成行为以旧版 API 为准，两者不可混读。
