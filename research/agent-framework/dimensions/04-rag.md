# 维度 4：RAG（检索增强生成）

> 本维度回答：框架把「文档管道（loader→切分→嵌入→索引）、混合检索（hybrid search + fusion）、重排（rerank）、引用溯源（citation）」当作多大的核心资产。17 个框架呈清晰光谱：一端是 RAG 原生框架（llama_index、langchain4j、spring-ai、dify 把全管道做进主包/主模块），中间是「抽象壳 + 生态承载」（langchain、agent-framework、agentscope、agentscope-java、spring-ai-alibaba），另一端是彻底让位外部（adk 双语言把检索让给 Vertex AI 托管服务、openai-agents 让给 OpenAI FileSearch、claude-sdk 完全没有、langgraph/deepagents 用「图模式 / agentic 检索」替代管线式 RAG）。

## 4.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| llama_index | ✅ | 最厚实现：15+ 索引类型、18 种 query engine、RRF/相对分数混合融合、rerank 后处理器抽象、内容块级引用、并行摄取管道 | llama-index-core/llama_index/core/retrievers/fusion_retriever.py#QueryFusionRetriever；query_engine/citation_query_engine.py#CitationQueryEngine；postprocessor/types.py#BaseNodePostprocessor；ingestion/pipeline.py#IngestionPipeline |
| langchain4j | ✅ | core 内全管道：QueryTransformer→QueryRouter→ContentRetriever→ContentAggregator（ScoringModel 重排 + RRF 融合）→ContentInjector，约 20 个向量库模块 | langchain4j-core/src/main/java/dev/langchain4j/rag/content/aggregator/ReRankingContentAggregator.java#ReRankingContentAggregator；同目录 ReciprocalRankFuser.java#ReciprocalRankFuser |
| spring-ai | ✅ | 22 个向量库模块 + spring-ai-rag 模块化管道（Transformer/Expander/Retriever/Joiner/Augmenter/PostProcessor）+ 2 个检索 Advisor + ETL 抽象；rerank 仅 Bedrock KB、citation 无抽象 | spring-ai-rag/（管道）；advisors/spring-ai-vector-store-advisor#QuestionAnswerAdvisor；spring-ai-commons/.../document/#DocumentReader |
| dify | ✅ | 平台级全管道：异步索引 runner、10+ 向量库、hybrid（semantic+full_text+keyword）、模型/加权双路 rerank + reorder、多库路由、retriever_resources 引用落 Message | api/core/rag/retrieval/dataset_retrieval.py#DatasetRetrieval；api/core/rag/rerank/weight_rerank.py#WeightRerankRunner；api/core/rag/entities/citation_metadata.py#RetrievalSourceMetadata |
| crewai | ✅ | Knowledge（7 种源，chromadb 底层）+ rag 基建（chromadb/qdrant 双 client + 18 个嵌入 provider 目录）；无 rerank/hybrid/citation 核心抽象 | lib/crewai/src/crewai/knowledge/knowledge.py#Knowledge；rag/embeddings/providers/（18 目录）；rag/{chromadb,qdrant}/ |
| agentscope | ✅ | KnowledgeBase（top_k/阈值/按 (document_id, chunk_index) 去重）+ 4 向量库 + 7 解析器 + app 层 KB REST 服务/异步索引 worker；无 rerank/hybrid/citation | src/agentscope/rag/_knowledge.py#KnowledgeBase；rag/_vdb/（qdrant/milvus-lite/mongodb/elasticsearch）；app/_router/_knowledge_base.py |
| langchain | ✅ | core 留抽象：BaseRetriever/VectorStore/InMemoryVectorStore/index()+RecordManager 增量去重/CrossEncoder rerank 抽象；实现散在 partners；hybrid/citation 无核心抽象 | libs/core/langchain_core/retrievers.py#BaseRetriever；vectorstores/base.py#VectorStore；indexing/api.py#index；cross_encoders.py#CrossEncoder |
| adk-python | 🟡 | 无自建向量/切分抽象，检索 = Vertex AI RAG/Search 托管工具族 + LlamaIndexRetriever 桥 + VertexAiRagMemoryService（检索即记忆） | src/google/adk/tools/retrieval/（base_retrieval_tool.py、vertex_ai_rag_retrieval.py、llama_index_retrieval.py）；memory/vertex_ai_rag_memory_service.py |
| agentscope-java | 🟡 | core 仅 Knowledge 接口 + GenericRAGHook（注上下文）/KnowledgeRetrievalTools（注工具）两种用法；5 个官方扩展全部委托外部引擎（bailian/dify/haystack/ragflow/simple） | agentscope-core/.../rag/Knowledge.java；agentscope-extensions/agentscope-extensions-rag/（5 模块） |
| spring-ai-alibaba | 🟡 | 核心（graph-core/agent-framework）无 RAG；官方 starter KnowledgeRetrievalNode + admin 知识库（IndexPipeline/splitter/DashscopeReranker，VectorStoreType 枚举仅 ELASTICSEARCH） | spring-boot-starters/.../builtin-nodes/.../KnowledgeRetrievalNode.java；admin-server-core/.../reranker/dashscope/DashscopeReranker.java |
| agent-framework | 🟡 | core 有 @vector_store_model 声明式抽象（VectorStoreField/CollectionDefinition + 过滤器），实现全在生态包（azure-ai-search beta、qdrant/postgres alpha、redis beta）；无 rerank/citation | python/packages/core/agent_framework/_vectors.py#VectorStoreCollectionDefinition(:332)/#VectorStoreField(:156)；生态包见 python/packages/ |
| adk-java | 🔶 | 无 ingestion/向量库，RAG = 「作工具喂给 LLM」：VertexAiRagRetrieval（BaseRetrievalTool 子类）+ VertexAiSearch/UrlContext/GoogleSearch grounding 工具 | core/src/main/java/com/google/adk/tools/retrieval/（BaseRetrievalTool.java、VertexAiRagRetrieval.java） |
| langgraph | 🔶 | 核心零 RAG 抽象；examples/rag 9 个 notebook 演示 agentic/adaptive/CRAG/self-RAG 图模式，检索组件全来自 langchain 生态 | examples/rag/langgraph_agentic_rag.ipynb 等 9 个【示例】 |
| langgraph4j | 🔶 | 框架零 RAG 抽象，由 langchain4j ContentRetriever 生态承载；how-tos 给 agentic/corrective/adaptive 三种图式示例 | how-tos/agentic-rag.ipynb、corrective-rag.ipynb、adaptiverag.ipynb【示例，二次核验存在】 |
| openai-agents-python | 🔶 | 仅托管 FileSearchTool（文件上传 OpenAI 向量存储后检索）+ WebSearch/CodeInterpreter；本地 retriever/向量库/rerank/引用全无 | src/agents/tool.py#FileSearchTool(:779)【核心=托管工具参数面】 |
| claude-agent-sdk-python | ❌ | 无 retriever/embedding/vector store 任何符号；最接近的是 CLI 服务端工具 web_search/web_fetch/code_execution 枚举 | src/claude_agent_sdk/types.py#ServerToolName(:967)【核心=枚举；执行在 CLI】 |
| deepagents | 🔶 | 核心检索范式 = agentic：grep（max_count=1000）/glob/read_file 分页在虚拟文件系统上找证据；talon 实验包有 hybrid 归档检索（见 4.2-E，二次核验确认 RRF k=60） | libs/deepagents/deepagents/backends/protocol.py:499；libs/talon/deepagents_talon/history_vectors.py#HistoryVectorIndex |

## 4.2 实现方式深析

按「RAG 在框架里的身份」分五个派系。

### A. 管道原生派：RAG 是框架的主干（llama_index、langchain4j、spring-ai）

三者都把「查询变换→路由→检索→融合/重排→注入」做成可组合管道，但注入点不同：

- **llama_index**：管道两端开放——`IngestionPipeline`（ingestion/pipeline.py:262）组合 transformations、断点缓存（ingestion/cache.py）、`num_workers` 多进程并行（:547/:606）；查询侧 `Retriever→NodePostprocessor→QueryEngine` 分层。混合检索是检索器级组合：`QueryFusionRetriever`（fusion_retriever.py:33）对多个 retriever + `num_queries` 生成查询做融合，`FUSION_MODES` 三档（:27-29 RECIPROCAL_RANK / RELATIVE_SCORE / DIST_BASED_SCORE）。rerank 是 `BaseNodePostprocessor`（postprocessor/types.py:12）——一个统一后处理器抽象，既装 llm_rerank/rankGPT/sbert_rerank 也装 node_recency/metadata_replacement。引用深入到内容块：`CitationBlock`/`CitableBlock`（base/llms/types.py:1048/:1025）是消息内容块类型，`CitationQueryEngine`（citation_query_engine.py:158）带 citation_chunk_size=512/overlap=20 的独立切分并强制提示词「Every answer should include at least one source citation」（:92）。
- **langchain4j**：管道以 `RetrievalAugmentor`（DefaultRetrievalAugmentor，支持异步分阶段）为根，AiServices 挂接点互斥校验（AiServices.java:177-178 contentRetriever vs retrievalAugmentor）。重排是聚合器：`ReRankingContentAggregator`（ScoringModel 打分 + minScore 阈值 + maxResults，多 query 时需 querySelector 选代表查询）；融合是 `ReciprocalRankFuser`（javadoc 引 Azure hybrid search 文档，`1.0/(k+rank)`，k 默认 60）。citation 是明确缺口：core+主模块 grep `citation` 零命中。
- **spring-ai**：Java 注解风格的两档用法——简单档 `QuestionAnswerAdvisor`（similaritySearch→模板拼接，文档回填 advise context 键 `qa_retrieved_documents`）；全控档 `RetrievalAugmentationAdvisor` 编排 QueryTransformer×N→QueryExpander→DocumentRetriever→DocumentJoiner→QueryAugmenter→DocumentPostProcessor。内置件含 LLM 侧变换（Rewrite/Translation/Compression/MultiQueryExpander）。**rerank 无通用抽象**：rg `rerank` 仅命中 `BedrockKnowledgeBaseVectorStore`（AWS 侧原生，二次核验确认）。ETL 三件套（Reader/Transformer/Writer）在 spring-ai-commons。

取舍对比：llama_index 用「检索器可组合 + 后处理器链」覆盖最多 RAG 变体（auto_merging/recursive/router/flare/sub_question）；langchain4j 用「单一 Augmentor 根 + 阶段接口」最规整；spring-ai 用「Advisor 挂到 ChatClient」最贴 Spring 编程模型，但 rerank/citation 双缺。

### B. 平台产品派：RAG 是带管理面的服务（dify、agentscope、crewai）

- **dify** 是唯一「索引即异步任务系统」的实现：`api/core/indexing_runner.py` + 15+ 个 celery 索引任务（document_indexing_task 等），extractor（notion/website）→splitter→index_processor。检索编排 `DatasetRetrieval` 支持单库/多库（multiple_retrieve 并行线程），多库路由用 `FunctionCallMultiDatasetRouter`/`ReactMultiDatasetRouter`（:675-686）。混合检索是枚举级公民：`RetrievalMethod`（retrieval/retrieval_methods.py:4）= SEMANTIC/FULL_TEXT/HYBRID/KEYWORD，`WeightRerankRunner`（rerank/weight_rerank.py:20）做 jieba 关键词分 × vector_weight + keyword_weight 加权融合（:67），`RerankRunnerFactory` 可切模型重排，另有 `ReorderRunner`（lost-in-the-middle 缓解）。引用是数据结构级：`RetrievalSourceMetadata`（entities/citation_metadata.py，18 字段：dataset/document/segment_id/score/hit_count/page/doc_metadata…）→ retriever_resources 落 Message → 响应管道回放（easy_ui_based_generate_task_pipeline.py:336）。甚至 RAG 本身可被编排为 Workflow（services/rag_pipeline/）。
- **agentscope**：core 层 `KnowledgeBase.retrieve`（top_k=5、score_threshold、按 (document_id, chunk_index) 去重、score 降序——_knowledge.py:193-225 docstring 明示），4 向量库 optional extras，`ApproxTokenChunker` token 近似分块；app 层补齐产品面（上传/管理 REST + blob_store Local/S3 + `enable_index_worker` 异步索引）。检索还能以 middleware 挂进 agent（middleware/_rag.py）。无 rerank/hybrid/citation（rg 零命中，二次核验确认）。
- **crewai**：面向 crew 的轻管道——`Knowledge`（knowledge/knowledge.py:88）+ 7 种源（pdf/csv/excel/json/text_file/string/crew_docling）+ `KnowledgeStorage`（chromadb）；rag 基建独立成 `rag/` 包（chromadb/qdrant 双 client + embeddings/providers 18 个 provider 目录，二次核验：aws/cohere/google/huggingface/ibm/instructor/jina/microsoft/ollama/onnx/openai/openclip/openrouter/roboflow/sentence_transformer/text2vec/voyageai/custom）。rerank 仅 crewai-tools 独立包的 contextualai 工具（🟡）；hybrid/citation ❌。

### C. 抽象壳派：core 留接口、生态/云填肉（langchain、agent-framework、agentscope-java、spring-ai-alibaba）

- **langchain**：core 保留四个稳定抽象（BaseRetriever、VectorStore+as_retriever、index()+RecordManager 增量去重、CrossEncoder rerank 接口），向量库实现全在 partners（chroma/qdrant…），切分在 libs/text-splitters。hybrid/citation 无核心抽象——与 llama_index 形成对照：langchain 1.x 把 RAG 从「框架主干」降级为「生态协议」。
- **agent-framework**：声明式方向——`@vector_store_model` 装饰 dataclass，`VectorStoreField`（vector/text-keyword/metadata 三类字段）+ `VectorStoreCollectionDefinition`（_vectors.py:156/:332）+ `_vector_filters.py`，检索结果经 context provider 注入对话。4 个生态包（azure-ai-search beta、qdrant/postgres alpha、redis beta）。rerank/hybrid/citation ❌。
- **agentscope-java**：core 薄到只剩 `Knowledge` 接口 + 两个用法（`GenericRAGHook` 检索结果注入上下文、`KnowledgeRetrievalTools` 检索作为工具）+ `RAGMode` 二选一；5 个官方扩展全部委托外部引擎（rag-bailian/rag-dify/rag-haystack/rag-ragflow/rag-simple）——「自建为零、委托为纲」。
- **spring-ai-alibaba**：双轨——graph-core/agent-framework 内零 RAG；官方 starter 出 `KnowledgeRetrievalNode`（图节点形态），admin server 出知识库（IndexPipeline/splitter/DashscopeReranker，但 VectorStoreType.java:28 枚举仅 ELASTICSEARCH）。DashScope 系（DashVector）反而不在内，二次核验确认。

### D. 云服务委托派：检索是别人家的事（adk-python、adk-java、openai-agents）

- **adk-python**（🟡）：`tools/retrieval/` 有正式抽象 `BaseRetrievalTool`，但三个实现里两个是云（VertexAiRagRetriever）、一个是桥（LlamaIndexRetriever 桥接 llama_index 生态，二次核验目录：base_retrieval_tool.py/vertex_ai_rag_retrieval.py/llama_index_retrieval.py/files_retrieval.py）。检索还有一种「记忆化」形态：`VertexAiRagMemoryService`（memory/）把 RAG 服务当 agent 长期记忆后端。工具族 VertexAiSearch/DiscoveryEngine/EnterpriseSearch 都是 grounding 工具。
- **adk-java**（🔶）：连桥都没有——`tools/retrieval/` 仅 BaseRetrievalTool + VertexAiRagRetrieval（二次核验目录仅 2 文件），配 VertexAiSearch/UrlContext/GoogleSearch grounding 工具。框架级 retriever/ingestion 管道不存在。
- **openai-agents-python**（🔶）：`FileSearchTool`（tool.py:779）是 Responses API 托管工具——文件先上传 OpenAI 向量存储，检索、引用标注都在服务端完成；SDK 本地零 RAG。

### E. 反管线派：agentic 检索替代 RAG 管道（deepagents；langgraph/langgraph4j 提供图模式）

- **deepagents**：核心检索三件套 `grep`（glob 过滤、output_mode 三种、默认 max_count=1000）+ `glob` + `read_file`（offset/limit/行号分页），跑在 BackendProtocol 虚拟文件系统上——「让模型自己检索」而非管道检索。**二次核验（档案 ⚠️ 已解决）**：talon 实验包 `history_vectors.py` 的 `HistoryVectorIndex` 是真 hybrid——`search_page()`（:280）把 `archive.lexical()` 词法排名与 `SearchOp` 语义检索（langgraph BaseStore，2s 超时）经 `_fuse()`（:377）做 **RRF 融合（1/(60+rank)，k=60）**，嵌入侧 `EmbeddingProfile` 支持 local（Qwen/Qwen3-Embedding-0.6B）/voyage/openai-compatible/atlas 四适配器，后台异步索引落 BaseStore，语义检索超时/失败显式降级为纯关键词（`using keyword search` warning）。但它是**会话历史归档检索**（alpha 外围），不是文档 ingestion 管道，评级维持 🔶。
- **langgraph / langgraph4j**：RAG = 图上的一种编排模式（agentic-rag/corrective-rag/adaptive-rag/self-rag），核心不给抽象。Python 侧 examples/rag 9 notebook，Java 侧 how-tos 3 notebook（二次核验文件存在）。

### 三个横向切面

**混合检索（vector+keyword+fusion）**：成体系的只有 4 家——llama_index（QueryFusionRetriever 3 融合模式）、langchain4j（ReciprocalRankFuser k=60）、dify（RetrievalMethod.HYBRID_SEARCH + 加权/模型 rerank）、deepagents-talon（RRF k=60，实验）。spring-ai/crewai/agentscope/langchain core 均无 keyword+vector 融合抽象。

**重排（rerank）**：抽象+实现俱全 = llama_index（BaseNodePostprocessor + llm/rankGPT/sbert/structured_llm 等）、langchain4j（ScoringModel + ReRankingContentAggregator）、dify（RerankRunnerFactory 模型档 + WeightRerankRunner 加权档 + ReorderRunner）。只有抽象没实现 = langchain（CrossEncoder 在 core，实现在 partners）、spring-ai-alibaba（admin 的 DashscopeReranker，单一供应商）。子项缺位 = spring-ai（仅 Bedrock KB）、crewai（独立包）、其余 ❌。

**引用溯源（citation）**：只有 2 家成体系——llama_index 把引用做进内容块类型（CitationBlock/CitableBlock）+ 专用 CitationQueryEngine（独立 citation 切分 + 强引用提示词）；dify 把引用做进检索元数据（RetrievalSourceMetadata 18 字段 → retriever_resources → Message）。spring-ai 仅把文档回填 context（`qa_retrieved_documents`）无定位标注；langchain4j 明确零命中；openai-agents 的引用标注发生在 OpenAI 服务端（FileSearch annotations），SDK 不参与。

## 4.3 跨语言对齐

| 对 | Python 侧 | Java 侧 | 差异要点 |
|---|---|---|---|
| langgraph ↔ langgraph4j | 核心零 RAG；examples/rag 9 个 notebook（agentic/adaptive/CRAG/self-RAG 各 local/云变体） | 核心零 RAG；how-tos 3 个 notebook（agentic/corrective/adaptive） | **对等**：两侧都是「图模式示例 + 生态承载（langchain / langchain4j 的 ContentRetriever）」，Python 示例量更多 |
| adk-python(2.9) ↔ adk-java(1.9) | 🟡：BaseRetrievalTool 抽象 + VertexAiRagRetriever + **LlamaIndexRetriever 桥** + FilesRetriever + VertexAiRagMemoryService（RAG 即记忆） | 🔶：仅 BaseRetrievalTool + VertexAiRagRetrieval + grounding 工具族 | **Python 超出**：多 llama_index 桥（本地生态逃生门）与 RAG 记忆服务；Java 全押 GCP 托管，无本地逃生门 |
| agentscope ↔ agentscope-java | ✅：KnowledgeBase + 4 向量库 + 7 解析器 + app 层 KB 服务/索引 worker | 🟡：Knowledge 薄接口 + 5 外部引擎委托扩展（bailian/dify/haystack/ragflow/simple） | **Python 超出（自建广度）**；Java 独有「委托 dify/haystack/ragflow」的取法——不自建管道而编排现成 RAG 引擎 |

## 4.4 取舍与趋势

1. **「RAG 框架」与「Agent 框架」正在解耦**：langgraph/deepagents/openai-agents/claude-sdk 四个 2025-26 年的新世代 agent 框架核心全部零 RAG 抽象，把检索交给生态（langchain）、云（Vertex/OpenAI）或 agentic 检索（grep/read_file）。对比 2023-24 世代（llama_index/langchain4j/spring-ai）把 ingestion 管道当主干——RAG 从「框架必备件」降级为「可插拔能力」。
2. **混合检索的收敛实现是 RRF**：langchain4j `ReciprocalRankFuser`（k=60，引 Azure 文档）、deepagents-talon `_fuse`（k=60）、llama_index `FUSION_MODES.RECIPROCAL_RANK` 三家独立实现了同一公式 `1/(k+rank)`；dify 反其道用可配权重的线性融合（vector_weight + keyword_weight）+ 模型 rerank 双路。RRF 正在成为混合检索的事实默认。
3. **rerank 是抽象普及、实现分化的切面**：有 rerank 抽象的框架（llama_index/langchain4j/dify/langchain/spring-ai-alibaba）都把它建模为「独立后处理阶段」（NodePostprocessor / ContentAggregator / DataPostProcessor），但实现广度差异极大——从 6+ 内置（llama_index）到单供应商（DashscopeReranker）；spring-ai 主框架反而完全没有。
4. **citation 是最稀缺的能力**：17家里只有 llama_index（内容块级）和 dify（元数据级）有真正引用数据结构；其余要么回填原文让下游自理（spring-ai），要么零命中（langchain4j）。检索可引用性普遍不是 agent 框架的优先项。
5. **Java 双子星的 RAG 策略完全相反**：langchain4j 把 RAG 管道做进 core（对标 Python langchain 的黄金时代形态），spring-ai 用 Advisor 机制 + 22 向量库矩阵但缺 rerank/citation；而 adk-java/agentscope-java 选择了「接口 + 云/外部引擎委托」。同一语言生态内 RAG 资产浓度差异悬殊。
6. **「检索即记忆/检索即工具」的新形态**：adk-python 的 VertexAiRagMemoryService 把 RAG 服务当记忆后端、agentscope 的 RAGMiddleware 把检索挂成 agent 中间件、dify 的 DatasetRetrieverTool 把知识库当工具——检索正在从「管道阶段」变成 agent 运行时里可与 memory/tool 互换位置的构件。
