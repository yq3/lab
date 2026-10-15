# 10b. 厂商官方 RAG 实践：Google 与 Microsoft（托管服务形态 + 官方架构指南）

> **性质**：网络文档级调研（非源码级），补齐 01-09 开源源码调研的两家云厂商对照维度。证据分级：【一手-文档】官方文档/架构指南/官方博客原文（附 URL 与关键引文）、【转述】第三方转述、❌/⚠️ 查不到或未核实。调研日 2026-10-15，云文档时效性强（本批文档 update-cycle 90-180 天），半年后需重核。
> **上游**：microsoft/graphrag 已源码级覆盖（dim05），本文只补 Azure 检索/架构/托管服务侧与 Google 全侧。

## 1. 两家实践总表

### 1.1 托管服务能力面

| 能力 | Google（Vertex AI Search，**已更名 Agent Search**，归属 Gemini Enterprise Agent Platform） | Microsoft（Azure AI Search + Foundry） |
|---|---|---|
| 混合检索 | 关键词/语义/blended 模式 + 数据增强功能 ⚠️（blend 具体参数未单独核实）；索引含 BM25/语义/向量 | BM25 + 向量并行 + **RRF 融合**（`1/(rank+k)`，k=60 固定常量，官方原文 "performs best when you set k to a small value, such as 60"）【一手-文档】 |
| 重排 | Rank Service（Vertex Ranking API）；RAG Engine 内置 rerank | **Semantic Ranker**：Bing 系多语 DL 模型，RRF 之后仅重排 **top 50**，每文档摘要输入上限 2048 token（2024-11 从 256 提升），`@search.rerankerScore` 0-4 分离返回；用 semantic ranker 时官方建议向量 `k=50` 吃满输入【一手-文档】 |
| 查询变换 | 多轮搜索、facet、boost；⚠️ high retrieval 特性（文档导航可见）页面抓取失败未核实 | **Query rewrite（preview）**：生成最多 10 个查询变体再检索；**Agentic Retrieval（GA 2026-04 API）**：LLM 查询规划拆子查询→并行执行（关键词/向量/混合）→子查询级 semantic 重排→合并，reasoning effort 分档（minimal/low/medium），返回 grounding 数据+引用+activity log【一手-文档】 |
| 分块/摄取 | RAG Engine：Layout Parser（DoCLAY）/LLM Parser、转换（去 PII/上下文摘要）、算子管线、约束参数 | Indexer + Skillset（Text Split 集成向量化）、Content Understanding（prebuilt-documentSearch 等输出 RAG-ready Markdown）【一手-文档】 |
| 数据刷新 | Target Channel（控制 serving 版本）+ EntityRefresh（定时重爬刷新）【一手-文档】 | Indexer 定时调度 + 增量变更检测；ACL 权限增量同步（2026-05-preview 起 SharePoint 独特权限项级增量）【一手-文档】 |
| 评测 | **Check Grounding API**（产品化 groundedness 打分）+ Gen AI Evaluation Service | 架构指南评测阶段 + RAG Experiment Accelerator（实验框架）【一手-文档】 |

### 1.2 官方推荐参数（有明确数字的才列）

| 参数 | Google 官方值 | Microsoft 官方值 |
|---|---|---|
| 分块大小 | RAG Engine **默认 chunk_size 1024 token / overlap 256 token**，官方建议实验区间 **100-600 token** 评估质量与成本；chunk 数取决于检索长度 | 架构指南不给固定数（"chunking approach is a semipermanent choice"，按文档结构度选策略）；官方 benchmark 实验用 **512 token / 25% overlap**；提示用 BERT token 而非字符计数【一手-文档】 |
| LLM 增强分块 | **官方推荐 LLM 数据转换**并给出自家实验数字：上下文摘要 +12.9% win-rate、问题式分块 +15-20%、上下文标题 +2.7%、问题+上下文标题组合 +27-33%【一手-文档】 | 架构指南把"语言模型增强"列为正式分块策略（图片/表格生成文本表示），无数字【一手-文档】 |
| top_k | RAG Engine 默认 **top 10**；VectorDistance 0.0（全返回）由 lambda 控制：0.5 平衡 / 0.3 质量优先 / 0.7 效率优先（>0.7 有检索失败风险）【一手-文档】 | 用 semantic ranker 时 `k=50`；默认返回 top 50，`maxTextRecallSize` 默认 1000【一手-文档】 |
| 相似度阈值 | 架构指南：向量搜索 cosine 距离 0.5-0.6 起步、rank 服务 0.4-0.5【一手-文档】 | 无官方阈值数（提醒 rerankerScore 分布会漂移，"don't make the limits too granular"）【一手-文档】 |
| Grounding 阈值 | Check Grounding 引用阈值 **默认 0.6**；支持分总分区间 [0,1]【一手-文档】 | — |

### 1.3 架构指南口径

- **Google Cloud 架构中心**（docs.cloud.google.com/architecture/rag-capable-gen-ai-app-using-vertex-ai）：RAG 系统划分为**数据摄取 / 服务（检索+生成）/ 质量评估**三个子系统，评估是架构一等公民（"An evaluation system is critical... LLM outputs are probabilistic and can be wrong"）；同族还有 Vector Search / AlloyDB / Cloud SQL(GKE) / Spanner Graph(GraphRAG) / 私有连接 / CI-CD(Harness) 六个变体参考架构，形成「按数据底座选拓扑」的矩阵【一手-文档】。
- **Azure 架构中心 RAG 系列**（learn.microsoft.com/azure/architecture/ai-ml/guide/rag/rag-solution-design-and-evaluation-guide）：应用流 = 智能应用→编排器（Microsoft Agent Framework / Semantic Kernel / Azure AI Agent service / LangChain）→AI Search→打包 top N→LLM；数据管线 = chunk→enrich→embed→persist；明确「**标准 RAG 适合单索引单查场景，超出（多步推理/动态选源/运行时分解）才考虑 agentic RAG——agent 把检索当按需调用的工具**」。评测指标官方命名：**groundedness / completeness / utilization / relevancy**【一手-文档】。
- **Baseline Foundry Chat 参考架构**：App Gateway+WAF / App Service / Foundry Agent Service / AI Search / Cosmos DB(enterprise_memory)；明确警告**会话级越权（BOLA）**与「同项目所有 agent 共享托管身份→按访问模式拆项目」；该基线本身不做文档级 security trimming（提示可换成自建 API 前置 AI Search）【一手-文档】。
- **GPT-RAG → 已更名 Agent Landing Zone**（github.com/Azure/GPT-RAG，1186⭐，MIT，2026-10-15 仍在推送）：官方 README 声明 "GPT-RAG has evolved into Agent Landing Zone"，定位变为「企业 agent 落地区」（零信任网络 + IaC + Foundry），组件拆为 agent-app-ui / agent-app-orchestrator / agent-app-ingestion 三仓——**老的 GPT-RAG 四组件（INGEST/CHAT/ADMIN/SKETCH）资料已过时**【一手-gh api】。

## 2. 权限感知检索专题（托管服务如何补上开源的最大缺口）

开源结论〔dim07〕：五平台权限粒度全部止步知识库/工作区级，**文档级权限过滤需自研**。两家托管的做法：

**Google：文档级 ACL 原生内置（GA）。**
- 数据模型：Discovery Engine 的 Document 带 `acl_info.readers.principals`（`user_id`/`group_id` 列表），官方示例即「Space→Page 层级、不同 readers」的文档树【一手-文档】docs.cloud.google.com/generative-ai-app-builder/docs/reference/rpc/google.cloud.discoveryengine.v1。
- 身份侧：连接企业 IdP（Set up data source access control），GCS/BigQuery/SharePoint 连接器同步源系统 ACL；查询时带用户身份，**LLM 摘要/语义重排发生在 ACL 过滤之后**（先裁剪再增强）【一手-文档】。

**Microsoft：四条路线并行，官方文档直接对比**（learn.microsoft.com/azure/search/search-document-level-access-overview）【一手-文档】：
1. **Security filters（GA，API 无关）**：索引加 `Collection(Edm.String)` 安全字段（filterable=true、retrievable=false），查询用 `group_ids/any(g: search.in(g, 'id1,id2'))` 过滤；官方强调 `search.in` 比一串 `or eq` 快到**亚秒级**；本质是字符串匹配，"There's no authentication or authorization through the security principal"——身份来源、ACL 灌入、刷新全靠应用自己（azd 模板配 `manageacl.py` + Entra ID token claims `oids`/`groups` 字段）。
2. **POSIX-like ACL / RBAC scopes（preview）**：ADLS Gen2/Blob 的 ACL/RBAC 由 indexer 摄入索引，查询请求头带 `x-ms-query-source-authorization`（用户 Entra token），引擎提取 user/group/scope claims 与索引内权限元数据比对、查询时裁剪——官方明说这是**引擎内 enforcement，比应用侧 post-trim 快**（"Filtering inside the search pipeline is faster than loading larger result sets into your application"），并消除嵌套组解析/ACL 遍历的自研代码。
3. **SharePoint ACLs（preview）**：indexer 抽取 SharePoint 权限元数据做查询时检查。
4. **Purview 敏感度标签（preview）**：按标签+策略过滤，且标签元数据随 agentic retrieval 响应透出给 agent 使用。
- Foundry RAG 概念文档官方口径："**Apply access control at retrieval time**... you can use document-level access control with security filters"，另加两条：生产用 Entra ID 别用 API key、**检索内容当不可信输入防注入**【一手-文档】。

**对自建的启示**：托管服务把「ACL 随数据摄入索引 + 查询时带用户 token 引擎内过滤 + 增量同步权限变更」做成了产品闭环；自建等价物 = quivr 的 ACL 表 + ES/PG 过滤（dim07 唯一接近的样板）+ 自研权限同步管道。注意 Azure 原生 ACL 三路线全是 preview（GA 的只有字符串 security filter），选型时按此计风险。

## 3. 与开源源码结论互证清单

| # | 开源结论（dim 引用） | 厂商证据 | 判定 |
|---|---|---|---|
| 1 | 混合检索+rerank 是标准配方〔dim04〕 | Azure 官方 BEIR benchmark：NDCG@10 = BM25 40.6 / 纯向量(ada-002) 45.0 / hybrid 48.4 / **hybrid+semantic ranker 50.0**；官方定性 "hybrid retrieval with semantic ranker offers significant benefits"【转述-微软博客原文转载】 | **一致**（且给出量化背书：hybrid 比纯向量 +3.4 点，+rerank 再 +1.6 点） |
| 2 | RRF k=60/61 免调参默认〔dim04：llama_index 60、haystack 61〕 | Azure RRF k=60 固定常量，官方引用同源实验结论 | **一致**（k=60 是跨实现行业默认；Azure 不开放调 k，另给向量权重乘子） |
| 3 | 文档级权限全军覆没需自研〔dim07〕 | Google 原生 GA、Azure 四路线（1 GA + 3 preview） | **开源没做到**——恰是托管服务的核心卖点；自建必须补：ACL 随索引存储、查询时引擎内过滤（勿 post-trim）、权限增量同步 |
| 4 | 评测以 faithfulness/groundedness 为纲〔dim08：ragas faithfulness = 陈述分解+NLI〕 | Azure 官方指标 groundedness/completeness/utilization/relevancy；Google **Check Grounding API 产品化**：claim 级打分（每句=一个 claim，**partial entailment 判失败**，比 ragas 更严）、支持分 [0,1]、引用阈值默认 0.6、平均 <500ms 可在线调用 | **一致且强化**：厂商把开源库的离线指标做成在线 API；Google 严格口径（部分蕴含=不支持）值得抄进自建 judge prompt |
| 5 | Agentic RAG 别神化，80% 场景固定管线〔dim06〕 | Azure 架构中心同款口径（单索引单查用标准 RAG，多步/动态选源才 agentic）；agentic retrieval 官方明言 "adds latency... handles query complexity that a single query can't" | **一致**（两家都把 agentic 检索做进引擎但都标注延迟代价） |
| 6 | 分块：ragflow 领域模板〔dim04〕、解析是生死线〔dim02〕 | Google 给数字（默认 1024/256，实验 100-600）且官方推荐 LLM 增强分块并公布增益（摘要 +12.9%、问题式 +15-20%、组合 +27-33%）；Azure 给方法学（结构度→策略矩阵，含 GraphRAG 分块引用 microsoft/graphrag） | **方向一致，颗粒度分歧**：Google 敢给默认值+实验数字，微软只给框架——自建可锚 Google 数字起步，但两家都强调必须按语料实验 |
| 7 | 线性加权（ragflow 0.7/0.3）vs RRF 两流派〔dim04〕 | Azure 只走 RRF（+向量权重乘子），无分数级加权模式 | **部分分歧**：托管侧押注 RRF 免调参路线；ragflow 式可解释权重旋钮是自建特色，两派各自成立 |
| 8 | 引用溯源是信任工程〔dim04/08：ragflow 双机制最完整〕 | Azure agentic retrieval 返回 source references + activity log；Google check grounding 返回带引用端点的 cited chunks | **一致**（厂商把引用做成 API 结构化字段，含执行过程日志——比开源普遍做的更进一层） |

## 4. 证据与存疑清单

**一手-文档（关键引文均核过原文）**：
- Azure：hybrid-search-ranking（RRF k=60）、semantic-search-overview（top50/2048 token/0-4 分）、agentic-retrieval-overview、search-document-level-access-overview（四路线）、search-security-trimming-for-azure-search（search.in 亚秒）、foundry/concepts/retrieval-augmented-generation（RAG vs 微调）、architecture/ai-ml/guide/rag/*（设计指南+切分）、baseline-microsoft-foundry-chat、developer/python/get-started-app-chat-document-security-trim（oids/groups）
- Google：docs.cloud.google.com/gemini-enterprise-agent-platform/build/rag-engine/fine-tune-rag-transformations（1024/256、lambda、LLM 转换增益）、generative-ai-app-builder/docs/check-grounding（0.6 阈值、claim 级、partial entailment）、docs/reference/rpc/google.cloud.discoveryengine.v1（acl_info）、architecture/rag-capable-gen-ai-app-using-vertex-ai（三子系统、cosine 阈值）
- gh api：Azure/GPT-RAG 元数据 + README（更名 Agent Landing Zone）
- 数字基准：2023-09 BEIR（BM25 40.6/向量 45.0/hybrid 48.4/hybrid+semantic 50.0，512 token/25% overlap）与 2024-11 更新（NDCG@3 均值 46.1→55.9，nq 43.5→61.7；semantic ranker v2 41.8→43.5）——来源为微软官方博客（techcommunity.microsoft.com 403，经 Argon Systems 官方转载核对 2023 数字、2024 数字经 web_reader 直读原文），**标注【转述-微软原文】**。

**存疑/未核实（❌⚠️）**：
1. ⚠️ Vertex AI Search "high retrieval" 特性：generative-ai-app-builder 文档导航中存在该页，但三种方式抓取均失败（超时/500），具体 spec 参数与效果数字未核实。
2. ⚠️ Google 独立《RAG Best Practices 白皮书》未能定位原文（cloud.google.com/blog 网络受限），本报告以 RAG Engine 官方文档 + 架构中心为替代一手来源；社区流传的 "500-1000 token" 说法未经 Google 原文核实，不予采信。
3. ⚠️ Vertex AI Search 混合检索的 blend/boost 具体算法参数未单独抓取（本轮聚焦 RAG Engine 与 ACL）。
4. ⚠️ Azure 原生文档级 ACL 依赖 2025-11-01/2026-08-01-preview API，GA 进度以 whats-new 页为准（本轮检索时点为 preview）；`ingestionPermissionOptions` 与 `assetStore`/图片服务互斥是已知限制。
5. ❌ 两家均未公布 RRF 各路召回窗口等内部参数（Azure maxTextRecallSize=1000 可配但混合两路的各自 top 无官方推荐组合）。
6. 备注：Vertex AI Search→Agent Search、RAG Engine→Gemini Data/Gemini Enterprise Agent Platform、GPT-RAG→Agent Landing Zone 三处更名均为 2025-2026 年发生，网上旧名资料大面积过期（与 dim01「大重写周期」结论同构）。
