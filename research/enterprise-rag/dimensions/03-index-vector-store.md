# 维度 03：索引与向量库（基建能力 × 平台用法）

> 调研日期：2026-10-12。基线：milvus@55b4415230 / qdrant@016542aa5（1.19.2）/ pgvector@f37c13f（0.8.7）/ ragflow@deb1235be / dify@79effdd498 / anything-llm@2a10d052 / kotaemon@9ad3e4e4。
> 方法：只 grep 定位 RAG 功能面（过滤/混合检索/融合/多租户/量化/部署），不漫游存储引擎内部。证据分三级：【核心】源码主链路；【示例】测试/用例；【文档】仓库内文档/配置。

## 0. 两条前置发现（影响全篇结论）

1. **ragflow 已完成 Go 重写，Python 源码于 2026-09-28 整体删除**（`git log 670e68872 "refactor: remove python source code, part2"`）。旧 `rag/utils/es_conn.py`、`infinity_conn.py` 已不存在，文档引擎抽象迁移到 Go 的 `internal/engine/` 包。任务描述里"默认 ES/Infinity"的设计仍然成立，但证据全部来自 Go 侧新代码。
2. **qdrant 存在两条互不相通的文本检索路径**：payload 全文索引（charabia 分词，支持中文）与新版 server 端 BM25 稀疏向量（`lib/bm25`，仅空白符分词，**不支持中文**）。做中文混合检索时必须选对路径，详见第 3 节。

---

## 1. 基建对比总表（milvus / qdrant / pgvector）

| 维度 | milvus 2.x（55b4415） | qdrant 1.19.2 | pgvector 0.8.7 |
|---|---|---|---|
| 过滤语法 | 自有 DSL（ANTLR 文法）：`==/in/like/JSON_CONTAINS/TEXTMATCH/PHRASEMATCH/MATCH_ANY…`，操作符最全 | JSON 条件树（must/should/must_not 嵌套），按 payload field 组合 | SQL `WHERE`，天然万能 |
| 过滤实现 | 强类型 schema 字段 + 动态 JSON 字段；tantivy 倒排 + bitmap + JSON 索引 | payload 索引按字段类型建（map/numeric/geo/bool/full-text/struct），可声明 schema 与迁移 | PG 索引 + 迭代扫描（iterative_scan，0.8.0+）解决"先 ANN 后过滤召回不足" |
| 稀疏向量/全文 | SPARSE_FLOAT_VECTOR 字段 + BM25 Function（analyzer 由 tantivy FFI 提供，内置 jieba） | sparse vector 原生；payload 全文索引（charabia）；新版 `lib/bm25` 服务端 BM25 稀疏嵌入 | sparsevec 类型（≤1000 非零元）仅存储/距离计算，**无打分无分词** |
| 混合检索入口 | `HybridSearch` RPC：一个 collection 多个向量字段（含 dense+sparse）一次请求 | Query API：`prefetch` 递归组合多路（dense/sparse/filter/scroll），末端 fusion | ❌ 需 SQL 自行 JOIN + 应用层融合 |
| 融合算法 | rrf / weighted / decay / model（外部 rerank 模型）四类 reranker，另有 C++ 侧 xgboost 打分 | RRF（k 默认 2，支持 per-source 权重）/ DBSF（3σ 归一化） | ❌ DIY |
| 多租户 | partition key（int64/varchar，默认 64 partition 上限内建 16 个）+ partition-key isolation 属性；RLS 设计文档 | 单 collection + tenant payload 过滤（官方推荐模式，无 partition 概念） | 官方 README 明示：list 分区或分表 |
| 量化 | knowhere：IVF_SQ8 / IVF_PQ / SCANN / DISKANN / binary / GPU 系列；mmap 全字段可控 | SQ(int8) / PQ / Binary / TurboQuant(1~4bit) 四类，可按 segment 混用 | ❌ 无量化；靠 halfvec(2 字节) 降内存 |
| 索引 | HNSW/IVF 系列/DISKANN/GPU_CAGRA 等（knowhere 引擎） | HNSW（m/ef_construct/full_scan_threshold_kb）+ sparse inverted/mmap | HNSW + IVFFlat 两种 |
| 部署形态 | Lite（pip 嵌入）/ standalone（etcd+minio+rocksmq）/ cluster（etcd+minio+pulsar\|kafka\|woodpecker） | 单二进制；embedded `qdrant-edge`（Rust/Python FFI）；分布式=分片+副本（raft） | PG 扩展，跟随 PG 部署 |
| 规模定位 | 数十亿级分布式 | 单机到中等集群 | 亿内（取决于 PG 运维能力） |
| License | Apache-2.0 | Apache-2.0 | PostgreSQL License |

### 1.1 milvus 细节

- **过滤文法**【核心】：`~/develop/opensource/milvus/internal/parser/planparserv2/Plan.g4#L22-L30` —— `TEXTMATCH`、`TEXTMATCHFUZZY`、`PHRASEMATCH`、`MATCH_ALL/ANY/LEAST/MOST/EXACT`（数组阈值匹配）都在文法层。倒排基于 tantivy：`internal/core/src/index/InvertedIndexTantivy.h`。设计文档里还有行级安全（`docs/design-docs/design_docs/20250610-rls_design.md`）和拼音过滤（`20260209-pinyin_filter.md`）——企业权限过滤方向 milvus 走得最深。
- **BM25 function**【核心】：`internal/util/function/function.go#L38-L42` 注册 `FunctionType_BM25 / MinHash / TextEmbedding`；BM25 的分词器经 FFI 调 tantivy（`internal/core/src/segcore/tokenizer_c.cpp#create_tokenizer`）。**中文**：jieba 是一等公民 tokenizer【示例】：`tests/go_client/testcases/full_text_search_test.go#L73-80`（Chinese_Jieba 用例：jieba analyzer + 中文 query「信息检索的应用」+ BM25 function，活测试）；Python 侧对应用例 `tests/python_client/milvus_client/test_milvus_client_search_text_match.py#L332` 在本基线被 `@pytest.mark.skip`（reason="unstable: jieba tokenization vs Python substring mismatch"）——中文能力的证据以引擎实现 + Go 活测试为准。还支持 per-row 选分析器：`internal/util/function/multi_analyzer_bm25_function.go`。
- **稀疏索引**【核心】：`internal/core/src/index/Utils.cpp#L53-L80` —— `INDEX_SPARSE_INVERTED_INDEX` 与 `INDEX_SPARSE_WAND`，仅 IP 度量。
- **混合检索与融合**【核心】：`internal/proxy/impl.go#L3114`（`Proxy.HybridSearch`）；一个 collection 多向量字段由 `internal/proxy/task.go#L563`（`validateMultipleVectorFields`）校验。融合/重排链在 `internal/util/function/chain/rerank_builder.go#L39-L52`：reranker 四类 `decay/model/rrf/weighted`（`defaultRRFK = 60.0`）；`internal/util/function/rerank/` 下接了 cohere/tei/vllm/siliconflow/voyageai/zilliz/huggingface/ali 八家外部 rerank provider。C++ 侧还有 xgboost 打分器（`internal/core/src/rescores/BoostScoreRunner.cpp`、`xgboost_model_c.cpp`）。
- **多租户**【核心】：partition key 校验逻辑 `internal/proxy/task.go#L214-L252`（只能 int64/varchar、不可为主键、默认 16 个分区：`pkg/common/common.go#L80 DefaultPartitionsWithPartitionKey = 16`）；`pkg/common/common.go#L672 IsPartitionKeyIsolationKvEnabled` 提供"一租户一物理分区"的隔离模式。
- **量化/内存**：索引类型在 knowhere（外部库），仓库内证据【示例】`tests/python_client/common/common_func.py#L3436-L3474`（IVF_SQ8/IVF_PQ/HNSW/SCANN/DISKANN 参数模板）；内存控制靠 mmap 开关【文档】`configs/milvus.yaml#L764-L768`（vectorField/vectorIndex/scalarField/scalarIndex 四级 mmap）。
- **部署**【核心】`docker-compose.yml#L97-L124`：etcd + pulsar(可选) + minio；【文档】`configs/milvus.yaml#L174`（standalone 默认 rocksmq）；【文档】`README.md#L22`（Milvus Lite pip 嵌入 + standalone + K8s 分布式三形态）。

### 1.2 qdrant 细节

- **payload 索引**【核心】：`lib/segment/src/index/field_index/` 下按类型分目录（map_index/numeric_index/geo_index/bool_index/null_index/facet_index/full_text_index）；新版还有"结构化 payload"（`lib/segment/src/index/struct_payload_index/payload_index.rs`，带 schema 变更分类 `SchemaTransition`，支持声明式 payload schema 与平滑迁移）。
- **全文索引分词**【核心】：`lib/segment/src/data_types/index.rs#L271-L277` `TokenizerType{Prefix, Whitespace, Word, Multilingual}`；Multilingual 走 charabia（`lib/segment/src/index/field_index/full_text_index/tokenizers/multilingual.rs`），Cargo 特性显式开启 **chinese-segmentation + chinese-normalization**【核心】`lib/segment/Cargo.toml#L105-L110`，日文另走 vaporetto。
- **BM25 稀疏向量**【核心】：`lib/bm25/src/lib.rs` 是"compute-only"crate（k1/b/avg_doc_len 参数化），其分词器 `lib/bm25/src/basic_tokenizer.rs#L25-L27` 仅 `split_whitespace` —— **服务端 BM25 稀疏嵌入对中文无效**（整句成一个 token），中文稀疏检索要么走 payload 全文索引，要么客户端分词后喂 sparse vector。
- **Query API 融合**【核心】：调度在 `lib/collection/src/shards/local_shard/query.rs#L303,#L426-L437`：`ScoringQuery::Fusion` 分派到 `FusionInternal::Rrf{k, weights}` → `lib/segment/src/common/reciprocal_rank_fusion.rs#rrf_scoring`（`DEFAULT_RRF_K = 2`，带权重 RRF），`FusionInternal::Dbsf` → `lib/segment/src/common/score_fusion.rs`（Sum + 3σ 分布归一化）；prefetch 递归可嵌套（同文件 `recurse_prefetch`），还支持 MMR/采样/上下文查询。
- **量化**【核心】：`lib/quantization/src/`：SQ（u8）、PQ（`encoded_vectors_pq.rs`）、Binary、TurboQuant（`turboquant/mod.rs#TQBits{Bits4,Bits2,Bits1_5,Bits1}`，带 rotation/permutation 优化）；枚举入口 `lib/segment/src/types.rs#L1125-L1130 QuantizationConfig{Scalar,Product,Binary,Turbo}`。
- **HNSW**【核心】：`lib/segment/src/types.rs#L816-L828` `HnswConfig{m, ef_construct, full_scan_threshold_kb}`（注释明示 1Kb≈1 条 256 维向量，低于阈值走全扫描）。
- **多租户**：仓库内无专门模块；模式 = 单 collection + tenant 字段 payload 索引 + filter。README 提到官方 agent skills 覆盖 "tenant isolation, hybrid search" 主题【文档】`README.md#L42`。⚠️ 详细的官方多租户建议在 qdrant.tech 文档站，不在仓库内。
- **部署**：单二进制；嵌入式 `lib/edge/`（Rust crate `qdrant-edge` + Python `qdrant-edge-py`，见 `lib/edge/README.md`）；分布式分片+副本+raft（【文档】`README.md#L149`）。

### 1.3 pgvector 细节（仓库小，全量核对）

- **过滤即 SQL**【文档】：README "Filtering" 节：近似索引先扫后滤，召回不足时 0.8.0+ 开 `SET hnsw.iterative_scan = strict_order|relaxed_order`，配 `hnsw.max_scan_tuples`（默认 20000）/`ivfflat.max_probes` 上限；低基数条件建议 partial index，高基数建议表分区。
- **多租户**【文档】README "Multitenancy" 节原文：共享近似索引会让租户互相干扰召回，"use list partitioning or separate tables"（`PARTITION BY LIST(customer_id)`）。
- **类型与上限**【文档】：vector ≤2000 维、halfvec ≤4000、bit ≤64000、sparsevec ≤1000 非零元（README:253-255）；超 2000 维用表达式索引 `(embedding::halfvec(3))` 降精度（README:552-569）。
- **混合检索**【文档】：README:635 唯一一句——"Use together with Postgres full-text search for hybrid search"。即融合要自己在 SQL 里做（tsvector/tsrank + 向量距离，应用层或 SQL RRF）；中文分词需外挂 zhparser/pg_jieba 等 PG 扩展（❌ 本仓库无相关内容，属生态事实）。
- **License**：PostgreSQL License（`LICENSE`）。

---

## 2. 平台侧实际用法

### 2.1 用法总表

| 平台 | 默认向量库 | 适配清单 | chunk 全文放哪 | 租户粒度 |
|---|---|---|---|---|
| dify | **weaviate**（`docker/.env.example:163`） | 31 个后端包：weaviate/qdrant/milvus/chroma/pgvector/pgvecto-rs/elasticsearch(-ja)/opensearch/oracle/couchbase/analyticdb/myscale/relyt/tidb-vector/tidb-on-qdrant/tencent/baidu/vikingdb/upstash/oceanbase/seekdb/opengauss/tablestore/huawei_cloud/matrixone/clickzetta/iris/hologres/lindorm/vastbase/alibabacloud-mysql | **向量库**（page_content 字段）；文档元数据在主 PG | 一个 dataset 一个 collection |
| anything-llm | **lancedb**（`server/utils/helpers/index.js:88`，`VECTOR_DB ?? "lancedb"`） | 10 个：lance(chroma 同构)/chroma/chromacloud/pinecone/weaviate/qdrant/milvus/zilliz/pgvector/astra | **向量库**（`metadata.text`）；docId↔vectorId 映射在关系库 | 一个 workspace 一个 namespace（lance 表） |
| kotaemon | **chroma**（`flowsettings.py:100` ChromaVectorStore）+ LanceDB docstore | vectorstores：chroma/lancedb/milvus/qdrant/in_memory/simple_file；docstores：lancedb/elasticsearch/simple_file/in_memory | **docstore**（LanceDBDocumentStore），向量库只存 embedding+引用 | 单实例单租户（展示型项目） |
| ragflow | **elasticsearch**（`docker/.env:36 DOC_ENGINE=elasticsearch`） | DocEngine 七种：elasticsearch/opensearch(镜像可选)/infinity/serenedb/oceanbase/seekdb/vastbase（`internal/engine/engine.go#L23-L31`） | **doc engine**（content_with_weight）；文档元数据在 MySQL/PG | 索引按 dataset 分，租户过滤靠 kb_id 条件 + 每租户元数据索引 |

### 2.2 dify：适配器即插件

- 架构变化：适配器已从 `api/core/rag/datasource/vdb/<vendor>/` 迁出为 **uv workspace 插件包** `api/providers/vdb/vdb-*/`（【核心】`api/pyproject.toml#L63-L65` members = `providers/vdb/*`），通过 `dify.vector_backends` entry point 注册（【核心】`api/core/rag/datasource/vdb/vector_backend_registry.py`）。适配面只剩共享类型：`vector_type.py`（VectorType 枚举 31 项）、`field.py`（字段常量）、`vector_factory.py`（AbstractVectorFactory 协议）。
- 通用字段常量【核心】`api/core/rag/datasource/vdb/field.py`：`CONTENT_KEY="page_content"`、`METADATA_KEY="metadata"`、`GROUP_KEY="group_id"`、`SPARSE_VECTOR`、`PRIMARY_KEY="id"`、`DOC_ID="metadata.doc_id"`、`DOCUMENT_ID="metadata.document_id"` —— **过滤走 JSON 路径**（metadata.doc_id），metadata 是一坨 JSON。
- collection 命名【核心】`api/models/dataset.py#L436-L438`：`gen_collection_name_by_id → f"{prefix}_{dataset_id}_Node"`，**一个知识库一个 collection**。
- milvus schema【核心】`api/providers/vdb/vdb-milvus/src/dify_vdb_milvus/milvus_vector.py#L325-L395`：`metadata` JSON(65535) + `page_content` VARCHAR(65535) + `id` INT64 auto + `vector` + （开 `MILVUS_ENABLE_HYBRID_SEARCH` 时）`sparse_vector` SPARSE_FLOAT_VECTOR，并用 milvus Function（`text_bm25_emb`, FunctionType.BM25, AUTOINDEX/metric=BM25）把 page_content 自动转稀疏向量；page_content 开 `enable_analyzer` 并允许自定义 `analyzer_params`。
- ES 适配器【核心】`api/providers/vdb/vdb-elasticsearch/src/dify_vdb_elasticsearch/elasticsearch_vector.py#L281-L300`：`page_content` type=text（BM25 可用）、`vector` dense_vector(cosine)，metadata object 内仅 doc_id/document_id 显式 keyword 化。ES 有 `-ja` 变体（日文分词版），无中文变体。
- metadata 内容【核心】`api/core/rag/index_processor/index_processor_base.py#L223-L228`：`doc_id / doc_hash / document_id / dataset_id / doc_type`。

### 2.3 anything-llm：lance 默认 + 关系库管映射

- 默认与清单【核心】`server/utils/helpers/index.js#L87-L112`（switch 分发 10 家）。
- lance schema【核心】`server/utils/vectorDbProviders/lance/index.js#L382-L396`：记录为扁平结构 `{id: uuid, vector: values, ...metadata, text: chunk}` —— metadata 直接摊平成列，`text` 列存 chunk 全文（代码注释特意保留 LangChain 兼容的 `text` key）。
- doc↔chunk 映射：`DocumentVectors` 表（`{docId, vectorId}`，`bulkInsert`）存于自有关系库（默认 SQLite，可 PG）——即"向量库存内容+向量，关系库存文档级映射"，删除/重嵌按映射表精准操作（同文件 :336-344）。另有嵌入式缓存 `cachedVectorInformation` 复用已嵌 chunk。
- 索引粒度：**一个 workspace（= 租户）一张 lance 表**（`namespace` 即表名，`namespaceCount` 直接 `openTable(_namespace)`）。

### 2.4 kotaemon：docstore/vectorstore 双库分离

- 默认【核心】`flowsettings.py#L92-L104`：`KH_DOCSTORE = LanceDBDocumentStore`、`KH_VECTORSTORE = ChromaVectorStore`（Lance/Milvus/Qdrant 以注释形式列出备选）。实现即 llama-index wrapper：`libs/kotaemon/kotaemon/storages/vectorstores/chroma.py#L20-L21`（`stores_text=True, flat_metadata=True`）。
- 设计：**全文住 docstore，向量库持 embedding 与 node 引用**，检索后回 docstore 取原文——是四个平台里唯一"向量库不存 chunk 正文"的（chroma 的 stores_text=True 会冗余存一份，但事实源是 docstore）。

### 2.5 ragflow：为什么是 ES/Infinity（Go 重写后依然成立）

- 核心设计：**根本不引入独立向量库**，文档引擎一身二任（BM25 全文 + KNN 向量）。抽象接口【核心】`internal/engine/engine.go#DocEngine`：`CreateChunkStore / InsertChunks / Search / SearchMetadata / KNNScores / RunSQL / SupportsPageRank / FilterDocIdsByMetaPushdown`——一个接口同时定义了 chunk 存储、元数据存储、向量打分、SQL 透传。实现七种引擎（elasticsearch/infinity/oceanbase/seekdb/serenedb/vastbase），compose 里另有 opensearch 2.19.1 镜像（【核心】`docker/docker-compose-base.yml#L5-L190`）。
- 混合检索协议【核心】`internal/engine/types/types.go#L144-L166`：`MatchTextExpr + MatchDenseExpr + FusionExpr` 三元组。Infinity 侧把 FusionExpr 映射为原生 `table.Fusion("weighted_sum", topN, {normalize:"atan"})`（【核心】`internal/engine/infinity/chunk.go#L1185-L1217`）；ES 侧 text 路 boost=(1-w)、knn 路 weight=w，首段用固定权重召回、`vector_similarity_weight` 在 RerankWithKNN 阶段二次应用（【核心】`internal/engine/elasticsearch/chunk.go#L1206-L1330` 与 `internal/service/nlp/retrieval.go#L623-L641`，后者注释明确"Matches rag/nlp/search.py:331"保持与旧 Python 版行为一致）。
- schema【核心】：向量字段名 `q_<dim>_vec`（`internal/ingestion/knowledge_compile/writer.go#L571`），chunk 正文 `content_with_weight`，可更新字段 `important_keywords / questions / available_int / positions / tag_kwd / tag_feas`（`internal/handler/chunk.go#L588-L599`）；字段后缀 `_kwd/_int/_ltks/_fea` 编码 ES mapping 类型，`tag_feas` 显式建 `rank_features`（`internal/engine/elasticsearch/chunk.go#L88-L108`）。
- 中文【核心】：自带 Go 版 rag tokenizer（`internal/tokenizer/tokenizer.go#Tokenize/#FineGrainedTokenize`，spm/bpe 词表，注释"matching Python rag_tokenizer"），**写入前预分词**存进 `*_ltks` 字段——因为 "Elasticsearch has no server-side rag tokenizer"（`internal/engine/elasticsearch/chunk.go#L2009-L2015` 注释原文）；而 Infinity 路径 "stores content verbatim and lets Infinity tokenize on save"。即：ES 方案的中文 BM25 靠**应用层预分词**，Infinity 靠**引擎内置分词**。
- 多租户【核心】：chunk 索引按 dataset 建（`CreateChunkStore(baseName, datasetID...)`），检索强制 `kb_ids` bool 过滤（`buildBoolQueryFromCondition(req.Filter, req.KbIDs, ...)`）；文档元数据另建**每租户独立索引** `ragflow_doc_meta_<tenantID>`（`internal/engine/elasticsearch/common.go#L97-L99`）；近期还有多租户检索范围修复 `git log e7a3aef79 "fix: correct multi-tenant retrieval scope"`。

### 2.6 谁把 chunk 全文存进向量库

| 平台 | 正文位置 | 代价/收益 |
|---|---|---|
| dify | 向量库（page_content） | 换向量库需要搬迁正文；检索即取即用 |
| anything-llm | 向量库（metadata.text） | 同上；靠 DocumentVectors 表做文档级删除 |
| ragflow | doc engine（content_with_weight） | 全文检索本来就需要正文在同引擎 |
| kotaemon | docstore（LanceDB），向量库只存向量 | 换向量库零搬迁，代价是检索后多一次回表 |

## 3. 中文混合检索专题（谁能做中文 BM25）

| 引擎 | 中文 BM25 能力 | 证据 |
|---|---|---|
| Elasticsearch | ✅ IK 等分析器生态（引擎外挂插件）；ragflow 实践是**不装 IK**、应用层预分词进 `_ltks` 字段 | 【核心】ragflow `internal/engine/elasticsearch/chunk.go#L2009`（"no server-side rag tokenizer"）；dify ES 适配器用默认 text 分析器，中文按字切分效果有限 ⚠️（未验证 dify 中文检索效果，属推断） |
| Infinity | ✅ 内置中文分词，保存时切词 | 【核心】ragflow `chunk.go#L2015` 注释 "lets Infinity tokenize on save" |
| milvus | ✅ analyzer 内置 **jieba** tokenizer，BM25 Function 与 TEXTMATCH/PHRASEMATCH 过滤同源同分词 | 【核心】`internal/core/src/segcore/tokenizer_c.cpp` + 【示例】`tests/go_client/testcases/full_text_search_test.go#L73`（Chinese_Jieba 活测试；Python 侧中文用例被 skip，见 §1.1 注） |
| qdrant | ⚠️ **分路径**：payload 全文索引（Multilingual/charabia，Cargo 开启 chinese-segmentation）支持中文；新版服务端 BM25 稀疏向量（`lib/bm25`）只按空白切分，**中文整句成 token 基本不可用**，需客户端预分词喂稀疏向量 | 【核心】`lib/segment/Cargo.toml#L105-L110` vs `lib/bm25/src/basic_tokenizer.rs#L25-L27` |
| pgvector | ❌ 本体无分词；走 PG FTS 需外挂 zhparser/pg_jieba（生态事实，仓库内无证据） | 【文档】README:635 |

结论：**要"一个引擎同时中文 BM25 + 向量"**，开源里现成可用的是 ES(+IK 或预分词)、Infinity、milvus(2.5+ analyzer)；qdrant 中文全文走 payload 索引可行但与稀疏向量 RRF 融合路线（Query API）拼不起来（两条路径分数不互通），是个实际限制 ⚠️。

## 4. 自建选型决策树（素材）

- **已有 PG、规模 < 千万 chunk**：pgvector + SQL WHERE 过滤 + iterative_scan；混合检索用 `tsvector`（中文外挂分词扩展）+ 应用层 RRF。零新增组件、事务一致、DBA 可运维。上限：单写者、HNSW 内存占用大（无量化，用 halfvec 缓解）。
- **< 1M chunk、轻量私有部署**（类 anything-llm 场景）：嵌入式/单机方案——qdrant 单二进制、milvus standalone/lite、lancedb（纯嵌入式，anything-llm 默认即此）、chroma（kotaemon 默认）。
- **多租户 SaaS、单 collection 大规模**：qdrant（单 collection + tenant payload 索引 + filter，官方主推模式）或 milvus（partition key 物理隔离 + partition-key isolation 强化隔离）。dify 的"一租户/知识库一 collection"模式在租户数大时管理成本高（31 家适配器都要处理 collection 膨胀），milvus/qdrant 官方姿势都是共享 collection + 过滤。
- **需要混合检索 + 中文分词、不想拼两个引擎**：首选 ES/Infinity（ragflow 路线，全文与向量同引擎、同一次查询融合）；次选 milvus（BM25 function + jieba + HybridSearch rrf/weighted）。qdrant 中文场景只能选 payload 全文索引路径或客户端分词。pgvector 需要自己组装的部件最多。
- **融合算法要求**：qdrant（RRF 权重化 k=2 / DBSF）与 milvus（rrf k=60 / weighted / decay / model 外接 rerank）都在库内完成；pgvector 全在应用层。注意两家 RRF 默认 k 差 30 倍（2 vs 60），调参语义不同。

## 5. 证据清单与存疑

### 5.1 关键证据（按主题）

- milvus：文法 `internal/parser/planparserv2/Plan.g4#L22-L30`；BM25 function `internal/util/function/function.go#L38-L42`；jieba【示例】`tests/python_client/milvus_client/test_milvus_client_search_text_match.py#L334`；rerank `internal/util/function/chain/rerank_builder.go#L39-L52`、`internal/util/function/rerank/`（8 家 provider）；HybridSearch `internal/proxy/impl.go#L3114`；partition key `internal/proxy/task.go#L214-L252` + `pkg/common/common.go#L80`；隔离开关 `pkg/common/common.go#L672`；稀疏索引 `internal/core/src/index/Utils.cpp#L53-L80`；xgboost rescore `internal/core/src/rescores/`；部署 `docker-compose.yml#L97-L124`、`README.md#L22`、`configs/milvus.yaml#L174,#L764-L768`；RLS/拼音设计 `docs/design-docs/design_docs/20250610-rls_design.md`、`20260209-pinyin_filter.md`。
- qdrant：fusion `lib/segment/src/common/reciprocal_rank_fusion.rs`（k=2）、`score_fusion.rs`（DBSF=Sum+3σ）、调度 `lib/collection/src/shards/local_shard/query.rs#L426-L437`；tokenizers `lib/segment/src/data_types/index.rs#L271-L277`、charabia 中文特性 `lib/segment/Cargo.toml#L105-L110`；BM25 crate `lib/bm25/src/{lib,basic_tokenizer}.rs`；量化 `lib/quantization/src/`（含 turboquant）；HNSW `lib/segment/src/types.rs#L816-L828`；struct payload `lib/segment/src/index/struct_payload_index/payload_index.rs`；嵌入 `lib/edge/README.md`。
- pgvector：README 全文（Filtering/Iterative/Multitenancy/类型上限/halfvec/hybrid 提示），`sql/vector.sql`，`src/{hnsw*,ivf*}.c`。
- dify：默认 `docker/.env.example:163`；包清单 `api/providers/vdb/`（31 个）+ workspace 声明 `api/pyproject.toml#L63-L65` + 注册 `vector_backend_registry.py`；字段 `field.py`；命名 `api/models/dataset.py#L436-L438`；milvus schema `milvus_vector.py#L325-L395`；ES mapping `elasticsearch_vector.py#L281-L300`；metadata `index_processor_base.py#L223-L228`。
- anything-llm：默认 `server/utils/helpers/index.js#L87-L112`；lance schema `lance/index.js#L382-L396`；映射表同文件 :336-344。
- kotaemon：`flowsettings.py#L92-L104`；`libs/kotaemon/kotaemon/storages/vectorstores/chroma.py#L20-L21`。
- ragflow：接口 `internal/engine/engine.go#L23-L100`；默认 `docker/.env:36`；引擎镜像 `docker/docker-compose-base.yml#L5-L190`；三元组 `internal/engine/types/types.go#L144-L166`；Infinity fusion `internal/engine/infinity/chunk.go#L1185-L1217`；ES 加权与注释 `internal/engine/elasticsearch/chunk.go#L1206-L1330,#L2009-L2039`；检索侧 `internal/service/nlp/retrieval.go#L607-L641`；租户元数据索引 `internal/engine/elasticsearch/common.go#L97-L99`；字段命名 `internal/ingestion/knowledge_compile/writer.go#L571`、`internal/handler/chunk.go#L588-L599`；Go 重写 `git log 670e68872`、`e7a3aef79`。

### 5.2 存疑与未查证

1. ⚠️ milvus 索引类型全集在 knowhere 外部库，本仓库只见引用与测试模板；GPU/DiskANN 的生产配置面未深挖（超出 RAG 功能面范围）。
2. ⚠️ qdrant 官方多租户最佳实践（payload_m、单 collection vs 多 collection 的量化收益对比）在 qdrant.tech 文档站，仓库内无对应文档，本次未克隆验证。
3. ⚠️ pgvector 中文 FTS（zhparser/pg_jieba）与 SQL 级 RRF 模板均属 PG 生态外部内容，仓库内无证据，标注为生态事实。
4. ⚠️ dify ES 适配器默认 text 分析器对中文的实际检索效果未实测（推断：按字切分，弱于 IK；ragflow 用预分词绕开即旁证 ES 默认分析器不适合中文）。
5. ⚠️ qdrant payload 全文索引分数与新 BM25 稀疏路分数能否在同一次 Query API 里 RRF——从代码看全文索引走 filter/match 路径而非 scoring prefetch，两路融合未找到直接证据，按"不互通"处理。
6. ⚠️ milvus jieba analyzer 的分词质量（是否有自定义词典能力）在 tantivy-bench 外部子模块，未深入。
7. ℹ️ ragflow 的 seekdb/serenedb/vastbase/oceanbase 四个新引擎是近半年为国产化/一体机场景新增（compose 镜像可证存在），各自成熟度未评估。
