# 维度 12：观测评估（Observability & Evaluation）

> 本维度回答：**跑起来之后看得见什么（tracing/span/指标/成本）、跑完之后怎么评（eval）、开发时用什么看（dev UI）**。观测侧已成分化格局：OTel（含 gen_ai 语义约定）是 Java/企业栈的共识标准（9 家直埋），LangChain 系押注自有 callback 体系→LangSmith SaaS，openai-agents 用自有 trace 树+批量外发自家端点——标准派与商业生态派泾渭分明。**默认外发行为是隐私硬问题**：17 家中仅 openai-agents（trace 数据送 api.openai.com）与 crewai（匿名 OTLP 送 telemetry.crewai.com）默认开启外发。评估侧是全场最大缺口：完整开源 eval 工具链只有 adk-python 与 llama_index 两家，多数框架零 eval；dev UI 呈现"开源本地台 / 嵌入式调试服务器 / 闭源平台"三形态。

## 12.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| langchain | ✅ | callbacks/tracers 体系贯穿全 Runnable，LangChainTracer 上报 LangSmith（需 env+key），TracePolicy 脱敏；standard-tests 独立包；eval 平台为托管 LangSmith | libs/core/langchain_core/tracers/langchain.py#LangChainTracer(:134，:232 tracing_context 门控已核实)；libs/standard-tests/langchain_tests/ |
| langgraph | 🟡 | 内置 7 种 stream mode + debug 事件；分布式 tracing 依托 langchain-core callback→LangSmith；核心无 OTel | libs/langgraph/langgraph/types.py#StreamMode(:122)；pregel/main.py:2772；OTel rg 零命中 |
| langgraph4j | 🟡 | NodeHook/EdgeHook 三段拦截为统一观测点 + 官方 langgraph4j-opentelemetry 模块（span 树 + 内部 OTLP collector）；无 eval | langgraph4j-core/.../hook/NodeHook.java；langgraph4j-opentelemetry/.../OTELWrapCallTraceHook.java |
| langchain4j | ✅ | 三层 listener（模型/AiService 事件/agent）+ Micrometer Observation + OTel GenAI 指标名 + HTML 报告；无 eval 框架 | langchain4j-core/.../model/chat/listener/ChatModelListener.java；langchain4j-agentic/.../observability/AgentListener.java；langchain4j-micrometer-metrics/（OTelGenAi*） |
| deepagents | 🟡 | tracing 继承 LangSmith callback（ls_integration 元数据）；全自研中间件默认 TracePolicy 脱敏；evals 独立包（Harbor 基准 0.0.1） | libs/deepagents/deepagents/graph.py:969-978；middleware/filesystem.py:1743；libs/evals/ |
| agent-framework | ✅ | OTel 三层遥测（Agent/Chat/Embedding）默认叠加 + configure_otel_providers + feature usage 位图进 User-Agent（ADR-0033）+ core 评估模型 + Foundry evals | python/packages/core/agent_framework/observability.py#AgentTelemetryLayer(:2275)、#configure_otel_providers(:1592)；_evaluation.py#EvalItem(:183) |
| adk-python | ✅ | OTel 全链路（OTLP + sqlite_span_exporter + node_tracing）+ callback 列表化 + 完整 eval 框架（轨迹/LLM-as-judge/rubric/用户模拟）+ adk eval/conformance CLI | src/google/adk/telemetry/setup.py、sqlite_span_exporter.py#SqliteSpanExporter(:78，已核实)；evaluation/eval_set.py#EvalSet(:24)、llm_as_judge.py#LlmAsJudge(:69，已核实)；cli/cli_tools_click.py:1252 |
| adk-java | ✅ | OTel span（invoke_agent/execute_tool）+ 7 个 histogram 指标 + Plugin 体系（BigQuery 审计）；**eval 端点全部 501 stub** | core/.../telemetry/{Instrumentation,Metrics}.java；plugins/agentanalytics/BigQueryAgentAnalyticsPlugin.java；dev/.../EvaluationController.java（NOT_IMPLEMENTED 已核实） |
| openai-agents-python | ✅ | 自有 trace 树（trace + 10 类 span）+ BatchTraceProcessor **默认批量外发 api.openai.com/v1/traces/ingest**（5s）+ 细粒度 Usage + lifecycle hooks；无 OTel exporter、无 eval | src/agents/tracing/processors.py#BackendSpanExporter(:44，端点:45 已核实)、#BatchTraceProcessor(:541，schedule_delay 5.0 已核实)；span_data.py |
| claude-agent-sdk-python | 🟡 | OTEL 仅做 traceparent 透传（span 生成在 CLI 二进制）+ stderr 回调 + usage/cost/rate-limit/terminal_reason 结构化进消息流；无 tracing 抽象无 eval | _internal/transport/subprocess_cli.py#connect（propagate.inject :817-841）；types.py#ResultMessage、#ModelUsage(:1293) |
| crewai | ✅ | 统一事件总线（70+ 事件类型）+ **默认开启 OTLP 匿名遥测 telemetry.crewai.com:4319** + 付费平台 trace 上传 + 实验性评估（弱） | lib/crewai/src/crewai/events/event_bus.py#CrewAIEventsBus(:95)；lib/crewai-core/src/crewai_core/telemetry.py:45/:269-270（端点与关闭开关已核实）；experimental/evaluation/ |
| dify | ✅ | OpsTraceManager 按租户可插拔 trace（langfuse/langsmith/opik/arize + OTel 核心内置 ENABLE_OTEL）+ 运行/节点执行落库 + 控制台；eval 仅 hit-testing/标注 | api/core/ops/ops_trace_manager.py#OpsTraceManager；api/core/workflow/workflow_entry.py:184-185（ENABLE_OTEL 已核实）；services/hit_testing_service.py |
| llama_index | ✅ | instrumentation 基座外置独立包（Dispatcher/Span）+ RAG 领域事件留 core + OTel 桥集成包 + 10 个 callbacks 集成；**eval 全家桶 core 内置** | llama-index-instrumentation/src/.../dispatcher.py#Dispatcher(:50)；core/evaluation/（faithfulness 等）；integrations/observability/llama-index-observability-otel/ |
| agentscope | ✅ | TracingMiddleware OTel 全链路（reply/model/tool span，gen_ai semconv，未配置零开销短路）+ 29 事件类全链路流；无 eval | src/agentscope/middleware/_tracing/_trace.py#TracingMiddleware(:117)、_attributes.py；event/_event.py |
| agentscope-java | ✅ | OtelTracingMiddleware（Reactor ContextPropagationOperator 上下文传播）+ Tracer SPI + 12 类 Hook 事件 + harness AgentTrace + Studio 对接；无 eval | agentscope-core/.../tracing/OtelTracingMiddleware.java(:72)；extensions/agentscope-extensions-studio/.../StudioClient.java |
| spring-ai-alibaba | ✅ | graph/node/edge/metric 四组 Micrometer 观测（核心）+ starter 装配 + chat model 观测约定；评估仅 admin（独立构建 🔶） | spring-ai-alibaba-graph-core/.../observation/graph/GraphObservationDocumentation.java；spring-boot-starters/spring-ai-alibaba-starter-graph-observation/ |
| spring-ai | ✅ | Micrometer 全链路观测、属性直用 OTel gen_ai.* semconv（micrometer-otel 桥）+ 轻量 LLM-as-judge（Evaluator SPI/Relevancy/FactChecking） | spring-ai-model/.../chat/observation/ChatModelObservationDocumentation.java；spring-ai-commons/.../observation/conventions/AiObservationAttributes；.../evaluation/RelevancyEvaluator |

评级沿用档案；openai-agents/crewai/adk/dify/claude-sdk 的外发端点、开关、stub 状态均已二次核实。

## 12.2 实现方式深析

### 阵营一：OTel 原生直埋（标准派，9 家）

**微软 agent-framework** 是"OTel 一等公民"的范本：`Agent = AgentMiddlewareLayer + AgentTelemetryLayer + RawAgent` 洋葱叠层（_agents.py:1794）——遥测是可剥离 mixin，默认在、要裸机用 RawAgent；三层遥测覆盖 Agent/Chat/Embedding（含嵌入调用，少见），`configure_otel_providers`（observability.py:1592）一键装配。独有设计：**feature usage 位图进 User-Agent**（ADR-0033，各包 _feature_usage.py FeatureIndex）——框架版本+启用特性随每次模型 API 请求头外发至 provider，轻量到无后台线程。

**adk-python/adk-java（同构双实现）**：Python 侧 telemetry/setup.py 标准 OTLP traces+metrics 初始化（BatchSpanProcessor），`SqliteSpanExporter` 本地落盘（无后端也能留痕），`node_tracing` 图节点级 span，CLI `adk telemetry enable/disable/status` 开关化；Callbacks 六切入点（before/after × agent/model/tool）**接受列表形式**叠加。Java 侧 `invoke_agent <name>`/`execute_tool <name>` span（Instrumentation.java:185/255）+ 7 个 histogram（agent/tool 时长、请求响应大小、workflow 步数）+ dev 模块 ApiServerSpanExporter；加分项是 **BigQueryAgentAnalyticsPlugin**（BigQuery+GCS 落审计数据）。**两版 eval 能力天差地别**：Python 是全场最完整开源 eval（见下节），Java 的 dev EvaluationController 三个端点全部 501/log.warn "not implemented"（已核实）——API 形状先行、实现缺席。

**agentscope 双语**：Python `TracingMiddleware`（middleware/_tracing/_trace.py:117）reply/model-call/tool 三级 span，遵循 gen_ai 语义约定（SpanAttributes/OperationNameValues），**未配置时零开销短路**（不装 OTel 不付代价），OTLP exporter 在主依赖；观测的第二载体是 29 个 pydantic 事件类（Start/Delta/End 三段式）——流式即观测。Java 侧 OtelTracingMiddleware 用 Reactor `ContextPropagationOperator` 解决响应式流的上下文传播（异步链路 trace 续接是工程难点），Tracer SPI + NoopTracer 降级；另有 harness AgentTraceMiddleware/TranscriptMiddleware 与 Studio 扩展对接。

**spring-ai / spring-ai-alibaba / langchain4j（Java 企业栈三家）**：spring-ai 的属性命名直接采用 `gen_ai.operation.name`/`gen_ai.system`/`gen_ai.request.model` 标准 semconv（AiObservationAttributes 枚举），Micrometer 一层桥接 OTel——企业 APM（Prometheus/Jaeger）零适配；ChatClient/ChatModel/Advisor/Tool/VectorStore/Embedding 各有 Observation 体系。spring-ai-alibaba 在图引擎层加厚：graph/node/edge/metric 四组 ObservationDocumentation——**边执行也有埋点**（17 家唯一到 edge 粒度）。langchain4j 三层监听（ChatModelListener 模型层 / core observability 的 AiService 全套事件含 ToolCompensated/GuardrailExecuted / agentic AgentListener）+ micrometer-metrics 模块按 **OTel GenAI 语义约定的指标名**输出 + HtmlReportGenerator 事后 HTML 报告（非交互但零依赖）。

**langgraph4j**：观测点即横切底座——NodeHook/EdgeHook 各三段（BeforeCall/AfterCall/WrapCall），重试/OTel/技能注入共用同一拦截面；官方 langgraph4j-opentelemetry 模块提供 OTELWrapCallTraceHook（span 树）+ 内置 OTLP collector（OTELInternalHttpCollector，测试/演示可自收）。

**dify**：双轨——核心内置 OTel（ENABLE_OTEL 或插件开关时挂 ObservabilityLayer，workflow_entry.py:184-185 已核实），以及平台级的 **OpsTraceManager 按租户可插拔 trace 提供者**（配置加密存储 + LRU 解密缓存 + legacy/unified 双注册表）：langfuse/langsmith/opik/arize-phoenix 独立包 + 异步落盘任务——"观测后端是租户配置而非部署选择"是平台形态独有的设计。

### 阵营二：自有 callback/listener 体系 + 商业后端（LangChain 系）

**langchain/langgraph/deepagents**：观测=langchain-core callback 体系（BaseCallbackHandler/CallbackManager 贯穿所有 Runnable），`LangChainTracer`（tracers/langchain.py:134）POST 到 LangSmith endpoint——**但默认不外发**：:232 `get_tracing_context().get("enabled") is False` 即跳过（已核实），需 LANGSMITH_TRACING env + API key 显式开启。langgraph 侧的自有观测是 7 种 stream mode（values/updates/checkpoints/tasks/debug/messages/custom，types.py:122）+ StreamWriter 节点内自定义事件——面向调用方实时观测而非事后 tracing；`TracePolicy`（types.py:533，定义在 langgraph、langchain 提供 configure_trace_policy 进程级默认）控制 trace 载荷策略。deepagents 加厚：`ls_integration="deepagents"` + 子代理 `ls_agent_type=subagent` 元数据，且**全部自研中间件默认 `TracePolicy(process_inputs=omit_payload)` 脱敏**——工具入参（含文件内容）默认不进 trace。核心仓无 OTel（rg 零命中），跨厂商标准缺席是明确押注：生态绑定 LangSmith。

### 阵营三：自有 trace 格式 + 自家 ingest 端点（openai-agents）

**openai-agents-python**：内建完整自有 trace 模型——trace + 10 类 span（Agent/Task/Turn/Function/Generation/Response/Handoff/Guardrail/Custom/Transcription，span_data.py），`BatchTraceProcessor` 批量缓冲 **5 秒定时刷新**（processors.py:553 schedule_delay=5.0，已核实），默认 `BackendSpanExporter` 上传 `https://api.openai.com/v1/traces/ingest`（:45，已核实）——**开箱即把 trace 数据送出本机到 OpenAI**，需 `set_tracing_disabled(True)` 或 `set_trace_processors()` 显式接管；隐私开关 `trace_include_sensitive_data`、`workflow_name/trace_id/group_id/trace_metadata` 可控。无 OTel exporter（全库 rg opentelemetry=0），扩展点是 TracingProcessor/TracingExporter 协议。这个"私有格式+自家后端"组合与 LangChain→LangSmith 同构，但后者需显式开启、前者默认外发——**默认值的安全语义是两家最大差异**。

### 阵营四：协议透传式（claude-agent-sdk）

**claude-agent-sdk** 的观测边界就是进程边界：可选 otel extra，transport 在 connect 时 `propagate.inject` 把活跃 traceparent 注入 CLI 子进程 env（并清理陈旧 TRACEPARENT/TRACESTATE，best-effort 永不失败，subprocess_cli.py:817-841）——**span 生成在闭源 CLI 二进制内**，SDK 只保证分布式追踪上下文不断链。SDK 侧可观测的是**协议本身**：usage/cost（ResultMessage.total_cost_usd/model_usage，ModelUsage 含 per-model tokens/缓存/costUSD/provider）/rate_limit 事件/terminal_reason 全部结构化进消息流，`include_hook_events` 可把 hook 生命周期也变成流消息——"可观测即消息协议"的极端形态。无 callback 体系、无 eval。

### span 粒度与指标对照

| 粒度 | 有正式埋点的框架（代表证据） |
|---|---|
| LLM 调用 | 全员（gen_ai semconv 直埋：adk/agentscope×2/spring-ai×2/langchain4j/MS；自有：langchain on_llm_start、openai Generation/Response span、crewai llm 事件 6 类、claude usage 帧） |
| 工具执行 | adk execute_tool span、agentscope tool span、MS FunctionInvocation、openai Function span、langchain4j ToolExecuted 事件、crewai tool_usage 9 事件、saa edge 级 |
| **图节点/边** | adk node_tracing、saa node+edge Observation（唯一到边）、langgraph stream tasks/debug mode、langgraph4j NodeHook/EdgeHook、MS superstep_started/completed 事件、dify WorkflowNodeExecution 落库 |
| **多 agent 传递** | openai Handoff span、agentscope-java AgentTrace/Transcript、deepagents ls_agent_type=subagent、langchain run.subagents（SubagentTransformer）、MS agent span 嵌套、crewai A2A 32 事件类型 |

**token/成本计量**：消息流内结构化回报（claude 最细：per-model costUSD/缓存明细/RateLimitEvent/上下文窗口；dify total_price/currency 落 Message 表 + QuotaManagedModelInstance 配额结算；crewai UsageMetrics 聚合 + completion_cost）；观测系统聚合（MS UsageDetails+add_usage_details 跨层累加、spring-ai UsageAccumulator 跨工具轮累计、agentscope ChatUsage 含 cache tokens、agentscope-java ChatUsage **无 cost 计价**）；openai Usage 最全维度（requests/input/output/total + cached/cache_write/reasoning + request_usage_entries 按请求明细供成本核算）。langgraph 本体无 usage 对象（属 langchain-core 域）。成本看板对接：闭源平台（LangSmith/Foundry/AMP）或自建（deepagents dcode CostTrackingMiddleware 在外围包）。

### 评估（eval）框架——谁有开源可用的工具链

| 框架 | eval 能力 | 证据 |
|---|---|---|
| **adk-python（最全）** | EvalSet/EvalCase 数据集 + 轨迹评估（trajectory_evaluator 对比期望工具序列）+ 终态匹配（final_response_match_v1/v2）+ LlmAsJudge（AutoRater/rubric_scores）+ safety/hallucinations 评估器 + **用户模拟器**（LLM 驱动多轮模拟 + 预置 persona）+ `adk eval` CLI + GCS/local 结果管理 + `adk conformance record/test` 行为回放 | evaluation/ 目录（eval_set.py:24、llm_as_judge.py:69、simulation/）；cli_tools_click.py:1252/:1643/:568 |
| **llama_index（RAG 最全）** | faithfulness/relevancy/correctness/answer_relevancy/context_relevancy/pairwise/semantic_similarity/dataset_generation/benchmarks/retrieval 指标全家桶**内置主包** | llama-index-core/llama_index/core/evaluation/ |
| agent-framework | core 评估模型（EvalItem/EvalResults/ConversationSplitter/ExpectedToolCall）+ Foundry evals（ADR-0023，平台侧）；dotnet Workflows/Evaluation/ | python/packages/core/agent_framework/_evaluation.py:183/:374；packages/foundry/.../_foundry_evals.py |
| spring-ai | Evaluator SPI + RelevancyEvaluator（YES/NO 裁决）+ FactCheckingEvaluator（需 WireMock 文档）——轻量 LLM-as-judge，无 dataset/批量 harness | spring-ai-commons/.../evaluation/；spring-ai-client-chat/.../chat/evaluation/ |
| spring-ai-alibaba | 仅 admin 的 EvaluatorDO/EvaluatorTemplateDO/ExperimentResultDO（🔶 独立构建、发布方式 ⚠️） | spring-ai-alibaba-admin/server-start/.../ |
| deepagents | evals 独立包 0.0.1：Harbor 基准适配（langsmith/failure/stats）+ 雷达图 + tau3 子集 | libs/evals/ |
| crewai | experimental/evaluation（AgentEvaluator/run_experiment 基线对比）+ `crewai train`（多迭代 LLM 打分调提示词）/`crewai test`——OpenAI 评分模型路线，弱 | lib/crewai/src/crewai/experimental/evaluation/；lib/cli 的 train/test 子命令 |
| langchain | standard-tests 是集成测试套件（非 eval）；数据集/评估走托管 LangSmith（开源侧无 runner） | libs/standard-tests/ |
| dify | hit-testing（检索命中测试）+ 标注/feedback；无批量评测 runner ❌ | api/services/hit_testing_service.py |
| 其余 8 家 | 无 eval/dataset 抽象 ❌（langgraph/langgraph4j/langchain4j/openai-agents/claude-sdk/agentscope×2——多为 rg 零命中级缺失） | — |

### dev UI / 调试面

| 形态 | 框架 | 证据 |
|---|---|---|
| 开源本地控制台 | **adk web**（内置编译好的 React 前端：会话/事件/trace 浏览 + built_in_agents 辅助 agent）；**dify 控制台**（Next.js 全功能：应用/知识库/插件市场/工作区 Skill/成员 RBAC）；**agentscope-java service frontend**（React 管理台含 e2e 测试）+ admin starter CommandPlane | cli/cli_tools_click.py:2121、cli/browser/；web/app/(commonLayout)/；agentscope-service/frontend/src/ |
| 嵌入式调试服务器 | **langgraph4j studio**（jetty/springboot 宿主、SSE 流式、内嵌 webui viewer、JSON DSL 图导出）；**spring-ai-alibaba studio**（内嵌 agent-chat-ui 静态资源 + threads/resume REST + YAML 热重载）；**MS devui**（beta 官方包：`devui` CLI + React 前端 + OpenAI 兼容端点 + tracing 页，可当 playground） | studio/{base,jetty,springboot}/；spring-ai-alibaba-studio/；python/packages/devui/agent_framework_devui/_cli.py:149 |
| 闭源平台 UI | LangGraph Studio/LangSmith（langgraph dev 本地 server 开源、UI 与生产 server 属 Platform）；CrewAI AMP（OSS 侧仅 TUI：crew_run_tui/checkpoint_tui/memory_tui——注意 lib/devtools 是**内部文档工具非产品**，纠正常见误称）；LlamaCloud | libs/cli（dev server）；lib/cli/src/crewai_cli/crew_run_tui.py |
| 终端/无 UI | openai-agents（`repl.py#run_demo_loop` REPL 调试循环）；agentscope（console/ 终端渲染 + examples/web_ui React 示例级）；claude-sdk（转录磁盘 JSONL 可直读 + sessions.py 离线枚举 API）；langchain4j（HtmlReportGenerator 事后报告）；adk-java（dev server REST 7 Controller **无 UI** ⚠️是否有外部前端项目未证实）；spring-ai（观测交 Micrometer 后端呈现） | — |

## 12.3 跨语言对齐

| 对 | Python 侧 | Java 侧 | 差异判断 |
|---|---|---|---|
| langgraph ↔ langgraph4j | 观测=7 种 stream mode + debug 事件；tracing 押注 langchain-core callback→LangSmith；核心无 OTel | NodeHook/EdgeHook 统一拦截面 + **官方 langgraph4j-opentelemetry 模块**（span 树 + 内部 OTLP collector） | **Java 超出**：OTel 官方模块是 Python 核心明确缺席的能力；Python 的 stream mode 实时观测 Java 无完全等价物 |
| adk-python(2.9) ↔ adk-java(1.9) | OTel（OTLP + sqlite 落盘 + node_tracing + telemetry CLI）+ callback 列表化 + plugins（auto_tracing 等 4+）；**eval 巨型模块 + CLI** | OTel span + 7 指标对齐；Plugin 单接口 14 钩子 + **BigQuery 审计插件**（Java 独有）；**eval 三端点全 501 stub** | 观测**已对齐**（Java 的 BigQuery 审计是加分项）；eval 是**双语最大缺口**——同为官方实现，Python 全工具链 vs Java 纯 stub |
| agentscope ↔ agentscope-java | TracingMiddleware（gen_ai semconv、未配置零开销）+ 29 事件类 + ReplyBudgetControlMiddleware（token 预算治理）；无 eval | OtelTracingMiddleware（Reactor 上下文传播）+ Tracer SPI + 12 类 Hook + AgentTrace/Transcript + Studio 扩展；无 eval | **语义对齐**（OTel+事件双载体）；Python 多预算治理、Java 多 Studio 可视化与 transcript；**双侧一致无 eval** |

## 12.4 取舍与趋势

1. **OTel 已赢下标准之争的一半**：9 家（MS/adk×2/agentscope×2/spring-ai×2/langchain4j/langgraph4j + dify 内置开关）直埋 OTel，其中 agentscope×2、spring-ai、langchain4j 明确对齐 gen_ai semconv；另一半是商业生态绑定——LangChain 系走自有 callback→LangSmith、openai-agents 走自有 trace 树→自家 ingest 端点、claude-sdk 只透传 traceparent（span 在闭源 CLI）。选型时"观测数据出口"几乎等于"商业立场"。
2. **默认外发是必须写进采购清单的隐私事实**：仅 openai-agents（trace→api.openai.com/v1/traces/ingest，5s 批量，默认开）与 crewai（匿名 OTLP→telemetry.crewai.com:4319，默认开，OTEL_SDK_DISABLED/CREWAI_DISABLE_TELEMETRY 关闭）两家默认把数据送出本机；MS 的 feature usage 位图随 User-Agent 外发至模型 provider；LangSmith 需 env+key 显式开启（tracers/langchain.py:232 门控已核实）。企业引入 openai-agents/crewai 的第一件事是关遥测。
3. **span 粒度从 LLM/工具标配下沉到图节点、边、多 agent 传递**：saa 做到 edge 级 Observation、adk node_tracing、MS superstep 事件、openai Handoff span、deepagents/langchain 的 subagent 观测句柄——随着编排复杂化，"节点间传递"本身成为需要观测的一等事件。
4. **eval 是全场最大空白，且开源完整度与框架热度不成正比**：完整工具链只有 adk-python（轨迹+judge+模拟+CLI+conformance）与 llama_index（RAG 指标 core 内置）；MS/core 模型 + Foundry 平台、spring-ai 轻量 judge 是中间态；langgraph/openai-agents/claude-sdk/agentscope×2 等热门框架零 eval——评估要么上 SaaS（LangSmith/Foundry），要么自建。adk-java 的 501 stub 说明 eval 也是双语对齐中最难同步的部分。
5. **dev UI 三形态对应三种商业化路径**：开源本地台（adk web、dify 控制台、agentscope-java frontend——观测面即产品面）拉新；嵌入式调试服务器（langgraph4j studio、saa studio、MS devui）服务存量栈；闭源平台 UI（LangGraph Studio、CrewAI AMP、LlamaCloud）把观测做付费墙——观测数据天然是"截图级"的销售素材，平台化框架普遍从观测面切入商业化。
6. **成本计量位置分化反映架构位置**：终端形态框架把 cost 塞进消息流（claude 的 total_cost_usd/RateLimitEvent 最细）；服务形态落业务表并接配额（dify total_price+quota）；库形态交观测系统聚合（MS/spring-ai 的 usage 累加器）——计费能力与框架离钱的距离成正比。
