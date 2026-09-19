# gpt-researcher 解剖档案

> 基线：~/develop/opensource/gpt-researcher @ 6f998577 (2026-08-23)；canonical assafelovic/gpt-researcher；Apache-2.0。本档案属 D 组快扫：火力在维度 2（规划→执行循环）与维度 6（检索器/爬虫 provider 抽象），其余从简。交叉引用 `agent-framework/profiles/langgraph.md`、`deepagents.md`。

## 1. 产品定位与形态（简）

- 自主研究 agent：输入一个问题，产出带引用的研究报告（规划→检索→爬取→压缩→综合写作）。形态三套：Python 库（`GPTResearcher` 类）、CLI（`cli.py`）、FastAPI 后端 + Next.js 前端（`backend/` + `frontend/`，WebSocket 流式）。
- 另有两条并行演进线：`multi_agents/`（LangGraph 多 agent 报社流水线）、`deep_agents/`（基于 LangChain deep-agents 包 `build_agent` 的实现，`deep_agents/main.py`【核心】）。

## 2. Agent 执行架构 ★重点

- **单 agent 不是工具调用循环，是固定流水线**：【核心】`gpt_researcher/agent.py#GPTResearcher` 组合 7 个 skill 对象（`skills/researcher.py#ResearchConductor`、`skills/writer.py#ReportGenerator`、`skills/context_manager.py#ContextManager`、`skills/browser.py#BrowserManager`、`skills/curator.py#SourceCurator`、`skills/deep_research.py#DeepResearchSkill` 等），LLM 只在固定点位被调用（选题、拆 query、压缩、写作），无 function-calling 主循环。
- **规划→执行**：`conduct_research`（`skills/researcher.py#conduct_research`）——先 `choose_agent` 选角色 prompt → `plan_research`：先对原始 query 做一次初始检索，把搜索结果作为上下文让 strategic LLM 生成子查询列表（`actions/query_processing.py#plan_research_outline`，`json_repair` 解析 + 多形态防御性归一化 `_normalize_sub_queries`），原始 query 追加进列表。
- **并发检索编排**：子查询全部 `asyncio.gather` 并发（`_get_context_by_web_search` L382）；单条子查询内 = 所有 retriever 顺序搜（同步 HTTP 走 `asyncio.to_thread`，`query_processing.py#get_search_results`）→ 去重新 URL（`visited_urls` 集合跨子查询/父子 researcher 共享去重）→ `BrowserManager` 用 WorkerPool 并发爬取（`max_scraper_workers` + 限速延迟，`utils/workers.py`）→ 向量压缩。
- **上下文汇总**：每条子查询的爬取结果经 `ContextCompressor`（`context/compression.py`）：embedding 相似度过滤（阈值可配）+ top-10 截断，各子查询产出字符串后 `" ".join` 拼接为总 context；可选 `SourceCurator` 再做一次 LLM 筛源（`cfg.curate_sources`）。
- **深度研究 = 递归 breadth/depth**：`skills/deep_research.py#DeepResearchSkill`（默认 breadth=4/depth=2/并发=2），每层产出 learnings + follow-up questions 下一层展开，`max(2, breadth//2)` 逐层减半，`asyncio.Semaphore` 限并发——Open Deep Research 模式克隆。
- **多 agent 编排层（LangGraph）**：`multi_agents/agents/orchestrator.py#ChiefEditorAgent`——`StateGraph(ResearchState)` 固定拓扑 browser→planner→human→researcher→writer→fact_checker→visualizer→publisher，条件边实现计划修订回环（`max_plan_revisions` 限次）；`langgraph.json` 可被 LangGraph 平台加载。注意这是**旁路产品线**，FastAPI 主服务默认走单 agent 流水线（`backend/server/app.py`）。

## 3. 技术底座（简）

- Python + FastAPI/WebSocket；LLM 网关自研（`llm_provider/generic/`，litellm 兜底，支持 OPENAI_BASE_URL 自定义兼容端点）；embedding/向量存储走 LangChain 生态（`memory/embeddings.py`、`vector_store/`）。主流程不依赖 LangGraph；`multi_agents/` 依赖（交叉引用 `agent-framework/profiles/langgraph.md`）。

## 4. 状态与持久化（简）

- 单次研究会话状态（context/visited_urls/costs）全在内存对象上，无 checkpoint；`add_costs(cost)` 按 `_current_step` 归集分步成本（`agent.py#add_costs`）——轻量但可审计的分步计费钩子。
- 后端报告持久化 = 单个 JSON 文件读写锁（`backend/server/report_store.py#ReportStore`，无数据库）；日志有 JSON handler（`utils/logging_config.py#get_json_handler`）记录 query/context/costs。无多租户、无鉴权（`app.py` 无 auth 依赖）❌。

## 5. HITL 与风控（简）

- 唯一审批点在 `multi_agents/`：LangGraph human 节点（`agents/human.py#HumanAgent.review_plan`）——研究计划经 WebSocket 推给前端等人反馈，条件边带反馈回 planner 重规划，`plan_revision_count` 限次。主流程（单 agent/深度研究）无任何人工门 ❌。

## 6. 工具与业务系统集成 ★重点

- **检索器 provider 注册表**：`retrievers/__init__.py` 显式导入 21 个 provider（tavily/bing/brave/ddg/serper/…/mcp/bocha），按 cfg `RETRIEVERS` 环境变量逗号列表实例化（`actions/__init__.py#get_retrievers`）；新接一个数据源=写一个类+注册一行。
- **契约用能力声明而非启发式**：`retrievers/base.py#BaseRetriever.requires_scraping` 类属性——声明"返回 URL 待爬"还是"已带全文"；docstring 记载了教训：旧版用 `len(raw_content)>100` 猜内容是否已抓取，导致长 snippet 被误当全文、引用丢失（#1846/#1892）。可选 ABC、鸭子类型兼容第三方。
- **爬虫同样多 provider**：`scraper/`（firecrawl/tavily_extract/beautiful_soup/pymupdf/arxiv/browser/web_base_loader），`Scraper` 类按 URL 批量分派 + WorkerPool 并发（`actions/web_scraping.py#scrape_urls`）。
- **MCP 检索器带执行策略**：fast（原 query 跑一次+缓存）/deep（每子查询都跑）/disabled 三档（`skills/researcher.py#_get_mcp_strategy`），`asyncio.Lock` 防并发重复填充缓存；会话级 MCP 配置改 `cfg.retrievers` 而非 `os.environ`，避免进程级环境污染（`agent.py#_process_mcp_configs`，#1676）。
- 凭据：各 provider 自取环境变量 API key（如 `retrievers/tavily/tavily_search.py#get_api_key`），无统一密钥管理 ❌。

## 7. 部署与产品化（简）

- docker-compose（backend+frontend+mongo 可选）、Procfile、MCP server（`mcp-server/`）暴露研究能力；CLI/PIP 库三形态。单机单用户设计：无队列、无配额、无租户隔离；成本统计（`get_costs`/`get_step_costs`）是唯一的用量观测。可观测性可选 LangSmith/Monocle（`multi_agents/main.py` 环境开关）【文档+示例】。

## 8. 对本项目的适用性

- **可借鉴**：①「规划→并发执行→汇总」无需图框架即可用 `asyncio.gather`+子任务对象实现，与 LangGraph 图编排可叠加——财务场景的"取数任务分解→并发查多数据源→压缩汇总"可直接套此形态（`skills/researcher.py`）；② provider 注册表 + `requires_scraping` 式能力声明契约，对 Java 侧「财务数据源适配器 SPI + 注解声明读写语义」是直接样板（`retrievers/base.py`）；③ 分步成本归集（`agent.py#add_costs` + `_current_step`）是低成本审计字段；④ `visited_urls` 跨层级共享去重 + MCP 会话配置不污染全局 env，都是工程细节级可抄。
- **不可迁移**：其"工具"只读（检索/爬取），无事务、无审批语义；单 JSON 文件报告存储、无鉴权多租户——企业级财务要求下均需重做；深度研究递归无预算硬顶（仅 depth/breadth 软顶）。
- **避坑**：固定流水线把 LLM 当"文本处理器"而非决策器，灵活性受限但可控性极高——审批合规场景反而是优点；子查询无限并发（gather 无 Semaphore，仅爬取层限流）易打爆下游 API；`multi_agents` 人工反馈依赖 WebSocket 阻塞等待（`websocket.websocket.receive_text()`），服务化时需换异步审批工单模式。
