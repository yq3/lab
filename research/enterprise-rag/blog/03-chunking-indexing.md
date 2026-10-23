# 给 Agent 造知识库（三）：分块与索引——结构感知切分、双路索引与 schema 设计

> 本文事实基于 2026-10 冻结的开源源码基线与当日可访问的官方文档，源码基线 commit 见文末参考节。

上一篇的结论是：解析层是中文场景的生死线。这一篇顺着管线往下走，讲解析之后的两个环节——**切分（chunking）**与**索引 schema**。分块决定"召回的池子里有什么"，schema 决定"这个池子能被怎样过滤、怎样打分"。这两件事做错，后面再好的混合检索和重排都是在错误的数据上做精修。

先亮出本篇三个观点：

1. **切分要结构感知，不要 markdown 盲切**。解析器已经输出了标题层级、表格边界、页码，切分层应该消费这些结构——这是解析库与平台对码后的共识做法，dify 是反例。
2. **切分策略和检索策略是一体的**。ragflow 证明：chunk 里带什么字段，直接决定检索时哪些内容拿到数倍权重。"怎么切"在入库那一刻就已经在参与排序。
3. **索引是投影，不是真相**。嵌入模型钉死版本、chunk 源与向量索引分离存储，是换模型、换引擎时不用推倒重来的救命设计（quivr 样板）。

## 一、切分策略全景

### 1.1 五种基本盘

按"信息来源从少到多"排，切分策略大致五档：

- **固定窗口**：按 token/字符数硬切 + overlap。最简单，也最浪费——句子和表格被拦腰斩断是常态。
- **递归切分**：分隔符优先级递归（段落 → 句子 → 词），碰到边界就停，超长才降级。工业默认打底方案。
- **语义切分**：相邻句嵌入相似度低于阈值处断开，块边界跟随语义而非长度。
- **父子块（small-to-big）**：小块用于检索（向量精度高），命中后换出大块（父块/整段）送生成（上下文完整）。解决"检索粒度 ≠ 生成粒度"的矛盾。
- **句子窗口**：父子块的极限形态——以单句为检索单位，命中后带出前后 N 句窗口送生成。适合精确问答。

两个框架把这份清单做成了"全家桶"。llama_index 的 node parser 目录（`run-llama/llama_index@7169bcd0d llama-index-core/llama_index/core/node_parser/`）覆盖：`text/token.py`（TokenTextSplitter，固定 token 窗口）、`text/sentence.py`（SentenceSplitter，句子级递归）、`text/code.py`（代码语法感知）、`text/semantic_splitter.py` 与 `text/semantic_double_merging_splitter.py`（嵌入断点的语义切分）、`text/sentence_window.py`（SentenceWindowNodeParser，句为检索单位、窗口为生成单位）、`relational/hierarchical.py`（HierarchicalNodeParser，多级父子块），另有文件级与 langchain 桥接。

haystack 的 preprocessors 目录（`deepset-ai/haystack@05cab58ac haystack/components/preprocessors/`）同样齐：`document_splitter.py`（word/sentence/line/page 四种 split_by + overlap）、`recursive_splitter.py`、`hierarchical_document_splitter.py`（父子层级）、`embedding_based_document_splitter.py`（语义切分）、`markdown_header_splitter.py`、`python_code_splitter.py`、`csv_document_splitter.py`，外加 cleaner/tokenizer 辅助件。

三家平台的对照（逐项出处见文末参考节）：

| 平台 | 切分实现 | 父子块 | 句子窗口 |
|---|---|---|---|
| ragflow | 12 种领域模板（JSON DSL，见第三节）+ 通用切分件 `SplitOperator`（strategy=sentence/length/boundaries，chunkSize 以 rune 计）`infiniflow/ragflow@deb1235be internal/parser/chunk/split.go` | 有（`mom_id`，检索出口换父块） | 无 |
| dify | 递归切分，默认分隔符 `["\n\n", "\n", "。", ". ", " ", ""]`（内置中文句号）；三种索引形态 general / parent-child / QA-summary | 有（PARAGRAPH / FULL_DOC 两种父形态） | 无 |
| llama_index | node parser 全家桶 | 有（AutoMerging） | 有 |
| haystack | preprocessors 12 种 | 有（AutoMerging） | 有 |
| kotaemon | TokenSplitter（1024/256）+ SentenceWindowSplitter（包装 llama_index）`Cinnamon/kotaemon@9ad3e4e4 libs/kotaemon/kotaemon/indices/ingests/files.py` | 无 | 有 |

一个值得记的巧合：kotaemon 的默认 `chunk_size=1024 / overlap=256` 与下文 Google 官方默认值完全一致——独立演化出同一组数字，说明这组参数确实落在"够大保留上下文、够小保向量精度"的甜区。

五种策略怎么配？对码五家后的结论很朴素：**先用递归 token 打底上线，用真实查询验证，再按失败模式加层**——召回不准（细节被向量稀释）就降 chunk 尺寸或加父子块；上下文断裂（答案在场但 LLM 用不上）就升父块粒度或加句子窗口；跨段关联问题多，才轮到语义切分与 LLM 增强。语义切分每个边界都要过一次 embedding 模型，索引成本数倍于递归切分，把它留给高价值库。

### 1.2 父子块三家对照：同一个思想的三种落点

父子块（small-to-big）三家的实现位置很有代表性——**同一个思想，可以放在管线的三个不同位置**：

- **切分层造层级**（llama_index / haystack）：`HierarchicalNodeParser` 预先把文档切成多级块，检索时 `AutoMergingRetriever` 统计叶子命中占比，不足阈值就向上合并父块（`llama_index@7169bcd0d llama-index-core/llama_index/core/retrievers/auto_merging_retriever.py`；haystack 同款 `haystack@05cab58ac haystack/components/retrievers/auto_merging_retriever.py`）。层级是显式数据结构。
- **索引层存关系**（dify）：`langgenius/dify@79effdd498 api/core/rag/index_processor/processor/parent_child_index_processor.py` 定义 ParentMode.PARAGRAPH / FULL_DOC 两种父形态 + `subchunk_segmentation` 子块配置；检索时子块入库被命中，出口按 `PARENT_CHILD_INDEX` doc_form 把 `child_index_node_ids` 映射回父 segment（`api/core/rag/datasource/retrieval_service.py`）。父子关系是索引里的元数据映射。
- **检索出口换块**（ragflow）：命中 chunk 若带 `mom_id` 字段，按 (mom_id, doc_id, kb_id) 分组换出父块内容——父子块完全发生在检索出口，切分层不感知（`infiniflow/ragflow@deb1235be internal/service/nlp/retrieval.go#RetrievalByChildren`）。

自建时怎么选？切分层造层级（llama_index 式）最灵活但侵入切分器；ragflow 式出口换块改造成本最低——给 chunk 加一个 `mom_id` 字段，检索出口加一步 group-by，任何已有系统都能渐进加上。

### 1.3 结构感知的前提：解析输出得有结构

五种策略里除固定窗口外都依赖"文本里有结构信号"。这正是上一篇双服务拓扑的用武之地：docling 的 HybridChunker 按文档结构树切块（chunking 模块在外部包 docling-core，`docling-project/docling@dd477a9f docling/chunking/__init__.py` 只是 re-export）；MinerU 的 content_list 输出本身就是天然块边界（`opendatalab/MinerU@b7f3dd0c mineru/render/`）。正确姿势是**拿结构输出（标题层级/表格/页码）指导切分，而不是拿 markdown 后再盲切**。

dify 是反例：解析侧用 pypdfium2 纯文本抽取（无布局模型），切分侧是含"。"的递归切分——解析与切分都最薄，扫描件在默认配置下无解。它把中文句号放进默认分隔符是加分项，但天花板在解析侧。

## 二、官方参数锚点：Google 敢给默认值

切分参数是网上吵架重灾区。给一组可用的锚点（均为**官方文档口径，非源码级验证**；Google 这批产品 2025-2026 经历 Vertex AI Search→Agent Search、RAG Engine→Gemini Data 更名，旧名资料大面积过期）：

- **默认值**：Google RAG Engine 默认 chunk_size **1024 token / overlap 256 token**；
- **实验区间**：官方建议在 **100-600 token** 之间实验，评估质量与成本的平衡；
- **LLM 增强分块的增益**（Google 自家实验，win-rate 口径）：上下文摘要 **+12.9%**、问题式分块（为 chunk 生成问答对）**+15-20%**、上下文标题 +2.7%、问题式 + 上下文标题组合 **+27-33%**。

出处：Google 官方文档 RAG Engine transformations 页（URL 见文末）。两个使用提醒：

1. Google 敢给默认数字，微软偏不给——Azure 架构指南的原话是分块方案是"a semipermanent choice"（半永久选择，换起来成本极高），按文档结构度选策略、必须按语料实验；其官方 benchmark 用的是 512 token / 25% overlap，并提醒**用 BERT tokenizer 计数而不是数字符**（中文一字一 token 的直觉在英文模型上不成立，反之亦然）。两家共识是：**数字只做起点，别当圣旨**。
2. LLM 增强分块的收益数字很诱人，但注意它和 Anthropic 的 Contextual Retrieval（为每 chunk 生成 50-100 token 定位上下文再嵌入）是同族思路——**索引侧花 LLM 成本换检索质量**，成本账要按自己的语料量算（细节留到第 5 篇）。

自建起步的务实配方（源码对码结论）：**递归 token 切分 256-512 打底**；高价值场景再加父子块或句子窗口；LLM 增强分块按预算加码。

## 三、ragflow 领域 chunk 模板：切分即检索策略

ragflow 最有辨识度的资产是**领域 chunk 模板**：切分不是一种算法，而是按文档体裁定制的解析管线模板。

### 3.1 十二份 JSON DSL

当前基线（Go 重写版）的类型枚举在 `infiniflow/ragflow@deb1235be internal/entity/dataset.go#ParserType*`：presentation / laws / manual / paper / book / qa / table / general / naive / picture / one / audio / email / knowledge_graph（naive 是 general 的别名）。实现上，12 份 JSON 模板（`template/ingestion_pipeline_{general,qa,manual,table,paper,book,laws,presentation,picture,one,audio,email}.json`）以 `go:embed` 打进二进制，每份是一段**可编辑的 ingestion pipeline DSL**——不再是旧版 Python 每模板一个硬编码类（`internal/ingestion/pipeline/builtin_registry.go`）。我本地数过该目录：恰好 12 个 JSON 文件，与注册表一致。

模板的价值不在"切得更整齐"，而在**每种模板产出的 chunk 带不同字段，而这些字段直接进入检索打分**。

### 3.2 字段级 boost：模板的检索红利

ragflow 的重排打分（无 rerank 模型路径）核心是加权 token 相似度：query 分词后构造权重字典（unigram ×0.4、相邻 bigram ×0.6，token 权重来自 NLP 词频统计的 term weighting），文档侧 token 则带**字段级 boost**：

```
content_ltks ×1 + title_tks ×2 + important_kwd ×5 + question_tks ×6
```

出处：`ragflow@deb1235be internal/service/nlp/reranker.go#RerankStandard`（权重字典构造在 `#tokensToDict`，term weighting 在 `internal/service/nlp/term_weight.go`）。最终相似度 `sim = tkW·tsim + vtW·vsim`，向量权重默认 0.3（`internal/entity/skill_search.go:52`）。

这意味着：**paper 模板抽出的章节标题 ×2、law 模板抽出的条款关键词 ×5、qa 模板的问句 token ×6**——同一份切分产物，标题和条款号天然比正文重数倍。这是"模板体系"真正的检索价值：结构化字段在切分期生成、在检索期变现。另有 tag 命中分 ×10 与 PageRank 直接加进最终分（`internal/service/nlp/retrieval.go#applyRankFeatureScores`，tag 数据落在 `tag_feas` 字段、显式建 ES `rank_features` 类型：`internal/engine/elasticsearch/chunk.go#L88-L108`）。

一个锚点补充（历史源码证据）：纯 Python 时代的查询侧还有 ES multi_match 字段 boost `title^10 / important^30 / question^20 / content^2`（锚点 2508c46c8 `rag/nlp/query.py:31-39`），索引侧 boost 与今天 Go 版逐项一致（锚点 `rag/nlp/search.py:322`）。两代实现都认同一件事：**字段权重是切分层与检索层的共同资产**。

### 3.3 Python 版曾有 15 个模板：Go 版丢了两个

历史锚点对照给出一个回归项：纯 Python 时代的模板工厂是 16 键 15 模块（锚点 `rag/svr/task_executor.py:84-101`，`rag/app/` 每模板一个 .py），比 Go 版多出 **resume**（2740 行简历结构化解析器）与 **tag**（160 行，Excel/CSV 内容抽标签对写入 `tag_kwd`，喂给上文的 rank_feature 链路）。Go 版 12 个 JSON 模板与 ParserType 枚举中两者皆无。需要如实标注：这一"回归"判定基于代码存在性，是否被官方以其他形式主动废弃未查 release notes；如果你依赖简历解析或自动打标，选型 ragflow 前要自己验证现状。

自建启示：不必照抄 12 个模板，但**"按体裁选切分模板 + 模板产出加权字段"**这个两层设计值得搬——chunk 元数据里预置 title/question/keywords 字段，检索层给它们倍率，成本极低、收益直接。

## 四、索引 schema 两流派：JSON blob 与强类型字段

切好的 chunk 落库，第一个设计决策是 schema 怎么定。开源平台分成了两个流派。

### 4.1 dify：metadata-as-JSON-blob

dify 的向量库适配面极宽（31 个后端包，已迁移为 uv workspace 插件 `langgenius/dify@79effdd498 api/providers/vdb/`，经 `dify.vector_backends` entry point 注册：`api/core/rag/datasource/vdb/vector_backend_registry.py`），共享字段常量只有一页（`api/core/rag/datasource/vdb/field.py`）：`CONTENT_KEY="page_content"`、`METADATA_KEY="metadata"`、`DOC_ID="metadata.doc_id"`——**过滤走 JSON 路径，metadata 是一坨 JSON**。

以 milvus 适配器为例（`api/providers/vdb/vdb-milvus/src/dify_vdb_milvus/milvus_vector.py`）：`metadata` JSON(65535) + `page_content` VARCHAR(65535) + `id` INT64 自增 + `vector`；开启 `MILVUS_ENABLE_HYBRID_SEARCH` 时再加 `sparse_vector` SPARSE_FLOAT_VECTOR，并用 milvus Function（`text_bm25_emb`，FunctionType.BM25）把 page_content 自动转稀疏向量——page_content 字段开 `enable_analyzer`、可自定义 `analyzer_params`。collection 命名一知识库一个：`{prefix}_{dataset_id}_Node`（`api/models/dataset.py`）。

这个流派的代价与收益都直白：一套 schema 通吃 31 家引擎，适配器写起来快；代价是过滤条件被压进 JSON 路径（`metadata.doc_id`），引擎侧的类型语义、专用索引、字段级打分能力都被抹平——ragflow 式的"某字段 ×5"在 blob 流派里没有落点。

### 4.2 ragflow：强类型字段，后缀编码引擎类型

ragflow 走另一头：chunk 字段全部强类型，字段名后缀直接编码引擎语义——向量字段 `q_<dim>_vec`（`infiniflow/ragflow@deb1235be internal/ingestion/knowledge_compile/writer.go:571`）、正文 `content_with_weight`、`*_kwd`（关键词）、`*_ltks`（分词结果）、`*_int`（数值）、`*_fea`（rank feature）。可人工干预的检索字段（`important_keywords / questions / available_int / positions / tag_kwd / tag_feas`）在 chunk 更新接口里显式暴露（`internal/handler/chunk.go:588-599`）。

收益：ES mapping 可以按字段精确定型（`tag_feas` 建 `rank_features`），字段级 boost、过滤、聚合都有的放矢；代价：schema 与引擎深度耦合，换引擎要重写映射层。ragflow 敢这么做，因为它只支持七种文档引擎（`internal/engine/engine.go#DocEngine`：elasticsearch / opensearch / infinity / serenedb / oceanbase / seekdb / vastbase），而 dify 要伺候 31 家。

### 4.3 chunk 正文存引擎内，还是 docstore 分离

第二个决策：chunk 全文放哪。

| 平台 | 正文位置 | 代价 / 收益 |
|---|---|---|
| dify | 向量库（page_content 字段） | 检索即取即用；换向量库要搬迁正文 |
| anything-llm | 向量库（`metadata.text` 列，`Mintplex-Labs/anything-llm@2a10d052 server/utils/vectorDbProviders/lance/index.js:382-396`，记录是扁平结构、metadata 摊平成列） | 同上；靠关系库 `DocumentVectors` 表（docId↔vectorId）做文档级删除/重嵌 |
| ragflow | 文档引擎（content_with_weight） | 全文检索本来就需要正文同引擎，天然一致 |
| kotaemon | **docstore（LanceDBDocumentStore），向量库只存 embedding 与引用**（`Cinnamon/kotaemon@9ad3e4e4 flowsettings.py:92-104`） | 四家唯一分离：换向量库零搬迁，代价是检索后多一次回表 |

（细节：kotaemon 默认向量库 chroma 的 wrapper 标了 `stores_text=True`，会冗余存一份正文，但事实源是 docstore——见 `libs/kotaemon/kotaemon/storages/vectorstores/chroma.py:20-21`。）

我的看法：**正文分离（kotaemon 式）是被低估的选项**。它多一次回表，但换来的是"向量库纯变成可替换的 ANN 加速器"——与下一节的可重建架构天然配套。规模大到回表成为瓶颈时再合并也不迟。

### 4.4 双路索引在 schema 上的落点

本系列第 5 篇要讲的混合检索（BM25 + 向量双路），在 schema 层的预埋就是**双字段**：

- milvus：一个 collection 多向量字段（dense + sparse）由 `milvus-io/milvus@55b4415230 internal/proxy/task.go#validateMultipleVectorFields` 校验放行，稀疏侧由 BM25 Function 生成（`internal/util/function/function.go`，FunctionType_BM25）；
- ES：全文与向量同索引，检索协议是 `MatchTextExpr + MatchDenseExpr + FusionExpr` 三元组（`ragflow@deb1235be internal/engine/types/types.go:144-166`）；
- dify 的 milvus 适配即上文 sparse_vector + Function 的组合。

切分层要配合的是：双路意味着**分词结果与原文都要留**——ragflow 存 `content_with_weight`（原文，给向量与重排）+ `content_ltks`（预分词，给 BM25）。中文场景这一对字段的必要性，第 4 篇展开。

### 4.5 第三个预埋：权限字段

还有一个容易被漏的 schema 决策：**权限**。本系列第 7 篇会展开——开源五平台的权限粒度全部止步于知识库/工作区级，文档级 ACL 要自研；而自研的正确落点恰恰在 schema 层：把 doc→用户/组的 ACL 冗余成检索索引的一个字段，查询时在引擎内过滤，而不是应用层 post-trim。托管服务是这么做的（Google 文档级 ACL 的 `acl_info.readers.principals` 随索引摄入，查询时带用户身份过滤，官方文档口径）；引擎侧也接得住——milvus 标量过滤、qdrant payload、ES bool 查询都支持这种字段过滤（源码对码结论）。入库时多带一列，是整个权限体系成本最低的入场券，事后补则要全量重嵌。

## 五、嵌入模型钉版本与索引可重建

最后一个设计决策，回答两个必然会来的问题："嵌入模型想换怎么办""向量库想换怎么办"。

**换嵌入模型 = 全量重嵌，没有增量路径**——不同模型的向量空间不兼容，混库即乱码。两个侧面证据：dify 的多知识库并行检索要求所有库同 embedding 模型，否则强制走 rerank 模型模式（`dify@79effdd498 api/core/rag/retrieval/dataset_retrieval.py`）；ragflow 的多 dataset 联合检索同样先校验同 embedding 模型（`ragflow@deb1235be internal/service/dataset/search.go#SearchDatasets`）。既然重嵌不可避免，**架构上就要把"重建"当成一等操作设计**——quivr 是本轮调研里唯一把这件事说破并做进代码的样板：

- **真相源与投影分离**：PostgreSQL 17 + SeaweedFS（S3 兼容）是 canonical 真相，Weaviate 索引只是可随时重建的投影（`The-Vibe-Company/quivr@67a6c0e9f deploy/compose/compose.yaml`，quivr 不在文首基线表内、commit 见参考节）；
- **嵌入模型钉死**：TEI 容器固定 `multilingual-e5-small`（384 维），防向量空间漂移——换模型是显式的运维事件，不是悄悄的配置变更；
- **重建是代码不是文档**：`internal/retrieval/rebuild.go` 负责向量索引重建，Temporal 的 backfill 工作流（`internal/orchestration/temporal/backfill.go`）负责重放摄取；其设计甚至允许"文本先分段即刻可搜（lexical 路），嵌入后台补齐，向量重建期间关键字结果仍在场"（README 自述 "Useful early, richer later"）。

ragflow 的物质基础类似（原始文件在 MinIO、任务态在 MySQL，摄取任务带断点续跑），但把"可重建"写成显式承诺的只有 quivr。反面对照是 dify：没有独立对象存储（文件在本地卷/DB），正文又在向量库里——换引擎时两层都要搬。自建清单三件套：**嵌入模型版本写进 collection 元数据并校验；chunk 源（docstore/对象存储）与向量索引分离；重建做成幂等任务而不是手写脚本**。

## 小结

- 切分打底用递归 token（256-512），结构感知（docling 结构树 / MinerU content_list）是正确姿势，Google 默认 1024/256、实验区间 100-600 可作锚点；
- 高价值场景加父子块——ragflow 式 `mom_id` 出口换块改造成本最低；句子窗口留给精确问答；
- 学 ragflow 的"模板产出加权字段"（title×2 / important_kwd×5 / question_tks×6），但注意 Go 版已丢 resume/tag 两模板；
- schema 两流派按适配面取舍：多引擎适配选 JSON blob（dify），深度用引擎能力选强类型（ragflow）；正文分离（kotaemon）换可替换性；
- schema 层预埋三件事：双路字段（原文 + 分词）、加权字段（title/keywords/question）、权限字段（ACL 冗余进索引）；
- 嵌入模型钉版本、索引当投影（quivr），重建做成幂等任务。

### 系列目录：《给 Agent 造知识库：企业级 RAG 搭建手记》

1. 企业级 RAG 全景：一篇文档到一段回答之间发生了什么
2. RAG 的第一道生死线：中文文档解析怎么做
3. 分块与索引：结构感知切分、双路索引与 schema 设计（本篇）
4. 检索引擎选型对比：ES、milvus、pgvector、qdrant 与嵌入式方案
5. 检索算法：混合检索、融合公式与重排的正确姿势
6. 让答案可信：引用溯源的三种实现机制
7. 开源 RAG 平台都不敢做的事：文档级权限与检索期过滤
8. 上线前后的质量防线：RAG 评测体系从零搭建
9. GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计
10. 实战设计：Python 自建轻量知识库服务，给 deepagents 供数

**下一篇预告**：chunk 终究要落进一个引擎。ES、milvus、pgvector、qdrant 还是嵌入式方案？中文 BM25 谁能一个引擎搞定、谁会掉坑里？第 4 篇逐项对码。

## 参考与出处

本文基线（源码级冻结，2026-10）：`infiniflow/ragflow@deb1235be`、`langgenius/dify@79effdd498`、`run-llama/llama_index@7169bcd0d`、`deepset-ai/haystack@05cab58ac`、`Cinnamon/kotaemon@9ad3e4e4`、`Mintplex-Labs/anything-llm@2a10d052`、`docling-project/docling@dd477a9f`、`opendatalab/MinerU@b7f3dd0c`、`milvus-io/milvus@55b4415230`；另有 `The-Vibe-Company/quivr@67a6c0e9f`（历史锚点轮基线）。Google/Azure 数字为官方文档口径（网络级，非源码）。

**GitHub 源码链接**：

- ragflow：<https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/nlp/reranker.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/nlp/retrieval.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/nlp/term_weight.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/entity/dataset.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/ingestion/pipeline/builtin_registry.go> ·
  <https://github.com/infiniflow/ragflow/tree/deb1235be/internal/ingestion/pipeline/template> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/ingestion/knowledge_compile/writer.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/handler/chunk.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/engine/elasticsearch/chunk.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/engine/types/types.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/parser/chunk/split.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/entity/skill_search.go> ·
  <https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/dataset/search.go>
- dify：<https://github.com/langgenius/dify/blob/79effdd498/api/core/rag/splitter/fixed_text_splitter.py> ·
  <https://github.com/langgenius/dify/blob/79effdd498/api/core/rag/index_processor/processor/parent_child_index_processor.py> ·
  <https://github.com/langgenius/dify/blob/79effdd498/api/core/rag/datasource/retrieval_service.py> ·
  <https://github.com/langgenius/dify/blob/79effdd498/api/core/rag/datasource/vdb/field.py> ·
  <https://github.com/langgenius/dify/blob/79effdd498/api/core/rag/datasource/vdb/vector_backend_registry.py> ·
  <https://github.com/langgenius/dify/blob/79effdd498/api/providers/vdb/vdb-milvus/src/dify_vdb_milvus/milvus_vector.py> ·
  <https://github.com/langgenius/dify/blob/79effdd498/api/models/dataset.py> ·
  <https://github.com/langgenius/dify/blob/79effdd498/api/core/rag/retrieval/dataset_retrieval.py>
- llama_index：<https://github.com/run-llama/llama_index/tree/7169bcd0d/llama-index-core/llama_index/core/node_parser> ·
  <https://github.com/run-llama/llama_index/blob/7169bcd0d/llama-index-core/llama_index/core/retrievers/auto_merging_retriever.py>
- haystack：<https://github.com/deepset-ai/haystack/tree/05cab58ac/haystack/components/preprocessors> ·
  <https://github.com/deepset-ai/haystack/blob/05cab58ac/haystack/components/retrievers/auto_merging_retriever.py>
- kotaemon：<https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/flowsettings.py> ·
  <https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/kotaemon/kotaemon/indices/ingests/files.py> ·
  <https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/kotaemon/kotaemon/storages/vectorstores/chroma.py>
- anything-llm：<https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/server/utils/vectorDbProviders/lance/index.js>
- quivr：<https://github.com/The-Vibe-Company/quivr/blob/67a6c0e9f/deploy/compose/compose.yaml> ·
  <https://github.com/The-Vibe-Company/quivr/blob/67a6c0e9f/internal/retrieval/rebuild.go> ·
  <https://github.com/The-Vibe-Company/quivr/blob/67a6c0e9f/internal/orchestration/temporal/backfill.go>
- docling / MinerU / milvus：<https://github.com/docling-project/docling/blob/dd477a9f/docling/chunking/__init__.py> ·
  <https://github.com/opendatalab/MinerU/tree/b7f3dd0c/mineru/render> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/internal/proxy/task.go> ·
  <https://github.com/milvus-io/milvus/blob/55b4415230/internal/util/function/function.go>

**官方文档**：

- Google RAG Engine 数据转换（分块默认值/实验区间/LLM 增强分块增益）：<https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/rag-engine/fine-tune-rag-transformations>
- Azure RAG 解决方案设计与评估指南（分块策略口径）：<https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-solution-design-and-evaluation-guide>

**证据边界说明**：ragflow Python 锚点证据（15 模板、查询侧字段 boost）来自 git 历史锚点 2508c46c8（worktree 只读考古）；resume/tag 回归判定基于代码存在性，未核实官方 release notes；Google/Azure 数字为官方文档口径；kotaemon TokenSplitter 默认值为源码证据。
