# 10a. 厂商第一方实践：OpenAI 与 Anthropic 的官方 RAG 最佳实践

> 调研日期：2026-10-15。本篇是开源源码级调研（01-09）的补充维度：厂商自己怎么做 RAG、卖什么、官方口径怎么说。
> 证据等级标注：【一手-源码】本地 openai-cookbook（~/develop/opensource/openai-cookbook，commit 9aad95f，2026-09-12）；【一手-文档】官方文档/博客原文（给 URL 与引文）；【转述】第三方文章。
> 网络说明：platform.openai.com 与 developers.openai.com 对 WebFetch 返回 403，改用备用网页读取工具成功取到正文；platform.claude.com 部分页面区域封锁，docs.claude.com 可读。

---

## 一、两家实践总表

| 维度 | OpenAI | Anthropic |
|---|---|---|
| 商用形态 | **托管 RAG 产品**：vector store + File Search 工具 + Retrieval API，一站式（分块/embedding/检索/重排全内置） | **方法学 + API 原语**：无托管向量库产品，给 Contextual Retrieval 方法、Citations API、prompt caching；实现留给用户/生态（AWS Bedrock 已集成） |
| 分块 | 内置自动分块，默认 `max_chunk_size_tokens=800`、`chunk_overlap_tokens=400`，可覆盖（100–4096 tokens，overlap ≤ 一半）【一手-文档】 | 不做产品化分块；官方建议「usually no more than a few hundred tokens」，成本测算按 800-token chunk【一手-文档】 |
| 混合检索 | **内置且可调**：`hybrid_search` 参数带 `rrf_embedding_weight` / `rrf_text_weight`（RRF 倒数排名融合，语义+稀疏关键词），ranker 可选（`auto` / `default-2024-08-21`）+ `score_threshold`【一手-文档】；cookbook 原文确认「score 由我们的 ranker 计算，用的是 hybrid search」【一手-源码】 | 官方实测配方：contextual embeddings + contextual BM25 融合（建议 rank fusion），rerank 用第三方 Cohere Rerank【一手-文档】 |
| Rerank | ranker 内置但内部不公开（是否 cross-encoder 未披露）；cookbook 另有 LLM 当 cross-encoder 的教程【一手-源码】 | 明确用 Cohere Rerank：top-150 召回重排取 top-20【一手-文档】 |
| 查询变换 | 产品内置 `rewrite_query: true`【一手-文档】；cookbook 有 HyDE 教程；Deep Research 官方建议前置轻量模型做 prompt rewriter【一手-源码】 | Contextual Retrieval 不涉及查询侧；2025 年 context engineering 叙事转向「agent 自主生成查询」【一手-文档】 |
| 引用 | annotations 内联引用，含 `start_index/end_index`（字符区间）、`file_id/filename`【一手-源码+文档】 | Citations API：documents 参数（text/PDF block），响应给 `cited_text` + 引用定位，可接 web search / Google Search【一手-文档】 |
| 定价 | 向量库按存储计费：首 1GB 免费，之后 **$0.10/GB/天**【一手-文档】 | 上下文化成本 **$1.02/百万文档 token**（一次性，靠 prompt caching 压下来）【一手-文档】 |
| 官方 RAG vs 长上下文口径 | 经典口径「Search 优于微调」（教风格不教事实）；大语料受上下文长度限制，用 Search-Ask【一手-源码】 | 知识库 **< 200k tokens（约 500 页）直接全塞 prompt + prompt caching，别做 RAG**【一手-文档】 |

### OpenAI 产品化设计细节（File Search / Retrieval API）

【一手-文档】https://developers.openai.com/api/docs/guides/retrieval 与 .../guides/tools-file-search：

- 核心承诺：「When you add a file to a vector store it will be automatically chunked, embedded, and indexed」——开发者不碰分块和 embedding，只上传文件。
- 开发者可控面：分块参数（静态覆盖）、`max_num_results`（默认 10，上限 50）、`score_threshold`（0–1）、RRF 双权重、`rewrite_query`、属性过滤（`eq/ne/gt/gte/lt/lte` 支持 string/number/date，`and/or` 嵌套）与文件级过滤（type/source/filename）。
- 可观测性：`include=["output[*].file_search_call.search_results"]` 可逐条检查检索命中；独立 `vector_stores.search` API 支持脱离 LLM 单独做检索（评测友好）。
- 限制：单文件 512MB / 5M tokens。
- 演进：Assistants API file_search → Responses API file_search，官方发了迁移指南（旧版仍可用）。

对照 ragflow/dify：OpenAI 把「分块+混合检索+重排+引用」全部收进托托管黑盒，换取零运维；代价是分块策略只有静态参数一种（无结构感知模板、无父子块），过滤能力弱于专业检索平台。**业界验证点**：它敢用「800 token + 400 overlap + RRF 混合」当默认值且不暴露更多分块选项，说明这套朴素默认对通用文档已够用；混合检索是一等公民参数而非高级功能。

### OpenAI cookbook RAG 相关 recipe 清单

【一手-源码】`~/develop/opensource/openai-cookbook/examples/`（仓库更新至 2026-09-12）：

| Recipe | 要点 |
|---|---|
| `File_Search_Responses.ipynb` | 托管 RAG 全流程；官方确认 ranker 用 hybrid search；教 LLM 生成评测集 + Recall@k / Precision@k / MRR / MAP |
| `Question_answering_using_embeddings.ipynb` | 经典 Search-Ask 两步法；「Why search is better than fine-tuning」官方口径出处；指出可结合多路检索、HyDE、关键词改写 |
| `Search_reranking_with_cross-encoders.ipynb` | bi-encoder 召回 + GPT 当 cross-encoder 重排（few-shot + `logit_bias` + logprobs 打分）；强调「over-fetch 再重排」和域内 few-shot |
| `Parse_PDF_docs_for_RAG.ipynb` | GPT-4o 视觉解析 PDF（幻灯片/网页导出）；按页逻辑分块；建议给 chunk 前置标题/文档描述元数据；结尾建议「rule-based filtering or re-ranking」 |
| `vector_databases/chroma/hyde-with-chroma-and-openai.ipynb` | HyDE 查询变换 + 距离阈值过滤，SciFact 基准实测显著提升；「naive query and retrieval may not produce the best results」 |
| `evaluation/Evaluate_RAG_with_LlamaIndex.ipynb` | 检索评估（Hit Rate、MRR）与响应评估（Faithfulness、Relevancy）分离；「Evaluation should serve as the primary metric」 |
| `RAG_with_graph_db.ipynb` | GraphRAG 方向 |
| `deep_research_api/`（3 个 notebook） | o3/o4-mini-deep-research：agent 自主规划子问题+搜索+代码执行；MCP 挂内部知识库（File Storage 自动向量化）；内联引用带字符区间 |
| `chatgpt/rag-quickstart/` | Azure / GCP / Pinecone-Retool 三套企业快速启动 |
| `vector_databases/`（20+ 库） | Redis hybrid query、Elasticsearch hybrid 等第三方集成 |

### Agentic 检索方向（OpenAI）

【一手-文档】web search guide 原文：「**agentic search with reasoning models** is an approach where the model takes an active role in search — deciding when and what to search, automatically generating refined queries, and ranking results」，即模型主动决定搜不搜、搜什么、自己改写排序；相关 concepts 文档还列了 search ranking、query generation、reflexion。产品侧对应 File Search（Responses API 工具，模型自主调用）与 Deep Research API（多步规划+引用）。⚠️ 注：openai.com/index/agentic-search-developers 博客本体被 403 挡住，未取到原文，仅以 developers.openai.com 文档为准。

---

## 二、Contextual Retrieval 专题（Anthropic，2024-09-19）

【一手-文档】https://www.anthropic.com/news/contextual-retrieval（与 /engineering/contextual-retrieval 同文）

### 问题定义
朴素分块后 chunk 丢失文档级语境：例句「The company's revenue grew by 3% over the previous quarter.」脱离原文后不知道是哪家公司、哪个季度——embedding 和 BM25 都无法正确命中。

### 方法解剖（四步递进）
1. **Contextual Embeddings**：用 Claude（原文为长上下文小模型，cookbook 实现用 Haiku 级）对每个 chunk 生成 50–100 token 的定位上下文——prompt 给整篇文档 + 用标签包住的 chunk，要求「give a short succinct context to situate this chunk within the overall document」。生成结果前置到 chunk 再做 embedding。
2. **Contextual BM25**：同一份上下文前缀也加进 BM25 索引。BM25 负责精确词面匹配（如错误码「TS-999」），弥补 embedding 对稀有 token 的弱项。
3. **混合融合**：contextual embeddings + contextual BM25 融合（官方推荐 rank fusion 类做法）。
4. **Rerank**：top-150 召回交给 reranker（实测 Cohere Rerank）逐条与 query 打分，取 top-20 进模型。

### 实测数字（top-20 chunk 检索失败率）
| 配置 | 失败率 | 降幅 |
|---|---|---|
| 基线（纯 embedding） | 5.7% | — |
| + Contextual Embeddings | 3.7% | **-35%** |
| + Contextual BM25（混合） | 2.9% | **-49%** |
| + Rerank | 1.9% | **-67%** |

其余结论：上下文化在所有测试的 embedding 模型组合上都有效（Gemini、Voyage 表现最佳）；top-20 优于 top-5/top-10。

### 成本
一次性预处理 **$1.02 / 百万文档 token**（按 800-token chunk、8k-token 文档、50-token 指令、100-token 上下文测算）——可行性的关键是 prompt caching：整篇文档进缓存后逐 chunk 复用，官方称 caching 对长上下文「reduces latency by >2x and costs by up to 90%」（prompt caching 定价：写 1.25x、读 0.1x，5m/1h 两档 TTL）【一手-文档】。

### 适用边界与调优
- 知识库 **< 200k tokens（约 500 页）：不做 RAG**，全塞 prompt + prompt caching 更简单更好。
- 调优清单：chunk 边界/大小/overlap、选强 embedding 模型、定制 contextualizer prompt（如注入领域术语表）、**始终跑 evals**。

### 后续演进
- 无官方 v2 / 继任方法（2025–2026 检索确认）；2025-09 Anthropic 工程叙事转向 [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)：context rot（token 越多 recall 越差）、just-in-time 检索（Claude Code 用 grep/head/tail 定向读而非全量加载）、预取+自主探索的混合策略、「do the simplest thing that works」【一手-文档】。
- 生态落地：anthropic-cookbook 收录官方实现 `capabilities/contextual-embeddings/`（guide.ipynb + Promptfoo 评估脚本 + AWS Lambda 参考实现）【一手-源码，gh api 确认路径】；AWS Bedrock Knowledge Bases 2025-06 集成 contextual retrieval【转述】。

### Claude Citations（引用机制）
【一手-文档】https://docs.claude.com/en/docs/build-with-claude/citations ：API 请求级支持——`documents` 参数直接传 text / PDF content block，回答时逐句返回 `cited_text` 及其引用的文档片段；可把用户 prompt 本身放进 document 要求带引用回答；与 web search / Google Search 工具组合引用网页。官方可靠性提醒：上下文须包含完整源文档（否则引用会失败/漂移）、streaming 下 citation 事件可能跨 chunk 分裂、引用断言只覆盖到前缀文本。**设计取向**：把「引用」做成模型 API 原语（生成时对齐源文档），而不是检索后处理拼 URL——与开源「引用溯源当幻觉锚点」结论同向，但粒度到文档片段。

---

## 三、与开源源码结论互证清单

| 开源结论 | OpenAI 官方 | Anthropic 官方 | 判定 |
|---|---|---|---|
| 混合检索+rerank 是标配（BM25+向量融合+cross-encoder 重排） | RRF 混合为内置一等公民参数（双权重可调）+ ranker + score_threshold；cookbook 教 LLM cross-encoder | contextual BM25+embedding 融合 + Cohere Rerank，-49%→-67% 实测 | **一致，业界共识**。开源（ragflow/dify 等）与两家厂商三方互证 |
| 分块：结构感知优于盲切、父子块/句子窗口 | 产品默认 800/400 盲切即够用；cookbook 另建议按页/标题逻辑分块 + chunk 前置元数据（标题、文档描述） | 800-token 上下，但用「LLM 生成上下文前置」补语境，等价于 chunk 自带文档记忆 | **部分分歧**：两家都没产品化父子块/句子窗口——Anthropic 用「语义补语境」路线替代结构化父子块，OpenAI 用「chunk 前置元数据」轻量替代；LlamaIndex 式高级分块在厂商侧属 DIY 建议而非产品能力 |
| 查询变换（多查询/改写） | 产品内置 `rewrite_query`；HyDE 官方教程；Deep Research 建议前置 rewriter 模型；agentic search = 模型自生成查询 | Contextual Retrieval 全在索引侧，查询侧不处理；2025 叙事把查询变换内化进 agent 循环 | **半一致**：OpenAI 与开源结论一致且产品化；Anthropic 走「重索引、轻查询」路线——contextual retrieval 把功夫花在离线侧，是个真实的设计分歧 |
| 评测：引用溯源当幻觉锚点 | cookbook 教 Recall@k/MRR/MAP + Faithfulness/Relevancy 分层评估；产品内置字符区间 annotations | cookbook 配 Promptfoo 评估脚本；官方反复强调 always run evals；Citations API 把溯源做成原语 | **一致，业界共识**；厂商额外贡献：检索评估与响应评估分层、引用粒度到字符/片段 |

**开源没做到 / 厂商领先的点**：
1. 引用带字符区间（`start_index/end_index` annotations）作为产品原语——开源平台引用多停在文档级。
2. 查询改写内置进检索工具参数。
3. prompt caching 把「LLM 增强索引」成本压到 $1.02/M tokens——没有 caching 经济学的自建系统做 contextual retrieval 会贵一个量级。
4. RRF 混合权重作为公开可调参数（开源有混合但权重暴露程度不一）。

**厂商口径与开源常见默认的分歧**：
1. **rerank 模型来源**：Anthropic 官方实测直接用第三方 Cohere Rerank——印证开源界「重排器自建不如专用模型」的现状。
2. **小库不做 RAG**：Anthropic 明确 <200k tokens 全塞+缓存优于 RAG；开源平台（ragflow/dify）默认万物皆 RAG，缺少这个「不检索」出口。
3. **商业形态**：OpenAI 收敛成托管黑盒（换取零运维、按存储计费），Anthropic 只发方法学——企业自建开源栈恰好卡在两者之间：能力面学 Anthropic 配方，运维面学 OpenAI 产品设计。

### 对企业自建开源栈的启示
综合两家第一方实践，给企业级 RAG 选型的三条硬结论：其一，检索质量的钱应该优先花在「索引侧补语境 + 混合 + 重排」这三件已被厂商实测验证的事上（合计降幅 67%），而不是花在更花哨的分块图算法上——两家厂商都没把父子块/句子窗口当核心武器。其二，评测必须分层：检索层（Recall@k/MRR）与响应层（忠实度/引用）分开度量，且引用锚点要细到片段乃至字符区间，这在两家都是产品原语。其三，成本结构决定架构：没有 prompt caching 类的经济学，上下文化这类 LLM 增强索引的方案会贵一个量级——自建栈评估此类技术时必须把缓存命中率算进总账。

---

## 四、证据与存疑清单

### 证据
- 【一手-源码】`~/develop/opensource/openai-cookbook/examples/`：`File_Search_Responses.ipynb`（hybrid search ranker 原文、MRR/MAP 评估法；注意实际路径在 examples/ 根，复核 2026-10-15 修正）、`Question_answering_using_embeddings.ipynb`（search vs fine-tuning 口径原文）、`Search_reranking_with_cross-encoders.ipynb`、`Parse_PDF_docs_for_RAG.ipynb`、`vector_databases/chroma/hyde-with-chroma-and-openai.ipynb`、`evaluation/Evaluate_RAG_with_LlamaIndex.ipynb`、`deep_research_api/introduction_to_deep_research_api.ipynb`（仓库 commit 9aad95f，2026-09-12）。
- 【一手-文档】OpenAI：https://developers.openai.com/api/docs/guides/retrieval 、.../guides/tools-file-search 、.../guides/tools-web-search （agentic search 段）。
- 【一手-文档】Anthropic：https://www.anthropic.com/news/contextual-retrieval （两次抓取交叉验证数字）、https://docs.claude.com/en/docs/build-with-claude/citations 、https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents 、https://platform.claude.com/docs/en/build-with-claude/prompt-caching 。
- 【一手-源码（远程确认）】anthropics/anthropic-cookbook `capabilities/contextual-embeddings/`（gh api 目录树 + README）。
- 【转述】AWS Bedrock 集成 contextual retrieval（2025-06）；LangChain reference 镜像 OpenAI agentic search 定义。

### 存疑
1. ⚠️ **「contextual chunk headers」未在现版原文出现**：任务提示中的 chunk headers（文档标题/日期前置）在当前 anthropic.com 文章两次抓取均无此节，疑为 2024 原版内容在后续更新中删除，或与其他文章混淆。现版方法只有 LLM 生成的 situate 上下文。
2. ⚠️ **OpenAI ranker 内部机制未披露**：官方只给 ranker 版本号（default-2024-08-21）与 RRF 权重，是否为 cross-encoder、是否含学习排序均无公开信息。
3. ❌ **openai.com 博客原文未取到**（agentic search 开发者博客 403），agentic search 结论以 developers.openai.com 文档为准，未覆盖博客可能有的额外设计说明。
4. ⚠️ **OpenAI「RAG vs 长上下文」无单页官方决策文档**：口径拼自 cookbook 经典段落（search 优于 fine-tuning）与 Anthropic 的 200k-token 边界，两家均未给出完整的「RAG/微调/长上下文」三方决策矩阵文档。
5. ⚠️ **platform.claude.com 区域封锁**：Claude RAG 专题页（docs 的 RAG how-to）未直接读到，引用机制以 citations 文档为准。
