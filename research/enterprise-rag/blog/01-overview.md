# 企业级 RAG 全景：一篇文档到一段回答之间发生了什么

《给 Agent 造知识库：企业级 RAG 搭建手记》第 1 篇。

> 本文事实基于 2026-10 冻结的开源源码基线与当日可访问的官方文档，源码基线 commit 见文末参考节。

## 一、先说一个坏消息：你收藏的 RAG 教程可能已经失效

为了给公司内部搭一个给 Agent 供数的知识库，我最近做了一轮源码级调研：22 个开源仓库（5 个端到端 RAG 平台、3 个编排框架、2 个 GraphRAG 实现、3 个文档解析器、3 个向量库、2 个评测库，加 Java 生态对照仓与官方 cookbook 等复用仓）对码当前基线，另外对 OpenAI、Anthropic、Google、微软四家厂商的第一方实践做了文档级调研。这个系列十篇文章，就是这轮调研的整理稿。

调研的第一个发现不是任何技术结论，而是一个时效性警报：**这批仓库正集体处于「大重写周期」，2025 年及之前的网上资料——包括大量教程和专栏——对它们大面积失效**。几个最有代表性的例子：

| 仓库 | 大众认知 | 2026-10 基线实况 |
|---|---|---|
| ragflow | Python + deepdoc 深度解析 | 已重写为 Go 单二进制四角色；**Python 源码 2026-09-28 整体删除**（git log 提交 `670e68872` 起，分三批删完） |
| quivr | Python「第二大脑」RAG agent | 2026-09-03 从 orphan 分支推倒重写为 Go「内容流搜索与监测引擎」，无 LLM agent 循环；冻结基线时仓库仅 5 周龄，README 自评 "evaluation stage… do not run it in production yet"（`The-Vibe-Company/quivr@67a6c0e9f README.md`） |
| MinerU | magic_pdf 时代管线 | 4.0 全新架构（backend/model/parser 分层 + 新底层库 docvortex），effort 四档 + 1.2B VLM |
| docling | DocLayNet YOLO + TableFormer | 布局模型默认换成 Heron（YOLO 已弃用），公式走 Granite VLM，还内置了 10+ 个第三方 VLM 预设，活成了「VLM 解析模型聚合器」 |
| haystack 2.x | core 自带 TransformersSimilarityRanker | cross-encoder 重排已移出 core，只剩 LLM/MetaField 等 4 个 ranker，网上教程与现状不符 |
| dify | agent 可挂知识库工具 | agent_v2 节点对 DATASET_RETRIEVAL 工具类型直接 raise，产品决策是「知识路径与 agent 路径分离」（`langgenius/dify@79effdd498 api/core/workflow/nodes/agent_v2/dify_tools_builder.py#_tool_layer_destination`） |

这对选型有三个直接含义。

**第一，任何判断必须锚定一个冻结的基线 commit，并且接受它半年后就过期。** 拿着 2024 年的 ragflow 文章去读今天的代码，目录都对不上——旧 `api/`、`rag/` 目录已不存在，主代码全在 `cmd/` + `internal/`（`infiniflow/ragflow@deb1235be`，迁移状态见其 AGENTS.md）。顺带一个坑：ragflow 的 `v1.0.0-rc1` tag（2026-09-29 打的）已经是 Go 版，Python 时代的 tag 止于 v0.9.0 系列，按 tag 找旧版会踩空。

**第二，「重写」不等于「回归」。** 我们把 ragflow 的 Python 遗产版（2026-03 纯 Python 最后完整态 `2508c46c8`）用 git worktree 挂出来逐项对照过：核心检索算法（融合公式、字段权重、引用归因参数）在 Go 版里是一致的，但存在已验证的回归项——use_kg 图检索只移植了聊天路径、dataset/chunk 检索 API 路径仍是 Warn 跳过（`infiniflow/ragflow@deb1235be internal/service/dataset/search.go:324`），resume/tag 两种 chunk 模板消失，agent 运行时插件管理器无等价物。用新版本时要知道自己丢了什么。

**第三，star 数与「能抄的代码量」无关。** quivr 冻结时 39.6k star，但它的当前历史是五周前从零开始的第二个 root commit——组织易主、代码零继承，旧 Python 版封存在 `v1-final` tag 里。看仓库先看它「现在是什么」，而不是「曾经是什么」。

这就是写这个系列的动机：把 22 仓的对码结论钉在明确的时间桩上，整理成一篇文档到一段回答之间的完整工程地图。本文是总览：全链路考虑面、参考架构、三条建设路线，以及「企业级」这个词的真实含义。

## 二、一篇文档到一段回答：完整的考虑面

很多人对 RAG 的想象是一根直线：文档切块、向量化、检索、拼 prompt。真正动手会发现它是一条七环节的管道，外加六块横切关注点。缺了任何一格，项目都会在某个规模上卡死。

**管道七环节：**

| # | 环节 | 核心问题 | 一句话结论（后续篇目展开） |
|---|---|---|---|
| 1 | 接入 Ingestion | 文档从哪来、原件谁保管 | 对象存储是 canonical 真相源，索引只是投影（第 3 篇） |
| 2 | 解析 Parsing | 扫描件/表格/公式怎么还原成结构 | 中文场景生死线，MinerU + docling 双服务拓扑（第 2 篇） |
| 3 | 切分 Chunking | 块边界从哪来 | 拿解析的结构输出指导切分，不做 markdown 盲切（第 3 篇） |
| 4 | 索引 Indexing | 存哪个引擎、schema 长什么样 | 中文混合检索有明确的引擎分野，选错很难补救（第 3 篇） |
| 5 | 检索 Retrieval | 怎么召回 | BM25 + 向量双路、召回窗口给足，融合用 RRF 或可解释加权（第 4 篇） |
| 6 | 重排 Rerank | 怎么精排 | cross-encoder 喂原文、分数归一到 [0,1]（第 4 篇） |
| 7 | 生成 Generation | 怎么带引用回答 | 引用溯源是信任工程，纯 prompt 引用只适合 demo（第 4 篇） |

**横切六块：**

- **架构**：同步与异步怎么切、任务怎么不丢（本文第三节）；
- **权限**：谁能看哪份文档，并且要在检索结果里强制过滤（本文第五节、第 7 篇）；
- **评测**：检索质量和回答质量怎么量化、怎么进 CI 门禁（第 8 篇）；
- **安全**：telemetry 出墙点、凭据治理、prompt injection 防护（第 7 篇）；
- **成本**：索引与查询成本、部门配额与分摊（第 8、9 篇）；
- **演进**：GraphRAG 与 Agentic RAG 是增量路径不是推翻重来（第 5、6 篇）。

这套考虑面不是我的发明，是从 22 个仓库的现状归纳的；而且开源侧的核心配方拿到了厂商的量化背书：Azure 官方 BEIR 实测 NDCG@10 从 BM25 的 40.6、纯向量 45.0，到混合 48.4、混合加 semantic ranker 50.0——「混合检索加重排」这两个环节的钱最难省。Anthropic 的 Contextual Retrieval 数字链更陡：索引侧补语境加混合加重排，检索失败率累计下降 67%。这两组数字的出处和适用条件，第 5 篇专门讲。

## 三、参考架构：五家平台用同一副骨架

五个端到端平台（ragflow、dify、anything-llm、quivr、kotaemon）形态各异——从 dify 的十几个容器到一个 Gradio 进程——但对码下来，骨架惊人地一致：

```
              ┌──────────── 控制面（同步 REST）────────────┐
              │  文档上传 / 状态查询 / 检索问答 API / 管理台  │
              └──────┬──────────────────────────┬─────────┘
                     │ 写任务表 + 发队列消息        │ 检索请求
        ┌────────────▼───────────┐    ┌──────────▼─────────────┐
  文件对象存储 ◄── │  摄取 worker 池          │    │  检索服务（同步）        │
  (canonical 真相)│  解析→切分→嵌入→索引      │    │  双路召回→融合→重排      │
        │         │  心跳+租约+断点续跑       │    │  →权限过滤→prompt→引用  │
        │         └────────────┬───────────┘    └──────────┬─────────────┘
        │                      │                           │
  ┌─────▼──────────┐   ┌───────▼─────────┐   ┌─────────────▼───────────┐
  │ 元数据库 (PG/MySQL)│   │ 文档/向量引擎      │   │ LLM/嵌入/重排模型接入     │
  │ 任务态、ACL、审计  │   │ BM25+KNN 同库     │   │ (运行时可插拔)           │
  └────────────────┘   │ 或分库             │   └─────────────────────────┘
                       └──────────────────┘
```

### 3.1 控制面与数据面分离：五家无一例外

同步 REST 只做控制面（上传、查询状态、检索问答），解析、切分、嵌入、入库这些重活全部下异步任务系统，任务态落关系库。五家的实现从轻到重排成一条光谱：

| 平台 | 控制面 | 异步件 | 一句话点评 |
|---|---|---|---|
| dify | Flask REST | Celery + Redis，多队列分优先级 | 摄取管道四段式在 `langgenius/dify@79effdd498 api/core/indexing_runner.py#IndexingRunner`：抽取→切分→嵌入→入库，任务挂在 `api/tasks/document_indexing_task.py` 的 dataset 队列 |
| ragflow | gin REST（Go） | NATS JetStream + MySQL 任务表 | 任务工程化五家最高：worker 心跳 + 任务租约 + 调度行 poll 与队列 notify 混合消费 + 断点续跑（`infiniflow/ragflow@deb1235be internal/ingestion/service/ingestion_service.go#handleAndExecute`） |
| quivr | Go 标准库 HTTP | Temporal 持久化工作流 | 长任务、重试、补偿全部外包给成熟组件（`The-Vibe-Company/quivr@67a6c0e9f internal/orchestration/temporal/`） |
| anything-llm | Express | 无队列：collector 子进程 + IPC | 嵌入放进可牺牲子进程，文件头注释明说「OOM 只杀 worker 不杀主服务」（`Mintplex-Labs/anything-llm@2a10d052 server/jobs/embedding-worker.js`） |
| kotaemon | Gradio | Gradio 内置 queue | 嵌入在请求线程里做，天花板明显——反面对照 |

为什么这条是第一性原则？因为解析和嵌入的耗时以分钟计，放进同步链路意味着一次上传卡死一个 worker、一次进程重启丢一批任务。dify 的多队列设计（dataset 与 priority_dataset 分池）还解决了多租户场景的插队公平性——大租户批量重建索引时，小租户的单文档不至于饿死。自建时起步可以用 anything-llm 式的子进程隔离（比引入完整队列轻一个量级），量上来再换真队列，但「控制面不跑重活」这条从第一天就不能破。

### 3.2 canonical 真相与索引投影分离：quivr 样板

quivr V2 虽然只有五周龄、自评别上生产，但它的数据治理观是五家里最强的，值得单独抄：**PG + 对象存储（SeaweedFS）是 canonical 真相，搜索索引（Weaviate）只是可随时重建的投影**；嵌入模型钉死单一版本（multilingual-e5-small）防止向量空间漂移（`The-Vibe-Company/quivr@67a6c0e9f README.md`、`deploy/compose/compose.yaml`）。它还有一个「先可用、后丰富」的摄取设计：文本先分段即刻可搜（lexical），嵌入等富化后台补齐，混合搜索在向量索引重建期间保留关键字结果——README 称之为 "Useful early, richer later"（方向有 `internal/processing/enrichment.go`、`internal/retrieval/rebuild.go` 的代码分布印证；调度细节档案未逐行核对，如实标注）。

为什么这条是救命设计？因为企业场景里文档会改、嵌入模型会换、索引引擎可能会被替换。如果向量库里存的是唯一副本，每次换嵌入模型就是一次全量迁移灾难；如果原件和结构化产物都在对象存储里钉着版本，索引坏了、模型换了，重放一遍摄取管道就恢复。ragflow 的「PG/MySQL + MinIO 为真相源、ES/Infinity 只是投影」是同款思路。

### 3.3 模型接入的可插拔程度，决定你后不重启

LLM、嵌入、重排模型的接入方式，五家分两派：dify 走独立插件守护进程，模型 provider 按租户从 plugin_daemon 拉取、运行时热装（`langgenius/dify@79effdd498 api/core/plugin/impl/model_runtime_factory.py`）；ragflow Go 版退化为编译期 factory switch——183 个 provider 文件、一个大 switch 分发，加一个 provider 要发版（`infiniflow/ragflow@deb1235be internal/entity/models/factory.go#CreateModelDriver`）。自建系统的启示：模型上新频率远高于你的想象，别把接入做成发版动作。

## 四、三条建设路线与决策口诀

### 路线 A：开箱平台（自建最少）

| 平台 | 什么时候选它 | 关键边界 |
|---|---|---|
| ragflow（Apache-2.0） | 要 RAG 专项能力最强：深度解析、12 种领域 chunk 模板、句级引用溯源、混合检索权重可调、五家最强的 KB 级权限策略引擎 | Go 重写期文档脱节；SSO/审计/配额是 EE 空壳；模型 key 明文存库 |
| dify（修改版 Apache） | 要的是 LLM 应用平台而非纯 RAG：可视化 workflow、租户体系、插件生态、多模型接入最成熟 | RAG 检索层偏浅（无查询变换、无 RRF）；「企业级」大半在闭源 enterprise 墙外；**telemetry 默认开**；多租户对外运营需商业授权 |
| anything-llm（MIT） | 最快起步、最小部署：单容器 + SQLite + LanceDB，可 air-gap，license 最干净 | 无混合检索、无重排主链、任务不持久化，文档量上千后天花板明显 |
| kotaemon（Apache-2.0） | 只当 RAG 算法试验台（GraphRAG/LightRAG/多 rerank 开关最全） | 单进程、2026-05 后停滞，不进生产 |
| quivr V2（MIT） | 只当检索引擎/MCP 检索后端参考（可重建索引观、审计触发器值得抄） | 5 周龄 v0、无 LLM 循环、无中文优化，不进生产 |

### 路线 B：框架自建（代码优先）

- **llama_index**：检索策略全家桶最全——查询变换、融合、重排、父子块、句子窗口都是 core 模块，适合「少写编排、多复用检索策略」；
- **haystack 2.x**：工程件最扎实（Pipeline 组件化、Agent 状态机与上下文压缩、evaluators），适合严谨工程；注意 cross-encoder 重排已移社区 hub；
- **langgraph**：编排控制力最强（可恢复长流程），但 agentic RAG 的经典示例已全部归档；
- Java 团队：langchain4j 的检索增强管线（路由/重排/RRF + 本地 ONNX rerank）明显强于 spring-ai（无 rerank 抽象、无混合检索件），第 10 篇给完整划法。

### 路线 C：平台骨架 + 自建增强（多数企业的实际最优解）

用 ragflow 或 dify 当骨架，白拿「上传→解析→索引→问答」的全链路与任务系统，然后**把治理缺口全部自研补齐**——文档级 ACL、SSO 网关、查询审计、配额。判断依据很硬：治理自研量是刚性的（下一节会看到平台不会替你做），而解析、索引、检索层自研的边际收益低于直接用现成件。

**决策口诀**：验证性 POC → anything-llm；生产知识问答、文档重（扫描件/表格多）→ ragflow + 自研治理层；要 workflow 化多应用 → dify（内部单租户用、第一件事关 telemetry）；检索策略要极致定制 → llama_index 或 haystack 自建；Java 主链 → langchain4j 主管线 + Python 解析微服务。

## 五、「企业级」的真相：五条落差

「企业级」是开源 RAG 被宣传淹没最严重的词。逐项对码后，落差集中在五条：

**1. 文档级权限，五平台全军覆没。** 五家的权限粒度全部止步于「库」级：ragflow 到 dataset（但策略引擎本身是五家最细，private/tenant/shared 加按用户/租户共享，且检索入口真的会查权限）、dify 到 dataset（`only_me/all_team/partial_members`）、anything-llm 到 workspace、quivr 到 corpus（API key 级，没有用户实体）、kotaemon 干脆全局共享。而「财务只能检索财务文档、并在检索结果里强制过滤」这个企业刚需，需要 ACL 表加 chunk 到 doc 的映射、在组装进 LLM prompt 之前过滤——全部自研。讽刺的是，这恰是托管服务的最大卖点：Google 的托管检索把文档级 ACL 做成原生能力（ACL 随索引摄入、查询时带用户身份在引擎内过滤），Azure 也有 security filter 路线——自建系统可以照抄这个模式，第 7 篇展开。

**2. SSO 是假象。** ragflow 社区版的 OAuth handler 全部返回 "not implemented"（`infiniflow/ragflow@deb1235be internal/handler/user_auth_ee.go:26-77`，配置文件里摆着 OAuth2/OIDC 模板，但 CE 构建不可用）；dify OSS 里的 SSO/RBAC 本质是调用闭源 dify-enterprise 的 HTTP 客户端，纯 OSS 部署拿不到；anything-llm 的 "Simple SSO" 是 API key 换临时 token 的桥接，不是协议级对接。现实做法是平台前面加 Keycloak 或 OAuth2 proxy，五家里只有 kotaemon 给了 OIDC 样板。

**3. 「自托管 = 数据不出门」不成立（对 dify）。** 社区版 telemetry 默认开启，`DISABLE_TELEMETRY` 默认 False，上报端点 `https://otel.dify.ai/v1/events`，每 30 分钟一次心跳，payload 含 instance_id、OS、arch（`langgenius/dify@79effdd498 api/configs/feature/__init__.py:840-860`）。私有化部署清单第一件事应是 `DISABLE_TELEMETRY=true`。anything-llm 的 PostHog 同理（可关）；ragflow、quivr、kotaemon 干净。

**4. 审计与配额基本靠自研。** 五家里只有 quivr 认真做了审计表——而且是 append-only 加数据库触发器防篡改（`The-Vibe-Company/quivr@67a6c0e9f migrations/20261006T0039Z_audit_events.sql`）——但审计范围明确排除读和检索，「谁查了什么」不在其中。配额只有 anything-llm 有每用户日限（`server/endpoints/chat.js:61`）。

**5. 宣称与实现的系统性落差。** 精选对码实锤：

| 宣称 | 实况 |
|---|---|
| ragflow「enterprise-ready」 | CE 的 OAuth 全 stub，审计/配额全在 EE 空壳文件里 |
| dify「SSO/RBAC/审计」 | OSS 侧只是闭源企业版的 HTTP 客户端 |
| quivr「agent-first」 | Python 时代标签；Go 重写版无任何 LLM 调用 |
| kotaemon 集成 GraphRAG | 通道绑旧版 parquet 表名，配 graphrag v3.x 预期不可用 |
| 「细粒度文档权限」（行业性话术） | 五平台全部没有，含部分闭源产品的话术 |

结论不是「开源不能用」，而是：**把平台当管道骨架用，把治理当自研项目排期**。混着期待，上线后一定会在安全评审那天翻车。

## 六、这个系列怎么走

后面九篇按管道顺序推进：第 2 篇讲解析（中文场景的生死线），第 3 篇讲切分与索引，第 4 篇讲检索与重排，第 5、6 篇讲两个可选的增量方向（GraphRAG、Agentic RAG），第 7、8 篇讲治理与评测这两块必须自研的横切面，第 9 篇拿四家厂商的官方实践与开源结论互证，第 10 篇给出分场景的技术栈组装蓝图。每篇的事实断言都带 `owner/repo@commit 路径` 级出处，你可以顺着链接直接进源码核对。

## 参考与出处

源码基线（2026-10 冻结，正文引用均为行内 `owner/repo@commit 路径` 格式）：

- infiniflow/ragflow @ deb1235be — https://github.com/infiniflow/ragflow/blob/deb1235be/internal/handler/user_auth_ee.go （OAuth stub）；…/internal/service/dataset/search.go （use_kg 未实现）；…/internal/ingestion/service/ingestion_service.go （心跳/租约/混合消费）；…/internal/entity/models/factory.go （编译期模型工厂）；…/AGENTS.md （Go 迁移状态与 Python 删除清单）
- langgenius/dify @ 79effdd498 — https://github.com/langgenius/dify/blob/79effdd498/api/core/indexing_runner.py （摄取四段式）；…/api/tasks/document_indexing_task.py （Celery 队列）；…/api/core/workflow/nodes/agent_v2/dify_tools_builder.py （dataset 工具拒绝）；…/api/configs/feature/__init__.py （telemetry 默认开）；…/api/core/plugin/impl/model_runtime_factory.py （租户级模型插件）
- Mintplex-Labs/anything-llm @ 2a10d052 — https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/server/jobs/embedding-worker.js （子进程隔离）；…/server/endpoints/chat.js （每用户日限）
- The-Vibe-Company/quivr @ 67a6c0e9f — https://github.com/The-Vibe-Company/quivr/blob/67a6c0e9f/README.md （架构与状态自评）；…/deploy/compose/compose.yaml （依赖栈）；…/migrations/20261006T0039Z_audit_events.sql （append-only 审计）
- Cinnamon/kotaemon @ 9ad3e4e4 — https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/sso_app.py （OIDC 样板）
- deepset-ai/haystack @ 05cab58ac — https://github.com/deepset-ai/haystack/blob/05cab58ac/haystack/components/rankers/ （core ranker 清单，cross-encoder 已移出）
- docling-project/docling @ dd477a9f — https://github.com/docling-project/docling/blob/dd477a9f/docling/datamodel/stage_model_specs.py （Heron 默认与 VLM 预设）
- opendatalab/MinerU @ b7f3dd0c — https://github.com/opendatalab/MinerU/blob/b7f3dd0c/ （4.0 架构，详见第 2 篇）

官方文档（2026-10-15 可访问）：

- Azure AI Search 混合检索排序（RRF k=60）：https://learn.microsoft.com/azure/search/hybrid-search-ranking
- Anthropic Contextual Retrieval：https://www.anthropic.com/news/contextual-retrieval
- Azure BEIR 数字为微软官方博客结论的转载核对（techcommunity 原文 403），证据等级弱于上述一手文档，采信时注意。

另外：BGE 系嵌入、TEI 推理服务等模型层说法为生态通识，未源码级验证。

## 系列目录

《给 Agent 造知识库：企业级 RAG 搭建手记》：

1. 企业级 RAG 全景：一篇文档到一段回答之间发生了什么（本篇）
2. RAG 的第一道生死线：中文文档解析怎么做
3. 分块与索引：结构感知切分、双路索引与 schema 设计
4. 检索引擎选型对比：ES、milvus、pgvector、qdrant 与嵌入式方案
5. 检索算法：混合检索、融合公式与重排的正确姿势
6. 让答案可信：引用溯源的三种实现机制
7. 开源 RAG 平台都不敢做的事：文档级权限与检索期过滤
8. 上线前后的质量防线：RAG 评测体系从零搭建
9. GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计
10. 实战设计：Python 自建轻量知识库服务，给 deepagents 供数

下一篇预告：解析是中文 RAG 的第一道生死线——扫描件、表格、公章、公式，任何一样处理不好，后面的切分、检索、重排全是白搭。我们会解剖 MinerU 4.0、docling、unstructured 三强的管线与模型清单，以及 ragflow「自研轻量 + 外挂重炮」的拓扑为什么值得抄。
