# 维度 8：编排（Orchestration）

> 本维度回答：框架用什么范式表达「执行流」——图/状态机（graph/state machine）、事件流（event-driven）、还是声明式 DSL；分支/循环/并行的表达力上限在哪（conditional edge、Send 动态扇出、fan-in/join）；子流程边界（subgraph/subflow/subagent）怎么切；代码优先还是可视化优先。17 框架总体格局：**图范式是最大公约数但实现深度三六九等**——只有 langgraph（Pregel/BSP）和 MS agent-framework（RunnerImpl 超步）有真正的批量同步执行引擎；agentscope v2 用「删除组合子」给出了反向教训（细粒度编排 API 生命周期短）；spring-ai 的 advisor 链证明「不做编排」也是一种编排立场；可视化编排只有平台型（dify/saa admin）是生产件，库型框架的可视化基本是调试器（Studio/devui）而非画布。

## 8.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| langchain | 🟡 | 编排引擎整体透传 langgraph：create_agent 构造 StateGraph、中间件钩子编译为图节点；core 仅留 LCEL 组件管道 | libs/langchain_v1/langchain/agents/factory.py#L1187（StateGraph 构造）、:1568（`f"{m.name}.before_agent"` 节点生成）；libs/core/langchain_core/runnables/graph.py |
| langgraph | ✅ | 本仓立身之本：Pregel/BSP 引擎 + Graph/Functional 双 API + Send/Command + subgraph + 并行执行器 | libs/langgraph/langgraph/pregel/main.py#Pregel:450（docstring Plan/Execution/Update 三相）；types.py#Send:704/#Command:799；_algo.py#prepare_next_tasks:349 |
| langgraph4j | ✅ | 图/条件边/Command 动态路由/静态并行（allOfFailFast）/subgraph 三形态/断点续跑 + PlantUML/Mermaid 导出；**无 Send 动态扇出** | langgraph4j-core/.../StateGraph.java；internal/node/ParallelNode.java#allOfFailFast:96（二次核验）；action/SubCompiledGraphNodeAction.java |
| langchain4j | ✅ | 五种固定拓扑 workflow 组合子（sequence/parallel/parallelMapper/loop/conditional）+ 声明式注解 + supervisor；**非自由图**（无 addNode/addEdge 原语） | langchain4j-agentic/.../AgenticServices.java:119-280（七种 builder）；declarative/`@SequenceAgent` 等注解 |
| deepagents | 🟡 | 无自有图抽象，返回 langgraph `CompiledStateGraph`；自有贡献 = 受保护中间件栈装配 + 子代理子图 + 远端 Agent Protocol 委派 | libs/deepagents/deepagents/graph.py#L291（返回类型）、_apply_custom_middleware:204-238；middleware/subagents.py:640 |
| agent-framework (MS) | ✅ | Pregel 超步 Workflow 引擎：builder/fan-out/fan-in/子图（WorkflowExecutor）/函数式双 API/checkpoint/`_viz` 可视化 | python/packages/core/agent_framework/_workflows/_workflow_builder.py#add_edge:230/add_fan_out_edges:282/add_fan_in_edges:511（二次核验）；_runner.py#RunnerImpl:46（"run a workflow in Pregel supersteps"，max_iterations=100） |
| adk-python | ✅ | 2.x 通用图引擎（edges→Graph、DEFAULT_ROUTE 条件路由、JoinNode 汇合、`ctx.run_node()` 动态节点、RetryConfig）+ 经典三 workflow agent 统一进图 + `adk web` | src/google/adk/workflow/_workflow.py#Workflow:147；_graph.py#DEFAULT_ROUTE:91；_join_node.py#JoinNode:32；agents/base_agent.py#L112（`BaseAgent(BaseNode)`，二次核验） |
| adk-java | ✅ | agent 树三件套（Sequential/Parallel/Loop）+ RequestProcessor 管道；无 Python 2.x 的通用 workflow 图 | core/.../agents/{SequentialAgent,ParallelAgent,LoopAgent}.java；flows/llmflows/RequestProcessor.java |
| openai-agents-python | ❌ | 无 Graph/Workflow/Supervisor 类（全库 grep 证实）；分支/循环/并行由用户代码承担，官方 pattern 在 examples | src/agents/extensions/visualization.py#draw_graph:406（只读渲染）；examples/agent_patterns/{routing,parallelization}.py【示例】 |
| claude-agent-sdk-python | ❌ | 线性消息管道；无 graph/workflow/subgraph 抽象；后台任务只是消息语义（task_started/progress 生命周期记账保 stdin 保活） | _internal/query.py#_track_task_lifecycle（全 src 无 workflow/graph 符号） |
| crewAI | ✅ | Flow 事件驱动 DSL（@start/@listen/@router + and_/or_ 条件 + EachAction 声明式循环）+ Crew 双进程（sequential/hierarchical）+ YAML 声明式 + plot-flow | lib/crewai/src/crewai/flow/runtime/__init__.py#Flow:442；runtime/_actions.py#EachAction:313（二次核验）；lib/cli/src/crewai_cli/run_declarative_flow.py |
| dify | ✅ | 引擎外置 graphon==0.7.0（PyPI）+ 平台侧层装饰器（CFS 时间片/暂停持久化）+ 19 种内置节点 + 可视化画布 + DSL 导入导出 | api/pyproject.toml:48（graphon==0.7.0，二次核验）；api/core/workflow/workflow_entry.py#WorkflowEntry；web/app/components/workflow/ |
| llama_index | ✅ | 事件驱动 Workflow/@step/Context（引擎外置为官方包 llama-index-workflows，core 为 1 行 shim）+ AgentWorkflow 六个显式 @step | llama-index-core/.../core/workflow/workflow.py（shim）；agent/workflow/multi_agent_workflow.py 六个 @step（:381/:436/:466/:523/:643/:681，二次核验） |
| agentscope | ✅ | 窄带编排：仅 GoalPipeline（执行者-验证者循环）+ SOPEngine（步骤化 SOP 状态机、断点续跑、每步 attempt 预算）；v1 pipeline 组合子/msghub 已整体删除 | src/agentscope/pipeline/_goal_pipeline.py；sop/_engine.py#SOPEngine:24 |
| agentscope-java | 🔶 | 无图/workflow DSL（v1 pipeline 同步删除）；替代物是 harness 层高层原语（subagent task/team/MessageBus/PeriodicGate 周期唤醒） | rg 全仓无 StateGraph/GraphBuilder 命中；agentscope-harness/.../coordination/PeriodicGate.java、bus/MessageBus.java |
| spring-ai-alibaba | ✅ | graph-core（langgraph4j 合规 fork）+ 新增多路并行边 + flow 四件套 + agent 即图节点 + Studio/Admin 可视化 | spring-ai-alibaba-graph-core/.../StateGraph.java#addParallelConditionalEdges:491 + AsyncMultiCommandAction（二次核验）；agent/flow/agent/{Sequential,Parallel,Loop,LlmRouting}Agent.java |
| spring-ai | 🔶 | advisor 链是唯一管道抽象（call/stream 双链 + Ordered），工具循环 do/while 是唯一内置循环；官方哲学「workflow 用普通 Java 代码组合」 | spring-ai-client-chat/.../advisor/ToolCallingAdvisor.java:149-216（do/while）；docs/.../api/effective-agents.adoc【文档】 |

评级说明：与档案一致，二次核验未推翻任何评级。agentscope(Python) ✅ / agentscope-java 🔶 的差异是「Python 落地了 SOP/GoalPipeline 两个高层模式而 Java 未同步」，属能力面差非评级修正。

## 8.2 实现方式深析

### 8.2.1 三大范式（+第四种「拒绝编排」）

**范式一：图/状态机。** 又分三个子档：

- **Pregel/BSP 引擎档（2 家）**：langgraph `Pregel`（main.py:450）docstring 明确三相超步（Plan/Execution/Update），节点执行期写入互不可见（BSP 屏障）；调度判定 = channel 版本 vs `versions_seen` 差分（`prepare_next_tasks`，_algo.py:349）——天然幂等可恢复。MS agent-framework `RunnerImpl`（_runner.py:46 "A class to run a workflow in Pregel supersteps"，默认 max_iterations=100）每个超步 yield superstep_started/completed 事件并自动落 checkpoint。两家都提供「图 API + 函数式 API」双表面编译到同一引擎（langgraph `@task/@entrypoint` ↔ MS `FunctionalWorkflow`），子图都是普通节点（langgraph 编译图作节点 + `checkpoint_ns` 命名空间 ↔ MS `WorkflowExecutor`）。
- **拉取式逐节点引擎档**：langgraph4j 刻意拒绝 Pregel——执行引擎是作者自研 `org.bsc.async.AsyncGeneratorFlow` 的 `Emitter`（CompiledGraph.java:589）逐节点推进，换来流式原生（`stream()` 返回可取消 AsyncGenerator、背压友好），代价是**无 superstep 语义、无 Send 动态扇出**，并行只能静态声明（`ParallelNode#allOfFailFast`，可用 `RunnableConfig#addParallelNodeExecutor` 定制线程池）。spring-ai-alibaba graph-core fork 后补了 `addParallelConditionalEdges`（AsyncMultiCommandAction 多路分发 → 编译期织入 ConditionalParallelNode，强制单一汇聚点 CompiledGraph.java:179-189）——相当于在 langgraph4j 之上加回了 Send 的静态子集。dify 同属此类：graphon 引擎的 GraphEngine + GraphEngineConfig（min/max workers、scale_up/down 阈值动态线程池）。
- **agent 树档**：adk 的经典三件套（SequentialAgent/ParallelAgent/LoopAgent + ExitLoopTool）是「编排树内节点」而非图；2.x 的关键统一步是 `BaseAgent(BaseNode)`（base_agent.py:112，二次核验）——agent 树与 workflow 图共享同一运行时（`_run_impl` 的 SETUP→LOOP→FINALIZE 编排循环），Sequential/Parallel/Loop 退化为图特例。langchain4j 的五种 workflow 组合子是「固定拓扑嵌套组合」：sequenceBuilder/parallelBuilder/parallelMapperBuilder/loopBuilder/conditionalBuilder（AgenticServices.java:119-280）可任意深度嵌套但无 addNode/addEdge 原语——自由图需求刻意让渡给姊妹项目 langgraph4j。

**范式二：事件流。** crewai Flow 与 llama_index Workflow 同属此类，但深度不同：
- crewai `Flow`（flow/runtime/__init__.py:442）是**事件驱动 DSL**：`@start` 起跑、`@listen` 订阅（支持 and_/or_ 组合条件）、`@router` 按返回值字符串选分支；步骤编译为动作对象（Code/Tool/Crew/Agent/Expression/Script/**Each**——EachAction:313 支持声明式 each 循环与 if_ 条件）。可成环、可分支、可并行（循环语义在事件层而非图引擎层）。配套 `FlowTrackable` 基类 + contextvar 让 Flow 内创建的 Crew/Agent 自动携带 flow_id——两套编排模型正交组合的关键手法。另有 YAML 声明式 Flow（ScriptAction 把 YAML 内嵌 Python 源码 AST 包装执行，默认禁用需 `CREWAI_ALLOW_FLOW_SCRIPT_EXECUTION=1` 显式放行）。
- llama_index Workflow 是**步骤间事件传递**：`@step` 消费/发射 Event，多 agent 编排 `AgentWorkflow` 本身就是六个显式 @step（init_run→setup_agent→run_agent_step→parse_agent_output→call_tool→aggregate_tool_results），每步独立可观测/可中断/可 checkpoint；HITL 也是事件往返（`ctx.wait_for_event` + `InputRequiredEvent`）。引擎本体已外置为官方包 llama-index-workflows（core 只剩 1 行 shim）。
- agentscope(Python) 的 29 个 pydantic 事件类是「观测/协议载体」而非编排 API——v2 删除了 v1 的 sequential/branch/switch pipeline 组合子与 msghub，只留 `GoalPipeline`（executor+verifier 循环）与 `SOPEngine`（SOP=步骤列表 + SOPPhase 状态机 + SOPRunState 断点续跑 + 每步 attempt 预算 + 步骤间 handover；SOPRunState 序列化校验「步骤数变更即报错」）。**这是 17 家中唯一公开「编排 API 做减法」的案例**：设计决策明言细粒度编排 API 生命周期短，通用多 agent 协作改走 A2A 协议 + team 工具。agentscope-java 同步删除 v1 pipeline，替代物全是 harness 高层原语（SubagentsMiddleware 的 task 工具、TeamsMiddleware、MessageBus 异步唤醒、PeriodicGate 周期门 = cron 型常驻 agent 原语）。

**范式三：声明式 DSL / 可视化。** 只有平台型框架把它做成生产件：
- dify：可视化画布（web/app/components/workflow/）+ DSL 导入导出（app_dsl_service.py）是主交互面；19 种内置节点（LLM/TOOL/CODE/HTTP_REQUEST/IF_ELSE/ITERATION/LOOP/QUESTION_CLASSIFIER/PARAMETER_EXTRACTOR/HUMAN_INPUT/ANSWER/VARIABLE_AGGREGATOR/AGENT…）覆盖分支/循环/迭代/并行；引擎本体 1.17 外置为 graphon 库，平台扩展走 GraphEngineLayer 装饰器（TimeSliceLayer CFS 调度、PauseStatePersistenceLayer、ConversationVariablePersistLayer）——「编排引擎可独立演进、平台关注点横切注入」。
- spring-ai-alibaba：admin 前端 spark-flow 画布 + 22 个 NodeDataConverter + DifyDSLAdapter（Dify DSL 迁移吸收存量用户）+ 代码导出；studio 是本地调试 UI（内嵌 agent-chat-ui）。
- MS agent-framework：声明式 YAML 覆盖 agent 与 workflow 定义（packages/declarative，released）；执行还是代码 API，YAML 是部署形态。
- langchain4j：声明式注解（`@SequenceAgent` 等 + Supplier 参数注入）——「interface 即应用」的 Java 式 DSL。
- 库型框架的可视化基本都是**调试器**而非画布：langgraph Studio（闭源平台）/ langgraph4j 嵌入式 Studio（SSE + JSON DSL 导出）/ MS devui（beta，React 前端 + OpenAI 兼容端点）/ adk `adk web`（内置编译好的 React 前端）/ adk-java dev server（REST 无 UI，GraphController 返回 DOT）/ langgraph4j 与 saa 的 Mermaid/PlantUML 文本导出 / MS `_viz.py`（WorkflowViz → graphviz/Mermaid）/ openai-agents `draw_graph()`（graphviz 渲染 handoff 关系，只读）。

**范式四（对照项）：拒绝编排。** spring-ai 官方文档 `effective-agents.adoc` 立场明确——chain/parallelization/routing/orchestrator-workers/evaluator-optimizer 五模式「用普通 Java 代码组合」，仓库只给 advisor 链 + ToolCallingAdvisor 的 do/while（唯一内置循环）。advisor 链本质是**横切关注点管道而非编排**：按 `Ordered` 排序、请求正穿/响应倒穿、链尾固定挂 ChatModelCallAdvisor/StreamAdvisor——它是「LLM 版 HandlerInterceptor」，循环之外的分支/并行/子流程一律留白（留给 spring-ai-alibaba 等衍生）。openai-agents 与 claude-agent-sdk 同立场（❌ 编排）：前者把 pattern 下沉 examples，后者是线性消息管道（后台任务的 task 生命周期只是连接管理，query.py:52 的 DEFERRING_TASK_TYPES 记账为保 stdin）。

### 8.2.2 分支/循环/并行的表达力光谱

| 表达力 | 谁有 | 原语与证据 |
|---|---|---|
| 条件分支 | 几乎所有图/事件框架 | langgraph conditional edge（路由函数返回节点名）/ `Command(goto=)`；adk `DEFAULT_ROUTE`（FunctionNode 返回值选边，_graph.py:91）；langchain4j conditionalBuilder；dify IF_ELSE/QUESTION_CLASSIFIER 节点；crewai @router |
| 静态并行 + 汇合 | langgraph4j（allOfFailFast）、langchain4j parallelBuilder、adk ParallelAgent/JoinNode（_join_node.py:32）、MS add_fan_out_edges/add_fan_in_edges（builder:282/:511）、dify 并行 + VARIABLE_AGGREGATOR、saa ConditionalParallelNode | 汇合语义差异：langgraph4j fail-fast 全体取消；MS fan-in 缓冲进 checkpoint（`_edge_state` 部分填充）支持跨进程恢复 |
| **动态扇出（map-reduce）** | 仅 langgraph（`Send`，types.py:704：边函数返回 N 个 Send 携带独立状态实例化目标节点）+ langchain 继承（Send 分发 tool_calls，factory.py:1964）+ langgraph ToolNode 并行（executor.map:821/gather:858） | langgraph4j ❌、MS 的 fan_out 是编译期声明非运行时动态、crewai 每个监听者独立调用算浅层动态 |
| 循环 | langgraph（图成环 + superstep 计数）、langchain4j loopBuilder + maxIterations=10 + ExitCondition 谓词、adk LoopAgent + ExitLoopTool、dify LOOP/ITERATION 节点、crewai 事件环、agentscope SOP 步骤序列 | 循环出口语义：谓词式（ExitCondition/ExitLoopTool）vs 图条件边式（回边不成立即出） |
| 循环内 HITL/恢复 | langgraph（interrupt + Command(resume)，节点重放）、saa（ResumableSubGraphAction + interruptsBefore/After）、MS（request_info 事件进 checkpoint + IDLE_WITH_PENDING_REQUESTS）、dify（WorkflowPause + PauseStatePersistenceLayer 含响应流位置） | 恢复粒度是编排引擎的试金石：只有带 checkpoint 的图引擎能做「循环第 N 步暂停后跨进程续跑」 |

### 8.2.3 子流程边界：subgraph / subflow / workflow-as-tool

- **subgraph（同一引擎内嵌套）**：langgraph 编译图直接作节点，`get_subgraphs`（main.py:1076）+ `checkpoint_ns` 命名空间隔离；langgraph4j 三形态（CompiledGraph / StateGraph / NodeAction，`SubCompiledGraphNodeAction#resumeSubGraphId` 支持子图断点恢复）；MS `WorkflowExecutor` 子图即普通节点；saa `addNode(id, StateGraph|CompiledGraph)` + agent 子图共享 checkpoint 时 threadId 拼接 `parentId_subGraphId`。
- **workflow-as-tool（跨边界复用）**：dify `workflow_as_tool` + `WORKFLOW_CALL_MAX_DEPTH` 防递归（workflow_entry.py:139-141）——无 SUBWORKFLOW 节点，嵌套全靠工具化；llama_index agent.run 可包成工具（orchestrator 模式）；MS workflow 可暴露为 MCP 工具（hosting-mcp 的 `_workflow_tool.py`）。
- **agent 即节点**：adk 2.x `BaseAgent(BaseNode)`；saa `BaseAgent#asNode()`（BaseAgent.java:49）；langchain create_agent 的 `name` 参数专为子图挂载。
- **远端子流程**：langgraph `RemoteGraph`（pregel/remote.py:118）把部署在 Platform 的图当本地节点；deepagents AsyncSubAgent 经 langgraph_sdk 连远端 Agent Protocol server——「子图边界越过进程」的两条官方通道。

### 8.2.4 代码优先 vs 可视化：一张全景

| 产出 | 框架 | 开源情况 |
|---|---|---|
| 生产级可视化画布（编排主界面） | dify（web 画布 + DSL）、spring-ai-alibaba admin（spark-flow + Dify DSL 迁移） | 开源（dify）/ 开源但独立构建（saa admin ⚠️不在根 modules） |
| 本地开发台（调试器） | adk `adk web`（内置 React 前端）、MS devui（beta 包）、langgraph4j Studio（嵌入式 jetty/springboot）、saa studio（内嵌 agent-chat-ui）、adk-java dev server（REST 无 UI ⚠️是否有外部前端未证实）、langgraph Studio（闭源平台） | 除 langgraph Studio 外开源 |
| 文本导出（Mermaid/PlantUML/DOT） | langgraph4j 与 saa（双格式导出）、MS _viz.py、adk-java GraphController（DOT）、crewai plot-flow、openai-agents draw_graph | 全开源 |
| 声明式定义（YAML/注解） | MS declarative（agent+workflow YAML）、dify DSL、crewai YAML Flow、langchain4j 注解 + adk-java YAML Config Agent（maven_plugin 热重载） | 开源 |

## 8.3 跨语言对齐

| 对 | 维度 8 差异 | 证据 |
|---|---|---|
| langgraph ↔ langgraph4j | 灵魂能力（图构建/状态归并/checkpoint/时间旅行/HITL）实质对齐；**引擎层三大缺口：无 Pregel superstep、无 Send 动态扇出、并行仅静态 ParallelNode**；Java 多 Mermaid+PlantUML 双导出与嵌入式 Studio | CompiledGraph.java#Emitter:589 vs pregel/main.py#Pregel:450；types.py#Send:704 |
| adk-python(2.9) ↔ adk-java(1.9) | Python 2.x 有通用 workflow 图（edges/JoinNode/动态节点/RetryConfig，`BaseAgent(BaseNode)` 统一 agent 树与图）；Java 只有 agent 树三件套 + RequestProcessor 管道，**无通用图**——但注意版本差（Python 领先一个大版本），缺口可能部分是版本而非定位 | workflow/ 包 vs agents/{Sequential,Parallel,Loop}Agent.java；跨语言对齐表「通用 workflow 图：缺失」 |
| agentscope(Python) ↔ agentscope-java | 两侧同步删除 v1 pipeline 组合子/msghub（同一教训）；Python 保留并新增 GoalPipeline + SOPEngine 两个高层模式（断点续跑状态机），Java 无对应物，替代是 subagent task/team/MessageBus/PeriodicGate 高层原语 | pipeline/_goal_pipeline.py + sop/_engine.py vs agentscope-harness/.../coordination/PeriodicGate.java |

## 8.4 取舍与趋势

1. **「删组合子」是 2025-2026 最有信息量的反面教训**：agentscope v1 的 sequential/branch/switch/msghub 在 v2 双语整体删除，替换物是两个高层模式（GoalPipeline/SOP）+ 协作协议（A2A/team 工具）；同期 openai-agents/claude-sdk/spring-ai 从未做过编排，langchain4j 只做固定拓扑组合子。共同的判断：**通用图编排的学习成本与维护成本在「agent 框架」层级不划算**，要么下沉为专职引擎（langgraph/MS workflow/graphon），要么上浮为平台画布（dify/saa admin）。
2. **引擎外置/复用成为分层常规**：dify 把引擎抽成 graphon PyPI 包、llama_index 把 workflow 引擎外置为 llama-index-workflows（core 只剩 shim）、langchain/deepagents 硬依赖 langgraph（版本耦合 `langgraph>=1.2.11,<1.3.0`）、spring-ai-alibaba 合规 fork langgraph4j（LICENSE 明示）——「编排引擎」正在变成可替换的独立资产而非框架私有物。
3. **Pregel/BSP 仍是 durably-executable 编排的唯一成熟答案**：只有 langgraph 与 MS RunnerImpl 有 superstep 屏障 + channel 版本差分调度，因此也只有它们能免费获得「任意步暂停/恢复/time-travel」（配合 checkpoint）；拉取式引擎（langgraph4j Emitter、graphon）换流式简洁，代价是 Send/动态扇出缺失与恢复语义要额外补（saa 在 fork 上补 parallel conditional edges 即此症状）。
4. **「agent 即图节点」成为统一方向**：adk 2.x（BaseAgent extends BaseNode）、saa（asNode()）、langchain（name 参数 + 中间件编译成节点）、MS（AgentExecutor 是图执行器）——编排引擎不再区分「agent 步」与「普通步骤」，多 agent 与 workflow 收敛到同一张图；openai-agents 的 handoff 链与 claude 的 Task 工具是没有图引擎时的两种替代形态。
5. **可视化分裂为「画布（平台）」与「调试器（库）」两个市场**：生产画布只出现在带控制台的平台（dify、saa admin、crewai Enterprise 的闭源 AMP）；库框架普遍提供本地调试台或文本导出（Mermaid/PlantUML/DOT），且倾向把「图定义」导出为可 diff 的文本——代码优先阵营把可视化定位为观测而非创作。
6. **spring-ai 的留白是编排生态的「反面验证」**：官方 effective-agents.adoc 明确把编排留给普通 Java 代码，结果衍生框架 spring-ai-alibaba 直接 fork langgraph4j 补图引擎 + flow 四件套 + admin 画布——「库层不做的，生态层用别人的引擎做」是 Java 生态特有的补位模式。
