# 维度 09：Java 生态 RAG 能力对照（spring-ai / langchain4j / spring-ai-alibaba）

> **问题**：用 Java 技术栈自建 RAG，生态成熟度到哪了、缺什么、Python 侧要不要保留。
> **基线**：spring-ai `b5eb0272f`（主干 2.0.2-SNAPSHOT）、langchain4j `0028928ea`（主干 1.21.0-beta31-SNAPSHOT）、spring-ai-alibaba `f82da0b50`（v1.1.2.2，2026-03-10 发布线）。三者均 Apache-2.0。
> **方法**：targeted grep + 接口/实现类清单核对；Python 侧结论引用本轮其他维度（llama_index / haystack 轮档案），不重新深挖。

## 一、总表

| 能力 | spring-ai | langchain4j | spring-ai-alibaba（现主干） |
|---|---|---|---|
| ETL 抽象 | 3 个函数式接口（Reader=Supplier / Transformer=Function / Writer=Consumer），**无 Pipeline 编排类** | 同级接口 + **EmbeddingStoreIngestor 一站式 ETL** 封装 | 复用 spring-ai，另在 Graph 中节点化（DocumentExtractorNode） |
| 文档解析器 | 4 个 reader：PDF(PDFBox 3.0.7)/Tika(3.3.1)/Markdown(commonmark)/HTML(jsoup) | 6 个 parser：PDFBox/POI/Tika/**docling**/Markdown/YAML + 7 个 loader（S3/GCS/GitHub/Playwright/Selenium 等，负责"取"） | 主仓无自有解析器（DashScope 多模态解析在 extensions 仓） |
| 切分 | TextSplitter / TokenTextSplitter（1 个） | **9 种**：recursive/段落/句子/行/词/字符/正则/**层级父子切分**（small-to-big） | 复用 spring-ai |
| 向量库适配 | **21 个**（vector-stores/ 目录：pgvector/milvus/qdrant/chroma/weaviate/es/opensearch/mongo-atlas/neo4j/oracle/cassandra/couchbase/coherence/gemfire/mariadb/pinecone/redis/azure/bedrock-kb/s3-vector/typesense）+ 内存 SimpleVectorStore | 主仓 **24 个模块**含实现（多 milvus-v2/vespa/tablestore/infinispan/hibernate 等）+ InMemoryEmbeddingStore；另有未克隆的 community 仓增量 ⚠️ | 无自有适配，直接用 spring-ai 的 |
| metadata filter | ✅ Filter.Expression + ANTLR 文本解析，**42 个文件**实现各库方言转换 | ✅ core 内 Filter/MetadataFilterBuilder（比较/逻辑），各 store 有 mapper；另有 **LLM 生成 SQL→Filter** 的 filter-parser-sql | 复用 spring-ai |
| 检索增强 API | QuestionAnswerAdvisor + RetrievalAugmentationAdvisor（Transformer×Expander×Retriever×Joiner×PostProcessor×Augmenter） | RetrievalAugmentor 管线（Transformer/Router/Retriever/Aggregator/Injector 各成体系） | Graph 节点化封装（KnowledgeRetrievalNode） |
| rerank | ❌ **无通用抽象**（仅 Bedrock KnowledgeBase 托管服务可配 rerank 模型 ARN） | ✅ **ScoringModel 接口 + 6 实现**（Cohere/Jina/Voyage/VertexAI/Watsonx/ONNX 本地 BERT cross-encoder），ReRankingContentAggregator 可直接嵌进管线 | ✅（外挂）RerankModel 接口 + DashScope rerank，实现在 extensions 仓 |
| 混合检索/BM25 | ❌ ES store 仅 kNN，无 hybrid/BM25/RRF 代码 | ⚠️ 部分：**Milvus-v2 稠密+稀疏 BM25 hybrid**、**ES hybrid（服务端 RRF+reranker，需付费 license）**、core 有 ReciprocalRankFuser 原语；无「任意库+本地 BM25」通用件 | ❌ 无 |
| Agentic | ChatClient + Advisor 链 + ToolCalling/ToolCallAdvisor + MCP 模块 + ToolSearchAdvisor | AiServices（声明式，RAG/tools/memory 同挂）+ 新 langchain4j-agentic（Planner/supervisor） | ✅ 重点：Agent Framework（React/Sequential/Parallel/Routing/Loop）+ Graph 运行时 + A2A |
| 工程化 | ✅ Micrometer（chat/advisor/vectorstore 全观测）、testcontainers 连接工厂 + 每 store IT | ✅ observation + micrometer-metrics 模块、每 store testcontainers IT | ✅ graph-observation starter + Admin 平台 |
| 版本节奏 | 1.0 GA（2025-05）→ 1.1 → **主干 2.0.2-SNAPSHOT** | 1.0 GA（2025 中）→ **主干 1.21.0-beta31-SNAPSHOT**（stable/dev API 分层） | 1.1.2.2（2026-03），基于 Spring AI 1.1.0 |

## 二、检索增强管线解剖（两套体系对比）

这是 Java 侧成熟度的分水岭，两家都做了"管线化"抽象，但完整度取向不同。

### spring-ai：Advisor 挂载 + RAG 子管线

两入口【核心】：

1. `~/develop/opensource/spring-ai/advisors/spring-ai-vector-store-advisor/src/main/java/org/springframework/ai/chat/client/advisor/vectorstore/QuestionAnswerAdvisor.java#class` —— 实现 `BaseAdvisor` 的开箱即用 RAG 顾问：持有 `SearchRequest` + `PromptTemplate`，advise 时调 `vectorStore.similaritySearch()`，把结果塞进 user prompt；`doGetFilterExpression()` 支持从**用户上下文动态注入 filter 表达式字符串**（`FilterExpressionTextParser` 解析）——权限过滤的一个实用钩子。
2. `~/develop/opensource/spring-ai/spring-ai-rag/src/main/java/org/springframework/ai/rag/advisor/RetrievalAugmentationAdvisor.java#class` —— 完整可组装管线，六个插槽：
   - `List<QueryTransformer>`（pre）：实现有 `CompressionQueryTransformer`（压缩对话历史）、`TranslationQueryTransformer`（翻译）、`RewriteQueryTransformer`（改写）；
   - `QueryExpander`：`MultiQueryExpander`（多查询扩展）；
   - `DocumentRetriever`：`VectorStoreDocumentRetriever`（唯一内置实现）；
   - `DocumentJoiner`：`ConcatenationDocumentJoiner`（唯一内置，多路仅拼接）；
   - `List<DocumentPostProcessor>`（post）；
   - `QueryAugmenter`：`ContextualQueryAugmenter`（拼 prompt，支持 allowEmpty 标记）。
   路径前缀 `spring-ai-rag/src/main/java/org/springframework/ai/rag/`（preretrieval/postretrieval/retrieval/generation 四包）。支持 `TaskExecutor`/`Scheduler` 做检索并发。
   注意其结构是**单 Retriever + Joiner**（transformer 顺序作用于同一查询流），没有"路由到不同 retriever"的 QueryRouter 概念；Advisor 本身挂在 ChatClient 调用链上（`spring-ai-client-chat/.../advisor/api/Advisor.java`、`CallAdvisor`/`StreamAdvisor` 分流式/非流式）。

**评价**：骨架正确、默认件偏薄——Joiner 只会拼接、无重排、无融合、无路由；真正的增强点（rerank/RRF）需要自己写组件插进 PostProcessor/Joiner 槽位。

### langchain4j：五段式 Augmentor，rerank/RRF 是一等公民

`~/develop/opensource/langchain4j/langchain4j-core/src/main/java/dev/langchain4j/rag/`【核心】：

- 入口 `RetrievalAugmentor` / `AugmentationRequest` / `AugmentationResult`；默认实现 `DefaultRetrievalAugmentor`（流程：Query → ①QueryRouter 路由到 N 个 ContentRetriever → ②并行检索（默认 executor，Java 21+ 虚拟线程）→ ③ContentAggregator 融合/重排 → ④ContentInjector 注入 prompt）。
- `query/transformer/`：`DefaultQueryTransformer`、`CompressingQueryTransformer`、`ExpandingQueryTransformer`（多查询）；
- `query/router/`：`DefaultQueryRouter`、**`LanguageModelQueryRouter`**（LLM 决定查询发给哪些 retriever——多知识库路由，spring-ai 无对应物）；
- `content/retriever/`：`EmbeddingStoreContentRetriever`（带 maxResults/minScore/filter，且**内嵌 EmbeddingModel 自动改写查询**）、`WebSearchContentRetriever`（挂 web 搜索引擎）、`ListeningContentRetriever`（失败/成功监听，接观测）；
- `content/aggregator/`：`DefaultContentAggregator`、**`ReRankingContentAggregator`**（用 ScoringModel 对多路内容统一重排）、**`ReciprocalRankFuser`**（RRF 融合）；
- `content/injector/`：`DefaultContentInjector`（模板化注入 + metadata 保留）。
- 挂载方式：`AiServices.builder().retrievalAugmentor(...)`（`~/develop/opensource/langchain4j/langchain4j/src/main/java/dev/langchain4j/service/AiServices.java`），与 tools、memory 平级。

**评价**：与 spring-ai 相比多了三块拼图——**QueryRouter（多库路由）、ReRankingContentAggregator（重排进管线）、ReciprocalRankFuser（多路融合）**。多查询扩展 × 多 retriever × RRF/rerank 聚合，能纯 Java 拼出「多路召回+融合重排」的标准企业 RAG 检索层，这在 spring-ai 里要手写 Joiner。

### rerank 专项

- langchain4j【核心】：`langchain4j-core/src/main/java/dev/langchain4j/model/scoring/ScoringModel.java#interface`（`scoreAll(List<TextSegment>, String query)` 返回 `Response<List<Double>>`）。实现：`langchain4j-cohere/.../CohereScoringModel.java`（配 RerankRequest/RerankResponse DTO）、`langchain4j-jina/.../JinaScoringModel.java`、`langchain4j-voyage-ai/.../VoyageAiScoringModel.java`、`langchain4j-vertex-ai/.../VertexAiScoringModel.java`、`langchain4j-watsonx`、以及 `langchain4j-onnx-scoring/`（`OnnxScoringBertCrossEncoder` 本地推理，**免 API 依赖的本地 rerank**，私有化部署友好）。
- spring-ai：❌。全仓 grep `rerank` 仅命中 Bedrock KnowledgeBase（`vector-stores/spring-ai-bedrock-knowledgebase-store/.../BedrockKnowledgeBaseVectorStore.java`，配置 `reranking-model-arn` 交给 AWS 托管服务）。无 ScoringModel 层抽象，无 Cohere/Jina 客户端，无本地 cross-encoder。**这是与 Python 生态最刺眼的一处差距**（llama_index / haystack 均有 reranker 抽象与多家实现，见 05/06 维度结论）。
- spring-ai-alibaba 补位：`spring-boot-starters/spring-ai-alibaba-starter-builtin-nodes/.../node/KnowledgeRetrievalNode.java` 引用 `com.alibaba.cloud.ai.model.RerankModel` + `DashScopeRerankOptions`（内部类 `KnowledgeRetrievalDocumentRanker` 实现检索后排序）——但这两个类型**不在主仓源码里**，来自外部 artifact `spring-ai-alibaba-starter-dashscope`（见下文第四节）⚠️。

### 混合检索专项

- langchain4j ✅（有限）：① `langchain4j-elasticsearch/src/main/java/dev/langchain4j/store/embedding/elasticsearch/ElasticsearchConfigurationHybrid.java`——kNN+全文由 ES 服务端 RRF 融合、可带 reranker，**需 ES 付费 license**（javadoc 原话）；配套 `rag/content/retriever/elasticsearch/ElasticsearchContentRetriever.java` 支持 knn/full-text/hybrid/hybrid+reranker 四种。② `langchain4j-milvus-v2/.../MilvusV2EmbeddingStore.java`——`MilvusSparseMode.BM25` 稠密+稀疏混合（`buildHybridSearchRequest`、sparse_vector 字段、`io.milvus.HybridSearchReq`）。③ core 的 `ReciprocalRankFuser` 给了自拼多路的原语。
- spring-ai ❌：ES store 主代码无 hybrid/BM25/RRF 命中，`similaritySearch` 单路 kNN。要做混合得自建（如 BM25 用 Lucene 另写一路，结果在 Advisor/Joiner 层融合）。
- 通用性局限（两家同病）：没有 Python 侧「BM25Retriever 任意库可插 + 多种融合策略（RRF/加权/分布融合）」的通用组件（对照 haystack 2.x HybridRetriever / llama_index QueryFusionRetriever 的生态位），Java 的 hybrid 绑定在特定托管服务能力上。

## 三、与 Python 生态差距清单（三档）

### A. Java 能做（生态已就位，不必求助 Python）

1. **标准向量 RAG 主管线**：读（Tika/PDFBox/POI）→ 切（含层级父子切分）→ 嵌 → 21~24 家向量库 → 检索 → 生成，两框架全链路 API 齐备，且都过了 1.0 GA，API 相对稳。
2. **metadata filter / 权限过滤**：spring-ai `Filter.Expression`（42 个方言转换器文件）、langchain4j `Filter`（比较/逻辑完备，各 store mapper）。QA Advisor 还支持从请求上下文动态注入 filter 字符串。
3. **多路召回 + 融合 + 重排**（langchain4j 路线）：MultiQuery 扩展 × LanguageModelQueryRouter 多库路由 × RRF 融合 × Cohere/Jina/Voyage/**本地 ONNX** rerank，全在框架内。
4. **观测与测试基建**：spring-ai 的 Micrometer 全链路（chat/advisor/vectorstore 三层 Observation）+ testcontainers 连接细节工厂（chroma/qdrant/opensearch/typesense 等）；langchain4j 有 observation/micrometer 模块 + 各 store 的 testcontainers IT。企业化工程配套不输 Python。
5. **Agentic RAG**：langchain4j AiServices（声明式接口把 RAG+tools+memory 打包）、spring-ai ChatClient+Advisor 链；spring-ai-alibaba 直接给了 Graph 化 RAG agent 工作流示例（rewrite→retrieve→agent，`examples/multiagent-patterns/workflow/.../ragagent/RagAgentConfig.java`【示例】）。形态上 Java 用「Advisor 链/声明式 Service + Graph」对照 Python 的 langgraph/llama-index workflow，表达力够用、社区模式库少一些。

### B. Java 要自己写（生态有缝，需补胶水/自研）

1. **rerank（spring-ai 路线）**：无抽象。要么自写 ScoringModel 等价物（HTTP 调 Cohere/Jina/DashScope，或 ONNX Runtime 加载 bge-reranker——可参考 langchain4j-onnx-scoring 的做法），要么换 langchain4j/引入 spring-ai-alibaba extensions 的 RerankModel。
2. **混合检索通用件**：BM25 一路需自建（Lucene 在手，工作量可控但没人替你写）；融合除 RRF 外的加权/分布融合要自己实现；ES hybrid 绑付费 license，Milvus hybrid 绑 Milvus v2。
3. **复杂文档解析**：Tika/PDFBox 对扫描件、复杂表格、版面还原的能力弱于 Python 侧专用解析器（MinerU/unstructured/pikepdf 生态，见 03/04 维度）。langchain4j 的 docling parser 是对接 Python docling 服务的封装，等于曲线承认了这一点。表格结构化抽取、OCR、版面分析建议独立成解析服务（Python 或商用 API），Java 侧只做编排。
4. **ETL 编排（spring-ai）**：没有 Pipeline 类，Reader→Transformer→Writer 靠手写函数组合与批处理容错（断点续传、增量更新、失败重试队列）；langchain4j 的 EmbeddingStoreIngestor 也只是薄封装。企业级摄入管线（去重、版本化、增量索引）两家都要自建——这部分 Python 侧（llama_index ingestion pipeline + 变换缓存）同样要自建，差距不大，属"两边都自己写"。

### C. 建议 Python 做（短期别在 Java 里硬啃）

1. **深度文档解析服务**：MinerU/docling/unstructured 一线工具链 + PDF 复杂版面的长尾问题；作为独立微服务输出 Markdown/JSON，Java 主链消费。
2. **评测体系**：RAGAS/trulens 类现成评测器与数据集工具在 Java 无对应物（spring-ai-alibaba Admin 有评测宣称，但主仓内未验证实现）⚠️。
3. **前沿检索技术快跑跟进**：GraphRAG/LightRAG/ColBERT/late-interaction 等新玩具（05 维度）首发几乎都在 Python，等成熟后要么服务化引入，要么等 Java 侧跟进（langchain4j 社区偶有 PR）。

## 四、spring-ai-alibaba 增值与去向查证

- **定位大转身**：现主干已不是"Spring AI 的 DashScope 增强包"，而是 Agentic/Workflow/Multi-agent 框架（README 自述 "A production-ready framework for building Agentic, Workflow, and Multi-agent applications"）：`spring-ai-alibaba-agent-framework`（ReactAgent、Sequential/Parallel/Routing/LoopAgent、context engineering、HITL）+ `spring-ai-alibaba-graph-core`（状态图运行时）+ Admin 可视化平台 + Sandbox。RAG 在其中是「Graph 的一个节点」而非独立模块。
- **DashScope/RerankModel 外迁**：主仓源码已无 `com.alibaba.cloud.ai.dashscope` 包；builtin-nodes 通过 optional 依赖 `spring-ai-alibaba-starter-dashscope` 引入（`spring-boot-starters/spring-ai-alibaba-starter-builtin-nodes/pom.xml`）。README 第 141 行明确指向独立仓 `spring-ai-alibaba/spring-ai-extensions`（"Extended implementations for Spring AI core concepts, including DashScopeChatModel, MCP registry"），CHANGELOG 1.1.0.0 亦记录构建于 Extensions 1.1.0.0【文档】。**即：DashScope 模型适配与 RerankModel 抽象在 extensions 仓，本次未克隆，源码级结论标 ⚠️**。
- **GraphRAG 查证**：❌ 主仓无实现——当前树 grep `GraphRAG` 仅命中示例目录名 `ragagent`；**全历史（3250 commits）pickaxe 搜 "GraphRAG" 零命中**；docs/ 无 GraphRAG 文档。早年（0.x 时代）官网宣称的 GraphRAG 支持在现主干不存在，若仍维护应也在 extensions 仓或已废弃，未验证 ⚠️。现存的 RAG 增强就两件：`KnowledgeRetrievalNode`（检索+DashScope rerank 节点）与 `DocumentExtractorNode`（解析节点），均在 `spring-boot-starters/spring-ai-alibaba-starter-builtin-nodes/src/main/java/com/alibaba/cloud/ai/graph/node/`【核心】。
- **对 Java 团队的实际意义**：它补的不是 RAG 能力，而是 **agent 编排与工程化平台**（Graph 运行时、可视化 Admin、A2A/Nacos、沙箱）。若走 spring-ai 路线又要 rerank，其 extensions 的 RerankModel 是现成参考实现。

## 五、Java 团队落地建议

1. **框架选型按"检索层野心"分**：检索层要 rerank/路由/RRF 全家桶 → **langchain4j**（五段式 Augmentor + ScoringModel 六实现是硬差距）；团队已重度 Spring 化、要的是与 Spring Boot/观测体系无缝 → **spring-ai**（Micrometer/testcontainers/autoconfigure 体验最佳），但 rerank/融合自建。两者不互斥：spring-ai 管生成与 Advisor，检索层引 langchain4j 组件（Filter 模型不同，需换算层）。
2. **rerank 最短路径**：私有化 → ONNX 本地 cross-encoder（抄 langchain4j-onnx-scoring）；云上 → Cohere/Jina/Voyage HTTP 客户端（百行级）；国内云 → DashScope rerank（spring-ai-alibaba extensions）。
3. **混合检索**：已用 Milvus → 直接 milvus-v2 的 BM25 hybrid；已用 ES 且有付费 license → langchain4j ES hybrid；否则「Lucene BM25 自建一路 + 向量一路 + RRF 融合」，融合原语可复用 `ReciprocalRankFuser`。
4. **文档解析独立成服务**：Java 主链只吃 Markdown/JSON；深度解析（扫描件/表格/版面）交给 Python 侧（MinerU/docling）部署的独立服务。这条边界划清后，"Python 侧要不要保留"的答案就是：**保留一个解析（+评测）小服务即可，主管线可以全 Java**。
5. **警惕 spring-ai-alibaba 的定位漂移**：它的价值在 agent 编排与平台化，不在 RAG 增值；引入前确认 extensions 仓（DashScope/RerankModel 真身）的版本节奏与质量，其 1.x 与 Spring AI 1.1 绑定。

## 六、证据与存疑清单

### 证据（节选，均为冻结基线）

【核心】接口与实现类：
- `~/develop/opensource/spring-ai/spring-ai-commons/src/main/java/org/springframework/ai/document/DocumentReader.java#interface`（Supplier）、同目录 `DocumentTransformer.java`（Function）、`DocumentWriter.java`（Consumer）；`spring-ai-commons/.../transformer/splitter/TokenTextSplitter.java`
- `~/develop/opensource/spring-ai/spring-ai-rag/src/main/java/org/springframework/ai/rag/advisor/RetrievalAugmentationAdvisor.java#class`；`advisors/spring-ai-vector-store-advisor/.../QuestionAnswerAdvisor.java#class`
- `~/develop/opensource/spring-ai/spring-ai-vector-store/src/main/java/org/springframework/ai/vectorstore/filter/`（Filter/antlr4/converter）；42 个 FilterExpressionConverter 实现文件散布 vector-stores/
- `~/develop/opensource/spring-ai/spring-ai-spring-boot-testcontainers/src/main/java/org/springframework/ai/testcontainers/service/connection/`（chroma/qdrant/opensearch/typesense/mcp 连接工厂）；`vector-stores/spring-ai-pgvector-store/src/test/.../PgVectorStoreObservationIT.java` 等 IT
- `~/develop/opensource/langchain4j/langchain4j-core/src/main/java/dev/langchain4j/rag/DefaultRetrievalAugmentor.java#class`（含五段流程 javadoc、虚拟线程 executor 说明）；`rag/query/router/LanguageModelQueryRouter.java`、`rag/content/aggregator/ReRankingContentAggregator.java`、`rag/content/aggregator/ReciprocalRankFuser.java`
- `~/develop/opensource/langchain4j/langchain4j-core/src/main/java/dev/langchain4j/model/scoring/ScoringModel.java#interface`；`langchain4j-cohere/.../CohereScoringModel.java`、`langchain4j-onnx-scoring/.../OnnxScoringBertCrossEncoder.java`、`langchain4j-jina|voyage-ai|vertex-ai|watsonx` 同款
- `~/develop/opensource/langchain4j/langchain4j-elasticsearch/src/main/java/dev/langchain4j/store/embedding/elasticsearch/ElasticsearchConfigurationHybrid.java`（javadoc 注明需付费 license）；`langchain4j-milvus-v2/.../MilvusV2EmbeddingStore.java`（MilvusSparseMode.BM25 / HybridSearchReq）
- `~/develop/opensource/spring-ai-alibaba/spring-boot-starters/spring-ai-alibaba-starter-builtin-nodes/src/main/java/com/alibaba/cloud/ai/graph/node/KnowledgeRetrievalNode.java`（import com.alibaba.cloud.ai.model.RerankModel / DashScopeRerankOptions）

【示例】：`spring-ai-alibaba/examples/multiagent-patterns/workflow/.../ragagent/RagAgentConfig.java`（rewrite→retrieve→agent 工作流）；langchain4j `langchain4j-easy-rag/`（极简 RAG 入口）。

【文档】：spring-ai `spring-ai-docs/.../api/vectordbs/bedrock-knowledge-base.adoc`（reranking-model-arn 托管 rerank）；spring-ai-alibaba `README.md`（extensions 仓指引、框架定位）、`CHANGELOG.md`（1.1.0.0 基于 Spring AI 1.1.0 + Extensions 1.1.0.0）。

### 存疑（未验证，不臆测）

1. ⚠️ **spring-ai-alibaba extensions 仓未克隆**：DashScope 适配、`com.alibaba.cloud.ai.model.RerankModel` 的接口质量与实现深度、以及 GraphRAG 是否在该仓存活，均未做源码级验证（仅主仓 pom 依赖与 README 指引佐证其存在与归属）。
2. ⚠️ **langchain4j-community 仓未克隆**：社区侧向量库/模型增量（如更多国产库适配）未清点，本文向量库计数仅覆盖主仓。
3. ⚠️ spring-ai 各向量库适配的**深度差异**（如 neo4j/opensearch 是否支持 filter 全算子）未逐一验证，仅确认 42 个转换器文件存在与 pgvector/ES 的 IT 存在。
4. ⚠️ spring-ai-alibaba Admin 的「评测」宣称只有平台截图/文档，主仓 `spring-ai-alibaba-admin` 未做 RAG 评测能力的源码核查。
5. ⚠️ 版本结论以冻结基线为准：spring-ai 主干为 2.0.2-SNAPSHOT（1.0/1.1 已 GA 发布）、langchain4j 主干 1.21.0-beta31-SNAPSHOT；正式 GA tag 的精确内容未逐 tag 比对。
