# 企业级 RAG 系统/Agent 专项调研（怎么搭、用什么搭、各家怎么做的）

> **性质**：RAG 全链路源码级调研。核心问题：要搭建一个**企业级 RAG agent/系统**（私有化、可治理、可评测），业界开源方案在**数据接入 → 文档解析 → 切分索引 → 检索重排 → 生成 → 评测可观测 → 权限多租户**各环节分别做到了什么程度、怎么实现的、该怎么选型和组装。
> **方法**：分层对象清单（平台 / 框架 / 检索技术 / 文档解析 / 向量基建 / 评测，另有 Java 生态对照）→ 少量核心对象做 `profiles/` 深挖 + 按系统构建块做 `dimensions/` 横向矩阵 → `report.md` 综合出选型与参考架构。
> **上游**：`research/agent-framework/`（llama_index / langchain / langgraph / spring-ai / langchain4j 已有框架轮档案）、`research/agent-oss/`（dify 已有产品轮档案）、`research/agent-persistence/`（dify / WrenAI 存储档案）。**本轮对复用对象只补 RAG 视角新证据，框架级结论引用上游不重复。**

## 对象清单（六层 + Java 对照）

### A. 端到端 RAG 平台（自建系统最直接的参考）

| 仓库 | star | 入选理由 | 基线 HEAD |
|---|---|---|---|
| infiniflow/ragflow | 92.1k | RAG 专项引擎之最，深度文档解析（deepdoc）+ 引用溯源，国内企业落地最多 | deb1235be |
| langgenius/dify | 158.2k | 通用 LLM 应用平台，RAG 是其一等模块，知识库 + 工作流编排 | 79effdd498（复用，无漂移） |
| Mintplex-Labs/anything-llm | 67.0k | 轻量全栈桌面/私有部署 RAG 工作台，多用户多工作区模型 | 2a10d052 |
| The-Vibe-Company/quivr（原 QuivrHQ） | 39.6k | 「第二大脑」型 RAG agent；**注意：已重写为 Go 为主**（根有 go.mod/cmd），Python 时代结论需重验 | 67a6c0e9f |
| Cinnamon/kotaemon | 25.8k | RAG 技术展示台（GraphRAG/LightRAG/多种 rerank 集成），低活跃（2026-05 后无实质提交）仍具参考价值 | 9ad3e4e4 |

### B. RAG 编排框架（代码优先自建路线）

| 仓库 | star | 入选理由 | 基线 HEAD |
|---|---|---|---|
| run-llama/llama_index | 52.5k | RAG 框架标杆，检索/索引抽象最全 | 7169bcd0d（复用） |
| deepset-ai/haystack | 26.7k | 企业级 pipeline 框架（2.x），德国系严谨工程，生产口碑 | 05cab58ac |
| neuml/txtai | 13.0k | 嵌入式一体化（向量+图+流水线），**元数据级不克隆** | — |

### C. 高级检索技术（GraphRAG / 知识图谱增强）

| 仓库 | star | 入选理由 | 基线 HEAD |
|---|---|---|---|
| microsoft/graphrag | 36.3k | GraphRAG 原始论文官方实现，社区检测 + 层级摘要 | 5faaaf4f |
| HKUDS/LightRAG | 40.1k | 轻量 GraphRAG 变体，双层检索（低层实体 + 高层主题），国内影响大 | 4d0afc1bc |

### D. 文档解析 Ingestion（企业非结构化数据的门卫）

| 仓库 | star | 入选理由 | 基线 HEAD |
|---|---|---|---|
| docling-project/docling | 68.7k | IBM 出品，版面分析 + 表结构识别 + 读序模型，kotaemon/许多平台的标准后端 | dd477a9f |
| opendatalab/MinerU | 81.5k | 中文文档解析事实标准（上海 AI Lab），OCR/公式/表格全 | b7f3dd0c |
| Unstructured-IO/unstructured | 15.6k | 解析分区事实标准之一，英文生态影响大 | e2f22b38 |

### E. 向量与检索基建（只看 RAG 相关特性：过滤/混合检索/多租户/全文）

| 仓库 | star | 入选理由 | 基线 HEAD |
|---|---|---|---|
| milvus-io/milvus | 46.4k | 国内企业最常用分布式向量库 | 55b4415230 |
| qdrant/qdrant | 35.0k | Rust 高性能，payload 过滤与多租户设计典范 | 016542aa5 |
| pgvector/pgvector | 23.3k | PostgreSQL 扩展，SQL 生态零新增组件路线 | f37c13f |
| weaviate / chroma | 16.9k / 29.5k | **元数据级不克隆**（经平台层使用方式带出） | — |

### F. 评测与可观测

| 仓库 | star | 入选理由 | 基线 HEAD |
|---|---|---|---|
| vibrantlabsai/ragas（原 explodinggradients） | 16.0k | RAG 评测事实标准（faithfulness/answer relevancy/上下文精度召回） | 298b682 |
| confident-ai/deepeval | 18.8k | LLM 单测框架，RAG 指标 + red teaming，生产 CI 集成 | 2213fac0f |
| Arize-ai/phoenix | 11.8k | tracing/可观测，**元数据级不克隆** | — |

### G. Java 生态对照（复用 framework 轮克隆）

spring-ai（b5eb0272f）、langchain4j（0028928ea）、spring-ai-alibaba（f82da0b50）：RAG 能力面（ETL/向量库适配/检索增强 API）与 Python 生态差距对照——面向 Java 团队的企业落地选型。

> 复用仓基线 2026-10-12 全数核验，与 persistence 轮记录一致，无漂移。langchain 348c9dc572 / langgraph e539ac122f 同步冻结备用于 Agentic RAG 维度。

### 排除记录（Phase 0 核验，2026-10-12）

- weaviate/Verba（7.7k⭐）：**已归档**（2026-06）
- truefoundry/cognita（4.4k⭐）：**已归档**（2026-03）
- vanna-ai/vanna（23.8k⭐）：**已归档**（2026-02），Text2SQL RAG 方向
- open-webui（154.4k⭐）：活跃但本质是 LLM 前端网关，RAG 为外挂，元数据级提及
- zylon-ai/private-gpt（57.6k⭐，原 imartinez/privateGPT）：迁移存续活跃，但架构上被 ragflow/dify 覆盖，元数据级提及
- khoj / DocsGPT / litellm：活跃，分别偏个人助手 / 文档问答单点 / LLM 网关，元数据级提及
- ragas 迁移至 vibrantlabsai 后主分支 push 停在 2026-02，但 issue 区活跃（2026-10 仍有修复），标注活跃度风险后仍入选

## 证据纪律（沿用 agent-framework 轮约定）

- 所有结论可溯源：`~/develop/opensource/<repo>/路径#符号`；证据三级——【核心】核心代码实现 /【示例】examples 或 demo /【文档】文档宣称；查不到标 ❌ 或 ⚠️待确认，不臆测。
- 区分「产品宣称」与「代码实现」（agent-oss 轮教训），企业级特性（权限/多租户/评测）必须对码。
- 研究期间冻结已分析仓库（不 `git pull`）；基线 HEAD 见上表（克隆完成后统一核验回填）。
- 元数据级对象不纳入源码级结论，结论明确标注「非源码级」。
- 网络受限：github.com 网页 / raw 常超时，查元数据 / README / 文件内容优先 `gh api`。

## 调研维度（dimensions/，按搭建构建块组织）

| # | 维度 | 问题 |
|---|---|---|
| 01 | 平台架构 | 五个平台的分层/服务拆分/部署形态/技术栈/扩展机制，自建参考架构从谁身上取材 |
| 02 | 文档解析与切分 | deepdoc / docling / MinerU / unstructured 的解析管线，表格/OCR/中文，平台怎么接 |
| 03 | 索引与向量库 | 平台们用什么存、schema 长什么样、milvus/qdrant/pgvector 的过滤/混合检索/多租户能力 |
| 04 | 检索与重排 | 混合检索（向量+BM25/全文）、融合、rerank、查询变换（改写/HyDE/分解）、分块策略 |
| 05 | GraphRAG 与知识增强 | graphrag / LightRAG 的建图、检索、与向量 RAG 的混用 |
| 06 | Agentic RAG | RAG 作为 agent 工具、迭代检索、多跳、langgraph/llama_index/dify 的 agentic 形态 |
| 07 | 企业治理 | 权限（文档级/行级）、多租户、配额、审计、私有化部署清单 |
| 08 | 评测与可观测 | ragas / deepeval 指标体系、平台自带评测、tracing |
| 09 | Java 生态对照 | spring-ai / langchain4j / spring-ai-alibaba 的 RAG 能力面 |

## 进度 checklist（分批可续）

- [x] Phase 0：选型圈定 + gh api 批量核验（29 仓，发现 3 处迁移、3 处归档）
- [x] Phase 0.5：克隆 15 仓（全量，无断流）+ 复用仓基线核验回填（无漂移）
- [x] 元数据级对象信息收集（open-webui/litellm/private-gpt/txtai/phoenix/DocsGPT/khoj）
- [x] Phase 2：dimensions ×9（01平台架构 / 02解析切分 / 03向量库 / 04检索重排 / 05GraphRAG / 06Agentic / 07治理 / 08评测 / 09Java）——dim02 首跑撞 API 限流后重跑完成
- [x] Phase 3：report.md 综合报告（TL;DR 十条 / 参考架构 / 三路线 / 分场景技术栈 / 实施蓝图 / 落差汇总 / 风险登记）
- [x] 复核：14 项抽查（13 命中 + 1 处修正：milvus jieba 中文 Python 用例被 skip，证据改锚 Go 活测试，见 report §12）
- 备注：本轮不做 profiles（九维已覆盖 ragflow/haystack 等对象的机制细节，单档全景信息增量低于成本），方法沿 agent-persistence 轮「维度主导」先例

## 目录

- [report.md](./report.md) —— 综合报告（最终交付，先读这篇：TL;DR 十条 / 参考架构 / 三条路线 / 分场景技术栈 / 实施蓝图 / 宣称vs实现落差 / 复核记录）
- [dimensions/](./dimensions/) —— 九份构建块深挖（过程档案，结论均可溯源到源码路径）：
  [01 平台架构](./dimensions/01-platform-arch.md) ·
  [02 解析切分](./dimensions/02-ingestion-parsing.md) ·
  [03 索引向量库](./dimensions/03-index-vector-store.md) ·
  [04 检索重排](./dimensions/04-retrieval-rerank.md) ·
  [05 GraphRAG](./dimensions/05-graphrag.md) ·
  [06 Agentic RAG](./dimensions/06-agentic-rag.md) ·
  [07 企业治理](./dimensions/07-governance.md) ·
  [08 评测可观测](./dimensions/08-eval-observability.md) ·
  [09 Java 生态](./dimensions/09-java-ecosystem.md)
