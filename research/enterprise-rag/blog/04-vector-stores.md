# 给 Agent 造知识库（四）：检索引擎选型对比——ES、milvus、pgvector、qdrant 与嵌入式方案

> 本文事实基于 2026-10 冻结的开源源码基线与当日可访问的官方文档，源码基线 commit 见文末参考节。

上一篇定下了 chunk 与 schema，这一篇回答一个躲不开的问题：**这些 chunk 落进哪个引擎**。我的立场先摆出来：引擎选型决定的不是"谁跑分高"，而是**你后面要自建多少东西**——过滤语法、混合检索、中文分词、融合算法，每一项要么引擎白送、要么你自己拼。尤其中文场景，"一个引擎能不能同时做中文 BM25 和向量检索"这一问，直接把候选砍掉一半。

先交代证据口径：milvus（`milvus-io/milvus@55b4415230`）、qdrant（`qdrant/qdrant@016542aa5`，1.19.2）、pgvector（`pgvector/pgvector@f37c13f`，0.8.7）三仓源码级对码；**ES 本体不在本轮克隆基线内**，它的行为证据来自 ragflow 的引擎适配层代码与平台用法，IK 分析器等属「生态通识，未源码级验证」；Infinity/Weaviate/OpenSearch 同理（经 ragflow/dify/quivr 的使用方式带出）。

## 一、三条路线总述

### 路线一：文档引擎路线——一库双能力

用一个"本来就会全文检索"的引擎同时做 BM25 与 KNN：ES / OpenSearch / Infinity / Weaviate。ragflow 是这条路线的旗手：它**根本不引入独立向量库**，文档引擎一身二任，抽象接口 `infiniflow/ragflow@deb1235be internal/engine/engine.go#DocEngine` 一个接口同时定义 chunk 存储、元数据存储、向量打分、SQL 透传（支持 elasticsearch / opensearch / infinity / serenedb / oceanbase / seekdb / vastbase 七种，默认 ES：`docker/.env:36 DOC_ENGINE=elasticsearch`）。检索协议是 `MatchTextExpr + MatchDenseExpr + FusionExpr` 三元组（`internal/engine/types/types.go:144-166`）——全文与向量在**同一次查询**里融合，不存在双写一致性问题。

Weaviate 同属此列：dify 的默认向量库是它（`langgenius/dify@79effdd498 docker/.env.example:163`），quivr V2 也用它做 lexical+vector 双路（平台用法证据，本体未克隆）。OpenSearch 在 ragflow 的部署里有现成镜像（2.19.1，`docker/docker-compose-base.yml:5-190`）；Infinity 则走"保存时引擎内分词"的路线（代码注释证据见第三节）。

### 路线二：分布式向量库——milvus 与 qdrant

为向量检索而生的专用引擎，2.x 起补齐稀疏向量与全文能力（milvus 2.5+ 的 BM25 Function 是分水岭），过滤、量化、分布式是主业。规模上限数十亿级。两家的气质不同：milvus 是"数据库做派"——自有查询 DSL、行级安全设计文档、外接 rerank provider 生态，企业权限过滤方向走得最深；qdrant 是"引擎做派"——payload 索引类型学做得最细（map/numeric/geo/bool/facet/full-text/struct 各一类），查询协议递归组合。平台侧的采用也有信号：kotaemon 的可选清单里 milvus/qdrant 并列（`flowsettings.py` 注释形式），anything-llm 的 10 家适配里 qdrant/milvus/zilliz 同列。

### 路线三：嵌入式 + SQL——pgvector / LanceDB / chroma / SQLite 系

不新增常驻服务：pgvector 是 PG 扩展（跟随 PG 部署），LanceDB/chroma/FAISS/sqlite-vec 直接嵌进应用进程。anything-llm 默认 LanceDB（`Mintplex-Labs/anything-llm@2a10d052 server/utils/helpers/index.js:88`，`VECTOR_DB ?? "lancedb"`）、kotaemon 默认 chroma + LanceDB docstore（`Cinnamon/kotaemon@9ad3e4e4 flowsettings.py:92-104`）——两家轻量平台都不约而同选了嵌入式。

平台默认值本身是个信号：**重的平台选文档引擎（ragflow→ES），轻的平台选嵌入式（anything-llm→LanceDB）**；dify 作为例外靠 31 家适配器插件把选择权交给用户。

## 二、milvus vs qdrant vs pgvector：逐项对码

看引擎对比，我建议盯四个问题：过滤表达力（决定权限/元数据过滤怎么写）、全文与稀疏能力（决定混合检索的原料）、融合在库内的程度（决定第 5 篇的配方有多少能白嫖）、多租户姿势（决定 SaaS 化的物理结构）。先上总表，再给逐项证据。

| 维度 | milvus 2.x | qdrant 1.19.2 | pgvector 0.8.7 |
|---|---|---|---|
| 过滤语法 | 自有 DSL（ANTLR 文法）：`==/in/like/JSON_CONTAINS/TEXTMATCH/PHRASEMATCH/MATCH_ANY…`，操作符最全 | JSON 条件树（must/should/must_not 嵌套） | SQL `WHERE`，天然万能 |
| 稀疏/全文 | SPARSE_FLOAT_VECTOR + BM25 Function（analyzer 经 tantivy FFI，**内置 jieba**） | sparse vector 原生 + payload 全文索引（charabia）；服务端 BM25 稀疏嵌入仅空白分词 | sparsevec 类型仅存储/距离计算，**无打分无分词** |
| 混合检索入口 | `HybridSearch` RPC：一个 collection 多向量字段一次请求 | Query API：`prefetch` 递归组合多路，末端 fusion | 无，SQL 自行 JOIN + 应用层融合 |
| 融合在库内程度 | rrf / weighted / decay / model 四类 reranker + 外接 8 家 rerank provider | 加权 RRF（默认 k=2）/ DBSF | 全 DIY |
| 多租户 | partition key（默认 16 分区）+ isolation 隔离模式；RLS 设计文档 | 单 collection + tenant payload 过滤（官方推荐模式） | README 明示：list 分区或分表 |
| 量化 | knowhere：IVF_SQ8 / IVF_PQ / SCANN / DISKANN / binary / GPU；mmap 四级可控 | SQ(int8) / PQ / Binary / TurboQuant(1~4bit)，可按 segment 混用 | 无量化；halfvec(2 字节) 降内存 |
| 部署形态 | Lite（pip 嵌入）/ standalone（etcd+minio+rocksmq）/ cluster | 单二进制；嵌入式 qdrant-edge；分布式分片+副本（raft） | PG 扩展，跟随 PG |
| 规模定位 | 数十亿级分布式 | 单机到中等集群 | 亿内（取决于 PG 运维能力） |
| License | Apache-2.0 | Apache-2.0 | PostgreSQL License |

**过滤**。milvus 的过滤文法直接写进 ANTLR 文法文件（`milvus@55b4415230 internal/parser/planparserv2/Plan.g4:22-30`）：TEXTMATCH、TEXTMATCHFUZZY、PHRASEMATCH、MATCH_ANY/LEAST/MOST/EXACT（数组阈值匹配）都在文法层，倒排索引基于 tantivy（`internal/core/src/index/InvertedIndexTantivy.h`）；设计文档里还有行级安全（`docs/design-docs/design_docs/20250610-rls_design.md`）与拼音过滤——企业权限过滤方向走得最深。qdrant 的 payload 索引按字段类型分目录建（map/numeric/geo/bool/full-text 等，`lib/segment/src/index/field_index/`），新版还有声明式 payload schema 与平滑迁移（`lib/segment/src/index/struct_payload_index/payload_index.rs`，SchemaTransition）。pgvector 的过滤就是 SQL：README 明示近似索引先扫后滤、召回不足时 0.8.0+ 开 `SET hnsw.iterative_scan = strict_order|relaxed_order`，配 `hnsw.max_scan_tuples`（默认 20000）/`ivfflat.max_probes`；低基数条件建议 partial index、高基数建议表分区。

顺带看**平台适配面**：dify 把向量库适配器做成了 uv workspace 插件（31 个 `api/providers/vdb/vdb-*` 包，经 `dify.vector_backends` entry point 注册：`api/core/rag/datasource/vdb/vector_backend_registry.py`），共享面只剩 VectorType 枚举与字段常量；ragflow 收敛为七种文档引擎一个接口；anything-llm 是 10 家的 switch 分发（`server/utils/helpers/index.js:87-112`）。三家的取舍与上一篇的 schema 两流派同构：**适配面越宽，对单引擎的深度定制越浅**——dify 能换 31 家库，但换不出 ragflow 那种字段级打分。

**混合检索入口**。milvus 的 `Proxy.HybridSearch`（`internal/proxy/impl.go:3114`）支持一个 collection 多个向量字段（dense+sparse）一次请求，多向量字段由 `internal/proxy/task.go#validateMultipleVectorFields` 校验；BM25 Function 在 `internal/util/function/function.go:38-42` 注册（FunctionType_BM25 / MinHash / TextEmbedding），还支持 per-row 选分析器（`internal/util/function/multi_analyzer_bm25_function.go`）。稀疏索引有 SPARSE_INVERTED_INDEX 与 SPARSE_WAND 两类、仅 IP 度量（`internal/core/src/index/Utils.cpp:53-80`）。qdrant 走 Query API 的 `prefetch` 递归组合（dense/sparse/filter/scroll 多路嵌套，调度在 `lib/collection/src/shards/local_shard/query.rs:426-437` 的 `recurse_prefetch`），末端做 fusion。pgvector README 全文只有一句混合检索提示："Use together with Postgres full-text search for hybrid search"（README:635）——**部件全要自己组装**。

**融合在库内的程度**（这决定你第 5 篇要讲的混合检索有多少能白嫖）。融合放在库内的好处不只是省代码：两路分数同源、同一次请求返回，避免了应用层拉两份候选集再对齐的网络与一致性开销。milvus 的 rerank 链在 `internal/util/function/chain/rerank_builder.go:39-52`：rrf / weighted / decay / model（外接 rerank 模型）四类，`defaultRRFK = 60.0`，`internal/util/function/rerank/` 下接了 cohere/tei/vllm/siliconflow/voyageai/zilliz/huggingface/ali 八家外部 provider，C++ 侧还有 xgboost 打分器（`internal/core/src/rescores/`）。qdrant 是加权 RRF（`lib/segment/src/common/reciprocal_rank_fusion.rs`，`DEFAULT_RRF_K = 2`，支持 per-source 权重）与 DBSF（`score_fusion.rs`，Sum + 3σ 分布归一化——按每路分数分布重缩放，抗离群值，与 haystack/llama_index 的 dist_based 同思想）。pgvector 全 DIY。

这里有个**跨实现的 k 值对照**值得抄进选型笔记：qdrant 默认 k=2，milvus k=60，llama_index k=60（`run-llama/llama_index@7169bcd0d llama-index-core/llama_index/core/retrievers/fusion_retriever.py`，注释引 Cormack SIGIR09 原论文），haystack k=61（论文 60 + Python 0 基修正，`deepset-ai/haystack@05cab58ac haystack/utils/misc.py`），Azure 固定 k=60（官方文档原话 "performs best when you set k to a small value, such as 60"）。**k=60 是行业默认**；qdrant 的 2 不是 bug，但调参语义完全不同——从别家迁移参数时别照抄。

**多租户**。milvus：partition key 只能 int64/varchar、不可为主键，默认 16 个分区（`pkg/common/common.go:80`），`IsPartitionKeyIsolationKvEnabled` 提供"一租户一物理分区"强化隔离（同文件 :672）。qdrant：无 partition 概念，官方姿势是单 collection + tenant 字段 payload 索引 + filter（详细的官方量化建议在 qdrant.tech 文档站，仓库内无对应文档，本轮未核）。pgvector：README 的 Multitenancy 节原话——共享近似索引会让租户互相干扰召回，"use list partitioning or separate tables"。反面参照是 dify 的"一知识库一 collection"（`api/models/dataset.py`），租户数大时 31 家适配器都要面对 collection 膨胀。

**量化与内存**。milvus 的索引类型在 knowhere 外部库，仓库内证据是测试模板（`tests/python_client/common/common_func.py:3436-3474`）与 mmap 四级开关（`configs/milvus.yaml:764-768`）。qdrant 的量化在 `lib/quantization/src/`，TurboQuant 带到 1~4 bit（枚举入口 `lib/segment/src/types.rs:1125-1130`）；HNSW 配置 `m/ef_construct/full_scan_threshold_kb`（同文件 :816-828，注释明示 1Kb 约等于一条 256 维向量，低于阈值直接全扫描）。pgvector 无量化，超 2000 维用 halfvec 表达式索引降精度（README:552-569）；类型上限：vector ≤2000 维、halfvec ≤4000、sparsevec ≤1000 非零元。

**部署重量**。milvus 三形态（README:22）：Milvus Lite 是 pip 依赖级嵌入（单机原型），standalone 依赖 etcd+minio、消息默认 rocksmq（`configs/milvus.yaml:174`），cluster 换 pulsar/kafka/woodpecker（`docker-compose.yml:97-124`）——"重"是分布式能力的价格。qdrant 一个二进制起服务，嵌入式形态是 `lib/edge/`（Rust crate + Python 绑定），分布式靠分片+副本+raft（README:149）。pgvector 跟随 PG，运维体系零新增。

## 三、中文 BM25 专题：谁能一个引擎搞定（本篇传播点）

中文混合检索的引擎分野，是本次调研最实用的结论之一。逐家过：

**milvus：内置 jieba，一等公民**。BM25 的分词器经 FFI 调 tantivy（`internal/core/src/segcore/tokenizer_c.cpp#create_tokenizer`），jieba 是内置 analyzer。证据要如实说：Go 客户端测试里有活着的中文用例（`tests/go_client/testcases/full_text_search_test.go:73-80`：jieba analyzer + 中文 query「信息检索的应用」+ BM25 function）；Python 侧对应用例在本基线被 `@pytest.mark.skip` 标记（reason="unstable: jieba tokenization vs Python substring mismatch"）——中文能力的证据以引擎实现 + Go 活测试为准，效果请自己用真实语料验证。加分项：BM25 Function 与 TEXTMATCH/PHRASEMATCH 过滤同源同分词，全文检索与过滤的中文口径一致。

**ES：靠 IK 插件或应用层预分词**。IK 分析器是成熟的引擎外挂生态（「生态通识，未源码级验证」）。ragflow 的实践更狠：**不装 IK，应用层预分词**——自带 Go 版 rag tokenizer（`internal/tokenizer/tokenizer.go`，注释 "matching Python rag_tokenizer"），写入前把分词结果存进 `*_ltks` 字段，理由写在代码注释里："Elasticsearch has no server-side rag tokenizer"（`internal/engine/elasticsearch/chunk.go:2009-2015`）；而 Infinity 路径 "stores content verbatim and lets Infinity tokenize on save"（引擎内置中文分词）。另一个旁证：dify 的 ES 适配器用默认 text 分析器（`api/providers/vdb/vdb-elasticsearch/src/dify_vdb_elasticsearch/elasticsearch_vector.py:281-300`），且它有 `-ja` 日文分词变体、没有中文变体——中文大概率按字切分、效果有限（未实测，属推断）；ragflow 专门写预分词层绕开默认分析器，本身就是"ES 默认分析器不适合中文"的工程旁证。

**qdrant：分路径，有坑**。这是选型时最容易踩的雷，拆开说：

1. **payload 全文索引路径可用**：Multilingual tokenizer 走 charabia，Cargo 特性显式开启 chinese-segmentation + chinese-normalization（`lib/segment/Cargo.toml:105-110`）。
2. **服务端 BM25 稀疏向量路径对中文无效**：新版 `lib/bm25` 是 compute-only crate，其分词器只有 `split_whitespace`（`lib/bm25/src/basic_tokenizer.rs:25-27`）——**中文整句成一个 token，基本不可用**。要么客户端自己分词后喂稀疏向量，要么放弃这条路。
3. **两条路径拼不起来（本轮按"不互通"处理）**：从代码看全文索引走 filter/match 路径而非 scoring prefetch，与 Query API 的 RRF 融合路（稀疏向量那条）在同一次查询里合并打分，未找到直接证据。做中文混合检索选 qdrant，等于在"全文索引路径（能中文、不进融合）"与"稀疏向量路径（进融合、不能中文）"之间二选一，是个实际限制。

如果已经被 qdrant 锁定又要中文，工程上的正解只有两条：全文走 payload 索引、融合退回应用层；或客户端 jieba 预分词后把稀疏向量当普通 sparse 输入喂进去（分词责任回到自己手里，与 ragflow 对 ES 的做法同构）。

**pgvector：全靠外挂**。本体无分词无打分，走 PG FTS 需外挂 zhparser/pg_jieba 等扩展（「生态事实，仓库内无证据，未源码级验证」），混合检索的融合也在应用层拼。

**结论**：要"一个引擎同时中文 BM25 + 向量"，开源里现成可用的是 **ES（应用层预分词，ragflow 路线）/ Infinity / milvus（BM25 Function + jieba）**；qdrant 中文全文走 payload 索引可行但与稀疏向量融合路线拼不起来；pgvector 需要自己组装的部件最多。

最后给一个务实的验证方法（工程建议，非档案断言）：别信任何benchmark，**拿 20-50 条自己业务里的真实 query（含口语化中文、缩写、错别字），在候选引擎上只跑 BM25 单路召回，人工标 top-10 相关性**。引擎的中文分词好不好，两个小时就能见分晓——这比读十篇对比文章都准。

## 四、嵌入式方案细讲：轻量需求的四件套

（本节引擎本体特性属「生态通识，未源码级验证」；平台用法与 llama_index 集成现状为源码/目录级证据。）

**LanceDB**：真 ANN 索引 + 列式存储的嵌入式库，数据即文件、零服务进程。anything-llm 默认选它（上文的 helpers/index.js），其 lance 记录是扁平结构 `{id, vector, ...metadata 摊平成列, text: chunk 全文}`，代码注释特意保留 LangChain 兼容的 `text` key（`server/utils/vectorDbProviders/lance/index.js:382-396`）；文档级删除/重嵌靠关系库 `DocumentVectors` 表（docId↔vectorId）精准操作（同文件 :336-344），另有嵌入式缓存 `cachedVectorInformation` 复用已嵌 chunk，重嵌时省一遍嵌入调用。一个 workspace（租户）一张 lance 表。

**Chroma**：kotaemon 的默认向量库（`flowsettings.py`，ChromaVectorStore），persist 目录模式即单机落盘。用法见 `libs/kotaemon/kotaemon/storages/vectorstores/chroma.py:20-21`（`stores_text=True, flat_metadata=True`）。kotaemon 的组合值得注意：chroma 只当向量加速器，正文在 LanceDB docstore——正是上一篇说的"正文分离"形态，嵌入式方案里换向量库同样零搬迁。

**FAISS + SQLite**：FAISS 只管 ANN 索引，元数据过滤要自己拿 SQLite 配——quivr Python 时代（quivr-core 库形态）的默认就是 FAISS 本地（历史锚点证据）。适合"检索面窄、过滤简单"的场景。

**sqlite-vec + FTS5**：一个 SQLite 文件装下向量表与全文表。中文要点：FTS5 默认按 unicode 分词对中文无效，需 trigram 分词或 jieba 预分词建外部 token 表；sqlite-vec 的向量检索是暴力扫描（无 ANN 索引），边界在十万级向量以内；并发受 SQLite 写锁约束，WAL 模式下多读单写。

**llama_index 集成现状（本轮本地验证）**：本地克隆 `run-llama/llama_index@7169bcd0d llama-index-integrations/vector_stores/` 目录实测 78 个集成包，chroma / duckdb / faiss / lancedb 都在列，**sqlitevec 无目录——已移除**。选 sqlite-vec 路线的读者注意：官方集成没了，自己写 VectorStore 接口或直接裸用 SQL。

两个中间态值得一提：milvus-lite 是 milvus 的 pip 嵌入形态（README:22 三形态之一），qdrant 有单二进制与嵌入式 `qdrant-edge`（`lib/edge/`，Rust crate + Python 绑定）——它们与各自的分布式版本同属一个引擎，从 POC 升到服务化时少一次换引擎（「生态通识，未源码级验证」）；LanceDB/chroma 的数据就是目录里的文件，迁移面小，但单机天花板也更硬。

嵌入式四件套的共同边界：单机、单写者、无分布式——POC、桌面产品、air-gap 私有化够用；文档量上百万 chunk 或多租户并发写入时，老老实实换路线一/二。

## 五、选型决策树

四个维度：**数据量 × 已有基建 × 中文需求 × 部署重量**。

```
已有 PG 运维体系，且规模 < 千万 chunk？
├─ 是 → pgvector + SQL WHERE + iterative_scan
│        混合 = tsvector + 中文分词扩展 + 应用层 RRF（自组装件最多，零新增组件、事务一致）
└─ 否 ↓
   中文混合检索优先，不想拼两个引擎？
   ├─ 是 → ES（应用层预分词，ragflow 路线）/ Infinity / milvus 2.5+（jieba + BM25 Function）
   └─ 否 ↓
      多租户 SaaS、单 collection 大规模？
      ├─ 是 → milvus（partition key + isolation）/ qdrant（tenant payload；中文全文只能走 payload 索引路径）
      └─ 否 ↓
         < 1M chunk、单机 / POC / air-gap？
         ├─ 是 → LanceDB / chroma persist / milvus-lite / qdrant 单二进制
         └─ 否 → 回到数据量与融合能力：库内融合要求高选 milvus（四类 reranker + 8 家 provider），
                  次选 qdrant（加权 RRF/DBSF），pgvector 全应用层
```

三条使用提醒：

1. **决策树是快筛不是判决**。pgvector 的"自组装件最多"在已有 DBA 团队手里可能反而是优势——事务一致、备份恢复、权限体系全是现成的；反过来，团队里没人养过 ES 集群，"一库双能力"的优势会被运维成本吃掉一半。
2. **中文需求要前置**。等检索效果不好才发现 qdrant 的 BM25 对中文无效，返工成本是全量重建索引（上一篇讲过，换分词路线约等于重嵌）。
3. **规模先动旋钮再动架构**。内存或延迟吃紧时，milvus 的 mmap 四级开关、qdrant 的 SQ/TurboQuant、pgvector 的 halfvec 都是不换引擎的降压药；量化解决不了再谈换路线。平台默认值可以抄作业：ragflow 选 ES（重、混合检索同库）、anything-llm 选 LanceDB（轻、嵌入式）——两家平台替你做过的取舍，比任何 benchmark 都诚实。
4. **顺序别反**。本篇先于检索策略讲基建，是行文顺序；实际决策顺序应该反过来——先想清楚第 5 篇的检索配方（要不要混合、融合放库内还是应用层、rerank 怎么接），再挑能让这些件白嫖最多的引擎。先选引擎再定策略，等于先买房再想通勤。
5. **别拿 collection 当租户的万能解**。"一知识库/一租户一 collection"（dify 模式）在租户规模化后要面对 §2 说过的管理成本；milvus（partition key）与 qdrant（tenant payload + filter）的官方姿势都是共享 collection 加物理/逻辑分区。

## 小结

- 三条路线：文档引擎（一库双能力，ragflow 旗手）> 专用向量库（milvus/qdrant，规模与融合能力）> 嵌入式+SQL（pgvector/LanceDB/chroma，零新增组件）；
- milvus 的融合与外接 rerank 在库内做得最深（四类 reranker + 8 家 provider），qdrant 次之（加权 RRF k=2 / DBSF），pgvector 全 DIY；RRF k=60 是跨实现行业默认（Azure 固定 60、llama_index 60、haystack 61），qdrant 的 k=2 语义不同；
- **中文 BM25 分野**：milvus 内置 jieba（Go 活测试证据）；ES 靠 IK 或预分词（ragflow 的 `_ltks` 实践）；qdrant 的服务端 BM25 只按空白切分、中文整句成 token，且 payload 全文索引与 Query API 融合路不互通；pgvector 全外挂；
- 嵌入式方案按"单机/单写者"划边界，llama_index 官方集成 chroma/duckdb/faiss/lancedb 在列、sqlitevec 已移除。

### 系列目录：《给 Agent 造知识库：企业级 RAG 搭建手记》

1. 企业级 RAG 全景：一篇文档到一段回答之间发生了什么
2. RAG 的第一道生死线：中文文档解析怎么做
3. 分块与索引：结构感知切分、双路索引与 schema 设计
4. 检索引擎选型对比：ES、milvus、pgvector、qdrant 与嵌入式方案（本篇）
5. 检索算法：混合检索、融合公式与重排的正确姿势
6. 让答案可信：引用溯源的三种实现机制
7. 开源 RAG 平台都不敢做的事：文档级权限与检索期过滤
8. 上线前后的质量防线：RAG 评测体系从零搭建
9. GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计
10. 实战设计：Python 自建轻量知识库服务，给 deepagents 供数

**下一篇预告**：引擎选定、双路召回就位，接下来是检索层的标准配方——RRF 与线性加权两流派怎么选、ragflow 的 0.7/0.3 锚点、cross-encoder 该喂原文还是分词文本。第 5 篇见。

## 参考与出处

本文基线（源码级冻结，2026-10）：`milvus-io/milvus@55b4415230`、`qdrant/qdrant@016542aa5`（1.19.2）、`pgvector/pgvector@f37c13f`（0.8.7）、`infiniflow/ragflow@deb1235be`、`langgenius/dify@79effdd498`、`Mintplex-Labs/anything-llm@2a10d052`、`Cinnamon/kotaemon@9ad3e4e4`、`run-llama/llama_index@7169bcd0d`、`deepset-ai/haystack@05cab58ac`；`The-Vibe-Company/quivr@67a6c0e9f` 仅用于 FAISS 历史锚点证据。ES/Infinity/Weaviate/OpenSearch 本体未克隆，相关断言标注生态通识或平台用法证据。

**GitHub 源码链接**：

- milvus：<https://github.com/milvus-io/milvus/blob/55b4415230/internal/parser/planparserv2/Plan.g4> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/internal/proxy/impl.go> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/internal/proxy/task.go> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/internal/util/function/function.go> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/internal/util/function/chain/rerank_builder.go> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/internal/util/function/multi_analyzer_bm25_function.go> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/internal/core/src/segcore/tokenizer_c.cpp> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/internal/core/src/index/Utils.cpp> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/pkg/common/common.go> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/tests/go_client/testcases/full_text_search_test.go> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/tests/python_client/milvus_client/test_milvus_client_search_text_match.py> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/configs/milvus.yaml> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/README.md> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/docs/design-docs/design_docs/20250610-rls_design.md>
- qdrant：<https://github.com/qdrant/qdrant/blob/016542aa5/lib/segment/src/data_types/index.rs> ·
  <https://github.com/qdrant/qdrant/blob/016542aa5/lib/segment/Cargo.toml> ·
  <https://github.com/qdrant/qdrant/blob/016542aa5/lib/bm25/src/basic_tokenizer.rs> ·
  <https://github.com/qdrant/qdrant/blob/016542aa5/lib/segment/src/common/reciprocal_rank_fusion.rs> ·
  <https://github.com/qdrant/qdrant/blob/016542aa5/lib/segment/src/common/score_fusion.rs> ·
  <https://github.com/qdrant/qdrant/blob/016542aa5/lib/collection/src/shards/local_shard/query.rs> ·
  <https://github.com/qdrant/qdrant/tree/016542aa5/lib/quantization/src> ·
  <https://github.com/qdrant/qdrant/blob/016542aa5/lib/segment/src/types.rs> ·
  <https://github.com/qdrant/qdrant/tree/016542aa5/lib/segment/src/index/field_index> ·
  <https://github.com/qdrant/qdrant/blob/016542aa5/lib/segment/src/index/struct_payload_index/payload_index.rs> ·
  <https://github.com/qdrant/qdrant/blob/016542aa5/lib/edge/README.md>
- pgvector：<https://github.com/pgvector/pgvector/blob/f37c13f/README.md>
- ragflow：<https://github.com/infiniflow/ragflow/blob/deb1235be/internal/engine/engine.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/engine/types/types.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/engine/elasticsearch/chunk.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/tokenizer/tokenizer.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/docker/.env>
- dify：<https://github.com/langgenius/dify/blob/79effdd498/docker/.env.example> ·
  <https://github.com/langgenius/dify/blob/79effdd498/api/providers/vdb/vdb-elasticsearch/src/dify_vdb_elasticsearch/elasticsearch_vector.py> ·
  <https://github.com/langgenius/dify/blob/79effdd498/api/models/dataset.py>
- anything-llm：<https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/server/utils/helpers/index.js> ·
  <https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/server/utils/vectorDbProviders/lance/index.js>
- kotaemon：<https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/flowsettings.py> ·
  <https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/kotaemon/kotaemon/storages/vectorstores/chroma.py>
- llama_index / haystack / quivr：<https://github.com/run-llama/llama_index/blob/7169bcd0d/llama-index-core/llama_index/core/retrievers/fusion_retriever.py> ·
  <https://github.com/run-llama/llama_index/tree/7169bcd0d/llama-index-integrations/vector_stores> ·
  <https://github.com/deepset-ai/haystack/blob/05cab58ac/haystack/utils/misc.py> ·
  quivr FAISS 历史锚点：<https://github.com/The-Vibe-Company/quivr/blob/947a78541/core/quivr_core/brain/brain_defaults.py>（v1-final tag，Python 版最后提交；947a78541 为 67a6c0e9f 仓库历史内的锚点 commit）

**官方文档**：

- Azure AI Search 混合检索与 RRF（k=60 固定常量）：<https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking>

**证据边界说明**：milvus jieba 的 Python 用例在本基线被 skip（unstable），中文能力证据以引擎实现 + Go 活测试为准；qdrant「payload 全文索引与 Query API 融合路不互通」为代码层未见互通证据的判定，本轮未找到反例；dify ES 适配器默认分析器的中文效果未实测（推断按字切分）；IK / zhparser / pg_jieba / LanceDB / chroma / FAISS / sqlite-vec 引擎本体特性为「生态通识，未源码级验证」；llama_index 集成目录现状（78 包、sqlitevec 已移除）为本轮本地克隆实测。
