# claude-agent-sdk-python 框架档案

> 基线：~/develop/opensource/claude-agent-sdk-python @ f101a76 2026-09-11；版本 claude-agent-sdk 0.2.152（pyproject.toml），**内置捆绑 Claude Code CLI 2.1.269**（src/claude_agent_sdk/_cli_version.py#`__cli_version__`；HEAD 提交即 bump 本身，CHANGELOG 0.2.152 条目写 2.1.259 系滞后）。CLI 最低版本 2.0.0（_internal/transport/subprocess_cli.py#`MINIMUM_CLAUDE_CODE_VERSION`），低于仅 warning。

## 1. 定位

Anthropic 官方 Python SDK，本质是 **Claude Code CLI 子进程的宿主适配层**：pip 安装的 wheel 内捆绑 CLI 二进制（构建期由 scripts/download_cli.py 下载进 src/claude_agent_sdk/_bundled/，transport 优先使用），SDK 用 stdio 上的 stream-json NDJSON 双工协议驱动它。agent 循环、内置工具、权限执行、压缩、skills 发现等运行时能力全部在 CLI（闭源二进制，只能以【文档】级证据引用其行为）；Python 层（src 约 7.7k 行）提供 Options 配置面、控制协议路由、消息解析、会话/持久化工具与进程内 MCP 桥。目标用户：想把 Claude Code 全量能力（工具、权限、hooks、skills、子代理）嵌入自己程序的开发者——CI 自动化、聊天后端、自定义 agent 宿主。不是通用 agent 框架：无模型无关抽象、无编排原语。

## 2. 仓库结构与核心包

- 构建：hatchling 单包 `src/claude_agent_sdk`（pyproject.toml；wheel 只含 src/claude_agent_sdk，sdist 另带 tests/scripts/examples）。
- 依赖极简：anyio + sniffio + mcp(1.x/2.x) + jsonschema；可选 extra：`otel`（opentelemetry-api）、`examples`（S3/Redis/PG 参考适配器的后端客户端）。无重框架依赖。
- 目录：`src/claude_agent_sdk/`（types.py 2466 行、client.py、query.py、__init__.py 含 @tool/create_sdk_mcp_server）；`_internal/`（transport/subprocess_cli.py 1189 行、query.py 控制协议 987 行、sessions.py 2024 行、session_mutations/resume/store/summary、sdk_mcp_bridge、transcript_mirror_batcher、message_parser）；`testing/`（session_store_conformance，不依赖 pytest）；`tests/`（单元）、`e2e-tests/`（真实 API）、`examples/`（16 个示例 + plugins/session_stores 参考实现）。
- 仓库自身 dogfood `.claude/`（agents/commands/skills/settings.json），CI 用 Claude 做 issue 分诊与 code review（.github/workflows/claude-*.yml）。
- wheel 构建矩阵五平台（ubuntu x64/arm64、macos arm64/x64、windows），各平台下载对应 CLI 二进制（.github/workflows/build-and-publish.yml matrix）。

## 3. 核心抽象清单

| 符号 | 路径 | 一句话说明 |
|---|---|---|
| `query()` | src/claude_agent_sdk/query.py#query | 一次性/单向流式入口，内部恒走 streaming 模式 |
| `ClaudeSDKClient` | src/claude_agent_sdk/client.py#ClaudeSDKClient | 双向有状态客户端：interrupt/set_permission_mode/set_model/rewind_files/MCP 控制/stop_task/get_context_usage |
| `ClaudeAgentOptions` | src/claude_agent_sdk/types.py#ClaudeAgentOptions | 40+ 字段全量配置（见 §5 各维度） |
| `Transport` | _internal/transport/__init__.py#Transport | 抽象传输 ABC（connect/write/read_messages/end_input/close），docstring 明示可自定义做远程连接 |
| `SubprocessCLITransport` | _internal/transport/subprocess_cli.py#SubprocessCLITransport | 唯一内置传输：anyio 子进程 + NDJSON 行帧 + CLI 发现/版本检查/安全校验 |
| `Query` | _internal/query.py#Query | 控制协议路由：initialize 握手、can_use_tool/hook_callback/mcp_message 反向调用、任务生命周期记账 |
| `InternalClient` | _internal/client.py#InternalClient | query() 的编排实现（resume 物化 → transport → Query → 消息流） |
| `parse_message` | _internal/message_parser.py#parse_message | CLI JSON 帧 → 类型化 Message（未知类型跳过保前向兼容） |
| `@tool` / `create_sdk_mcp_server` | src/claude_agent_sdk/__init__.py | 进程内 MCP server：TypedDict/JSON Schema 校验 + 错误转 isError 结果 |
| `SdkMcpBridge` | _internal/sdk_mcp_bridge.py#SdkMcpBridge | 把 CLI 的 mcp_message 控制请求桥到 mcp 内存 transport 上的真 `mcp.server.Server` |
| `AgentDefinition` | src/claude_agent_sdk/types.py#AgentDefinition | 声明式子代理（12 字段：prompt/tools/model/skills/memory/mcpServers/maxTurns/background/effort/permissionMode…） |
| `CanUseTool` / `PermissionResult*` | src/claude_agent_sdk/types.py | HITL 审批回调签名与结果（Allow 可改输入+改权限规则） |
| `HookMatcher` / `HookInput` | src/claude_agent_sdk/types.py | 事件匹配器 + 10 种事件强类型输入联合 |
| `SessionStore` | src/claude_agent_sdk/types.py#SessionStore | 外部存储镜像协议（append/load 必选，list/delete/list_subkeys/summaries 可选，鸭子类型探测） |
| `TranscriptMirrorBatcher` | _internal/transcript_mirror_batcher.py#TranscriptMirrorBatcher | 镜像帧批处理（500 条/1MiB 或每 turn 刷写） |
| `list_sessions` 等 | _internal/sessions.py#list_sessions / get_session_info / get_session_messages / list_subagents | 纯 Python 读 CLI 磁盘转录（stat+head/tail lite 读） |
| `fork_session` 等 | _internal/session_mutations.py#fork_session / rename_session / tag_session / delete_session | 离线会话操作（fork 重写 UUID 链，0o600 建文件） |
| `fold_session_summary` | _internal/session_summary.py#fold_session_summary | 增量会话摘要折叠（store 在 append 内调用） |
| `materialize_resume_session` | _internal/session_resume.py#materialize_resume_session | 从 store 物化会话到临时 CLAUDE_CONFIG_DIR（含凭据复制/重写）以供 CLI resume |
| `run_session_store_conformance` | testing/session_store_conformance.py | 13 项行为契约 conformance 套件（随包发行） |
| 消息类型 | src/claude_agent_sdk/types.py#Message | User/Assistant/System/Result/StreamEvent/RateLimitEvent/ConversationReset + task 生命周期子类 |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | Claude 系直连开箱即用（经捆绑 CLI）；model/fallback_model/运行时 set_model/betas；cost/usage/rate-limit 全结构化回报；非直连 provider（bedrock/vertex 等）配置路径未见 ⚠️ | types.py#ClaudeAgentOptions（model/fallback_model/betas）、_internal/query.py#Query.set_model、types.py#ModelUsage、types.py#RateLimitEvent |
| 2 | 上下文工程 | ✅ | system_prompt 三形态 + preset append + exclude_dynamic_sections 跨用户 prompt 缓存；autocompact/压缩执行在 CLI【文档】，SDK 暴露 PreCompact hook 与 get_context_usage() 全量口径 | types.py#SystemPromptPreset、client.py#ClaudeSDKClient.get_context_usage、types.py#ContextUsageResponse |
| 3 | 记忆 | 🟡 | 无 SDK 记忆抽象；CLAUDE.md/auto-memory/子代理 memory（user/project/local）由 CLI 与 .claude 目录约定承载，SDK 仅经 setting_sources 开关 | types.py#ClaudeAgentOptions.setting_sources（"Must include project to load CLAUDE.md"）、types.py#AgentDefinition.memory、types.py#ContextUsageResponse.memoryFiles |
| 4 | RAG | ❌ | 无 retriever/vector store/rerank/citation 任何抽象；仅有 CLI 内置服务端工具 web_search/web_fetch | types.py#ServerToolName（全 src 无 retriever/embedding 符号） |
| 5 | 工具系统 | ✅ | CLI 内置工具集（Bash/Read/Edit/…）+ 细粒度 allow/deny 规则（`Bash(ls:*)`）+ MCP 五形态接入（stdio/sse/http/**进程内 sdk**/claudeai-proxy）+ Bash 沙箱配置 + maxResultSizeChars | src/claude_agent_sdk/__init__.py#create_sdk_mcp_server、_internal/sdk_mcp_bridge.py#SdkMcpBridge、types.py#SandboxSettings、types.py#McpServerConfig |
| 6 | Skill 机制 | ✅ | options.skills 单一开关（"all"/名单）：SDK 自动注入 `Skill(name)` 规则并默认 setting_sources=user+project；SKILL.md 发现与渐进披露在 CLI【文档】 | _internal/transport/subprocess_cli.py#_apply_skills_defaults、_internal/transport/subprocess_cli.py#_validate_skill_name、types.py#ClaudeAgentOptions.skills |
| 7 | 规划推理 | ✅ | thinking（adaptive/enabled/disabled + display 摘要化）/effort 五档/output_format 结构化输出（--json-schema）/max_turns/max_budget_usd/task_budget（API 侧 token 预算 beta）；agent 循环本体在 CLI【文档】 | types.py#ThinkingConfig、types.py#TaskBudget、_internal/transport/subprocess_cli.py#_build_command（--json-schema/--task-budget/--effort） |
| 8 | 编排 | ❌ | 无 graph/workflow/branch/loop/parallel/subgraph 抽象，SDK 是顺序消息流；后台任务生命周期消息（task_started/progress/updated）与 CLI Task 工具不构成编排原语 | _internal/query.py#Query._track_task_lifecycle（全 src 无 workflow/graph 符号） |
| 9 | 多 Agent | ✅ | 声明式 `agents: dict[str, AgentDefinition]` 经 initialize 下发，CLI Agent 工具调度（含并行）；子代理转录可枚举回读（parent_tool_use_id/parent_agent_id 关联）；跨会话 peer/coordinator 消息【文档】 | types.py#AgentDefinition、_internal/query.py#Query.initialize（request["agents"]）、_internal/sessions.py#list_subagents、types.py#MessageOrigin |
| 10 | 持久化 | ✅ | 本地 JSONL 会话（resume/continue/fork/任意消息点截断恢复 resume_session_at+resume_drops_turn）+ SessionStore 外部镜像协议 + S3/Redis/PG 参考适配器 + 13 项 conformance 套件 + 增量摘要 | types.py#SessionStore、_internal/session_mutations.py#fork_session、_internal/session_resume.py#materialize_resume_session、examples/session_stores/、testing/session_store_conformance.py |
| 11 | HITL | ✅ | can_use_tool 审批回调（可改输入 updatedInput、运行时改权限规则/模式/目录 updatedPermissions）+ 6 种 permission_mode + PreToolUse hook allow/deny/ask/**defer** + DeferredToolUse 挂起后恢复 + 回调遮蔽告警 | types.py#_configure_can_use_tool、_internal/query.py#Query._handle_control_request、types.py#DeferredToolUse、types.py#CanUseToolShadowedWarning |
| 12 | 观测评估 | 🟡 | OTEL 仅做 traceparent 透传（可选 extra，span 生成在 CLI【文档】）+ stderr 回调 + usage/cost/rate-limit/terminal_reason 结构化进消息流；无 tracing 抽象无 eval | _internal/transport/subprocess_cli.py#SubprocessCLITransport.connect（propagate.inject）、pyproject.toml [otel]、types.py#ResultMessage |
| 13 | 安全治理 | ✅ | 三层权限（规则+模式+审批回调/hooks）+ Bash 沙箱（网络域名/unix socket/文件违规忽略，CLI 执行【文档】）+ Windows BatBadBut 拒绝与 flag 注入防护（--flag=equals 绑定）+ skill 名/子路径校验 | types.py#PermissionUpdate、subprocess_cli.py#_reject_windows_batch_cli、subprocess_cli.py#_reject_windows_cmd_metacharacters、types.py#SandboxNetworkConfig |
| 14 | 部署运行时 | ❌ | 无 server/队列/池化/cron；每次 query 一个 CLI 子进程（stdout 1MiB 缓冲上限、atexit 收割孤儿进程），进程生命周期管理精细但无并发治理，部署留给宿主 | subprocess_cli.py#connect、subprocess_cli.py#_ACTIVE_CHILDREN、subprocess_cli.py#_DEFAULT_MAX_BUFFER_SIZE |
| 15 | 管理平面 | ❌ | 无 console/dashboard/租户/计费；仅 SessionKey.project_key docstring 提示多租户部署可用 tenant id 自行命名空间 | types.py#SessionKey.project_key |

⚠️ 共 1 处（维度 1：非直连 provider 的启用方式只有 ModelUsage.provider 的文档枚举值，SDK 无对应配置字段，CLI 侧环境变量配置未在本仓库证实）。

## 5. 维度证据明细

**边界总述（适用于所有维度）**：SDK↔CLI 唯一通道是 stdio 上的 NDJSON（`claude --output-format stream-json --verbose --input-format stream-json`，subprocess_cli.py#_build_command；stdin 喂 JSON 行、stdout 逐行解析 `_LineFramer`+`_parse_stdout_line`）。同一通道复用双向控制 RPC：SDK→CLI 的 control_request（interrupt/set_model/mcp_status 等，_internal/query.py#`_send_control_request`）与 CLI→SDK 的 control_request（can_use_tool/hook_callback/mcp_message 反调，_internal/query.py#`_handle_control_request`）。**无 websocket/HTTP transport**：仓库内唯一实现是 SubprocessCLITransport，Transport ABC docstring 仅预留"remote Claude Code connections"的自定义可能。凡 CLI 二进制内实现（agent 循环、权限执行、压缩、工具执行、tracing span）证据等级均为【文档】（SDK docstring/类型注释宣称）。

### 1 模型接入【核心=配置面与回报面；执行在 CLI【文档】】
- `ClaudeAgentOptions.model/fallback_model/betas`（types.py:2035-2052）映射 `--model/--fallback-model/--betas`（subprocess_cli.py:612-619）；运行时切换 `Query.set_model`（query.py:697）。
- 成本与用量由 CLI 计算并回报【文档】：`ResultMessage.total_cost_usd/usage/model_usage`（message_parser.py:319-323 透传 CLI 的 `total_cost_usd/modelUsage` 字段）；`ModelUsage` 含 per-model tokens/缓存/costUSD/contextWindow/provider（types.py:1293）。
- `RateLimitEvent/RateLimitInfo`：CLI 在限流状态迁移时发 `rate_limit_event` 帧（types.py:1376-1414；tests/test_rate_limit_event_repro.py）。
- ⚠️ bedrock/vertex/foundry 等仅出现在 `ModelUsage.provider` 的注释枚举（types.py:1312-1315），SDK 无 provider 配置字段，如何启用未在本仓库证实。
- 证据等级：SDK 侧【核心】；推理请求执行/重试/provider 路由【文档】。

### 2 上下文工程
- system_prompt 三形态：str / `{"type":"preset","preset":"claude_code"(,append)}` / `{"type":"file","path"}`（types.py#SystemPromptPreset、#SystemPromptFile）；None 时显式传 `--system-prompt ""` 清空（subprocess_cli.py:568-571）。
- `exclude_dynamic_sections`：剥掉 per-user 动态段（cwd/auto-memory/git status）重注入首条 user message，换取跨用户 prompt cache 命中（types.py:46-57 docstring）——SDK 从 preset 里抽取后经 initialize 下发（client.py:171-178）。
- autocompact 在 CLI【文档】（ContextUsageResponse.isAutoCompactEnabled/autoCompactThreshold 字段透传）；SDK 暴露 PreCompact hook（trigger manual/auto + custom_instructions，types.py:366-371）。
- `get_context_usage()`：与 CLI `/context` 命令同口径的全量分解（分类 tokens、memoryFiles、mcpTools、agents、skills、messageBreakdown，types.py:764-836；控制请求 subtype=get_context_usage，query.py:680）。
- 证据等级：类型与请求【核心】；压缩行为【文档】。

### 3 记忆
- 无任何 memory 抽象/存储接口（全 src 无对应符号）。CLI 的文件式记忆（CLAUDE.md、auto-memory）经 `setting_sources` 开关：`"Must include 'project' to load CLAUDE.md files"`（types.py:2218-2228 docstring）【文档】。
- 子代理可声明 `memory: user|project|local`（AgentDefinition.memory，types.py:98）【文档，字段透传 CLI】。
- `ContextUsageResponse.memoryFiles` 回报已加载 CLAUDE.md 及 token 数（types.py:801-802）。
- 评级 🟡：能力由 CLI 平台约定承载，SDK 主包无实现。
- 证据等级：字段/开关【核心】；加载与记忆机制【文档】。

### 4 RAG
- ❌。无 retriever/vector store/rerank/citation/ingestion。最接近的是 CLI 服务端工具 `web_search/web_fetch` 与 `code_execution`（ServerToolName 枚举，types.py:967-976）【核心=枚举；工具本身 CLI/API 侧】。

### 5 工具系统
- 工具面三层：`tools`（基础工具集，可 `[]` 全关）、`allowed_tools`（免审批规则，支持 `Bash(ls:*)` 细粒度）、`disallowed_tools`（types.py:1944-2033；subprocess_cli.py:582-607 映射 CLI flags）。工具执行本体（Bash/Read/Edit/Skill/Agent…）在 CLI【文档】。
- MCP 五形态配置联合（types.py#McpServerConfig，605-651）：stdio/sse/http + `claudeai-proxy`（输出型）+ **`sdk` 进程内 server**。
- 进程内 MCP 是 SDK 层最重的自研能力【核心】：`@tool` 装饰器（TypedDict→JSON Schema 自动推导，__init__.py:338-430）+ `create_sdk_mcp_server()`（jsonschema 参数校验、异常转 isError 结果，__init__.py:491-619）+ `SdkMcpBridge` 用 mcp 官方内存 transport 把 CLI 的 mcp_message JSON-RPC 桥到真 `mcp.server.Server`（sdk_mcp_bridge.py:1-20 模块 docstring）；兼容 mcp 1.x/2.x（_mcp_compat.py）。
- `strict_mcp_config` 屏蔽 .mcp.json/用户设置/插件提供的 server（types.py:1984-1989）。
- 沙箱：SandboxSettings（enabled/excludedCommands/network.allowedDomains/allowUnixSockets/ignoreViolations 等，types.py:848-930）由 SDK 合并进 --settings JSON（subprocess_cli.py#_build_settings_value）；实际沙箱执行在 CLI（macOS/Linux）【文档】。
- `ToolAnnotations.maxResultSizeChars`：工具结果内联阈值，经 `_meta` 传给 CLI（__init__.py#_build_meta）。
- 证据等级：配置/桥接/校验【核心】；工具执行与沙箱机制【文档】。

### 6 Skill 机制
- `options.skills: list[str] | "all"` 是唯一开关：SDK 注入 `Skill`（all）或 `Skill(name)`（名单）到 allowedTools，并在 setting_sources 未设时默认 `["user","project"]` 以便 CLI 发现已安装 skills（subprocess_cli.py#_apply_skills_defaults，519-560）【核心】。
- 名单严格校验（括号/逗号/控制字符/BOM/通配符/前导斜杠/反斜杠均拒绝，subprocess_cli.py#_validate_skill_name）——因为名字要进 CLI 的 --allowedTools 规则文法【核心，同时是 CLI 规则文法的【文档】旁证】。
- skills 是**上下文过滤器而非沙箱**：未列出的 skill 对模型隐藏且被 Skill 工具拒绝，但文件仍可被 Read/Bash 读到（types.py:2230-2250 docstring）【文档】。
- SKILL.md 发现、渐进披露、`plugin:skill` 命名在 CLI【文档】；SDK 侧支持 `plugins=[{type:"local",path}]` 加载本地插件（含 commands/agents/skills/hooks，subprocess_cli.py:722-728，examples/plugins/demo-plugin 为【示例】）。
- 证据等级：注入与校验【核心】；skill 运行语义【文档】。

### 7 规划推理
- thinking 三态：adaptive（Opus 4.6+ 模型自决）/enabled（budget_tokens）/disabled，另有 display: summarized|omitted（Opus 4.7+ 默认 omitted）（types.py:1787-1802）→ `--thinking/--max-thinking-tokens/--thinking-display`（subprocess_cli.py:747-765）【核心映射；思考执行 CLI→API】。
- effort 五档 low/medium/high/xhigh/max（types.py#EffortLevel）→ `--effort`；旧 max_thinking_tokens 已标 deprecated。
- 结构化输出：`output_format={"type":"json_schema","schema":…}` → `--json-schema`，结果回 `ResultMessage.structured_output`（types.py:2309-2315；e2e-tests/test_structured_output.py【示例】）。
- 预算双轨：`max_budget_usd`（USD 硬预算，超限返回 error_max_budget_usd，examples/max_budget_usd.py【示例】）与 `task_budget`（API 侧 token 预算，随 task-budgets-2026-03-13 beta 头下发，types.py:67-76）。`max_turns` 限制轮数。
- plan 模式（permission_mode="plan"）只规划不执行（types.py:1991-1999 docstring）【文档】。
- 证据等级：全部控制点【核心】（字段+flag 映射+结果字段）；循环与执行【文档】。

### 8 编排
- ❌。SDK 是线性消息管道；无 graph/workflow/state machine/并行/子图/可视化。后台任务仅是消息语义：task_started/progress/notification/updated + `stop_task` 控制（types.py:1173-1260；query.py#_track_task_lifecycle 用 DEFERRING_TASK_TYPES={local_agent,local_workflow} 记账以决定 stdin 保活，query.py:52）——这是连接管理而非编排原语【核心】。CLI 的 Task/Agent 工具内并行调度【文档】。

### 9 多 Agent
- `options.agents: dict[str, AgentDefinition]` 声明式子代理（description/prompt/tools/disallowedTools/model/skills/memory/mcpServers/initialPrompt/maxTurns/background/effort/permissionMode，types.py:86-105），**不走 CLI flag，恒经 initialize 控制请求下发**（subprocess_cli.py:716-717 注释；query.py:262-267）【核心】。
- 调度执行在 CLI 的 Agent(Task) 工具【文档】；SDK 回报面：子代理消息带 `parent_tool_use_id`（forward_subagent_text=True 时转发其 text/thinking，types.py:2158-2168）；task 消息带 agent 归属（_SubagentContextMixin.agent_id/agent_type，types.py:293-309）。
- 子代理转录可离线枚举回读：`list_subagents/get_subagent_messages`（含 agent 元数据 sidecar 恢复 parent_agent_id，sessions.py:1199-1511）【核心】；亦有 store 变体【核心】。
- 跨会话协作仅消息来源标注：MessageOrigin kind=peer/coordinator/task-notification（types.py:1028-1100，peer 的 fromSession/verifiedPeerPid 字段）——能力在 CLI【文档】，SDK 只透传。
- 无 supervisor/handoff/swarm/registry 抽象；多 agent 拓扑由 prompt 声明 + CLI 内部决定。
- 证据等级：声明与回读【核心】；调度与跨会话【文档】。

### 10 持久化（本框架最强维度之一）
- 真相源是 CLI 本地 JSONL：`~/.claude/projects/<sanitized-cwd>/<session-uuid>.jsonl`，子代理在 `subagents/agent-{id}` 子路径（sessions.py 模块 docstring、types.py#SessionKey）；SDK 用与 CLI 一致的路径 sanitize（djb2 风格 base36 hash，sessions.py#_simple_hash 注释 "matching the CLI's directory naming"）直接读写【核心】。
- resume 面：`resume`(session id)/`continue_conversation`(最近会话)/`session_id`(指定 UUID)/`fork_session`(resume 到新 id)/`resume_session_at`(截断到某消息)+`resume_drops_turn`(校验被丢弃轮次归属，拒绝时抛含 "Resume rejected by --resume-drops-turn:" 的 ProcessError)（types.py:2001-2210；全部映射 CLI flags，subprocess_cli.py:629-711）【核心映射；resume 执行 CLI【文档】】。
- 离线操作纯 Python 实现【核心】：`fork_session` 重写全链 UUID+parentUuid、O_EXCL 0o600 建文件（session_mutations.py:240-345）；rename/tag/delete 同文件级操作。
- SessionStore 协议【核心】：CLI 加 `--session-mirror` 后每条转录行镜像给 SDK（transcript_mirror 帧被读循环剥离不进消息流，query.py:348-355）；`TranscriptMirrorBatcher` batched(默认，500 条/1MiB/每 turn)/eager 两种刷写；append 失败重试 3 次后降级为 MirrorErrorMessage 系统消息**不中断会话**（types.py#MirrorErrorMessage、query.py#report_mirror_error）。
- resume-from-store：`materialize_resume_session` 把 store 内容物化到临时 CLAUDE_CONFIG_DIR（含 .credentials.json 复制/keychain 读取与重写、settings 剥离），子进程从临时目录 resume（session_resume.py:130-221、326-494）【核心】。
- 摘要侧车：`fold_session_summary` 纯函数折叠 first_prompt/标题等，store 在 append 内维护（session_summary.py:112）【核心】。
- 参考适配器 S3/Redis/Postgres 在 examples/session_stores/（README 明示"不打包、非生产维护"）【示例】；`testing/session_store_conformance.py` 13 项契约套件随包发行【核心】。
- InMemorySessionStore 内置（session_store.py:35）【核心】。

### 11 HITL
- `can_use_tool` 回调：CLI 权限规则评估为 "ask" 时经 control_request(can_use_tool) 反调 SDK（query.py:478-530）；返回 `PermissionResultAllow(updated_input/updated_permissions)` 或 `PermissionResultDeny(message/interrupt)`——**可在审批时改写工具输入并动态增删权限规则/切模式/加目录**（types.py:116-197）【核心】。互斥校验与 stdio 路由在 `_configure_can_use_tool`（设 permission_prompt_tool_name="stdio"，types.py:1896-1919）【核心】。
- 遮蔽告警：allowed_tools 整工具放行（"Read"/"Read()"）或 bypassPermissions 会让回调不被调用，连一条 UserWarning（含 skills="all" 注入裸 Skill 的情形）——`_warn_if_can_use_tool_shadowed`（types.py:1805-1893）【核心】。
- permission_mode 六值：default/acceptEdits/plan/bypassPermissions/dontAsk/auto（"auto"=模型分类器审批，client.py:284-294 docstring）【核心枚举；语义 CLI【文档】】；运行时 `set_permission_mode`。
- Hooks（10 事件，见维度 13 之外的治理面）：PreToolUse 可回 permissionDecision allow/deny/**ask/defer**；defer 使运行停止并把待决调用放进 `ResultMessage.deferred_tool_use`，宿主决定是否 resume（types.py:1279-1291）——把「挂起等人工」做成一等协议消息【核心】。
- 多 matcher 同事件**并发分发**（docstring 明示，types.py:2133-2139）【文档】。
- `permission_prompt_tool_name` 可改路由到自定义 MCP 工具（types.py:2054-2059）。
- 证据等级：协议与类型【核心】；权限评估次序【文档】。

### 12 观测评估
- OTEL：可选 extra；transport 在 connect 时 `propagate.inject` 把活跃 traceparent 注入子进程 env（并清理陈旧 TRACEPARENT/TRACESTATE），best-effort 永不失败（subprocess_cli.py:817-841）【核心】；span 生成在 CLI【文档】。
- `stderr` 回调逐行收 CLI 诊断（subprocess_cli.py#_handle_stderr）【核心】。
- 可观测即协议：usage/cost/model_usage/rate_limit/terminal_reason("completed"/"max_turns"/"aborted_streaming")/api_error_status(HTTP 码) 结构化进消息（types.py#ResultMessage）【核心】；`include_hook_events` 可把 hook 生命周期也变为流消息（HookEventMessage，types.py:1443-1474）。
- 无 tracing 抽象、无 callback 体系（除 hooks）、无 eval/dataset。评级 🟡。
- 证据等级：注入与类型【核心】；span【文档】。

### 13 安全治理
- 权限三层：settings 规则（allow/deny/ask，经 --settings 注入或 setting_sources 文件层）+ permission_mode + 运行时审批（can_use_tool/hooks）；`PermissionUpdate` 支持六种变更（addRules/replaceRules/removeRules/setMode/addDirectories/removeDirectories）与四个落盘目的地（userSettings/projectSettings/localSettings/session）（types.py:108-197）【核心协议；评估执行 CLI【文档】】。
- 沙箱：Bash 命令文件/网络隔离（macOS/Linux），域名白名单、unix socket、违规忽略清单（types.py#SandboxSettings）；文件系统读写限制用 Read/Edit 权限规则表达而非沙箱项（docstring 明示分工，types.py:893-897）【核心配置；执行【文档】】。
- Windows 注入防御【核心】：拒绝 .bat/.cmd 作 CLI（BatBadBut/CVE-2024-27980 同类修复，subprocess_cli.py#_reject_windows_batch_cli，全路径组件+NTFS 流名都查）；resume/session_id 等 externally-sourced 值拒绝 cmd 元字符；可选值 flag 一律 `--flag=value` 防 flag 注入（subprocess_cli.py:632-639、696-711、731-745）。
- 其他：skill 名文法校验（见维度 6）、resume 物化的 `_is_safe_subpath` 防路径逃逸（session_resume.py:591）、fork 文件 0o600、`user=` 以非 root 运行子进程（subprocess_cli.py:860）、进程退出 atexit 收割（subprocess_cli.py:50-60）。
- 无 guardrail/PII/内容安全抽象。
- 证据等级：SDK 侧防御与协议【核心】；沙箱与权限执行【文档】。

### 14 部署运行时
- ❌（作为框架能力）。进程模型：每次 query()/connect() 一个 CLI 子进程（无池化/复用；另有一次性 `cli -v` 版本探测进程，2s 超时）；stdout 单行缓冲上限默认 1MiB（max_buffer_size 可调）；关闭走 shielded 三段升级（等 5s → SIGTERM 等 5s → SIGKILL），atexit 兜底防孤儿（subprocess_cli.py#close、#_kill_active_children）【核心】。
- 无 FastAPI/server/cron/queue/temporal/docker 服务化设施（Dockerfile.test 仅测试用）。并发治理（多会话扇出、限流）完全留给宿主。
- 证据等级：进程管理【核心】。

### 15 管理平面
- ❌。无 console/dashboard/租户/计费/配置中心。多租户最近的一点是 SessionKey.project_key 的 docstring 建议（"Multi-tenant deployments should set this to a tenant ID"，types.py:1502-1505）与 `_copy_auth_files` 的凭据隔离【核心 docstring】。

## 6. 设计决策要点

1. **运行时整体外置、二进制随包发行**：Python 层只做协议适配（~7.7k 行），agent 能力升级以"每周 bump 捆绑 CLI 版本"节奏进行（CHANGELOG 0.2.143→0.2.152 几乎全是 CLI bump；HEAD 提交本身即 bump 2.1.269）。好处：宿主零配置获得全部 Claude Code 能力；代价：黑盒边界，所有 CLI 行为只能【文档】级引用，SDK 与 CLI 版本耦合紧密（低于 2.0.0 仅 warning 不阻断）。
2. **单通道双工协议**：消息流与控制 RPC 复用同一 stdin/stdout NDJSON（control_request/control_response 双向、request_id 关联、control_cancel_request 取消）。由此派生最精巧的补丁逻辑：有 hooks/SDK-MCP/can_use_tool 时 stdin 必须保活到"无在飞任务的 result 帧"（#1088），用 DEFERRING_TASK_TYPES 记账在 query.py:762-817 有长篇注释承认这是推断而非协议保证。
3. **Hook 反转**：Claude Code 的 shell hook 体系（settings.json 里的外部命令）被 SDK 内化为进程内 Python 回调——initialize 注册 callback_id，CLI 经 control_request(hook_callback) 反调，async_/continue_ 关键字转译（query.py#_convert_hook_output_for_cli）。企业策略/审计零外部进程接入。
4. **can_use_tool = stdio 权限工具 + 遮蔽检测**：回调被改写为 `--permission-prompt-tool stdio`，并用 `_whole_tool_allowed` 复刻 CLI 规则解析器来预判哪些工具会在回调前被自动放行，发出 CanUseToolShadowedWarning——用 advisory 而非 raise 承认"故意只管部分工具"的合法用法（types.py:1814-1893）。
5. **持久化双轨：本地 JSONL 为真相源 + SessionStore 镜像**：CLI 照常写盘（可 CLAUDE_CONFIG_DIR=/tmp 做临时副本），适配器拿二级副本；uuid 幂等、at-most-once 投递、失败降级为 MirrorErrorMessage 不伤会话；resume-from-store 用临时配置目录物化（连凭据重写都处理了）。配套发行 conformance 套件把"协议泛化性"做成可执行断言——少见的协议质量工程。
6. **会话工具绕过 CLI 直读磁盘格式**：list/fork/rename/tag 是纯 Python 重实现 CLI 的转录格式（路径 sanitize 复刻 JS hash、fork 重写 UUID 链、lite head/tail 读避免全量解析）——赢得离线能力，但与 CLI 格式隐式耦合（格式演进需跟版）。
7. **防御性工程密度异常高**：BatBadBut 全组件路径检查、`--flag=value` 强制绑定、skill 名规则文法校验、1MiB 帧上限、孤儿进程收割、shielded close、`async for` 不关迭代器的 PEP 533 手动 aclose（client.py:54-71）—— subprocess 边界上的每个坑都有针对性注释与测试。
8. **进程内 MCP 桥**：`type:"sdk"` server 不spawn外部进程，用 mcp 官方内存 transport 把控制通道 JSON-RPC 桥到用户提供的 `mcp.server.Server`，工具校验/错误语义由 SDK 统一保证（跨 mcp 1.x/2.x）。

## 7. 跨语言对齐

不适用（非 Java 镜像仓库）。注：姊妹实现 TypeScript SDK 是多处行为的对照基准（docstring 反复出现 "matching the TypeScript SDK"，如 hasBidirectionalNeeds、lastErrorResultText、CLAUDE_SDK_CAN_USE_TOOL_SHADOWED 告警对应），但未纳入本研究本地仓库清单。
