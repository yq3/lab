# crewAI 框架档案
> 基线：~/develop/opensource/crewAI @ 894898f84 2026-09-12；版本 **1.15.21**（`lib/crewai/src/crewai/__init__.py:51 __version__`；根 `pyproject.toml` 为 **uv workspace**，成员 `lib/{crewai, crewai-core, crewai-tools, cli, devtools, crewai-files}`，无 git tag 对照、以包内版本为准）

## 1. 定位
「角色扮演式多 agent 协作」框架：以 **Crew（团队）/ Agent（角色）/ Task（任务）** 三元组为核心抽象，用自然语言角色分工驱动 agent 协作；v0.x 后追加 **Flow**（`@start/@listen/@router` 事件驱动编排）作为与 Crew 正交的第二编排模型，用于确定性工作流与 Crew 组合。形态是**库 + CLI**（`crewai` 命令：脚手架/运行/训练/测试/replay/deploy），不是低代码平台。目标用户是 Python 开发者与 AI 工程团队；商业边界清晰——本地编排核心开源，**执行托管、Web 控制台、SSO、审计、定时触发在付费 CrewAI Enterprise（AMP 平台）**，OSS 侧只留 API 客户端与遥测上报。1.15 系列的最大重构：记忆统一为单一 `Memory`（旧 ShortTerm/LongTerm/Entity 三件套已删除）+ 仓库重组为 uv monorepo。

## 2. 仓库结构与核心包
- 根 `pyproject.toml` = uv workspace（`[tool.uv.workspace] members = lib/crewai, crewai-tools, devtools, crewai-files, cli, crewai-core`）；`lib/crewai` 用 hatchling，版本取自 `src/crewai/__init__.py`。
- 核心包 `lib/crewai/src/crewai/`（约 30 个子包）：`crew.py`(2490 行)/`agent/core.py`(2155)/`task.py`(1566) 三巨头 + `process.py`；`flow/`（dsl 装饰器 + `runtime/` 执行引擎 + persistence + 可视化 + 会话式扩展）；`memory/`（统一记忆 + LanceDB 存储 + 编码/召回双流水线）；`knowledge/` + `rag/`（RAG 基建：chromadb/qdrant + 20 家 embedder）；`llm.py`(约 2600 行) + `llms/`（base_llm、cache、6 家原生 provider）；`tools/`（BaseTool/@tool/agent_tools 委派/tool_failure）；`mcp/`（MCP 客户端内置主包）；`a2a/`（A2A 协议完整实现）；`skills/`（SKILL.md 体系）；`events/`（统一事件总线 + tracing 监听器）；`state/`（checkpoint）；`hooks/`（11 切入点拦截）；`security/`（指纹）；`telemetry/`；`project/`（@crew 脚手架装饰器）；`lite_agent.py`（轻量单 agent）；`experimental/`（评估/会话式）；`translations/`（多语言提示词）。
- 兄弟包：`lib/cli` → `crewai-cli`（`crewai` 命令全量：create/run/train/test/replay/chat/deploy/enterprise/login/logout/memory/checkpoint/skills 等）；`lib/crewai-core` → 共享底座（version/telemetry/`token_manager.py` Fernet 加密凭据存储/plus_api/paths）；`lib/crewai-tools` → 独立工具包（60+ 工具目录：搜索/爬取/数据库/沙箱 e2b+daytona/多模态等）；`lib/crewai-files` → 多模态文件处理；`lib/devtools` → 内部文档工具（非产品）。

## 3. 核心抽象清单

| 符号 | 路径 | 说明 |
|---|---|---|
| `Crew(FlowTrackable)` | lib/crewai/src/crewai/crew.py#Crew(:164) | 团队容器：agents/tasks/process/memory/planning/checkpoint；kickoff 系列入口（:995 同步、:1130 async、:1094/:1184 for_each） |
| `Agent` | lib/crewai/src/crewai/agent/core.py#Agent | 角色 agent：role/goal/backstory/llm/tools/max_iter/respect_context_window |
| `LiteAgent` | lib/crewai/src/crewai/lite_agent.py#LiteAgent(:193) | 无 Task 依赖的轻量单 agent（会话式/chat 场景），同样 FlowTrackable |
| `Task` / `ConditionalTask` | lib/crewai/src/crewai/task.py / tasks/conditional_task.py | 任务单元：context 依赖、output_json/output_pydantic、human_input、callback、guardrail(s)、async_execution |
| `Process` | lib/crewai/src/crewai/process.py#Process(:6) | 仅 sequential / hierarchical（consensual 是 TODO 注释） |
| `CrewAgentExecutor` | lib/crewai/src/crewai/agents/crew_agent_executor.py#CrewAgentExecutor | agent 执行循环：native tool-calling 优先、失败自动降级 ReAct 文本模式（:600），max_iter 截断（:365/:525） |
| `Flow` | lib/crewai/src/crewai/flow/runtime/__init__.py#Flow(:442)，kickoff(:2069) | 事件驱动编排引擎；`flow/flow.py` 只是再导出壳 |
| `@start/@listen/@router/and_/or_` | lib/crewai/src/crewai/flow/dsl/{_start,_listen,_router,_conditions}.py | Flow 排线 DSL；router 按返回值字符串选监听分支 |
| `FlowTrackable` | lib/crewai/src/crewai/flow/flow_trackable.py#FlowTrackable(:15) | Crew/Agent/LiteAgent 共同基类：经 contextvar 自动捕获 flow_id/request_id，Flow 内嵌 Crew 免参数打通 |
| `Memory` | lib/crewai/src/crewai/memory/unified_memory.py#Memory(:76) | v1.15 统一记忆：LLM 分析打分（semantic/recency/importance 加权、半衰期、consolidation 去重）、LanceDB 默认存储 |
| `EncodingFlow` / `RecallFlow` | lib/crewai/src/crewai/memory/{encoding_flow.py:75, recall_flow.py:58} | 记忆写入（批量嵌入 + N 路并发 LLM 抽取）/ 读取（RLM 式置信度路由自适应深挖）——内部复用 Flow 引擎 |
| `StorageBackend` / `LanceDBStorage` | lib/crewai/src/crewai/memory/storage/{backend.py:45, lancedb_storage.py:42} | 存储协议 + 默认实现（另有 qdrant_edge）；`kickoff_task_outputs_storage.py:18` SQLite 落 kickoff 日志供 replay |
| `LLM` / `BaseLLM` | lib/crewai/src/crewai/{llm.py#LLM(:371), llms/base_llm.py#BaseLLM(:159)} | `__new__` 工厂路由：原生 SDK（openai/anthropic/azure/bedrock/gemini/snowflake）优先、其余落 LiteLLM 兜底 |
| `BaseTool` / `Tool` / `@tool` | lib/crewai/src/crewai/tools/base_tool.py#BaseTool(:103)/Tool(:521)/tool(:678) | 工具基类（Pydantic args schema、EnvVar 声明式凭据）+ 函数装饰器 |
| `AgentTools` | lib/crewai/src/crewai/tools/agent_tools/agent_tools.py#AgentTools(:16) | 委派工具组：delegate_work / ask_question（hierarchical manager 的手脚） |
| `MCPClient` | lib/crewai/src/crewai/mcp/client.py#MCPClient(:67) | MCP 消费端：stdio/SSE/StreamableHTTP 三 transport、tool_resolver、filters、执行超时重试（mcp_tool_wrapper.py:156） |
| `HumanInputProvider` | lib/crewai/src/crewai/core/providers/human_input.py#HumanInputProvider(:60) | HITL 通道 Protocol（同步实现 :147），可替换为企业 Web 审批 |
| `CrewPlanner` | lib/crewai/src/crewai/utilities/planning_handler.py#CrewPlanner(:37) | planning=True 时的预执行规划：planner agent 生成 per-task 分步计划注入各任务 |
| `CrewAIEventsBus` | lib/crewai/src/crewai/events/event_bus.py#CrewAIEventsBus(:95) | 统一事件总线：同步线程池 + 异步专用 loop、handler 依赖图 |
| `Hooks(InterceptionPoint)` | lib/crewai/src/crewai/hooks/dispatch.py#InterceptionPoint(:40) | 11 个拦截点（execution/input/output、pre/post_model_call、pre/post_tool_call、pre/post_step）+ HookAborted |
| `@crew/@agent/@task/@before_kickoff` | lib/crewai/src/crewai/project/annotations.py(:42-181) | 项目脚手架装饰器（CLI create 生成物的骨架） |
| `SkillRegistry` / `SkillTool` | lib/crewai/src/crewai/skills/{registry.py, tool.py} | SKILL.md 体系：本地/平台注册表、版本对齐、渐进加载 |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | LLM 类工厂路由原生 SDK（6 家）+ LiteLLM 兜底百余模型；流式/成本/缓存/重试齐 | lib/crewai/src/crewai/llm.py#LLM:371、llms/providers/、agents/cache/cache_handler.py |
| 2 | 上下文工程 | ✅ | 布尔级 respect_context_window 超窗摘要 + 0.85 窗口配比 + prompt cache 断点；无通用 trim/压缩管道 | lib/crewai/src/crewai/agent/core.py:288、llm.py:2503/get_context_window_size、llms/cache.py:27 |
| 3 | 记忆 | ✅ | v1.15 统一 Memory：LLM 写入打分 + 置信度召回流水线 + scope 命名空间 + LanceDB 默认 | memory/unified_memory.py#Memory:76、memory/recall_flow.py:58、memory/memory_scope.py |
| 4 | RAG | ✅ | knowledge（7 种源）+ rag（chromadb/qdrant + 20 家 embedder）内置主包；rerank/citation 缺位 | knowledge/knowledge.py#Knowledge:88、rag/embeddings/providers/、rag/{chromadb,qdrant}/ |
| 5 | 工具系统 | ✅ | BaseTool/@tool + 结构化失败策略 + MCP 内置主包（超时/重试/过滤）；普通工具无核心超时 | tools/base_tool.py#BaseTool:103、tools/tool_failure.py:57、mcp/client.py#MCPClient:67 |
| 6 | Skill 机制 | ✅ | SKILL.md 注册表/加载器/校验/事件/工具化 + CLI skills 子命令 + 平台分发 | skills/registry.py、skills/tool.py、lib/cli/src/crewai_cli/skills/ |
| 7 | 规划推理 | 🟡 | planning=True 只有 kickoff 前一次性分步规划；运行时仅 max_iter 截断与 guardrail 重试 | utilities/planning_handler.py#CrewPlanner:37、agents/crew_agent_executor.py:365 |
| 8 | 编排 | ✅ | Flow 事件驱动 DSL（listen 条件/each 循环/可视化/YAML 声明式）+ Crew 双进程 + 任务级并发 | flow/runtime/__init__.py#Flow:442、flow/runtime/_actions.py#EachAction:313、lib/cli/src/crewai_cli/run_declarative_flow.py |
| 9 | 多 Agent | ✅ | hierarchical=manager+委派工具；langgraph/openai-agents 双向适配；A2A 完整（含 agent 出卡片） | crew.py:1521/_create_manager_agent、agents/agent_adapters/、a2a/wrapper.py:97、a2a/utils/agent_card.py:579 |
| 10 | 持久化 | ✅ | Crew checkpoint 断点续跑 + replay(task_id) 按 SQLite 执行日志重放 + Flow @persist | crew.py:400/:1548/:2034、memory/storage/kickoff_task_outputs_storage.py:18、flow/persistence/decorators.py#persist:147 |
| 11 | HITL | ✅ | human_input 答案后反馈循环 + 可替换 HumanInputProvider + Flow 级 LLM 辅助人审；无中断-恢复原语 | agents/crew_agent_executor.py:1625、core/providers/human_input.py:60、flow/human_feedback.py#HumanFeedbackConfig:189 |
| 12 | 观测评估 | ✅ | 统一事件总线（70+ 事件类型）+ OTLP 遥测 + 平台 trace 上传 + 实验性评估框架（弱） | events/event_bus.py#CrewAIEventsBus:95、telemetry/constants.py:9、experimental/evaluation/agent_evaluator.py:47 |
| 13 | 安全治理 | 🟡 | guardrail 三形态 + 11 切入点 hooks + 组件指纹；无 PII/权限/内容安全库，SecurityConfig 多项 TODO | utilities/guardrail.py:123、tasks/llm_guardrail.py:49、hooks/dispatch.py:40、security/security_config.py |
| 14 | 部署运行时 | 🟡 | OSS 无内置服务端/镜像；`crewai deploy` 推付费平台，triggers/cron 也是平台侧客户端 | lib/cli/src/crewai_cli/cli.py:714/deploy、lib/cli/src/crewai_cli/triggers/main.py:23 |
| 15 | 管理平面 | 🟡 | 控制台/SSO/审计全在付费 AMP（enterprise-api yaml 仅文档）；OSS 侧 TUI + oauth login + plus_api 客户端 | docs/v1.15.21/enterprise-api.base.yaml、lib/cli/src/crewai_cli/{crew_run_tui,checkpoint_tui}.py、plus_api.py |

## 5. 维度证据明细

**1 模型接入【核心】**
- `LLM(BaseLLM)`（lib/crewai/src/crewai/llm.py:371）用 `__new__` 做工厂路由：`custom_openai=True` 强制原生 OpenAI（须自定义 endpoint）→ 显式 `provider=` → 模型名前缀映射（openai/anthropic/claude/azure/google/gemini/bedrock/aws/openrouter/deepseek/ollama/hosted_vllm/cerebras/dashscope/snowflake…）→ 命中 `SUPPORTED_NATIVE_PROVIDERS`（llm.py:330）且通过模型常量表校验则走原生 SDK，否则落 **LiteLLM 兜底**（懒加载，llm.py:84-158）。
- 原生 provider 六家：`llms/providers/{openai, anthropic, azure, bedrock, gemini, snowflake, openai_compatible}` 各自 completion 实现；openai/anthropic 默认 `max_retries=2`（providers/openai/completion.py:326、anthropic/completion.py:259）。
- 流式 `stream=True`（llm.py:393）+ `Crew.stream` 字段（crew.py:321）+ step_callback；成本：`completion_cost`（llm.py:373）与 `Crew.usage_metrics/token_usage`（crew.py:274/:408，`types/usage_metrics.py#UsageMetrics` 聚合）。
- 缓存两层：`Crew.cache=True` → 工具级 SQLite 缓存（`agents/cache/cache_handler.py:10`）；LLM 层 prompt cache 断点标记（`llms/cache.py#mark_cache_breakpoint:27`，system 尾+user 尾断点，executor :204-206 注释）。
- 无多模型 fallback 链（❌，与 ADK FallbackModel 对比明显）；上下文窗口常量表内置于 llm.py（mistral 等条目）。

**2 上下文工程【核心】**
- `Agent.respect_context_window`（agent/core.py:288，「Keep messages under the context window size by summarizing content」）——唯一的历史压缩开关，布尔级、超窗时摘要或中止（llm.py:1939 分支）。
- 窗口预算：`get_context_window_size`（llm.py:2503）查常量表并乘 `CONTEXT_WINDOW_USAGE_RATIO=0.85`（llm.py:329）；超窗异常 `utilities/exceptions/context_window_exceeding_exception.py`。
- Prompt 工程：`translations/` 多语言模板 + `utilities/i18n.py`；`AgentReasoning`（utilities/reasoning_handler.py:107）处理推理模型思维链的解析与注入。
- 无消息级 trim/摘要管道、无事件压缩器（❌ 对比 ADK/LangGraph）——上下文管理刻意薄。

**3 记忆【核心】**
- v1.15 统一 `Memory`（memory/unified_memory.py:76）：旧 ShortTerm/LongTerm/EntityMemory 类已全仓删除（rg 零命中）。`Crew.memory` 布尔/实例二态（crew.py:256），`create_crew_memory`（crew.py:656）以 `/crew/<name>` 为 root_scope、embedder 走 `rag/embeddings/factory.py#build_embedder`、分析 LLM 取 chat_llm 或首个 agent llm（默认 gpt-5.4-mini）。
- 写入：`EncodingFlow`（memory/encoding_flow.py:75）——单次批量嵌入 → 批内去重 → N 路并发 LLM 抽取（scope/类别/重要性）+ 相似度 ≥0.85 触发 consolidation 合并 → 批量重嵌入落库。
- 读取：`RecallFlow`（memory/recall_flow.py:58）——LLM 生成子查询与过滤器、(子查询×scope) 并行检索、置信度 ≥0.8 直接返回 / ≤0.5 触发深挖（exploration_budget 限额）；打分 = semantic 0.5 + recency 0.3（30 天半衰期）+ importance 0.2。
- 注入：`Agent._retrieve_memory_context`（agent/core.py:656）task kickoff 前 `recall(query, limit=5)` 拼进任务 prompt（"Relevant memories:" 块）；执行器保存 `_save_to_memory`（agents/agent_builder/base_agent_executor.py:31，委派中间结果不落库）。
- 存储：`StorageBackend` Protocol（memory/storage/backend.py:45）+ LanceDB 默认（lancedb_storage.py:42，后台自动 compact）+ `qdrant_edge_storage.py`；`MemoryScope/MemorySlice`（memory/memory_scope.py）做作用域视图。
- 遗忘：无显式 forget API（❌）；reset_memories 仅 CLI 清库（utilities/reset_memories.py + `crewai reset-memories`）。

**4 RAG【核心】**
- `Knowledge`（knowledge/knowledge.py:88）+ 7 种源（source/：pdf/csv/excel/json/text_file/string/**crew_docling**）；存储 `KnowledgeStorage` 底层 chromadb（knowledge/storage/knowledge_storage.py:22）。
- `rag/` 基建：`chromadb/` 与 `qdrant/` 双 client（config/factory/types 分目录），`rag/embeddings/providers/` **20 家嵌入供应商**（openai/google/cohere/azure/aws/ibm/jina/ollama/onnx/voyageai/sentence_transformer/huggingface…+custom），`rag/factory.py#create_client:41` 可注册扩展。
- 无 rerank、无 citation、无 hybrid search 核心抽象（❌）；contextualai rerank 以 crewai-tools 独立包工具存在（🟡 lib/crewai-tools/src/crewai_tools/tools/contextualai_rerank_tool）。

**5 工具系统【核心】**
- `BaseTool`（tools/base_tool.py:103）Pydantic args schema 自动生成；`Tool`(:521) 泛型包装 + `@tool`(:678 重载支持带参/无参)；`EnvVar`(:96) 在工具上声明式声明所需环境变量（凭据面）。
- 执行：`tools/tool_usage.py#ToolUsage:84` 解析/调度/回填；**结构化失败策略** `tool_failure.py`——`ToolFailurePolicy`(:57)（如 fail/raise/retry/ignore 语义）+ 失败记录聚合（`collect_tool_failures:237`）。
- MCP 内置主包：`mcp/client.py#MCPClient:67` + 三 transport（mcp/transports/{stdio,sse,http}.py，streamable HTTP 默认）+ `config.py`（MCPServerStdio/HTTP/SSE 模型，`allowed_tool_names` 过滤）+ `tool_resolver.py`/`filters.py`；MCP 工具执行有超时与重试（tools/mcp_tool_wrapper.py:156 `_execute_tool_with_timeout`，MCP_TOOL_EXECUTION_TIMEOUT）。
- 普通工具无核心级超时/结果截断（⚠️：核心包内未见 ToolUsage 超时参数；`string_utils.py:30` 的 truncate 仅处理函数名合规）。
- 沙箱：核心 ❌；crewai-tools 有 `e2b_sandbox_tool`、`daytona_sandbox_tool`（🟡 独立包）。
- 独立包 `crewai-tools` 60+ 内置工具（brave/exa/firecrawl/oxylabs 搜索、爬取、SQL 系列、composio/multion/browserbase、llamaindex 适配等）。

**6 Skill 机制【核心】**
- `skills/` 全套：`registry.py`（SkillRef 解析、本地路径/Plus 平台缓存双源、`download_skill:275`、SKILL.md frontmatter 版本对齐 :183-209）、`loader.py`/`parser.py`/`validation.py`/`cache.py`/`events.py`、`tool.py`（SkillTool 工具化，渐进激活 `activate` 参数控制只读元数据还是加载全量 SKILL.md 指令，registry.py:134）。
- CLI `crewai skills` 子命令（lib/cli/src/crewai_cli/skills/）安装/列出；Flow 侧有 `flow/skill.py` 挂钩；`experimental/skills/` 仅占位。

**7 规划推理【核心，能力窄】**
- `Crew.planning=True`（crew.py:347）→ `_handle_crew_planning`（crew.py:1454）→ `CrewPlanner`（utilities/planning_handler.py:37）：造一个 "Task Execution Planner" agent，一次性为每个任务生成 step-by-step 计划（`PlanPerTask` Pydantic），注入各任务 description——**预执行规划，不参与运行时循环**。
- 运行时护栏：`max_iter` 截断（crew_agent_executor.py:365/:525，`handle_max_iterations_exceeded`）；guardrail 失败重试 `guardrail_max_retries=3`（task.py:279）；`AgentReasoning`（utilities/reasoning_handler.py:107）把推理模型的思考过程结构化（ReasoningPlan/AgentReasoningOutput）供展示与评估。
- 无 reflect/自评循环、无预算（token/调用数）硬闸（❌）；结构化输出由 Task.output_json/output_pydantic 承担（task.py:175/:185）。

**8 编排【核心】**
- 双模型：**Crew**（process 仅 sequential/hierarchical，process.py:6；任务级 `async_execution` 并发 + context 依赖，crew.py:788-865；`kickoff_for_each`(:1094) 批量）与 **Flow**（事件驱动，可成环/分支/并行）。
- Flow 引擎：`flow/runtime/__init__.py#Flow:442`（kickoff:2069，按 `_order_start_methods_for_kickoff` 排序起跑）；DSL `@start`(dsl/_start.py:18)/`@listen`(_listen.py:18，支持 and_/or_ 组合)/`@router`(_router.py:97，返回值字符串选分支)；步骤编译为动作对象（runtime/_actions.py：Code/Tool/Crew/Agent/Expression/**Script/Each**——EachAction:313 支持声明式 each 循环与 if_ 条件）。
- **YAML 声明式 Flow**：`flow/flow_definition.py` 可序列化定义 + CLI `run_declarative_flow.py`（`uv run crewai run` 内嵌项目环境执行）；其中 ScriptAction（_actions.py:252）把 YAML 内嵌 Python 源码 AST 包装成函数执行，**默认禁用**、需 `CREWAI_ALLOW_FLOW_SCRIPT_EXECUTION=1` 显式放行（FlowScriptExecutionDisabledError:49）。
- 组合：`FlowTrackable`（flow/flow_trackable.py:15）+ contextvar（flow/flow_context.py）让 Flow 内创建的 Crew/Agent 自动携带 flow_id/request_id——正交不互侵。
- 可视化：`flow/visualization/`（builder/renderers）+ CLI plot-flow；`crewai plot-flow`。无任意 DAG 图引擎（循环语义只在事件层，❌ 对比 LangGraph/ADK workflow）。

**9 多 Agent【核心】**
- hierarchical 真相：`_run_hierarchical_process`（crew.py:1516）= `_create_manager_agent`（:1521，自定义 manager_agent 强制清空 tools :1535 抛错；否则用 manager_llm 造 manager，挂 `AgentTools(agents).tools()` 委派工具）→ 仍走 `_execute_tasks` 顺序执行、executing_agent 换成 manager（:497）——**manager+委派工具，不是调度器**。
- 委派工具组：`tools/agent_tools/agent_tools.py#AgentTools:16`（delegate_work / ask_question，描述模板带 coworkers 列表）。
- 跨框架适配：`agents/agent_adapters/`（`LangGraphAgentAdapter:40`、`OpenAIAgentAdapter:51`）把 LangGraph/OpenAI Agents 的 agent 当 crewAI agent 用——反向互操作通道。
- A2A 完整实现：`a2a/wrapper.py#wrap_agent_with_a2a_instance:97`（agent 获得远端委派能力，并发 fetch AgentCard :262、prompt 增强 :639）、`utils/agent_card.py#inject_a2a_server_methods:579`（**agent 反向暴露 to_agent_card**）、`updates/{streaming,polling,push_notifications}` 任务更新通道、`auth/` 鉴权、`extensions/`（a2ui）；事件 32 个 A2A 类型（events/types/a2a_events.py）。
- 无 swarm/registry 概念（❌，靠 manager+委派+A2A 组合）。

**10 持久化【核心】**
- Crew checkpoint：`Crew.checkpoint`（crew.py:400，CheckpointConfig 经 `_coerce_checkpoint`）+ `state/checkpoint_listener.py` 监听事件落库；恢复经 `_get_execution_start_index`（crew.py:1548，找第一个 output 为 None 的任务续跑）；`checkpoint_inputs/train`(:418)。
- replay：`Crew.replay(task_id)`（crew.py:2034）从任意中间任务重放，数据源 `KickoffTaskOutputsSQLiteStorage`（memory/storage/kickoff_task_outputs_storage.py:18，WAL、记录 task_id/expected_output/output/inputs/was_replayed）。
- Flow 持久化：`flow/persistence/base.py#FlowPersistence:18`（ABC）+ SQLite 实现（sqlite.py:24）+ 工厂 + `@persist` 装饰器（decorators.py:147）；`state/runtime.py#RuntimeState:177`。
- 存储.dict：记忆 LanceDB/Qdrant、执行日志/工具缓存 SQLite；无 Postgres/Redis 后端（❌）。

**11 HITL【核心，反馈式形态】**
- `Task.human_input`（task.py:233）→ 执行器在 **LLM 已给出答案之后**调用 `_handle_human_feedback`（crew_agent_executor.py:1625，同步/异步 :1637 双版本）——循环收集反馈直到满意，不是任务前审批（与 interrupt/resume 范式不同）。
- 通道抽象：`core/providers/human_input.py#HumanInputProvider:60`（Protocol：setup_messages/post_setup_messages/handle_feedback）+ `SyncHumanInputProvider:147` 控制台实现 + `get_provider` 工厂（:37 导入）——企业可换 Web 审批通道；`setup_messages` 支持会话恢复语义。
- Flow 级：`flow/human_feedback.py`（HumanFeedbackResult:149/HumanFeedbackConfig:189/PreReviewResult:218/**DistilledLessons:226**——LLM 把人审反馈蒸馏为可复用经验）+ `flow/async_feedback/` 异步人审 + `flow/dsl/_human_feedback.py#human_feedback:23` 装饰器。
- 无 First-class 中断原语/挂起恢复存储（❌ 该形态；恢复靠 checkpoint 维度）。

**12 观测评估【核心】**
- 统一事件总线 `CrewAIEventsBus`（events/event_bus.py:95）：同步 handler 走线程池、异步走专用 event loop、`handler_graph.py` 做依赖编排；事件类型按域分文件（events/types/：a2a 32 个、tool_usage 9、llm 6、mcp 8、task 4、skill 7、system 5、llm_guardrail 3 + event_types.py 主体）。
- 遥测：**默认开启** OTLP 匿名上报 `https://telemetry.crewai.com:4319`（telemetry/constants.py:9-11）；关闭需 `OTEL_SDK_DISABLED` 或 `CREWAI_DISABLE_TELEMETRY`（lib/crewai-core/src/crewai_core/telemetry.py:269-270）；采集 crew 结构概要（telemetry.py:284 crew_creation）。
- 平台 trace：`events/listeners/tracing/`（trace_listener.py 挂事件总线、TraceBatchManager 批量上传、需 `get_auth_token`——即付费平台通道）。
- 回调：`Crew.step_callback`（crew.py:299）+ `Task.callback`（task.py:160）；usage_metrics 成本聚合。
- 评估（弱）：`experimental/evaluation/`（AgentEvaluator:47、run_experiment:56 基线对比/回归断言、metrics/）；CLI `crewai train`（多迭代 LLM 打分微调提示词，utilities/training_handler.py）+ `crewai test`（评分）——评测仅 OpenAI 评分模型路线（⚠️ 待确认评分模型限制，来自文档口径）。

**13 安全治理【核心切入 + 大量 TODO】**
- Guardrail 三形态：`Task.guardrail/guardrails`（task.py:252/:263 + utilities/guardrail.py#process_guardrail:123，失败重试 3 次）；`LLMGuardrail`（tasks/llm_guardrail.py:49，LiteAgent 驱动）；`HallucinationGuardrail`（tasks/hallucination_guardrail.py:20）。
- Hooks 拦截层：`hooks/dispatch.py#InterceptionPoint:40` 11 个切入点（EXECUTION_START/INPUT/OUTPUT/EXECUTION_END + PRE/POST_MODEL_CALL + PRE/POST_TOOL_CALL + PRE/POST_STEP），`register:119`/`HookAborted:75` 可中止执行——治理/审计/改写的正式切入点。
- `security/`：`Fingerprint`（fingerprint.py:41，组件身份指纹+审计元数据）+ `SecurityConfig`（security_config.py，注释明示 Authentication/Scoping/Impersonation 均 **TODO**）。
- 凭据：`crewai_core/token_manager.py#TokenManager:22` Fernet 加密落盘（登录 token）；工具凭据走 EnvVar 声明 + CLI `build_env_with_all_tool_credentials`。
- 脚本执行门控（FlowScriptExecutionDisabledError）；无 PII/内容安全库、无细粒度权限模型（❌）。

**14 部署运行时【生态（付费平台）】**
- OSS 无内置 server/FastAPI/Docker（❌）；运行入口 = Python 库调用或 CLI `crewai run`（含 TUI 模式 crew_run_tui.py）。
- `crewai deploy create/list/push/validate/status/logs/remove`（lib/cli/src/crewai_cli/cli.py:714-790 + deploy/main.py）全部是对 CrewAI 企业平台的 REST 客户端（PlusAPI）。
- 定时/事件触发：`crewai triggers`（triggers/main.py:23 list_triggers/:37 execute_with_trigger）同为平台侧客户端——cron/webhook 在 AMP 平台，不在 OSS。
- 会话式：`crewai chat`（cli.py:997 → crew_chat.py）本地起 chat；Flow conversational mixin（flow/conversational_mixin.py）。
- 企业 REST 契约仅文档：docs/v1.15.21/enterprise-api.base.yaml（/inputs、/kickoff、/status、/resume + webhook）。

**15 管理平面【生态（付费平台）】**
- 控制台/SSO/组织/计费在付费 AMP：`crewai login/logout`（oauth2，authentication/ + enterprise/main.py#configure:21 对接企业 OAuth 配置）、`organization/`（组织切换客户端）。
- OSS 侧本地界面仅 TUI：`crew_run_tui.py`（运行台）、`checkpoint_tui.py`（断点浏览）、`memory_tui.py`（记忆浏览）、`tui_picker.py`。
- `plus_api.py`（再导出 crewai_core.plus_api.PlusAPI）+ `platform_tools_catalog.py`（平台工具目录）是对接面；无自托管 console/admin（❌）。

## 6. 设计决策要点
1. **双正交编排模型 + contextvar 桥接**：Crew（LLM 协作语义）与 Flow（确定性事件流）完全解耦，靠 `FlowTrackable` 基类 + `flow_context` 的 contextvar 在对象实例化瞬间捕获 flow_id——Flow 内嵌 Crew 零参数侵入，是本仓最干净的分层手法（flow/flow_trackable.py:15）。
2. **记忆即 Flow**：统一 Memory 的写入（EncodingFlow）与召回（RecallFlow）本身就用 Flow 引擎实现（`is_crewai_internal` 标记、抑制事件外发）——框架自举食用；质量三信号加权（semantic/recency 半衰期/importance）+ 置信度驱动的探索预算，取代静态 short/long/entity 分类。
3. **LLM 层「原生优先、LiteLLM 兜底」**：六家原生 SDK 直连拿全参数控制（含各家 max_retries/cache 断点），其余长尾全推 LiteLLM——比全走 LiteLLM 的框架多一层性能/可控性，比全自研省维护面（llm.py __new__ 工厂 + SUPPORTED_NATIVE_PROVIDERS 常量表校验）。
4. **执行日志即重放源**：每次 kickoff 落 SQLite（WAL），`replay(task_id)` 从任意任务重放 + checkpoint 自动断点续跑 + Flow @persist——三种恢复语义共享「事件/输出先落盘」的单一事实（kickoff_task_outputs_storage.py / crew.py:2034 / flow/persistence/）。
5. **hierarchical 是委派不是调度**：manager agent 挂 delegate_work/ask_question 工具顺序执行任务清单——多 agent 协作被建模为「工具化的人际委派」，与图调度器范式（LangGraph/ADK）刻意不同；跨框架互操作反而靠 adapters（langgraph/openai_agents）+ A2A 双向补足。
6. **HITL 选择「答案后反馈」而非「中断-恢复」**：human_input 在 LLM 出答案后进反馈循环，人审通道抽象成 Protocol（HumanInputProvider）留企业 Web 审批接口；Flow 级进一步用 LLM 把人审蒸馏成 DistilledLessons 反哺记忆。
7. **OSS/付费边界激进**：遥测默认外发（telemetry.crewai.com:4319，需环境变量显式关）、trace 上传需平台登录、deploy/triggers/skills 分发全指向 AMP——开源核心可用，但「平台重力」处处可感（企业引入第一件事是关遥测）。
8. **声明式 YAML Flow 的安全取舍**：ScriptAction 允许 YAML 内嵌 Python 源码，但默认禁用 + env 显式放行 + AST 重包装（不插值用户输入）——「信任边界=项目源码」的明确注释（runtime/_actions.py:252-310）。

## 7. 跨语言对齐
（不适用：crewAI 无官方跨语言对等实现；本档案为 Python 版。）
