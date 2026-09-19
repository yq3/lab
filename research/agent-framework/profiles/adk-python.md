# Google ADK（adk-python）框架档案
> 基线：~/develop/opensource/adk-python @ 7b246e01 2026-09-11；版本 **2.9.0**（`src/google/adk/version.py`，pyproject `dynamic=["version"]` 注入；git tag 仅到 v1.32.0、落后 1611 commits，**以包内版本为准**）

## 1. 定位
Google 官方「Agent Development Kit」Python 实现：面向构建**生产级、模型无关、服务全可插拔**的多 agent 系统的全代码框架（库 + CLI，非低代码平台）。核心卖点是三层可插拔——模型（注册表 + 多供应商 adapter）、执行流（request processor 管道）、服务三件套（Session/Artifact/Memory，InMemory → SQL/GCS/Vertex 同接口），并与 Vertex AI 企业工具链（Agent Engine、RAG、Model Armor、Eval）深度集成。目标用户是企业后端/平台工程师；`adk web` 调试台 + `adk eval` + `adk deploy` 覆盖开发-评估-部署闭环。2.x 相对 1.x 的最大变化：新增 `workflow/` 通用图引擎、`App` 顶层容器、`Context` 新统一上下文 API、skills 实验支持。

## 2. 仓库结构与核心包
- 单包 `google-adk`（PEP 621，`pyproject.toml`，src 布局），入口 `adk` = `google.adk.cli`（click）。
- `src/google/adk/` 子包：`agents/`（BaseAgent 家族 + Context/InvocationContext/RunConfig）、`workflow/`（2.x 新图引擎）、`flows/llm_flows/`（执行流 + request processors）、`sessions/`、`artifacts/`、`memory/`、`models/`（LLM 注册表与供应商）、`tools/`（含 `mcp_tool/`、`openapi_tool/`、`retrieval/`、Google 云工具族）、`auth/`、`code_executors/`、`planners/`、`skills/`、`a2a/`（协议双向支持）、`apps/`（App 容器 + 事件压缩）、`cli/`（web/api_server/run/eval/deploy/conformance）、`evaluation/`（eval 框架 + 用户模拟）、`telemetry/`、`plugins/`、`live/`（双向流）、`optimization/`（GEPA 提示词优化）、`integrations/`（firestore/redis/e2b/daytona/livekit/langchain/crewai 等 21 项）、`labs/`（antigravity、openai adapter）、`environment/`（本地/沙箱环境抽象）。
- 附 `tests/`、`docs/`；无根级 server 代码——运行时全部经 CLI 起（devserver 内嵌）。

## 3. 核心抽象清单

| 符号 | 路径 | 说明 |
|---|---|---|
| `BaseAgent(BaseNode)` | agents/base_agent.py#BaseAgent | 一切 agent 基类；2.x 起 agent 即 workflow 节点 |
| `LlmAgent` / `Agent` 别名 | agents/llm_agent.py#LlmAgent(:259) / :1346 `Agent: TypeAlias = LlmAgent` | LLM agent 主类：model/instruction/tools/callbacks/output_schema/planner |
| `SequentialAgent` / `ParallelAgent` / `LoopAgent` | agents/{sequential,parallel,loop}_agent.py | 经典三工作流 agent（编排树内节点） |
| `Workflow(BaseNode)` | workflow/_workflow.py#Workflow(:147) | 2.x 通用图引擎：edges→Graph、SETUP/LOOP/FINALIZE 编排循环 |
| `FunctionNode` / `@node` / `Edge` / `DEFAULT_ROUTE` | workflow/_function_node.py、_node.py、_graph.py | 图节点（函数签名↔state_schema 校验）、条件路由 |
| `Context` | agents/context.py#Context(:112) | 新统一上下文：state/actions/artifacts/credentials/run_node/request_credential/branch |
| `InvocationContext` + `_InvocationCostManager` | agents/invocation_context.py:87/:57 | 一次调用的运行时数据；llm 调用计数器 |
| `Runner` | runners.py#Runner(:179) | 对外执行入口，`run_async()` 异步事件流 |
| `SingleFlow` / `AutoFlow` | flows/llm_flows/single_flow.py:84 / auto_flow.py | LLM 执行流；AutoFlow = SingleFlow + transfer processor |
| `BaseLlmRequestProcessor` | flows/llm_flows/_base_llm_processor.py:32 | 请求处理管道（instructions/output_schema/transfer/compaction/cache/fencing…） |
| `Session` / `State` | sessions/session.py / state.py:61 | app/user/session 三元组 + 作用域前缀 state（app:/user:/temp:） |
| `BaseSessionService` 族 | sessions/（InMemory/Database/SQLite/VertexAi） | 持久化服务族；integrations 下另有 Firestore/Redis |
| `Event(LlmResponse)` / `EventActions.state_delta` | events/event.py:91 / event_actions.py:94 | 事件溯源：一切状态变更落为事件增量 |
| `BaseMemoryService` 族 | memory/（InMemory/VertexAiRag/VertexAiMemoryBank） | 跨会话记忆，RAG 交给 Vertex 托管 |
| `BaseTool` / `FunctionTool` | tools/base_tool.py:57 / function_tool.py:93 | 工具基类 + 自动函数调用（AFC） |
| `BaseToolset` + `ToolPredicate` | tools/base_toolset.py:66/:44 | 工具集抽象 + 谓词过滤（per-agent tool 可见性） |
| `McpToolset` / `to_mcp` | tools/mcp_tool/mcp_toolset.py / _agent_to_mcp.py | MCP 双向：消费 MCP server / agent 反暴露为 MCP server |
| `AgentTool` | tools/agent_tool.py:109 | agent-as-tool（含单轮/Task 变体） |
| `RemoteA2aAgent` / `to_a2a()` | agents/remote_a2a_agent.py:625 / a2a/utils/agent_to_a2a.py:79 | A2A 协议消费端 / 服务端（Starlette app） |
| `BaseLlm` + `LLMRegistry` + `FallbackModel` | models/base_llm.py / registry.py#LLMRegistry:62 / _fallback_model.py:207 | 模型 SPI、正则注册表、故障转移包装 |
| `AuthCredential` / `BaseCredentialService` | auth/auth_credential.py / credential_service/base_credential_service.py:28 | 工具鉴权（API key/HTTP/OAuth2/SA）+ 凭据存取服务 |
| `SkillToolset` + `SkillRegistry` | tools/skill_toolset.py:1319 / skills/skill_registry.py:26 | SKILL.md 渐进披露（List/Search/Load/RunScript 四工具，实验性） |
| `BasePlanner` / `PlanReActPlanner` / `BuiltInPlanner` | planners/ | ReAct 式计划-执行 / Gemini 内置 thinking |
| `NodeInterruptedError(BaseException)` | workflow/_errors.py:22 | HITL 中断原语（BaseException 防被吞） |
| `App` | apps/app.py#App(:53) | 2.x 顶层容器：root_agent 或 root_node + 应用级 plugins + 压缩/可恢复配置 |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | 注册表 + Gemini/LiteLlm/Anthropic 原生 adapter，流式/回退/缓存齐全 | models/registry.py#LLMRegistry、models/_fallback_model.py#FallbackModel |
| 2 | 上下文工程 | ✅ | token 阈值事件压缩、内容压缩、LLM 摘要器、显式 prompt cache | flows/llm_flows/compaction.py、apps/compaction.py、flows/llm_flows/context_cache_processor.py |
| 3 | 记忆 | ✅ | MemoryService 三件套，跨会话 RAG 记忆交 Vertex 托管 | memory/vertex_ai_rag_memory_service.py:167、tools/preload_memory_tool.py |
| 4 | RAG | 🟡 | 无自建向量库抽象，检索 = Vertex RAG/Search 工具族 + llama_index 适配 | memory/vertex_ai_rag_memory_service.py、tools/retrieval/vertex_ai_rag_retrieval.py |
| 5 | 工具系统 | ✅ | AFC 函数工具 + Toolset 谓词过滤 + MCP 双向 + OpenAPI/鉴权 + 7 种代码执行器 | tools/function_tool.py:93、tools/mcp_tool/_agent_to_mcp.py、code_executors/ |
| 6 | Skill 机制 | ✅ | 主包内 SKILL.md 渐进披露四工具 + 沙箱脚本执行（标注 experimental） | tools/skill_toolset.py:1319#SkillToolset、skills/README.md |
| 7 | 规划推理 | ✅ | Plan-ReAct planner、内置 thinking planner、GEPA 提示词优化、max_llm_calls=500 硬预算 | planners/plan_re_act_planner.py:35、flows/llm_flows/_nl_planning.py、optimization/、run_config.py:40 |
| 8 | 编排 | ✅ | 2.x 通用图引擎（条件路由/并行 Join/动态节点/重试/超时）+ 经典三工作流 agent + `adk web` 可视化 | workflow/_workflow.py#Workflow:147、agents/parallel_agent.py:250、cli/cli_tools_click.py:2121 |
| 9 | 多 Agent | ✅ | 层级树 + transfer 工具 + AgentTool + A2A 双向（RemoteA2aAgent/to_a2a） | flows/llm_flows/auto_flow.py、agents/remote_a2a_agent.py:625、a2a/utils/agent_to_a2a.py:79 |
| 10 | 持久化 | ✅ | SessionService 4 核心实现 + 2 集成包（InMemory/SQLite/SQLAlchemy 任意 SQL/VertexAi + Firestore/Redis）+ 事件溯源 state + 回放/rewind | sessions/database_session_service.py:285、events/event_actions.py:94、workflow/utils/_replay_manager.py |
| 11 | HITL | ✅ | 节点中断 + request_confirmation 工具级审批 + resume_inputs 恢复 + UiWidget | workflow/_errors.py:22、flows/llm_flows/request_confirmation.py:259、runners.py:605、events/ui_widget.py:25 |
| 12 | 观测评估 | ✅ | OTel 全链路 + callback 列表化 + 完整 eval 框架（轨迹/LLM-as-judge/rubric/用户模拟） | telemetry/setup.py、agents/llm_agent.py:886、evaluation/eval_set.py:24、cli/cli_tools_click.py:1252 |
| 13 | 安全治理 | 🟡 | 治理靠 callback/plugin 切入点 + 事件审计轨迹；内容安全走 Model Armor/Vertex 生态，无内置 PII/guardrail 库 | agents/llm_agent.py:488-550、plugins/、integrations/model_armor/ |
| 14 | 部署运行时 | ✅ | `adk web/api_server/run/deploy/eval/optimize/conformance` CLI 全家桶 + to_a2a Starlette + Agent Engine/Cloud Run deployer + Live 双向流 | cli/cli_tools_click.py（:945 run、:2121 web、:1252 eval、:445 deploy）、a2a/utils/agent_to_a2a.py:79、live/ |
| 15 | 管理平面 | 🟡 | 本地 `adk web` 控制台（会话/事件/trace 浏览）+ 多租户命名空间内置；云端管理面依托 Vertex AI Agent Engine，框架本身无 admin/billing | cli/adk_web_server.py、cli/browser/（内置 React 前端）、sessions/session.py:43-47 |

## 5. 维度证据明细

**1 模型接入【核心】**
- `LLMRegistry`（models/registry.py:62）按模型名正则解析 `BaseLlm` 子类，支持 `register()` 与懒注册；LlmAgent.model 只填字符串即可。
- 供应商 adapter：`Gemini`/`GoogleLLM`（models/google_llm.py:96，AI Studio/Vertex 双通道）、`LiteLlm`（models/lite_llm.py，代理至 LiteLLM 百余模型，含 anthropic provider 特判 :418）、`AnthropicLlm` 原生（models/anthropic_llm.py:132，SSE 流式注释详尽）、`Gemma`（gemma_llm.py:168，Gemma3 function-calling 兼容垫片 + Ollama 变体 :375）、`ApigeeLLM`（企业网关）、labs 下 `OpenAiLlm`/`OpenAiResponsesLlm`（labs/openai/）。
- `FallbackModel`（models/_fallback_model.py:207）包装多模型顺序回退，统一各家 provider 的错误归一化（:182 注释）。
- 流式：`BaseLlm.generate_content_async(stream=)`；Live API 走 `flows/llm_flows/_live_llm_flow.py`。usage 统计：`LlmResponse.usage_metadata`（models/llm_response.py:139）。默认模型 `gemini-3.5-flash`，可用 `LlmAgent.set_default_model` 覆盖（llm_agent.py:295）。
- 显式 prompt cache：`gemini_context_cache_manager.py` + `ContextCacheRequestProcessor`（flows/llm_flows/context_cache_processor.py:36，从 session 事件恢复 cache 元数据）。

**2 上下文工程【核心】**
- `include_contents: 'default'|'none'`（llm_agent.py:431）控制历史注入；instruction 支持静态字符串或 callable（instructions processor）。
- 事件压缩：`EventsCompactionConfig` token 阈值触发（apps/compaction.py#_estimate_prompt_token_count:151 + flows/llm_flows/compaction.py 请求处理器，压缩后记 Compaction 事件防重复）；内容压缩 `flows/llm_flows/_content_compaction.py`（Gemini API 原生 content compaction，含函数调用恢复 :123）。
- 摘要器抽象 `BaseEventsSummarizer`/`LlmEventSummarizer`（apps/）；`output_schema` 结构化输出（llm_agent.py:443，且支持与 tools 并用，经 `_output_schema_processor` + `_model_response_finalizer` 兜底）。
- `EventCompaction` 事件动作（event_actions.py:58）使压缩本身可溯源、可恢复。

**3 记忆【核心】**
- `BaseMemoryService`（memory/base_memory_service.py:44）两个方法族：`add_session_to_memory` + `search_memory`（返回 `SearchMemoryResponse`/`MemoryEntry`）。
- 实现：`InMemoryMemoryService`、`VertexAiRagMemoryService`（:167，Vertex AI RAG 托管语料）、`VertexAiMemoryBankService`（:175，Memory Bank 托管记忆）。
- 工具化：`preload_memory_tool`/`load_memory_tool`（tools/）注入检索结果；Context 统一暴露 memory 访问（agents/context.py）。

**4 RAG【核心+生态】**
- 框架不含向量库/切片/rerank 自研抽象；RAG = 托管服务：VertexAiRag 工具族（tools/vertex_ai_search_tool.py、discovery_engine_search_tool.py、enterprise_search_tool.py）。
- `tools/retrieval/`：`BaseRetrievalTool` + `VertexAiRagRetriever` / `LlamaIndexRetriever`（桥接 llama_index 生态）/ `FilesRetriever`（本地文件）。评 🟡：正式抽象存在但检索能力本体在 Vertex/llama_index 侧。

**5 工具系统【核心】**
- `FunctionTool`（tools/function_tool.py:93）：Python 函数签名+docstring 自动生成 declaration，Gemini AFC 自动执行；`_function_tool_declarations`/`_automatic_function_calling_util` 支撑。
- `BaseToolset`（base_toolset.py:66）+ `ToolPredicate`（:44）：`before_agent_callback(toolset, callback_context)` 返回谓词实现 per-agent/per-run 工具可见性过滤；McpToolset/OpenApiToolset/ToolboxToolset/SkillToolset 皆走此抽象。
- MCP 双向：消费端 `McpToolset`（mcp_tool/mcp_toolset.py，stdio/SSE/StreamableHTTP + 会话管理 + OAuth），服务端 `_agent_to_mcp.py` 把 agent 变成 MCP server（`server.run(transport="stdio"|"streamable-http")`，:188 注释）；另有 stdio config 开关 `_set_allow_config_stdio_servers`（:78，安全闸门）。
- OpenAPI：`tools/openapi_tool/`（spec 解析器 + auth 子包）；企业工具族：BigQuery/Spanner/Bigtable/PubSub/Data Agent/API Hub/Application Integration/Google Toolbox。
- `ToolContext`/`Context`：state 增量写、artifacts、`request_credential`（agents/context.py:659）、`actions`（escalate/end_invocation 等）、tool_confirmation。
- 鉴权：`auth/` 全套——AuthCredential（Http/OAuth2/ServiceAccount 模型，auth_credential.py:70-139）、exchanger/refresher、`in_memory/session_state` 两种 `BaseCredentialService`（credential_service/base_credential_service.py:28）、`authenticated_function_tool.py`。
- 代码执行：7 个 executor（built_in/container/gke/unsafe_local/vertex_ai/agent_engine_sandbox + base），`timeout_seconds`（base_code_executor.py:81）。

**6 Skill 机制【核心，实验性】**
- `skills/`（README 明示 experimental）：`SkillRegistry`（skill_registry.py:26）+ `SkillToolset`（tools/skill_toolset.py:1319）实现渐进披露四工具——`ListSkillsTool`(:209)/`SearchSkillsTool`(:240)/`LoadSkillTool`(:304 读 SKILL.md 指令)/`LoadSkillResourceTool`(:398) + `RunSkillScriptTool`(:960，脚本经 `_SkillScriptCodeExecutor`(:628) 沙箱执行)。
- 与 Claude Agent Skills 格式对齐（SKILL.md 必需，skill_toolset.py:175）；另有 integrations/skill_registry（GCP 托管源）。

**7 规划推理【核心】**
- `PlanReActPlanner`（planners/plan_re_act_planner.py:35）：ReAct 式计划-执行循环，经 `flows/llm_flows/_nl_planning.py` 处理器把计划注入请求；`BuiltInPlanner`（built_in_planner.py:32）用 Gemini thinking_config。
- 预算护栏：`RunConfig.max_llm_calls` 默认 500（run_config.py:40 `_DEFAULT_MAX_LLM_CALLS`，`ADK_MAX_LLM_CALLS` 环境变量覆盖），由 `_InvocationCostManager.increment_and_enforce_llm_calls_limit`（invocation_context.py:57）抛 `LlmCallsLimitExceededError` 硬停。
- `optimization/`：GEPA 遗传式提示词优化（gepa_root_agent_prompt_optimizer.py）+ agent_optimizer；eval rubric 反哺。
- 结构化输出 `output_schema`（Pydantic→Schema）；无内置 reflect 循环（reflect_retry 以 plugin 形态存在：plugins/_reflect_retry_model_plugin.py）。

**8 编排【核心】**
- 2.x `Workflow`（workflow/_workflow.py:147）：声明式 `edges: list[EdgeItem]` → `Graph.from_edge_items().validate_graph()`；`DEFAULT_ROUTE` 条件路由（FunctionNode 返回值选边）、`JoinNode` 并行汇合、`@node` 装饰器 + `ctx.run_node()` 动态节点（`max_concurrency` 只管边触发节点防死锁 :163 注释）、`RetryConfig`/`NodeTimeoutError`、`state_schema` 与函数签名交叉校验（:197）。
- 编排循环 `_run_impl` = SETUP（seed START triggers）→ LOOP（NodeRunner 调度）→ FINALIZE（收集终端输出 + 中断）；`rerun_on_resume` 控制恢复语义。
- 经典三件套仍在：`SequentialAgent`（sequential_agent.py:94）/`ParallelAgent`（parallel_agent.py:250）/`LoopAgent`（loop_agent.py:66 + ExitLoopTool）；agent 树构造时回填 parent_agent。
- 可视化：`adk web`（cli_tools_click.py:2121）内置编译好的 React 前端（cli/browser/）。LangGraph 互操作：`LangGraphAgent`（agents/langgraph_agent.py:84）把 compiled StateGraph 适配为 ADK agent（thread_id 由三元组派生，checkpointer 兼容）。

**9 多 Agent【核心】**
- 层级树 + transfer：`AutoFlow` 挂 `agent_transfer.request_processor`（auto_flow.py），为可达 agent 注入 `transfer_to_agent` 工具（tools/transfer_to_agent_tool.py），支持 parent↔sub↔peer 方向及 `disallow_transfer_to_peers`。
- `AgentTool`（agent_tool.py:109）：agent-as-tool，`_SingleTurnAgentTool`(:393) 与 `_TaskAgentTool`(:440，配合 agents/llm/task/ 的 `FinishTaskTool` 表达 A2A 任务语义)。
- A2A 双向：`RemoteA2aAgent(BaseAgent)`（remote_a2a_agent.py:625）消费远端 A2A（AgentCard 解析 :400）；`to_a2a(agent_or_workflow)`（a2a/utils/agent_to_a2a.py:79）产出 Starlette app，事件↔任务转换在 a2a/converters/（含 long_running_functions 映射），`a2a_experimental` 装饰器显式标注实验态（a2a/experimental.py）。
- `ManagedAgent`（agents/_managed_agent.py:120）：Vertex AI 托管 agent 的客户端适配。无独立 "AgentTeam/swarm" 抽象（❌，由层级树 + transfer + A2A 组合覆盖）。

**10 持久化【核心】**
- `BaseSessionService`（sessions/base_session_service.py:63）：`get_session/create_session/append_event/list_sessions…`；实现：InMemory、`SQLiteSessionService`、`DatabaseSessionService`（database_session_service.py:285，SQLAlchemy，DBAPI 协议 :126，即 Postgres/MySQL 等）、`VertexAiSessionService`（:143）；integrations 下 `FirestoreSessionService`（firestore_session_service.py:79）与 `RedisSessionService`（_redis_session_service.py:53）。
- `Session` = `app_name/user_id/id` + `state` + `events[]`（session.py:39-64）——多租户命名空间内置。
- 事件溯源：`EventActions.state_delta`（event_actions.py:94）+ `artifact_delta`(:118)，append_event 即状态演进，天然审计/回放；`Session.state` 前缀作用域 `app:/user:/temp:`（state.py:64-66）。
- 恢复：workflow `ReplayManager.scan_workflow_events` 重建执行态（workflow/utils/_replay_manager.py）、`sessions/_rewind_utils.py` 回退、`ResumabilityConfig`（apps/_configs.py）。artifacts：InMemory/GCS/File 三实现（artifacts/）。

**11 HITL【核心】**
- 中断原语：`NodeInterruptedError(BaseException)`（workflow/_errors.py:22，基类防框架 except 捕获）；Workflow 收集 WAITING 节点中断并在 resume 时恢复（`_collect_remaining_interrupts`，_workflow.py:331）。
- 工具级审批：`request_confirmation` 请求处理器（flows/llm_flows/request_confirmation.py:259，注入 `adk_request_confirmation` 工具）+ `ToolConfirmation` 模型（tools/tool_confirmation.py:29）经 Context 读写（agents/context.py:268）。
- 恢复入口：Runner 从消息提取 `resume_inputs`（runners.py:605 `_extract_resume_inputs`）续跑挂起的函数调用。
- 富交互：`UiWidget`（events/ui_widget.py:25）随事件下发前端组件意图。

**12 观测评估【核心】**
- OTel：telemetry/setup.py 标准 OTLP traces+metrics 初始化（BatchSpanProcessor），`sqlite_span_exporter` 本地落盘，google_cloud/ Agent Engine exporter，`node_tracing` 图节点级 span；CLI 还有 `adk telemetry enable/disable/status`（cli_tools_click.py:406-432）。
- Callbacks：before/after × agent/model/tool 六切入点（llm_agent.py:488-550），且**接受列表形式**（`canonical_before_model_callbacks` 等 :886-931，`_normalize_callbacks`）——横切策略可叠加。
- Plugins（plugins/base_plugin.py + plugin_manager.py）：auto_tracing、debug_logging、reflect_retry、save_files_as_artifacts、bigquery_agent_analytics 等开箱组件。
- Eval：`EvalSet`/`EvalCase`（evaluation/eval_set.py:24、eval_case.py:148）；轨迹指标（trajectory_evaluator）+ 终态匹配（final_response_match_v1/v2）+ `LlmAsJudge`（llm_as_judge.py:69 AutoRater/rubric_scores）+ safety/hallucinations 评估器；用户模拟器（evaluation/simulation/，LLM 驱动多轮模拟 + 预置 persona）；`adk eval`（cli_tools_click.py:1252）+ `eval_set` 组(:1643)，GCS/local 结果管理器；`adk conformance record/test`(:568) 行为一致性回放。

**13 安全治理【核心切入 + 生态承载】**
- 无内置 guardrail 内容审查库（❌ PII/内容安全本地实现）；治理范式 = callback 六切入点（列表化，可做权限/审计/限流）+ 事件溯源审计轨迹。
- `integrations/model_armor/`（Vertex Model Armor 内容安全，🟡 生态）；`Gemma`/沙箱 code executors、MCP stdio 白名单开关（mcp_toolset.py:75-93）、api_server 的 DNS-rebinding/origin 校验中间件（cli/api_server.py:250-310）体现默认防御姿态。
- `unsafe_local_code_executor` 以命名显式警示风险。

**14 部署运行时【核心】**
- CLI（cli_tools_click.py）：`create`(:775) 脚手架、`run`(:945) 终端交互（含 resume 提示 :754）、`web`(:2121) 开发台（事件流/trace UI）、`deploy`(:445，Cloud Run/Agent Engine deployers，cli/deployers/）、`eval`(:1252)、`optimize`(:1513)、`conformance`(:568)、`telemetry`(:406)。
- `adk api_server`：FastAPI/uvicorn，`/api/reasoning_engine`（非流式）+ `/api/stream_reasoning_engine`（SSE）（cli/fast_api.py:573/:616），带 CORS 与 host 白名单中间件。
- `to_a2a()` 产出 Starlette 服务（rpc_path 前缀、agent_card、push notification/task store 注入点）；Live 双向流（live/ + `_live_llm_flow.py`）面向语音/实时。
- 无内置 cron/队列（❌，Cloud 侧 eventarc trigger 集成属 🟡）。

**15 管理平面【核心（本地台）+ 生态（云台）】**
- `adk web` 即本地控制台：会话/事件浏览、trace 查看（cli/adk_web_server.py + cli/browser/ 内置 React 产物 + cli/built_in_agents 内置辅助 agent）。
- 多租户：app_name/user_id 命名空间内建于 Session 模型；service_registry.py 管理服务装配。
- 无框架内 admin/租户计费/配置中心（❌）；云端管理面依托 Vertex AI Agent Engine（ManagedAgent/deployers/telemetry，🟡 平台承载）。

## 6. 设计决策要点
1. **Agent 即节点**：2.x 把 `BaseAgent` 直接挂在 `workflow/_base_node.BaseNode` 下，agent 树与图编排统一为同一运行时（`_run_impl` 编排循环），Sequential/Parallel/Loop 退化为图特例——与 LangGraph「一切皆图」殊途同归但保留了声明式 edges + state_schema 签名校验（`_validate_state_schema`）。
2. **事件溯源式 State**：状态只经 `EventActions.state_delta` 随事件持久化（append_event 是唯一写路径），服务实现只需追加存储；回放（ReplayManager）、rewind、审计、压缩标记全部免费获得。
3. **执行流 = 可组合 request processor 管道**：SingleFlow 装配 instructions/output_schema/transfer/compaction/cache/fencing 等处理器，AutoFlow 仅多挂一个 transfer processor——控制流特性是数据不是代码分支，用户可插入自定义 processor。
4. **双向互操作优先**：MCP 消费端（McpToolset）与服务端（agent→MCP server）、A2A 消费端（RemoteA2aAgent）与服务端（to_a2a()）成对出现；A2A 实验态用独立装饰器显式告警而非隐藏。
5. **Callback 列表化 + Plugin 双轨**：六切入点回调支持单函数或列表（canonical_*_callbacks），Plugin 再以 App 级组件聚合——横切关注点既可 per-agent 又可全局。
6. **托管服务边界清晰**：RAG/记忆/评估 judge/内容安全全部让位给 Vertex 生态（框架只留 SPI + adapter），本地开发用 InMemory/SQLite/LocalEvalService 平替，同接口切换。
7. **预算与终止双护栏**：语义终止（`is_final_response`）+ 硬预算（max_llm_calls=500，env 可调）由 `_InvocationCostManager` 在每次 LLM 调用前强制执行，防失控循环。
8. **默认模型紧贴自家**（gemini-3.5-flash 内置默认、Gemma 兼容垫片、Apigee 网关 adapter）同时保持 LiteLLM/Anthropic/OpenAI(labs) 开放通道——平台倾向明显但不封闭。

## 7. 跨语言对齐
（不适用：本档案为 adk-python；adk-java 另见 profiles/adk-java.md。要点预告：Java 版无 `workflow/` 通用图引擎与 skills 模块，以 RequestProcessor 管道 + Plugin 单接口对齐处理器思路；JDBC 持久化缺失对应本仓 DatabaseSessionService。）
