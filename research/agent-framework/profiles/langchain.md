# langchain（Python monorepo）框架档案

> 基线：~/develop/opensource/langchain @ 348c9dc572 2026-09-11；版本：`langchain` 1.4.0（libs/langchain_v1）、`langchain-core` 1.6.3（libs/core，tag core 1.6.3）、`langchain-classic` 1.0.8（libs/langchain）、`langchain-text-splitters` 1.1.2、`langchain-tests` 1.1.9（libs/standard-tests）。

## 1. 定位

LangChain 是 LLM 应用的**组件框架**（库，非平台），目标用户是自建应用的 Python 开发者。1.x 的核心命题：**agent = LangGraph 图 + 中间件**——`create_agent` 把 model/tools/system_prompt/middleware 组装成一个编译后的 LangGraph 图，横切能力（摘要、HITL、PII、沙箱、限流、回退）全部以 `AgentMiddleware` 钩子形式注入并被编译为图节点。仓库是 monorepo：抽象层在 langchain-core，agent 组装在 langchain 1.x，0.x LCEL/chain 兼容层独立为 langchain-classic，具体模型/向量库接入拆到 libs/partners 下 16 个集成包。执行引擎、持久化、工具执行节点全部**透传 langgraph**（pyproject 硬依赖 `langgraph>=1.2.11,<1.3.0`），本仓库不含图引擎与部署运行时。

## 2. 仓库结构与核心包

| 包目录 | 包名 | 版本 | 角色 |
|---|---|---|---|
| libs/core | langchain-core | 1.6.3 | 抽象基座：消息/提示词/模型/工具/检索/缓存/限流/callbacks/LCEL Runnable |
| libs/langchain_v1 | langchain | 1.4.0 | 1.x agent 组装：create_agent + middleware 全家桶 + MCP；依赖 langgraph>=1.2.11 |
| libs/langchain | langchain-classic | 1.0.8 | 0.x 兼容层：Chain/AgentExecutor/memory/legacy retrievers；依赖 core，不被 v1 依赖 |
| libs/partners/* | langchain-openai、-anthropic、-chroma、-qdrant 等 | 各自独立 | 16 个官方集成包（模型/向量库） |
| libs/standard-tests | langchain-tests | 1.1.9 | 集成包标准测试套件 |
| libs/text-splitters | langchain-text-splitters | 1.1.2 | 文档切分 |
| libs/model-profiles | langchain_model_profiles | — | 模型能力元数据（ModelProfile）数据包 |

langchain 1.x 对 langgraph 的依赖边界（rg 统计 libs/langchain_v1）：`langgraph.runtime`×11、`langgraph.types`×10（interrupt/Command/TracePolicy）、`prebuilt.tool_node`×5（ToolNode 全套 re-export）、`channels`、`store.base`、`cache.base`、`graph.state`、`stream.*`。即：**图引擎、Runtime、HITL interrupt、ToolNode、checkpointer/store/cache 类型、TracePolicy 均为 langgraph 提供**。证据：libs/langchain_v1/langchain/tools/tool_node.py（纯 re-export）、libs/langchain_v1/langchain/agents/middleware/_trace_policy.py#L14（`from langgraph.types import TracePolicy`）。

## 3. 核心抽象清单

| 符号 | 路径 | 一句话说明 |
|---|---|---|
| `create_agent` | libs/langchain_v1/langchain/agents/factory.py#L840 | 组装 model/tools/middleware 成 `CompiledStateGraph`，1.x 唯一 agent 工厂 |
| `AgentMiddleware` | libs/langchain_v1/langchain/agents/middleware/types.py#L385 | 中间件基类，6 类钩子（before/after_agent、before/after_model、wrap_model_call、wrap_tool_call） |
| `AgentState` | libs/langchain_v1/langchain/agents/middleware/types.py#L349 | messages/structured_response + 中间件 state_schema 合并 |
| `SummarizationMiddleware` | libs/langchain_v1/langchain/agents/middleware/summarization.py#L232 | 上下文压缩，TriggerClause 组合触发条件 |
| `HumanInTheLoopMiddleware` | libs/langchain_v1/langchain/agents/middleware/human_in_the_loop.py#L219 | 按工具名 interrupt 审批，approve/edit/reject/respond 四种决策 |
| `ShellToolMiddleware` | libs/langchain_v1/langchain/agents/middleware/shell_tool.py#L518 | 沙箱化 shell 工具，Host/Docker/Codex 三种执行策略 |
| `PIIMiddleware` / `ContextEditingMiddleware` | libs/langchain_v1/langchain/agents/middleware/pii.py#L492 / context_editing.py#L187 | 脱敏 / 敏感内容事后编辑 |
| `MCPAdapter` | libs/langchain_v1/langchain/mcp/adapter.py#L125 | 基于 fastmcp 的 MCP 客户端适配器 |
| `init_chat_model` | libs/langchain_v1/langchain/chat_models/base.py#L195 | 字符串路由到 provider 包（`"openai:gpt-5.5"`） |
| `BaseChatModel` | libs/core/langchain_core/language_models/chat_models.py#L284 | 模型接入抽象（含 rate_limiter、缓存钩子） |
| `ModelProfile` | libs/core/langchain_core/language_models/model_profile.py#L13 | 模型能力元数据（经 `model.profile` 暴露） |
| `ChatPromptTemplate` | libs/core/langchain_core/prompts/chat.py#L794 | 提示词模板（LCEL Runnable） |
| `BaseTool` / `InjectedToolArg` | libs/core/langchain_core/tools/base.py#L433 / #L1726 | 工具抽象 / 注入参数不进 LLM schema |
| `BaseCache` / `BaseRateLimiter` | libs/core/langchain_core/caches.py#L32 / rate_limiters.py#L11 | LLM 响应缓存 / 请求限流抽象 |
| `BaseRetriever` / `VectorStore` | libs/core/langchain_core/retrievers.py / vectorstores/base.py#L43 | RAG 检索抽象 |
| `LangChainTracer` | libs/core/langchain_core/tracers/langchain.py#L134 | LangSmith 上报 tracer |
| `Chain` / `AgentExecutor` | libs/langchain/langchain_classic/chains/base.py#L52 / agents/agent.py#L1012 | 0.x legacy chain 与 ReAct 执行器 |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | BaseChatModel + 字符串路由 init_chat_model + 缓存/限流/用量/fallback 全有，具体 provider 在 partners | libs/core/langchain_core/language_models/chat_models.py#BaseChatModel；libs/langchain_v1/langchain/chat_models/base.py#init_chat_model |
| 2 | 上下文工程 | ✅ | 提示词模板、动态 system prompt、token 触发摘要中间件、消息历史全内置 | libs/langchain_v1/langchain/agents/middleware/summarization.py#SummarizationMiddleware；libs/core/langchain_core/prompts/chat.py#ChatPromptTemplate |
| 3 | 记忆 | 🟡 | 会话记忆透传 langgraph checkpointer、跨线程透传 BaseStore，摘要作短时记忆；无长期记忆/画像抽象 | libs/langchain_v1/langchain/agents/factory.py#create_agent（checkpointer/store 参数，类型来自 langgraph） |
| 4 | RAG | ✅ | Retriever/VectorStore/indexing/切分抽象在 core+text-splitters，向量库在 partners | libs/core/langchain_core/retrievers.py#BaseRetriever；libs/core/langchain_core/indexing/api.py#index |
| 5 | 工具系统 | ✅ | BaseTool/@tool/InjectedToolArg 在 core，MCPAdapter 内置，沙箱 shell 中间件；ToolNode 执行透传 langgraph | libs/core/langchain_core/tools/base.py#BaseTool；libs/langchain_v1/langchain/mcp/adapter.py#MCPAdapter |
| 6 | Skill 机制 | ❌ | langchain 1.x 内无 skill/渐进披露抽象（rg 零命中），官方实现在 deepagents 仓库 | —（libs/langchain_v1 全文检索 'skill' 无结果） |
| 7 | 规划推理 | 🔶 | agent 主循环（model→tools）+ 结构化输出 + TodoList/调用限额中间件；无显式 planner/reflection 抽象 | libs/langchain_v1/langchain/agents/middleware/todo.py#TodoListMiddleware；libs/langchain_v1/langchain/agents/structured_output.py |
| 8 | 编排 | 🟡 | agent 编排引擎（StateGraph/Pregel/subgraph）整体透传 langgraph；core 仅组件级 LCEL Runnable 管道 | libs/langchain_v1/langchain/agents/factory.py#L1187（StateGraph 构造）；libs/core/langchain_core/runnables/graph.py |
| 9 | 多 Agent | 🔶 | 仅 `name` 子图嵌套 + `run.subagents` 观测句柄；supervisor/handoff 原语刻意不做，去 langgraph/deepagents 生态 | libs/langchain_v1/langchain/agents/_subagent_transformer.py#SubagentTransformer |
| 10 | 持久化 | 🟡 | checkpointer/store/图执行 cache 参数与类型全透传 langgraph，存储实现在 langgraph 仓库 | libs/langchain_v1/langchain/agents/factory.py#L87（`from langgraph.cache.base import BaseCache`） |
| 11 | HITL | ✅ | HumanInTheLoopMiddleware 按工具 interrupt + when 谓词 + 四种决策；MCP elicitation 也走 interrupt | libs/langchain_v1/langchain/agents/middleware/human_in_the_loop.py#HumanInTheLoopMiddleware |
| 12 | 观测评估 | ✅ | callbacks/tracers 体系内置 LangSmith 上报，TracePolicy 脱敏；标准测试套件独立包；评估平台为托管 LangSmith | libs/core/langchain_core/tracers/langchain.py#LangChainTracer；libs/standard-tests/langchain_tests/unit_tests/chat_models.py#ChatModelUnitTests |
| 13 | 安全治理 | ✅ | PII/上下文编辑/沙箱三策略 shell/SSRF 防护内置；无泛化 guardrail/审计抽象 | libs/langchain_v1/langchain/agents/middleware/pii.py#PIIMiddleware；libs/core/langchain_core/_security/_ssrf_protection.py#validate_safe_url |
| 14 | 部署运行时 | ❌ | v1/core 无 server/fastapi 代码（rg 零命中）；dev server 与平台在 langgraph 仓库及闭源 LangGraph Platform | —（libs/langchain_v1、libs/core 检索 'fastapi\|uvicorn' 无结果） |
| 15 | 管理平面 | ❌ | 无 console/dashboard/租户/计量；观测管理面是托管 LangSmith（文档宣称，非本仓库代码） | — |

## 5. 维度证据明细

### 维度 1：模型接入 ✅
- `BaseChatModel(BaseLanguageModel[AIMessage])`：模型接入根抽象，bind_tools/rate_limiter/stream 均定义于此。【核心】libs/core/langchain_core/language_models/chat_models.py#L284
- `init_chat_model(model, model_provider=...)`：统一字符串接口按前缀路由到 provider 集成包（如 `openai:gpt-5.5` → langchain-openai），contributor 注释维护 provider 映射表。【核心】libs/langchain_v1/langchain/chat_models/base.py#L195
- `ModelProfile`（TypedDict）：模型能力元数据经 `model.profile` 暴露（状态/发布日期/能力项），配套独立数据包 libs/model-profiles（langchain_model_profiles）。【核心】libs/core/langchain_core/language_models/model_profile.py#L13
- `UsageMetadata` 挂在 AIMessage.usage_metadata，merge 时自动累加。【核心】libs/core/langchain_core/messages/ai.py#L104
- `BaseCache`/`InMemoryCache`：LLM 响应缓存抽象（进阶实现在 community 生态）。【核心】libs/core/langchain_core/caches.py#L32
- `BaseRateLimiter`/`InMemoryRateLimiter`：与 BaseChatModel 配合限流。【核心】libs/core/langchain_core/rate_limiters.py#L11
- fallback/retry 双轨：模型级 `ModelFallbackMiddleware`/`ModelRetryMiddleware`（1.x agent）+ LCEL `RunnableWithFallbacks`（0.x 兼容）。【核心】libs/langchain_v1/langchain/agents/middleware/model_fallback.py#L279；libs/core/langchain_core/runnables/fallbacks.py
- 跨 provider 内容块标准化：`messages/block_translators/`（anthropic/bedrock/openai/google_genai 等 9 个翻译器）。【核心】libs/core/langchain_core/messages/block_translators/
- 具体 provider：libs/partners 下 16 包，如 `ChatOpenAI`。【核心】libs/partners/openai/langchain_openai/chat_models/base.py#L2823

### 维度 2：上下文工程 ✅
- `ChatPromptTemplate`/`BasePromptTemplate`：模板即 LCEL Runnable。【核心】libs/core/langchain_core/prompts/chat.py#L794、prompts/base.py#L38
- `dynamic_prompt`：按 state 动态生成 system prompt 的中间件工厂。【核心】libs/langchain_v1/langchain/agents/middleware/types.py#L1690
- `SummarizationMiddleware`：`TriggerClause`（tokens/messages/fraction 可组合）触发压缩，无 tokenizer 时用近似计数（chars_per_token=3.3，或按 usage_metadata 缩放）。【核心】libs/langchain_v1/langchain/agents/middleware/summarization.py#L232、#L187、#L227
- `BaseChatMessageHistory`/`InMemoryChatMessageHistory`：消息历史抽象。【核心】libs/core/langchain_core/chat_history.py#L22
- `RunnableWithMessageHistory`：LCEL 层历史注入（0.x 风格）。【核心】libs/core/langchain_core/runnables/history.py#L39
- `system_prompt` 是 create_agent 一等参数（str/SystemMessage）。【核心】libs/langchain_v1/langchain/agents/factory.py#L796

### 维度 3：记忆 🟡
- 会话记忆 = checkpointer（langgraph BaseCheckpointSaver），create_agent 直收参数；跨 thread = store（langgraph BaseStore）。【核心·透传】libs/langchain_v1/langchain/agents/factory.py#L847-L850（checkpointer/store 参数）
- 短时上下文管理靠 `SummarizationMiddleware`（见维度 2）。【核心】libs/langchain_v1/langchain/agents/middleware/summarization.py#L232
- 0.x 显式 memory 对象（ConversationBufferMemory 等）只在 classic。【核心·legacy】libs/langchain/langchain_classic/memory/buffer.py#L24
- 长期记忆/用户画像/遗忘：本仓库无抽象；deepagents 的 AGENTS.md memory 在独立仓库。【未见】

### 维度 4：RAG ✅
- `BaseRetriever`：检索器根抽象。【核心】libs/core/langchain_core/retrievers.py#BaseRetriever
- `VectorStore`(ABC)/`VectorStoreRetriever`/`InMemoryVectorStore`：向量库抽象含 as_retriever。【核心】libs/core/langchain_core/vectorstores/base.py#L43、#L964
- `index()` + `RecordManager`：去重增量索引 API。【核心】libs/core/langchain_core/indexing/api.py#L296、indexing/base.py#L22
- 文档切分独立包；向量库实现（chroma/qdrant）在 partners。【核心】libs/text-splitters、libs/partners/chroma
- `CrossEncoder` rerank 抽象在 core（cross_encoders.py）；hybrid search / citation 无核心抽象。【部分】

### 维度 5：工具系统 ✅
- `BaseTool`(RunnableSerializable)/`@tool`/`InjectedToolArg`（参数注入不暴露给 LLM）/`BaseToolkit`。【核心】libs/core/langchain_core/tools/base.py#L433、#L1726、#L1935
- 工具执行节点 ToolNode 整体透传：libs/langchain_v1/langchain/tools/tool_node.py 是对 `langgraph.prebuilt.tool_node` 的纯 re-export（InjectedState/InjectedStore/ToolRuntime 同源）。【核心·透传】
- MCP：`MCPAdapter` 基于 fastmcp Client/ClientGroup，接受 URL/transport/MCPConfig；elicitation 用 `langgraph.types.interrupt` 实现人答。【核心】libs/langchain_v1/langchain/mcp/adapter.py#L125、mcp/elicitation.py#L23
- 沙箱：`ShellToolMiddleware` + `_execution.py` 三策略——`HostExecutionPolicy`(:92)/`CodexSandboxExecutionPolicy`(:191)/`DockerExecutionPolicy`(:267)，基类 `BaseExecutionPolicy`(:57)。【核心】libs/langchain_v1/langchain/agents/middleware/shell_tool.py#L518、_execution.py
- 工具选择：`LLMToolSelectorMiddleware`/`ProviderToolSearchMiddleware`/`LLMToolEmulator`。【核心】libs/langchain_v1/langchain/agents/middleware/tool_selection.py#L123 等
- 工具级 timeout/truncation：核心无专门抽象（在 langgraph ToolNode 或需自建）；credential 管理无专门抽象。【未见·局部】

### 维度 6：Skill 机制 ❌
- libs/langchain_v1 全文检索 skill/progressive disclosure 零命中。Anthropic SKILL.md 渐进披露的官方实现在 deepagents 仓库（SkillsMiddleware），不在本仓库。【未见】

### 维度 7：规划推理 🔶
- agent 主循环：model 节点(:1543) → tools 节点(:1547)，`Send` 并行分发 tool_calls(:1964)，recursion_limit 默认 9999(:1831)。【核心】libs/langchain_v1/langchain/agents/factory.py
- 结构化输出：`response_format`（ToolStrategy/ProviderStrategy/Pydantic/raw dict）四 overload 类型化返回。【核心】libs/langchain_v1/langchain/agents/factory.py#L772-L868、agents/structured_output.py
- 预算/限额：`ModelCallLimitMiddleware`(:94)/`ToolCallLimitMiddleware`(:141)。【核心】libs/langchain_v1/langchain/agents/middleware/model_call_limit.py、tool_call_limit.py
- 轻量规划：`TodoListMiddleware`（PlanningState 的 todo 读写）。【核心】libs/langchain_v1/langchain/agents/middleware/todo.py#L174
- 显式 planner / plan-and-execute / reflection 抽象：核心无（可经 middleware 或 langgraph 自建）。【未见·局部】

### 维度 8：编排 🟡
- `create_agent` 本体即图装配器：构造 `StateGraph`(:1187) → add_node → `graph.compile(checkpointer=...)`(:1841)，返回 `CompiledStateGraph`——图执行引擎整体透传 langgraph。【核心·透传】libs/langchain_v1/langchain/agents/factory.py
- 中间件钩子编译为独立图节点：`graph.add_node(f"{m.name}.before_agent", ...)`（:1568，before/after_model 同模式 :1592-1640）。【核心】同上
- `wrap_model_call` 洋葱链：`_chain_model_call_handlers`（:263），首个注册为最外层。【核心】同上
- 节点级跳转：`hook_config(can_jump_to=["end","model"])` / `JumpTo`，`_add_middleware_edge`(:2040) 生成跳转边。【核心】libs/langchain_v1/langchain/agents/middleware/types.py#L881、factory.py#L2040
- 组件级管道：LCEL Runnable（branch/router/retry/mermaid 可视化）在 core。【核心】libs/core/langchain_core/runnables/graph.py
- studio/可视化：LangGraph Studio 在 langgraph 生态与托管平台。【生态】

### 维度 9：多 Agent 🔶
- 嵌套：create_agent 的 `name` 参数专门用于把 agent 图作为子图节点挂入父图。【核心】libs/langchain_v1/langchain/agents/factory.py#L861-L867（docstring 明说 multi-agent 用途）
- 观测：`SubagentTransformer` 把嵌套命名 agent 提升为类型化 `run.subagents` 流句柄（转发子 scope 事件）。【核心】libs/langchain_v1/langchain/agents/_subagent_transformer.py#L120
- supervisor/handoff/swarm/group chat/a2a：本仓库无任何抽象（rg 零命中）；官方多 agent 方案在 langgraph-supervisor / langgraph-swarm / deepagents 等独立仓库。【未见→生态】

### 维度 10：持久化 🟡
- `checkpointer`/`store`/`interrupt_before/after` 均为 create_agent 参数，类型 `Checkpointer`/`BaseStore` 来自 langgraph。【核心·透传】libs/langchain_v1/langchain/agents/factory.py#L847-L853
- 图执行缓存：`cache: BaseCache` 参数，`from langgraph.cache.base import BaseCache`（factory.py#L87）——非 LLM 响应缓存。【核心·透传】
- Checkpoint 存储（InMemory/Sqlite/Postgres）实现全在 langgraph 仓库（libs/checkpoint*）。【生态】
- core 侧仅 `BaseStore`(键值 stores.py) 与 InMemory 实现等轻量抽象。【核心】libs/core/langchain_core/stores.py

### 维度 11：HITL ✅
- `HumanInTheLoopMiddleware`：按工具名 intercept，`when: Callable[[ToolCallRequest], bool]` 谓词(:195)；人工决策 `DecisionType = Literal["approve","edit","reject","respond"]`(:51)。【核心】libs/langchain_v1/langchain/agents/middleware/human_in_the_loop.py#L219
- interrupt/resume 底层机制透传 langgraph（`langgraph.types.interrupt`，需 checkpointer）。【核心·透传】
- 静态断点：create_agent 的 interrupt_before/interrupt_after 节点名单。【核心】libs/langchain_v1/langchain/agents/factory.py#L851-L853
- MCP elicitation（服务器向人要输入）也走 interrupt 且按序匹配。【核心】libs/langchain_v1/langchain/mcp/elicitation.py#L23

### 维度 12：观测评估 ✅
- callbacks 体系：BaseCallbackHandler/CallbackManager 贯穿 core 所有 Runnable。【核心】libs/core/langchain_core/callbacks/
- `LangChainTracer`：POST 到 LangChain/LangSmith endpoint 的内置 tracer。【核心】libs/core/langchain_core/tracers/langchain.py#L134
- 脱敏：`TracePolicy`/`omit_payload` 类型定义在 langgraph.types，v1 提供 `configure_trace_policy()` 进程级默认 + 每中间件 `_wrap_trace_kwargs`/`_node_trace_policy`。【核心·部分透传】libs/langchain_v1/langchain/agents/middleware/_trace_policy.py#L22
- 标准测试：langchain-tests 的 `ChatModelUnitTests` 等基类供集成包回归。【核心】libs/standard-tests/langchain_tests/unit_tests/chat_models.py#L277
- 评估/数据集管理：托管 LangSmith（独立产品，langsmith 包为 pip 依赖）。【生态/文档】

### 维度 13：安全治理 ✅
- `PIIMiddleware` + `RedactionRule`/`PIIMatch`：正则规则脱敏，出错可 `PIIDetectionError` fail-closed。【核心】libs/langchain_v1/langchain/agents/middleware/pii.py#L492、_redaction.py
- `ContextEditingMiddleware`：对话后敏感内容编辑（遗忘式擦除）。【核心】libs/langchain_v1/langchain/agents/middleware/context_editing.py#L187
- 沙箱执行：Host/Codex/Docker 三策略（见维度 5）。【核心】libs/langchain_v1/langchain/agents/middleware/_execution.py#L57
- SSRF 防护：`validate_safe_url`/`is_safe_url`，RFC1918 私网默认拦截，供集成包 URL 参数校验。【核心】libs/core/langchain_core/_security/_ssrf_protection.py#L41
- 泛化 guardrail 框架 / 权限系统 / 审计日志：无统一抽象（各安全点为具体中间件）。【未见·局部】

### 维度 14：部署运行时 ❌
- libs/langchain_v1 与 libs/core 检索 fastapi/uvicorn/server 零命中；本仓库不含任何 server/cron/queue/docker。【未见】
- 生态：`langgraph dev` 本地 server 在 langgraph 仓库 cli；生产 API server（Postgres/Celery/Studio）是闭源 LangGraph Platform。【生态·文档】

### 维度 15：管理平面 ❌
- 无 console/dashboard/admin/tenant/billing 代码；trace 管理面是托管 LangSmith（文档宣称）。【未见】

## 6. 设计决策要点

1. **agent = LangGraph 图 + 中间件，钩子编译为图节点**：每个 before/after 钩子变成 `f"{m.name}.before_model"` 独立节点（factory.py:1568-1640），横切能力因此可组合、可在图轨迹中观测；代价是中间件多时图节点/边数量膨胀（jump_to 边生成逻辑 factory.py:2040 起）。
2. **执行内核整体外置 langgraph**：图引擎、Runtime、interrupt、ToolNode、checkpointer/store/图缓存类型、连 TracePolicy 都定义在 langgraph——langchain 1.x 是「装配层 + 组件抽象层」，与引擎是硬版本耦合（`langgraph>=1.2.11,<1.3.0`）。
3. **0.x 不删不弃，独立成包**：langchain-classic 1.0.8 完整保留 Chain/AgentExecutor/memory 老抽象，依赖 core 但 1.x 不反向依赖；`langchain_core/agents.py` 仍留 AgentAction/AgentFinish 类型供 legacy。
4. **模型能力元数据标准化**：ModelProfile（TypedDict）+ 独立数据包 langchain_model_profiles，让运行时按模型能力（而非 provider 判断）选策略，如 structured output 的 ProviderStrategy。
5. **MCP 不自研客户端**：MCPAdapter 委托 fastmcp 的 Client/ClientGroup，elicitation 复用 langgraph interrupt 语义。
6. **不预设 tokenizer 依赖**：SummarizationMiddleware 默认近似 token 计数（3.3 chars/token 或 usage_metadata 缩放），避免每模型装分词器。
7. **多 agent 刻意留白**：核心只给 `name` 子图嵌套与 `run.subagents` 观测句柄，supervisor/swarm/harness 放独立仓库（langgraph-supervisor、deepagents），保持装配层简单。

## 7. 跨语言对齐

不适用（本仓库为 Python 单语；Java 侧对应物见 langchain4j、langgraph4j 各自档案）。
