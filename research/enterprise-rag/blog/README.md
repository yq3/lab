# 《给 Agent 造知识库：企业级 RAG 搭建手记》博客系列

> 基于 [enterprise-rag 调研](../README.md)（22 仓源码级 + OpenAI/Anthropic/Google/Microsoft 四家第一方实践 + ragflow/quivr 历史锚点对照）写成的 10 篇技术博客。
> **写作纪律**：所有事实性断言附出处——开源仓以 `owner/repo@基线commit 路径` 标注（文末参考节给 GitHub 完整链接），官方文档给 URL；通识性内容明确标注「生态通识，未源码级验证」；调研中存疑的结论要么不写、要么如实标注。
> **时效声明**：全系列事实基于 2026-10 冻结的源码基线与当日可访问的官方文档。RAG 开源圈正处大重写周期（ragflow 已 Go 重写、quivr 重启、MinerU/docling 换代），阅读时请注意时间差。

## 目录

| # | 标题 | 一句话 |
|---|---|---|
| 1 | [企业级 RAG 全景：一篇文档到一段回答之间发生了什么](./01-overview.md) | 三条建设路线；「企业级」的真相 |
| 2 | [RAG 的第一道生死线：中文文档解析怎么做](./02-parsing.md) | MinerU 4.0 + docling 双服务拓扑；三强解剖与生产建议 |
| 3 | [分块与索引：结构感知切分、双路索引与 schema 设计](./03-chunking-indexing.md) | 切分策略全景；schema 两流派；嵌入模型钉版本 |
| 4 | [检索引擎选型对比：ES、milvus、pgvector、qdrant 与嵌入式方案](./04-vector-stores.md) | 三条路线与深度对比；中文 BM25 分词是隐藏变量 |
| 5 | [检索算法：混合检索、融合公式与重排的正确姿势](./05-retrieval-rerank.md) | 融合公式两流派（RRF vs 加权）；rerank 正确姿势；厂商量化背书 |
| 6 | [让答案可信：引用溯源的三种实现机制](./06-citations.md) | 句级归因/确定性标记/LLM 声明+程序校验 |
| 7 | [开源 RAG 平台都不敢做的事：文档级权限与检索期过滤](./07-permissions.md) | 五平台全军覆没的实证；自研 ACL 与托管服务的可抄模式 |
| 8 | [上线前后的质量防线：RAG 评测体系从零搭建](./08-evaluation.md) | ragas 指标算法解剖 + deepeval 门禁 + 在线监控 + 中文校准 |
| 9 | [GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计](./09-graphrag-agentic.md) | 四问判断框架；80% 场景固定管线；MCP 反转姿态 |
| 10 | [实战设计：Python 自建轻量知识库服务，给 deepagents 供数](./10-build-kb-for-agent.md) | 一个进程一个文件的完整实施蓝图（设计方案，非上线复盘） |

## 统一基线表（全系列源码证据的锚点）

| 仓库 | 基线 commit（2026-10 冻结） | 仓库 | 基线 commit |
|---|---|---|---|
| infiniflow/ragflow | `deb1235be` | milvus-io/milvus | `55b4415230` |
| langgenius/dify | `79effdd498` | qdrant/qdrant | `016542aa5` |
| Mintplex-Labs/anything-llm | `2a10d052` | pgvector/pgvector | `f37c13f` |
| The-Vibe-Company/quivr | `67a6c0e9f` | vibrantlabsai/ragas | `298b682` |
| Cinnamon/kotaemon | `9ad3e4e4` | confident-ai/deepeval | `2213fac0f` |
| run-llama/llama_index | `7169bcd0d` | microsoft/graphrag | `5faaaf4f` |
| deepset-ai/haystack | `05cab58ac` | HKUDS/LightRAG | `4d0afc1bc` |
| docling-project/docling | `dd477a9f` | langchain-ai/langgraph | `e539ac122f` |
| opendatalab/MinerU | `b7f3dd0c` | langchain-ai/langchain | `348c9dc572` |
| Unstructured-IO/unstructured | `e2f22b38` | openai/openai-cookbook | `9aad95f` |
| spring-projects/spring-ai | `b5eb0272f` | langchain4j/langchain4j | `0028928ea` |

历史锚点（第 5/9 篇用到）：ragflow 纯 Python 最后完整态 = `2508c46c8`（2026-03-04）；quivr Python 版最后态 = `947a78541`（2025-06-19，v1 封存于 `v1-final` tag）。

## 与调研档案的关系

博客是 [dimensions/](../dimensions/)（13 份维度深挖）与 [report.md](../report.md) 的面向公众重述与综合：论断范围不超出档案，档案中的 ⚠️/❌ 存疑项在博客中如实保留标注。需要完整证据链（本地路径#符号级）时请回读档案原文。
