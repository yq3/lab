# 维度 04：检索策略与重排（Hybrid / Fusion / Rerank / Query Transform / 引用溯源）

> 对象：`infiniflow/ragflow`（基线 deb1235be，**注意：该基线已重写为 Go**，检索逻辑在 `internal/`，旧 `rag/nlp/` Python 路径已不存在，本文全部用 Go 源码取证）、`run-llama/llama_index`（基线 7169bcd0d）、`deepset-ai/haystack`（基线 05cab58ac）、`Cinnamon/kotaemon`（基线 9ad3e4e4）、参照 `langgenius/dify`（基线 79effdd498）。
> 问题意识：分块与 embedding 决定"召回的池子里有什么"，而**检索策略与重排直接决定"送给 LLM 的是什么"**——这是回答质量的最后一道闸门。本文对码回答：混合检索的融合公式各家怎么写（加权 vs RRF vs 分布归一）、rerank 模型怎么接（谁支持无 API 本地推理）、查询变换（HyDE/多查询/分解）做到了什么程度、父子块/句子窗口等"检索视角的切分"怎么配合、引用溯源（答案→来源 chunk）谁真正做出来了。

## 1. 总表

| 维度 | ragflow（Go 重写版） | dify | llama_index | haystack | kotaemon |
|---|---|---|---|---|---|
| 混合检索 | ES/Infinity 双路（BM25+kNN），引擎级 `weighted_sum` fusion + 应用层重算融合 | 三路并发（jieba 关键词/ES 全文/向量）→ 去重 → 后处理器融合 | 框架级：多 retriever + 4 种 fusion 模式任选 | Pipeline 自由组装：BM25 retriever + embedding retriever + DocumentJoiner | 双线程（向量 + docstore 全文），简单拼接无融合公式 |
| 融合公式 | `sim = tkW·tsim + vtW·vsim`（默认向量权重 0.3）；rerank 模型时 `sim = tkW·tsim + vtW·rerank_sim` | 加权模式：`vw·cosine + kw·TF-IDF-cosine`（jieba）；或直接 cross-encoder 重排；**无 RRF** | RRF（k=60）/ relative_score（min-max+检索器权重）/ dist_based（μ±3σ）/ simple（取最大分） | RRF（k=61，支持路权重）/ concatenate（去重取最高分）/ merge（同 ID 加权求和）/ distribution_based（μ±3σ 归一） | ❌ 无公式（全文命中 score=-1 排前、向量命中带真实分，交给 reranker 排） |
| rerank 接入 | `RerankModel` 统一抽象，94 个 provider 驱动（cohere/jina/voyage/nvidia/huggingface…），分数强制归一 [0,1] | ModelManager 生态（rerank 模型作为一种 model type），加权模式可完全不用模型 | postprocessor 体系：core 4 种 + 25 个集成包（cohere/jina/BGE/flashrank/TEI…） | core 只剩 LLMRanker/MetaField/LostInMiddle；**cross-encoder 已移出 core**（社区 hub）⚠️ | rerankings 目录 3 个（Cohere/Voyage/TEI）+ rankings 目录 LLM 评分 3 个 |
| 本地 rerank 推理 | ✅ huggingface.go（本地）、vllm/xinference/ollama 等 OpenAI 兼容端点 | ⚠️ 走 model_runtime 提供商（xinference 等本地服务可接，无进程内推理） | ✅ 最全：sbert（进程内 CrossEncoder）、flag-embedding（BGE）、flashrank、openvino、colbert、TEI | ❌ core 无（hub 社区组件有 TransformersSimilarityRanker） | ⚠️ TEI 走独立 HTTP 服务（tei_fast_rerank），无进程内 |
| 查询变换 | LLM 关键词提取（append 到 query）+ LLM 跨语言翻译 | ❌ 无 query rewrite 节点（仅 metadata 过滤条件用 LLM 生成） | ✅ 最全：HyDE/Decompose/StepDecompose/sub-question/multi-query（fusion 内置）/FLARE/multistep | QueryExpander（LLM 多查询扩展）+ MultiQuery 系 retriever | ❌ |
| 分块策略（检索视角） | 12 种领域 parser 模板（JSON DSL）+ 父子块（mom_id）；chunk 内字段加权（title×2/important×5/question×6） | general/parent-child/QA-summary 三形态；分段可配置分隔符+长度 | node parser 全家桶：token/sentence/semantic/sentence_window/code/hierarchical | splitter 12 种：word/sentence/line/page/recursive/hierarchical/semantic(embedding) | TokenSplitter + SentenceWindowSplitter（包装 llama_index） |
| 父子块/句子窗口 | ✅ RetrievalByChildren（子块命中换父块）；窗口 ❌ | ✅ parent-child（paragraph/full-doc 父模式）；窗口 ❌ | ✅ AutoMergingRetriever+Hierarchical；✅ SentenceWindow+MetadataReplacement | ✅ AutoMergingRetriever+hierarchical_document_splitter；✅ SentenceWindowRetriever | 窗口 ✅（Splitter 层）；父子块 ❌ |
| 引用溯源 | ✅✅ 双机制：embedding 句级归因（阈值下降搜索）+ agentic 确定性 chunk_id 提取 | ✅ chunk 级（前端展示来源 segment，无句级归因） | ⚠️ CitationQueryEngine（prompt 让 LLM 输出 [N]，来源块二次切分 512/20） | ❌ 无内置 | ✅ inline citation（LLM 输出 START/END_PHRASE 原文短语 + 程序回定位）+ 引用可视化 |
| 多知识库检索 | ✅ 多 dataset 联合（同 embedding 模型校验）；use_kg 图检索 ❌ Go 未实现 | ✅ 最丰富：多库并行合并 / function-call 路由 / ReAct 路由（dataset 即 tool） | RouterRetriever / RecursiveRetriever / SQL-join 风格组合 | MultiRetriever（并发+去重+RRF） | UI 多选 collection → scope 过滤 |

## 2. 混合检索实现：融合公式逐家对码

### 2.1 ragflow：应用层线性加权（含自研 token 相似度）

ragflow 的混合检索是「引擎粗召回 + 应用层精算」两段式【核心】`~/develop/opensource/ragflow/internal/service/nlp/retrieval.go#scoreSearchResult`：

- **召回段**：ES（或 Infinity/OceanBase 等）同时跑 BM25 全文与 kNN 向量两路。关键细节：非 Infinity 引擎的 fusion 表达式用**固定权重 `"0.001,1"`**（即召回窗口实际按向量排），用户配置的权重延后到应用层【核心】`internal/service/nlp/retrieval.go#buildRetrievalFusionExpr` + 常量 `esFusionWeights`（注释明确对齐旧 Python `rag/nlp/search.py:331` 的行为）；只有 Infinity 引擎把用户权重直接传给引擎的 `weighted_sum`（`buildInfinityFusionExpr`）。
- **融合段**（无 rerank 模型时）【核心】`internal/service/nlp/reranker.go#HybridSimilarity`：

```
sim = tkWeight·tsim + vtWeight·vsim
```

  其中 `vtWeight = vector_similarity_weight`（**默认 0.3，即关键词路占 0.7**）【核心】`internal/entity/skill_search.go:52`（`default:0.3`）；权重和必须为 1 的校验在【核心】`internal/service/similarity_weight.go#ResolveVectorSimilarityWeight`。
- **tsim 不是 BM25 原始分**，是自研加权 token 相似度：query 分词后构造权重字典——unigram 权重 `w×0.4`、相邻 bigram 权重 `max(w_i, w_i+1)×0.6`（`reranker.go#tokensToDict`），token 权重来自 NLP 词频统计的 term weighting（`internal/service/nlp/term_weight.go`，即旧 `rag/nlp term_weight.py` 的 Go 移植）；文档侧 token 更带**字段级 boost：content×1 + title×2 + important_kwd×5 + question_tks×6**【核心】`reranker.go#RerankStandard`。
- 额外信号：tag 命中与 PageRank 直接加到最终分（`applyRankFeatureScores`，注释 `tag_score*10 + pagerank`）。
- 检索参数默认值（体现工程口径）：similarity_threshold=0.2、rerank_candidates_count=64、knn_top_k=1024（上限 2048）【核心】`internal/service/dataset/search.go#SearchDatasets`。向量权重 ≥0.8 时 ES 全文路放寬 min_match（`retrieval.go#minMatch`）。

### 2.2 dify：三路并发 + 两种后处理，无 RRF

【核心】`~/develop/opensource/dify/api/core/rag/datasource/retrieval_service.py#_retrieve`：`hybrid_search` 时 ThreadPoolExecutor 并发跑三路——jieba 关键词（`keyword_search`，走 `Keyword(dataset=dataset)`）、ES 全文（`full_text_index_search` → `search_by_full_text`）、向量（`embedding_search`）——汇合后 `_deduplicate_documents` 去重，交给 `DataPostProcessor` 二选一（`api/core/rag/data_post_processor/data_post_processor.py`）：

- **weighted_score**【核心】`api/core/rag/rerank/weight_rerank.py#run`：

```
score = vector_weight · cosine(query_emb, doc_emb) + keyword_weight · cosine(TF-IDF(query), TF-IDF(doc))
```

  关键词侧是 **jieba 提词 + 局部 TF-IDF（IDF = ln((1+N)/(1+n))+1，仅在本次候选集内统计）+ cosine**——不是索引期 BM25 分数，是候选集上的重算。向量侧优先复用 chunk 已有 score，缺失时实时 embed 补算（`weight_rerank.py#_calculate_cosine`）。
- **reranking_model**：cross-encoder 直接对 (query, chunk) 打分重排（`api/core/rag/rerank/rerank_model.py#RerankModelRunner`，经 ModelManager 拿任意 rerank 提供商，支持多模态 rerank）。
- **无 RRF**：全 `core/rag` 目录 grep `rrf|reciprocal` 零命中❌。加权模式与模型模式互斥（`rerank_factory.py#RerankRunnerFactory`，仅两 case）。
- 单路语义检索也默认过 rerank：`semantic_search` 配了 rerank 模型即触发（retrieval_service.py `embedding_search` 内）。

### 2.3 llama_index：4 种 fusion 模式，教科书级实现

【核心】`~/develop/opensource/llama_index/llama-index-core/llama_index/core/retrievers/fusion_retriever.py`，`QueryFusionRetriever` 同时是**混合检索与多查询**的合体（内置 LLM 生成 `num_queries-1` 个扩展查询，`#_get_queries`）。`FUSION_MODES`（#L24）：

| 模式 | 公式 | 实现符号 |
|---|---|---|
| RECIPROCAL_RANK | `Σ 1/(rank+60)`，跨查询/检索器累加，按 hash 去重 | `#_reciprocal_rerank_fusion`（k=60，注释引 Cormack SIGIR09 原论文） |
| RELATIVE_SCORE | 每个结果集内 min-max 归一到 [0,1] → ×检索器权重 → ÷查询数 → 同节点求和 | `#_relative_score_fusion` |
| DIST_BASED_SCORE | 同上，但 min/max 取 μ±3σ（抗离群） | `#_relative_score_fusion(dist_based=True)` |
| SIMPLE | 同节点取各路最大分 | `#_simple_fusion` |

retriever 权重可选传入（不传则均分 1/n，强制归一化，`__init__`）。

### 2.4 haystack：Joiner 组件化，k=61 的 RRF

haystack 把融合做成独立组件【核心】`~/develop/opensource/haystack/haystack/components/joiners/document_joiner.py#DocumentJoiner`，四种 `JoinMode`：

- `concatenate`：去重取最高分；
- `merge`：同 ID 文档分数加权求和（weights 参数对应各输入路）；
- `reciprocal_rank_fusion`【核心】`haystack/utils/misc.py#_reciprocal_rank_fusion`：`k=61`（论文 60 + Python 0 基修正，注释写明），**支持每路权重**（resolved_weights），比 llama_index 的 RRF 多了路权重维度；
- `distribution_based_rank_fusion`【核心】`document_joiner.py#_distribution_based_rank_fusion`：每路按 μ±3σ 重缩放到 [0,1] 再拼接（去重取最高），即 llama_index DIST_BASED_SCORE 的同源思想（注释引 DBF medium 文章）。

典型混合管线即 `BM25Retriever + EmbeddingRetriever → DocumentJoiner`（docstring 官方示例）；新组件 `MultiRetriever`（experimental，`components/retrievers/multi_retriever.py`）把"多检索器并发 + 去重 + RRF"封装成单组件（内部同样调 `_reciprocal_rank_fusion`）。

### 2.5 kotaemon：有混合无融合

【核心】`~/develop/opensource/kotaemon/libs/kotaemon/kotaemon/indices/vectorindex.py#VectorRetrieval.run`（retrieval_mode: vector/text/hybrid，默认 hybrid）：双线程并发查向量库（LanceDB 等）与 docstore 全文（BM25），**结果直接拼接**——全文命中 `score=-1` 排在前、向量命中带真实分在后（`if doc not in vs_ids` 去重），无任何融合公式，排序完全交给后置 reranker 链。另有 `first_round_top_k_mult=10` 的过采样机制（do_extend 时第一轮取 10 倍候选再由 rerank 收敛）。

**小结**：融合公式三家流派——ragflow/dify 是「分数级线性加权」（要求两路分数同尺度，ragflow 用自研 token 相似度保证可比性、dify 用重算 TF-IDF 保证可比性）；llama_index/haystack 提供「排名级 RRF」（免调参、天然抗分数尺度不一）；DBF/μ±3σ 归一是两者折中。**只有 ragflow 给关键词路默认 0.7 的高权重**，其余家默认对两路更均衡。

## 3. 重排（rerank）：抽象、模型与本地推理

### 3.1 ragflow：rerank 分数也要进融合公式

【核心】`~/develop/opensource/ragflow/internal/service/nlp/reranker.go#RerankByModel`：配置 rerank 模型时不做向量召回分数融合，而是 `sim = tkWeight·tsim + vtWeight·modelSim`——**cross-encoder 分数被当作"向量相似度"成分**混入加权公式。两个工程细节值得抄：

1. **分数归一化**【核心】`#NormalizeRerankScores`：Cohere/Jina/Voyage 返回已校准的 [0,1]，NVIDIA 返回原始（常为负的）logit——归一化器检测是否在 [0,1]，出界且有区分度时 min-max 重缩放、无区分度时逐元素 clamp（注释明确镜像旧 Python `rag/llm/rerank_model.py#_normalize_rank` 契约）。
2. **喂原文不喂 token**：给 cross-encoder 的文档是 `content_with_weight` 原文而非 `content_ltks`（分词/stem 后的文本会压垮神经 reranker 的相关性分数，注释写明教训）。
3. rerank 后分页受限：配置 rerank 模型只支持 page=1（`retrieval.go:143-144`），rerank_candidates_count 默认 64 是参与重排的候选集大小。
4. rerank 驱动面极宽：`internal/entity/models/` 94 个 provider 驱动文件，rerank 作为标准模型类型贯穿（`types.go#RerankModel` + `NewRerankModel`）；本地推理由 `huggingface.go#Rerank`（进程内）与 vllm/xinference/ollama/openai_api_compatible 等自托管端点覆盖。

### 3.2 llama_index：postprocessor 体系 + 25 个集成包，本地推理最全

抽象在【核心】`llama-index-core/llama_index/core/postprocessor/node.py`（BaseNodePostprocessor，与 retriever 解耦、可插任意 query engine）。core 自带 4 个 rerank：`sbert_rerank.py`（**进程内 sentence-transformers CrossEncoder**，默认模型 `cross-encoder/stsb-distilroberta-base`）、`llm_rerank.py`（LLM 相关性打分）、`rankGPT_rerank.py`（滑动窗口 LLM 重排）、`structured_llm_rerank.py`。集成包 `llama-index-integrations/postprocessor/` 25 个，覆盖 API 系（cohere/jinaai/voyageai/nvidia/siliconflow/dashscope/bedrock/google/mixedbread/alibabacloud/aimon/pinecone-native）与**本地系（flag-embedding=BGE、flashrank、openvino、colbert、colpali、tei、contextual、rankllm）**——本地 cross-encoder 选项是五家里最多的。另有非 rerank 后处理器：`metadata_replacement.py`（句子窗口换上下文）、`optimizer.py`（LongContextReorder，lost-in-the-middle 缓解）、`node_recency.py`、`pii.py`。

### 3.3 dify / haystack / kotaemon

- **dify**：rerank 是 ModelManager 的一种模型类型（`graphon.model_runtime` ModelType.RERANK），RerankModelRunner 统一调用；weighted_score 模式可零模型运行。多模态 rerank（查询+图片）有显式分支（`rerank_model.py#fetch_multimodal_rerank`）。无进程内本地推理，本地部署走 xinference 等 HTTP 服务提供商。
- **haystack**：⚠️ 重要变化——本基线 core 的 `components/rankers/` 只剩 `llm_ranker.py`（LLM 打分）、`lost_in_the_middle.py`、`meta_field.py`、`meta_field_grouping_ranker.py`；曾经 core 里的 `TransformersSimilarityRanker` / `SentenceTransformersDiversityRanker` 已**不在 core 仓库**（全仓 grep 类定义零命中；`evaluators/sas_evaluator.py` 仍依赖 sentence-transformers 做评测），cross-encoder 重排需从 haystack 社区 hub 装组件。选型时须注意这与网上大量 haystack 2.x 教程的认知不一致。
- **kotaemon**：两层抽象——`libs/kotaemon/kotaemon/rerankings/`（base.py#BaseReranking + **CohereReranking**（默认 `rerank-v4.0-fast`）、**VoyageAIReranking**、**TeiFastReranking**（HuggingFace Text Embeddings Inference 服务的 `/rerank` HTTP 端点，自托管本地推理的正解））与 `indices/rankings/`（LLM 系：`llm.py#LLMReranking`（LLM 列表打分）、`llm_scoring.py`、`llm_trulens.py#LLMTrulensScoring`（TruLens 相关性）、`cohere.py`）。应用层【核心】`libs/ktem/ktem/index/file/pipelines.py#DocumentRetrievalPipeline`：rerankers 是**链式 Sequence**，逐个 `reranker.run(documents, query)`，LLM 类 reranker 前先截断到 top_k 控制成本（`if isinstance(reranker, LLMReranking)` 分支）。

**谁支持"无 rerank API 服务时的本地推理"**：llama_index ✅ 最全（进程内 sbert/BGE/flashrank/colbert + TEI 端点）；ragflow ✅（huggingface 进程内 + vllm/xinference 端点）；kotaemon ⚠️ 仅 TEI 自托管端点；dify ⚠️ 仅经由本地推理服务商（xinference）；haystack ❌ core 不含。

## 4. 查询变换（rewrite / multi-query / 分解 / HyDE / step-back）

| 家 | 能力 | 证据 |
|---|---|---|
| llama_index | **最全**：HyDE、查询分解、step-decompose、sub-question、多查询（fusion 内置）、多步（multistep/FLARE） | 【核心】`llama-index-core/llama_index/core/indices/query/query_transform/base.py`：`HyDEQueryTransform`#L96（LLM 生成假设性答案文档再 embed 检索）、`DecomposeQueryTransform`#L153、`StepDecomposeQueryTransform`#L259、`FeedbackQueryTransform`；【核心】`question_gen/llm_generators.py#LLMQuestionGenerator` + `query_engine/sub_question_query_engine.py`（子问题拆分并行检索再合成）；`query_engine/multistep_query_engine.py` 与 `flare/`（前瞻式主动检索）；多查询即 `fusion_retriever.py#_get_queries`（LLM 一次生成 n-1 条变体）。⚠️ step-back 在 core 未见独立实现（示例在 docs/cookbooks，标文档级） |
| haystack | LLM 查询扩展 | 【核心】`haystack/components/query/query_expander.py`（JSON 输出 n_expansions 条同义查询，few-shot prompt）；配套 `retrievers/multi_query_text_retriever.py` / `multi_query_embedding_retriever.py`（多查询并发检索，自动接 joiner）。HyDE/分解 ❌ core 无 |
| ragflow | LLM 关键词增强 + 跨语言翻译 | 【核心】`internal/service/dataset/search.go#SearchDatasets`：`keyword=true` 时 LLM 抽 3 个关键词 append 到 query（`service.KeywordExtraction` + `AppendKeywords`）；`cross_languages` 配置时 LLM 翻译 query（`service.CrossLanguages`）。无 HyDE/分解 ❌ |
| dify | ❌ 无 query rewrite | `core/rag` 与 workflow 节点 grep `rewrite` 仅命中无关文件；LLM 仅用于 metadata 过滤条件生成（`dataset_retrieval.py#_automatic_metadata_filter_func`）。工作流里可手工接 LLM 节点改写 query，但无内置原语 |
| kotaemon | ❌ 无 | — |

## 5. 分块策略：检索视角的切分（解析细节归维度 03，此处只看切分参数与检索配合）

**llama_index node parser 清单**（`llama-index-core/llama_index/core/node_parser/`）：`text/token.py`（TokenTextSplitter，固定 token 窗口）、`text/sentence.py`（SentenceSplitter，递归句子级）、`text/code.py`（代码语法感知）、`text/semantic_splitter.py`（SemanticSplitterNodeParser，embed 百分位断点）、`text/semantic_double_merging_splitter.py`、`text/sentence_window.py`（SentenceWindowNodeParser，句为检索单位、窗口为生成单位）、`text/langchain.py`（桥接）、`relational/hierarchical.py`（HierarchicalNodeParser，多级块父子）+ `file/`（文件级）。

**haystack preprocessors 清单**（`haystack/components/preprocessors/`）：`document_splitter.py`（word/sentence/line/page 四种 split_by + overlap）、`recursive_splitter.py`、`hierarchical_document_splitter.py`（父子层级，配合 AutoMergingRetriever）、`embedding_based_document_splitter.py`（语义切分）、`markdown_header_splitter.py`、`python_code_splitter.py`、`csv_document_splitter.py`、`document_cleaner.py`/`text_cleaner.py`/`sentence_tokenizer.py` 等。

**父子块 / 句子窗口的检索配合**（small-to-big 思想，五家对照）：

- llama_index：`HierarchicalNodeParser` 造层级 + `retrievers/auto_merging_retriever.py#AutoMergingRetriever`（叶子命中占比不足时向上合并父块）；句子窗口 = `SentenceWindowNodeParser` + `postprocessor/metadata_replacement.py`（命中句换出周围窗口送生成）。
- haystack：`hierarchical_document_splitter` + `retrievers/auto_merging_retriever.py`；`retrievers/sentence_window_retriever.py`（检出窗口邻居）。父子块与句子窗口双支持，组件化最干净。
- ragflow：父子块在**检索出口处**完成——【核心】`internal/service/nlp/retrieval.go#RetrievalByChildren`：命中 chunk 带 `mom_id` 字段则按 (mom_id, doc_id, kb_id) 分组换出父块内容；句子窗口 ❌。
- dify：【核心】`api/core/rag/index_processor/processor/parent_child_index_processor.py`（ParentMode.PARAGRAPH / FULL_DOC 两种父形态 + `subchunk_segmentation` 子块配置）；检索时子块入库被命中、出口按 `PARENT_CHILD_INDEX` doc_form 映射回父 segment（`api/core/rag/datasource/retrieval_service.py` `child_index_node_ids → child_chunk_map` 段）。另有 **QA-summary 索引形态**（segment 摘要命中取 max 分数回原 segment，retrieval_service.py `summary_score_map` 段）。句子窗口 ❌。
- kotaemon：`indices/splitters/__init__.py` 仅 TokenSplitter 与 SentenceWindowSplitter（包装 llama_index），父子块 ❌。

**ragflow 领域 chunk 模板专题**见第 6 节。

## 6. ragflow 领域 chunk 模板体系（特色机制）

这是 ragflow 区别于通用框架的核心资产：**切分不是一种算法，而是 12 份按文档体裁定制的"解析管线模板"**，本基线已演化为 JSON DSL + 注册表机制：

- **类型枚举**【核心】`~/develop/opensource/ragflow/internal/entity/dataset.go#ParserType*`：`presentation / laws / manual / paper / book / qa / table / general / naive / picture / one / audio / email / knowledge_graph`（naive 为 general 别名）。
- **模板即数据**【核心】`internal/ingestion/pipeline/builtin_registry.go`：12 份 JSON 模板 `template/ingestion_pipeline_{general,qa,manual,table,paper,book,laws,presentation,picture,one,audio,email}.json` 以 `go:embed` 打进二进制，`builtinParserOrder` 固定前端展示顺序，`aliases`（naive→general）保证旧数据可跑；每份模板是一段**可编辑的 ingestion pipeline DSL**（chunk 组件拼装），不再是旧版 Python 硬编码 parser 类。
- **检索视角的关键**：每种模板产出的 chunk 带不同字段，而这些字段直接进入重排权重——`content_ltks`（正文 token）、`title_tks`×2、`important_kwd`×5、`question_tks`×6（`reranker.go#RerankStandard`）。即 **"paper 模板抽出的章节标题、law 模板抽出的条款号、qa 模板的问句"在检索时获得数倍权重**，这是模板体系真正的检索价值（解析侧的 deepdoc 属维度 03）。
- ⚠️ `use_kg`（知识图增强检索）在 Go 重写版**尚未实现**：`internal/service/dataset/search.go:323-325` 直接 `common.Warn("use_kg is not yet implemented in Go - skipping KG retrieval")`——旧版 Python 的 GraphRAG 检索能力是当前基线的回归项。

## 7. 引用溯源：答案句子 → 来源 chunk

- **ragflow（最完整，双机制）**【核心】：
  1. 概率式：`internal/service/citation.go#InsertCitations`——把答案按标点分句（保留代码块），每句实时 embed，与各候选 chunk 向量做 cosine，**阈值下降搜索**（0.63 起、每轮 ×0.8 降到 0.3，取相似度 > max×0.99 的 chunk，每句至多 4 个），在句尾机械插入 `[ID:n]`（n 为 chunk 在引用列表中的序号）；兼容清洗 LLM 吐出的坏引用格式（`(ID:12)`、`【ID:12】`、`(**ID:5**)` 等，`badCitationPatterns`）。
  2. 确定性：`internal/agentic_rag/citations.go#ExtractCitedChunkIDs / InsertCitationMarkers`——agentic 管线的每条事实行本就带 `chunk_id: <id>` 溯源字段（工具输出打印的），正则提取后按首现顺序编号新增 `[ID:N]`，**无需任何相似度猜测**。
- **kotaemon**【核心】`libs/kotaemon/kotaemon/indices/qa/citation_qa_inline.py#AnswerWithInlineCitation`：prompt 强制 LLM 输出 `CITATION LIST`（每条引用含 `START_PHRASE/END_PHRASE`——**必须从 CONTEXT 原样复制的 ~6 词短语**）+ 答案内 `【number】` 标记；程序侧 `find_start_end_phrase`（`qa/utils.py`）把短语回定位到源文档 span 实现前端高亮。三种模式 off/inline/paraphrase（`libs/ktem/ktem/reasoning/simple.py`，paraphrase 走 `CreateCitationVizPipeline`）。这是「LLM 声明 + 程序校验定位」的代表性设计。
- **dify**：chunk 级引用——检索结果作为 `retrieval_resource`（segment 列表 + score）随消息返回，前端展示来源文档/段落；无句级归因机制 ❌（`dataset_retrieval.py` 全文无 sentence-level citation）。
- **llama_index**：`query_engine/citation_query_engine.py#CitationQueryEngine`——把检索节点再切成 512/20 的引用子块编号，prompt（CITATION_QA_TEMPLATE）令 LLM 按 `[N]` 引用；归因粒度受限于 LLM 自觉，无程序校验 ⚠️。
- **haystack**：❌ core 无 citation 组件（引用属应用层）。

## 8. 高级特性：缓存 / 评估钩子 / 多知识库路由

- **缓存**：真正的**语义查询缓存五家都无**❌（dify 仅 embedding 结果缓存 `embedding/cached_embedding.py`；llama_index core 有 ingestion cache 但无 query cache；haystack `components/caching/cache_checker.py` 是"docstore 元数据查重"用途，非语义缓存；ragflow 检索路径无 query 缓存）。语义缓存需外接（如 GPTCache 类方案）。
- **检索评估钩子**：haystack 最体系化——`components/evaluators/` 有 `document_mrr.py / document_ndcg.py / document_recall.py / context_relevance.py / faithfulness.py / sas_evaluator.py`（SAS 用 sentence-transformers 算语义相似），可作为 pipeline 组件直接对召回质量离线评测【核心】。llama_index 靠 `BaseRetriever` 的 callback/dispatcher 体系（instrumentation 包）。dify 走 Ops trace：`dataset_retrieval.py#_on_query` 落 `DatasetQuery` 审计行（独立事务）+ `_on_retrieval_end` 更新 segment `hit_count`（含 PG 死锁重试），配合开箱的命中统计面板。ragflow 记检索日志（zap 结构化字段：candidates/vectorSimilarityWeight 等）。
- **多知识库联合检索**：
  - dify 三种模式【核心】`api/core/rag/retrieval/dataset_retrieval.py`：`multiple_retrieve`（所有库并行检索→合并去重→统一 rerank，跨库要求同 embedding 模型否则强制 rerank 模型模式）；`single_retrieve` + `FunctionCallMultiDatasetRouter`（把每个知识库注册为 LLM function tool，LLM 选一个库）或 `ReactMultiDatasetRouter`（ReAct 循环选库）——**"检索即工具调用"的 agentic 路由**。
  - ragflow：多 dataset 一次请求联合（`SearchDatasets` 校验所有库同 embedding 模型后单次混合检索跨库执行）。
  - llama_index：`retrievers/router_retriever.py`（按 query 路由到子 retriever/索引）、`recursive_retriever.py`（引用链递归）。haystack：`MultiRetriever` 并发合流。kotaemon：UI 多选 collection → `selected_ids` 变 `scope`（doc_ids 过滤）下推到 docstore/vectorstore（`libs/ktem/ktem/index/file/index.py#get_pipeline`）。

## 9. 自建检索层推荐配方（基于五家对码的结论）

1. **召回**：BM25 + kNN 双路在引擎侧融合（ES weighted_sum 或 Qdrant/Milvus prefetch），召回窗口给足（ragflow 口径：knn_top_k 1024、rerank 候选 64）；**不要在召回期用用户阈值过滤向量分**（dify #35233 教训：embedding 分数与融合分不同尺度，过早过滤会误杀高质量 chunk——`retrieval_service.py` embedding_score_threshold=0.0 特判）。
2. **融合**：默认 **RRF（k=60/61）**，免调参且天然免疫两路分数尺度差异（llama_index/haystack 同款）；若产品需要"可解释的权重旋钮"给用户/管理员，用 ragflow/dify 式线性加权（`0.7·关键词 + 0.3·向量` 是 ragflow 验证过的默认锚点），但必须保证两路分数同尺度（重算 TF-IDF 或自研 token 相似度，而不是拿引擎 BM25 原始分硬混）。
3. **重排**：有 GPU/API 预算→Cohere/Jina/BGE-reranker API；**无外部服务→llama_index 的 sbert/flag-embedding（BGE）进程内方案，或自托管 TEI 端点（kotaemon/ragflow 同款路径）**。rerank 分数进融合公式前先归一化 [0,1]（ragflow NormalizeRerankScores 的 min-max/clamp 双分支值得直接抄）；给 cross-encoder 喂 chunk 原文而非分词文本。
4. **查询变换**：性价比排序——LLM 多查询扩展（fusion 内置，召回率提升最稳）> LLM 关键词增强（ragflow，中文场景尤其有效）> HyDE（生成质量依赖模型，慎用默认）。dify 式"完全不变换"是下限而非推荐。
5. **切分配合**：正文用递归 token 切分（256-512）打底；高价值场景加**父子块**（子块检索、父块送生成——ragflow mom_id / dify parent-child / llama_index AutoMerging 三家同思路）或**句子窗口**（精确问答场景）；ragflow 的"字段级权重"（标题/关键词条款/问句 ×2/×5/×6 进重排）是低成本高收益的独门技巧，自建时可在 chunk 元数据里预置 boosted 字段。
6. **引用溯源**：要做到句级归因，选 ragflow 双机制（embedding 句级归因兜底 + 让 LLM 带 chunk_id 输出的确定性路径）或 kotaemon 的 START/END_PHRASE 协议；纯 prompt 引用（llama_index）只适合 demo。
7. **别指望的**：语义查询缓存（五家都没有，需自建或外接）、haystack core 的 cross-encoder rerank（已移社区 hub）、ragflow Go 版的 KG 检索（未实现）。

## 10. 证据与存疑清单

**核心证据（均已亲读源码）**：
- ragflow：`internal/service/nlp/retrieval.go`（scoreSearchResult / buildRetrievalFusionExpr / esFusionWeights / minMatch / RetrievalByChildren）；`internal/service/nlp/reranker.go`（HybridSimilarity / RerankStandard / RerankByModel / NormalizeRerankScores / tokensToDict / TokenSimilarity）；`internal/service/nlp/term_weight.go`；`internal/service/similarity_weight.go#ResolveVectorSimilarityWeight`；`internal/service/dataset/search.go#SearchDatasets`；`internal/entity/skill_search.go:52`；`internal/entity/dataset.go#ParserType*`；`internal/ingestion/pipeline/builtin_registry.go` + `template/ingestion_pipeline_*.json`；`internal/service/citation.go#InsertCitations`；`internal/agentic_rag/citations.go`；`internal/entity/models/`（94 驱动、cohere/jina/voyage/nvidia/huggingface 等）
- dify：`api/core/rag/datasource/retrieval_service.py`（_retrieve / keyword_search / embedding_search / full_text_index_search / PARENT_CHILD_INDEX 映射）；`api/core/rag/rerank/weight_rerank.py`；`api/core/rag/rerank/rerank_model.py`；`api/core/rag/rerank/rerank_factory.py`；`api/core/rag/index_processor/processor/parent_child_index_processor.py`；`api/core/rag/retrieval/dataset_retrieval.py`（multiple_retrieve / _on_query / router）；`api/core/rag/retrieval/router/multi_dataset_function_call_router.py`
- llama_index：`llama-index-core/.../retrievers/fusion_retriever.py`（FUSION_MODES / _reciprocal_rerank_fusion / _relative_score_fusion / _simple_fusion）；`.../postprocessor/`（sbert_rerank / llm_rerank / rankGPT_rerank / metadata_replacement / optimizer）；`llama-index-integrations/postprocessor/`（25 包）；`.../indices/query/query_transform/base.py`；`.../question_gen/llm_generators.py`；`.../query_engine/citation_query_engine.py`；`.../node_parser/text/*` + `relational/hierarchical.py`；`.../retrievers/auto_merging_retriever.py`
- haystack：`haystack/components/joiners/document_joiner.py`（JoinMode 4 种 / _distribution_based_rank_fusion）；`haystack/utils/misc.py#_reciprocal_rank_fusion`（k=61）；`haystack/components/query/query_expander.py`；`haystack/components/rankers/`（目录仅 4 文件）；`haystack/components/retrievers/`（multi_query_* / multi_retriever / auto_merging / sentence_window）；`haystack/components/preprocessors/`（12 文件）；`haystack/components/evaluators/`（10 文件）；`haystack/components/caching/cache_checker.py`
- kotaemon：`libs/kotaemon/kotaemon/indices/vectorindex.py#VectorRetrieval.run`；`libs/kotaemon/kotaemon/rerankings/`（base/cohere/voyageai/tei_fast_rerank）；`libs/kotaemon/kotaemon/indices/rankings/`（llm/llm_scoring/llm_trulens/cohere）；`libs/ktem/ktem/index/file/pipelines.py#DocumentRetrievalPipeline`；`libs/kotaemon/kotaemon/indices/qa/citation_qa_inline.py`；`libs/ktem/ktem/reasoning/simple.py`；`libs/ktem/ktem/index/file/index.py`

**存疑/查不到（❌/⚠️）**：
1. ⚠️ **ragflow 基线已 Go 重写**：任务书所述 `rag/nlp/`、`api/` Python 路径在 deb1235be 不存在（`rag/` 仅剩 prompts），本文全部以 `internal/` Go 代码取证；Go 版多处注释声明"镜像旧 Python 行为"（如 search.py:331、insert_citations），但旧 Python 与 Go 的行为等价性未逐条验证（有 `python_parity_test.go` / `golden_parity_test.go` 等对拍测试佐证）。
2. ⚠️ ragflow `use_kg` 图增强检索：Go 版明确未实现（仅 Warn 跳过），需 KG 能力时应参考其旧 Python 版或 LightRAG（见维度 05）。
3. ⚠️ haystack cross-encoder rerank：core 仓库无 TransformersSimilarityRanker/SentenceTransformersDiversityRanker（类定义全仓零命中），应移至社区组件库 haystack-hub（未克隆该仓库验证，标存疑）；网上 haystack 2.x 教程多与现状不符。
4. ❌ dify：无 query rewrite/multi-query/HyDE（core 无原语）；无 RRF（融合仅加权与 cross-encoder 两模式）。
5. ❌ 五家均无语义查询缓存；llama_index core 无 query cache（仅 ingestion/embedding 缓存外围）；kotaemon/ragflow/llama_index 无检索质量评估组件（haystack/dify 有，形态不同）。
6. ⚠️ llama_index step-back prompting：core 无独立 QueryTransform（仅 docs/cookbook 示例级），不计入其查询变换能力清单。
7. ⚠️ kotaemon hybrid 去重逻辑 `if doc not in vs_ids`（Document 对象与 id 列表比较）疑似无效比较，实际去重可能依赖后续 reranker——未深究是否隐性 bug，仅记录。
