# OpenAI Agents SDK（openai-agents-python）框架档案

> 基线：~/develop/opensource/openai-agents-python @ fbd2dbca 2026-09-11；版本 0.22.2（`pyproject.toml`，包名 `openai-agents`，import 名 `agents`）

## 1. 定位

OpenAI 官方的"生产级极简"多 agent Python SDK：只提供少量原语（Agent、Runner、handoff、guardrail、tool、session、tracing），不做图编排。核心执行模型是**单循环 agent loop**（模型调用 → 工具/handoff 解析 → 循环，`max_turns` 兜底），多 agent 协作完全通过 **handoff-as-tool**（把控制流转移编码为 `transfer_to_<agent>` 工具调用）实现。默认深度绑定 OpenAI Responses API（默认模型 `gpt-5.6-luna`），但通过 `Model`/`ModelProvider` 协议与 `MultiProvider` 前缀路由全链路可换第三方模型。目标用户是从 demo 走向生产的 Python 开发者；值得注意 0.22.x 已从早期极简形态长成重量运行时：内建可中断/可序列化恢复的 `RunState`（5271 行）、成体系的多厂商沙箱子系统、HITL 审批面。

## 2. 仓库结构与核心包

- 单包仓库：`src/agents/` 一个 Python 包（约 145 个 .py），无 workspace 拆分；`examples/`、`docs/`（mkdocs，13+ 指南）、`integration_tests/`。
- 硬依赖仅 6 个：`openai>=3`、`pydantic`、`griffelib`（docstring→schema）、`typing-extensions`、`requests`、`mcp>=1.19`（`pyproject.toml`）。可选 extras 共 22 组：voice / viz / litellm / any-llm / realtime / sqlalchemy / redis / mongodb / dapr / encrypt / docker / e2b / daytona / modal / runloop / vercel / cloudflare / blaxel / s3 / temporal 等——沙箱与记忆后端按需安装。
- 子包布局（`src/agents/`）：
  - 根：`agent.py`(1083 行)、`run.py`(2635)、`run_state.py`(5271)、`tool.py`(2924)、`guardrail.py`、`agent_output.py`、`result.py`、`items.py`、`model_settings.py`、`lifecycle.py`、`repl.py`
  - `run_internal/`：循环内部件（`run_loop.py` 2683 行、`turn_resolution.py` handoff 解析、`approvals.py`、`guardrails.py`、`tool_execution.py`、`session_persistence.py`、`prompt_cache_key.py`、`model_retry.py` 等 26 文件）
  - `models/`：`interface.py`（Model/ModelProvider 协议）、`openai_responses.py`、`openai_chatcompletions.py`、`multi_provider.py`、`default_models.py`、`_openai_retry.py`
  - `handoffs/`：`__init__.py`（handoff() 工厂）、`history.py`（嵌套历史折叠）
  - `memory/`：`session.py`（协议）、`sqlite_session.py`、`openai_conversations_session.py`、`openai_responses_compaction_session.py`、`session_settings.py`
  - `mcp/`：`server.py`(2600 行)、`manager.py`（MCPServerManager）、`util.py`
  - `tracing/`：`processors.py`、`span_data.py`、`create.py`、`provider.py`、`setup.py`
  - `sandbox/`：config/manifest/mounts/snapshot/runtime/network 策略等约 28 文件
  - `voice/`、`realtime/`：语音管线与 Realtime 子系统
  - `extensions/`：`memory/`（Redis/Mongo/SQLAlchemy/Dapr/加密会话）、`models/`（litellm/any-llm）、`sandbox/`（e2b/daytona/modal/runloop/vercel/cloudflare/blaxel 七厂商）、`experimental/codex/`、`experimental/hosted_multi_agent/`、`visualization.py`、`handoff_filters.py`、`tool_output_trimmer.py`
  - `testing/`：`model.py`（ModelScript 脚本化 mock 模型）、`sandbox.py`

## 3. 核心抽象清单

| 符号 | 路径 | 一句话说明 |
|---|---|---|
| `Agent` / `AgentBase` | src/agents/agent.py:296 / :183 | dataclass 配置体：instructions（str/Callable/多语言 dict）、prompt（Responses 模板）、model、model_settings、tools、handoffs、input/output_guardrails、output_type、hooks、tool_use_behavior；`AgentBase` 与 RealtimeAgent 共享 name/tools/mcp_servers/mcp_config |
| `Agent.as_tool()` | src/agents/agent.py:583 | 把 agent 包装成 FunctionTool（结构化入参、流式透传、可 needs_approval）——agent 即工具 |
| `Runner` / `AgentRunner` | src/agents/run.py:259 / :548 | 入口门面 `run/run_sync/run_streamed`；实际循环在 `AgentRunner` + `run_internal/` |
| `RunResult` / `RunResultStreaming` | src/agents/result.py | 含 `interruptions`（待审批列表）、`to_state()` 转 RunState |
| `RunState` | src/agents/run_state.py:764 | 可序列化运行快照（格式版本 1.0→1.13），HITL 暂停/审批/跨进程恢复边界；`approve/reject/always_approve`、`to_json/from_json/to_string/from_string` |
| `Handoff` / `handoff()` | src/agents/handoffs/__init__.py:126 / :260 | 多 agent 原语：`transfer_to_<name>` 工具 + `on_invoke_handoff` + `input_type` 结构化参数 + `input_filter` + `is_enabled` + `nest_handoff_history` |
| `InputGuardrail` / `OutputGuardrail` | src/agents/guardrail.py:72 / :134 | tripwire 检查器；InputGuardrail 带 `run_in_parallel`（默认 True，与首轮模型调用并发） |
| `function_tool` / `FunctionTool` | src/agents/tool.py | 装饰器从签名+docstring 生成严格 JSON schema；`is_enabled`、`needs_approval`、工具超时、`failure_error_function` |
| `HostedMCPTool` / `MCPServerStdio/Sse/StreamableHttp` | src/agents/tool.py:1117 / src/agents/mcp/server.py:1888/:2030/:2200 | 托管 MCP 与本地三种传输 MCP 客户端，`tool_filter` 静态/动态过滤、`require_approval` |
| `AgentOutputSchema` | src/agents/agent_output.py:61 | output_type→strict JSON schema + 校验（非对象类型自动包 `{"response": ...}` 包装层） |
| `Session`（Protocol） | src/agents/memory/session.py:43 | 极小会话协议：`session_id` + `get_items/add_items/pop_item/clear_session` 四方法 + `session_settings` |
| `OpenAIResponsesCompactionSession` | src/agents/memory/openai_responses_compaction_session.py:82 | 会话装饰器：候选条目 ≥10 时自动调服务端 `responses.compact` 压缩历史（默认模型 gpt-4.1） |
| `Model` / `ModelProvider` / `MultiProvider` | src/agents/models/interface.py:37/:138、multi_provider.py:62 | 模型协议（get_response/stream_response）+ 前缀路由（无前缀或 openai/→OpenAIProvider、litellm/、any-llm/、自定义 provider_map、unknown_prefix_mode 透传） |
| `BatchTraceProcessor` / `BackendSpanExporter` | src/agents/tracing/processors.py:541 / :44 | 默认批量外发 `https://api.openai.com/v1/traces/ingest`（5s 定时刷新） |
| `Usage` | src/agents/usage.py:196 | requests/input/output/total tokens + cached/cache_write/reasoning 细节 |
| `RunHooksBase` / `AgentHooksBase` | src/agents/lifecycle.py:13 / :106 | 生命周期回调：on_llm_start/end、on_agent_start/end、on_handoff、on_tool_start/end |
| `VoicePipeline` / `SingleAgentVoiceWorkflow` | src/agents/voice/pipeline.py:21、workflow.py:62 | STT→workflow→TTS 三段语音管线 |
| `RealtimeAgent` / `RealtimeSession` | src/agents/realtime/agent.py:28、session.py:175 | WebSocket Realtime API 的有状态 agent（继承 AgentBase，支持 realtime handoff） |
| `draw_graph()` | src/agents/extensions/visualization.py:406 | graphviz 渲染 agent handoff 关系图（可选 viz extra） |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | Model/ModelProvider 协议全可替换，MultiProvider 前缀路由（openai/litellm/any-llm/自定义），任意 OpenAI 兼容客户端，内建重试与流式，默认 gpt-5.6-luna | src/agents/models/interface.py#Model；models/multi_provider.py#MultiProvider；_config.py#set_default_openai_client；models/default_models.py#get_default_model |
| 2 | 上下文工程 | ✅ | 动态 instructions、handoff input_filter、SessionSettings 条目截断、compaction 会话装饰器、服务端 context_management 透传；无本地 token 预算管理 | src/agents/agent.py#instructions；handoffs/__init__.py#HandoffInputFilter；memory/session_settings.py#SessionSettings；memory/openai_responses_compaction_session.py#OpenAIResponsesCompactionSession；model_settings.py#context_management |
| 3 | 记忆 | ✅ | Session 协议 4 方法 + SQLite/OpenAI Conversations 核心，Redis/Mongo/SQLAlchemy/Dapr/加密在主包 extensions/memory（可选依赖）；无长期记忆/用户画像 | src/agents/memory/session.py#Session；memory/sqlite_session.py#SQLiteSession；extensions/memory/__init__.py |
| 4 | RAG | 🔶 | 仅托管 FileSearchTool（OpenAI 侧检索），无 retriever/向量库/rerank/引用框架 | src/agents/tool.py#FileSearchTool |
| 5 | 工具系统 | ✅ | function_tool 严格 schema、hosted 工具组（web_search/code_interpreter/image_gen）、MCP 三传输+tool_filter+审批+Manager、工具超时/错误回注、7 厂商沙箱 | src/agents/tool.py#function_tool；mcp/server.py#MCPServerStdio；tool.py#ShellTool；tool_guardrails.py；sandbox/ |
| 6 | Skill 机制 | 🔶 | 仅 ShellTool 向托管容器透传 skills 元数据（引用/内联两种），SDK 层无 Agent Skills 抽象 | src/agents/tool.py#ShellToolInlineSkill；tool.py#ShellToolSkillReference |
| 7 | 规划推理 | ✅ | agent loop 本体即 ReAct 循环：结构化输出（strict schema）+ max_turns=10 硬护栏 + GPT-5 reasoning effort 默认表；无 plan/reflect/budget 抽象 | src/agents/agent_output.py#AgentOutputSchema；run_config.py#DEFAULT_MAX_TURNS；models/default_models.py |
| 8 | 编排 | ❌ | 无图/工作流/并行编排引擎，无 Studio；仅 handoff 链与 as_tool（并发仅 guardrail 层），draw_graph 只做渲染 | src/agents/extensions/visualization.py#draw_graph（全库 grep 无 Graph/Workflow/Supervisor 类） |
| 9 | 多 Agent | ✅ | handoff() 原语（transfer_to_* 工具、input_filter、is_enabled、nest_handoff_history）+ Agent.as_tool + voice/realtime handoff + 实验性 hosted_multi_agent | src/agents/handoffs/__init__.py#handoff；agent.py#as_tool；extensions/experimental/hosted_multi_agent/model.py |
| 10 | 持久化 | ✅ | Session 多后端 + RunState 版本化可序列化快照（暂停/恢复/sticky 决策/沙箱载荷）；无自动逐轮 checkpoint，Temporal 仅示例 | src/agents/run_state.py#RunState；memory/；examples/sandbox/extensions/temporal/ |
| 11 | HITL | ✅ | needs_approval 覆盖全部工具面（含 MCP/HostedMCP/as_tool），interruptions 中断 + RunState.approve/reject + always_approve 粘性决策跨进程恢复 | src/agents/items.py#ToolApprovalItem；run_state.py#RunState；docs/human_in_the_loop.md |
| 12 | 观测评估 | ✅ | 内建 traces/spans（10+ span 类型）默认批量外发 OpenAI + 细粒度 usage + lifecycle hooks；无 OTel exporter、无 eval 框架 | src/agents/tracing/processors.py#BackendSpanExporter；usage.py#Usage；lifecycle.py#RunHooksBase |
| 13 | 安全治理 | ✅ | 三层 guardrail（run 输入/输出 + 工具输入/输出三态处置）+ 审批 + 沙箱隔离（网络策略/挂载安全/归档限额）+ 加密会话 | src/agents/guardrail.py；tool_guardrails.py；sandbox/_mount_security.py；extensions/memory/encrypt_session.py#EncryptedSession |
| 14 | 部署运行时 | 🔶 | 无 server/队列/定时/HA 运行时；仅 realtime FastAPI/WebSocket demo 与 Temporal 持久化示例 | examples/realtime/app/server.py；examples/sandbox/extensions/temporal/ |
| 15 | 管理平面 | ❌ | 无 console/dashboard/租户/计费；trace 数据面直连 OpenAI 平台查看 | src/agents/tracing/processors.py#_OPENAI_TRACING_INGEST_ENDPOINT |

⚠️ 待确认：0 项（本次所有维度均已回源码定级；缺席能力以 ❌/🔶 标注）。

## 5. 维度证据明细

### 维度 1 模型接入
- `Model` 抽象基类：`get_response`/`stream_response` 两方法 + tracing 钩子，`ModelProvider.get_model(model_name)` 工厂（src/agents/models/interface.py:37/:138）。【核心】
- `MultiProvider` 按 `前缀/模型名` 路由：无前缀或 `openai/`→OpenAIProvider（Responses 或 ChatCompletions）；内建 `litellm/`、`any-llm/` 惰性 fallback；`provider_map` 可注册自定义；`openai_prefix_mode`/`unknown_prefix_mode` 支持 `model_id` 透传给 OpenAI 兼容端点（src/agents/models/multi_provider.py:62-252）。【核心】
- 默认绑定：`set_default_openai_key/client/api` 全局替换（src/agents/_config.py:13-27）；默认模型 `gpt-5.6-luna`（`OPENAI_DEFAULT_MODEL` 可覆盖），并按模型名正则给 GPT-5.x 系列配 reasoning effort 默认值（src/agents/models/default_models.py:99-103、:36-60）。【核心】
- 重试与超时：`ModelSettings.retry: ModelRetrySettings`（含退避），实现在 models/_openai_retry.py、run_internal/model_retry.py；另有 `examples/basic/retry.py`、`retry_litellm.py`。【核心】+【示例】
- usage/cost：`Usage` 统计 requests、input/output/total tokens、`cached_tokens`/`cache_write_tokens`/`reasoning_tokens` 细节（src/agents/usage.py:196-215）；`request_usage_entries` 按请求明细供成本核算（docs/usage.md:46）。`ModelSettings.prompt_cache_retention`/`prompt_cache_options` + run_internal/prompt_cache_key.py 管理 prompt cache。【核心】
- 第三方：`extensions/models/litellm_provider.py`、`any_llm_provider.py`（主包内，可选 extras）；WebSocket 传输的 Responses（responses_websocket_session.py、`openai_use_responses_websocket`）。【核心】

### 维度 2 上下文工程
- 动态系统提示：`instructions` 接受 `str | Callable(ctx,agent) | dict[locale,str]`（多语言）；`prompt` 直接挂 Responses Prompt 模板（src/agents/agent.py:309、Agent.prompt 字段）。【核心】
- handoff 上下文裁剪：`HandoffInputFilter` 收到 `HandoffInputData`（input_history/pre_handoff_items/new_items/run_context/input_items）可改写下一 agent 输入；`nest_handoff_history` 把上游历史折叠成嵌套摘要载荷（`handoffs/history.py#default_handoff_history_mapper`；extensions/handoff_filters.py 提供 RECOMMENDED 过滤器）。【核心】
- 历史压缩：`OpenAIResponsesCompactionSession` 是 Session 装饰器，默认候选条目 ≥10（DEFAULT_COMPACTION_THRESHOLD）触发 `responses.compact`（服务端压缩，默认模型 gpt-4.1，可自定义 should_trigger_compaction）（src/agents/memory/openai_responses_compaction_session.py:58-114）。【核心】
- 截断：`SessionSettings.limit` 条目数截断（memory/session_settings.py:38）；`ModelSettings.truncation`（Responses 参数）。本地 token 级 trim/summarize 无——`extensions/tool_output_trimmer.py` 只做工具输出裁剪。【核心】+缺口
- 服务端上下文管理：`ModelSettings.context_management: list[ContextManagement]` 原样透传 Responses API（src/agents/model_settings.py:191、models/openai_responses.py:1026）。【核心】

### 维度 3 记忆
- `Session` Protocol 仅 `session_id` + 4 方法（get_items/add_items/pop_item/clear_session），可选 `session_settings`；另有 `SessionABC` 基类（src/agents/memory/session.py:43-132）。【核心】
- 核心实现：`SQLiteSession`（含跨进程文件锁）、`OpenAIConversationsSession`（OpenAI Conversations API 托管历史）（memory/sqlite_session.py:18、openai_conversations_session.py）。【核心】
- 主包扩展后端（可选 extras）：`RedisSession`、`MongoDBSession`、`SQLAlchemySession`（任意 SQL）、`DaprSession`、`AsyncSQLiteSession`、`AdvancedSQLiteSession`、`EncryptedSession`（透明加密切面，包任意后端）（src/agents/extensions/memory/__init__.py:25-50、encrypt_session.py:106）。【核心（同包可选依赖）】
- 会话即 run 循环的持久层：`Runner.run(..., session=)`，run_internal/session_persistence.py 负责落库与回滚快照。【核心】
- 长期记忆/用户画像/遗忘：无（无 semantic memory 抽象）。❌

### 维度 4 RAG
- 仅 `FileSearchTool`（src/agents/tool.py:779）：OpenAI 托管向量检索（文件先上传 OpenAI 存储）；本地 retriever/向量库/rerank/引用标注均无。🔶
- 检索类还有 `WebSearchTool`（:817）与 `CodeInterpreterTool`（:1148），均为托管工具而非 RAG 管道。【核心（但属托管工具）】

### 维度 5 工具系统
- `@function_tool`：griffe 解析签名+docstring 生成 schema，默认强制 strict（`ensure_strict_json_schema`）；`failure_error_function` 把工具异常转成回给模型的消息；`is_enabled` 动态启停；工具级超时三策略（continue/cancel/raise，`ToolTimeoutError`）（src/agents/tool.py:449-539、:603-607）。【核心】
- 工具护栏：`ToolInputGuardrail`/`ToolOutputGuardrail`，输出三态 `allow / reject_content / raise_exception`（src/agents/tool_guardrails.py:40-116）。【核心】
- 托管工具组：WebSearch/FileSearch/CodeInterpreter/ImageGeneration/HostedMCPTool（src/agents/tool.py:779/:817/:1148/:1213/:1117）；本地执行工具：`ComputerTool`（GUI 自动化，tool.py:872）、`ShellTool`（容器网络策略 domain allowlist + skills 元数据，tool.py:1271-1500）、`ApplyPatchTool`。【核心】
- `tool_search` 工具面（tool.py:1613）：大量工具时由模型按需搜索发现——工具的渐进披露。【核心】
- MCP：本地三传输 `MCPServerStdio/Sse/StreamableHttp`（mcp/server.py:1888/:2030/:2200），`tool_filter` 支持静态 dict（allowed_tools）与动态 callable（含 ToolFilterContext + agent）（:882-1064）；`MCPServerManager` worker 池统一 connect/cleanup（mcp/manager.py）；托管侧 `HostedMCPTool` 支持 `require_approval` 与 `on_approval_request`。【核心】
- 沙箱执行：src/agents/sandbox/（manifest、挂载物化、快照、rclone 同步、归档限额、mount 安全审计）+ extensions/sandbox 七厂商（E2B/Daytona/Modal/Runloop/Vercel/Cloudflare/Blaxel）+ `SandboxAgent`；docs/sandbox/ 三篇指南。【核心】
- ToolContext（tool_context.py）：工具内读 usage、写 custom data、携带审批信息。【核心】

### 维度 6 Skill 机制
- 无 SDK 级 Agent Skills 抽象（无 skill 发现/渲染/progressive disclosure）。❌（框架层）
- `ShellTool` 参数接受 `skills` 元数据（`ShellToolLocalSkill`、`ShellToolSkillReference`、`ShellToolInlineSkill`，tool.py:1271-1350）——把技能声明透传给托管 shell 容器执行，属托管平台能力的参数化。🔶

### 维度 7 规划推理
- 循环本体：`AgentRunner.run` 组装 system prompt + tools + handoffs + output_schema 调模型，解析工具/handoff 后进入下一轮；`DEFAULT_MAX_TURNS = 10`（run_config.py:45），超限抛 `MaxTurnsExceeded`（exceptions.py:444），可经 error handler `finalize_max_turns_handler_output` 接管产出最终结果（run_internal/run_loop.py:753）。【核心】
- 结构化输出：`output_type` 任意 Python 类型 → `AgentOutputSchema`（strict 默认开启；非 BaseModel/dict 类型自动包 `{"response": ...}` TypedDict 包装；`validate_json` 严格校验并脱敏报错）（src/agents/agent_output.py:61-187）。【核心】
- 推理控制：`ModelSettings.reasoning`（effort/summary）；GPT-5.x 系列按模型名自动默认 effort（default_models.py:54-60）；reasoning 内容回放（models/reasoning_content_replay.py）。【核心】
- planning/reflection/预算：无（无 plan 数据结构、无 reflect 钩子、无 token/成本硬预算）。❌（子项）

### 维度 8 编排
- 无 Graph/Workflow/StateMachine/Supervisor 类（全库 grep 证实）；分支/循环/并行由用户代码控制，官方 pattern 在 examples/agent_patterns/（routing.py、parallelization.py、deterministic.py、forcing_tool_use.py 等）【示例】。
- `draw_graph(agent)` 用 graphviz 渲染静态 handoff 关系图（extensions/visualization.py:406，可选 viz extra）——仅可视化，非编排。【核心（只读）】
- 唯一框架级"编排"是 handoff 链（见维度 9）与 guardrail 并发（见维度 13）。

### 维度 9 多 Agent
- `handoff(agent, on_handoff=..., input_type=..., input_filter=..., is_enabled=...)`：生成默认名 `transfer_to_<agent_name>` 的工具（handoffs/__init__.py:207-211），模型调用后 `on_invoke_handoff` 返回目标 agent，`turn_resolution.py:2635` 将 `run_state._current_agent` 切换为新 agent；`input_type` 参数经 strict schema 校验后传给 `on_handoff`；`is_enabled` 可按 ctx 动态隐藏。【核心】
- `Agent.as_tool()`：agent 作为工具被调用（新 agent 收生成输入而非会话历史，原 agent 继续掌舵）；支持结构化入参、嵌套流式、嵌套审批透传到外层 run（agent.py:583-640；docs/human_in_the_loop.md:5-7）。【核心】
- realtime/voice 也各有 handoff（realtime/handoffs.py）。【核心】
- 实验性 `hosted_multi_agent`：把多 agent 编译为 Responses API beta 的托管编排 Model（extensions/experimental/hosted_multi_agent/model.py）；`experimental/codex` 把 Codex 封装为工具/线程。【核心（experimental）】
- swarm/群聊/supervisor/A2A/registry：无。❌

### 维度 10 持久化
- Session 即持久层（见维度 3），thread 语义由 `session_id` 承载；服务端托管 `OpenAIConversationsSession` + `previous_response_id`/`conversation_id` 两种续接模式（docs/sessions/index.md 755 行）。【核心】
- `RunState`：显式快照而非自动 checkpoint——`result.to_state()` 导出（含 context/usage/model responses/pending approvals/sandbox resume payload/prompt cache key），版本化序列化 1.0→1.13 带 changelog；恢复用 `Runner.run(agent, state)`（run.py:603 `run_state` 参数；run_state.py:199-216 版本表）。【核心】
- 恢复安全语义：防止对同一 Session 并发恢复、pending session write 确认机制（run_state.py:767-776）。【核心】
- Temporal durable workflow：仅 examples/sandbox/extensions/temporal/（temporal_session_manager.py 等，含 TUI）。【示例】

### 维度 11 HITL
- 声明面：`needs_approval`（bool 或 callable）覆盖 function_tool、Agent.as_tool、ShellTool、ApplyPatchTool；本地 MCP 用 `require_approval`；HostedMCPTool 用 `tool_config={"require_approval": "always"}`（docs/human_in_the_loop.md:43）。【核心】
- 中断面：暂停时 `RunResult.interruptions` 携带 `ToolApprovalItem`（agent.name/tool_name/arguments），流式同样支持（items.py:556；result.py:519；run_internal/approvals.py）。【核心】
- 决策面：`state.approve(interruption)` / `state.reject(...)` / `always_approve=True` 粘性决策（按 call_id 或工具身份记忆，存进 RunState 跨序列化存活）→ `Runner.run(agent, state)` 原地续跑（docs/human_in_the_loop.md:48-57）。程序化即时审批回调 `on_approval`。【核心】
- 示例：examples/agent_patterns/human_in_the_loop{,_custom_rejection,_stream}.py、examples/memory/*hitl*.py。【示例】

### 维度 12 观测评估
- tracing 默认开启：懒初始化默认 provider + `BatchTraceProcessor`（5s 批量刷新）+ `BackendSpanExporter` 上传 `https://api.openai.com/v1/traces/ingest`（tracing/processors.py:45/:541-576、setup.py:55-59）——数据默认出境到 OpenAI，需 `set_tracing_disabled(True)` 或 `set_trace_processors()` 显式接管。【核心】
- Span 体系：trace + 10 类 span（Agent/Task/Turn/Function/Generation/Response/Handoff/Custom/Guardrail/Transcription…，span_data.py）；`trace_include_sensitive_data` 开关、`workflow_name/trace_id/group_id/trace_metadata`（run_config.py）。【核心】
- 无内建 OTel exporter（全库 grep opentelemetry=0）；扩展点是 `TracingProcessor`/`TracingExporter` 协议。❌（OTel 子项）
- usage：见维度 1；lifecycle hooks 双层（run 级 + agent 级）可做审计回调。【核心】
- eval：无数据集/评估模块；`testing/model.py#ModelScript` 是脚本化 mock 模型（单测用，非 eval）。❌（eval 子项）

### 维度 13 安全治理
- run 级护栏：`InputGuardrail`（tripwire 触发抛 `InputGuardrailTripwireTriggered`）/`OutputGuardrail`；**input guardrail 默认与首轮模型调用并发**（`run_in_parallel=True`），tripwire 即 `model_task.cancel()`（guardrail.py:100；run.py:1726-1760）；output guardrails 之间也并行（run_internal/guardrails.py:171-225）。【核心】
- 工具级护栏：三态处置 allow/reject_content（拒绝但继续，消息回模型）/raise_exception（tool_guardrails.py:80-116）；可配 `pre_approval_tool_input_guardrails`（run_config.py:146）在审批前跑。【核心】
- 审批：见维度 11。【核心】
- 沙箱隔离：本地/七云厂商沙箱 + `_mount_security.py` 挂载安全 + 容器网络域 allowlist + 归档解压限额（sandbox/ 全目录）。【核心】
- 内容安全/PII 检测器：不自带（guardrail 函数留给用户，可接 OpenAI moderation）。❌（子项）
- 数据加密：`EncryptedSession` 静态加密会话（extensions/memory/encrypt_session.py）。【核心】

### 维度 14 部署运行时
- 无内建 server/dev server/queue/cron/HA；库形态嵌入用户应用（`Runner` 即入口）。❌（框架级）
- realtime FastAPI+WebSocket demo（examples/realtime/app/server.py:12）与 Temporal 持久化示例（examples/sandbox/extensions/temporal/）。【示例】
- `repl.py#run_demo_loop` 提供终端 REPL 调试循环（docs/repl.md）。【核心（调试件）】

### 维度 15 管理平面
- 无 console/dashboard/租户/计费/配置中心。❌
- trace 数据面直连 OpenAI 平台（`_OPENAI_TRACING_INGEST_ENDPOINT`），查看依赖 OpenAI 侧 UI——管理能力外置于 OpenAI 账号体系而非本框架。🟡（平台外置）

## 6. 设计决策要点

1. **Handoff-as-tool 是唯一多 agent 原语**：控制流转移复用工具调用协议（`transfer_to_<name>`），零新概念；`nest_handoff_history` 把上游对话折叠为嵌套摘要避免上下文爆炸。代价是没有 supervisor/群聊等高层编排，pattern 下沉到 examples。
2. **Guardrail 并发执行换延迟**：input guardrail 默认与首轮模型调用 `asyncio.gather` 并发、tripwire 即取消模型任务；`run_in_parallel=False` 可退回串行前置。这是本 SDK 最常被引用的执行时机设计。
3. **Session 极小协议 + 装饰器扩展**：4 方法协议换来实现自由度；压缩（compaction）与加密（EncryptedSession）都做成装饰器而非继承体系；Redis/Mongo/SQLAlchemy 后端放主包 extensions 靠可选依赖。
4. **HITL = 可序列化 RunState 而非回调**：暂停点导出为版本化 JSON 快照（1.0→1.13 迁移表）、粘性审批决策随快照存活、跨进程恢复——面向无状态 Web 服务设计，比进程内 interrupt 更"存储友好"；但也意味着没有自动逐轮 checkpoint。
5. **Tracing 默认外发 OpenAI**：开箱即批量上传 `api.openai.com/v1/traces/ingest`，隐私默认值激进，企业需显式关闭或换 processor——与"生产级"定位的张力点。
6. **OpenAI 深度绑定作为默认、抽象保证可逃逸**：默认模型/推理力度默认表/hosted 工具/MCP 托管形态都先服务 OpenAI 平台，但 `Model`/`ModelProvider` + `MultiProvider` 前缀路由（含 litellm/any-llm 内建 fallback）让第三方模型是一等公民而非补丁。
7. **上下文管理外包给服务端**：本地只有条目截断与工具输出裁剪，压缩走 `responses.compact`、上下文管理走 Responses `context_management`——框架假设你用 OpenAI 后端时体验最完整。
8. **极简原语 + 重量内脏的演化路径**：公共 API 仍是 Agent/Runner 少数概念，但 `run.py`(2635)+`run_internal/run_loop.py`(2683)+`run_state.py`(5271)+`sandbox/` 表明执行、恢复、沙箱横切能力大量内联在循环内部件里——从"几百行 POC"长成自带审批/恢复/沙箱的单体运行时。

## 7. 跨语言对齐

无官方对齐版（本仓仅 Python；JavaScript 版 openai-agents-js 为独立仓库，docs/human_in_the_loop.md:107 提及与其镜像，未纳入本地源码对比）。
