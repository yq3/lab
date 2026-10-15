# 11b. Quivr 遗留 Python 版全貌（vs V2 Go 版）

> 调研对象：git worktree `/tmp/wt-quivr-py`，锚点 `947a78541`（2025-06-19 "fix: add Claude 4 support"，Python 版最后提交，即 V2 仓库中的 `v1-final` tag）。
> 对照基线：`~/develop/opensource/quivr` @ `67a6c0e9f`（V2 Go 版，2026-10-12）。
> 证据标注：相对 `/tmp/wt-quivr-py`（记作 PY:）或 `~/develop/opensource/quivr`（记作 GO:）；Era A（产品时代）代码已不在锚点树中，用只读 `git show 7acb52a96^:<path>` 取证（`7acb52a96` = 2024-10-21 删除 backend/frontend 的转折提交）。

## 0. 一句话结论

"Quivr Python 版"其实是**两段形态**：2023-05～2024-10 是「第二大脑」全栈 SaaS（Next.js + FastAPI + Supabase/pgvector + Celery），2024-10-21 起砍掉产品层、退化为纯 Python RAG 库 `quivr-core`（LangChain/LangGraph 栈，FAISS 默认）。V2 Go 版不是它的重写，而是 15 个月断代后由 The Vibe Company 在同一品牌仓库里**另起炉灶的新产品**（仅继承名字与"给 agent 供数"的定位）。

## 1. Python 版全貌

### 1.1 仓库时间线（同一 main 分支的四个阶段）【核心】

| 阶段 | 时间 | 形态 | 关键证据 |
|---|---|---|---|
| Era A 产品 | 2023-05-12 ~ 2024-10-21 | monorepo：backend(api/worker/core/supabase) + frontend + cms | `git ls-tree 7acb52a96^`；首个提交 `921d7e250` (2023-05-12) |
| Era B 库 | 2024-10-21 ~ 2025-06-19 | 只剩 core/ + docs/ + examples/，即 `quivr-core` 0.0.33 | `7acb52a96 "feat(quivr-core): beginning (#3388)"` 删除 backend/ 与 frontend/ |
| 断代 | 2025-06-19 ~ 2026-09-03 | 零提交（15 个月） | `git log 947a78541..67a6c0e9f --reverse` 首条为 2026-09-03 |
| V2 | 2026-09 至今 | Go 引擎 | GO: `git log`；`d9f490782`（2026-10-04）"Quivr v2: replace the v1 code base with the v2 engine" |

锚点 `947a78541` 的树里**没有任何服务端代码**：只有 `core/`（41 个 py 文件）、`docs/`（mkdocs，core.quivr.com）、`examples/`、vercel.json（仅 `deploymentEnabled: false` 残留）。网络通识里的"Supabase 栈聊天产品"对应的是 Era A，须区分。

### 1.2 Era A：第二大脑产品（2023-05 ~ 2024-10）

- **形态**：Web 聊天产品（"Think of it as Obsidian, but turbocharged with AI"），README 主打 Public/Private brains 分享、Porter 一键部署【文档：`git show 7acb52a96^:README.md`】。
- **技术栈**【核心：`git show 7acb52a96^:backend/api/pyproject.toml`】：FastAPI + uvicorn + supabase(python) + asyncpg/psycopg2 + sqlmodel + **pgvector** + celery[redis] + litellm + langchain 0.2 + sentry + posthog + resend；OAuth 同步集成（notion-client、google-api、dropbox、msal）。前端 Next.js + `@supabase/auth-helpers-nextjs` + tiptap + growthbook/june/posthog（增长工程全套）【核心：`git show 7acb52a96^:frontend/package.json`】。部署为 6 个 docker 服务（frontend/backend-api/worker/notifier/beat/flower + redis），Supabase 托管在云上。
- **数据模型**【核心：`backend/supabase/migrations/20240103173626_init.sql`】：`brains`（model/max_tokens/temperature 直接挂在 brain 上）、`brains_users`（**rights varchar + default_brain bool**，权限模型就是一张关联表一个字符串列）、`brains_vectors`（brain↔chunk 多对多）、`knowledge`/`knowledge_vectors`、`chats`/`chat_history`、`api_keys`、`user_daily_usage`、`brain_subscription_invitations`、`composite_brain_connections`（brain 组合）。还有 `api_brain_definition` 表 + `modules/brain/integrations/{Claude,GPT4,SQL,Proxy,Notion}`——"API brains"把外部模型/SQL 当作一种 brain 接入，这是当时"agent"标签的主要落点【核心：目录列表】。
- **RAG 数据流**【核心】：上传 → Supabase Storage 签名 URL（`modules/upload/service/generate_file_signed_url.py`）→ Celery worker `quivr_worker/process/process_file.py`（parse_file → store_chunks）→ `quivr_core.processor.registry.get_processor_class` 按扩展名选处理器 → chunk 入 PG，向量经 pgvector 写 `vectors` 表。
- **检索**【核心：`quivr_api/vectorstore/supabase.py` + migration `20240320215813_fix_match_vector_function.sql`】：`match_vectors` RPC = 纯余弦 ANN（`1 - (embedding <=> query_embedding)`），但带一个亮点——**按 chunk_size 累计预算截断**（`sum(chunk_size) OVER (ORDER BY similarity DESC) <= max_chunk_sum`，按 token 预算装满上下文）；另有 `match_brain` 跨 brain 路由（查询相似度选 brain）。**全仓 grep tsvector/to_tsquery 零命中——无混合检索**。
- **治理**：认证 = Supabase JWT（jose HS256 校验）或 api_keys 双通道（`middlewares/auth/auth_bearer.py`）【核心】；配额 = `monthly_chat_credit`（默认免费档 20/用户设置 100）【核心：migration `20240122194117`】；Stripe 订阅（`stripe_customers.sql`、subscription_routes）；RLS 依赖 Supabase 默认 policy。审计/评测：❌ 无审计日志；评测仅有 phospho edge function（实验性打分）⚠️。

### 1.3 Era B：quivr-core 库（2024-10 ~ 2025-06，锚点状态）

- **定位**："We take care of the RAG so you can focus on your product. Simply install quivr-core"——从 SaaS 转型为 pip 包（README），服务对象从终端用户变为开发者，商业化转向企业定制（见 Zendesk 专用节点）。
- **技术栈**【核心：`core/pyproject.toml`】：pydantic v2 + **langchain 0.3 + langgraph 0.2** + faiss-cpu + megaparse-sdk + tiktoken/transformers（分词器）+ langfuse（观测）+ rapidfuzz；LLM 面 = langchain-openai/anthropic/mistralai/google-genai/groq/cohere。**默认三件套**：OpenAIEmbeddings + FAISS 本地 + gpt-4o（`core/quivr_core/brain/brain_defaults.py`）——不再是 Supabase/pgvector（仅 docs 里留有 pgvector 接入页）。
- **API 面**：无 HTTP 服务，暴露 `Brain` 类：`Brain.from_files()` → `brain.ask()/ask_streaming()/asearch()`；可 `save()/load()` 序列化到本地目录（仅支持 FAISS+OpenAI embedder，其他抛异常）【核心：`core/quivr_core/brain/brain.py`】。2025-05 起 Brain 出现 `workspace_id`（#3590），是企业多租户改造的萌芽。
- **RAG 数据流**【核心：`brain.py::afrom_files`】：load_qfile → StorageBase（TransparentStorage/LocalStorage，SHA-1 去重）→ processor registry（优先级堆 + 懒加载：txt/pdf 基线 Tika，16 种扩展名走 Megaparse，缺依赖自动降级）→ RecursiveCharacterTextSplitter 风格切分（`splitter.py`：chunk_size=400 字符 / overlap=100，**字符数而非 token**）→ FAISS 索引。
- **检索与生成（LangGraph 流水线）**【核心：`core/quivr_core/rag/quivr_rag_langgraph.py`】：工作流由 **YAML 声明**（nodes/edges，`rag/entities/config.py::WorkflowConfig`），默认链 filter_history → rewrite → retrieve → generate_rag。可选节点构成一个"agentic RAG"全家桶：
  - 任务分解（`SplittedInput` 结构化输出拆多问题）+ 意图识别（用户指令动态改 system prompt）；
  - `dynamic_retrieve`：top_n 不够就翻倍重检（最多 3 轮）；
  - rerank：Cohere/Jina（`ContextualCompressionRetriever`），阈值过滤；无 reranker 时 IdempotentCompressor 占位；
  - `tool_routing`/`run_tool`：LLM 判断任务是否需要外部工具，唯一内置 web search = Tavily，另有 `cited_answer` 工具（结构化引用输出）【核心：`llm_tools/`】；
  - `reduce_rag_context`：token 超限时先裁历史再裁文档（最多 20 轮）；
  - 流式输出经 `astream_events`，全链路 Langfuse trace。
  - 检索本身仍是**纯向量**（`asimilarity_search_with_score`），无 lexical/hybrid；`retrieve_full_documents_context` 按 knowledge_id 拉全文档，但代码内 assert 标注 "enterprise only feature"——闭源版钩子。
  - `generate_zendesk_rag`：Zendesk 工单场景专用节点（2025-02-03 #3586 起 8 个相关提交）——末期主要收入方向的痕迹。
- **治理**：库形态下无认证/配额/审计；观测 = Langfuse（`rag/utils.py::LangfuseService`）。token 预算管理精细（`LLMModelConfig` 硬编码 7 家供应商 ~40 个模型的 context/output 上限与 HF tokenizer）。

## 2. V1 vs V2 对照总表

| 维度 | V1 Python（Era A 产品 / Era B 库） | V2 Go（67a6c0e9f） |
|---|---|---|
| 产品定位 | 个人"第二大脑"聊天 SaaS → RAG SDK 库 | 内容流搜索引擎/监测引擎，"durable before fast" |
| 用户 | C 端用户/开发者 | agent/程序（key 级 scope，MCP stdio） |
| 语言框架 | Python：FastAPI + Celery + LangChain/LangGraph | Go 单二进制（api/worker/migrate）+ Temporal |
| 存储 | Supabase：PG+pgvector（canonical 即索引）/Storage/Auth | PG17+S3 canonical，Weaviate 索引为可重建投影 |
| 向量库 | pgvector（产品）/ FAISS-cpu（库） | Weaviate（lexical+vector 混合）+ TEI E5-small 钉死 |
| 嵌入 | OpenAIEmbeddings（默认，可换） | 自托管 TEI，无多供应商 |
| LLM 面 | 7 家供应商 ~40 模型，LangChain 全家桶 | **零 LLM**（internal/ grep openai/anthropic = 0） |
| 检索 | 纯向量余弦 + Cohere/Jina rerank + token 预算截断 | lexical/semantic/hybrid，"honest search"回源再授权 |
| 切分 | 400 字符/100 重叠 | Segmentation/Derivation 领域模型（结构化流水线） |
| 领域语言 | Brain/Knowledge/Chat（human 语义） | Corpus/Record/RecordVersion/Part/Segmentation/Blob |
| 权限 | brains_users.rights 字符串 + Supabase RLS | key scope + netguard SSRF 防护 + append-only 审计 |
| 配额/商业化 | monthly_chat_credit + Stripe 订阅 | 无用户体系（v0 评估阶段） |
| 一致性模型 | 无幂等概念，Celery at-least-once | 幂等键 + 不可变 Version |

**继承关系近乎为零**：唯一勉强算延续的是"为上层 agent 提供检索底座"的产品哲学——Era A 的 API brains/integration brains（把外部能力当 brain）→ Era B 的 tool_routing → V2 的 MCP server（`GO: internal/online/mcp_stdio.go`），但三者间没有任何代码或 API 兼容。

## 3. V2 是重写还是新产品：证据化结论

**结论：新产品（same-brand reboot），不是 V1 的重写。** 证据链：

1. **断代 15 个月**：main 分支 2025-06-19 后第一条提交是 2026-09-03 `88f692141 "docs(architecture): define quivr v2 foundation"`，之后依次是"archive architecture discovery transcript""select Go for the core runtime"（`fb76ac5f9`，2026-09-04）——V2 从架构文档重新推导，而非从 V1 代码迁移【核心：GO: git log】。
2. **替换提交自述**：`d9f490782`（2026-10-04，StanGirard 署名）提交信息明说 *"Joins the v2 history (engine, plugins, docs) to the v1 history so that every contributor stays credited. The resulting tree is the v2 tree; v1 remains available … on the v1 branch and under the v1-final tag"*——v2 树是外部带入后嫁接的，保留 v1 历史仅为署名；单提交 2253 文件 +37.8 万/-2.6 万行【核心】。
3. **组织易主**：V2 Go module path = `github.com/The-Vibe-Company/quivr`，AGENTS.md/文档处处指向 The Vibe Company 的 Linear 工作区（Quivr V2 project, THE-531）——运营主体已换【核心：GO: internal/reference/mcp/mcp.go import、AGENTS.md】。
4. **技术栈与领域语言全换**：无任何 Python 残留、无 LangChain 依赖、无 LLM 调用；brain/knowledge/chat 概念整体消失，代之以 Corpus/Record 体系（对照表见上）。连许可证都从 Apache 2.0 换成 MIT（PY: LICENSE vs GO: README badge）。
5. **刻意封存而非演进**：锚点提交被打成 `v1-final` tag（GO: `git tag -l`，指向 947a78541），语义就是"V1 完结"。

一句话：**V2 借了 Quivr 的名字和仓库（含 star 数与贡献者历史），做的是一个领域、语言、栈、用户全不同的新引擎。**

## 4. 对主报告既有结论的影响评估

1. **"V1=brains+Supabase 的通识结论需拆两段说**：该描述只对 2024-10 之前的产品形态成立；2024-10 后的开源仓库是 quivr-core 库（FAISS+LangGraph），若主报告引用 V1 作为"Supabase 系 RAG 产品"案例，应注明证据来自 Era A（需 git 考古，锚点树中已不存在）。
2. **V1 是否值得作为参考实现**：
   - **不值得**作为当前企业 RAG 架构参考：纯向量检索、无混合、无审计、无幂等、切分按字符、权限是 rights 字符串列——这些恰是 V2 用"canonical PG+S3 + 可重建索引 + 幂等 + append-only 审计"逐项反着做的，V1 的价值主要是作为**V2 设计决策的对照组**。
   - **有限值得**记录的三个工程细节：① `match_vectors` 的 chunk_size 累计预算截断（按 token 预算装上下文，比固定 top-k 优雅）；② Era B 的 dynamic_retrieve（rerank 结果不够好则扩 top_n 重检，≤3 轮）与 reduce_rag_context（先裁历史再裁文档）——可作为 04-retrieval/06-agentic 章节的 LangGraph 时代样本；③ Langfuse 全链路观测在 2024 年已是标配。
   - 它是 **LangChain/LangGraph 栈 RAG 的典型终局标本**：供应商面极宽（7 家 LLM + 2 家 rerank）但底座能力（持久化/一致性/治理）全部缺位，最终转向（弃 LangChain 栈重写为 Go + 自管 PG）本身就是对主报告"自建 vs 框架"讨论的有力数据点。
3. **对 01-platform-arch**：Quivr 案例应改写为"两代同牌异构系统"：V1（LangChain 系，SaaS→SDK 失败/停滞）→ V2（Go+Temporal，搜索监测引擎）。V2 的 MCP-only 检索暴露与 V1 无 API 兼容，不能作为"演进保留接口"的证据。
4. **时间线修正**：V1 死因锚定 2024-10-21（产品层删除）而非 2025-06（最后提交）；2025-06~2026-09 为空窗，V2 起点 2026-09-03。

## 5. 证据与存疑清单

### 证据（分级）
- 【核心】PY: `core/pyproject.toml`、`core/quivr_core/{brain/brain.py, rag/quivr_rag_langgraph.py, rag/entities/config.py, processor/registry.py, processor/splitter.py, storage/local_storage.py, brain/brain_defaults.py, llm_tools/*}`（均 @947a78541）
- 【核心】Era A（git show 7acb52a96^:）：`backend/api/pyproject.toml`、`frontend/package.json`、`backend/supabase/migrations/{init, fix_match_vector_function, monthly-credit, policies}.sql`、`quivr_api/middlewares/auth/auth_bearer.py`、`quivr_api/vectorstore/supabase.py`、`quivr_worker/process/process_file.py`、`docker-compose.yml`
- 【核心】GO: `git log 947a78541..67a6c0e9f`（断代+V2 起点）、`d9f490782`（v1→v2 替换自述）、`v1-final` tag、`go.mod` 首现 2026-09-15（#8）、`internal/online/mcp_stdio.go`、`README.md`、`AGENTS.md`
- 【文档】PY: `README.md`（两种形态）、`docs/docs/vectorstores/{faiss,pgvector}.md`、GO: `README.md`（V2 定位）
- 【示例】PY: `core/example_workflows/`、`examples/`（chatbot/whisper/voice）

### 存疑（不臆测）
1. ⚠️ **V2 开发过程的完整历史**：`d9f490782` 自述"joins the v2 history"，但 2026-09 起的 v2 提交已在本仓库分支上（PR #1~#8, The-Vibe-Company 命名空间）；嫁接前是否有独立私有仓无法从本仓库证实。
2. ⚠️ **Era A 商业数据/死因**：代码只能证明 2024-10 战略收缩为库 + 2025 年押注 Zendesk 类企业定制（enterprise-only 钩子、workspace_id 改造）；营收与用户数据不可考。
3. ❌ **V1 混合检索/rerank 之外的高级检索**：确认不存在（tsvector/BM25 零命中）；Era B 对 pgvector/Hybrid 的支持仅是 LangChain 通用的 `as_retriever`，未见配置级 hybrid。
4. ❌ **评测体系**：两代 V1 均无 RAGAS/回归评测框架代码，仅 Langfuse 观测 + phospho（Era A，实验性）。
5. ⚠️ **quivr-core 停更时的实际企业版形态**：`get_vectors_by_knowledge_id` 等 "enterprise only" 断言暗示存在闭源企业分支，本仓库不可见。
