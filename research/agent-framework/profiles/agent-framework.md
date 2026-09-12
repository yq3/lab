# Microsoft Agent Framework 框架档案

> 基线：~/develop/opensource/agent-framework @ 3c6707077 2026-09-11；版本 Python `agent-framework` 1.18.0（`python/pyproject.toml`）、.NET 1.21.0（`dotnet/nuget/nuget-package.props:4` VersionPrefix）。Go 实现已拆至独立仓 microsoft/agent-framework-go（`go/README.md`，本仓仅留指针）。

## 1. 定位（3-5 句：解决什么问题、库还是平台、目标用户）

微软官方的「生产级 AI Agent 与多 Agent Workflow」框架，2025 年由 AutoGen（多 Agent 编排血统）与 Semantic Kernel（企业 .NET 血统）合并而来，仓内 README 直挂两份迁移指南（`README.md:104-105`）。本质是**库 + 平台扩展点**而非托管平台：核心是 Agent 抽象与 Pregel 式 Workflow 引擎，外围以 ~40 个（Python）/ 38 个（.NET）官方包接通 Azure Foundry、Purview、A2A、MCP、各类模型 provider。目标是企业开发者（尤其 .NET/Azure 栈）：安全审批、内容标签、OTel、声明式 YAML 均为一等公民。双语言同构（Python + C#），靠共享 ADR（`docs/decisions/`，0001–0040）与声明式 spec 约束对齐。

## 2. 仓库结构与核心包（构建配置证据）

- 顶层：`python/` + `dotnet/` 双主干 + `docs/`（含 47 个 ADR 文件）+ `declarative-agents/`（YAML 样例）+ `go/`（外链）。
- Python 单仓多包（uv workspace），`python/PACKAGE_STATUS.md` 给出成熟度分层：
  - **released**：core、openai、foundry、github_copilot、orchestrations、declarative、ag-ui（+ 聚合包 `agent-framework`）；
  - **beta**：a2a、anthropic、bedrock、gemini、mistral、ollama、claude、copilotstudio、devui、purview、redis、mem0、hyperlight、monty(CodeAct)、lab 等；
  - **alpha**：hosting / hosting-a2a / hosting-mcp / hosting-responses / hosting-telegram、postgres、qdrant、azure-cosmos-memory。
- Python 核心包 `python/packages/core/agent_framework/` 关键模块：`_agents.py`（1953 行）、`_tools.py`（4223 行）、`_sessions.py`（2454 行）、`_clients.py`、`_middleware.py`、`observability.py`、`security.py`、`_skills.py`、`_compaction.py`、`_vectors.py`、`_evaluation.py`、`_mcp.py`、`_harness/`（10 文件）、`_workflows/`（24 文件）。
- .NET：`dotnet/src/` 38 个 `Microsoft.Agents.AI.*` 项目（Abstractions / AI / Workflows / Mcp / Harness / DevUI / Purview / Foundry(.Hosting) / A2A / AGUI / Hyperlight / LocalCodeAct / CosmosNoSql / Valkey / Hosting(.AspNetCore/.A2A/.OpenAI/.AzureStorage) / Aspire DevUI 等）。

## 3. 核心抽象清单（符号 | 路径 | 一句话）

| 符号 | 路径（python/packages/core/agent_framework/ 下） | 一句话 |
|---|---|---|
| `BaseAgent` :376 | `_agents.py` | Agent 协议基类（run/run_stream，SerializationMixin） |
| `RawAgent` :727 | `_agents.py` | 裸 Agent：client + instructions + tools，无中间件无遥测 |
| `Agent` :1794 | `_agents.py` | 推荐主类 = `AgentMiddlewareLayer`+`AgentTelemetryLayer`+`RawAgent` 洋葱叠层 |
| `BaseChatClient` :221 | `_clients.py` | 模型接入统一协议（get_response/get_streaming_response） |
| `AgentMiddleware` :641 / `FunctionMiddleware` :713 / `ChatMiddleware` :791 | `_middleware.py` | 三类中间件（Agent 级 / 工具调用级 / chat 请求级）+ 各自 Pipeline 与 Layer |
| `FunctionInvocationLayer` :3446 + `FunctionInvocationConfiguration` :1427 | `_tools.py` | 工具调用循环层；max_iterations / max_function_calls / max_duration_seconds 预算 |
| `Workflow` :228 / `WorkflowBuilder` :53（add_edge :230 / fan_out :282 / fan_in :511） | `_workflows/_workflow.py`、`_workflow_builder.py` | 图编排 + 统一 run(message / responses / checkpoint_id) 入口 :746 |
| `Runner`（Pregel superstep，:46/:125/:168） | `_workflows/_runner.py` | 超步引擎，每步边界提交状态并自动落 checkpoint |
| `WorkflowCheckpoint` :31 / `CheckpointStorage` :130 | `_workflows/_checkpoint.py` | checkpoint 含 graph_signature_hash 拓扑校验、previous 链、`_edge_state` fan-in 缓冲、pending_request_info_events |
| `AgentExecutor` :129 / `WorkflowExecutor` :112 / `FunctionExecutor` :36 / `FunctionalWorkflow` :685 | `_workflows/_agent_executor.py` 等 | 图上四种执行器；WorkflowExecutor 即子图嵌套；Functional 为函数式 API（`WorkflowInterrupted` :95） |
| `AgentSession` :1707 / `SessionStore` :1785 / `FileSessionStore` :1862 | `_sessions.py` | 会话状态与存储协议 + ContextProvider/HistoryProvider 注入机制 |
| `Skill` :619 / `SkillsProvider` :1908 / `MCPSkill` | `_skills.py` | Agent Skills 抽象（frontmatter + 惰性资源/脚本），文件/内联/MCP 三源 |
| `create_harness_agent` | `_harness/_agent.py` | 「batteries included」工厂：todo/mode/memory/skills providers + AgentLoopMiddleware + 工具审批 + compaction |
| `AgentLoopMiddleware` :219（默认 10 轮）+ `JudgeVerdict` :106 | `_harness/_loop.py` | 外层反复运行循环 + 可继续性判断（judge） |
| `ToolApprovalRule` :86 / `ToolApprovalState` :158 | `_harness/_tool_approval.py` | 工具审批规则（always/scope/参数匹配）持久化于会话 |
| `MemoryStore` :561 / `MemoryFileStore` :663 / `MemoryContextProvider` :976 | `_harness/_memory.py` | harness 文件式长期记忆（话题索引） |
| `IntegrityLabel` :121 / `ConfidentialityLabel` :138 / `ContentLabel` :157 | `security.py` | 内容完整性/机密性标签（ADR-0024 防提示注入） |
| `ChatTelemetryLayer` :1883 / `AgentTelemetryLayer` :2275 / `configure_otel_providers` :1592 | `observability.py` | OTel 一等公民（含 Embedding 遥测 :2213） |
| `CompactionStrategy` :61 / `group_messages` :200 | `_compaction.py` | 上下文压缩协议（tokenizer + 函数调用/结果配对成组） |
| `ChatOptions.response_format` :3818 | `_types.py` | 结构化输出（ADR-0036） |
| `UsageDetails` + `add_usage_details` :433 | `_types.py` | 跨层 usage 聚合 |

编排独立包 `python/packages/orchestrations/agent_framework_orchestrations/`（released）：`GroupChatOrchestrator` :98 / `AgentBasedGroupChatOrchestrator` :284（`_group_chat.py`）、`HandoffAgentExecutor` :202 + `HandoffBuilder` :569（`_handoff.py`）、Magentic 家族（`_magentic.py`，`MagenticProgressLedger` :308 / `MagenticManagerBase` :469）、`SequentialBuilder` :65（`_sequential.py`）、Concurrent（`_concurrent.py`）、`AgentApprovalExecutor` :169（`_orchestration_request_info.py`，HITL 审批执行器）。

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | BaseChatClient 统一协议，10+ 官方 provider 包（含 Anthropic 四种部署路由）；无内置 router/fallback | python/packages/core/agent_framework/_clients.py#BaseChatClient |
| 2 | 上下文工程 | ✅ | compaction 协议一等公民（分组+tokenizer）；系统提示走 instructions；无通用 prompt template 库 | python/packages/core/agent_framework/_compaction.py#CompactionStrategy |
| 3 | 记忆 | ✅ | core 内 AgentSession/SessionStore + harness 文件式长期记忆；mem0/redis 等生态扩展 | python/packages/core/agent_framework/_sessions.py#SessionStore |
| 4 | RAG | 🟡 | core 有 @vector_store_model 抽象，向量库全在生态包（beta/alpha）；无 rerank/citation | python/packages/core/agent_framework/_vectors.py#vector_store_model |
| 5 | 工具系统 | ✅ | @tool schema 推断 + 审批 + 预算限制；MCP 客户端在 core、MCP 服务端在 hosting-mcp；hyperlight 沙箱 | python/packages/core/agent_framework/_tools.py#tool |
| 6 | Skill 机制 | ✅ | core 内完整 Skill 抽象：frontmatter 渐进披露 + File/Inline/MCP 三源 + {skills} 指令模板（ADR-0037） | python/packages/core/agent_framework/_skills.py#Skill |
| 7 | 规划推理 | 🟡 | 结构化输出/ReAct 循环/预算齐全，但无独立 planner 抽象；规划以 Magentic ledger、Todo、loop-judge 形式存在 | python/packages/orchestrations/agent_framework_orchestrations/_magentic.py#MagenticProgressLedger |
| 8 | 编排 | ✅ | Pregel 超步图引擎：builder/fan-in/out/子图/函数式双 API/_viz 可视化 | python/packages/core/agent_framework/_workflows/_workflow.py#Workflow |
| 9 | 多 Agent | ✅ | orchestrations 包（released）：GroupChat/Magentic( supervisor+ledger )/Handoff/Sequential/Concurrent + A2A | python/packages/orchestrations/agent_framework_orchestrations/_group_chat.py#GroupChatOrchestrator |
| 10 | 持久化 | ✅ | 每超步自动 checkpoint + 图哈希校验恢复 + checkpoint 链；会话存储 File(core)/Cosmos/Redis 生态 | python/packages/core/agent_framework/_workflows/_checkpoint.py#WorkflowCheckpoint |
| 11 | HITL | ✅ | request_info 事件 + IDLE_WITH_PENDING_REQUESTS + responses 续跑，pending 请求入 checkpoint；工具审批三层 | python/packages/core/agent_framework/_workflows/_events.py#IDLE_WITH_PENDING_REQUESTS |
| 12 | 观测评估 | ✅ | OTel 三层遥测 + configure_otel_providers + feature usage 位图上报（ADR-0033）+ core 评估模型 + Foundry evals | python/packages/core/agent_framework/observability.py#AgentTelemetryLayer |
| 13 | 安全治理 | ✅ | 纵深最全：内容标签(ADR-0024) + 工具审批规则 + MCPSpecificApproval + Purview 策略外评(beta) + hyperlight 沙箱 | python/packages/core/agent_framework/security.py#ContentLabel |
| 14 | 部署运行时 | 🟡 | 托管走「app-owned 路由 helpers + Foundry Hosting/Local + Aspire/DevUI + Durable Azure Functions(ADR-0032)」；hosting 系列多 alpha，无自产生产 server/队列 | python/packages/hosting/pyproject.toml（description: execution-state helpers） |
| 15 | 管理平面 | 🟡 | devui 官方包（beta）：本地 playground + OpenAI 兼容端点 + React 前端；无多租户 console/billing | python/packages/devui/agent_framework_devui/_cli.py#main |

⚠️ 数量：0（本轮结论均回源码验证；个别子能力缺失处以 ❌ 注明而非存疑）。

## 5. 维度证据明细

**1 模型接入**
- `BaseChatClient`（`python/packages/core/agent_framework/_clients.py:221`）统一 get_response/流式接口，Agent 只依赖该协议【核心】。
- provider 全走官方独立包：openai（released，`OpenAIChatClient` `_chat_client.py:3587` Responses API + `OpenAIChatCompletionClient` `_chat_completion_client.py:1349`，Azure OpenAI 经 azure endpoint/TokenCredential 同客户端接入 `_chat_client.py:107,132`）；foundry（released，`FoundryChatClient` `_chat_client.py:929`）；anthropic（beta，直连/Bedrock/Vertex/Foundry 四个客户端文件：`anthropic/agent_framework_anthropic/_chat_client.py:1689`、`_bedrock_client.py`、`_vertex_client.py`、`_foundry_client.py`）【核心】。
- 另有 bedrock/gemini/mistral/ollama/claude/chatkit/copilotstudio/github_copilot（后两个 released）【核心】。
- 流式：`ResponseStream` 贯穿 Agent/Workflow；usage 聚合 `UsageDetails`+`add_usage_details`（`_types.py:433`）【核心】。
- 未见内置 model router / fallback / retry 策略（core `_clients.py` 无 fallback/retry 命中）——用户可自写 AgentMiddleware/ChatMiddleware 实现 ❌。

**2 上下文工程**
- 系统提示为 `instructions` 参数（`Agent.__init__`，`_agents.py:1893` 附近）；未见 SK 式通用 PromptTemplate/Handlebars 库（core `__init__.pyi` 无 PromptTemplate 导出）❌。
- 压缩一等公民：`CompactionStrategy` 协议 + `TokenizerProtocol` + `CharacterEstimatorTokenizer`（`_compaction.py:52,61,76`）；`group_messages`（:200）把函数调用/结果、reasoning 消息成组后再摘要（`_unambiguous_function_call_result_pairs` :105），Agent 构造器直接收 `compaction_strategy`/`tokenizer`【核心】。
- Skills 有 `{skills}` 占位符指令模板（`_skills.py` SkillsProvider 的 instruction_template）【核心】。
- 声明式 YAML 亦覆盖 agent 定义（`python/packages/declarative`，released）【核心】。

**3 记忆**
- 短期会话：`AgentSession`+`SessionStore`（core `_sessions.py:1707,1785`）+ `FileSessionStore` :1862；ADR-0034 定义其序列化规范【核心】。
- 长期记忆两路：harness 文件式 `MemoryStore`/`MemoryFileStore`/`MemoryContextProvider`（`_harness/_memory.py:561,663,976`，话题索引 MemoryTopicRecord :351）在 core；mem0（beta，`packages/mem0/.../_context_provider.py`）、redis（beta，context/history provider）生态扩展【核心+🟡】。
- 会话持久化存储生态：redis（beta）、azure-cosmos（beta history/checkpoint）；未见 forget/淘汰策略抽象 ❌。

**4 RAG**
- core 抽象：`@vector_store_model` 装饰器 + `VectorStoreCollectionDefinition`/`VectorStoreField`（`_vectors.py:727,332,156`），`_vector_filters.py` 过滤器【核心】。
- 实现全在生态包：azure-ai-search（beta，vector store + context provider）、qdrant（alpha）、postgres（alpha）、redis（beta）【🟡】。
- 未见 rerank、hybrid search、citation 抽象 ❌（检索即向量检索 + context provider 注入）。

**5 工具系统**
- `@tool` 装饰器（`_tools.py:1231`）schema 自动推断；`approval_mode`（:1237 起，默认 `never_require` :477）【核心】。
- 调用循环与预算：`FunctionInvocationLayer`（:3446）+ `FunctionInvocationConfiguration`（:1427，max_iterations/max_function_calls/max_duration_seconds，见 :418 docstring）【核心】。
- MCP：客户端在 core（`_mcp.py`，`MCPSpecificApproval` :86、结果体积预算截断 `_EncodedSizeBudget` :241、OTel 注入 meta :624）；服务端在 `packages/hosting-mcp`（agent/workflow 暴露为 MCP 工具：`_agent_tool.py`/`_workflow_tool.py`，alpha）【核心+🟡】。
- 沙箱：hyperlight 包（beta）+ shell 工具（`packages/tools`，`agent_framework_tools.shell`）【🟡】。
- Workflow 级还能 per-executor 注入 tools/kwargs（`Workflow.run` 的 tools/function_invocation_kwargs，`_workflow.py:746` 起）【核心】。

**6 Skill 机制**
- 完整抽象在 core（ADR-0037 agent-skills-design）：`Skill`(ABC) :619 + `SkillFrontmatter` :683（渐进披露：先只见 name/description），资源 `SkillResource` :104 与脚本 `SkillScript` :339 惰性读取【核心】。
- 三种来源：`FileSkill`/`FileSkillsSource`、`InlineSkill`、`MCPSkill`（skill 经 MCP 分发）；Source 可组合（Aggregating/Caching/Deduplicating/Filtering，见 `__init__.pyi:172-186` 导出）【核心】。
- `SkillsProvider(ContextProvider)`（:1908）把 skill 清单注入指令模板 `{skills}` 占位符；.NET 侧对应 `dotnet/src/Microsoft.Agents.AI.Mcp/Skills/`（`AgentMcpSkillResource.cs:21`）【核心】。

**7 规划推理**
- 结构化输出：`ChatOptions.response_format`（`_types.py:3818`，ADR-0036）+ `_parse_structured_response_value` :2265【核心】。
- ReAct 循环即 FunctionInvocationLayer 的迭代循环（预算见上）【核心】。
- 显式规划抽象不存在：无 Planner/Reflection 类；代替物是 orchestrations 的 Magentic progress ledger（`_magentic.py:272-338`，任务分解+复盘循环）、harness 的 `TodoProvider`（`_harness/_todo.py` TodoItem :54）、`AgentLoopMiddleware` 的 judge（`JudgeVerdict` `_harness/_loop.py:106`）【核心但分散→🟡】。

**8 编排**
- 图引擎：`Workflow`（`_workflow.py:228`）+ `WorkflowBuilder`（`_workflow_builder.py:53`，add_edge :230 / add_fan_out_edges :282 / add_fan_in_edges :511）；`Runner` 显式按 Pregel superstep 循环（`_runner.py:46` docstring、:125 起，每步 yield superstep_started/completed 事件）【核心】。
- 执行器：`AgentExecutor` :129、`FunctionExecutor` :36、`WorkflowExecutor` :112（子图）、`ChatForwardingExecutor`；另有函数式 API `FunctionalWorkflow`（`_functional.py:685`，`RunContext` :116、`WorkflowInterrupted` :95）双风格并存【核心】。
- `_viz.py` 提供图可视化数据；devui 前端可渲染【核心】。
- 声明式 workflow YAML：`packages/declarative` + `dotnet .../Workflows.Declarative`（Foundry/Mcp 变体）【核心】。

**9 多 Agent**
- orchestrations 包（released）构建于 Workflow 之上：`GroupChatOrchestrator` :98 / `AgentBasedGroupChatOrchestrator` :284（LLM 选下一发言者）、`HandoffAgentExecutor` :202（handoff 工具 + `HandoffSentEvent` :80）、Magentic（supervisor + progress ledger + 复盘重规划）、`SequentialBuilder` :65、Concurrent【核心】。
- HITL 编排件：`AgentApprovalExecutor` :169 / `AgentRequestInfoExecutor` :89（`_orchestration_request_info.py`）【核心】。
- A2A 协议：`packages/a2a`（beta）`A2AExecutor`（`_a2a_executor.py:31`，AgentExecutor 子类，远程 agent 入图）+ `A2AAgentSession`/`A2AContinuationToken`（`_agent.py:68,184`）；服务端 `packages/hosting-a2a`（alpha）【核心（beta）】。
- AutoGen 血统对应物在 `python/samples/autogen-migration/`；GroupChat/Handoff/Magentic 名字直接沿用【示例】。

**10 持久化**
- `WorkflowCheckpoint`（`_checkpoint.py:31`）：`graph_signature_hash` 恢复时拓扑校验、`previous_checkpoint_id` 链、`_executor_state`/`_edge_state`（fan-in 部分填充缓冲）、`pending_request_info_events`【核心】。
- Runner 每个 superstep 结束自动落 checkpoint（`_runner.py:168`）；`Workflow.run(checkpoint_id=...)` 恢复、`run(responses=...)` 续答（`_workflow.py:746` 统一入口，二者可组合）【核心】。
- 存储：core `InMemoryCheckpointStorage` :204 / `FileCheckpointStorage` :251 + `CheckpointStorage` 协议 :130；Cosmos（`packages/azure-cosmos/_checkpoint_storage.py`，beta）；Foundry 托管态 `foundry_hosting/_state_store.py`【核心+🟡】。
- 会话侧 SessionStore（见维度 3）；dotnet 侧 `Checkpointing/`、`CheckpointManager.cs`、`ExternalRequest.cs` 对应【核心】。

**11 HITL**
- 统一机制：executor 内 `ctx.request_info()` + `@response_handler`（`_request_info_mixin.py`）→ 事件流 request_info 事件 → Workflow 状态 `IDLE_WITH_PENDING_REQUESTS`（`_events.py:88`）→ 调用方 `run(responses={request_id: ...})` 续跑；**pending 请求写入 checkpoint，可跨进程恢复**（`_checkpoint.py` pending_request_info_events 文档）【核心】。
- 工具审批：`@tool(approval_mode=...)` + `ToolApprovalMiddleware`/`ToolApprovalRule`（`_harness/_tool_approval.py:86`，规则含参数级匹配、审批决定持久化 `ToolApprovalState` :158）；MCP 专用 `MCPSpecificApproval`（`_mcp.py:86`）；ADR-0006 userapproval【核心】。
- orchestrations 的 `AgentApprovalExecutor` 把审批做成图上执行器【核心】。

**12 观测评估**
- OTel 内建三层：`AgentTelemetryLayer`（:2275）、`ChatTelemetryLayer`（:1883）、`EmbeddingTelemetryLayer`（:2213），`configure_otel_providers`（:1592）一键配置（`observability.py`）；Agent 主类默认叠加遥测层【核心】。
- 特性使用位图进 User-Agent（ADR-0033，各包 `_feature_usage.py` FeatureIndex）【核心】。
- 评估：core `_evaluation.py`（`EvalItem` :183、`EvalResults` :374、`ConversationSplitter` :79、ExpectedToolCall :141）+ Foundry evals（`packages/foundry/.../_foundry_evals.py`，ADR-0023）；dotnet `Workflows/Evaluation/`【核心】。

**13 安全治理**
- 内容标签：`ContentLabel` = `IntegrityLabel`×`ConfidentialityLabel`（`security.py:121,138,157`），标签随消息流转并可 combine（ADR-0024 防提示注入）【核心】。
- 策略外评：`packages/purview`（beta）`PurviewPolicyMiddleware`（Agent 级 `_middleware.py:24`）/`PurviewChatPolicyMiddleware`（Chat 级 :150）对接 Microsoft Purview【🟡】。
- 沙箱执行：hyperlight（beta）+ shell 工具；.NET 另有 `Tools.Shell`/`Hyperlight` 项目【🟡】。
- 未独立 Content Safety / PII 模块（python/dotnet 源码 grep `ContentSafety` 无命中）❌——依赖 Purview/Foundry 侧。

**14 部署运行时**
- 哲学是「app-owned hosting」：`packages/hosting`（alpha）只给执行态 helpers，服务由用户框架（FastAPI/ASP.NET）承载；`hosting-responses`（alpha）提供 OpenAI Responses 形状端点 helpers【🟡】。
- Azure 路线：`foundry_hosting`（beta，长运行/弹性 agent，ADR-0035）+ `foundry_local`（beta）+ Durable Agents（Azure Functions 持久化，ADR-0032，dotnet `Hosting.*`）【🟡】。
- 协议出口：hosting-a2a、hosting-telegram、ag-ui（released）、hosting-mcp【🟡】。
- 无自产 queue/cron/HA 运行时 ❌。

**15 管理平面**
- `packages/devui`（beta）：CLI 入口为 `devui` 命令（`pyproject.toml [project.scripts] devui`，`_cli.py:149 main`）——检索线索中的 `afr` 工具名在本仓无命中（已 grep README/pyproject 确认）❌（以 devui 为准）。
- devui 含 OpenAI 兼容服务（`_server.py`、`_openai/`）、会话管理、agent 发现（`_discovery.py`）、tracing 页（`_tracing.py`）+ React 前端（`frontend/`）；.NET 侧 `Microsoft.Agents.AI.DevUI` + `Aspire.Hosting.AgentFramework.DevUI`【🟡】。
- 无多租户 console / 计费 / 配置中心 ❌（企业治理交给 Foundry/Purview 平台侧）。

## 6. 设计决策要点（框架独有取舍）

1. **洋葱分层 Agent 而非继承树**：`Agent = AgentMiddlewareLayer + AgentTelemetryLayer + RawAgent`（`_agents.py:1794`），可观测与中间件是可剥离的 mixin 层——遥测默认在、要裸机用 RawAgent。
2. **双 API 编排（图 + 函数式）共用同一 Pregel 引擎与 checkpoint**：`WorkflowBuilder` 图与 `FunctionalWorkflow` 函数式都落到同一 Runner/checkpoint 体系；子图即 `WorkflowExecutor` 普通节点。
3. **HITL = 可持久化暂停点**：request_info 事件进 checkpoint，`IDLE_WITH_PENDING_REQUESTS` + `run(responses=)` 与崩溃恢复走同一条 checkpoint 通道，人机协同与容错统一。
4. **checkpoint 带图哈希校验**（`graph_signature_hash`）：恢复时验证拓扑兼容，防「改图后恢复旧 checkpoint」这类静默错误。
5. **安全纵深四层**：工具级审批规则（参数级匹配、决定持久化）→ MCP 专项审批 → 消息内容标签（完整性×机密性格，ADR-0024）→ Purview 外部策略评估；这是本组框架里唯一把「标签随消息流转」做进 core 类型的。
6. **core 里长出一个编码 Agent harness**：`create_harness_agent` 打包 todo/mode/file-memory/skills/background-agents providers + AgentLoopMiddleware（judge 决定是否继续，默认 10 轮）+ 工具审批——对标 Claude Code 式产品的「参考实现进核心库」，并配 monty(CodeAct)/lab 实验包。
7. **Agent Skills 直接对齐 Anthropic 规范**：frontmatter 渐进披露 + 惰性资源/脚本 + MCP 作为 skill 分发通道（ADR-0029/0037），且 Python/.NET 双侧实现。
8. **包治理显式化**：`PACKAGE_STATUS.md` 逐包标注 alpha/beta/rc/released + API 级 staged features（`_feature_stage.py` 实验告警）；双语言对齐靠 47 个共享 ADR + 声明式 YAML spec。

## 7. Python vs .NET 对齐度简评

总体**高度同构、命名对齐**（同名概念：AIAgent/ChatClientAgent、Workflow/Checkpointing、GroupChat/Handoff/Magentic/Sequential/Concurrent、Harness、DevUI、Purview、A2A、AGUI、Hyperlight、Declarative 均双侧存在）：

- 抽象对应：Python `Agent`（`_agents.py:1794`）↔ .NET `AIAgent`（`dotnet/src/Microsoft.Agents.AI.Abstractions/AIAgent.cs:38`）；Python `AgentMiddleware/FunctionMiddleware/ChatMiddleware` ↔ .NET filter/middleware 体系（ADR-0007 agent-filtering-middleware）。
- 结构差异：Python 把 orchestrations 拆成独立 released 包 `agent-framework-orchestrations`，.NET 并入 `Microsoft.Agents.AI.Workflows`（`Specialized/` 目录：`HandoffAgentExecutor.cs`、`Magentic/MagenticOrchestrator.cs`、`SequentialWorkflowBuilder.cs`）；.NET 多出 `AzureAI.Persistent`、`Valkey`、`LocalCodeAct`、`Workflows.Generators`，Python 多出 chatkit/claude/monty/lab 等。
- 成熟度节奏：.NET 版本号领先（1.21.0 vs Python 1.18.0），Python 侧大量包处于 beta/alpha（hosting 系列 alpha）；Skills 双侧已实现但入口不同（.NET 在 Mcp 项目的 Skills/ 目录）。
- 版本节奏差 3 个 minor 是**双侧对齐的已知噪音**，非能力代差；对齐由 ADR（如 0032 durable、0035 hooks）+ 声明式 spec 强制约束，属于双语言框架治理的可复制范式。
