# 05 · 检索算法：混合检索、融合公式与重排的正确姿势

> 本文事实基于 2026-10 冻结的开源源码基线与当日可访问的官方文档，源码基线 commit 见文末参考节。

分块与索引决定"召回的池子里有什么"，而检索策略与重排决定"最终送给 LLM 的是什么"——这是回答质量的最后一道闸门。这一篇把五家开源实现（ragflow / dify / llama_index / haystack / kotaemon）的混合检索、融合公式、rerank 接入逐个拆开对码，拿微软和 Anthropic 的官方实测数字交叉背书，中间穿插一个"注释说谎"的真实考古案例，最后给一份可以直接抄的七条配方。

先交代背景：ragflow 在 2026 年已整体重写为 Go（Python 源码 2026-09-28 从主干删除），本文 ragflow 证据全部取自 Go 代码 `internal/`；涉及旧 Python 版时标注历史锚点 commit `2508c46c8`（纯 Python 最后完整态，2026-03-04）。

## 1. 为什么一定是"混合"：先把数字摆上桌

不谈直觉，先看两组官方数字。

**微软（Azure AI Search，BEIR 基准，NDCG@10）**【转述-微软原文】：

| 检索配置 | NDCG@10 |
|---|---|
| BM25 关键词 | 40.6 |
| 纯向量（ada-002） | 45.0 |
| 混合（关键词+向量，RRF 融合） | 48.4 |
| 混合 + Semantic Ranker（重排） | 50.0 |

出处是微软 2023-09 官方博客；techcommunity.microsoft.com 对调研环境不可达，数字经 Argon Systems 的官方转载核对（调研时一次、本文写作时又独立复核一次，两轮读取一致）。读法：混合比纯向量 +3.4 个点，再加重排 +1.6 个点——**混合是及格线，重排是拉开差距的那一步**。2024-11 同团队更新（新版 Semantic Ranker 与配置优化）把 NDCG@3 均值从 46.1 提到 55.9（nq 数据集 43.5→61.7）【转述-微软原文】，方向未变。Azure 把 RRF 常量 k=60 固定在引擎里、不开放调参，官方口径是"k 取 60 这样的小值时表现最好"。

**Anthropic（Contextual Retrieval，2024-09，top-20 chunk 检索失败率）**：

| 配置 | 失败率 | 相对降幅 |
|---|---|---|
| 纯 embedding 基线 | 5.7% | — |
| + 上下文化嵌入（每 chunk 前置 LLM 生成的 50–100 token 定位上下文） | 3.7% | -35% |
| + 上下文化 BM25（同一份上下文前缀进 BM25 索引，两路融合） | 2.9% | -49% |
| + Cohere Rerank（top-150 重排取 top-20） | 1.9% | -67% |

成本侧：上下文化是一次性预处理 **$1.02/百万文档 token**，可行性的关键是 prompt caching——整篇文档进缓存后逐 chunk 复用（官方称缓存对长上下文降延迟 2 倍以上、降成本至多 90%）。没有这套缓存经济学的自建系统照抄会贵一个量级，评估时必须把缓存命中率算进总账。

两条数字链加上五家开源对码，结论收敛成一句话：**单路向量检索是下限；BM25 补词面（错误码、型号、专有名词这类 embedding 的弱项），向量补语义；rerank 负责最后的精排**。产品侧佐证还有 OpenAI：其托管 File Search 把混合检索做成一等公民参数（`hybrid_search` 带 `rrf_embedding_weight` / `rrf_text_weight` 双权重可调，另配 ranker 与 score_threshold），cookbook 原文确认其 ranker 用的就是 hybrid search——托管黑盒敢把默认值压在这套配方上，与开源、与 Azure/Anthropic 三方互证。注意数字的适用边界：BEIR 是英文公开基准，Anthropic 是其内部场景实测，中文企业语料上绝对值会变，但相对收益结构是稳的（此句为生态通识判断，未源码级验证）。

## 2. 融合公式两流派：分数级加权 vs 排名级 RRF

五家的融合落到源码只有两大流派：ragflow / dify 是**分数级线性加权**（要求两路分数同尺度），llama_index / haystack 是**排名级 RRF 及其变体**（只看名次不看分数）。kotaemon 是反例——有混合、无融合公式，后面单独说。

### 2.1 流派一：分数级线性加权

**ragflow** 的混合检索是"引擎粗召回 + 应用层精算"两段式（`infiniflow/ragflow@deb1235be internal/service/nlp/retrieval.go#scoreSearchResult`）。融合段（无 rerank 模型时）的公式在 `internal/service/nlp/reranker.go#HybridSimilarity`：

```
sim = tkWeight · tsim + vtWeight · vsim
```

- `vtWeight` 即配置项 vector_similarity_weight，**默认 0.3——关键词路占 0.7**（`internal/entity/skill_search.go:52` 的 `default:0.3`；权重和必须为 1 的校验在 `internal/service/similarity_weight.go#ResolveVectorSimilarityWeight`）。五家里只有 ragflow 给关键词路这么高的默认权重——它的自研 token 相似度与 term weighting 整套基建都在为关键词路服务，这个默认值不是随手拍的。
- 这个公式要成立，有个容易被忽略的前提：**tsim 和 vsim 必须同尺度**。ragflow 不拿 BM25 原始分凑数，而是自研加权 token 相似度 tsim：query 分词后构造权重字典，unigram 权重 ×0.4、相邻 bigram 取两 token 权重较大者 ×0.6（`reranker.go#tokensToDict`，token 权重来自 NLP 词频统计的 term weighting 移植）；文档侧 token 再叠加**字段级 boost：content×1 + title×2 + important_kwd×5 + question_tks×6**（`reranker.go#RerankStandard`）。字段 boost 是 ragflow 领域 chunk 模板（paper/laws/qa 等 12 种）真正的检索价值兑现处——qa 模板抽出的问句在重排时拿 6 倍权重。另有 tag 命中与 PageRank 直接加进最终分（`reranker.go` 的 applyRankFeatureScores，注释 `tag_score*10 + pagerank`）。

**dify** 走同流派但换了把尺子。混合检索时三路并发（jieba 关键词 / ES 全文 / 向量），去重后交给后处理器二选一（`langgenius/dify@79effdd498 api/core/rag/rerank/rerank_factory.py#RerankRunnerFactory`，仅两个 case，互斥）：

- **weighted_score**（`api/core/rag/rerank/weight_rerank.py#run`）：`score = vw·cosine(query_emb, doc_emb) + kw·cosine(TF-IDF(query), TF-IDF(doc))`。关键词侧不是索引期 BM25 分，而是**在本次候选集上重算的局部 TF-IDF**（IDF = ln((1+N)/(1+n))+1，N 为候选文档数），目的同样是让两路分数可比；向量侧优先复用召回时的 score，缺失才实时补 embed。
- **reranking_model**：cross-encoder 对 (query, chunk) 直接打分重排（`api/core/rag/rerank/rerank_model.py#RerankModelRunner`，经 ModelManager 可接任意 rerank 提供商，查询+图片的多模态 rerank 有显式分支）。另一个容易误判的细节：dify 在**单路**语义检索下，只要配了 rerank 模型也会触发重排——rerank 不是混合检索的附属品，而是独立的精排层。
- 全 `core/rag` 目录 grep `rrf|reciprocal` 零命中——dify 没有 RRF。

### 2.2 流派二：排名级 RRF

RRF 公式 `1/(k + rank)` 只用名次不用分数，天然免疫两路分数尺度差异，也免调权重——代价是丢掉了分数携带的置信信息。

**llama_index**（`run-llama/llama_index@7169bcd0d llama-index-core/llama_index/core/retrievers/fusion_retriever.py`，`#FUSION_MODES`）给了四种模式任选：

| 模式 | 公式 | 实现符号 |
|---|---|---|
| RECIPROCAL_RANK | `Σ 1/(rank+60)`，跨查询/检索器累加 | `#_reciprocal_rerank_fusion`（k=60，注释直接引 Cormack et al. SIGIR 2009 原论文） |
| RELATIVE_SCORE | 每个结果集内 min-max 归一到 [0,1] → ×检索器权重 → ÷查询数 → 同节点求和 | `#_relative_score_fusion` |
| DIST_BASED_SCORE | 同上，但 min/max 取 μ±3σ（抗离群） | `#_relative_score_fusion(dist_based=True)` |
| SIMPLE | 同节点取各路最大分 | `#_simple_fusion` |

检索器权重可选传入，不传则均分并强制归一。另外 `QueryFusionRetriever` 同时是混合检索与多查询扩展的合体（内置 LLM 生成 num_queries-1 条变体，见第 5 节）。

**haystack** 把融合做成独立组件（`deepset-ai/haystack@05cab58ac haystack/components/joiners/document_joiner.py#DocumentJoiner`）：`concatenate`（去重取最高分）/ `merge`（同 ID 分数加权求和，weights 对应各输入路）/ `reciprocal_rank_fusion` / `distribution_based_rank_fusion`（每路按 μ±3σ 重缩放到 [0,1] 再拼接）。RRF 实现在 `haystack/utils/misc.py#_reciprocal_rank_fusion`：**k=61**——论文的 60 加上 Python 列表 0 基序号的 1，注释写明；且**支持每路权重**（resolved_weights），比 llama_index 的 RRF 多了路权重维度。新组件 MultiRetriever（experimental）把"多检索器并发 + 去重 + RRF"封装成单组件。

**k 的行业默认**：Azure 固定 60、llama_index 60、haystack 61——跨实现一致。这个量级的 k 平滑头部名次差异，对几十上百的候选集足够稳。反过来，qdrant 内置 RRF 的默认 k=2 是完全不同的调参语义（第 4 篇提过）——抄公式时把常量一起抄对。DBF（μ±3σ 归一）则是两流派的折中：保留分数信息但按分布归一、抗离群。

### 2.3 反例：有混合、无融合（kotaemon）

kotaemon 默认 hybrid 模式（`Cinnamon/kotaemon@9ad3e4e4 libs/kotaemon/kotaemon/indices/vectorindex.py#VectorRetrieval.run`）：双线程并发查向量库与 docstore 全文（BM25），**结果直接拼接**——全文命中 score=-1 排在前、向量命中带真实分在后，无任何融合公式，排序完全交给后置 reranker 链；另有 `first_round_top_k_mult=10` 的过采样机制（第一轮取 10 倍候选，由 rerank 收敛）。这是"把融合问题推给 rerank 模型"的极简路线，代价是 rerank 变成单点依赖。一个存疑记录：其去重判断 `if doc not in vs_ids` 是 Document 对象与 id 列表的比较，疑似无效比较——调研中记为疑似 bug，未深究，此处如实标注。

### 2.4 怎么选

- 默认 **RRF**：免调参、抗尺度差异，llama_index / haystack / Azure 同款。
- 产品需要"可解释的权重旋钮"（给管理员调、给客户解释）→ 线性加权，但必须自己解决两路同尺度（重算 TF-IDF 或自研 token 相似度）。**不能拿引擎 BM25 原始分和 cosine 硬混**：BM25 无上界、cosine 在 [0,1]，直接加权后向量路会被系统性稀释（分数尺度问题属生态通识，未源码级验证）。
- ragflow 的 0.7/0.3（关键词 0.7）是唯一一家"关键词路占大头"的验证过的默认锚点，中文场景值得从这组值起步做网格。

## 3. 一个真实教训：esFusionWeights 考古，或"读注释不如读代码"

ragflow Go 版 `internal/service/nlp/retrieval.go` 里有一个引擎级融合权重常量（:645 附近）：

```go
// esFusionWeights is the pair the reference gives every non-Infinity backend
// (rag/nlp/search.py:331). 0.001 rather than 0 keeps a lexical leg for engines
// that reject a zero weight.
const esFusionWeights = "0.001,1"
```

注释自称镜像旧 Python 的 `rag/nlp/search.py:331`。调研轮对此做了锚点考古（git worktree 挂纯 Python 最后完整态 `2508c46c8` 逐行比对 + 主仓 git log 追历史），结论是**注释失实**：

1. Python 时代引擎侧权重从来是 `"0.05,0.95"`（文本 0.05 / 向量 0.95，`infiniflow/ragflow@2508c46c8 rag/nlp/search.py:127`；自 2025-07-29 提交 `342a04ec8` 起就在）。`git log -S'"0.001,1"'` 在 search.py 全历史零命中——Python 从未有过这个值。
2. `search.py:331` 这一行在锚点版确实存在，但内容是 `hybrid_similarity` 的**应用层**融合调用（:327-331），与引擎侧 FusionExpr 权重无关——注释引用的行号与它写死的常量对不上任何 Python 版本，它实际指向的是 2026-09 的过渡期 Python（Go 与 Python 并存、被同步改写的窗口期）。
3. `"0.001,1"` 是 Go 自定值：0.001 而非 0，是给拒绝零权重的引擎保留一条词面路。

这个案例值得写进博客，因为它恰好踩在 ragflow 检索设计里最值得抄的一个结构上：**召回段与融合段分离**。对非 Infinity 引擎，引擎级 fusion 只负责粗召回定序（`0.001,1` 的实际含义：召回窗口基本按向量排），用户配置的 0.7/0.3 权重延迟到应用层才生效；只有 Infinity 引擎把用户权重直接传给引擎的 `weighted_sum`（`retrieval.go#buildInfinityFusionExpr`——而 Python 版在该路径是固定 0.05/0.95 且跳过 rerank、忽略用户权重，Go 属行为修正型偏离）。"引擎怎么粗排"与"业务怎么加权"解耦，这个分层本身是好设计；坏的是注释把自定值标成了"Matches 旧版"。

工程教训两条：

1. **迁移/重写项目里，"Matches X" 的注释要当代码读、不要当合同信**——它是作者意图的证据，不是行为等价的证明。ragflow 同类偏离还有两处：min_match（Python 固定 0.3、空结果重试 0.1；Go 改为向量权重 ≥0.8 时取 0 的条件式，`retrieval.go#minMatch`）与 rerank 输入文本（Python 喂分词后 token 串、Go 喂原文，见下节）。判定"镜像与否"的唯一办法是锚点对拍——ragflow 自己只给 chunker 建了 golden 对拍（`internal/ingestion/component/chunker/golden_parity_test.go`），检索段没有。
2. **读开源检索代码，先分清一段代码在管"召回段定序"还是"融合段最终分"**——两段的权重语义完全不同。本例中引擎侧权重 0.001,1 与用户侧 0.7/0.3 并不矛盾，混在一个层面读就会得出"ragflow 权重自相矛盾"的错误结论。

## 4. 重排专题：分数怎么进公式、怎么归一、喂什么文本

### 4.1 rerank 分数替代向量分进融合公式

ragflow 配置 rerank 模型时，不做向量召回分融合，而是（`internal/service/nlp/reranker.go#RerankByModel`）：

```
sim = tkWeight · tsim + vtWeight · rerank_sim
```

cross-encoder 分数被当作"向量相似度成分"顶进同一条加权公式。好处是公式稳定：接不接 rerank 模型，上层结构不变，权重旋钮语义连续。dify 则是另一极端——rerank 模型模式直接以 cross-encoder 分数为最终序（与加权模式互斥）。

### 4.2 分数归一：min-max / clamp 双分支

rerank 提供商的分数口径不齐：Cohere / Jina / Voyage 返回已校准的 [0,1]，NVIDIA 返回原始 logit（常为负值）。ragflow 的 `#NormalizeRerankScores` 做集中归一，三分支值得直接抄：先检测整批分数是否落在 [0,1]——在界内则**保留绝对值**（不把已校准分数再压一遍）；出界且批内有区分度则 **min-max 重缩放**；无区分度（全同分）则逐元素 **clamp**。注释明确声明镜像旧 Python `rag/llm/rerank_model.py#_normalize_rank` 的契约（这一条契约经锚点对拍成立，Python 是分散在个别 provider 内做、Go 集中化）。

### 4.3 喂原文，不喂分词文本

给 cross-encoder 的文档侧是 `content_with_weight` **原文**而非 `content_ltks` 分词串——分词/stem 后的文本会压垮神经 reranker 的相关性打分（Go 代码注释写明的教训）。对照锚点：Python 旧版正是把分词后的 token 串喂给 reranker（`rag/nlp/search.py` rerank_by_model 路径），Go 改掉了，属于有意改进而非"镜像"。自建同理：**rerank 的输入口径 = 原文**，索引期为 BM25 做的分词、去词干、字段拼接都不要带过来。

### 4.4 候选窗口口径

ragflow 的默认参数把三个口径分开（`internal/service/dataset/search.go#SearchDatasets`）：similarity_threshold=0.2（最终分阈值）、knn_top_k=1024（召回窗口，上限 2048）、rerank_candidates_count=64（参与重排的候选数）。锚点对照补一个细节：Python 版的 RERANK_LIMIT 是 `max(30, ceil(64/page_size)*page_size)`——给重排候选数加了 30 的下限，避免小分页时候选集过薄。Anthropic 口径同构：top-150 重排取 top-20。另两个工程细节：ragflow 配置 rerank 模型时只支持 page=1（分页要求全量重排，代价失控，`retrieval.go` 显式报错）；kotaemon 的 10 倍过采样同理。自建时把"召回 top_k / rerank 候选数 / 返回数"分成三个参数，别共用。

### 4.5 本地 rerank 生态（没有外部 API 时怎么办）

- **llama_index 最全**：core 自带 4 个后处理器（sbert 进程内 CrossEncoder，默认模型 `cross-encoder/stsb-distilroberta-base`；LLM 打分；RankGPT 滑窗；结构化 LLM），另有 `llama-index-integrations/postprocessor/` 25+ 集成包，本地系覆盖 flag-embedding（BGE）、flashrank、openvino、colbert、colpali、TEI、rankllm。
- **ragflow**：`internal/entity/models/huggingface.go` 进程内推理 + vllm / xinference / ollama 等 OpenAI 兼容自托管端点；rerank 驱动面极宽——`internal/entity/models/` 下 94 个 provider 驱动文件（目录共 183 个文件，其余为测试）。
- **kotaemon**：TEI 独立 HTTP 服务（`/rerank` 端点，TeiFastReranking）+ Cohere / Voyage API（Cohere 默认模型 `rerank-v4.0-fast`）；LLM 评分型 reranker 前先截断 top_k 控制成本。
- **dify**：无进程内推理，本地部署走 xinference 等本地推理服务商。
- **haystack** ⚠️：core 的 rankers 只剩 LLMRanker / LostInTheMiddle / MetaField 系——TransformersSimilarityRanker 等已移出 core 进社区 hub（本基线全仓无类定义；社区 hub 未克隆验证，如实标注）。网上大量 haystack 2.x 教程与现状不符，选型时注意。
- 厂商背书：Anthropic 官方实测直接用第三方 Cohere Rerank——"重排器自建不如用专用模型"是开源与厂商的共识。

## 5. 查询变换的性价比序

按投入产出排序：**多查询扩展 > LLM 关键词增强 > HyDE（慎用）**。

1. **多查询扩展**：llama_index 的 QueryFusionRetriever 内置（LLM 一次生成 n-1 条查询变体，并发检索再融合，`fusion_retriever.py#_get_queries`）；haystack 有 QueryExpander（JSON 输出 n 条同义查询）配 multi_query 系 retriever。召回率提升最稳，代价是每次检索多一次轻量 LLM 调用。
2. **LLM 关键词增强**：ragflow `keyword=true` 时 LLM 抽 3 个关键词 append 到 query（`internal/service/generator.go#KeywordExtraction` + `#AppendKeywords`）。**中文场景尤其有效**——分词歧义与专有名词（产品名、错误码、内部缩写）是中文检索的主要漏召回源，LLM 补词比分词器规则稳。另有跨语言翻译开关（`#CrossLanguages`）。
3. **HyDE**：LLM 先生成假设性答案文档、拿它 embed 去检索（`llama-index-core/llama_index/core/indices/query/query_transform/base.py#HyDEQueryTransform`；OpenAI cookbook 也有教程）。效果强依赖生成模型质量，假设文档跑偏会带偏检索——默认别开，有评测护航再开。

下限参照：dify 与 kotaemon 完全没有查询变换原语——dify 连 LLM 改写查询的内置用法都没有，LLM 仅用于生成 metadata 过滤条件（`api/core/rag/retrieval/dataset_retrieval.py` 的自动元数据过滤分支）；工作流里可手工接 LLM 节点改写 query，但那是编排层的自救而非检索原语。厂商侧则是真实的设计分歧：OpenAI 把 `rewrite_query: true` 做进检索工具参数（查询侧），Anthropic 的 Contextual Retrieval 全部功夫花在索引侧、查询侧不处理——两条路线互补而非对立，但两者都与"完全不变换"拉开差距。

## 6. 召回期阈值过滤的坑：dify #35233

分数尺度的坑不只存在于融合，也存在于过滤。dify 有一个真实修复（代码注释直接引 issue #35233）：混合检索曾在**向量召回期**就应用用户的 score_threshold——但 embedding 相似度与融合后 / 重排后的分数不是同一尺度，过早过滤会把高质量 chunk 误杀在召回期。修复后的行为（`api/core/rag/datasource/retrieval_service.py`）：hybrid 路径在向量召回时把阈值特判为 0.0（`embedding_score_threshold`），过滤统一推迟到融合 / 重排之后。

规矩一句话：**阈值只对"最终口径的分数"生效；召回期只管把窗口给足**。

## 7. 推荐配方（七条）

1. **召回**：BM25 + kNN 双路在引擎侧融合（ES weighted_sum 或 Milvus/Qdrant 的 prefetch），召回窗口给足（ragflow 口径：knn_top_k 1024、rerank 候选 64）；不要在召回期用用户阈值过滤向量分（dify #35233 教训）。
2. **融合**：默认 RRF（k=60/61），免调参且免疫两路分数尺度差异；若产品需要可解释的权重旋钮，用线性加权（`0.7·关键词 + 0.3·向量` 是 ragflow 验证过的中文锚点），但必须保证两路分数同尺度——重算 TF-IDF 或自研 token 相似度，不能拿引擎 BM25 原始分硬混。
3. **重排**：有 GPU/API 预算 → Cohere / Jina / BGE-reranker API；无外部服务 → llama_index 的 sbert / flag-embedding 进程内方案，或自托管 TEI 端点（kotaemon / ragflow 同款路径）。rerank 分数进公式前先归一化 [0,1]（ragflow 的 min-max/clamp 双分支直接抄）；给 cross-encoder 喂 chunk 原文而非分词文本。
4. **查询变换**：多查询扩展 > LLM 关键词增强（中文尤其有效）> HyDE（模型依赖重，慎用默认）。"完全不变换"是下限而非推荐。
5. **切分配合**：正文递归 token 切分（256–512）打底；高价值场景加父子块（子块检索、父块送生成：ragflow mom_id / dify parent-child / llama_index AutoMerging 三家同思路）或句子窗口；ragflow 的字段级权重（标题 / 关键词条款 / 问句 ×2/×5/×6 进重排）是低成本高收益技巧，自建可在 chunk 元数据里预置 boosted 字段（切分细节见第 3 篇）。
6. **索引侧补语境**：预算允许时上 Contextual Retrieval（上下文化 + 混合 + 重排合计 -67%，$1.02/百万文档 token），前提是有 prompt caching 类经济学，对缓存命中率算总账。
7. **别指望的**：语义查询缓存（五家都没有，需外接 GPTCache 类方案）、haystack core 的 cross-encoder rerank（已移社区 hub）、ragflow Go 版检索 API 的 KG 增强（未实现——聊天路径已移植、dataset/chunk 检索路径 Warn 跳过，属回归项）。

## 参考与出处

开源源码（基线 commit 均为 2026-10 冻结）：

- ragflow 检索融合与重排：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/nlp/retrieval.go （`#scoreSearchResult` / `#buildRetrievalFusionExpr` / `#esFusionWeights` / `#minMatch` / `#RetrievalByChildren`）
- ragflow 相似度计算：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/nlp/reranker.go （`#HybridSimilarity` / `#RerankStandard` / `#RerankByModel` / `#NormalizeRerankScores` / `#tokensToDict`）
- ragflow 默认参数与权重：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/entity/skill_search.go （:52 `default:0.3`）、https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/dataset/search.go （`#SearchDatasets`）、https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/similarity_weight.go （`#ResolveVectorSimilarityWeight`）
- ragflow 查询增强：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/generator.go （`#KeywordExtraction` / `#AppendKeywords` / `#CrossLanguages`）
- ragflow 本地 rerank 与 chunker 对拍：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/entity/models/huggingface.go 、https://github.com/infiniflow/ragflow/blob/deb1235be/internal/ingestion/component/chunker/golden_parity_test.go
- ragflow 历史锚点（纯 Python 最后完整态 2508c46c8）：https://github.com/infiniflow/ragflow/blob/2508c46c8/rag/nlp/search.py （:127 FusionExpr `"0.05,0.95"`、:331 hybrid_similarity 调用）、https://github.com/infiniflow/ragflow/blob/2508c46c8/rag/nlp/query.py （:174-198 token 相似度 0.4/0.6）
- dify 检索与后处理：https://github.com/langgenius/dify/blob/79effdd498/api/core/rag/datasource/retrieval_service.py （`#_retrieve`、embedding_score_threshold 特判与 #35233 注释）、https://github.com/langgenius/dify/blob/79effdd498/api/core/rag/rerank/weight_rerank.py （`#run` / `#_calculate_cosine`）、https://github.com/langgenius/dify/blob/79effdd498/api/core/rag/rerank/rerank_factory.py （`#RerankRunnerFactory`）
- dify 阈值误杀 issue：https://github.com/langgenius/dify/issues/35233
- llama_index 融合与查询变换：https://github.com/run-llama/llama_index/blob/7169bcd0d/llama-index-core/llama_index/core/retrievers/fusion_retriever.py （`#FUSION_MODES` / `#_reciprocal_rerank_fusion` / `#_relative_score_fusion`）、https://github.com/run-llama/llama_index/blob/7169bcd0d/llama-index-core/llama_index/core/indices/query/query_transform/base.py （`#HyDEQueryTransform`）
- llama_index 重排生态：https://github.com/run-llama/llama_index/tree/7169bcd0d/llama-index-integrations/postprocessor 、https://github.com/run-llama/llama_index/blob/7169bcd0d/llama-index-core/llama_index/core/postprocessor/sbert_rerank.py
- haystack 融合组件：https://github.com/deepset-ai/haystack/blob/05cab58ac/haystack/components/joiners/document_joiner.py （`#DocumentJoiner` 四模式）、https://github.com/deepset-ai/haystack/blob/05cab58ac/haystack/utils/misc.py （`#_reciprocal_rank_fusion` k=61）
- kotaemon 检索与重排链：https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/kotaemon/kotaemon/indices/vectorindex.py （`#VectorRetrieval.run`）、https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/ktem/ktem/index/file/pipelines.py （`#DocumentRetrievalPipeline`）

官方文档与厂商原文：

- 微软 BEIR 数字（techcommunity 原文对调研环境不可达，经 Argon Systems 官方转载核对，两轮独立读取一致）【转述-微软原文】：https://argonsys.com/microsoft-cloud/library/azure-cognitive-search-outperforming-vector-search-with-hybrid-retrieval-and-ranking-capabilities
- Azure RRF k=60 与 hybrid 排序：https://learn.microsoft.com/azure/search/hybrid-search-ranking
- Azure Semantic Ranker（top-50 重排、2048 token 输入）：https://learn.microsoft.com/azure/search/semantic-search-overview
- Anthropic Contextual Retrieval（-35%/-49%/-67% 数字链、$1.02/M token）：https://www.anthropic.com/news/contextual-retrieval
- Anthropic prompt caching：https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- OpenAI File Search（rewrite_query、RRF 双权重、ranker）：https://developers.openai.com/api/docs/guides/tools-file-search
- OpenAI cookbook HyDE 教程：https://github.com/openai/openai-cookbook/blob/9aad95f/examples/vector_databases/chroma/hyde-with-chroma-and-openai.ipynb
- OpenAI cookbook cross-encoder 重排教程：https://github.com/openai/openai-cookbook/blob/9aad95f/examples/Search_reranking_with_cross-encoders.ipynb

## 系列目录

《给 Agent 造知识库：企业级 RAG 搭建手记》全 10 篇：

1. 企业级 RAG 全景：一篇文档到一段回答之间发生了什么
2. RAG 的第一道生死线：中文文档解析怎么做
3. 分块与索引：结构感知切分、双路索引与 schema 设计
4. 检索引擎选型对比：ES、milvus、pgvector、qdrant 与嵌入式方案
5. 检索算法：混合检索、融合公式与重排的正确姿势（本篇）
6. 让答案可信：引用溯源的三种实现机制
7. 开源 RAG 平台都不敢做的事：文档级权限与检索期过滤
8. 上线前后的质量防线：RAG 评测体系从零搭建
9. GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计
10. 实战设计：Python 自建轻量知识库服务，给 deepagents 供数

下一篇我们聊"答案可信"：检索把最相关的 chunk 送给了 LLM，但用户凭什么相信答案里的每个数字？句级归因、确定性标记、LLM 声明 + 程序校验——引用溯源的三种实现机制，ragflow 和 kotaemon 各自给出了教科书级的两种。
