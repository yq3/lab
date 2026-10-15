# 企业级 RAG 系统/Agent 搭建调研报告

> **调研问题**：要搭建一个企业级 RAG agent/系统（私有化、可治理、可评测、中文为主），业界开源方案在数据接入→文档解析→切分索引→检索重排→生成→评测可观测→权限治理全链路分别做到了什么程度、怎么实现、怎么选型组装。
> **方法**：六层对象（5 平台 + 3 框架 + 2 GraphRAG + 3 解析器 + 3 向量库 + 2 评测库，另有 Java 生态 3 仓对照）× 九个构建块维度，全部源码级对码（15 仓新克隆 + 7 仓复用，基线见 [README.md](./README.md)）。证据三级标注，结论可溯源到 `~/develop/opensource/<repo>/路径#符号`。**补充轮（2026-10-15）**：厂商第一方最佳实践两路网络级调研（OpenAI/Anthropic〔dim10a〕、Google/Microsoft〔dim10b〕，证据等级【一手-文档/一手-源码/转述】），用于与开源结论互证。
> **过程文档**：九份维度深挖 + 两份厂商补充在 [dimensions/](./dimensions/)，本文是综合层——每个结论标注来源维度（如〔dim04〕）。

---

## 0. TL;DR：十句话结论

1. **开源 RAG 正处于大重写周期**：ragflow 已整体重写为 Go（Python 源码 2026-09-28 删除）、quivr 2026-09-03 从 orphan 分支推倒重写（现仅 5 周龄、自评别上生产）、MinerU 换代 4.0 全新架构、docling 模型阵容全换、haystack 把 cross-encoder 移出 core、dify agent_v2 反向取消「知识库挂 agent 工具」。**2025 年及之前的网上资料（含大量教程）对这批仓库大面积失效，一切结论必须对码当前基线。**
2. **五家平台共同验证了同一条企业 RAG 骨架**：同步 REST 只做控制面，解析/切分/嵌入/入库全部下异步任务系统，任务态落关系库；重活异步化 + 索引可重建（PG/对象存储为真相源，向量索引只是投影）是两条第一性原则。〔dim01〕
3. **文档级权限全军覆没**：五个平台的权限粒度全部止步于知识库/工作区/corpus 级（ragflow 到 dataset、dify 到 dataset、anything-llm 到 workspace、quivr 到 corpus、kotaemon 无），「谁能看到哪份文档并在检索结果里过滤」需要自研——这是自建系统最大的必答题。〔dim07〕
4. **中文混合检索的引擎分野**：要「一个引擎同时中文 BM25 + 向量」，现成可用的是 ES（应用层预分词，ragflow 路线）/ Infinity / milvus（内置 jieba）；qdrant 的服务端 BM25 稀疏向量只按空白切分，中文整句成 token 不可用（坑）；pgvector 全靠自组装。〔dim03〕
5. **检索层标准配方已经收敛**：BM25+向量双路召回（召回窗口给足）→ RRF 或线性加权融合（ragflow 验证过的锚点：关键词 0.7 / 向量 0.3）→ cross-encoder 重排（分数归一 [0,1]、喂原文不喂分词文本）→ 引用溯源（ragflow 双机制最完整）。查询变换首选多查询扩展和 LLM 关键词增强，HyDE 慎用。〔dim04〕
6. **解析层是中文场景生死线，双服务拓扑是答案**：MinerU 4.0 做扫描件/复杂 PDF 主力（中文 OCR 一等公民、公式表格标配、basic 档 0.8GB CPU 可跑），docling 做原生 PDF/Office/HTML（格式面最宽、结构输出最完整）；ragflow Go 版自己就示范了「自研轻量 + 外挂 MinerU/docling 重炮」的拓扑。**模型权重 license 全线未核实（HF 不可达），采购前必须逐卡确认——这是本次调研的最大遗留风险。**〔dim02〕
7. **GraphRAG 是可选项不是必选项**：先过「四问」（全局性问题占比 >10-20%？语料稳定？预算 3-10 倍？图库运维？）；要上，LightRAG mix 模式是从现有向量 RAG 渐进升级的最平滑路径（KG+向量同预算融合），微软 graphrag 只在「全局主题问题」上有不可替代性（社区报告 map-reduce），代价是索引成本 500-1500+ LLM 调用/MB 且增量不重聚类。〔dim05〕
8. **Agentic RAG 别神化**：企业知识问答 80% 场景固定管线（retrieve→rerank→generate）就是工业默认；agent 循环留给多信源/多跳/自判信息充分的场景。经典范式（CRAG/self-RAG/adaptive）的官方实现只剩 langgraph（已归档示例）和 llama_index（吸收进 core）两家；工程件最全的是 haystack 的 PipelineTool + Agent（state_schema/hooks/上下文压缩）。〔dim06〕
9. **评测组合定型**：ragas（评测计算器：faithfulness/answer_relevancy/context 指标 + 知识图谱合成测试集）+ deepeval（pytest 门禁 + 自带 ragas 适配器 + OTel tracing 在线抽样评测）。中文场景两库都没有开箱 judge prompt，上线前必须人工校准 judge 与人的一致性。〔dim08〕
10. **Java 团队能搭主链**：langchain4j 的五段式检索增强管线（路由/重排/RRF 全有 + 本地 ONNX rerank）明显强于 spring-ai（无 rerank 抽象、无混合检索）；边界划法 = Java 主管线 + Python 解析微服务（MinerU/docling）+ Python 评测脚本。〔dim09〕

**厂商互证增补（补充轮 2026-10-15，dim10a/10b）**：

11. **开源侧的核心配方全部拿到厂商量化背书**：Azure 官方 BEIR 实测 NDCG@10 = BM25 40.6 / 纯向量 45.0 / 混合 48.4 / 混合+semantic ranker 50.3；Anthropic Contextual Retrieval 数字链：上下文化嵌入 -35% → +contextual BM25 -49% → +Cohere Rerank **-67%**（top-20 失败率 5.7%→1.9%，一次性成本 $1.02/百万文档 token，靠 prompt caching 撑住）。**钱优先花在「索引侧补语境 + 混合 + 重排」三件已验证的事上**，别急着上花哨的分块图算法——两家厂商都没把父子块/句子窗口当核心武器。
12. **RRF k=60 是跨实现行业默认**（Azure 固定 k=60 + llama_index 60 + haystack 61）；但托管侧只走 RRF，ragflow 式 0.7/0.3 可解释加权是自建特色，两派各自成立。Google 敢给默认数字（chunk 1024/overlap 256，实验区间 100-600；LLM 增强分块官方增益：摘要 +12.9%、问题式 +15-20%、组合 +27-33%），可作自建起步锚点。
13. **托管服务对开源的最大降维打击恰是文档级权限**（正中 dim07 缺口）：Google 文档级 ACL 原生 GA（`acl_info` 随索引摄入 + 查询时用户身份过滤，LLM 增强发生在 ACL 过滤之后）；Azure 四路线（security filter GA + 引擎内 Entra token 比对等三条 preview）。自建等价模式可抄：**ACL 随索引摄入 + 查询时引擎内过滤（勿 post-trim）+ 权限增量同步**。另外评测被产品化（Google Check Grounding 在线 groundedness 打分，partial entailment 判失败比 ragas 严格）、引用细到字符区间（OpenAI annotations）——都是开源该追的方向。

---

## 1. 背景与方法

- 委托问题：搭建企业级 RAG agent/系统。企业级四要素取：**私有化可部署、权限可治理、质量可评测、架构可演进**（agentic 形态作为演进方向而非前提）。
- 对象圈定与核验（Phase 0，gh api 实测 29 仓）：发现 3 处迁移（quivr→The-Vibe-Company、ragas→vibrantlabsai、privateGPT→zylon-ai）、3 处归档（Verba/Cognita/vanna），全部排除或降级为元数据级；15 仓新克隆（镜像加速，全量无断流）。
- 九个维度全部源码级对码，分维度报告即过程档案；本文负责合成：参考架构、路线选择、分场景技术栈、实施蓝图、风险清单。
- 上游衔接：agent-framework 轮（17 框架）、agent-oss 轮（18 产品）、agent-persistence 轮（25 仓存储）覆盖了 dify/llama_index/langgraph/spring-ai/langchain4j 的框架级与存储级结论，本轮只补 RAG 视角。

## 2. 时效性警报：大重写周期（本轮第一发现)

先说调研本身的发现：**这批仓库的「现在」与大众认知差距极大**。

| 仓库 | 大众认知 | 当前基线实况 | 证据 |
|---|---|---|---|
| ragflow | Python + deepdoc 深度解析 | Go 单二进制 4 角色，Python 源码 2026-09-28 整体删除；deepdoc 以 ONNX Runtime Go 原生重建；检索逻辑全在 `internal/` | 〔dim01/02/04〕git log 670e68872 |
| quivr | Python「第二大脑」RAG agent | 2026-09-03 orphan 分支重写为 Go「内容流搜索与监测引擎」，无 LLM agent 循环，自评 "evaluation stage, do not run in production" | 〔dim01/06〕双 root 实证 |
| MinerU | magic_pdf 时代管线 | 4.0 全新架构（backend/model/parser 分层 + docvortex 底层），effort 四档（flash→xhigh），high+ 加 1.2B VLM | 〔dim02〕 |
| docling | DocLayNet YOLO + TableFormer | 布局默认 Heron（YOLO 已弃用），公式走 Granite VLM，VlmPipeline 内置 MinerU2.5/GLM-OCR/Nemotron-Parse 等 10+ 预设（已成 VLM 解析聚合器） | 〔dim02〕 |
| haystack 2.x | core 带 TransformersSimilarityRanker | cross-encoder 重排已移出 core（只剩 LLM/MetaField 等 4 个 ranker），网上教程与现状不符 | 〔dim04〕 |
| dify | agent 可挂知识库工具 | agent_v2 对 DATASET_RETRIEVAL 工具类型直接 raise（「知识路径与 agent 路径分离」的产品决策）；workflow 引擎已外置为独立包 graphon | 〔dim06〕 |
| langgraph | examples 里有 CRAG/self-RAG | 全部标注 archived（迁往 LangChain 文档站），不再随库演进 | 〔dim06〕 |
| spring-ai-alibaba | DashScope RAG 增强包 | 已转型 Agentic/Graph 编排框架，DashScope 与 RerankModel 外迁 extensions 仓；GraphRAG 宣称在主仓全历史零命中 | 〔dim09〕 |
| Google 全家（补充轮） | Vertex AI Search / RAG Engine / GPT-RAG 旧名资料 | 三处更名：Vertex AI Search→**Agent Search**（Gemini Enterprise Agent Platform）、RAG Engine→**Gemini Data**、Azure GPT-RAG→**Agent Landing Zone**（老四组件架构作废，gh api 核实 MIT/1186⭐仍活跃） | 〔dim10b〕 |

**对选型的直接含义**：(a) 选型判断必须锚定本次调研基线（HEAD 见 README），半年后需重核；(b) ragflow 的 Go 版仍有迁移回归项（use_kg 图检索直接 Warn 跳过未实现），Python 时代能力 ≠ 现有能力；(c) star 数与「能抄的代码量」无关（quivr 39.6k⭐ 但 5 周前清零重来）。

## 3. 参考架构：从五家平台提炼的企业 RAG 标准拓扑

```
                    ┌─────────────── 控制面（同步 REST）───────────────┐
                    │  文档上传/状态查询/检索问答 API/管理台             │
                    └──────┬──────────────────────────────┬────────────┘
                           │ 写任务表+发队列消息            │ 检索请求
                    ┌──────▼──────────────┐      ┌────────▼──────────────────┐
  文件对象存储 ◄─── │  摄取 worker 池      │      │  检索服务（同步）          │
  (S3/MinIO,       │  解析→切分→嵌入→索引 │      │  双路召回→融合→rerank      │
   canonical真相)  │  心跳+租约+断点续跑   │      │  →权限过滤→prompt→引用     │
                    └──────┬──────────────┘      └────────┬──────────────────┘
                           │                                │
              ┌────────────▼───────────────┐   ┌───────────▼────────────────┐
              │ 文档/向量引擎（可同库）       │   │ LLM/嵌入/rerank 模型接入    │
              │ ES/Infinity: BM25+KNN 同库  │   │ (运行时可插拔/租户级)       │
              │ 或 milvus(jieba) / qdrant   │   └────────────────────────────┘
              │ 或 pgvector(+自拼 BM25)     │   ┌────────────────────────────┐
              └────────────────────────────┘   │ 横切：元数据库(PG/MySQL)、  │
                                              │ 任务队列、评测、tracing、    │
                                              │ 权限 ACL、审计、配额        │
                                              └────────────────────────────┘
```

各层来源与理由（均为五家对码结论）：

1. **控制面/数据面分离**：五家无一例外——dify（REST+Celery）、ragflow（gin API + NATS JetStream worker）、quivr（api/worker + Temporal）、anything-llm（server+collector 子进程）、kotaemon（Gradio queue）。同步链路里绝不跑解析和嵌入。〔dim01〕
2. **任务工程化**（ragflow 样板）：worker 心跳 + 任务租约 + 关系库调度行 poll + 队列 notify 混合消费 + 断点续跑；dify 的多队列分池（dataset/priority_dataset）解决租户插队公平性。〔dim01〕
3. **canonical 真相与索引投影分离**（quivr 样板）：PG+对象存储是真相，搜索索引可随时重建；嵌入模型钉版本防向量空间漂移。文档会改、模型会换，这条是救命设计。〔dim01〕
4. **向量+全文同库 vs 分库**：ragflow/quivr 用同库引擎（ES/Infinity/Weaviate）省掉双写一致性；dify 是分库反面参照（30+ 向量库 + 独立 jieba 关键字索引，关键字索引只有 jieba 一种实现）。中文场景同库是更优解（见 §5.2）。〔dim01/03〕
5. **模型接入运行时可插拔**（dify 样板，plugin_daemon 租户级热装）；ragflow Go 版退化为编译期 factory switch（加 provider 要发版）是反面教材。〔dim01〕
6. **进程隔离最小实现**（anything-llm 样板）：本地跑嵌入/解析模型时放可牺牲子进程（OOM 只杀 worker），起步阶段比引入完整队列轻一个量级。〔dim01〕

## 4. 三条建设路线与决策依据

### 路线 A：开箱平台（自建最少）

| 平台 | 什么时候选它 | 关键边界 |
|---|---|---|
| **ragflow**（Apache-2.0） | 要「RAG 专项能力最强」：深度解析（deepdoc Go 原生 + MinerU/docling 外挂）、12 种领域 chunk 模板、句级引用溯源、混合检索权重可调、多租户 KB 级权限策略引擎（五家最强） | Go 重写期文档脱节；use_kg 未实现；SSO/审计/配额是 EE 空壳（CE 的 OAuth handler 全部 not implemented）；模型 key 明文存库 |
| **dify**（修改版 Apache） | 要「LLM 应用平台而非纯 RAG」：可视化 workflow 编排、租户体系、插件生态、多模型接入最成熟 | RAG 检索层偏浅（无查询变换、无 RRF、扫描件无解）；「企业级」大半在闭源 enterprise 服务墙外；**telemetry 默认开启上报 otel.dify.ai**；多租户对外运营需商业授权 |
| **anything-llm**（MIT） | 要「最快起步/最小部署」：单容器、SQLite+LanceDB、可 air-gap、license 最干净 | 无混合检索、无 rerank 主链、无任务持久化；文档量上千后天花板明显 |
| kotaemon（Apache-2.0） | 只当「RAG 算法试验台」（GraphRAG/LightRAG/多 rerank 开关最全） | 单进程、动态建表、2026-05 后停滞；不进生产 |
| quivr V2（MIT） | 只当「检索引擎/MCP 检索后端」参考（可重建索引观、审计触发器设计值得抄） | 5 周龄 v0、无 LLM 循环、无中文优化；不进生产 |

### 路线 B：框架自建（代码优先）

- **llama_index**：RAG 检索策略全家桶最全（查询变换/融合/重排/父子块/句子窗口都是 core 模块，本地 rerank 选项最多），适合「少写编排、多复用检索策略」。〔dim04/06〕
- **haystack 2.x**：工程件最扎实（Pipeline 组件化、PipelineTool 自动 schema、Agent 状态/hooks/上下文压缩、evaluators 组件），适合「企业级严谨工程 + 自搭范式」；注意 cross-encoder 已移社区 hub。〔dim04/06〕
- **langgraph**：编排控制力最强（StateGraph+条件边+Postgres checkpointer，可恢复长流程），但 agentic RAG 素材全在归档示例。〔dim06〕
- Java 侧见 §8。

### 路线 C：平台骨架 + 自建增强（多数企业的实际最优解）

用 ragflow/dify 当骨架拿到「上传→解析→索引→问答」的全链路与任务系统，然后**把治理缺口全部自研补齐**（文档级 ACL、SSO 网关、查询审计、配额），必要时把检索层替换/包一层自研服务。判断依据：治理自研量是刚性的（§7），平台不会替你做；而解析/索引/检索层自研的边际收益低于直接用现成件。

**决策口诀**：验证性 POC → anything-llm；生产知识问答、文档重（扫描件/表格多）→ ragflow（+自研治理层）；要 workflow 化多应用 → dify（内部单租户用、关 telemetry）；检索策略要极致定制/科研 → llama_index 或 haystack 自建；Java 主链 → §8。

## 5. 构建块逐层结论

### 5.1 解析与切分（dim02）

- **双服务拓扑**：Office/HTML/原生 PDF → docling（docling-serve，REST `/v1/convert/source`）；扫描 PDF/图片/公式重 → MinerU 4.0（api_server，medium 起步、重要文档 high 档；basic 档 0.8GB 纯 CPU）。ragflow Go 版的 `parse_method` 分发（deepdoc/mineru/docling/paddleocr/somark/tcadp/monkeyocr 七后端）就是这个拓扑的现成设计参考。
- **切分两层分工**：解析库做结构感知（docling HybridChunker 按文档树、MinerU content_list 天然块边界），平台侧只做 token 上限微调；**正确姿势是拿结构输出（标题层级/表格/页码）指导切分，而不是 markdown 盲切**——dify（分隔符含"。"的递归切分）是「解析切分都最薄」的反例，扫描件在默认配置下无解。
- 避坑：unstructured 模型推理在闭源包、中文仅 tesseract，不作中文主力；MinerU Apache-2.0 有附加条款（MAU>1 亿或月收>2000 万美元需授权 + 在线服务署名义务）。
- **未闭环风险**：模型权重 license 全线未核实（HF 网络不可达；IBM 系有 CC-BY-NC 历史先例），商用前逐卡确认。

### 5.2 索引与向量库（dim03）

| 场景 | 推荐 | 理由 |
|---|---|---|
| 中文混合检索、不想拼两个引擎 | ES（应用层预分词，ragflow 路线）/ Infinity / milvus 2.5+（BM25 Function + 内置 jieba） | 一个引擎同做中文 BM25 + KNN；milvus 还有 rrf/weighted/decay/model 四类融合在库内 |
| 已有 PG、规模 < 千万 chunk | pgvector + SQL WHERE + iterative_scan | 零新增组件、事务一致；混合检索自拼（tsvector+中文分词扩展+应用层 RRF） |
| 多租户 SaaS 单 collection | qdrant（tenant payload 索引）或 milvus（partition key + isolation） | 官方主推姿势；**qdrant 的 BM25 稀疏向量按空白切分，中文不可用**（payload 全文索引路径与 Query API 融合路不互通） |
| 嵌入式/单机轻量 | LanceDB / chroma / milvus-lite / qdrant 单二进制 | anything-llm（LanceDB）同款 |

- **平台 schema 两流派**：dify = metadata-as-JSON-blob（过滤走 JSON 路径）；ragflow = 强类型字段（`q_<dim>_vec`/`content_with_weight`/`*_kwd` 后缀编码引擎类型）。chunk 正文存引擎内（dify/anything-llm/ragflow）还是 docstore 分离（kotaemon 唯一）——后者换向量库零搬迁，代价是回表。
- 融合算法在库内程度：milvus（rerank 四类 + 外接 8 家 rerank provider）> qdrant（加权 RRF k=2 / DBSF）> pgvector（全 DIY）。注意 qdrant 与 milvus 的 RRF 默认 k 差 30 倍（2 vs 60），调参语义不同。

### 5.3 检索与重排（dim04）

推荐配方（五家对码合成，细节见 dim04 §9）：

1. 召回：BM25+kNN 双路，召回窗口给足（ragflow 口径：knn_top_k 1024、rerank 候选 64）；不要在召回期用用户阈值过滤向量分（dify #35233 教训：分数不同尺度过早过滤误杀）。
2. 融合：默认 RRF（k=60/61）免调参；要「可解释权重旋钮」用线性加权（`0.7·关键词 + 0.3·向量` 是 ragflow 验证过的锚点），但两路分数必须同尺度（重算 TF-IDF/token 相似度，不能拿引擎 BM25 原始分硬混）。**厂商量化背书（补充轮）**：Azure BEIR 实测混合比纯向量 NDCG@10 +3.4、再加重排 +1.6；RRF k=60 是 Azure 固定常量，与 llama_index(60)/haystack(61) 跨实现一致。〔dim10b〕
2b. **索引侧补语境（Contextual Retrieval，预算允许时强烈建议）**：LLM 为每 chunk 生成 50-100 token 定位上下文前置后再嵌入/入 BM25 索引，Anthropic 实测与混合+rerank 叠加共降检索失败率 67%，一次性成本 $1.02/百万文档 token（关键前提是 prompt caching 类经济学，自建要对缓存命中率算总账）；与「查询侧变换」是两条互补路线（OpenAI 押查询侧 rewrite_query、Anthropic 押索引侧补语境）。〔dim10a〕
3. 重排：有预算 → Cohere/Jina/BGE API；私有化 → llama_index 进程内 sbert/BGE（flag-embedding）、自托管 TEI 端点（kotaemon/ragflow 同款）或 langchain4j ONNX 本地（Java 侧）。分数进融合公式前归一 [0,1]（ragflow min-max/clamp 双分支值得直接抄）；cross-encoder 喂 chunk 原文不喂分词文本。
4. 切分配合：递归 token（256-512）打底；高价值场景加父子块（三家同思路：ragflow mom_id / dify parent-child / llama_index AutoMerging）；**ragflow 字段级权重（title×2 / important_kwd×5 / question_tks×6 进重排）是低成本高收益的独门技巧**。
5. 引用溯源：ragflow 双机制（embedding 句级归因兜底 + agentic 确定性 chunk_id 提取）或 kotaemon START/END_PHRASE 协议（LLM 声明+程序校验）；纯 prompt 引用只适合 demo。
6. 查询变换性价比序：多查询扩展 > LLM 关键词增强（中文尤其有效，ragflow）> HyDE（模型依赖重）。
7. 别指望：语义查询缓存（五家都没有，需外接）、haystack core 的 cross-encoder（已移 hub）、ragflow Go 版 KG 检索（未实现）。

### 5.4 GraphRAG（dim05）

- 判断四问：全局性问题占比 >10-20%？语料稳定（报告/规范/案例库 vs 频繁改写 wiki）？预算（graphrag 索引 500-1500+ LLM 调用/MB ≈ 纯向量 3-10 倍；LightRAG 210-450 ≈ 2-4 倍）？愿意运维图库？
- **LightRAG mix 模式**是渐进最优解：一次索引同时产出 KG + chunk 向量，查询时同预算轮询融合（KG 检索失败向量结果仍在场）；存储可全 PG 一把梭；增量即日常操作。
- 微软 graphrag 的不可替代性 = global search（社区报告 map-reduce 答全局主题）与 drift search（global 播种+local 迭代）；代价：无索引前成本预估器（只有事后统计）、增量只拼接不重聚类（社区边界退化，需定期全量重建）。
- 混用路径：KG 当副索引（kotaemon 模式：两套索引并存、检索结果合流、可灰度可回退）优于当唯一检索层。

### 5.5 Agentic RAG（dim06）

- **先做形态判断**：问答口径稳定/延迟成本敏感/要可评测 → 固定管线（80% 场景）；多信源/多跳分解/读后再检索/自判信息充分 → agent 循环。务实推荐「管线做骨架、局部嵌 agent」（dify question-classifier 分流式）。
- RAG-as-tool 实现深度排序：haystack PipelineTool（自动 schema 生成）> llama_index（RetrieverTool/QueryEngineTool + SubQuestion/MultiStep/FLARE 进 core）> langgraph（ToolNode，示例归档）> kotaemon DocSearchTool（教科书式工具描述写法）> dify（agent_v2 明确拒绝 dataset 工具，只有旧 Chat App 单库模式）。
- **quivr 的反向姿态值得注意**：自己不做 agent，把检索做成 MCP 工具服务器（list_corpora→search→read_record，带鉴权与精确溯源）——「agent 循环住在客户端」适合「已有 agent、缺高质量检索后端」的组合。
- reasoning 模型适配都停留在展示层（think 标签修复/渲染），无决策层适配——不用指望现成的。

### 5.6 评测与可观测（dim08）

- **离线**：ragas TestsetGenerator（知识图谱+persona+multi_hop 合成候选）→ 人工抽检修正如黄金集；指标组合：无参考先跑 faithfulness+answer_relevancy+ContextUtilization，有标注补 context_recall（NonLLM/ID-based 零 LLM 成本）+answer_correctness；检索侧 hit-rate/MRR 自算（两家平台都不带 IR 指标）。
- **门禁**：deepeval pytest 断言（assert_test+threshold）挂 CI；ragas 指标可经其内置适配器包进去。
- **在线**：trace（dify 原生接 Langfuse；自建用 ragas 导出端或 deepeval OTel @observe）+ 流量抽样 1-5% 跑 reference-free 指标 + 用户弱信号（点赞/标注命中）定期回灌评测集。
- **中文硬前提**：两库 judge prompt 全英文（ragas `adapt()` 运行时 LLM 翻译、deepeval community 模板未落地），上线前用 ~50 条人工双评验证 judge-人一致性后才可作门禁。**厂商参照（补充轮）**：Google 把 groundedness 做成在线 API（Check Grounding：claim 级打分、**partial entailment 判失败**（比 ragas 宽松判定更严）、引用阈值默认 0.6、<500ms）——自建 judge prompt 可抄其严格口径；评测必须分层（检索层 Recall@k/MRR 与响应层 faithfulness 分开）是两家厂商共同纪律。〔dim10a/10b〕
- 平台自带的都是「调试器」不是「评测系统」（dify hit testing/ragflow RetrievalTest 只返回 chunk 列表供人眼看）；ragflow 引用机制可当免费的在线幻觉检测锚点（引用了不存在的 ID = 幻觉证据）。

### 5.7 企业治理（dim07）

自研补齐清单（按优先级）：

1. **文档级 ACL + 检索期过滤**（最大缺口，五家全无）：ACL 表（doc→用户/组）+ chunk 带 doc_id 映射，**在返回给 LLM 组 prompt 之前过滤**（前置：把允许 doc_id 集合转成引擎 filter——milvus 标量过滤/qdrant payload/ES bool 都支持；后置：rerank 前过滤兜底）。**托管服务的成熟模式可照抄（补充轮）**：Google 的「ACL 随索引摄入（`acl_info.readers.principals`）+ 查询时带用户身份在引擎内过滤 + LLM 增强发生在过滤之后 + 权限增量同步」闭环；Azure 的 `search.in()` 亚秒级 security filter（GA）与 Entra token 引擎内比对（preview）——自建等价物 = ACL 冗余进检索索引字段 + 查询注入用户组过滤，勿在应用层 post-trim。〔dim10b〕
2. **协议级 SSO**：平台前加 OAuth2 proxy / Keycloak；只有 kotaemon 给了 OIDC 样板（gradiologin）。
3. **查询级审计**（谁/何时/查了什么/返回哪些来源）：dify dataset_queries + anything-llm event_logs 抄表结构，quivr 的 append-only 触发器 + SECURITY DEFINER 定长清理整体搬。
4. **配额与成本分摊**：只有 anything-llm 有每用户日限；按部门 token/存储配额需自建计量+拦截。
5. **凭据治理**：只有 dify 做了 RSA+AES 加密落库；统一走 KMS/secret manager。
6. **出墙体检**：dify（telemetry 默认开，`DISABLE_TELEMETRY=true` 第一件事）、anything-llm（PostHog 同理）；ragflow/quivr/kotaemon 干净。
7. **license 边界**：放心内用修改 = anything-llm/quivr（MIT）、ragflow/kotaemon（Apache-2.0）；dify 多租户对外运营需商业授权（内部单 workspace 自用不受限）；MinerU 附加条款见 §5.1。
- 附加安全面：上传校验（类型/大小）各平台有、病毒扫描全无、prompt injection 防护五家全无（要自研输入侧防护）、quivr 的 netguard（拨号期 SSRF 防护）与 connector 凭据密封值得抄。

## 6. 推荐技术栈（分场景）

### 场景一：中小规模（<100 万 chunk、内部数百用户、中文文档为主）

- **骨架**：ragflow CE（Apache-2.0）单集群部署（Go 单二进制 + MySQL + MinIO + ES/Infinity + NATS，按需 TEI）
- **解析**：内置 deepdoc 起步；扫描件重时外挂 MinerU api_server（ragflow 原生支持 parse_method=mineru）
- **检索**：默认混合检索（关键词 0.7/向量 0.3 起步调参）+ TEI 自托管 BGE rerank
- **自研治理层**：前置 Keycloak/OAuth2 proxy（SSO）+ 文档级 ACL 服务（检索前置过滤）+ 审计表
- **评测**：ragas 离线黄金集 + deepeval CI 门禁（中文 prompt 先校准）

### 场景二：已有 Java 技术栈与 PG/中间件体系的企业

- **主管线全 Java**：spring-ai（ChatClient+Advisor+Micrometer 观测，21 家向量库）为底 + langchain4j 检索层组件（五段式 Augmentor、LanguageModelQueryRouter 多库路由、ReciprocalRankFuser、**ONNX 本地 BGE rerank**——spring-ai 无 rerank 是硬缺口，langchain4j 补上）
- **向量库**：已用 Milvus → milvus-v2 的 BM25 hybrid（jieba 中文原生）；已用 PG → pgvector+自拼混合
- **Python 侧保留两个小服务**：MinerU/docling 解析服务（输出结构化 Markdown/JSON，Java 消费）+ ragas/deepeval 评测脚本
- spring-ai-alibaba 只在需要其 Graph 编排/Admin 平台时引入（RAG 增值已外迁，GraphRAG 宣称未随主仓存活）

### 场景三：多租户对外服务 / 检索策略极致定制

- **自建检索服务**（haystack 或 llama_index 底座）+ 引擎选 milvus（partition key 物理隔离）或 qdrant（tenant payload；中文 BM25 走 payload 全文索引路径）
- 编排：固定管线为主 + agent 循环局部嵌入（CRAG 式自查档位：检索质量分低时才触发重写/再检索）
- 索引可重建架构（quivr 观）：PG+S3 canonical、索引投影、嵌入模型钉版本

## 7. 实施蓝图（MVP → 生产 → 进阶）

**MVP（≈4-6 周，验证解析与检索质量）**
1. 部署 ragflow CE 或 anything-llm（或 Java: spring-ai+pgvector+langchain4j rerank）
2. 解析双服务拓扑（MinerU api_server + docling-serve），先拿 50-100 份真实企业文档（含扫描件/复杂表格）测解析质量——**解析质量不达标，后面全部白搭**
3. 混合检索 + rerank 调参；建 50-100 条人工黄金问答集（含中文）跑 ragas 基线
4. 验收口径：解析抽检（表格/公式/页码正确率）、context_recall、faithfulness、句级引用可用

**生产化（+8-12 周，治理与可靠性）**
1. 文档级 ACL（检索前置过滤）+ SSO 网关 + 查询审计（append-only）+ 配额
2. 任务可靠性：摄取 worker 心跳/租约/断点续跑；索引重建 runbook（换嵌入模型/换引擎）
3. CI 评测门禁（deepeval+黄金集，变更防护）+ 在线 tracing（Langfuse/自建 OTel）+ 抽样在线评测
4. 出墙体检（telemetry 全关）、凭据进 KMS、上传校验与病毒扫描、输入侧 injection 防护
5. 验收口径：权限越权测试全绿、评测门禁卡住回归、审计可回放

**进阶（按需）**
1. GraphRAG：先 LightRAG mix 副索引灰度（kotaemon 模式），全局问答需求实锤再评估微软版
2. Agentic：question-classifier 式分流（简单问题走管线、复杂问题进 agent 节点/循环）；或检索 MCP 工具化（quivr 模式）接入已有 agent
3. 多模态（图片/图表理解）：docling VlmPipeline 聚合器路线（MinerU2.5/GLM-OCR 预设）

## 8. Java 团队专属结论（dim09 摘要）

- **三档差距清单**：Java 能做（标准向量 RAG 主管线/metadata filter/多路召回融合重排/观测测试基建/Agentic）；Java 要自己写（spring-ai 的 rerank、通用混合检索件、ETL 编排）；建议 Python 做（深度解析、评测、前沿检索技术跟进）。
- **框架选择**：检索层野心大 → langchain4j（ScoringModel 6 实现 + ReRankingContentAggregator + RRF 是硬差距）；重度 Spring 化要无缝 → spring-ai（Micrometer/testcontainers 体验最佳）+ 自写/外挂 rerank。两者可混用（Filter 模型不同需换算层）。
- rerank 最短路径：私有化 → ONNX 本地 cross-encoder（抄 langchain4j-onnx-scoring）；云上 → Cohere/Jina HTTP；国内 → DashScope rerank（spring-ai-alibaba extensions 仓）。

## 9. 宣称 vs 实现落差汇总（对码实锤）

| 宣称 | 实况 | 维度 |
|---|---|---|
| ragflow「enterprise-ready」 | CE 的 OAuth handler 全部 not implemented（`user_auth_ee.go`）；审计/配额全在 EE 空壳 | dim07 |
| dify「SSO/RBAC/审计」 | OSS 侧只是调闭源 dify-enterprise 的 HTTP 客户端；纯 OSS 拿不到 | dim07 |
| dify 开源自托管=数据不出门 | telemetry 默认开上报 otel.dify.ai | dim07 |
| anything-llm「Simple SSO」 | 是 API key 换 token 桥接，非协议级 SSO | dim07 |
| quivr「agent-first」 | Python 时代标签；Go 重写版无任何 LLM 调用 | dim06 |
| kotaemon 集成 GraphRAG | 微软通道绑旧版 parquet 表名，配 graphrag v3.x 预期不可用 | dim05 |
| spring-ai-alibaba GraphRAG 支持 | 主仓全历史 3250 commits 零命中 | dim09 |
| haystack 教程里的 TransformersSimilarityRanker | 已移出 core，须装社区 hub 组件 | dim04 |
| deepeval 多语言 community 模板 | 宣称存在、克隆中目录不存在 | dim08 |
| 「细粒度文档权限」（行业性） | 五平台全部 ❌（含部分闭源产品的话术） | dim07 |

## 10. 元数据级对象与排除记录

- **厂商第一方实践（补充轮，网络级非源码）**：OpenAI 把 RAG 收敛成托管黑盒（vector store 自动分块 800/400 + 内置 RRF 混合 + ranker + rewrite_query，$0.10/GB/天），其「小库不做 RAG」与 Anthropic 口径（<200k token 直接长上下文+缓存）构成有用的出口判断；Anthropic 只发方法学（Contextual Retrieval + Citations API 原语）；Google/微软托管服务代表企业级 RAG 天花板形态（原生 ACL、在线 grounding 评测、引擎内 agentic retrieval GA）。详见 dim10a/10b。
- **open-webui**（154k⭐）：LLM 前端网关，RAG 为外挂，知识库场景不如上述平台；**litellm**（61k⭐）：模型网关，支持 /rerank 端点，可作自建系统的模型接入层补充（与 dify plugin_daemon 同生态位）；**private-gpt/zylon**（57.6k⭐）：活跃但架构被 ragflow/dify 覆盖；**DocsGPT**（18.3k⭐，MIT）：宣称 air-gapped 全环境内跑，轻量备选；**khoj**（37.7k⭐）：AGPL-3.0，商用传染性强，排除；**Verba/Cognita/vanna 已归档**（2026-02~06）；**txtai**（13k⭐）：嵌入式一体化设计有参考价值（向量+图+SQL 融合数据库），未源码级核验。
- 模型层事实（生态通识，未源码级）：嵌入中文主流 BGE 系 / 多语 E5 系；rerank 主流 BGE-reranker 系（TEI/vLLM 可自托管）。

## 11. 风险与存疑登记（下一步动作）

1. **模型权重 license 未核实**（最高优先级）：docling Heron/Egret/Granite、MinerU2.5、InfiniFlow/deepdoc 的 HF 卡在本次网络环境不可达。商用前必须逐卡确认（IBM 系有 CC-BY-NC 历史先例）。→ 动作：HF 可达时补验并回填 dim02。
2. **基线时效**：ragflow Go 迁移未完成（AGENTS.md 有 pending 清单）、quivr 每周大变、dify rag_pipeline 新特性未稳。→ 动作：任何实施决策前重核 HEAD。
3. quivr-core（Python 旧库）独立仓去向未核实；dify enterprise 服务不可用时的降级行为未逐条追；milvus/qdrant 官方多租户建议阈值未在仓库内核实（引擎代码证据充分）。
4. 中文评测 judge 校准、ES 默认分析器中文效果、kotaemon hybrid 去重疑似 bug 等小项见各维度存疑清单。

## 12. 复核记录（2026-10-12，抽查 14 项回源码验证）

对 report 与维度文档引用的关键断言抽样回源码核对（grep/sed 定位行号与内容）：

| # | 断言 | 证据 | 结果 |
|---|---|---|---|
| 1 | ragflow 向量权重默认 0.3 | `ragflow/internal/entity/skill_search.go:52`（`default:0.3`） | ✅ 行号内容全中 |
| 2 | ragflow CE OAuth 全 stub | `internal/handler/user_auth_ee.go:26-38`（4 个 "not implemented"） | ✅ |
| 3 | ragflow use_kg 未实现 | `internal/service/dataset/search.go:324`（Warn 跳过） | ✅ |
| 4 | dify telemetry 默认开 | `api/configs/feature/__init__.py`（DISABLE_TELEMETRY default=False + otel.dify.ai endpoint） | ✅ |
| 5 | dify agent_v2 拒绝 dataset 工具 | `nodes/agent_v2/dify_tools_builder.py:368` | ✅ |
| 6 | milvus jieba 中文测试 | python 用例被 `@pytest.mark.skip`（unstable）；**Go 侧 Chinese_Jieba 用例是活测试** | ⚠️ 已修正 dim03 表述（原引 python 用例作主证据，降级为引擎实现+Go 活测试） |
| 7 | qdrant BM25 仅空白分词 | `lib/bm25/src/basic_tokenizer.rs`（`split_whitespace`） | ✅ |
| 8 | ragas faithfulness 链路 | `_faithfulness.py:34/73/218` 三类精确命中 | ✅ |
| 9 | llama_index RRF k=60 | `fusion_retriever.py:119`（注释引原论文） | ✅ |
| 10 | langchain4j ScoringModel/ONNX | 接口文件 + onnx-scoring 目录存在 | ✅ |
| 11 | docling Heron 默认布局 | `stage_model_specs.py:1012`（preset_id="layout_heron_default"，RT-DETR ResNet50） | ✅ |
| 12 | MinerU 中文 OCR 注册 | `model/registry.py:23-52`（PP-DocLayoutV2 / ch_PP-OCRv6_tiny_det.onnx / PP-FormulaNet） | ✅ |
| 13 | ragflow MinerU/docling 外挂桥 | `internal/parser/parser/pdf_parser_{mineru,docling}.go` 存在（复核时先因目录层级少列一层误判未命中，复查确认存在） | ✅ |
| 14 | quivr 审计 append-only | `migrations/20261006T0039Z_audit_events.sql:31-59`（双触发器 + prune SECURITY DEFINER） | ✅ |

结论：14 项抽查 13 项直接命中、1 项（milvus jieba 测试表述）已修正。总体证据质量可信。

**补充轮复核（2026-10-15，dim10a/10b 本地可核部分 4 项）**：

| # | 断言 | 证据 | 结果 |
|---|---|---|---|
| S1 | OpenAI cookbook「ranker uses hybrid search」原文 | `openai-cookbook/examples/File_Search_Responses.ipynb` grep 命中 "ranker which uses hybrid search" | ✅（10a 原引用路径多了一层目录，已修正为 examples/ 根） |
| S2 | 「search is better than fine-tuning」官方口径出处 | `examples/Question_answering_using_embeddings.ipynb` grep 命中原文 | ✅ |
| S3 | HyDE 教程存在 | `examples/vector_databases/chroma/hyde-with-chroma-and-openai.ipynb` | ✅ |
| S4 | cross-encoder 重排教程存在 | `examples/Search_reranking_with_cross-encoders.ipynb` | ✅ |

dim10b 为纯网络文档级（Azure/Google 文档不可本地核验），其关键数字（BEIR、k=60、Check Grounding 0.6）均带 URL 与引文标注，按【一手-文档/转述-微软原文】等级采信。

---

## 附录 A：维度文档导航

| 维度 | 文件 | 一句话结论 |
|---|---|---|
| 01 平台架构 | [01-platform-arch.md](./dimensions/01-platform-arch.md) | 五家重→轻光谱；异步任务骨架是共识；quivr/ragflow 重写考古 |
| 02 解析切分 | [02-ingestion-parsing.md](./dimensions/02-ingestion-parsing.md) | MinerU 4.0 + docling 双服务拓扑；权重 license 风险 |
| 03 索引向量库 | [03-index-vector-store.md](./dimensions/03-index-vector-store.md) | 中文 BM25 引擎分野；qdrant BM25 中文坑；平台 schema 两流派 |
| 04 检索重排 | [04-retrieval-rerank.md](./dimensions/04-retrieval-rerank.md) | 融合公式两流派；0.7/0.3 锚点；引用溯源双机制；推荐配方 |
| 05 GraphRAG | [05-graphrag.md](./dimensions/05-graphrag.md) | LightRAG mix 渐进路径；微软版增量缺陷；四问判断框架 |
| 06 Agentic RAG | [06-agentic-rag.md](./dimensions/06-agentic-rag.md) | 80% 固定管线；范式只剩两家；dify agent_v2 反向；quivr MCP 反转 |
| 07 企业治理 | [07-governance.md](./dimensions/07-governance.md) | 文档级权限 5/5 缺失；SSO 假象；自研补齐清单七条 |
| 08 评测可观测 | [08-eval-observability.md](./dimensions/08-eval-observability.md) | ragas+deepeval 组合；中文 judge 校准硬前提；平台只有调试器 |
| 09 Java 生态 | [09-java-ecosystem.md](./dimensions/09-java-ecosystem.md) | langchain4j 检索层胜出；Java 主管线 + Python 解析/评测边界 |
| 10a 厂商实践：OpenAI/Anthropic | [10a-vendor-openai-anthropic.md](./dimensions/10a-vendor-openai-anthropic.md) | 托管黑盒 vs 方法学；Contextual Retrieval 数字链（-67%）；索引侧 vs 查询侧分歧 |
| 10b 厂商实践：Google/Microsoft | [10b-vendor-google-microsoft.md](./dimensions/10b-vendor-google-microsoft.md) | BEIR 量化背书；文档级 ACL 托管闭环；Check Grounding 在线评测；三处产品更名 |
