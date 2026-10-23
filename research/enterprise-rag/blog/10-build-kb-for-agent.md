# 10 | 实战设计：Python 自建轻量知识库服务，给 deepagents 供数

> 本文事实基于 2026-10 冻结的开源源码基线与当日可访问的官方文档，源码基线 commit 见文末参考节。

先亮明身份：这是**设计方案篇**，不是上线复盘。前九篇把 22 个仓库的源码结论与四家厂商口径摊开之后，这一篇把它们收拢成一份可以直接开工的实施蓝图——需求边界、架构、逐条设计决策、MCP 接入、数据模型、里程碑与验收口径。设计里所有「别人验证过」的构件都标注了出处，出处全部来自前九篇的调研档案；尚未验证的部分我会明说。**本文没有一行代码跑在生产上**，把它当作一份诚实的图纸，而不是胜利宣言。

## 一、需求与边界：先画清楚要做什么

需求五条：

1. **企业内部知识库**：私有化部署，语料以中文为主（PDF/Office/扫描件混杂），量级在「百万 chunk 以下、数百用户以内」；
2. **消费者是 deepagents**（LangChain 系的 Python 深度 agent 库），不是人——不需要聊天界面，不需要 workflow 可视化编排；
3. **要上传前端**：内部用户（或 agent 自身）能把文档喂进来；
4. **轻量部署**：一台机器或小集群拉得起来，容器数个位数；
5. **可二开**：代码量小到团队能读完、能改。

这个需求面为什么导向自建薄服务而不是装一个平台？逐家过一遍第 2 篇的结论：

- **ragflow**：RAG 专项能力最强，但正处于 Go 重写期（文档与社区资料大面积失效），`use_kg` 图检索是半移植回归项；CE 版的 SSO/审计/配额是空壳（OAuth handler 全部 not implemented），模型 key 明文存库；默认部署要拉起一整套存储全家桶（`infiniflow/ragflow@deb1235be internal/handler/user_auth_ee.go`、`docker/docker-compose-base.yml`）。
- **dify**：10+ 容器起步，对「只要知识库」的场景过重；RAG 检索层偏浅（无查询变换、无 RRF、扫描件默认无解）；telemetry 默认开启上报；而且 agent_v2 明确禁止知识库挂 agent 工具（第 9 篇）——与「给 agent 供数」的诉求相反。
- **anything-llm**：单容器最轻，但无混合检索、无 rerank 主链、任务无持久化，文档量上千后天花板明显。
- **kotaemon / quivr**：一个是单进程演示级，一个 5 周龄 v0 自评别上生产。

更本质的一条：**平台的两大价值——面向人的产品面（聊天 UI、编排、多租户运营）与治理面——前者本需求用不上，后者恰好是五家全部缺失、必须自研的部分**（文档级权限，第 7 篇结论）。调研报告的路线 C（平台骨架 + 自建治理层）适合「面向人的知识问答」；而当消费者是 agent 时，平台的产品面价值归零，剩下的就是「检索质量 + 治理 + 工具面」三件事——这三件事自建薄服务全部做得到，还免掉了背一整个平台的运维与 license 负担。第 9 篇已经论证过这个形态：**agent 住客户端（deepagents 进程），知识库做工具服务器**（quivr 的 MCP 反转姿态是同款）。

## 二、总体架构：一个控制面进程 + 三个旁路容器

```
 ┌──────────────┐        ┌──────────────────────────┐
 │ 上传前端       │        │ deepagents（消费者进程）    │
 │（静态页，薄壳）│        │ agent 循环住在这里          │
 └──────┬───────┘        └────────────┬─────────────┘
        │ REST 上传/状态                │ MCP（stdio/SSE）调用工具
        ▼                              ▼
 ┌────────────────────────────────────────────────┐
 │ FastAPI 进程（控制面 + 检索面 + MCP server）      │
 │  · REST：upload / status / search / admin       │
 │  · FastMCP：search / upload / list_documents    │
 │  · 检索管线（同步）：双路召回→RRF→rerank→ACL 过滤  │
 │  · 摄取调度：写 tasks 表 → 唤醒 worker 子进程      │
 └───────┬───────────────────────────┬────────────┘
         │ 任务                       │ 读写
 ┌───────▼────────┐        ┌─────────▼──────────────┐
 │ 摄取 worker     │        │ SQLite（元数据+FTS5+向量）│
 │（可牺牲子进程）  │        │ 或 LanceDB（向量）+      │
 │ 解析→切分→嵌入   │        │ SQLite（元数据+FTS5）    │
 └───┬────────┬───┘        └────────────────────────┘
     │        │                        ▲
 ┌───▼───┐ ┌──▼──────┐        ┌────────┴─────────────┐
 │MinerU │ │docling- │        │ TEI 容器（嵌入+重排）    │
 │api_   │ │serve    │        │ bge-m3 / bge-         │
 │server │ │         │        │ reranker-v2-m3（钉版本）│
 └───────┘ └─────────┘        └──────────────────────┘
 原始文件与解析产物落本地对象目录（canonical 真相，索引可随时重建）
```

组件清单与出处：

| 组件 | 职责 | 参照来源（前九篇结论） |
|---|---|---|
| FastAPI 进程 | 控制面 REST + MCP server + 同步检索管线 | 五平台共识：同步 REST 只做控制面，重活全部异步化〔第 2/6 篇〕 |
| 摄取 worker 子进程 | 解析→切分→嵌入→入库，OOM 只杀 worker | anything-llm 的最小进程隔离（`server/jobs/embedding-worker.js` IPC 注释「OOM 只杀 worker 不杀主服务」）〔第 6 篇〕 |
| tasks 任务表 | 状态机 + 心跳 + 租约，断点可续 | ragflow 样板：worker 心跳 + 任务租约 + 关系库调度行 poll + 队列 notify 混合消费〔第 6 篇〕 |
| MinerU api_server | 扫描件/复杂 PDF 解析（中文 OCR 一等公民） | 第 3 篇双服务拓扑〔dim02〕 |
| docling-serve | 原生 PDF/Office/HTML 解析（格式面最宽） | 同上，REST `/v1/convert/source`（ragflow Go 桥调的就是它） |
| TEI 容器 | bge-m3 嵌入 + bge-reranker-v2-m3 重排 | kotaemon `TeiFastReranking`、ragflow compose 的 tei-cpu/gpu profile 同款路径〔第 5 篇〕 |
| SQLite / LanceDB | 元数据 + 全文 + 向量 | anything-llm 默认 LanceDB 同款（`server/utils/helpers/index.js:88`）；SQLite 见 §3.2 |

三条铁律，全部来自第 6 篇的数据治理结论：**控制面与数据面分离**（同步链路绝不跑解析和嵌入）；**摄取任务化**（任务态落关系库，进程死了任务可续）；**索引可重建**（原始文件与解析产物是 canonical 真相，向量索引只是投影——quivr 把这条当第一性原理，嵌入模型钉死单版本防向量空间漂移，是五家中数据治理观最强的〔第 6 篇〕）。

## 三、关键设计决策逐条

### 3.1 解析：双服务拓扑，不自己造解析器

按文件类型路由：原生 PDF/Office/HTML → docling-serve；扫描件/图片/公式重的 PDF → MinerU api_server（medium 档起步，重要文档 high 档）。这个拓扑不是我的发明——ragflow Go 版自己就是「自研轻量 + 外挂重炮」的示范，它的 `parse_method` 分发支持 deepdoc/mineru/docling 等七个后端（`infiniflow/ragflow@deb1235be internal/parser/pdf_parser_common.go:49-58`，MinerU 桥 `pdf_parser_mineru.go`、docling 桥 `pdf_parser_docling.go`）。

选型依据（第 3 篇）：MinerU 4.0 的中文 OCR（ch_PP-OCRv6）是一等公民、公式表格标配，basic 档 0.8GB 纯 CPU 可跑（`opendatalab/MinerU@b7f3dd0c mineru/model/registry.py`、README 硬件表）；docling 的 DoclingDocument 结构输出最完整（标题层级/表格/bbox/页码原生保留），格式面最宽（`docling-project/docling@dd477a9f`）。

切分遵循「结构感知而非盲切」：拿解析器的结构输出（标题边界、表格整块、页码）指导切分，平台侧只做 token 上限微调（256-512 递归打底）——dify 的「分隔符含句号的递归盲切 + pypdfium2 纯文本抽取」是第 3 篇点名的反面教材。

⚠️ 一个必须写进采购清单的风险：解析模型的**权重 license 全线未核实**（HF 在调研网络环境不可达；IBM 系模型有 CC-BY-NC 历史先例；MinerU 代码 license 是 Apache-2.0 但带 MAU/收入阈值与署名附加条款）。上线前逐卡确认，这是整个调研的最大遗留风险项。

### 3.2 存储：SQLite（FTS5 + sqlite-vec）或 LanceDB，起步不引入独立引擎

这个量级（< 百万 chunk、单机起步）的选型逻辑（第 4 篇）：

- **方案 A：SQLite 一把梭**——元数据、全文（FTS5）、向量（sqlite-vec 扩展）同库。中文 BM25 的做法抄 ragflow 的 ES 路线：**应用层 jieba 预分词后写入**（ragflow 原注释「Elasticsearch has no server-side rag tokenizer」，`internal/engine/elasticsearch/chunk.go:2009`）——FTS5 同样没有内置中文分词，预分词字段 + trigram 兜底是同构方案。零新增组件、事务一致、备份就是复制文件。（FTS5 与 sqlite-vec 属生态通识组件，未做源码级验证，设计选型。）
- **方案 B：LanceDB 存向量 + SQLite 存元数据与全文**——anything-llm 默认即此（LanceDB 本地嵌入式），向量检索性能与过滤能力更好，代价是两个存储。

刻意**不选**的：ES/Infinity（为十万级 chunk 拉一个检索引擎集群，运维不成比例）；qdrant（第 4 篇的坑：服务端 BM25 稀疏向量只按空白切分，中文整句成 token 不可用）；milvus（留作升级路径——它内置 jieba 的 BM25 Function 与库内 rrf/weighted 融合是中文混合检索的正解，`tests/go_client/testcases/full_text_search_test.go` 有中文活测试）。

存储访问收敛在一个 repository 接口后面（hybrid_search / insert / delete_by_doc 三个方法），**pgvector（已有 PG 时）与 milvus 都是配置级切换**——kotaemon 的 docstore/vectorstore 双库分离证明了「向量库不存 chunk 正文」时换库零搬迁（第 4 篇），我们让 chunk 正文常驻 SQLite、向量列可外移，是同一个思想的轻量版。

### 3.3 嵌入与重排：TEI 容器，模型钉版本

私有化部署下，嵌入用 bge-m3、重排用 bge-reranker-v2-m3，都跑在 HuggingFace TEI 容器里（模型选型属生态通识，未源码级验证；TEI 承载 bge 系是 kotaemon/ragflow 的同款路径）。两条纪律：

- **模型版本钉死并记录在每个 chunk 上**（embed_model 字段）——quivr 钉死 E5-small 的先例：嵌入模型一换，向量空间漂移，全库必须重嵌。钉版本 + 索引可重建，是这套设计的救命组合〔第 6 篇〕。
- **重排分数进融合公式前归一到 [0,1]**，且 cross-encoder 喂 chunk 原文、不喂分词文本——ragflow `NormalizeRerankScores` 的 min-max/clamp 双分支与「喂原文」的教训注释值得直接抄（`infiniflow/ragflow@deb1235be internal/service/nlp/reranker.go`）〔第 5 篇〕。

### 3.4 检索配方：第 5 篇的标准配方原样落地

双路召回（FTS5 BM25 + 向量 kNN，召回窗口给足——ragflow 口径 knn_top_k 1024、rerank 候选 64）→ **RRF 融合（k=60）**——免调参、免疫两路分数尺度不一，跨实现一致（llama_index k=60、haystack k=61、Azure 固定 60；若产品需要可解释旋钮，ragflow 验证过的锚点是关键词 0.7 / 向量 0.3，`internal/entity/skill_search.go:52`，但两路分数必须同尺度）→ TEI rerank 取 top-k → **引用溯源**。

引用溯源对 agent 消费者尤其重要（第 5/8 篇）：ragflow 双机制里，我们首选**确定性 chunk_id 提取**路线（`internal/agentic_rag/citations.go`——工具输出本就带 `chunk_id` 溯源字段，agent 引用了不存在的 ID 就是幻觉证据，等于免费的在线幻觉检测锚点），embedding 句级归因作后续增强（`internal/service/citation.go#InsertCitations`）。查询侧先做 LLM 关键词增强（中文场景性价比高，第 5 篇排序：多查询扩展 > 关键词增强 > HyDE 慎用），预算允许再评估索引侧 Contextual Retrieval——但要记住第 5 篇的提醒：没有 prompt caching 经济学，这类 LLM 增强索引会贵一个量级。

### 3.5 文档级 ACL：前置过滤，不是事后裁剪

第 7 篇的核心缺口：五个开源平台的权限粒度全部止步于知识库/工作区级，「谁能看到哪份文档并在检索结果里过滤」必须自研。方案直接抄托管服务的成熟模式（第 9 篇厂商互证）：

1. **ACL 随索引摄入**：acl_entries 表（doc → user/group），并把允许组冗余成 chunk 的可过滤字段（Google 的 `acl_info.readers.principals` 随文档摄入是同构）；
2. **查询时引擎内过滤**：把当前用户所属组转成 SQL WHERE / 向量库 metadata filter，在检索执行时下推——**勿在应用层 post-trim**（Azure 官方口径：引擎内过滤比加载大结果集到应用再裁剪快，且权限内容不进 LLM 上下文）；
3. **rerank 前兜底校验**：命中文档二次鉴权，防御性兜底（第 7 篇方案）；
4. **权限增量同步**：组关系变更时增量更新受影响文档的冗余字段。

审计与凭据一并最小集处理：audit_events 表 append-only（quivr 的 DB 触发器防篡改 + 定长保留设计整体搬，`migrations/20261006T0039Z_audit_events.sql`）；查询级审计字段对齐 dify dataset_queries（谁/何时/查了什么/返回哪些来源）；模型凭据走环境变量/secret manager，不学 ragflow 的明文存库（第 7 篇反面教材）。

### 3.6 评测门禁：上线前就立起来

第 8 篇方案的直接落地：ragas TestsetGenerator 合成候选问答（知识图谱 + persona + multi_hop），**人工抽检修正后作为黄金集**（合成集只做回归基线）；指标组合先跑无参考三件（faithfulness / answer_relevancy / ContextUtilization），有标注后补 context_recall（ID-based 版零 LLM 成本）；deepeval 的 pytest `assert_test` 断言挂 CI 做变更防护。中文硬前提：judge prompt 先用约 50 条人工双评验证 judge-人一致性，过了才配当门禁。

## 四、MCP 接入：deepagents 侧与服务侧

### 4.1 deepagents 怎么接（本地克隆验证过）

deepagents（本地克隆 `9e7d62ff6`，2026-09-11）的 README 特性清单明写「**Tools — bring your own functions or any MCP server**」，快速上手就是 `create_deep_agent(model=..., tools=[...])`。两条接入路径：

- **轻路径**：agent 代码里用 `langchain-mcp-adapters` 的 `MultiServerMCPClient` 把我们的 MCP server 的一组工具 load 成 LangChain tools 塞进 `tools=[...]`；
- **重路径**：deepagents 自带的 talon 运行时有完整的 MCP 工具生命周期管理——`libs/talon/deepagents_talon/mcp.py` 实际存在（本地验证），其中 `MCPToolProvider` 负责 load/refresh/reload MCP 工具、默认配置文件在 `.deepagents/.mcp.json`、并额外注入 `reload_mcp_configuration` / `get_mcp_server_status` 等管理工具，OAuth server 也有对应支持。它的 import 就是 `from langchain_mcp_adapters.client import MultiServerMCPClient`——两条路径底层同源。

### 4.2 服务侧：FastMCP 暴露三个工具

服务侧用 FastMCP（Python 生态的 MCP server 框架，生态通识）暴露工具面。工具不是 API 的直译，**工具描述是写给 LLM 看的**——kotaemon 的 DocSearchTool 是教科书式写法（「缺私有信息就搜这里，query 越具体越好」，`Cinnamon/kotaemon@9ad3e4e4 libs/ktem/ktem/reasoning/react.py`）：

- `search(query, top_k, doc_filter?)`：跑 §3.4 完整配方，返回命中块（chunk_id、doc_id、标题、页码、片段、分数）——溯源字段齐全，agent 才能带引用回答；
- `upload(file_path/content, metadata, acl?)`：投摄取任务，返回 task_id 与 doc_id（quivr 的 ingest profile 允许 agent 写入，是同款开放；ragflow 的 MCP server 没有上传工具，这是我们面向 agent 的差异点）；
- `list_documents(filter?)`：列出权限内文档与处理状态，对应 quivr `list_corpora` 的「先看有什么再搜」剧本。

### 4.3 对照 ragflow 内置 MCP server 的参数面

ragflow Go 版内置了官方 MCP server（`infiniflow/ragflow@deb1235be internal/mcp/server.go`），三个工具：`ragflow_retrieval` / `ragflow_list_datasets` / `ragflow_list_chats`。检索工具的参数面（`RetrievalRequest` 结构体 + `tools.json` schema）值得逐条对照：`dataset_ids`（缺省搜全部库）、`document_ids`、`question`、`page/page_size`、`similarity_threshold`（默认 0.2）、`vector_similarity_weight`（默认 0.3）、`top_k`、`rerank_id`、`keyword`（LLM 关键词增强开关）。两个值得抄的设计：**工具描述在 tools/list 时动态注入当前数据集清单**（把「有哪些库」写进 description，LLM 不用盲猜 dataset_id）；**60 秒超时中间件**统一卡住所有工具调用。两个我们不抄的：检索参数暴露过多（`vector_similarity_weight` 这类旋钮对 LLM 是噪音，MVP 固定服务端）；没有上传与权限上下文（ragflow 的 MCP 以 userID 隔离，但无文档级语义）。

## 五、数据模型草案

SQL 风格示意（**设计草案**，字段清单以够用为度；开工时按此建表再演化）：

```sql
-- 文档表：canonical 元数据；raw_object_key 指向原始文件与解析产物目录
CREATE TABLE documents (
  id            TEXT PRIMARY KEY,          -- ULID
  title         TEXT NOT NULL,
  source_uri    TEXT,                       -- 上传来源/路径
  content_hash  TEXT NOT NULL,              -- 内容哈希去重（LightRAG 同思路）
  mime_type     TEXT NOT NULL,
  page_count    INTEGER,
  parser        TEXT NOT NULL,              -- mineru | docling
  parse_effort  TEXT,                       -- mineru: flash/medium/high
  status        TEXT NOT NULL,              -- uploaded|parsing|chunked|indexed|failed
  acl_mode      TEXT NOT NULL DEFAULT 'private',  -- private|group|public
  owner         TEXT NOT NULL,
  raw_object_key TEXT NOT NULL,             -- 对象目录键（索引可重建的真相源）
  created_at    TIMESTAMP, updated_at TIMESTAMP
);

-- 块表：正文常驻此表；向量列可外移 LanceDB；keywords 是 jieba 预分词（FTS5 用）
CREATE TABLE chunks (
  id            TEXT PRIMARY KEY,
  doc_id        TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  content       TEXT NOT NULL,
  token_count   INTEGER,
  heading_path  TEXT,                       -- 结构感知切分的标题层级
  page_no       INTEGER, bbox_json TEXT,    -- 溯源定位
  keywords      TEXT,                       -- 预分词结果（空格连接）
  embed_model   TEXT NOT NULL,              -- 钉版本：bge-m3@<rev>
  allowed_groups TEXT,                      -- ACL 冗余（前置过滤下推字段）
  created_at    TIMESTAMP
);

-- ACL 表：文档级权限（第 7 篇最大缺口的补齐）
CREATE TABLE acl_entries (
  id             TEXT PRIMARY KEY,
  doc_id         TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  principal_type TEXT NOT NULL,             -- user | group
  principal_id   TEXT NOT NULL,
  permission     TEXT NOT NULL DEFAULT 'read',
  granted_by     TEXT, created_at TIMESTAMP,
  UNIQUE(doc_id, principal_type, principal_id, permission)
);

-- 审计表：append-only（quivr 触发器防篡改模式）
CREATE TABLE audit_events (
  id          TEXT PRIMARY KEY,
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,                -- search|upload|grant|revoke|...
  target_type TEXT, target_id TEXT,
  outcome     TEXT NOT NULL,                -- accepted | refused
  request_id  TEXT, detail_json TEXT,
  created_at  TIMESTAMP NOT NULL
);

-- 任务表：摄取状态机（ragflow 心跳+租约样板的最小化）
CREATE TABLE tasks (
  id           TEXT PRIMARY KEY,
  doc_id       TEXT REFERENCES documents(id),
  type         TEXT NOT NULL,               -- parse | embed | index
  status       TEXT NOT NULL,               -- pending|leased|running|done|failed
  lease_owner  TEXT, lease_until TIMESTAMP, -- 租约：worker 崩溃后任务可被重新认领
  heartbeat_at TIMESTAMP,
  attempts     INTEGER NOT NULL DEFAULT 0,
  error        TEXT, created_at TIMESTAMP, updated_at TIMESTAMP
);
```

## 六、MVP 里程碑与验收口径

| 里程碑 | 内容 | 验收口径 |
|---|---|---|
| M0（第 1 周） | 骨架端到端：上传 → docling 解析 → 切分 → TEI 嵌入 → SQLite 入库 → 单路向量检索 → MCP search 接 deepagents 跑通一次带引用问答 | deepagents 回答能落到 chunk_id 溯源 |
| M1（第 2-3 周） | 完整检索配方：jieba 预分词 FTS5 + 双路召回 + RRF + TEI rerank；50~100 份真实企业文档（含扫描件）上线 | **解析抽检**（表格/公式/页码正确率人工评分）；黄金集基线（faithfulness / context_recall） |
| M2（第 4-5 周） | 异步任务表 + worker 子进程（心跳/租约/重试）；MinerU 扫描件通道按类型路由；ACL 前置过滤 + 审计表 | **权限越权测试全绿**（无权用户在检索结果、MCP 工具返回、引用三个面都拿不到受控内容）；任务断点可续 |
| M3（第 6 周起） | 评测门禁进 CI（deepeval + 黄金集）；中文 judge 校准（约 50 条人工双评）；在线抽样评测与弱信号回灌 | 门禁能卡住检索层回归；judge-人一致性达标 |

这套验收口径直接取自调研报告的实施蓝图：解析抽检、context_recall、faithfulness、权限越权测试——**解析质量不达标，后面全部白搭**（第 3 篇的第一结论）。

**升级路径**（全部预留了缝，均为配置级或接口级切换）：存储 → pgvector（团队已有 PG 时，iterative_scan + 自拼混合）或 milvus 2.5+（内置 jieba BM25 + 库内 rrf/weighted 融合 + partition key 多租户），repository 接口不变；重排 → 云 API（Cohere/Jina/BGE API）替换 TEI，接口不变；解析 → MinerU 档位升级或 docling VlmPipeline 预设扩展（已成 VLM 解析聚合器，第 3 篇）；前端 → FastAPI 托管的静态页随时可换成正经管理台——quivr 的教训是反着说的：先把检索 API 契约定稳，UI 永远是薄壳。

GraphRAG 与 agentic 检索刻意不进 MVP：前者等「全局性问题占比」的数据说话（先副索引灰度，第 9 篇）；后者已经在架构里了——deepagents 自己就是 agent，我们只负责把工具面做好。

## 参考与出处

**开源源码（基线 commit 见文首引用块）**

- ragflow 治理空壳（OAuth stub）：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/handler/user_auth_ee.go
- ragflow 解析后端分发与 MinerU/docling 桥：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/parser/pdf_parser_common.go 、https://github.com/infiniflow/ragflow/blob/deb1235be/internal/parser/pdf_parser_mineru.go 、https://github.com/infiniflow/ragflow/blob/deb1235be/internal/parser/pdf_parser_docling.go
- ragflow 中文预分词注释（ES 无服务端分词）：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/engine/elasticsearch/chunk.go
- ragflow 混合检索权重锚点与召回口径：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/entity/skill_search.go 、https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/dataset/search.go
- ragflow rerank 归一化与「喂原文」：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/nlp/reranker.go
- ragflow 引用双机制：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/service/citation.go 、https://github.com/infiniflow/ragflow/blob/deb1235be/internal/agentic_rag/citations.go
- ragflow 内置 MCP server 与工具参数面：https://github.com/infiniflow/ragflow/blob/deb1235be/internal/mcp/server.go （工具 schema 在同目录 `tools.json`）
- MinerU 中文 OCR 注册与硬件档位：https://github.com/opendatalab/MinerU/blob/b7f3dd0c/mineru/model/registry.py 、https://github.com/opendatalab/MinerU/blob/b7f3dd0c/README.md （api_server：`mineru/parser/api_server.py`）
- docling 结构输出与 docling-serve：https://github.com/docling-project/docling/tree/dd477a9f/docling （serve 为独立仓，REST `/v1/convert/source` 经 ragflow Go 桥印证）
- anything-llm 嵌入子进程隔离与 LanceDB 默认：https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/server/jobs/embedding-worker.js 、https://github.com/Mintplex-Labs/anything-llm/blob/2a10d052/server/utils/helpers/index.js
- quivr 审计 append-only 触发器：https://github.com/The-Vibe-Company/quivr/blob/67a6c0e9f/migrations/20261006T0039Z_audit_events.sql
- kotaemon TEI 重排与 DocSearchTool：https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/kotaemon/kotaemon/rerankings/tei_fast_rerank.py 、https://github.com/Cinnamon/kotaemon/blob/9ad3e4e4/libs/ktem/ktem/reasoning/react.py
- milvus 中文 jieba BM25 活测试（升级路径依据）：https://github.com/milvus-io/milvus/blob/55b4415230/tests/go_client/testcases/full_text_search_test.go
- dify 查询审计参照：https://github.com/langgenius/dify/blob/79effdd498/api/models/dataset.py （`dataset_queries` 表）

**本地克隆验证（非基线表对象）**

- deepagents（本地克隆 `9e7d62ff6`，2026-09-11）：README「Tools — bring your own functions or any MCP server」；`libs/talon/deepagents_talon/mcp.py` 存在，含 `MCPToolProvider`、`.deepagents/.mcp.json` 默认配置与 `langchain_mcp_adapters.client.MultiServerMCPClient` 导入。

**证据等级说明**：开源部分为源码级（档案【核心】标注）；bge-m3 / bge-reranker-v2-m3 的模型选型、FTS5 / sqlite-vec / FastMCP 组件属生态通识，未做源码级验证；解析模型权重 license 为未闭环风险（HF 不可达）；本文所有「设计」性质的断言（数据模型、MVP 里程碑、验收口径）均为本篇产出，不是对任何已有系统的描述。

---

### 系列目录：《给 Agent 造知识库：企业级 RAG 搭建手记》

1. 企业级 RAG 全景：一篇文档到一段回答之间发生了什么
2. RAG 的第一道生死线：中文文档解析怎么做
3. 分块与索引：结构感知切分、双路索引与 schema 设计
4. 检索引擎选型对比：ES、milvus、pgvector、qdrant 与嵌入式方案
5. 检索算法：混合检索、融合公式与重排的正确姿势
6. 让答案可信：引用溯源的三种实现机制
7. 开源 RAG 平台都不敢做的事：文档级权限与检索期过滤
8. 上线前后的质量防线：RAG 评测体系从零搭建
9. GraphRAG 与 Agentic RAG：什么时候该上，什么时候是过度设计
10. 实战设计：Python 自建轻量知识库服务，给 deepagents 供数（本篇）

**全系列完。**十篇写完，回到系列标题——《给 Agent 造知识库》。如果你只带走一句话，让它是这句：把功夫花在解析质量、混合检索与重排、文档级权限这三件已被反复验证的事上，把 agent 循环留给消费者，把升级的缝留给自己。
