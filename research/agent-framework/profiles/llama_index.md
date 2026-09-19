# LlamaIndex 框架档案

> 基线：~/develop/opensource/llama_index @ 7169bcd0d 2026-09-11；版本 llama-index-core 0.14.24（`llama-index-core/pyproject.toml:37`）；Workflow 引擎为外部依赖 `llama-index-workflows>=2.14.0,<3`（`llama-index-core/pyproject.toml:83`，uv.lock 锁定 2.23.3，**引擎源码不在本仓库**）；`llama-index-instrumentation` 0.6.0（本仓库内独立包，`llama-index-instrumentation/pyproject.toml:10`）。

## 1. 定位

LlamaIndex 是「数据框架 + Agent 框架」双定位的 Python 库（非平台）：以 RAG/索引管道起家，0.12+ 起把 Agent 体系重构为「Workflow 事件驱动引擎之上的协议层」。目标用户是在自己应用里内嵌 RAG/Agent 能力的 Python 开发者；部署与编排平台（LlamaDeploy、LlamaCloud）在本仓库之外。最具辨识度的架构事实：**两台发动机都已外置**——workflow 引擎（外部 llama-index-workflows 包）和 instrumentation 核心（本仓库独立包 llama-index-instrumentation，core 内全为 shim），core 主仓只剩 agent 协议层 + RAG 数据层。旧 AgentRunner/AgentWorker/OpenAIAgent/FunctionCallingAgent 已在 core 0.13.0 整体删除（`CHANGELOG.md:6353`，PR #19529），全仓无残留，新旧两代并存的担忧不存在——只剩一代。

## 2. 仓库结构与核心包

```
llama_index/                        # 1.2GB monorepo
├── llama-index-core/               # 核心 0.14.24；llama_index/core/ 下 40+ 模块
├── llama-index-instrumentation/    # 独立观测包 0.6.0（src-layout：dispatcher/span/event_handlers）
├── llama-index-integrations/       # 24 类集成（只列举不精读）：
│     llms 103 | readers 150 | vector_stores 78 | embeddings 65 | tools 67（含 tools-mcp、tools-mcp-discovery）
│     callbacks 10（langfuse/arize-phoenix/wandb/openinference…）| observability 1（otel）
│     agent 2（agentmesh、azure）| memory 2（mem0、bedrock-agentcore）| voice_agents 3（openai/gemini-live/elevenlabs）
├── llama-index-utils/              # 4 个（azure/huggingface/oracleai/qianfan；注意 utils-workflow 不在此）
├── llama-dev/                      # monorepo 开发 CLI（包管理/测试自动化，非 Agent 运行时）
└── docs/                           # framework 文档（understanding/agent、rag、deployment 等）
```

关键 shim 验证（`llama-index-core/llama_index/core/workflow/`）：`workflow.py`、`context.py`、`handler.py`、`retry_policy.py`、`service.py`、`resource.py` 均为 1 行 `from workflows.xxx import xxx`；`events.py` 8 行 re-export；`instrumentation/dispatcher.py` 8 行 re-export 外部 `llama_index_instrumentation`。【核心】

## 3. 核心抽象清单

| 符号 | 路径 | 一句话说明 |
|---|---|---|
| `Workflow` / `@step` / `Context` / `Event` | llama-index-core/llama_index/core/workflow/{workflow,decorators,context,events}.py | 全部 1 行 shim，re-export 外部 llama-index-workflows 引擎 |
| `InputRequiredEvent` / `HumanResponseEvent` | 同上 events.py:6-7 | 内置 HITL 事件对（shim） |
| `JsonPickleSerializer` / `JsonSerializer` | workflow/context_serializers.py | checkpoint 序列化器（shim） |
| `BaseWorkflowAgent` | agent/workflow/base_agent.py:87 | Agent 基类：三方法协议 + 配置（tools/tool_retriever/can_handoff_to/initial_state/state_prompt/output_cls） |
| `take_step`/`handle_tool_call_results`/`finalize` | base_agent.py:246/256/262 | Agent 契约仅三个 async 方法，可脱离 workflow 经 AgentContext 单步调用 |
| `AgentContext`(Protocol) / `SimpleAgentContext` | agent/workflow/agent_context.py:17 | agent 与运行时解耦的上下文协议 |
| `FunctionAgent`/`CodeActAgent`/`ReActAgent` | agent/workflow/{function,codeact,react}_agent.py:19/63/38 | 三种执行策略，均为 BaseWorkflowAgent 子类 |
| `AgentWorkflow` | agent/workflow/multi_agent_workflow.py:99 | 多 agent 编排器 = 6 个显式 @step 的事件链 |
| `handoff()` | multi_agent_workflow.py:73 | handoff 即 return_direct 工具，运行时校验 can_handoff_to 白名单 |
| `AgentStream`/`AgentOutput`/`ToolCall(Result)` | agent/workflow/workflow_events.py:38/71/98/106 | 细粒度流式事件 |
| `LLM` / `CustomLLM` / `StructuredLLM` | llms/llm.py:163、llms/custom.py:22、llms/structured_llm.py:32 | 统一 LLM 抽象 + 自定义接入 + 结构化输出包装 |
| `Settings` | settings.py:19(`_Settings`)/:291(单例)；core/__init__.py:78 导出 | 全局 llm/embed_model/callback_manager/node_parser 注入点 |
| `CacheControl`/`CachePoint` | base/llms/types.py:790/795 | 内容块级 prompt 缓存标注（provider cache_control） |
| `BaseMemory`/`ChatMemoryBuffer`/`ChatSummaryMemoryBuffer` | memory/types.py:14、chat_memory_buffer.py:19、chat_summary_memory_buffer.py:26 | 记忆抽象：token_limit 裁剪、摘要压缩 |
| `Memory` + memory blocks | memory/memory.py:188；memory_blocks/{static,fact,vector}.py | 压力式 FIFO + Static/FactExtraction/Vector 三种块 |
| `SimpleComposableMemory`/`VectorMemory` | memory/simple_composable_memory.py:14、vector_memory.py:48 | 可组合记忆 / 向量检索记忆 |
| `BaseTool`/`AsyncBaseTool`/`FunctionTool` | tools/types.py:168/229、function_tool.py:71 | 工具基类（fn_schema 自动生成）与函数工具 |
| `ObjectRetriever` | objects/base.py:25 | 泛型检索器；agent.tool_retriever（base_agent.py:105）实现检索式工具选择 |
| `QueryFusionRetriever` | retrievers/fusion_retriever.py:33 | 混合检索：RRF（:27）/relative_score（:28）融合多路召回 |
| `CitationQueryEngine` | query_engine/citation_query_engine.py:158 | 内联引用标注（CitationBlock 见 base/llms/types.py:1048） |
| `BaseNodePostprocessor` | postprocessor/types.py:12 | rerank 抽象（LLM/rankGPT/SBERT/structured_llm 四种内置实现） |
| `BaseQuestionGenerator`/`SubQuestion` | question_gen/types.py:26/11 | 子问题分解生成器 |
| `IngestionPipeline` | ingestion/pipeline.py:262 | 摄取管道：transformations + cache + num_workers 并行（:547,:606） |
| `BaseRateLimiter`/`TokenBucket/SlidingWindow` | rate_limiter.py:24/60/218 | LLM 调用限流（非重试） |
| `Dispatcher`(shim)/`BaseEvent` 领域事件 | instrumentation/dispatcher.py(8 行)；instrumentation/events/{query,retrieval,rerank}.py | 观测基座外置，RAG 领域事件留在 core |
| `PIINodePostprocessor`/`NERPIINodePostprocessor` | postprocessor/pii.py:40/98 | 检索后 PII 脱敏 |
| `BaseVoiceAgent` | voice_agents/base.py:11 | 语音 agent 抽象（websocket 接口，集成 3 家） |
| `McpToolSpec`/`BasicMCPClient` | llama-index-integrations/tools/llama-index-tools-mcp/…/{base.py:19,client.py:98} | MCP 适配（ClientSession 子类 + 工具包装） |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | core 统一 LLM/多模态/流式/结构化抽象 + Settings 全局；103 个官方供应商集成包；无统一 usage 对象、无 LLM 级重试（有限流器） | llama-index-core/llama_index/core/llms/llm.py#LLM；settings.py#Settings；base/llms/types.py#CacheControl |
| 2 | 上下文工程 | ✅ | 完整模板体系 + 按上下文窗口装配（prompt_helper）+ 压力式 Memory(token_limit/flush) + 历史压缩 chat engine + agent state 注入 | prompts/base.py#PromptTemplate；memory/memory.py#Memory(token_flush_size)；chat_engine/condense_plus_context.py；agent/workflow/base_agent.py#state_prompt |
| 3 | 记忆 | ✅ | ChatMemory 体系 + 可组合 memory blocks（static/fact/vector）+ chat_store 持久化；长期记忆生态 mem0/bedrock-agentcore | memory/memory_blocks/{static,fact,vector}.py；storage/chat_store/；llama-index-integrations/memory/ |
| 4 | RAG | ✅ | 传统强项且最扎实：18 种 query engine、混合检索 RRF 融合、引用、rerank 抽象、子问题分解、全套索引类型、并行摄取管道 | retrievers/fusion_retriever.py#QueryFusionRetriever；query_engine/citation_query_engine.py#CitationQueryEngine；postprocessor/types.py#BaseNodePostprocessor；ingestion/pipeline.py#IngestionPipeline |
| 5 | 工具系统 | ✅ | BaseTool/FunctionTool 自动 schema、ObjectRetriever 检索式工具选择；MCP 在集成包层（🟡）；无 sandbox/timeout 内置 | tools/function_tool.py#FunctionTool；objects/base.py#ObjectRetriever；llama-index-integrations/tools/llama-index-tools-mcp/…/client.py#BasicMCPClient |
| 6 | Skill 机制 | ❌ | 全仓无 skill/渐进披露概念（flare 里的 "SKILL" 只是提示词文案） | —（检索 `skill`/`progressive disclosure` 仅命中 query_engine/flare/base.py:47 提示词字符串） |
| 7 | 规划推理 | ✅ | 反应式三策略（Function/ReAct/CodeAct）+ max_iterations=20 预算 + 双路结构化输出；无独立 planner/reflector 类 | agent/workflow/base_agent.py#DEFAULT_MAX_ITERATIONS(:67)；llms/structured_llm.py#StructuredLLM；tools/query_plan.py#QueryPlanTool；query_engine/flare/ |
| 8 | 编排 | ✅ | 事件驱动 Workflow/@step/Context（引擎外置为官方包，core 为 shim）+ AgentWorkflow 6 步显式链；可视化 draw 已废弃外移 | core/workflow/workflow.py(1 行 shim)；agent/workflow/multi_agent_workflow.py#AgentWorkflow(:381,:436,:466,:523,:643,:681 六个 @step) |
| 9 | 多 Agent | ✅ | AgentWorkflow 原生多 agent：handoff 即工具 + can_handoff_to 静态白名单；orchestrator（子 agent 作工具）为文档化模式；supervisor 预设不在本仓库 | multi_agent_workflow.py#handoff(:73)/#_get_handoff_tool(:216)；docs/…/agent/multi_agent.md（orchestrator 模式） |
| 10 | 持久化 | 🟡 | 双层：索引存储 core 内置（docstore/index_store/kvstore/chat_store）；workflow checkpoint 由外部 workflows 包承载，本仓库仅 shim + 示例 | storage/{docstore,index_store,chat_store}/；core/workflow/context_serializers.py(shim)；docs/examples/workflow/checkpointing_workflows.ipynb【示例】 |
| 11 | HITL | ✅ | 内置 InputRequiredEvent/HumanResponseEvent + ctx.wait_for_event(requirements 匹配) 审批模式；事件 API 经 shim 导出，实现在外部引擎 | core/workflow/events.py#InputRequiredEvent；docs/…/agent/human_in_the_loop.md（wait_for_event 完整示例）；examples/workflow/human_in_the_loop_story_crafting.ipynb【示例】 |
| 12 | 观测评估 | ✅ | instrumentation 基座（Dispatcher/Span）外置为独立包 0.6.0，core 留 RAG 领域事件；OTel 桥 + 10 个 callbacks 集成；eval 模块（faithfulness 等）core 内置 | llama-index-instrumentation/src/…/dispatcher.py#Dispatcher(:50)；core/instrumentation/dispatcher.py(8 行 shim)；llama-index-integrations/observability/llama-index-observability-otel/；core/evaluation/faithfulness.py |
| 13 | 安全治理 | 🔶 | 仅检索后 PII 脱敏处理器 + 隐私文档 + 集成包级信任层（agentmesh）；无 guardrail 框架/sandbox/审计日志 | postprocessor/pii.py#PIINodePostprocessor(:40)；docs/…/understanding/privacy.md；llama-index-integrations/agent/llama-index-agent-agentmesh/（CMVKIdentity 信任门控） |
| 14 | 部署运行时 | ❌ | 本仓库无 server/队列/调度（llama-dev 是 monorepo 开发 CLI；deployment 文档为 TODO 占位）；LlamaDeploy 为外部独立仓库（⚠️ 未本地验证） | llama-dev/README.md（"CLI for development…in the LlamaIndex monorepo"）；docs/…/deployment/deployment.md（正文仅 "TODO"） |
| 15 | 管理平面 | ❌ | 无 console/dashboard/租户/计费；商业管理面在 LlamaCloud SaaS（外部，⚠️ 未本地验证） | — |

## 5. 维度证据明细

### 1) 模型接入 【核心】
- `llms/llm.py:163 class LLM(BaseLLM)`：chat/complete + 全套 async/stream 变体（`stream_chat_response_to_tokens` :111）；`structured_predict`(:307)/`astream_structured_predict` 提供同步结构化。
- `llms/custom.py:22 CustomLLM`：三个抽象方法即可接入自定义模型；`llms/mock.py MockLLM` 测试用。
- `multi_modal_llms/base.py:75 MultiModalLLM`；消息内容块含 Text/Image/Audio/Video/Document/Thinking/ToolCall（`base/llms/types.py:249-1125`）。
- `base/llms/types.py:790 CacheControl`/`:795 CachePoint`：块级 prompt 缓存标注（Anthropic 式 cache_control）——缓存是核心内置。
- `settings.py:19 _Settings` + `:291 Settings = _Settings()`：全局 llm/embed_model/callback_manager/tokenizer/node_parser。
- 限流有、重试无：`rate_limiter.py:60 TokenBucketRateLimiter`/`:218 SlidingWindowRateLimiter`；core 无 LLM 调用重试逻辑（workflow step 级 retry policy 在外部引擎包）。
- usage：core 无统一 usage 对象（`ChatResponse` 仅 message/raw/additional_kwargs，`base/llms/types.py:1282`）；由各供应商集成自行透传（例：`llama-index-integrations/llms/llama-index-llms-openai/…/base.py:691-695` 从 raw_response.usage 取 token 数）。供应商广度靠生态：103 个 llms 集成包。

### 2) 上下文工程 【核心】
- `prompts/base.py:56/135/216`：BasePromptTemplate/PromptTemplate/ChatPromptTemplate；RichPromptTemplate 用于 memory blocks 渲染。
- `indices/prompt_helper.py`：按 LLM 上下文窗口预算装配 prompt（LlamaIndex 标志性机制）。
- `memory/memory.py:188 Memory`：FIFO 达 token_limit 时按 token_flush_size 弹出旧消息交给 memory blocks 处理，块内容经 `memory_blocks_template` 注入 system 或最新 user 消息（`chat_history_token_ratio` :0.7 预留比例）——压力式上下文管理，独此一家。
- `chat_engine/condense_plus_context.py`：CondensePlusContextChatEngine 历史压缩；`condense_question.py` 问题改写。
- `agent/workflow/base_agent.py:119 state_prompt` + `multi_agent_workflow.py:449-456`：把共享 state 格式化注入最后一条 user 消息（幂等，formatted_input_with_state 标志）。

### 3) 记忆 【核心】
- `memory/types.py:14 BaseMemory`；`chat_memory_buffer.py:19 ChatMemoryBuffer`（token_limit 裁剪 :26）；`chat_summary_memory_buffer.py:26`（超限自动 LLM 摘要）。
- memory blocks 三件套：`memory_blocks/static.py:8 StaticMemoryBlock`（静态注入）、`fact.py:67 FactExtractionMemoryBlock`（LLM 事实抽取=准长期记忆）、`vector.py:29 VectorMemoryBlock`（向量库检索回注，put 时入库 delete_nodes）。
- `simple_composable_memory.py:14`：多 primary/secondary 记忆组合。
- 持久化：`storage/chat_store/`（memory 后端可外接 chat store）。
- 生态：`llama-index-integrations/memory/`（mem0 长期记忆、bedrock-agentcore）。
- 无显式遗忘/用户画像治理 API。

### 4) RAG 【核心】（本框架最强维度）
- 检索层：`indices/` 15+ 索引类型（vector_store/keyword_table/tree/property_graph/knowledge_graph/document_summary/struct_store/multi_modal…）；`retrievers/` 含 `fusion_retriever.py:33 QueryFusionRetriever`（:27 RECIPROCAL_RANK、:28 RELATIVE_SCORE 融合 = 混合检索核心）、`auto_merging_retriever.py`（层级合并）、`recursive_retriever.py`（递归/子文档）、`router_retriever.py`。
- 查询层：`query_engine/` 18 种——`citation_query_engine.py:158`（引用）、`sub_question_query_engine.py`（配合 `question_gen/types.py:26 BaseQuestionGenerator` 分解）、`router_query_engine.py:316 ToolRetrieverRouterQueryEngine`（检索式路由）、`retry_query_engine.py`、`sql_vector_query_engine.py`（SQL+向量混合）、`flare/`（前瞻主动检索）、`jsonalyze/`、`pandas/`、`knowledge_graph_query_engine.py`。
- rerank：`postprocessor/types.py:12 BaseNodePostprocessor` 抽象 + 内置 llm_rerank/rankGPT_rerank/sbert_rerank/structured_llm_rerank/optimizer/node_recency/metadata_replacement。
- 摄取：`ingestion/pipeline.py:262 IngestionPipeline`（transformations 组合、`ingestion/cache.py` 断点续跑、:547/:606 num_workers 多进程并行）；`node_parser/`+`text_splitter.py` 切分全家桶。
- 引用是内容块级公民：`base/llms/types.py:1048 CitationBlock`/`:1025 CitableBlock`。
- 向量库/嵌入生态：78 个 vector_stores、65 个 embeddings 集成包。

### 5) 工具系统 【核心】
- `tools/types.py:168 BaseTool`/`:229 AsyncBaseTool`（同步工具经 `:253 BaseToolAsyncAdapter` 适配）；`ToolMetadata`(:24) + `DefaultToolFnSchema`(:17) 自动 pydantic schema。
- `tools/function_tool.py:71 FunctionTool.from_defaults`(:172)：普通 callable/async fn 自动转工具。
- 检索式工具选择：`objects/base.py:25 ObjectRetriever` 泛型协议；`agent/workflow/base_agent.py:105 tool_retriever`（运行时按 input_str aretrieve 动态附加工具，:278-280）。
- 工具输出容错：`ToolOutput.is_error/exception`（types.py:106）；`multi_agent_workflow.py:~370` 工具异常捕获转文本结果不炸流程。
- MCP=集成包层：`llama-index-integrations/tools/llama-index-tools-mcp/…/client.py:98 BasicMCPClient(ClientSession)` + `base.py:19 McpToolSpec`（🟡 生态承载）；另有 tools-mcp-discovery。
- 无 sandbox、无工具级 timeout/输出截断（core 内）。

### 6) Skill 机制 ❌
- 全仓检索 `skill`/`progressive disclosure`：core 仅 `query_engine/flare/base.py:47-55` 的提示词文案（"Skill 1. Use the Search API…"），非机制。【核心】
- 无 SKILL.md/渐进加载等任何对应物。

### 7) 规划推理 【核心】
- 三策略 agent：`function_agent.py:19`（原生 function calling 循环）、`react_agent.py:38 ReActAgent`（Thought/Action 文本协议，复用 `agent/react/output_parser.py`）、`codeact_agent.py:63 CodeActAgent`（写并执行 Python，DEFAULT_CODE_ACT_PROMPT :25）。
- 预算：`base_agent.py:67 DEFAULT_MAX_ITERATIONS=20`，经 ctx.store 的 max_iterations 每步检查（:297、:525）。
- 结构化输出双路：agent 级 `output_cls`/`structured_output_fn`（base_agent.py:125-131，产出 AgentStreamStructuredOutput 事件 workflow_events.py:49）；LLM 级 `structured_llm.py:32 StructuredLLM` + `llm.py:307 structured_predict`。
- 规划类工具：`tools/query_plan.py` QueryPlanTool、`query_engine/multistep_query_engine.py`；无独立 Planner/Reflector 抽象，反思仅靠提示词与 RetryQueryEngine。

### 8) 编排 【核心】（引擎外置需明示）
- 引擎不在本仓库：`core/workflow/{workflow,context,handler,retry_policy,service,resource}.py` 均 1 行 re-export 外部 `llama-index-workflows`（pyproject :83 依赖 >=2.14.0,<3；uv.lock 2.23.3）。多 worker/并发、retry policy、streaming 内部机制属外部包（⚠️ 无法本地回源验证）。
- `core/workflow/decorators.py`：唯一有逻辑的 shim——剥离废弃参数 `pass_context` 再转发 upstream_step。
- 编排层在本仓库：`multi_agent_workflow.py:99 AgentWorkflow` 六个显式 @step（:381 init_run → :436 setup_agent → :466 run_agent_step → :523 parse_agent_output → :643 call_tool → :681 aggregate_tool_results），每步独立可观测/可中断/可 checkpoint。
- 嵌套组合：agent.run 可包成工具（orchestrator 模式）、Workflow 可作工具（外部包能力）。
- 可视化：`workflow/drawing.py#draw_all_possible_flows` 已 @deprecated，指向外部 `llama-index-utils-workflow`（该包也不在本仓库）→ 图形化编排 ❌。

### 9) 多 Agent 【核心】+【文档】
- `AgentWorkflow(agents=[...])`：内存中多 agent 共享 ctx.store 的 memory/state/current_agent_name；单 agent 时 FunctionAgent/ReActAgent 自身即为 workflow（base_agent.py:741/:754 run）。
- handoff 即工具：`multi_agent_workflow.py:73 handoff()`（写 next_agent，return_direct）+ `:216 _get_handoff_tool`（按 can_handoff_to 过滤生成工具清单，单 agent 不生成）；运行时双重校验白名单（:84-86）。
- orchestrator 模式：文档化 pattern（`docs/…/agent/multi_agent.md:86` "expose each agent's run method as a tool"，附 notebook）。
- supervisor/human-handoff 预设、A2A：不在本仓库（⚠️ 外部 workflows 包/示例仓库，未验证）。
- 生态信任层：`llama-index-agent-agentmesh`（CMVKIdentity 密码学身份 + TrustGatedQueryEngine 访问控制）。

### 10) 持久化 🟡
- 索引/数据层【核心】：`storage/`（docstore、index_store、kvstore、chat_store、`storage_context.py`）；对应集成 storage 包（postgres/redis 等在 integrations/storage）。
- Workflow checkpoint【核心 shim + 示例】：`core/workflow/context_serializers.py` 1 行 shim re-export JsonSerializer/JsonPickleSerializer；引擎 checkpoint/resume API（ctx.to_checkpoint 等）在外部 workflows 包（⚠️ 细节未本地验证）；`docs/examples/workflow/checkpointing_workflows.ipynb` 演示用法【示例】。core docs 框架文档无 checkpoint 专页。

### 11) HITL ✅
- 内置事件：`core/workflow/events.py` re-export `InputRequiredEvent`/`HumanResponseEvent`（外部引擎定义）。
- 机制：工具内 `ctx.wait_for_event(HumanResponseEvent, waiter_id=…, waiter_event=InputRequiredEvent(...), requirements={…})` 阻塞等待，调用方从 `handler.stream_events()` 捕获后 `handler.ctx.send_event(...)` 恢复——审批即事件往返。【文档】`docs/…/agent/human_in_the_loop.md`（完整 dangerous_task 示例）+【示例】notebook。
- 与 checkpoint 组合可跨进程挂起恢复（外部引擎能力，⚠️）。

### 12) 观测评估 【核心】+🟡
- 基座外置：`llama-index-instrumentation`（0.6.0，`src/llama_index_instrumentation/dispatcher.py:50 Dispatcher`、SpanHandler/EventDispatcher/Manager，wrapt + ContextVar instrumentation_tags）；`core/instrumentation/dispatcher.py` 等 10 个文件为 1 行 shim。与 workflow 同款「引擎外置」策略。
- 领域事件留 core【核心】：`instrumentation/events/{query,retrieval,rerank}.py`（27-33 行真实实现）等 RAG 事件；`BaseTool`/`LLM` 均为 DispatcherSpanMixin（tools/types.py:168）。
- OTel 桥=集成包：`llama-index-integrations/observability/llama-index-observability-otel`（deps opentelemetry-sdk/api/semantic-conventions）。另有 10 个 callbacks 集成（langfuse/phoenix/wandb/openinference…）。
- 评估【核心】：`core/evaluation/`（faithfulness、relevancy、correctness、answer/context_relevancy、pairwise、semantic_similarity、dataset_generation、benchmarks、retrieval/）——少数把 eval 放主包核心的框架。

### 13) 安全治理 🔶
- 【核心】`postprocessor/pii.py:40 PIINodePostprocessor`/`:98 NERPIINodePostprocessor`：检索结果脱敏（NER 可选）。
- 【文档】`docs/…/understanding/privacy.md` 隐私说明。
- 【核心-生态】agentmesh 集成：密码学身份 + 信任门控 query engine（🟡）。
- guardrail 框架、工具 sandbox、审计日志、权限系统：❌。HITL 审批（InputRequiredEvent）是唯一流程级闸门。

### 14) 部署运行时 ❌
- core 无 fastapi/server/queue/cron（检索 0 命中）；`llama-dev` 自述 "CLI for development, testing, and automation in the LlamaIndex monorepo"——monorepo 工程工具，非 Agent 运行时。
- `docs/…/deployment/deployment.md` 正文仅 "TODO" 占位。
- LlamaDeploy（agent server/API server）为外部独立仓库，本仓库零代码（⚠️ 未本地验证）。

### 15) 管理平面 ❌
- 无 console/dashboard/租户/计费/配置中心任何代码。商业控制面=LlamaCloud（SaaS，外部 ⚠️ 未验证）。

## 6. 设计决策要点

1. **双引擎外置（独此一家）**：workflow 引擎（外部 llama-index-workflows）与 instrumentation 基座（本仓库独立包 llama-index-instrumentation）都被抽成可独立演进的包，core 只留 1 行 shim + 领域实现——引擎与数据框架彻底解耦，本档案因此有 3 处 ⚠️（引擎内部行为无法回源验证）。
2. **Agent=三方法协议而非类层次**：`take_step/handle_tool_call_results/finalize` + `AgentContext` Protocol（base_agent.py:246-262），agent 是可插拔到任意事件运行时的组件；对照教训是旧 AgentRunner/AgentWorker 双层抽象于 0.13.0 被整体删除（CHANGELOG.md:6353）——执行循环收敛为单一事件驱动模型。
3. **handoff 即 return_direct 工具 + 静态白名单**：控制流图声明式（can_handoff_to）、运行时校验（multi_agent_workflow.py:84-86），比自由 swam 可审计；编排本身是 6 个显式 @step，天然获得 checkpoint/HITL/重试粒度。
4. **上下文管理走「压力式 FIFO + memory blocks」**（memory/memory.py:188）：不是简单截断，而是超限时把旧消息降级到 fact/vector 块再按模板回注——比 sliding window 更接近人类记忆分层。
5. **RAG 全栈单包**：检索/融合/引用/rerank/子问题/摄取/评估全部塞进 core 主包（evaluation 都在核心），与「引擎都外置」形成鲜明反差——数据层是身份认同，agent 层是新方向。
6. **usage/重试留给集成**：core 无统一 usage 对象与 LLM 重试（仅限流器），token 统计由各供应商集成从 raw 透传（openai 集成 base.py:691）——「薄核心厚生态」哲学的代价。

## 7. 跨语言对齐

不适用（模板规定仅 langgraph4j / adk-java / agentscope-java 需要）。注：LlamaIndex.TS 为独立产品线，不在本地克隆范围。
