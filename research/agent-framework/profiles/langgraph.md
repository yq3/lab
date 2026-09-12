# LangGraph 框架档案

> 基线：~/develop/opensource/langgraph @ e539ac122 2026-09-09；版本（libs/*/pyproject）：langgraph 1.2.11、checkpoint 4.2.0、checkpoint-postgres 3.1.2、checkpoint-sqlite 3.1.1、prebuilt 1.1.0、checkpoint-conformance 0.0.2；cli / sdk-py / sdk-js 版本号为动态（打包时注入）。

## 1. 定位

LangGraph 是 LangChain 生态的**底层编排引擎**：以 Pregel/BSP（Bulk Synchronous Parallel）模型执行有状态、可持久化、可人机协同的 agent 图。它刻意不做模型接入、RAG、组件层——那是 langchain-core / langchain 1.x 的职责；本仓专注「图执行 + 持久化 + HITL 原语」三件事。目标用户是需要精细控制 agent 循环、状态语义与生产化持久化的工程师；上层封盖是 `langgraph.prebuilt`（create_react_agent / ToolNode），再往上是 langchain 1.x 的 `create_agent`（中间件体系，另仓）。开源部分 = 引擎 + 持久化 + prebuilt + SDK + 本地 dev server；生产级 API server（LangGraph Platform / LangSmith Deployments，镜像 `langchain/langgraph-api`）闭源商业分发。

## 2. 仓库结构与核心包

monorepo，`libs/` 下 10 个自包含包（各自 pyproject + Makefile）：

| 包 | 版本 | 职责 |
|---|---|---|
| `libs/langgraph` | 1.2.11 | Pregel 执行引擎、StateGraph/Functional API、Send/Command/interrupt、channels |
| `libs/checkpoint` | 4.2.0 | BaseCheckpointSaver / BaseStore / BaseCache 抽象 + InMemory 实现 + serde（jsonplus/加密） |
| `libs/checkpoint-sqlite` / `-postgres` | 3.1.1 / 3.1.2 | SqliteSaver / PostgresSaver（含 async 变体） |
| `libs/checkpoint-conformance` | 0.0.2 | 存储后端合规测试套件（spec/test_put、test_list、test_delta_channel_history…） |
| `libs/prebuilt` | 1.1.0 | create_react_agent、ToolNode、ValidationNode、HITL UI 类型 |
| `libs/cli` | 动态 | `langgraph dev`（拉起 dev server）、docker 部署配置生成 |
| `libs/sdk-py` / `libs/sdk-js` | 动态 | 平台客户端（threads/runs/assistants/crons/store）+ 自定义 auth + 流式传输 |

`docs/` 仅 redirect 配置；`examples/` 为教程 notebook（多 agent / RAG / planning / HITL 等，【示例】级证据）。

## 3. 核心抽象清单

| 符号 | 路径（仓库相对） | 一句话说明 |
|---|---|---|
| `StateGraph` / `CompiledStateGraph` | libs/langgraph/langgraph/graph/state.py#131 / #1404 | 图 builder；compile 后产物继承 Pregel |
| `Pregel` | libs/langgraph/langgraph/pregel/main.py#450 | 执行引擎本体（自身是 Runnable），Plan/Execute/Update 三相超步循环 |
| `PregelLoop` | libs/langgraph/langgraph/pregel/_loop.py#158 | 单次运行的状态机：tick()/after_tick() 逐 superstep 推进 |
| `prepare_next_tasks` | libs/langgraph/langgraph/pregel/_algo.py#349 | channel 版本差分判定本步激活哪些节点（Pregel next 语义） |
| `apply_writes` | libs/langgraph/langgraph/pregel/_algo.py#232 | 合并节点写入、更新 channel 版本 |
| `BaseChannel` 家族 | libs/langgraph/langgraph/channels/*.py | LastValue/Topic/EphemeralValue/BinaryOperatorAggregate/AnyValue/NamedBarrierValue/UntrackedValue/**DeltaChannel**(:delta.py#25，增量快照控 checkpoint 膨胀) |
| `add_messages` | libs/langgraph/langgraph/graph/message.py#61 | 内置消息 reducer（按 id 合并/替换） |
| `Send` | libs/langgraph/langgraph/types.py#704 | map-reduce 动态并行分发原语 |
| `Command` | libs/langgraph/langgraph/types.py#799 | 节点返回值即控制流：goto/update/resume，`PARENT` 可跳父图 |
| `interrupt` / `GraphInterrupt` | libs/langgraph/langgraph/types.py#851；errors.py#102 | 节点内抛异常冒泡暂停，resume 值经 Command 回填 |
| `PregelScratchpad` | libs/langgraph/langgraph/_internal/_scratchpad.py#9 | 任务级暂存：interrupt 顺序匹配 / resume 列表 / call 计数 |
| `@task` / `@entrypoint` | libs/langgraph/langgraph/func/__init__.py#110 / #262 | Functional API，编译为同一 Pregel 循环 |
| `Durability` | libs/langgraph/langgraph/types.py#89 | `sync/async/exit` 三级持久化强度 |
| `RetryPolicy`/`TimeoutPolicy`/`CachePolicy`/`TracePolicy` | libs/langgraph/langgraph/types.py#418/#452/#521/#533 | 节点级策略对象 |
| `IsLastStepManager`/`RemainingStepsManager` | libs/langgraph/langgraph/managed/is_last_step.py#9/#18 | 节点内可感知 recursion_limit 预算 |
| `BaseCheckpointSaver` | libs/checkpoint/langgraph/checkpoint/base/__init__.py#177 | 持久化接口 6 方法：get/get_tuple/list/put/put_writes/delete_thread（:228-321），另有 get_delta_channel_history(:583) |
| `BaseStore` | libs/checkpoint/langgraph/store/base/__init__.py#708 | 跨 thread 长期记忆：namespace+key 文档，search(query/filter) 语义检索，put(index=) 字段级索引 |
| `BaseCache` / `RedisCache` | libs/checkpoint/langgraph/cache/base/__init__.py#15；cache/redis/__init__.py#10 | LLM 调用结果缓存抽象 + Redis 实现（配合 CachePolicy） |
| `EncryptedSerializer` | libs/checkpoint/langgraph/checkpoint/serde/encrypted.py#8 | checkpoint 静态加密（pycryptodome AES 适配） |
| `InMemorySaver` / `SqliteSaver` / `PostgresSaver` | libs/checkpoint/.../memory/__init__.py#33；libs/checkpoint-sqlite/.../__init__.py#45；libs/checkpoint-postgres/.../__init__.py#40 | 三种官方存储后端（各含 Async 变体） |
| `create_react_agent` | libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py#278 | 预编译 ReAct agent 图（model 节点+tools 节点） |
| `ToolNode` | libs/prebuilt/langgraph/prebuilt/tool_node.py#622 | 工具批量执行节点：Send 并行(:293 注释)、executor.map(:821)/gather(:858) |
| `ValidationNode` | libs/prebuilt/langgraph/prebuilt/tool_validator.py#47 | 先验校验模型工具调用参数 |
| `HumanInterruptConfig` 等 | libs/prebuilt/langgraph/prebuilt/interrupt.py#11/#33/#51/#87 | HITL 决策 UI 类型（accept/edit/resume 描述结构） |
| `RemoteGraph` | libs/langgraph/langgraph/pregel/remote.py#118 | 把远端部署的图当本地节点用（PregelProtocol 实现） |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 |
|---|---|---|---|---|
| 1 | 模型接入 | 🟡 | 模型抽象全在 langchain-core/partner 包；本仓提供节点级 Retry/Timeout/Cache 策略与 token 流式 | libs/langgraph/langgraph/types.py#RetryPolicy/#CachePolicy；prebuilt/chat_agent_executor.py#278（model 参数支持动态选择） |
| 2 | 上下文工程 | 🔶 | 有 add_messages reducer 与 prebuilt prompt/response_format；trim/summarize 在 langchain 系另仓 | libs/langgraph/langgraph/graph/message.py#add_messages |
| 3 | 记忆 | ✅ | 双层：thread 内 checkpoint 短期记忆 + 跨 thread BaseStore 长期记忆（语义检索） | libs/checkpoint/.../store/base/__init__.py#BaseStore；types.py#interrupt 文档中 previous 模式 |
| 4 | RAG | 🔶 | 核心无 retriever 抽象；examples/rag 有 9 个范式 notebook（agentic/adaptive/CRAG/self-RAG） | examples/rag/langgraph_agentic_rag.ipynb 等【示例】 |
| 5 | 工具系统 | ✅ | ToolNode 并行执行/错误处理/Command 工具/注入原语；schema 定义依托 langchain-core @tool | libs/prebuilt/langgraph/prebuilt/tool_node.py#ToolNode（:821 executor.map） |
| 6 | Skill 机制 | ❌ | 无 skill/渐进披露抽象（deepagents 另仓实现） | 全仓 rg 'skill' 无核心命中 |
| 7 | 规划推理 | ✅ | create_react_agent（ReAct 循环+response_format 结构化输出）+ recursion_limit 步数预算；高级规划范式为示例 | libs/prebuilt/.../chat_agent_executor.py#278；pregel/_loop.py#1701（stop=step+limit+1） |
| 8 | 编排 | ✅ | 本仓立身之本：StateGraph/Functional API/Send/Command/subgraph/并行执行器 | libs/langgraph/langgraph/pregel/main.py#Pregel |
| 9 | 多 Agent | 🟡 | 原子能力（subgraph/Send/Command goto）内置；supervisor/swarm 封装在官方独立仓⚠️未本地验证 | pregel/main.py#get_subgraphs(:1076)；examples/multi_agent/【示例】 |
| 10 | 持久化 | ✅ | saver 三后端 + durability 分级 + pending writes + time-travel + conformance 套件 | libs/checkpoint/.../base/__init__.py#BaseCheckpointSaver；_loop.py#_put_checkpoint(:1081) |
| 11 | HITL | ✅ | interrupt/Command(resume) 函数式原语 + 静态 interrupt_before/after + prebuilt 决策类型 | libs/langgraph/langgraph/types.py#interrupt(:851)；prebuilt/interrupt.py#11 |
| 12 | 观测评估 | 🟡 | 内置 7 种 stream mode + debug 事件；分布式 tracing 依托 LangSmith（callback 生态）；OTel 未见 | libs/langgraph/langgraph/types.py#StreamMode(:122)；pregel/main.py:2772 |
| 13 | 安全治理 | ❌ | 无 guardrail/permission/sandbox 抽象；仅 checkpoint 静态加密与 SDK 侧 auth/encryption | libs/checkpoint/.../serde/encrypted.py#8；libs/sdk-py/langgraph_sdk/auth/ |
| 14 | 部署运行时 | 🟡 | 开源：cli dev server + SDK + RemoteGraph；生产 server 为闭源 langgraph-api 镜像 | libs/cli/langgraph_cli/docker.py:262-278；pregel/remote.py#RemoteGraph(:118) |
| 15 | 管理平面 | 🟡 | Studio/Platform 控制台闭源；开源侧经 SDK 客户端管理 threads/assistants/crons/store | libs/sdk-py/langgraph_sdk/_async/{threads,assistants,cron,store}.py |

⚠️ 待确认 2 处（详见第 5 节 #9、#10：langgraph-supervisor/swarm 官方独立仓、langgraph-checkpoint-redis 独立仓，均不在本地克隆范围，未做源码验证）。

## 5. 维度证据明细

### 1) 模型接入 🟡
- 本仓核心**不定义任何 ChatModel 抽象**，`create_react_agent(model=...)` 接受 `str | LanguageModelLike | Callable[[State, Runtime], BaseChatModel]`，支持按 runtime 动态选模（chat_agent_executor.py:279-292）。【核心】
- 节点级策略对象：`RetryPolicy`（types.py:418）、`TimeoutPolicy`（:452）、`CachePolicy`（:521，key_func+ttl）——作用于任意节点（含模型调用节点）。【核心】
- LLM 结果缓存：`BaseCache`/`RedisCache`（libs/checkpoint/langgraph/cache/，配合 func API 的 task 使用，func/__init__.py:33 导入）。【核心】
- token 级流式：stream mode `"messages"`（types.py:122-135）。【核心】
- provider 适配本体在 langchain-core 与 partner 包（另仓）→ 🟡。

### 2) 上下文工程 🔶
- `add_messages` reducer（graph/message.py:61）：按消息 id 合并/替换，是消息历史的官方状态语义。【核心】
- prebuilt `prompt` 参数支持 str/SystemMessage/Callable/模板；`response_format` 支持结构化最终输出（chat_agent_executor.py:278 签名）。【核心】
- trim/summarize/token 预算不在本仓（langchain-core trim_messages、langchain 1.x SummarizationMiddleware，另仓档案覆盖）。【文档】
- 长上下文增量优化：`DeltaChannel`（channels/delta.py:25）+ checkpoint `counters_since_delta_snapshot`（_loop.py:1081 内）按 (updates, supersteps) 计数做增量快照。【核心】

### 3) 记忆 ✅
- 短期 = checkpoint：thread_id 定位会话，`get_state/update_state/get_state_history`（pregel/main.py:1392/2515/1480）。【核心】
- 长期 = `BaseStore`（store/base/__init__.py:708）：namespace 元组 + key 文档模型；`search(query=, filter=, limit=, offset=)`（:779）自然语言检索；`put(index=[...])`（:856-874）声明哪些字段进向量索引，`index=False` 关闭。【核心】
- 嵌入适配：`EmbeddingsLambda`（store/base/embed.py:109）把任意 embed 函数包成 LangChain Embeddings 协议。【核心】
- Functional API 的 `entrypoint(previous=...)` 把上次 final 值作为本次入参（func/__init__.py:282-291 文档）。【核心】
- 语义记忆的向量库后端（Postgres pgvector 等）在平台/独立包，本仓仅内存实现 `InMemoryStore`（store/memory/__init__.py:136）。

### 4) RAG 🔶
- 核心包无 retriever/vector store/rerank 抽象（rg 无命中）。【核心（缺失）】
- examples/rag/ 9 个 notebook：agentic_rag、adaptive_rag、crag、self_rag（各有 local/云变体）——检索组件全部来自 langchain 社区包。【示例】
- 结论：RAG 是「图上的一种编排模式」而非框架能力 → 🔶。

### 5) 工具系统 ✅
- `ToolNode`（tool_node.py:622）：批量 tool_calls 并行执行——注释明言用 Send API 分发（:293），同步 executor.map（:821）、异步 asyncio.gather（:858）。【核心】
- 注入原语：`InjectedState`/`InjectedStore`/`ToolRuntime`（prebuilt/__init__.py 导出，tool_node.py 实现）——工具可读写图状态与 Store 而不暴露给 LLM schema。【核心】
- 工具可返回 `Command`（state 更新+goto）而非仅 ToolMessage（tool_node.py:657）。【核心】
- `ValidationNode`（tool_validator.py:47）：调工具前校验参数。【核心】；`ToolCallTransformer`（_tool_call_transformer.py）拦截改写工具调用流。【核心】
- 错误处理：`_default_handle_tool_errors`/`handle_tool_errors` 参数（tool_node.py:383-394）。【核心】
- 工具定义与 schema 生成在 langchain-core `@tool`（另仓）；MCP 适配在 langchain-mcp-adapters（另仓，未本地验证）→ 扣一项到生态。

### 6) Skill 机制 ❌
- 核心与 prebuilt 全文无 skill/progressive disclosure 概念（rg 无命中）。Anthropic Skills 范式由 deepagents（另仓，见其档案）在 LangGraph 之上实现。需用户自建 → ❌。

### 7) 规划推理 ✅
- `create_react_agent`（chat_agent_executor.py:278）：模型节点 ↔ 工具节点循环的官方 ReAct 实现，`response_format` 结构化输出、`pre/post_model_hook` 插桩点。【核心】
- 步数预算：`recursion_limit`（main.py:2563 校验 ≥1；_loop.py:1701 `stop = step + recursion_limit + 1`，超限抛错提示调参）。【核心】
- 节点内预算感知：`IsLastStepManager`/`RemainingStepsManager` managed value（managed/is_last_step.py:9/18），agent 可在最后一步主动收敛。【核心】
- 高级规划范式全在 examples：plan-and-execute、lats、reflexion、rewoo、self-discover、reflection。【示例】

### 8) 编排 ✅
- 执行模型：`Pregel`（main.py:450）类 docstring 明确 Pregel/BSP 三相（Plan/Execution/Update），节点执行期写入对彼此不可见（BSP 屏障）。【核心】
- 调度判定：`prepare_next_tasks`（_algo.py:349）按 channel 版本 vs `versions_seen` 差分激活节点——天然幂等可恢复。【核心】
- 两条构建路径：Graph API（StateGraph，state.py:131）与 Functional API（@task/@entrypoint，func/__init__.py:110/262），同编译到 Pregel。【核心】
- 状态语义：`Annotated[T, reducer]` 经 `_is_field_binop`（state.py:1904-1917）映射为 LastValue 或 BinaryOperatorAggregate。【核心】
- 动态路由：边函数返回 `Send`（types.py:704，map-reduce）；节点返回 `Command(goto=)`（types.py:799）。【核心】
- subgraph：编译图直接作节点，`get_subgraphs`（main.py:1076），`checkpoint_ns` 命名空间隔离状态（main.py:1203/1326）。【核心】
- 并行：`get_executor_for_config`（_executor.py）线程池执行同 superstep 任务。【核心】

### 9) 多 Agent 🟡
- 内置的是**原子能力**而非多 agent 框式：subgraph 嵌套（见上）、`Send` 并行分发、`Command(goto=)/PARENT` 跨层跳转（types.py:799+PARENT）。【核心】
- supervisor / swarm / hierarchical 等式样在官方独立仓（langgraph-supervisor、langgraph-swarm）⚠️不在本地 17 仓清单内，未做源码验证。【文档】
- examples/multi_agent/（multi-agent-collaboration、hierarchical_agent_teams）演示用原子能力自组。【示例】

### 10) 持久化 ✅
- 接口：`BaseCheckpointSaver` 6 方法（base/__init__.py:228-321）；官方后端 InMemory（checkpoint 包）/ Sqlite / Postgres（含 async 双形态）。Redis saver 为独立仓 langgraph-checkpoint-redis ⚠️未本地验证。【核心】
- durable execution：`Durability = "sync"/"async"/"exit"`（types.py:89）；`_put_checkpoint`（_loop.py:1081）按 durability 门控——`exit` 模式仅在退出时落盘（:1134 `exiting or durability != "exit"`）。【核心】
- 崩溃不丢已完成工作：节点执行中途写入以 pending writes 单独持久化（_loop.py:424-434 按 task_id 过滤），恢复时重放。【核心】
- time-travel：checkpoint id 单调，`get_state_history`（main.py:1480）回溯任意历史点，配合 `update_state`（:2515）改史重放。【核心】
- 存储合规：`libs/checkpoint-conformance`（spec/test_put、test_list、test_delete_thread、test_delta_channel_history 等）——新后端过套件即可替换。【核心】
- serde：`JsonPlusSerializer`（jsonplus.py:82）默认；`EncryptedSerializer`（encrypted.py:8）AES 静态加密。【核心】

### 11) HITL ✅
- 函数式原语 `interrupt(value)`（types.py:851）：首次调用抛 `GraphInterrupt`（errors.py:102）冒泡终止；resume 必须走 `Command(resume=...)`；**节点从头重放**，多次 interrupt 按**任务内顺序**匹配 resume 值——当前实现经 `PregelScratchpad`（_internal/_scratchpad.py:9，interrupt_counter/resume 列表），已非早期 `__resume__` 保留 channel 方案。【核心】
- 静态打断：`compile(interrupt_before=/interrupt_after=)`（graph/state.py:1183-1264，支持 `"*"` 全节点）。【核心】
- 强依赖 checkpointer（interrupt 文档明言）。【文档】
- prebuilt 决策类型：`HumanInterruptConfig/ActionRequest/HumanInterrupt/HumanResponse`（prebuilt/interrupt.py:11/33/51/87）——描述 allow_accept/allow_edit/allow_respond 的通用决策负载，供 Studio/前端消费。【核心】
- examples/human_in_the_loop/wait-user-input.ipynb。【示例】

### 12) 观测评估 🟡
- 内置流式观测：7 种 stream mode `values/updates/checkpoints/tasks/debug/messages/custom`（types.py:122），`StreamWriter` 节点内自定义事件（:141）。【核心】
- tracing 经 langchain-core callback 体系：`get_callback_manager_for_config`（main.py:42/2772）→ LangSmith 自动埋点（外部 SaaS，另仓协议）；`TracePolicy`（types.py:533）控制 trace 载荷策略。【核心+生态】
- OTel：核心与 prebuilt 无 opentelemetry 依赖（rg 无命中）。【核心（缺失）】
- 评估：examples/chatbot-simulation-evaluation（模拟评估）、run-id-langsmith.ipynb；框架无 eval/dataset 抽象。【示例】

### 13) 安全治理 ❌
- 无 guardrail/permission/sandbox/audit 内容安全抽象（核心与 prebuilt rg 仅 docstring 提及 guardrails 一词，chat_agent_executor.py:426 是 hook 用途举例）。【核心（缺失）】
- 已有的安全件：checkpoint 静态加密 `EncryptedSerializer`（serde/encrypted.py:8）；SDK 侧自定义鉴权 `langgraph_sdk/auth/` 与字段级加密 `encryption/types.py`（面向 LangGraph Platform 的 access control / PII 字段加密，开源 SDK 定义协议、执行在闭源平台）。【核心】
- 沙箱执行、PII 检测等由 langchain 1.x 中间件（PII、ShellTool 沙箱，另仓）或用户自建 → ❌。

### 14) 部署运行时 🟡
- 开源侧：`libs/cli`（langgraph dev 本地开发服务器、`langgraph build` 生成 docker-compose）；`libs/sdk-py`/`sdk-js` 双语客户端；`RemoteGraph`（pregel/remote.py:118）把远端部署图当本地子图调用。【核心】
- **闭源边界（明确）**：API server 本体是 `langgraph-api`——cli 的 docker.py:262-278 直接引用 `langchain/langgraph-api` 镜像作为 service；即 dev/prod server 的队列、Postgres 编排、Studio 属 LangGraph Platform / LangSmith Deployments 商业产品（README.md:46-57 链接 docs.langchain.com/langsmith/deployments）。【核心+文档】
- 定时任务：`cron` 客户端在 SDK（sdk-py/_async/cron.py）——面向平台 API，引擎本身不含 scheduler。【核心】
- 无内置 queue/temporal 集成（durable 由自身 checkpoint 体系承担，见 #10）。

### 15) 管理平面 🟡
- 开源仓不含任何 console/dashboard/tenant/billing；管理面 = LangGraph Studio（可视化调试 UI）+ LangSmith 控制台，均闭源平台（README.md:57）。【文档】
- 开源可达的管理接口：SDK 客户端 categories——threads、runs（含批量 join）、assistants、crons、store（sdk-py/_async|_sync/*.py），即「管理平面协议开源、实现闭源」。【核心】

## 6. 设计决策要点

1. **Pregel/BSP 而非解释器循环**：调度=channel 版本差分（_algo.py#prepare_next_tasks），执行=超步屏障（写入互不可见），使 durable/resume 语义免费获得——这是与「循环解释器」类框架（如 claude-agent-sdk）的根本分野。
2. **状态即 channel+reducer 的显式代数**：`Annotated[T, reducer]` 编译期映射到 channel 类型（state.py:1904-1917），并行写冲突语义由用户声明而非框架猜测；`DeltaChannel`/`counters_since_delta_snapshot` 再在其上解决快照膨胀。
3. **interrupt = 异常冒泡 + scratchpad 顺序匹配**：HITL 零侵入节点代码，代价是节点必须可重放（确定性）；该机制 1.x 已从保留 channel 演进为 `PregelScratchpad`（_internal/_scratchpad.py）。
4. **持久化接口窄化 + 合规套件**：saver 仅 6 方法，配 checkpoint-conformance 独立包，形成「实现窄接口+过套件=可插拔存储」的扩展范式；durability 三级（sync/async/exit）把一致性-延迟权衡交给调用点。
5. **能力分层严格**：引擎（langgraph）→ 持久化（checkpoint*）→ 预制件（prebuilt）→ 组件/中间件（langchain 另仓）→ 多 agent 式样（独立仓）→ 生产运行时（闭源平台）。开源/商业边界清晰可指证（docker.py 的 langgraph-api 镜像）。
6. **双 API 面向同一编译目标**：Graph API 与 Functional API（@task/@entrypoint）都降级为 Pregel 图，功能（checkpointer/interrupt/durability）天然对两者等价可用。
7. **观测押注 callback 生态而非 OTel**：tracing 走 langchain-core callback→LangSmith，跨厂商标准（OTel）在核心缺席。

## 7. 跨语言对齐

不适用（本档案为 Python 参考实现）。Java 对齐版 langgraph4j 见 `profiles/langgraph4j.md`（该档案含逐维度差异）。
