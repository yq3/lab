# 维度 01：平台架构 —— 五个端到端 RAG 平台的源码级横向分析

> 调研对象与基线：ragflow `deb1235be` / dify `79effdd498` / anything-llm `2a10d052` / quivr `67a6c0e9f` / kotaemon `9ad3e4e4`（均冻结于 2026-10-12 前后）。
> 证据标注：`~/develop/opensource/<repo>/路径#符号`；【核心】= 代码实现，【文档】= README/配置宣称，❌/⚠️ = 查不到或存疑。
> 本轮两个大意外：**ragflow 已在 2026-03 启动 Go 重写**（Python 服务待删）；**quivr 已于 2026-09 全仓推倒重写为 Go 的"内容流搜索引擎"**，与旧 Python"第二大脑"不再是同一个产品。网上 2025 年前的资料对这两家基本失效。

## 0. 总表

| | ragflow | dify | anything-llm | quivr (V2) | kotaemon |
|---|---|---|---|---|---|
| **形态结论** | 模块化单体：一个 Go 二进制 4 种角色（api/ingestor/admin/syncer）+ 外围存储全家桶 | 同镜像多进程：dify-api 镜像按 MODE 跑 api/worker/beat + 独立插件守护进程，最接近微服务 | 单容器双 Node 进程（server+collector），桌面级单体 | Go 模块化单体（api+worker 同二进制）+ Temporal 编排，依赖栈最重 | 单 Python 进程（Gradio 应用），纯单体 |
| **语言/框架** | Go（gin）+ React/TS 前端【核心 cmd/ragflow_server.go】 | Python（Flask + Celery）+ Next.js 前端【核心 api/app_factory.py】 | JavaScript Node（Express + Prisma）+ React 前端【核心 server/index.js】 | Go（标准库 HTTP）+ 少量 demo UI【核心 cmd/quivr/main.go】 | Python（Gradio + theflow）【核心 app.py】 |
| **任务队列** | NATS JetStream（任务态存 MySQL，poll+notify 混合）【核心】 | Celery + Redis broker，多队列分优先级【核心】 | 无外部队列：Bree 进程内调度 + 嵌入子进程 IPC【核心】 | Temporal 持久化工作流（backfill/ingest/acquire）【核心】 | 无：Gradio 内置 queue【核心 app.py】 |
| **元数据库** | MySQL（可 PG 等） | PostgreSQL（可 MySQL） | SQLite（可换 PostgreSQL） | PostgreSQL 17 | SQLite（SQLModel/alembic） |
| **文档/向量引擎** | ES / OpenSearch / Infinity / OceanBase / SereneDB / Vastbase 六选一（向量+全文同库） | 30+ 向量库插件化 + jieba 关键字索引（向量、关键字分库） | 10 家向量库（LanceDB 默认本地） | Weaviate（lexical+vector 同库） | Chroma 默认（向量）+ LanceDB（docstore），可选 Milvus/Qdrant/ES |
| **对象存储** | MinIO（S3/OSS/GCS 可选） | 无独立对象库（文件在本地卷/DB） | 本地文件系统 | SeaweedFS（S3 兼容，canonical 数据） | 本地目录 |
| **嵌入服务** | 可选 TEI 容器（tei-cpu/gpu profile） | 模型 API 即时调用（经插件守护进程） | 即时调用（本地引擎时嵌入在 worker 子进程） | TEI 容器钉死 E5-small(384d) | 即时调用 |
| **license** | Apache-2.0（纯） | Apache-2.0 + 附加品牌/LOGO 条款 | MIT | MIT | Apache-2.0 |

一句话：**五家正好排成一条"重→轻"光谱**：dify（微服务化最彻底）> ragflow（单体多角色+全家桶）> quivr（单体但外部编排最讲究）> anything-llm（一容器打包两进程）> kotaemon（一个 Gradio 进程）。没有一家是"REST 微服务满天飞"的形态——**重活全部走异步任务系统，同步 REST 只做控制面**，这是共同的骨架。

---

## 1. RAGFlow：Go 重写后的"单二进制多角色 + 存储全家桶"

### 1.1 服务拆分与形态

**重要事实：当前基线的 ragflow 是 Go 项目。** go.mod 于 2026-03-04 由 PR #13240「RAGFlow go API server」引入；仓库 AGENTS.md 明确写着"Go implements the API, admin, ingestor, and syncer modes… The Python API, admin, and workers are still present pending removal"【文档 ragflow/AGENTS.md】。冻结基线时旧 `api/`、`rag/` 目录已基本清空（`rag/` 只剩 prompts），主代码全在 `cmd/` + `internal/`【核心，git log `--diff-filter=A -- go.mod` 实证】。

运行形态是**一个二进制四种角色**，由启动参数区分：`--api`（HTTP 服务）/ `--ingestor`（摄取 worker）/ `--admin`（管理服务）/ `--syncer`（数据源同步），外加 `--migrate`（见 `cmd/ragflow_server.go#serverArgs`，mode 注释 `admin | api | ingestor | syncer | deepdoc | migrate`）【核心】。容器入口脚本默认同容器并发起 ragflow + N 个 task_executor（`WS` 环境变量控制 worker 数），并带 5 次重启重试【核心 docker/launch_backend_service.sh#task_exe/run_server】。Web 框架为 gin【核心 cmd/ragflow_server.go 的 import】。

外围服务（docker-compose-base.yml，多为可选 profile）【核心】：
- **文档+向量引擎（六选一）**：es01（elasticsearch）/ opensearch01 / infinity（infiniflow 自家）/ oceanbase / serenedb / vastbase——注意 ragflow 的路线是**向量与全文检索同库**（双路召回打融合分），不像 dify 向量、关键字分两套；
- MySQL 8（元数据+任务表）、MinIO（对象存储；代码里还有 S3/OSS/GCS 后端【核心 internal/storage/】）；
- Kvrocks（Redis 兼容，做缓存/锁）、NATS 2.14（任务队列）、Jaeger（tracing）；
- TEI（tei-cpu/tei-gpu，嵌入推理专用容器）、sandbox-executor-manager（Agent 代码沙箱执行器，profile 隔离）；
- ClickHouse：compose 里有，但 OSS 代码只有企业版桩（`internal/engine/clickhouse/clickhouse_ee.go` 是空 Driver + sync.Once，admin 健康检查引用）【核心】——⚠️ OLAP 分析能力在开源版是占位。

### 1.2 RAG 数据流（上传→可问答）

摄取链（异步，队列驱动）：
1. API 上传文件 → 文档入库 → `internal/service/document/document_ingest.go#IngestDocuments` → `internal/service/ingestion_task_service.go#CreateForDocuments`：写 MySQL 任务表 + `PublishTaskMessage(common.TaskSubject, …)` 发 NATS JetStream 消息【核心】；
2. ingestor worker 消费：`internal/ingestion/service/ingestion_service.go`（InitConsumer(common.TaskSubject)，注释明说消费循环是"poll MySQL 调度行 + NATS notify"混合模式，另有心跳 Heartbeat + 租约 lease 保证任务不丢【核心 #handleAndExecute】）；
3. 管道本体在 `internal/ingestion/pipeline/`（DSL 模板翻译 + canvas 驱动执行 + checkpoint 断点续跑），组件在 `internal/ingestion/component/`：`parser.go`/`parser_dispatch.go`（按格式分发，PDF 走 `internal/deepdoc/` 原生解析，视觉增强走 `pdf_vision_dispatch*.go`）→ `chunker/`（切分）→ `tokenizer.go`（BPE，C++ binding `internal/binding/cpp`）→ `task/embedder.go`（调嵌入模型，带限流/校准）→ `task/chunk_index_writer.go`（写入文档引擎）；另有 `extractor.go`（实体抽取）、`knowledge_compiler/`（知识编译/去重合并，独立 consumer）【核心】；
4. 队列引擎只支持 NATS：`internal/server/config/queue_engine_config.go#ParseQueueEngineConfig`（default 分支直接报"not supported"）【核心】。

检索链（同步，一次提问）：
- 入口多路：聊天/Agent（`internal/agent/tool/retrieval.go`、`internal/agent/runtime/retrieval.go`）、开放 API（`internal/handler/dify_retrieval_handler.go` 兼容 dify 检索协议、`internal/handler/mcp_retrieval.go` MCP 服务）、wikisearch（`internal/service/wikisearch/`）；
- 汇聚到 `internal/service/nlp/retrieval.go#RetrievalService`：混合检索（向量 KNN + 关键词 + 融合表达式，`VectorOnly` 纯向量模式，`RetrievalByChildren` 父子块回收），支持 rerank 模型、相似度阈值、向量权重【核心】；
- 引擎抽象在 `internal/engine/engine.go#DocEngine` 接口，ES/Infinity/OceanBase/… 各自实现【核心】。

### 1.3 扩展点

- **模型接入**：`internal/entity/models/` 一个 provider 一个文件（183 个文件：anthropic/ollama/vllm/…），统一实现 `ModelDriver` 接口，`factory.go#CreateModelDriver` 用大 switch 分发，兜底 `openai-api-compatible`【核心】。注意：**社区流传的"ragflow lazy-load 模型工厂"是旧 Python 时代的模式；Go 版是编译期注册 + factory switch，运行时不可插拔**（新增 provider 要改核心代码）。模型配置存 MySQL（启动时 `--migrate` 建模型 provider 表【核心 launch_backend_service.sh#run_migrations】）。
- **文档引擎**：`DocEngine` 接口可加新后端，但同样要动核心仓。
- **沙箱**：sandbox-executor-manager 独立容器进程，Agent 代码执行外置【核心 compose】。
- 没有用户级插件系统（对比 dify 的 plugin daemon）❌。

### 1.4 亮点与短板

亮点：单二进制部署心智极简，角色横向扩容清晰（多起几个 `--ingestor`）；任务系统的工程化程度是五家最高（心跳+租约+重投递计数器+断点续跑都有测试覆盖）；向量/全文同库省掉一套索引同步。
短板：Go 迁移期文档与社区资料严重脱节；存储全家桶默认拉起一大堆容器；模型 provider 无运行时插件机制；ClickHouse 等 EE 桩提示开源版与商业版能力有分叉。

---

## 2. Dify：同镜像多进程 + Celery + 插件守护进程（微服务化最彻底）

### 2.1 服务拆分与形态

compose 主栈（docker/docker-compose.yaml）【核心】：`api` 与 `worker`/`worker_beat` **共用同一个 `langgenius/dify-api` 镜像**，仅靠 `MODE=api / worker` 环境变量分化（worker 注释："The Celery worker for processing all queues (dataset, workflow, mail, etc.)"）；`api_websocket`（collaboration profile）；`web`（Next.js）；`db_postgres`（postgres:15，可切 MySQL）；`redis`（broker+缓存）；`plugin_daemon`（`dify-plugin-daemon`，插件运行时）；`sandbox` + `local_sandbox`（代码执行）；`agent_backend`/`agent_ssrf_proxy`（Agent 专用后端 + squid 代理）；`ssrf_proxy`、`nginx`、`certbot`；外加 20 余种向量库 profile（weaviate/qdrant/milvus/pgvector/chroma/oceanbase/…）。

进程间通信：REST/HTTP 为主。api ↔ plugin_daemon 走 HTTP（`PLUGIN_DAEMON_URL` 默认 `http://localhost:5002`，带 key 与超时【核心 api/configs/feature/__init__.py#PluginConfig】）；agent_backend 也是 HTTP（`AGENT_BACKEND_BASE_URL`【核心 compose worker env】）；无 gRPC 服务间调用（仅个别向量库客户端用 gRPC 连库）。

### 2.2 RAG 数据流

摄取链：
1. `controllers/`（REST）→ `api/services/dataset_service.py`（文档/知识库业务）→ `api/services/document_indexing_proxy/document_indexing_task_proxy.py` 投递 Celery；
2. `api/tasks/document_indexing_task.py#document_indexing_task`——`@shared_task(queue="dataset")`，另有 `priority_document_indexing_task`（queue="priority_dataset"）做租户级插队【核心】；
3. 真正的管道在 `api/core/indexing_runner.py#IndexingRunner`：`_extract`（抽取，`api/core/rag/extractor/` 30+ 格式）→ `_get_splitter`/切分（`api/core/rag/splitter/`）→ `_transform`（嵌入，`api/core/rag/embedding/`）→ `_load`（入库，`api/core/rag/index_processor/` 按 index_type 分发 paragraph/QA 两种处理器，写入 `api/core/rag/datasource/vdb/`）+ `_process_keyword_index`（jieba 关键字索引，`api/core/rag/datasource/keyword/jieba/`）【核心】；
4. Celery broker 为 Redis（`CELERY_BROKER_URL`，compose 起独立 redis 容器）【核心 api/configs/middleware/__init__.py#L291】。

检索链（一次提问）：
1. 应用层（chat/workflow/agent 三种 app 形态）→ `api/core/rag/retrieval/dataset_retrieval.py#DatasetRetrieval#retrieve`：多知识库检索、可配多路召回（multiple 模式做 fusion rerank）【核心】；
2. 单路 = 向量库（`datasource/vdb/vector_factory.py`，30+ 后端，清单见 `vector_type.py#VectorType`）+ 关键字索引（jieba）并行；
3. 后处理 `api/core/rag/data_post_processor/`（rerank/reorder）→ 注入 prompt → LLM；
4. 新动向：`api/tasks/rag_pipeline/rag_pipeline_run_task.py`（queue="pipeline"）+ `models.dataset.Pipeline`——把 RAG 摄取做成 workflow 式管道（实体含序列化的 invoke entities 文件）【核心】，是对"知识库即管道"的补课，值得后续维度单独跟。

### 2.3 扩展点

- **模型/工具/数据源全部走插件守护进程**：`api/core/plugin/impl/model_runtime_factory.py#create_plugin_provider_manager(tenant_id)` 按租户从 plugin_daemon 拉取 provider 实例【核心】——即 LLM/嵌入/rerank 接入是**运行时、租户级、可热装**的，这是与 ragflow 编译期注册的本质差异；
- 向量库：继承 `BaseVector` + 注册 `VectorType` 枚举即可加新库（代码内注册，非热插拔）；
- 关键字索引：`keyword_factory.py` 目前只有 jieba 一种实现，扩展位存在但空置【核心】。

### 2.4 亮点与短板

亮点：控制面/执行面分离教科书级（REST 只做编排，重活全下 Celery）；租户级队列与优先级队列；插件生态是五家唯一的运行时可插拔体系；sandbox/ssrf_proxy 等安全配套齐全。
短板：服务数量多（10+ 容器），小团队运维成本高；RAG 只是 dify 的一个模块，检索算法本身（切分、融合、引用）相比 ragflow/kotaemon 偏浅；license 附加条款需法务过目。

---

## 3. AnythingLLM：一容器两进程的"桌面级"全栈单体

### 3.1 服务拆分与形态

docker-compose 只有**一个 service**【核心 docker/docker-compose.yml】；容器入口脚本同时拉起两个 Node 进程：`node /app/server/index.js`（Express API，端口 3001，同时托管前端静态资源）与 `{ node /app/collector/index.js; } &`（文档收集器，内部 HTTP 端口 8888）【核心 docker/docker-entrypoint.sh#L25-27】。两进程间通信是 **localhost HTTP**：`server/utils/collectorApi/index.js#CollectorApi`（`http://0.0.0.0:8888`，用共享 CommunicationKey 做内部认证，注释明说"docker 内网不暴露即安全"）【核心】。

- 数据库：Prisma + **SQLite 默认**（`file:../storage/anythingllm.db`），schema 里注释提供 PostgreSQL 切换路径【核心 server/prisma/schema.prisma】；
- 向量库：`server/utils/vectorDbProviders/` 十家——lance（LanceDB，本地默认）/chroma/chromacloud/milvus/pgvector/pinecone/qdrant/weaviate/astra/zilliz【核心】；
- 无消息队列：定时与后台任务用 Bree（进程内调度器）+ PQueue 限并发【核心 server/utils/BackgroundWorkers/index.js#BackgroundService】。

### 3.2 RAG 数据流

摄取链：
1. 前端上传 → server 存 `collector/hotdir` → `CollectorApi#processDocument` POST 给 collector【核心 server/utils/collectorApi/index.js#L112】；
2. collector 按扩展名路由到每格式一个转换器（`collector/utils/constants.js#SUPPORTED_FILETYPE_CONVERTERS`：asTxt/asPDF/asDocx/asXlsx/asMbox/asEPub/asAudio(Whisper)/asImage(OCR) 等）【核心】；
3. 解析产物回传 server → `server/jobs/embedding-worker.js`：**在隔离子进程中跑嵌入**（IPC 协议 batch_starting/doc_starting/chunk_progress/…，文件头注释明说"OOM 只杀 worker 不杀主服务"），切分在 `server/utils/TextSplitter/`，写入向量库（`getVectorDbClass` 动态选 provider）【核心】。

检索链（一次提问）：
1. `server/utils/chats/*.js`（apiChatHandler/openaiCompatible 两套）→ `VectorDb.performSimilaritySearch`（按 workspace 的 namespace 查向量库）【核心 server/utils/chats/apiChatHandler.js#L354】；
2. 命中文本拼接 context → LLM；无独立 rerank 模型环节（有 `EmbeddingRerankers` 目录但检索主链未接）⚠️。

### 3.3 扩展点

- LLM/嵌入/语音提供商：`server/utils/AiProviders/`、`server/utils/EmbeddingEngines/` 每家一个模块，UI 里下拉选择（运行时配置存 DB，不改代码）【核心】；
- 向量库 provider 同上运行时切换；
- Agent 技能/Agent Flows（`server/utils/agents/`、`agentFlows/`）+ MCP 客户端（`server/utils/MCP/`）。

### 3.4 亮点与短板

亮点：**零依赖部署**（一个容器+SQLite+LanceDB 全本地，官方明说可 air-gap【文档 TERMS_SELF_HOSTED.md】）；"嵌入 worker 子进程隔离"是用最小复杂度解决真实问题（本地嵌入 OOM）的好样本；MIT license 对二次开发最友好之一。
短板：单容器无法横向扩容（collector 只有一个、任务无持久化队列，重启丢进行中的嵌入进度）；检索链路简单（无混合检索/无 rerank 主链）；企业级多租户/审计能力弱。

---

## 4. Quivr：The-Vibe-Company 时代的 Go 重写（专节）

### 4.1 重写时间线（git 考古实证）

- 旧史：仓库 2023-05-12 init（Python "第二大脑"，root commit `921d7e250`）【核心 git log --reverse】；
- **2026-09-03**：当前历史出现第二个 root（orphan 分支）`88f692141`「docs(architecture): define quivr v2 foundation」——V2 从零开分支，未沿用旧提交历史【核心 `git rev-list --max-parents=0 HEAD` 返回两个 root】；
- **2026-09-15**：go.mod 首次提交（PR #8「add the first scoped persistent Go API」）【核心 git log --diff-filter=A -- go.mod】；
- 冻结基线 67a6c0e9f（2026-10-04 合并 PR #3930「run the vector index on a dedicated machine」）：V2 落地约 **5 周**，README 自评"Status: evaluation stage. API is v0… Do not run it in production yet"【文档 README.md】。

### 4.2 现役架构形态

产品定位彻底变了：从"和你的文档聊天"变为「**把持续内容流变成搜索与监控的引擎**」（news/RSS/邮件流监测场景），README 架构图与正文明确：核心引擎保持通用，格式/AI 模型/业务规则全部下放插件【文档 README.md】。

- **形态**：Go 模块化单体。单 `quivr` 二进制提供 `api`、`worker`、`migrate`（另有 `plugin` CLI 与 online 运维命令、`storage`）【核心 cmd/quivr/main.go + internal/app/fixture_config_test.go 的命令表】；另有 `cmd/quivr-autoscaler`（按队列积压自动扩 worker，支持 KEDA/Railway）与 `cmd/quivr-plugin-api`、`cmd/quivr-reference`【核心 cmd/ 目录】；
- **依赖栈**（deploy/compose/compose.yaml，compose 只起依赖，api/worker 是 `make dev` 本地跑的 Go 进程）【核心】：PostgreSQL 17（事务目录：receipt/changes/manifest）、Temporal 1.8.3（**持久化编排**）、SeaweedFS（S3 兼容，canonical 字节+衍生物）、Weaviate（lexical+vector 双路）、TEI（钉死 `multilingual-e5-small` 384 维嵌入）；
- **与旧 Python 版的关系**：旧 Python 代码（quivr-core 库、FastAPI 服务）已不在当前树中；本仓库 git 历史仍可 checkout 旧版。独立的 `QuivrHQ/quivr-core` Python 库是否继续维护**本轮未核实**（存疑，见 §7）。根目录的 `multimodal-rag/` 是**空目录**（仅目录壳）⚠️，`quivr-search/` 是纯前端 demo（`make demo` 起的静态浏览器 UI）【核心目录内容】。

### 4.3 RAG 功能在哪、怎么流

quivr V2 的"RAG"是围绕**内容不可变模型**重做的（CONTEXT.md 定义了 Corpus/Record/RecordVersion/Part/NormalizedContent/Segmentation/Derivation/Blob 的领域语言，明令"Document 不是通用词"【文档 CONTEXT.md】）：

摄取链：
1. 客户端/连接器 → REST v0（OpenAPI 3.1 契约在 `contracts/http/v0/openapi.yaml`）→ api 进程写 PG（commit receipt + intent），投 Temporal 工作流【文档 README 架构图 + 核心代码分布印证】；
2. worker 跑 Temporal 工作流：`internal/orchestration/temporal/`（ingestion/backfill/connectors/acquire 等 workflow + activity，如 `backfill.go#backfillWorkflow`）【核心】；
3. 处理细节在 `internal/processing/`（ingestion_pages 分页摄取、enrichment、derivation 可复现衍生物、serving_projection）；**文本先分段即刻可搜（lexical），嵌入等富化后台补齐，混合搜索在向量重建期间保留关键字结果**——README 称之为 "Useful early, richer later"【文档 README.md，实现散布 internal/processing/enrichment.go 与 internal/retrieval/rebuild.go，⚠️ 未逐行核对调度细节】；
4. 插件承担具体能力：`plugins/` 下一方插件 core-ingest（切分入 Weaviate）、core-retrieve、hosted-embed、jev-rerank、pdf-text、rss、m365-mail、alerts、object-storage-archive 等；插件经 `internal/plugins/`（connector/ingestion/call 等接口）挂进引擎【核心 plugins/ 目录 + internal/plugins/*.go】。

检索链：api 进程收搜索请求 → Weaviate 混合召回 → **每个命中从 PG/S3 canonical 存储重水合并重鉴权**（README "Honest search"：依赖挂了返回错误而不是空成功）【文档 README.md；核心对应 internal/retrieval/retrieval.go/composition.go，⚠️ 重鉴权代码位未逐行定位】。

### 4.4 亮点与短板

亮点：把"可重建索引"（PG+S3 是真相，搜索索引只是投影）和"幂等写入"当第一性原理，这是五家中数据治理观最强的；Temporal 做持久编排，长任务/重试/补偿全部外包给成熟组件；嵌入模型钉死单版本，避免向量空间漂移。
短板：太年轻（5 周 + v0 + 自评别上生产）；RAG 呈现形态是"搜索引擎/监测"，没有聊天/引用问答产品面；中文场景无专门优化；社区资料几乎为零。

---

## 5. Kotaemon：单进程 Gradio 技术展示台

### 5.1 服务拆分与形态

**一个 Python 进程就是全部**：`app.py` → `ktem.main.App().make()` → `demo.queue().launch()`——UI、API、索引、检索、聊天全在 Gradio 进程内，`queue()` 是 Gradio 内置请求队列（无 broker）【核心 app.py】。仓库结构是 monorepo 双包：`libs/ktem/`（应用框架：Gradio 页面、SQLModel/alembic 数据层、索引管理、pluggy 扩展协议）+ `libs/kotaemon/`（RAG 组件库：loaders/parsers/embeddings/llms/indices/rerankings/storages，基于 theflow 管道框架）【核心目录结构】。注意任务提示里的 `kotaemon/` 根目录在当前基线不存在，代码在 `libs/` 下（README 的旧结构描述已过时⚠️）。

存储全家桶（flowsettings.py 默认值）【核心】：
- 元数据：SQLite（SQLModel，alembic 迁移在 libs/ktem/migrations）；
- 向量库：`KH_VECTORSTORE` 默认 **Chroma**（本地目录），注释里可选 LanceDB/Milvus/Qdrant；
- 文档库：`KH_DOCSTORE` 默认 LanceDBDocumentStore（可选 ES/SimpleFile）；
- 无对象存储、无消息队列、无独立嵌入服务。

### 5.2 RAG 数据流

摄取链（同步流式，在 Gradio 请求里跑）：
1. UI 上传 → `libs/ktem/ktem/index/file/ui.py`（流式进度，`indexing_pipeline.stream(files, reindex=…)`）【核心 ui.py#L1244-1248】；
2. `libs/ktem/ktem/index/file/pipelines.py#IndexPipeline`：loader（`libs/kotaemon/kotaemon/loaders/`，docling/azure/… 多后端）→ splitter（chunk_size/overlap 来自设置）→ embedding（`embedding_models_manager`）→ 双写 docstore + vectorstore（`run_embedding_in_thread` 可选线程化嵌入）【核心 pipelines.py#L330-L375】；
3. FileIndex 为每个知识库**动态建 SQL 表**（`index__{id}__source` / `index__{id}__index`，用 type() 运行时造 ORM 类）【核心 index/file/index.py#_setup_resources】。

检索链：`pipelines.py#DocumentRetrievalPipeline`（多 retriever 可插：默认向量 + 可选 GraphRAG/LightRAG/knet 图检索，`index/file/graph/`、`index/file/knet/`）→ rerank（`libs/kotaemon/kotaemon/rerankings/`）→ 聊天页组装 citation。GraphRAG/LightRAG 作为索引/检索管道变体接入而非独立服务【核心目录 + pipelines 结构】。

### 5.3 扩展点

- pluggy 钩子协议：`libs/ktem/ktem/extension_protocol.py#ktem_declare_extensions`（id/name/version/hook 声明式扩展，文档明确"不用 fork 就能加能力"）【核心】；
- 组件级：kotaemon 库的每个环节（loader/embedding/rerank/vectorstore）都是 theflow Component，配置里 `__type__` 字符串反序列化即换实现（`ktem/components.py#get_vectorstore`）【核心】；
- 模型池：`embedding_models_manager`/`llms_manager` 注册表 + settings UI 热选。

### 5.4 亮点与短板

亮点：**技术雷达最全**（GraphRAG/LightRAG、多 rerank、多种 citation UI 都有开关可试），适合当"RAG 算法试验台"；单文件配置换存储的 `__type__` 反序列化模式简洁好抄。
短板：单进程无法承载多人并发索引（嵌入在请求线程里做）；无任务持久化（进程挂了索引进度丢）；项目低活跃（README/提交 2026-05 后停滞，本轮对象清单已注明）；生产化（鉴权除简单登录外、审计、横向扩容）基本没做。

---

## 6. 自建参考架构小结：从五家各取什么

**值得抄的：**

1. **骨架（dify + ragflow 共同验证）**：同步 REST 只做控制面（上传/查询/状态），解析-切分-嵌入-入库全部下异步任务系统，任务态落关系库、消息只做唤醒。这是企业 RAG 的第一决策，五家无一例外。
2. **任务可靠性（ragflow）**：worker 心跳 + 任务租约 + MySQL 调度行 poll 与 NATS notify 混合消费、断点续跑。自建用 Redis Streams / NATS JetStream 均可复刻这套语义；dify 的 Celery 多队列（dataset/priority_dataset 分池）则是租户公平性的低成本解法。
3. **进程隔离的最小实现（anything-llm）**：如果本地跑嵌入/解析模型，把嵌入放进可牺牲的子进程（IPC 汇报进度），OOM 不伤主服务——比引入完整队列轻一个量级，适合从 0 到 1 阶段。
4. **数据治理观（quivr）**："关系库+对象存储是 canonical 真相，向量索引是可重建投影" + 幂等写入 + 版本不可变。企业场景文档会改、嵌入会换模型，索引可重建是救命设计；嵌入模型钉版本防漂移同样值得写进规范。
5. **模型接入的运行时插件化（dify）**：model provider 走独立守护进程 + 租户级热装，新模型上线不重启主服务。ragflow 的编译期 factory switch 是反面教材（加 provider 必须发版）。
6. **向量+全文同库（ragflow/quivr）**：混合检索若用 ES/Infinity/Weaviate 这类双能力引擎，可省掉 dify 式"向量库 + jieba 关键字库"双写一致性问题；若已定纯向量库，dify 的 keyword_index 分离是现成参照。
7. **可牺牲的 demo 面（quivr）**：核心引擎对 API 契约（OpenAPI 3.1 + conformance 用例）严肃，UI 只是薄壳——自建系统先把检索 API 契约定稳，前端随便换。

**反面教材/避坑：**

1. ragflow 的 Go 大迁移说明**文档型项目的重构阵痛**：2026-03 起重写，冻结时 Python 侧已删到只剩残骸，外部资料全部失效。自建选型时要看"活跃实现的语言"而不是 README 宣称。
2. quivr V2 证明 star 数与"能抄的代码量"无关：39.6k star 的仓可能 5 周前刚清零重来，且新形态未必是你想要的产品（它已不是聊天式 RAG）。
3. anything-llm 的无队列模式天花板明显：单容器、任务不持久化，文档量上千后嵌入吞吐与可靠性都成问题——可作起步形态，设计时要预留换队列的缝（它的 DocumentManager/collector 边界切分得好，替换成本可控）。
4. kotaemon 的动态建表（每知识库一套 SQL 表）在库数量大时是运维灾难，自建应学 dify/ragflow 用统一分表 + dataset_id 外键。
5. dify 的全家桶默认部署 10+ 容器，对一个"只要知识库问答"的企业场景过重——自建时应按 dify 的**分层**（api/worker/库/插件守护进程）学拆分，而不是照抄它的服务数量。

---

## 7. 证据与存疑清单

### 基线复核

| 仓库 | 基线（git log -1 实测） | 与任务书一致性 |
|---|---|---|
| ragflow | deb1235be41d…（2026-10-12） | 一致 |
| dify | 79effdd498…（fix(api): preserve literal NA…） | 一致 |
| anything-llm | 2a10d052a1…（Fix raw think blocks…） | 一致 |
| quivr | 67a6c0e9f3…（Merge PR #3930 dedicated vector index） | 一致 |
| kotaemon | 9ad3e4e49a…（feat: integrate PaddleOCR…） | 一致 |

### 关键证据索引（均为【核心】除注明外）

- ragflow：`docker/docker-compose-base.yml`；`docker/launch_backend_service.sh`；`cmd/ragflow_server.go#serverArgs`；`internal/server/config/queue_engine_config.go`；`internal/ingestion/service/ingestion_service.go#handleAndExecute`；`internal/service/ingestion_task_service.go#PublishTaskMessage`；`internal/ingestion/{component,pipeline,task}/`；`internal/service/nlp/retrieval.go#RetrievalService`；`internal/engine/clickhouse/clickhouse_ee.go`（EE 桩）；`internal/entity/models/factory.go#CreateModelDriver`；LICENSE（git log 显示自 2023-12-12 未改动，纯 Apache-2.0）；`AGENTS.md`（【文档】Go 迁移状态）。
- dify：`docker/docker-compose.yaml`；`api/tasks/document_indexing_task.py`；`api/core/indexing_runner.py#IndexingRunner`；`api/core/rag/retrieval/dataset_retrieval.py#DatasetRetrieval#retrieve`；`api/core/rag/datasource/vdb/vector_type.py#VectorType`；`api/core/rag/datasource/keyword/jieba/`；`api/configs/feature/__init__.py#PluginConfig`；`api/core/plugin/impl/model_runtime_factory.py`；`api/tasks/rag_pipeline/rag_pipeline_run_task.py`；LICENSE（Apache-2.0 附加条款原文）。
- anything-llm：`docker/docker-compose.yml`；`docker/docker-entrypoint.sh#L25-27`；`server/utils/collectorApi/index.js#CollectorApi`；`collector/utils/constants.js#SUPPORTED_FILETYPE_CONVERTERS`；`server/jobs/embedding-worker.js`（IPC 注释）；`server/utils/BackgroundWorkers/index.js#BackgroundService`；`server/prisma/schema.prisma`；`server/utils/vectorDbProviders/`；`server/utils/chats/apiChatHandler.js#L354`；LICENSE（MIT）；`TERMS_SELF_HOSTED.md`（【文档】air-gap 宣称）。
- quivr：`README.md`（【文档】架构图/状态自评）；`CONTEXT.md`（【文档】领域语言）；`cmd/quivr/main.go`；`deploy/compose/compose.yaml`；`internal/orchestration/temporal/backfill.go#backfillWorkflow`；`internal/processing/`、`internal/retrieval/`、`plugins/`、`internal/plugins/`；git 考古（双 root、go.mod 首提 2026-09-15、orphan root 2026-09-03）；LICENSE（MIT，The Vibe Company 2026）。
- kotaemon：`app.py`；`libs/ktem/ktem/main.py#App`；`libs/ktem/ktem/index/file/index.py#_setup_resources`；`libs/ktem/ktem/index/file/pipelines.py#IndexPipeline/#DocumentRetrievalPipeline`；`libs/ktem/ktem/components.py#get_vectorstore`；`flowsettings.py#KH_VECTORSTORE/KH_DOCSTORE`；`libs/ktem/ktem/extension_protocol.py`；LICENSE.txt（Apache-2.0）。

### 存疑清单（未定论，不臆测）

1. **quivr-core Python 库去向**：旧 `QuivrHQ/quivr-core` 独立仓库是否仍在维护、是否有 v1 停服公告——本轮未克隆未核实。若后续维度需要旧 quivr 的 RAG 实现作参照，只能 checkout 本仓 2026-09 前历史提交。
2. **quivr "重水合+重鉴权"检索的精确代码位**：README 宣称了语义，`internal/retrieval/` 结构印证方向，但未逐行定位鉴权调用点，标 ⚠️。
3. **dify rag_pipeline 的产品成熟度**：`api/tasks/rag_pipeline/` 与 `models.dataset.Pipeline` 是新代码，是否有 UI/文档配套未查，后续"检索与索引策略"维度应跟进。
4. **ragflow Python 残余的删除进度**：AGENTS.md 说 pending removal，冻结时 `rag/` 只剩 prompts、`api/` 已不存在，但 `sdk/python/`、`ragflow_deps/download_deps.py` 等仍在（【文档】AGENTS.md 迁移清单），最终形态可能再变。
5. **anything-llm EmbeddingRerankers 是否接入主检索链**：目录存在，apiChatHandler 主链未见调用，标 ⚠️（可能仅部分 provider 用）。
6. **kotaemon 活跃度**：README 与提交停在 2026-05（对象清单亦注明），后续维度引用其能力时注意不再对码新版本。
