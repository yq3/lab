# langgraph4j 框架档案

> 基线：~/develop/opensource/langgraph4j @ c2cf2e33 2026-09-06；版本 1.9.0-beta6（父 pom `langgraph4j-parent`，MIT，Java 17；依赖 langchain4j 1.19.0 / spring-ai 2.0.1 / org.bsc.async:async-generator 作者自研流式库）。1.8.x 走 LTS 分支 `support/1.8.x`。

## 1. 定位

LangGraph 的 Java 社区移植（作者 bsorrentino 主导，非 LangChain AI 官方），口号「Graph Engineering for Agentic AI Workflows in Java」。是一个**库**而非平台：以有向图 + 显式状态 + checkpoint 为骨架构建有状态、可中断恢复的 LLM 应用。模型/工具/RAG 完全不自己做，通过官方双集成模块接 **langchain4j** 与 **Spring AI** 两个 Java 模型生态。目标用户是偏好图式编排、需要 HITL/断点续跑、运行在 JVM 技术栈（尤其 Spring）上的团队。核心仓库无 CLI 部署链路，Studio 是嵌入式进程内调试服务器。

## 2. 仓库结构与核心包

Maven 多模块（父 pom.xml `<modules>`），模块划分即分层：

| 层 | 模块 | 说明 |
|---|---|---|
| 核心 | `langgraph4j-core`（org.bsc.langgraph4j） | 图/状态/checkpoint/hook/agent/skill 抽象，约 120 个 Java 文件，零模型依赖 |
| 核心配套 | `langgraph4j-dsl`、`langgraph4j-bom` | DSL 仅含 `JsonDslGenerator`（图定义导出 JSON，供 studio）；BOM 管版本 |
| langchain4j 集成 | `langchain4j/langchain4j-core`、`langchain4j/langchain4j-agent` | 工具桥（LC4jToolService）、消息序列化、AgentExecutor（ReAct 预制） |
| Spring AI 集成 | `spring-ai/spring-ai-core`、`spring-ai/spring-ai-agent`（+archetype） | SpringAIToolService、ReactAgentBuilder（含 skill/subagent 组合） |
| Studio | `studio/base`、`studio/jetty`、`studio/springboot`（quarkus 已注释停用） | 嵌入式可视化调试服务器 |
| Saver | postgres / oracle / mysql / redis / dynamodb / cockroachdb / hazelcast / sqlite 共 8 个外部 checkpoint 模块 | 见维度 10 |
| 观测 | `langgraph4j-opentelemetry` | OTEL hook |
| 示例 | `how-tos`（29 个 notebook，RAG/supervisor/subgraph/time-travel 等）、`samples`（仅 README，新示例已迁独立仓库） | |
| 实验性 | `javelit`（profile 门控） | 与 Javelit（Java 版 Streamlit）数据应用集成 |

## 3. 核心抽象清单

| 符号 | 路径（相对仓库根） | 一句话说明 |
|---|---|---|
| `StateGraph#addNode/addEdge/addConditionalEdges/addSubgraph` | langgraph4j-core/.../StateGraph.java:195-452 | 图构建器；条件边返回目标节点名或 `Command` |
| `CompiledGraph#stream/invoke/streamSnapshots` | langgraph4j-core/.../CompiledGraph.java:417-533 | 编译产物；`stream` 返回可取消 `AsyncGenerator<NodeOutput>` |
| `CompiledGraph#getStateHistory/updateState` | 同上 :188/:242 | 时间旅行历史与按节点回写状态（对齐 Python `get_state_history/update_state`） |
| `CompiledGraph.Emitter` | 同上 :589 | 执行引擎：逐节点推进 → hook 包裹 → nextNodeId 求路由 → checkpoint，循环 |
| `Command` | langgraph4j-core/.../action/Command.java:24 | `gotoNode + update` 合一的节点内动态路由（对齐 Python `Command`） |
| `AgentState` / `Channel` / `Reducer` / `RemoveByHash` | langgraph4j-core/.../state/ | 不可变状态快照 + channel 归并；RemoveByHash ≈ Python `RemoveMessage` |
| `AsyncNodeAction` / `AsyncEdgeAction` / `AsyncCommandAction` | langgraph4j-core/.../action/ | 节点/边动作函数式接口，返回 `CompletableFuture<partialState>` |
| `InterruptibleAction#interrupt` / `InterruptionMetadata` | langgraph4j-core/.../action/InterruptibleAction.java:60 | 节点内动态决定中断（接口 opt-in 式，非 Python 的 `interrupt()` 异常式） |
| `BaseCheckpointSaver` / `MemorySaver` / `FileSystemSaver` | langgraph4j-core/.../checkpoint/ | checkpoint SPI 与两个内置实现 |
| `NodeHook` / `EdgeHook`（Before/After/WrapCall） | langgraph4j-core/.../hook/ | 三段式统一拦截点，承载重试/OTEL/技能注入 |
| `Agent` / `AgentEx` | langgraph4j-core/.../agent/ | core 内 ReAct 图预制；AgentEx 含 action_dispatcher（每工具一节点）+ 审批节点 |
| `SkillParser` / `SkillSource` / `SkillPath` | langgraph4j-core/.../agent/skill/ | Markdown front-matter 技能解析（Agent Skills 风格） |
| `AgentExecutor`（+Builder） | langchain4j/langchain4j-agent/.../AgentExecutor.java | langchain4j 版 ReAct 预制（对齐 Python `create_react_agent`） |
| `SkillInjector` / `ToolSkillResolver` | langchain4j/langchain4j-agent/.../SkillInjector.java | 工具调用触发的动态技能：激活 id 入 state，body 经上下文注入不入 state |
| `LC4jToolMapBuilder#tool(McpClient)` | langchain4j/langchain4j-core/.../LC4jToolMapBuilder.java:100 | 把 MCP server 工具注册进图 |
| `StreamingChatGenerator` | langchain4j/langchain4j-core/.../generators/StreamingChatGenerator.java | 把 langchain4j token 流转成图内 `StreamingOutput` 事件 |
| `LangGraphStudioServer` | studio/base/.../LangGraphStudioServer.java | 嵌入式流式调试服务器（SSE + 内嵌 webui viewer） |
| `GraphRepresentation.Type{PLANTUML, MERMAID}` | langgraph4j-core/.../GraphRepresentation.java:53 | 图定义导出 PlantUML/Mermaid 源码 |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 |
|---|---|---|---|---|
| 1 | 模型接入 | 🟡 | core 零模型抽象，官方双集成（langchain4j / Spring AI）承载 ChatModel/流式，节点级 RetryPolicy 自带 | langchain4j/langchain4j-agent/.../AgentExecutorBuilder.java#chatModel；langgraph4j-core/.../hook/RetryPolicy.java#asHook |
| 2 | 上下文工程 | 🟡 | ConversationContextPolicy + MessageWindow 窗口裁剪；skill body 走上下文注入不入 state；无 token 预算/摘要 | langgraph4j-core/.../agent/ConversationContextPolicy.java；langchain4j-agent/.../MessageWindowConversationContextPolicy.java |
| 3 | 记忆 | 🔶 | 仅 thread 级 checkpoint 状态（MemorySaver+threadId），无跨线程长期记忆 Store | langgraph4j-core/.../checkpoint/MemorySaver.java；RunnableConfig.java#threadId（无 BaseStore 等价物） |
| 4 | RAG | 🔶 | 框架零 RAG 抽象，how-tos 给 agentic/corrective/adaptive RAG 三种图式模式示例 | how-tos/agentic-rag.ipynb、corrective-rag.ipynb、adaptiverag.ipynb |
| 5 | 工具系统 | ✅ | 工具即图节点：LC4jToolService 执行、MCP 客户端可注册、AgentEx 按工具名分发独立节点；无沙箱/超时/凭据 | langchain4j/langchain4j-core/.../LC4jToolMapBuilder.java#tool(McpClient)；AgentExecutor.java#executeTool |
| 6 | Skill 机制 | ✅ | 独有亮点：core 内置 SkillParser（front-matter）+ 工具触发渐进披露 SkillInjector（id 入 state、body 经上下文） | langgraph4j-core/.../agent/skill/SkillParser.java#getFrontMatter；langchain4j-agent/.../SkillInjector.java |
| 7 | 规划推理 | 🔶 | ReAct 预制（AgentExecutor/AgentEx）为核；plan-and-execute、reflection 仅为 notebook 示例；步数护栏靠 recursionLimit | langchain4j/langchain4j-agent/.../AgentExecutor.java；how-tos/plan-and-execute.ipynb；CompileConfig.java#recursionLimit |
| 8 | 编排 | ✅ | 图/条件边/Command 动态路由/并行分支 allOfFailFast/subgraph 三形态/断点续跑/图导出 PlantUML+Mermaid；无 Send 式 map-reduce | langgraph4j-core/.../StateGraph.java；internal/node/ParallelNode.java#allOfFailFast:96；action/SubCompiledGraphNodeAction.java#resumeSubGraphId |
| 9 | 多 Agent | 🔶 | 无 supervisor/handoff 核心抽象；supervisor 等模式在 how-tos；spring-ai-agent 有 SubAgent 组合件 | how-tos/multi-agent-supervisor.ipynb；spring-ai/spring-ai-agent/.../SubAgent.java、SkilledReactSubAgent.java |
| 10 | 持久化 | ✅ | checkpoint SPI + 内存/文件内置 + 8 个官方外部 saver（含 postgres/redis V2 双代）；getStateHistory/updateState/断点续跑含子图 | langgraph4j-core/.../checkpoint/BaseCheckpointSaver.java；langgraph4j-postgres-saver/.../PostgresSaverV2.java；CompiledGraph.java#updateState:242 |
| 11 | HITL | ✅ | interruptBefore/After/BeforeEdge + 节点内 InterruptibleAction + AgentEx 工具审批节点 + GraphResume 恢复 | langgraph4j-core/.../CompileConfig.java:63-125；agent/AgentEx.java#ApprovalNodeAction；how-tos/wait-user-input.ipynb |
| 12 | 观测评估 | 🟡 | NodeHook/EdgeHook 三段拦截为统一观测点 + 官方 OTEL 模块；无 eval/dataset | langgraph4j-core/.../hook/NodeHook.java；langgraph4j-opentelemetry/.../OTELWrapCallTraceHook.java |
| 13 | 安全治理 | ❌ | 无 guardrail/permission/PII/审计抽象（全仓 grep 零命中），仅 RetryPolicy 属可靠性 | ——（langgraph4j-core 全量检索无 guardrail/permission/pii） |
| 14 | 部署运行时 | 🟡 | Studio 嵌入式调试服务器（jetty/springboot，SSE 流式+webui）+ DSL JSON 导出；无生产 server/cron/queue/docker | studio/base/.../LangGraphStudioServer.java；studio/jetty、studio/springboot；langgraph4j-dsl/.../JsonDslGenerator.java |
| 15 | 管理平面 | ❌ | 无 console/tenant/billing；SQLiteSaverV2Dashboard 仅为 saver 的 thread/tag 查询 API 雏形 | langgraph4j-sqlite-saver/.../SQLiteSaverV2Dashboard.java#ThreadRecord |

## 5. 维度证据明细

**1 模型接入**【核心】`AgentExecutorBuilder#chatModel(ChatModel|StreamingChatModel)`（langchain4j 集成）与 `spring-ai-agent/.../DefaultChatService`（Spring AI 集成）是仅有的两条模型通道；token 级流式经 `StreamingChatGenerator`（onPartialResponse→`StreamingOutput`）灌入图流，`CallModel.java#applySync:123` 统一同步/流式节点动作。节点级重试 `RetryPolicy#asHook`（maxAttempts 默认 3，可配 retryOn）。无 router/fallback/cost 抽象（❌，由 langchain4j 的 FallbackChatModel 等生态件承担）。

**2 上下文工程**【核心】core `agent/ConversationContextPolicy.java` 定义"发模型前如何裁剪/注入消息"的策略接口；langchain4j 侧实现 `MessageWindowConversationContextPolicy`（按消息条数窗口）。`SkillInjector`（类注释明确 "materialize bodies through ConversationContextPolicy (never written into Graph State)"）实现技能正文渐进注入。system prompt 经 `AgentExecutorBuilder#systemMessage`。无 token 计数预算、无自动摘要裁剪（❌）。

**3 记忆**【核心】状态记忆=channel/reducer 归并的不可变 `AgentState` 快照 + `MemorySaver` 按 `RunnableConfig#threadId` 存 checkpoint，跨轮对话靠同 thread resume。跨线程长期记忆（Python `BaseStore`/InMemoryStore 语义记忆）❌ 无对应物。

**4 RAG**【示例】检索器/向量库/rerank 全部 ❌ 在框架内（由 langchain4j 的 `ContentRetriever` 生态承载）；how-tos 用图结构演示 agentic-rag / corrective-rag / adaptiverag 三种路由模式。

**5 工具系统**【核心】langchain4j 工具以 `ToolSpecification+ToolExecutor` 经 `LC4jToolMapBuilder` 注册、`LC4jToolService#execute` 执行（AgentExecutor.java:113 `executeTool`）；`LC4jToolMapBuilder#tool(McpClient):100` 直接挂 MCP server 工具（how-tos/agentexecutor-mcp.ipynb）；core `AgentEx` 把每个工具编译成独立分发节点（tool_name 1..N）。工具 schema/超时/沙箱/凭据治理 ❌（依赖 langchain4j ToolExecutor SPI）。Spring AI 侧对等（`SpringAIToolService`）。

**6 Skill 机制**【核心】Java 图框架中罕见的内置能力：core `SkillParser` 解析 markdown front-matter（name/description/字符串列表），`SkillPath/SkillSource` 为技能来源抽象；集成层 `SkillInjector`（builder 注入 `AgentExecutor.Builder#skillInjector:217`）实现**工具调用触发**的动态技能——工具成功结果 → resolver 解析激活技能 id → `Command#update()` 写入 `State.ACTIVE_SKILLS` channel → 下一轮 call model 时 body 经 ConversationContextPolicy 注入；支持 `UnloadTarget`（call model 后卸载）。Spring AI 侧另有 `SkilledReactSubAgent`/`SkillResource`。

**7 规划推理**【核心+示例】ReAct 有三层预制：core `Agent`（model→action_executor 两节点）→ `AgentEx`（action_dispatcher 每工具一节点 + 审批）→ 集成层 `AgentExecutor`（langchain4j）/`AgentExecutorEx`。plan-and-execute、basic-reflection 是 how-tos 演示的图模式而非抽象；死循环护栏是 `CompileConfig#recursionLimit`（对齐 Python）。结构化输出经 langchain4j `ResponseFormat`（AgentExecutorBuilder:62）。

**8 编排**【核心】`StateGraph`（addNode/addConditionalEdges/addSubgraph:327）→ `compile(CompileConfig)` → `CompiledGraph`。执行引擎 `Emitter`（CompiledGraph.java:589，基于作者自研 `org.bsc.async.AsyncGeneratorFlow`）逐节点推进，非 Pregel superstep；并行分支 `ParallelNode#allOfFailFast:96`（可 `RunnableConfig#addParallelNodeExecutor` 定制线程池）；动态路由 `Command`（节点动作直接返回 goto+update，`nextNodeId:305` 消费）；subgraph 三形态（CompiledGraph / StateGraph / NodeAction，`SubCompiledGraphNodeAction#resumeSubGraphId` 支持子图断点恢复）；图定义可导出 `GraphRepresentation.Type{PLANTUML, MERMAID}`。**无 Python `Send`/map-reduce 动态扇出（❌）**，并行需静态声明。

**9 多 Agent**【示例】supervisor 模式 = how-tos/multi-agent-supervisor.ipynb（addConditionalEdges+子图手工搭建）；官方 `spring-ai-agent` 模块提供 `SubAgent`/`CustomSubAgent` 组合抽象（🟡 边缘）；无 handoff/swarm/A2A 抽象（❌，langchain4j 主库的 agentic-a2a 承担）。

**10 持久化**【核心】`BaseCheckpointSaver` SPI（tag/version/checkpoints，`SubGraphSaver` 嵌套类支持子图存档）；内置 `MemorySaver`/`FileSystemSaver`；官方外部模块 8 个：postgres、sqlite（各有 V2 新代 + Dashboard 查询 API）、oracle、mysql、redis、dynamodb、cockroachdb、hazelcast——**后端数量超过 Python 官方（官方共 3 个后端：InMemory 内置 + postgres/sqlite 两个外部模块）**。恢复链路：`GraphResume` → `CompiledGraph#stream(GraphInput.resume())`，`updateState(config, values, asNode):242` 对齐 Python update_state，`getStateHistory:188` 支持时间旅行（how-tos/time-travel.ipynb）。跨线程 Store ❌。

**11 HITL**【核心】三层：编译期 `CompileConfig` interruptBefore/interruptAfter/**interruptBeforeEdge**（:124，边求值前中断，Python 无此粒度的独立开关）；节点内 `InterruptibleAction#interrupt(nodeId,state,config)` 返回 `InterruptionMetadata` 动态中断（对比 Python `interrupt()` 抛异常+恢复值回填，Java 是接口 opt-in 式，功能对齐风格不同）；预制 `AgentEx.ApprovalNodeAction` 工具调用审批（APPROVAL_RESULT channel + approvalOn(builder) 逐工具配置）。恢复 = 修改状态后 `GraphResume` 续跑。

**12 观测评估**【核心】`NodeHook`/`EdgeHook` 各三段（BeforeCall/AfterCall/WrapCall），可全局或按节点挂载（StateGraph.java:135-190），是重试（RetryPolicy#asHook）、追踪、技能注入的共同底座；`langgraph4j-opentelemetry` 提供 `OTELWrapCallTraceHook`（span 树）+ 内部 OTLP collector（OTELInternalHttpCollector）。无 callback handler 之外的 metrics/eval/dataset（❌）。

**13 安全治理**【核心反证】`grep -ri "guardrail|permission|pii|eval"` 在 langgraph4j-core 零命中；无沙箱（工具直接进程内执行）；无审计日志抽象。❌。

**14 部署运行时**【核心】Studio 是**嵌入式**调试服务器：`studio/base/LangGraphStudioServer`（jakarta servlet、SSE 流式、JSON DSL 图描述、内嵌 webui viewer），jetty/springboot 两种宿主（quarkus 模块存在但已从 modules 注释停用）；`langgraph4j-dsl` 的 `JsonDslGenerator` 把图定义导出 JSON。无独立 dev server、无 production server/queue/cron/docker/helm（❌，Python 有 langgraph-cli + Platform）。另有 `javelit` profile 实验模块（数据应用 UI）。

**15 管理平面**【核心】无 console/tenant/billing/config center（❌）。最接近的是 `SQLiteSaverV2Dashboard`/`PostgresSaverTest` 里的 `JtPostgresSaverDashboardApp`——thread/tag 记录查询 API 与 test 级 dashboard demo，非产品化。

## 6. 设计决策要点

1. **拒绝 Pregel，用拉取式 AsyncGenerator**：执行引擎是作者自研 `org.bsc.async:async-generator` 的 `Emitter`（CompiledGraph.java:589）逐节点循环，而非 Python 的 Pregel superstep 批处理。换来：流式原生（`stream()` 返回可取消 AsyncGenerator，背压友好）、实现简单、并行按节点静态声明；代价：**无 superstep 语义、无 `Send` 动态扇出/map-reduce**——这是与 Python 版最大的能力缺口。
2. **模型生态中立的双轨集成**：core 零模型依赖，官方 langchain4j 与 Spring AI 两套集成模块各自提供 tool service / 消息序列化（Jackson+std 双实现）/ ReAct builder，避免押注单一 Java LLM 框架。
3. **Skill 内置 core 且做成"工具触发 + 渐进披露"**：技能激活 id 走 state channel、正文走 ConversationContextPolicy 注入（SkillInjector javadoc 明确 "never written into Graph State"）， checkpoint 体积不随技能膨胀——比 Python langgraph 仓库内（无 skill 抽象）更早落地 Agent Skills 模式。
4. **Hook 即一切横切面**：NodeHook/EdgeHook 三段拦截统一承载重试、OTEL、技能注入、审批，不引入额外 AOP；`RetryPolicy#asHook` 让重试只是又一个 hook。
5. **HITL 粒度细**：interruptBefore/interruptAfter 之外额外提供 `interruptBeforeEdge`（边求值前停）与接口式节点内中断 `InterruptibleAction`，AgentEx 还把"工具审批"做成预制图节点（Python 需 interrupt()+Command 手工搭）。
6. **checkpoint 后端广度换深度**：8 个外部 saver 超过 Python 官方，但无跨线程 Store/BaseStore（语义记忆缺失）；saver V2 线（postgres/sqlite）+ Dashboard 查询 API 演进中。
7. **单人主导 + 激进迭代风险**：核心流式语义依赖作者个人库 `org.bsc.async`；`@Deprecated(forRemoval)` 常见（InterruptibleAction 旧签名等）；版本策略 1.9-beta 实验线 + 1.8 LTS 分支并行，企业引入需锁版本。

## 7. 跨语言对齐（vs Python langgraph @ e539ac122，2026-09-09）

对齐方法：Java 符号逐条对照 `~/develop/opensource/langgraph/libs/`（langgraph / prebuilt / checkpoint* / cli）目录与关键类名。

| # | 维度 | 对齐状态 | Python 侧 | Java 侧差异 |
|---|---|---|---|---|
| 1 | 模型接入 | 对等 | 框架本身无模型抽象（生态各自接） | 委托 langchain4j/Spring AI，性质相同 |
| 2 | 上下文工程 | 部分 | prebuilt `chat_agent_executor` 内置 trim/消息管理 | 仅 MessageWindow 策略 + skill 注入，无 token 级 trim |
| 3 | 记忆 | **缺失** | `libs/checkpoint/langgraph/store/base`（BaseStore/InMemoryStore 跨线程语义记忆） | 无 Store 等价物 ❌ |
| 4 | RAG | 对等 | 核心亦无 RAG（langchain 生态承载） | how-tos 模式示例对齐 |
| 5 | 工具系统 | 已对齐（机制不同） | `prebuilt/tool_node.py`（ToolNode） | AgentEx 按工具名分发节点 + LC4jToolService；MCP 两边都经外部客户端 |
| 6 | Skill 机制 | **Java 超出** | langgraph 仓库内无 skill 抽象 | core SkillParser + SkillInjector 内置 |
| 7 | 规划推理 | 已对齐 | `prebuilt/chat_agent_executor.py`（create_react_agent） | AgentExecutor/AgentEx 对位；reflection 等两边都是示例 |
| 8 | 编排 | **部分** | `pregel/`（24 文件 superstep 引擎）+ `types.py:704 Send`（map-reduce 扇出）+ Command | 图 API/channel/Command/时间旅行对齐；**无 Pregel、无 Send**，并行仅静态 ParallelNode；Mermaid/PlantUML 双导出（Python 仅 Mermaid） |
| 9 | 多 Agent | 对等（都在核心外） | supervisor/swarm 在独立包 langgraph-supervisor 等（不在本仓库） | how-tos + spring-ai-agent SubAgent |
| 10 | 持久化 | **Java 超出（广度）** | 官方 3 后端（InMemory + checkpoint-postgres/sqlite 两个外部模块） | 官方 8 个外部 saver；updateState/getStateHistory 对齐；**缺 Store（见 #3）** |
| 11 | HITL | 部分 | `types.py:851 interrupt()`（异常式+恢复值）+ `Command(resume=)` + prebuilt/interrupt.py | interruptBefore/After/Edge + 接口式 InterruptibleAction + GraphResume 全链路可用；无函数式 `interrupt()` 等价 API；额外多工具审批预制 |
| 12 | 观测评估 | Java 超出 | 无内置 OTEL（LangSmith 生态 sdk） | 官方 `langgraph4j-opentelemetry` 模块 |
| 13 | 安全治理 | 对等（都 ❌） | 无 guardrail 抽象 | 同 ❌ |
| 14 | 部署运行时 | 部分 | `libs/cli`（langgraph dev + LangGraph Studio）+ `pregel/remote.py`（RemoteGraph 连 Platform） | Studio 是嵌入式进程内服务器（jetty/springboot），非独立 dev server；**无 RemoteGraph/Platform 概念 ❌** |
| 15 | 管理平面 | 对等（都 ❌，Python Platform 为云服务非仓库内） | —— | 同 ❌ |

一句话总结：**图构建/状态归并/checkpoint/时间旅行/HITL 这些 LangGraph 灵魂能力 Java 版已实质对齐（甚至 saver 广度、OTEL、skill、工具审批超出）；引擎层（Pregel/Send/动态扇出）、跨线程 Store、Server 化部署是三大缺口。**
