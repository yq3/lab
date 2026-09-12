# AgentScope Java (agentscope-java) 框架档案

> 基线：~/develop/opensource/agentscope-java @ c5db8f72 2026-09-11；版本 pom.xml `revision=2.0.3-SNAPSHOT`（tag v2.0.2，HEAD = v2.0.2+144，Maven 多模块，Java 17，org: Alibaba）
> 对照仓：agentscope（Python）v2.0.8 @ b82253ba 2026-09-11。两侧 v2 均为破坏性重构：v1 的 pipeline（Sequential/Fanout/MsgHub）、SessionManager、FormFillingAgent 已删除。

## 1. 定位

阿里通义实验室 AgentScope 的 Java 版：基于 Project Reactor 的**事件驱动 ReAct Agent 框架 + coding-agent 级运行时**。三层递进——`agentscope-core`（轻核心：ReActAgent + middleware + state + tool + permission）、`agentscope-harness`（组装出"编码代理"级重能力：子代理/团队/沙箱/压缩/skill 策展）、`agentscope-service`（企业控制平面：Gateway/DataPlane/Scheduler 三进程 + React 管理台，宣称可治理 Claude/OpenClaw/QwenPaw 等多框架 Agent，见 `agentscope-service/README.md`）。目标用户是 Java/Spring 企业栈；交付形态除 Maven 工件外还有 11 个 Spring Boot starter、Docker/Helm 与 Go 写的 aistio 流量连接器。既是库也是平台。

## 2. 仓库结构与核心包

构建：Maven 多模块（根 `pom.xml#<modules>`，`<java.version>17`，reactor 为一线公民——示例规范禁止 `.block()`，见根 `SKILL.md`）。

| 模块 | 内容 |
|---|---|
| `agentscope-core` | `io.agentscope.core`（305 个 java 文件）：根级 `ReActAgent.java`（5401 行）+ agent/ model/ middleware/ state/ tool/ skill/ permission/ rag/ formatter/ tracing/ interruption/ hook/ credential/ workspace/ event/ memory/（整包 @Deprecated） |
| `agentscope-harness` | `io.agentscope.harness.agent`：HarnessAgent（2973 行，包装 ReActAgent）+ 19 个 middleware + subagent/ team/ bus/ coordination/ memory(compaction,session)/ sandbox(impl/docker)/ skill(curator,runtime)/ gateway/ filesystem/ transcript/ |
| `agentscope-service` | 三进程平台：`service-gateway`（GatewayApp）、`service-dataplane`（DataApp：托管会话/工具确认/内存挂载）、`service-scheduler`（SchedulerApp：cron 部署/渠道运行时/Outbound）+ `service-common` + `frontend/`（React 管理台）+ `aistio/`（Go 模块 `github.com/spring-ai-alibaba/aistio`，agent 流量连接器）+ docker/ helm/ docker-compose/ deploy/ |
| `agentscope-extensions` | 22 个官方扩展：model×5（dashscope/openai/anthropic/gemini/ollama）、mem×3（mem0/bailian/reme）、rag×5（simple/bailian/dify/haystack/ragflow）、sandbox×4（agentrun/daytona/e2b/kubernetes）、channel×5（dingtalk/feishu/github/gitlab/wecom）、protocol×4（a2a-client+server/agent-protocol/agui/chat-completions-web）、scheduler（quartz/xxl-job）、skills 仓库×3（git/mysql/postgresql）、存储×7（jdbc/redis/mysql/postgresql/mongodb/oss/cos）、studio、training、aistio、higress、nacos + `agentscope-spring-boot-starters/`（11 个 starter） |
| `agentscope-examples` | `agents/`：codingagent（issue→克隆→改码→开 PR 的自治编码 bot）、dataagent、paw（QwenPaw 的 Java 版个人助理）+ agui/ copilotkit/ documentation |
| `agentscope-dependencies-bom`、`agentscope-distribution` | BOM 与发行打包 |

## 3. 核心抽象清单

| 符号 | 路径 | 一句话说明 |
|---|---|---|
| `Agent` | agentscope-core/.../agent/Agent.java#L47 | `CallableAgent + StreamableAgent + ObservableAgent` 组合接口；回复契约 = `Mono<Msg>` 单终态 + `Flux<AgentEvent>` 事件流 |
| `ReActAgent` | agentscope-core/.../ReActAgent.java#L215 | 5401 行 ReAct 主类：reasoning/acting 循环、结构化输出双路径、HITL、maxIters 兜底 |
| `CallExecution` | agentscope-core/.../ReActAgent.java#L1653 | 内部类：`executeIteration(0)→reasoning→acting→reasoning(iter+1)`；`resumeAgent()` 从 pending 工具调用直接进 acting |
| `MiddlewareBase`/`MiddlewareChain` | agentscope-core/.../middleware/MiddlewareChain.java | onReasoning/onActing/onModelCall 三切面洋葱链，取代继承扩展 |
| `Hook` + 12 事件 | agentscope-core/.../hook/Hook.java | Pre/Post×Reasoning/Acting/Call/Summary + Chunk 事件的遗留观测面（v1 兼容） |
| `Model`/`ChatModelBase` | agentscope-core/.../model/ChatModelBase.java#L78 | `stream()→Flux<ChatResponse>` 流式模型基类 |
| `ModelRegistry` + `ModelProvider` SPI | agentscope-core/.../model/ModelRegistry.java#L104、#L367 | 按 modelId 解析命名实例或 `ServiceLoader<ModelProvider>` 工厂 |
| `ChatUsage` | agentscope-core/.../model/ChatUsage.java | inputTokens/outputTokens/cachedTokens/totalTokens/time（无 cost 计价） |
| `ModelContextWindows` | agentscope-core/.../model/ModelContextWindows.java | 按前缀推断 qwen/gpt 等上下文窗口（供压缩阈值用） |
| `HttpTransport`/`WebSocketTransport` | agentscope-core/.../model/transport/ | 可插拔网络层：JDK/OkHttp HTTP（含代理）+ WebSocket |
| `Toolkit` | agentscope-core/.../tool/Toolkit.java#L66 | 工具门面：注册/分组激活/schema 生成/元工具（reset_equipped_tools） |
| `@Tool` | agentscope-core/.../tool/Tool.java#L60 | 注解元数据：strict/readOnly/concurrencySafe/externalTool/stateInjected/dangerousFiles/dangerousDirectories |
| `McpClientManager` | agentscope-core/.../tool/McpClientManager.java | MCP 消费：StdIO/SSE/StreamableHttp 三传输（mcp/McpClientBuilder.java#L59） |
| `PermissionEngine`/`PermissionMode` | agentscope-core/.../permission/PermissionEngine.java | 6 步确定性求值：deny→ask→工具自检(bypass-immune)→allow→BYPASS→默认 ASK；模式 DEFAULT/ACCEPT_EDITS/EXPLORE/BYPASS/DONT_ASK |
| `AgentStateStore` | agentscope-core/.../state/AgentStateStore.java#L61 | userId+sessionId+key 三元组存取；`getVersioned`/`saveIfVersion`（#L104/#L131）CAS 乐观并发 |
| `AgentState` | agentscope-core/.../state/AgentState.java | 上下文/reply/工具缓存/任务/权限全量可序列化（v2 会话载体，取代 Memory） |
| `SkillBox`/`SkillRegistry` | agentscope-core/.../skill/SkillBox.java#L629 | SKILL.md 加载 + `load_skill_through_path` 渐进披露元工具 + FS/Classpath 仓库 |
| `Knowledge` | agentscope-core/.../rag/Knowledge.java#L34 | RAG 统一存取接口 + GenericRAGHook（检索注入）+ KnowledgeRetrievalTools（检索即工具） |
| `LongTermMemory` | agentscope-core/.../memory/LongTermMemory.java#L70 | record/retrieve 长期记忆抽象——**整包 @Deprecated(forRemoval, since 2.0.0)**，但 mem 扩展仍在用 |
| `InterruptControl` | agentscope-core/.../interruption/InterruptControl.java | session 级中断信号（USER/SYSTEM 源），HITL 基石 |
| `ToolSuspendException` | agentscope-core/.../tool/ToolSuspendException.java | 工具挂起（等审批/外部执行），下次 `call` 携 ConfirmResult 续跑 |
| `HarnessAgent` | agentscope-harness/.../HarnessAgent.java#L168 | 组装 ReActAgent + 19 middleware：subagent/team/sandbox/compaction/skill 策展/plan mode |
| `SubagentsMiddleware`/`TeamsMiddleware` | agentscope-harness/.../middleware/ | `task`/`task_output` 子代理工具（同步+后台）与 team 协作 |
| `ConversationCompactor` | agentscope-harness/.../memory/compaction/ConversationCompactor.java#L60 | token/消息数触发摘要压缩（keepTokens 保留、可换摘要模型、增量叠加） |
| `PeriodicGate` | agentscope-harness/.../coordination/PeriodicGate.java | 周期唤醒门（Local/StoreBacked 实现）——cron 型自主 agent 原语 |
| `GatewayApp`/`DataApp`/`SchedulerApp` | agentscope-service/service-{gateway,dataplane,scheduler}/ | 三进程控制平面：契约路由 / 托管会话与工具确认 / cron 部署与渠道 |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | core SPI+Registry+可插拔 HTTP/WS 传输；5 官方 provider（dashscope/openai/anthropic/gemini/ollama）各配 starter；usage 含 cachedTokens、无 cost | agentscope-core/.../model/ModelRegistry.java#resolve；agentscope-extensions/agentscope-extensions-model/（5 子模块） |
| 2 | 上下文工程 | ✅ | token/消息数触发摘要压缩 + 工具结果驱逐（正交机制）+ 窗口表推断 + system prompt 中间件 | agentscope-harness/.../memory/compaction/{CompactionConfig,ConversationCompactor}.java；model/ModelContextWindows.java |
| 3 | 记忆 | 🟡 | core memory 包整体弃用；长期记忆走旧 API 的 3 个官方扩展（mem0/bailian/reme）；会话上下文归 AgentState | agentscope-core/.../memory/Memory.java#@Deprecated；agentscope-extensions/agentscope-extensions-mem/（3 子模块） |
| 4 | RAG | 🟡 | core 仅 Knowledge 接口 + Hook/Tools 两用法；5 官方扩展全为外部引擎委托（bailian/dify/haystack/ragflow/simple），无自建向量库/rerank | agentscope-core/.../rag/Knowledge.java；agentscope-extensions/agentscope-extensions-rag/ |
| 5 | 工具系统 | ✅ | 注解 schema + 分组激活 + 元工具 + MCP 三传输 + shell 白名单校验 + 危险路径 + 5min 超时/重试配置 + 4 沙箱后端 | agentscope-core/.../tool/{Toolkit,Tool,McpClientManager,ToolkitConfig}.java；tool/coding/UnixCommandValidator.java |
| 6 | Skill 机制 | ✅ | SkillBox 渐进披露（load_skill_through_path）+ curator/usage 中间件 + FS/classpath/git/mysql/pg 仓库；仓库根本身就带一份 SKILL.md | agentscope-core/.../skill/SkillBox.java#L629；agentscope-harness/.../skill/curator/；agentscope-extensions/agentscope-extensions-skills/ |
| 7 | 规划推理 | ✅ | 完整 ReAct 循环（maxIters 兜底 summarizing、gotoReasoning、空回复提醒重试）+ 结构化输出 native/工具双路径 + TodoTools + PlanMode | agentscope-core/.../ReActAgent.java#summarizing(L3543)、#STRUCTURED_OUTPUT_TOOL_NAME(L222)；tool/builtin/TodoTools.java |
| 8 | 编排 | 🔶 | 无 graph/workflow DSL（v1 pipeline 已删）；替代物为 subagent task/team/MessageBus/PeriodicGate 高层原语 | rg 全仓无 StateGraph/GraphBuilder 命中；agentscope-harness/.../coordination/PeriodicGate.java、bus/MessageBus.java |
| 9 | 多 Agent | ✅ | agent-as-tool（core）+ task/task_output 子代理（同步/后台/跨节点）+ team + A2A client/server 扩展 + starter + 注册（admin/nacos/higress） | agentscope-core/.../tool/{AgentTool,subagent/SubAgentTool}.java；agentscope-extensions/agentscope-extensions-protocol/agentscope-extensions-a2a/ |
| 10 | 持久化 | ✅ | AgentStateStore 三元组 + VersionedState CAS 乐观并发 + 7 个官方存储后端（jdbc/redis/mysql/pg/mongo/oss/cos）+ v1 LegacyStateLoader | agentscope-core/.../state/AgentStateStore.java#saveIfVersion(L131)；agentscope-extensions/agentscope-extensions-jdbc/state/JdbcAgentStateStore.java |
| 11 | HITL | ✅ | session 级精准 interrupt + 工具挂起/二次 call 送达审批 + PERMISSION_ASKING 终态 + dataplane 跨进程审批协调 + AG-UI starter | agentscope-core/.../ReActAgent.java#L1838（HITL resume 校验）；agentscope-service/service-dataplane/.../ToolConfirmationCoordinator.java |
| 12 | 观测评估 | ✅ | OTEL middleware（Reactor 上下文传播）+ Tracer SPI + 全量 Hook 事件 + harness AgentTrace + Studio 对接；**eval/dataset ❌** | agentscope-core/.../tracing/OtelTracingMiddleware.java；agentscope-extensions/agentscope-extensions-studio/src/main/.../StudioClient.java |
| 13 | 安全治理 | ✅ | 6 步确定性权限链 + 5 模式 + bypass-immune 工具自检 + 危险路径 + Unix/Windows 命令校验 + 4 沙箱 + DB 分布式沙箱锁 + credential 包；无 PII/内容 guardrail | agentscope-core/.../permission/PermissionEngine.java；agentscope-extensions/agentscope-extensions-jdbc/sandbox/JdbcSandboxExecutionGuard.java |
| 14 | 部署运行时 | ✅ | 三进程 service（Gateway/DataPlane/Scheduler）+ Docker/Helm/compose + Go 版 aistio 连接器 + 11 Spring starter + quartz/xxl-job + 5 IM 渠道 | agentscope-service/{service-gateway,service-dataplane,service-scheduler}/、helm/、aistio/go.mod；agentscope-extensions/agentscope-extensions-scheduler/ |
| 15 | 管理平面 | ✅ | React 管理台 + admin starter（AgentRegistry/CommandPlane 管理命令面）+ scheduler 自托管管理 Web + Studio；无租户/计费 | agentscope-service/frontend/src/（React）；agentscope-extensions/.../agentscope-admin-spring-boot-starter/.../registry/AgentRegistry.java |

## 5. 维度证据明细

### 1) 模型接入
- `Model` SPI：`ModelRegistry.resolve(modelId)`（`agentscope-core/src/main/java/io/agentscope/core/model/ModelRegistry.java#L104`）先查命名实例，再走 `ServiceLoader.load(ModelProvider)`（#L367）工厂创建并按 `ModelCacheKey` 缓存。【核心】
- 5 个官方 provider 扩展（`agentscope-extensions/agentscope-extensions-model/`）：DashScope（自有 HttpClient + EndpointType + 加密工具）、OpenAI、Anthropic、Gemini、Ollama；anthropic/gemini 各带完整 formatter 子包（消息/媒体转换、会话合并）。Python 侧 10 家（含 deepseek/moonshot/volcengine/xai/openai_response），Java 少 5 家（OpenAI 兼容端点可部分覆盖）。【核心】
- 传输层可插拔：`model/transport/`（JDK/OkHttp HttpTransport + ProxyConfig + WebSocketTransport），模型 HTTP 客户端不绑定。全流式：`ChatModelBase#stream → Flux<ChatResponse>`（`ChatModelBase.java#L78`）。【核心】
- usage：`ChatUsage`（inputTokens/outputTokens/cachedTokens/totalTokens/time）——有缓存命中统计，**无 cost 计价、无 router/fallback**（Registry 只做解析不做路由）。starter：dashscope/openai/anthropic/gemini/ollama 各一个。【核心】
- 证据等级：以上均【核心】。

### 2) 上下文工程
- 压缩在 harness 层：`CompactionConfig`（`agentscope-harness/.../memory/compaction/CompactionConfig.java#L61`）——按消息数或估算 token 触发（0=禁用）、keepTokens 保留区、压缩预留 buffer、可指定专用摘要模型（#L237）。`ConversationCompactor#compactIfNeeded`（`ConversationCompactor.java#L60`）摘要叠加历史摘要（增量式）。【核心】
- 正交机制：`ToolResultEvictionConfig`——工具结果驱逐，与摘要压缩互不影响（javadoc 明示 orthogonal）。`ToolResultEvictionMiddleware`（harness middleware）。【核心】
- 窗口推断：`ModelContextWindows`（core）按最长前缀匹配 qwen3/gpt-4.1 等 → 供压缩阈值计算。【核心】
- system prompt 可被 middleware 链改写：`ReActAgent#applySystemPromptMiddlewares`（`ReActAgent.java#L779`）；空回复时注入合成提醒再推理（#L2487 附近 buildEmptyResponseReminder）。【核心】
- 与 Python 的差异：无「自主压缩工具」暴露、无图片先降级 HintBlock 的显式实现（⚠️未逐行核媒体降级）。

### 3) 记忆
- v2 路线：上下文即状态。`AgentState#getContext()` 为唯一会话载体；`agentscope-core/.../memory/` 整包 8 个类全部 `@Deprecated(forRemoval=true, since="2.0.0")`（`Memory.java#L34`、`LongTermMemory.java#L70`）。【核心】
- 但长期记忆实现仍在官方扩展且基于弃用 API：`agentscope-extensions-mem/` = mem0、memory-bailian（阿里云百炼）、reme 三套（`BailianLongTermMemory`、`ReMeLongTermMemory`），`LongTermMemoryTools` 支持 AGENT_CONTROL 模式（记忆读写成工具）。【核心】
- harness 侧：`MemoryConsolidator`/`MemoryFlushManager`/`MemoryBackgroundTasks`（`harness/agent/memory/`）+ `MemoryFlushMiddleware`/`MemoryMaintenanceMiddleware`。会话树/转写：`session/SessionTree`、`SessionTranscriptWriter`、`SessionFreshnessEvaluator`。【核心】
- 评级 🟡 原因：核心级新抽象缺位（弃用未替换），长期记忆能力依赖生态扩展。

### 4) RAG
- core 抽象极薄：`Knowledge` 接口（存/检文档）、`GenericRAGHook`（检索结果注入上下文）、`KnowledgeRetrievalTools`（检索作为工具暴露）、`RAGMode` 二选一模式、`model/{Document,DocumentMetadata,RetrieveConfig}`。【核心】
- 5 个官方扩展全为外部引擎委托：rag-simple（内存）、rag-bailian、rag-dify、rag-haystack、rag-ragflow（`agentscope-extensions/agentscope-extensions-rag/`）。【核心】
- 无向量库、无切分/ingestion 管道、无 rerank/citation/hybrid search。与 Python 侧（自带 parser word/ppt + 向量库集成）相比收窄。

### 5) 工具系统
- 注册与 schema：`@Tool`/`@ToolParam` 注解 + `ReflectiveFunctionTool` 反射生成 JSON schema；`Toolkit`（`tool/Toolkit.java#L66`）门面 + `ToolGroupManager` 分组激活（运行时切换工具面）+ `MetaToolFactory` 元工具（`reset_equipped_tools` 让模型自管分组）+ preset 参数（MCP 工具预置参）。【核心】
- 元数据即治理输入：readOnly（只读快路径）、concurrencySafe、externalTool、stateInjected、strict（严格 schema）、dangerousFiles/dangerousDirectories（`Tool.java#L90-L156`）——注解直接喂给权限引擎。【核心】
- MCP：`McpClientManager` + `mcp/McpClientBuilder`（StdIO/SSE/StreamableHttp 三传输，#L59-60）；harness `McpServerRegistrar` 支持配置注册。【核心】
- 执行治理：`ToolkitConfig` 内嵌 ExecutionConfig——默认 5 分钟超时、无重试；`ToolSuspendException` 挂起等审批。【核心】
- 内置工具族：`tool/file/{ReadFileTool,WriteFileTool}`、`tool/coding/{ShellCommandTool + Unix/WindowsCommandValidator}`（命令白名单校验）、`builtin/TodoTools`。【核心】
- 沙箱：harness 自带 docker 实现（`sandbox/impl/docker/`）+ 扩展 agentrun/daytona/e2b/kubernetes；`SandboxLifecycleMiddleware` 管生命周期；`JdbcSandboxExecutionGuard` 用 DB 锁防多节点并发执行同一沙箱。【核心】

### 6) Skill 机制
- core 完整 Claude 式实现：`SkillRegistry` + `SkillBox`（渐进披露：先给 name/description，`load_skill_through_path` 按需加载 SKILL.md 与资源，`SkillBox.java#L629`）+ `DynamicSkillMiddleware`（运行时挂载）+ `SkillToolFactory` + `SkillFileFilter`。【核心】
- 仓库后端：`skill/repository/{FileSystem,Classpath}SkillRepository`（core）+ 扩展 git/mysql/postgresql 仓库（`agentscope-extensions-skills/`）。【核心】
- harness 策展：`SkillCuratorMiddleware`/`SkillUsageMiddleware`/`runtime/SkillPromptBuilder` + `RuntimeContextSkillRepository`/`WorkspaceSkillRepository`。【核心】
- 有辨识度：仓库根 `SKILL.md` 本身就是给 AI 编码助手用的框架技能文件（教 AI 写 agentscope-java 代码，禁 `.block()` 等）。【核心】

### 7) 规划推理
- 循环（`ReActAgent.java` 内部类 CallExecution）：`executeIteration(0)→reasoning(iter)→acting(iter)→executeIteration(iter+1)`（#L2295/L2306/L2757）。【核心】
- 终止条件：① `isFinished`（无新工具调用即终态）；② `iter >= maxIters` → `summarizing()`（#L3543：先给 pending 工具补 error 结果再生成总结）；③ middleware 发 `RequestStopEvent`（记录 GenerateReason 后带终态返回）；④ `gotoReasoning`（hook 请求跳步，`reasoning(iter+1, ignoreMaxIters=true)` #L2466）；⑤ interrupt。【核心】
- maxIters 默认值双轨：builder 默认 10（#L4565），`agent/config/ReactConfig.DEFAULT_MAX_ITERS = 20`（`ReactConfig.java#L33`）+ `stop_on_reject` 选项（工具全拒即停）。【核心】
- 结构化输出双路径：native `responseFormat`（`doNativeStructuredCall` #L1284）不支持时回退注入 `generate_response` 合成工具（`doFallbackStructuredCall` #L1340，工具名常量 #L222）；`call(Class)`/`call(JsonNode)` 6 个重载（`CallableAgent.java#L43-95`）。【核心】
- 计划辅助：`builtin/TodoTools` + harness `PlanModeMiddleware` + `state/{Task,TaskContextState,PlanModeContextState}`。无 reflect/self-critique 内置。

### 8) 编排
- ❌ 无图/workflow：rg 全仓（core+harness main）无 `StateGraph|GraphBuilder|digraph` 命中；v1 的 Sequential/Fanout/MsgHub pipeline 已删（与 Python v2 同步取舍）。【核心】
- 替代原语（均在 harness，非通用编排 API）：`SubagentsMiddleware`（task/task_output 工具，同步+后台任务）、`TeamsMiddleware` + `team/TeamClient`、`bus/{MessageBus,WorkspaceMessageBus,AsyncToolRegistry}`（异步工具记录/唤醒）、`coordination/PeriodicGate`（Local/StoreBacked 两实现，周期唤醒 = cron 型常驻 agent）。【核心】
- 评级 🔶：有面向"自主代理"的高层协作原语，但用户要 DAG/分支循环仍需自建或用 subagent 模拟。

### 9) 多 Agent
- agent-as-tool：core `tool/AgentTool.java` + `tool/subagent/SubAgentTool`（SubAgentConfig/SubAgentProvider）。【核心】
- harness 子代理体系：`SubagentsMiddleware`/`DynamicSubagentsMiddleware`（动态声明）、`subagent/{DefaultAgentManager,SubagentFactory,SubagentSpecGenerator,TaskRepository}`；跨节点：`RemoteSubagentStub` + `RemoteAskPolicy` + `gateway/{SubagentRegistry,SubagentGatewayBridge}`（exposeSubagent 把本地子代理暴露为远端可调用）。【核心】
- team：`team/{TeamClient,LocalTeamClient,TeamCreateSpec,TeamMemberSpec,TeamTask,TeamWakeups}`。【核心】
- A2A：协议扩展双子模块 `agentscope-extensions-a2a-client`（A2aAgent、AgentCardResolver、PartParserRouter）与 `-server`；starter `agentscope-a2a-spring-boot-starter`（A2aJsonRpcController + AgentCardController 自动暴露 AgentCard）。【核心】
- 注册中心：admin starter `InMemoryAgentRegistry`；`agentscope-extensions-nacos`（配置/注册）与 `higress`（网关）扩展。⚠️ nacos/higress 扩展内容未逐文件细读。

### 10) 持久化
- 接口：`AgentStateStore`（`state/AgentStateStore.java#L61`）——`userId+sessionId+key` 三元组 get/save；**乐观并发**：`getVersioned`/`saveIfVersion`（#L104/#L131）CAS 写，冲突抛 `ConcurrentSessionModificationException`，`ConflictPolicy` 定策略；不支持版本的后端默认退化为无条件写。【核心】
- 后端矩阵：core InMemory/JsonFile；官方扩展 jdbc（方言抽象 `dialect/AbstractJdbcDialect`）、redis、mysql、postgresql、mongodb、oss、cos——7 个持久化后端 + `RedisDistributedStore`/`JdbcDistributedStore`（分布式协调）。【核心】
- 可恢复：ReActAgent 每轮持久化状态（`saveStateToSession` #L475），`resumeAgent` 从 pending 工具调用续跑；`LegacyStateLoader` 兼容 v1 会话。【核心】
- 快照：harness `sandbox/snapshot/` + `JdbcSnapshotSpec/JdbcRemoteSnapshotClient`（沙箱远端快照）。

### 11) HITL
- 中断：`InterruptControl`（USER/SYSTEM 源）挂 `AgentState`；`agent.interrupt(userId, sessionId, msg)` 精准中断指定会话（`ReActAgent.java#L963`）；每轮 `checkInterrupted` 检查点（#L1736）；shutdown 中断有 partialReasoningPolicy（保留/丢弃半截推理）。【核心】
- 审批即挂起：权限 ASK → 工具抛 `ToolSuspendException` → 本轮以 `GenerateReason.PERMISSION_ASKING` 终态返回（#L2815）；**第二次 `call` 携带 ConfirmResult 续跑**，resume payload 严格校验「当前正 ASKING 的工具」（#L1838），伪造/错位即拒绝。【核心】
- 跨进程审批：dataplane `ToolConfirmationCoordinator`/`PendingHandsToolService`/`InternalToolConfirmationController`——审批流在服务层流转。【核心】
- 协议级：`agentscope-agui-spring-boot-starter`（AG-UI 协议对接前端）；`chat-completions-web` 扩展暴露 OpenAI 兼容端点。

### 12) 观测评估
- OTEL：`OtelTracingMiddleware`（`tracing/OtelTracingMiddleware.java#L72`，含 `ContextPropagationOperator` reactor 上下文传播）；`Tracer`/`TracerRegistry`/`NoopTracer` SPI。【核心】
- 事件面：core `event/` AgentEvent 体系 + `hook/` 12 类事件（Pre/Post×Reasoning/Acting/Call/Summary + Chunk）+ `hook/recorder/`；harness `AgentTraceMiddleware`、`TranscriptMiddleware`。【核心】
- 可视化：`agentscope-extensions-studio`（StudioClient/StudioWebSocketClient/StudioMessageHook/StudioUserAgent）对接 AgentScope 平台。【核心】
- ❌ eval：全仓（core/harness/extensions main）无 eval/dataset/benchmark 正式抽象（rg 仅命中无关类名）。

### 13) 安全治理
- 权限引擎（`permission/PermissionEngine.java`）：确定性 6 步——① DENY 规则 ② ASK 规则 ③ 工具自检（bypass-immune：EXPLORE/ACCEPT_EDITS 只读判定 + 危险路径）④ ALLOW 规则 ⑤ BYPASS 模式放行 ⑥ 默认 ASK（DONT_ASK 模式降级为 DENY，#L189-198）。模式全集 DEFAULT/ACCEPT_EDITS/EXPLORE/BYPASS/DONT_ASK（`PermissionMode.java#L34-38`）。【核心】
- 工具侧防线：`@Tool#dangerousFiles/dangerousDirectories` + `ToolDangerousPathConstants`；`coding/UnixCommandValidator`/`WindowsCommandValidator` shell 白名单。【核心】
- 沙箱隔离：harness docker 实现 + agentrun/daytona/e2b/kubernetes 扩展 + `SandboxLifecycleMiddleware` + `JdbcSandboxExecutionGuard`（DB 分布式锁）。【核心】
- 凭证：core `credential/` 包 + 各模型扩展 credential 子包（如 AnthropicCredential）。❌ 无输入内容 guardrail/PII 检测。

### 14) 部署运行时
- 三进程平台（`agentscope-service/`）：service-gateway（`GatewayApp`、契约路由、会话解析）、service-dataplane（`DataApp`、`HarnessAgentBuildService`、`SessionTurnRunner`、`ManagedMemoryTools`、`MemoryMountService`、`SkillsBundleService`、外部沙箱注册表、自托管 worker）、service-scheduler（`SchedulerApp`、`CronDeploymentScheduler`、`ChannelRuntimeCatalog`、`OutboundService`、`HandsWorkerMain`）。【核心】
- 云原生：`docker-compose.yml`、`helm/agentscope-service/`、`deploy/`、`release/` runbook。【核心】
- aistio：Go 模块（`aistio/go.mod` = github.com/spring-ai-alibaba/aistio，含 connector/cmd/helm）——agent 流量治理连接器；extensions 下另有 Java 侧 `agentscope-extensions-aistio`。⚠️ 具体职责（Istio 集成面）未逐文件细读。【核心】
- 调度：`agentscope-extensions-scheduler`（quartz / xxl-job）+ harness `PeriodicGate`。【核心】
- 渠道：`agentscope-extensions-channel`（dingtalk/feishu/wecom/github/gitlab）。Spring 交付：11 个 starter（主 starter + 5 模型 + a2a/admin/agui/nacos/chat-completions-web）。【核心】

### 15) 管理平面
- Web 管理台：`agentscope-service/frontend/src/`（React：api/app/components/features/pages，含 e2e 测试）。【核心】
- admin starter：`AgentRegistry`/`InMemoryAgentRegistry`（agent 清单）、`CommandPlane`/`AdminCommandRegistry`（管理命令面）、`AgentInventory`、`SummarizationStrategy`。【核心】
- scheduler 自托管管理：`service-scheduler/.../web/managed/selfhosted/`（托管 agent 的 Web 管理）。【核心】
- 平台定位证据：service README「unified control plane … govern and coordinate Agents built with different frameworks — Claude, OpenClaw, QwenPaw」。❌ 无租户/计费/配额管理。

## 6. 设计决策要点

1. **Reactor 双契约**：`call() → Mono<Msg>`（一次调用恰好一个终态消息）+ `stream() → Flux<AgentEvent>`（细粒度事件流）——同步语义与流式语义分离，`Agent.java#L47` 接口组合表达。
2. **middleware 洋葱链取代继承**：core 只给 onReasoning/onActing/onModelCall 三切面；重能力（压缩、子代理、团队、沙箱、skill 策展、plan mode）全部以 19 个 harness middleware 组装，ReActAgent 本身不扩展。
3. **四段分层**：core（轻）→ harness（coding-agent 能力）→ service（企业控制平面）→ extensions（22 个长尾集成）——企业需求放服务层而非核心抽象（与 Python v2 教训一致：v1 细粒度编排 API 已整体删除）。
4. **权限元数据内嵌工具注解**：readOnly/dangerous*/strict 等在 `@Tool` 上声明，权限引擎按确定性 6 步链求值，bypass-immune 自检保证 BYPASS 模式也不能越过危险工具——Claude Code 式权限模型。
5. **CAS 乐观并发会话**：`saveIfVersion` + `VersionedState` 替代分布式锁管理多节点会话写冲突，`ConflictPolicy` 显式化。
6. **HITL = 终态 + 续跑**：审批不是回调阻塞而是 `PERMISSION_ASKING` 终态返回 + 第二次 call 携 ConfirmResult 校验续跑——天然适配 HTTP/进程边界，服务层再将其升级为跨进程审批协调。
7. **风险**：`ReActAgent` 单类 5401 行（上帝类）；v1→v2 破坏性重构（Memory/pipeline/SessionManager 删除或弃用但 mem 扩展仍挂在弃用 API 上）；maxIters 双默认值（builder 10 / ReactConfig 20）易混淆。

## 7. 跨语言对齐（vs agentscope Python v2.0.8 @ b82253ba）

对照方法：Python `src/agentscope/` 顶层目录逐个与 Java 模块映射；「已对齐」= 语义等价实现，「部分」= 有实现但能力面差，「缺失」= Java 侧无对应。

| 维度 | Python (v2.0.8) | Java (v2.0.3-SNAPSHOT) | 对齐 |
|---|---|---|---|
| Agent 抽象 | 单一 `Agent` 类 + `ReActConfig`（`agent/_agent.py#L117`，ReAct 行为配置化） | `ReActAgent` 类 + middleware chain（`ReActAgent.java#L215`） | **已对齐**（同构：config vs middleware，均弃继承树） |
| 执行循环 | `reply_stream→_reply_impl` while 循环，`max_iters` 默认 50、结构化输出 grace 5 轮 | executeIteration 循环，maxIters builder 默认 10（ReactConfig 20）、summarizing 兜底、gotoReasoning | **部分**（Java 无 grace_iters 等价物；但多 native responseFormat 直连路径） |
| 模型接入 | 10 vendor（含 deepseek/moonshot/volcengine/xai/openai_response）+ `embedding/` + `tts/` 顶层包 | 5 vendor 扩展 + starter；无 embedding/tts 包 | **部分**（Java 少 5 家与语音/嵌入栈；HTTP/WS 传输层更工程化） |
| 上下文工程 | `compress_context` 内建于 Agent：trigger/reserve ratio、摘要、回退截断、**自我压缩工具**、图片降级 HintBlock | harness `ConversationCompactor`（token/条数触发、增量摘要、专用模型）+ `ToolResultEviction` | **部分**（Java 无自我压缩工具；媒体降级 ⚠️待确认） |
| 记忆 | `middleware/_longterm_memory/`（agentic/mem0/reme）**非弃用**，正式中间件 | core memory 包整体 @Deprecated；mem0/bailian/reme 三扩展挂在弃用 API 上 | **部分**（Java 有 bailian 独有后端，但核心抽象未接续） |
| RAG | `rag/` 自带 parser（word/ppt）+ 向量库集成 | core `Knowledge` 接口 + 5 外部引擎委托扩展（bailian/dify/haystack/ragflow/simple） | **部分**（Java 无自建 ingestion/向量层，dify/haystack/ragflow 委托是 Java 独有取法） |
| 工具系统 | `Toolkit` docstring→schema、分组、MCP | `@Tool` 注解→schema、ToolGroupManager+元工具、MCP 三传输、dangerous 元数据 | **已对齐**（Java 元数据更治理向） |
| Skill | `skill/`（SKILL.md、渐进披露） | core `SkillBox`/`SkillRegistry` + harness curator + git/mysql/pg 仓库扩展 + 仓库根 SKILL.md | **已对齐**（Java 仓库后端更多） |
| 规划推理 | 结构化输出动态注入 `_GenerateStructuredOutput` 工具 | native responseFormat + `generate_response` 工具双路径 + TodoTools + PlanModeMiddleware | **已对齐**（Java 多 native 直连与 plan mode） |
| 编排 | `pipeline/GoalPipeline`（executor+verifier 循环验证）+ **`sop/` 引擎**（步骤化 SOP、断点续跑、attempt 预算） | ❌ 无 GoalPipeline/SOP 对应；subagent task/team/PeriodicGate 替代 | **缺失**（Python 高层模式未同步到 Java） |
| 多 Agent | `agent/_a2a_agent.py`（客户端适配）+ app 层 sub-agent/team 工具 + examples/a2a | A2A client+**server** 扩展 + starter + 跨节点 RemoteSubagentStub/SubagentRegistry + team + admin/nacos/higress 注册 | **已对齐/超出**（Java 有 server 端与注册中心生态） |
| 持久化 | `AgentState` + app 层 `SessionService`（SQL/Redis） | `AgentStateStore` CAS + 7 存储后端 + LegacyStateLoader + 沙箱快照 | **已对齐/超出**（Java 后端矩阵更大） |
| HITL | 全事件化 parked（RequireUserConfirmEvent + Result 事件重入） | interrupt + PERMISSION_ASKING 终态 + 二次 call 送达 + dataplane 跨进程协调 + AG-UI | **已对齐**（语义等价：Python 事件重入 vs Java 终态+续跑） |
| 观测 | OTEL `TracingMiddleware` + `ReplyBudgetControlMiddleware`（token 预算） | OtelTracingMiddleware + Hook 事件面 + AgentTrace + Studio；**无 budget middleware** | **部分**（预算控制缺） |
| 安全 | `permission/` 5 模式（DEFAULT/ACCEPT_EDITS/EXPLORE/BYPASS/DONT_ASK，`_types.py`） | `PermissionEngine` 同 5 模式 + 6 步显式求值链 | **已对齐**（Java 求值顺序文档化更细） |
| 部署运行时 | `app/` FastAPI 工厂（session/chat/hub/kb/workspace/model/credential/schedule router）+ MessageBus(in-memory/Redis) | 三进程 service + React 台 + Helm + aistio(Go) + 11 Spring starter + quartz/xxl-job + 5 IM 渠道 | **已对齐/超出**（Java 服务化更重、更贴 Spring 企业栈） |
| 管理平面 | app 层 hub/admin router + tui/console | service frontend + admin starter CommandPlane + scheduler 自托管 Web + Studio | **已对齐/超出** |
| Python 独有 | `realtime/`（语音多模态 agent）、`tui/`、`console/`、`sop/`、`pipeline/GoalPipeline`、embedding/tts | — | **缺失**（Java 无实时语音/终端交互层） |
| Java 独有 | — | `training` 扩展（TrainingRunner/TrainingRouter/AgentCloner/RunRegistry，RL 训练运行面）、aistio Go 连接器、Spring starter 矩阵、paw/codingagent 示例 | — |
| form（表单填充） | ❌ v2 已删（v1 FormFillingAgent；src 无 form 模块，已验证） | ❌ 同样无 | **一致**（两侧均已放弃该 v1 概念） |

**总评**：两侧共享设计语言（事件驱动、权限引擎、middleware、HITL 语义、v1 大删减），但演进重心分叉——Python 先行落地新抽象（SOP/GoalPipeline/内建压缩/realtime/预算控制），Java 侧强在企业工程化（存储矩阵、Spring starter、三进程控制平面、跨节点子代理、RL 训练扩展）。凡 Python 有 Java 无处多为能力面差而非架构差。
