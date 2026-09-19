# 维度 7：规划推理（Planning & Reasoning）

> 本维度回答：框架把「思考-行动-观察」循环做到哪一层——任务分解是显式 planner 组件、内嵌 todo 工具还是纯 prompt；谁实现了 ReAct 循环与反思（reflection）；结构化输出走什么 converter 体系；步数/预算超限时是抛异常还是优雅收尾；推理模型（reasoning model）的 thinking/reasoning content 是否一等公民。17 框架的总体格局：**ReAct 循环已是免费日用品**（所有 agent 框架都有某种 model↔tool 循环），分化发生在两端——往上，「显式规划」几乎整体撤退（deepagents 把 write_todos 移出默认栈、crewai 只做 kickoff 前一次性规划），往下，「循环边界的工程学」反而加码（预算三级化、超限优雅收尾、防 busy-loop）。没有一家把 plan-and-execute/reflection 做成核心抽象；它们要么是中间件（langchain）、要么是示例（langgraph）、要么是 contrib 模块（adk-java、langchain4j patterns）。

## 7.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| langchain | 🔶 | agent 主循环（model→tools 节点）+ 四策略结构化输出 + TodoList/调用限额中间件；无显式 planner/reflection 抽象 | libs/langchain_v1/langchain/agents/factory.py#L1831（recursion_limit=9_999）；middleware/todo.py#TodoListMiddleware；agents/structured_output.py |
| langgraph | ✅ | create_react_agent 官方 ReAct 预制 + recursion_limit 预算 + 节点内预算感知；高级规划范式（plan-execute/lats/reflexion/rewoo）全在 examples | libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py#278；libs/langgraph/langgraph/managed/is_last_step.py#IsLastStepManager；examples/（plan-and-execute 等）【示例】 |
| langgraph4j | 🔶 | ReAct 三层预制（Agent/AgentEx/AgentExecutor）；plan-and-execute、reflection 仅 how-tos notebook；护栏 recursionLimit | langchain4j/langchain4j-agent/.../AgentExecutor.java；how-tos/plan-and-execute.ipynb【示例】；langgraph4j-core/.../CompileConfig.java#recursionLimit |
| langchain4j | ✅ | SupervisorPlanner LLM 规划 + maxAgentsInvocations=10 + GOAP/BDI/debate/voting 六 patterns + ServiceOutputParser 按返回 Type 解析 | langchain4j-agentic/.../supervisor/SupervisorPlanner.java#L121；langchain4j-agentic-patterns/.../goap/GoalOrientedPlanner；langchain4j/.../service/output/ServiceOutputParser.java#parse |
| deepagents | 🔶 | write_todos 已移出默认栈（仅 Codex profile 注入）；规划让位于 RubricMiddleware 完成度门槛 + 上下文工程；recursion_limit=9_999 刻意近乎无限 | libs/deepagents/deepagents/profiles/harness/_openai_codex.py#L72（"SDK no longer provides it by default"）；middleware/rubric.py#RubricMiddleware；graph.py#L971 |
| agent-framework (MS) | 🟡 | 结构化输出/ReAct 循环/三级预算齐全，但无独立 Planner 类——规划以 Magentic ledger、harness TodoProvider、loop-judge 三种分散形态存在 | python/packages/core/agent_framework/_tools.py#FunctionInvocationConfiguration（max_iterations/max_function_calls/max_duration_seconds）；orchestrations/.../_magentic.py#MagenticProgressLedger:308 |
| adk-python | ✅ | PlanReActPlanner（ReAct 式计划-执行）+ BuiltInPlanner（Gemini thinking）+ GEPA 提示词优化 + max_llm_calls=500 硬预算 | src/google/adk/planners/plan_re_act_planner.py#L35；flows/llm_flows/_nl_planning.py；agents/run_config.py#L37（_DEFAULT_MAX_LLM_CALLS） |
| adk-java | 🟡 | 核心仅 outputSchema/inputSchema/ExitLoopTool/per-agent maxSteps；五种 LLM 规划器全在 contrib/planners；core 的 `planning` 布尔字段无消费点（二次核验确认） | core/.../tools/ExitLoopTool.java；contrib/planners/.../SupervisorPlanner.java#askLlm；core/.../agents/LlmAgent.java#L756（planning() 仅 getter） |
| openai-agents-python | ✅ | agent loop 本体即 ReAct：strict schema 结构化输出 + max_turns=10 + GPT-5 reasoning effort 默认表 + reasoning content 回放；无 plan/reflect/budget 抽象 | src/agents/run_config.py#L45（DEFAULT_MAX_TURNS）；src/agents/agent_output.py#AgentOutputSchema:61；src/agents/models/default_models.py；models/reasoning_content_replay.py |
| claude-agent-sdk-python | ✅ | thinking 三态（adaptive/enabled/disabled）+ effort 五档 + --json-schema 结构化输出 + 双轨预算（max_budget_usd / task_budget token beta）；循环本体在捆绑 CLI【文档】 | src/claude_agent_sdk/types.py#ThinkingConfig、#EffortLevel:37（low/medium/high/xhigh/max）、#TaskBudget；_internal/transport/subprocess_cli.py#_build_command |
| crewAI | 🟡 | planning=True 仅 kickoff 前一次性分步规划（CrewPlanner，不参与运行时循环）；运行时护栏只有 max_iter=25 截断 + guardrail 重试 | lib/crewai/src/crewai/utilities/planning_handler.py#CrewPlanner:37；agents/agent_builder/base_agent.py#L286（max_iter default=25，二次核验） |
| dify | ✅ | CoT-ReAct（scratchpad）/FC 双策略 + PARAMETER_EXTRACTOR/QUESTION_CLASSIFIER 节点 + LLM 自动生成工作流（ROUTER→PLANNER→BUILDERS）+ ExecutionLimits | api/core/agent/cot_agent_runner.py#CotAgentRunner；core/workflow/generator/runner.py；core/app/layers/（ExecutionLimitsLayer） |
| llama_index | ✅ | 三执行策略（FunctionAgent 原生 FC / ReActAgent 文本协议 / CodeActAgent 写并执行 Python）+ max_iterations=20 + 双路结构化输出 | llama-index-core/.../agent/workflow/{function,react,codeact}_agent.py；base_agent.py#L67（DEFAULT_MAX_ITERATIONS=20）；llms/structured_llm.py#StructuredLLM |
| agentscope | ✅ | ReAct 状态机（_next_action 三态分派）+ max_iters=50 强制总结收尾 + 结构化输出宽限 5 轮 + busy-loop 检测 + TaskTools + GoalPipeline 执行者-验证者循环 | src/agentscope/agent/_agent.py#_reply_impl:1017、_next_action:3491；agent/_config.py#ReActConfig:362（二次核验默认值）；pipeline/_goal_pipeline.py |
| agentscope-java | ✅ | CallExecution reasoning/acting 循环 + maxIters 兜底 summarizing()（先给 pending 工具补 error 再总结）+ 结构化输出 native/工具双路径 + TodoTools + PlanMode | agentscope-core/.../ReActAgent.java#summarizing:3543（二次核验）、#STRUCTURED_OUTPUT_TOOL_NAME:222；agent/config/ReactConfig.java#DEFAULT_MAX_ITERS=20 |
| spring-ai-alibaba | ✅ | ReactAgent（model↔tool 循环图）+ TodoListInterceptor + TaskTool 子代理 + LoopAgent.loopStrategy + BeanOutputConverter 路由决策 | spring-ai-alibaba-agent-framework/.../agent/interceptor/todolist/TodoListInterceptor.java；tools/task/TaskTool.java；flow/node/RoutingNode.java#L91 |
| spring-ai | 🔶 | 无 plan/ReAct 显式抽象（agentic 五模式仅文档+外部示例仓）；强项是结构化输出（BeanOutputConverter + 校验自纠错 advisor）与 40/150 工具限额 | spring-ai-model/.../converter/BeanOutputConverter.java；spring-ai-client-chat/.../advisor/StructuredOutputValidationAdvisor.java#L64（二次核验）；model/tool/DefaultToolCallingManager.java#L100/L107 |

评级说明：与档案无冲突（二次核验未推翻任何评级）；agent-framework 维持档案的 🟡（能力齐全但「规划」无正式抽象、分散三处）；adk-java 维持 🟡（planners 在 contrib、core 的 planning 字段空挂）。

## 7.2 实现方式深析

### 7.2.1 任务分解的三种形态：显式 planner / 内嵌 todo 工具 / 纯 prompt 撤退

**显式 planner 组件**（有独立类、接受任务产出计划）只有四家，且没有一家放在「核心必选」位置：

- **langchain4j**：`SupervisorPlanner` 是最完整的规划器——LLM 决定「下一步调哪个子 agent」，配套 `maxAgentsInvocations`（默认 10，`SupervisorAgentServiceImpl.java:31` 二次核验）与 `ResponseAgent`+`ResponseScore` 对子答案评分选优；更有 `langchain4j-agentic-patterns` 的 `GoalOrientedPlanner`（GOAP：`DependencyGraphSearch` 目标分解）、`BDIPlanner`（Desire）、`DebatePlanner`（ConvergenceStrategy）——17 家中唯一把经典规划算法做成官方模块的。
- **adk-java**：`contrib/planners` 提供 Planner 接口 + Sequential/Parallel/Loop/Supervisor/P2P 五种规划器与 `PlannerAgent`（自带规划循环，PlannerAgent.java:102-109）。注意二次核验确认：core 的 `LlmAgent.planning` 布尔字段（LlmAgent.java:100/756）**在 core 内零消费**（仅 getter，rg 全仓无 `.planning()` 调用点），是「字段先行、实现留在 contrib」的半成品。
- **crewai**：`CrewPlanner`（utilities/planning_handler.py:37）是**预执行一次性规划**——kickoff 前造一个 "Task Execution Planner" agent 为每个 Task 生成 step-by-step 计划（`PlanPerTask` Pydantic）注入任务描述，之后不再参与循环。这是「静态计划注入」而非运行时重规划。
- **dify**：规划被节点化/产品化——`PARAMETER_EXTRACTOR`（参数抽取）与 `QUESTION_CLASSIFIER`（语义路由）是图上的标准节点（json-repair 修 LLM 输出）；更进一步，`core/workflow/generator/runner.py` 用 LLM **生成整张工作流**（ROUTER→PLANNER→并行 BUILDERS→POSTPROC，web 端 cmd+K `/create` 入口）——「规划即建图」的平台路线。

**内嵌 todo 工具**（把计划做成 agent 可读写的状态 + 工具，模型自管理）是当前主流落地形态：

- langchain `TodoListMiddleware`（PlanningState 的 todo 读写，middleware/todo.py:174）——中间件形态，可插拔；
- agent-framework `_harness/_todo.py` 的 `TodoProvider`（TodoItem），由 `create_harness_agent` 打包进 harness；
- agentscope `tool/_task/` 的 TaskCreate/Get/List/Update 四工具 + 任务状态经 `InjectionConfig` 运行态注入；agentscope-java `builtin/TodoTools` + harness `PlanModeMiddleware`（PlanMode 是 Claude Code 式「只规划不执行」模式）；
- spring-ai-alibaba `TodoListInterceptor`（system prompt 注入 todo 指引 + `WriteTodosTool`）；
- adk-java/python 无 todo 工具（ADK 的规划走 planner 路线）。

**纯 prompt / 撤退**：deepagents 是标志性案例——0.7.x 把 `write_todos` **移出默认栈**，`_openai_codex.py:72-77` 明言 "the SDK no longer provides it by default"，仅 Codex profile 以 `extra_middleware=[TodoListMiddleware()]` 注入并配套 Plan Hygiene 提示词。设计决策原文：「从 harness 强加规划转向按模型训练偏好按需装配」。spring-ai、openai-agents 则根本没有规划概念（官方立场：reasoning model 自带规划能力，框架只管循环与预算）。

### 7.2.2 ReAct 循环与反思：谁在实现 thinking-acting-observation

按「循环宿主」分四个派系：

**派系一：图引擎上的 ReAct 预制件**（循环 = 图上两个节点来回的边）。
langgraph `create_react_agent`（chat_agent_executor.py:278）编译出 model 节点 ↔ ToolNode 循环；langchain 1.x `create_agent` 同构（factory.py:1543 model 节点、:1547 tools 节点，`Send` 并行分发 tool_calls）；langgraph4j `Agent`（两节点）→ `AgentEx`（action_dispatcher 每工具一节点 + 审批节点）→ `AgentExecutor`（langchain4j 集成）三层预制；spring-ai-alibaba `ReactAgent.initGraph` 组 `AGENT_MODEL_NAME`→`AGENT_TOOL_NAME` 循环图（ReactAgent.java:311-405）。这一派的循环边界控制天然继承图引擎（recursion_limit），优点是循环的每一步可 checkpoint/可 interrupt。

**派系二：解释器内嵌 ReAct 状态机**（循环 = 解释器 while/do-while）。
agentscope 最精细：`_reply_impl`（_agent.py:1017）while 循环内 `_next_action`（:3491）返回 `Reasoning | Acting | Exit` 三态分派，且「一轮 reasoning+acting 的全部工具调用有结果才 `cur_iter += 1`」——迭代计数语义明确；agentscope-java `CallExecution.executeIteration(0)→reasoning(iter)→acting(iter)→executeIteration(iter+1)`（ReActAgent.java:2295/2306/2757）。openai-agents `AgentRunner.run` + `run_internal/run_loop.py`（2683 行）解析工具/handoff 后进入下一轮。MS agent-framework `FunctionInvocationLayer`（_tools.py:3446）迭代循环 + 三级预算。adk 的 `BaseLlmFlow`/`SingleFlow`/`AutoFlow` 是「执行流 + RequestProcessor 管道」形态。crewai `CrewAgentExecutor` 有双模式：native tool-calling 优先、失败自动降级 ReAct 文本模式（crew_agent_executor.py:600）——17 家中唯一保留文本 ReAct 协议降级路径的。llama_index 三策略并存（FunctionAgent/ReActAgent/CodeActAgent），其中 ReActAgent 仍用 Thought/Action 文本协议。langchain4j `ToolService.executeInferenceAndToolsLoop`（:599，:637 `while(true)`）。claude-agent-sdk 循环本体在捆绑 CLI 二进制内（【文档】级证据）。

**派系三：平台节点化的推理**。dify 把 ReAct 做成 AgentRunner 策略（CotAgentRunner 的 `AgentScratchpadUnit` + Observation stop 词）而非库抽象。

**反思（reflection）**：没有一家做成核心抽象，但存在四个正式实现：
- deepagents `RubricMiddleware`：模型每次想结束（无 tool_calls）时由独立 grader 子代理复审 transcript，`needs_revision` 则注入 HumanMessage 反馈续跑，直到 satisfied/failed/max_iterations——「完成度门槛」；
- agentscope `GoalPipeline`：executor 报告 → verifier 判 pass/fail/impossible（max_iters=10、每 agent 结构化输出 max_retries=3）——执行者-验证者循环；
- MS `MagenticProgressLedger`（orchestrations/_magentic.py:308）：任务分解 + 复盘重规划（AutoGen Magentic 血统）；
- spring-ai `StructuredOutputValidationAdvisor`（L64）：按 schema 校验响应、失败把错误追加进 user message 重调模型（maxRepeatAttempts 次）——输出级自纠错回路。
其余框架的反思 = 提示词 + 重试（langgraph examples/lats、reflexion；llama_index RetryQueryEngine；adk-python reflect_retry 是 plugin 不是核心）。

### 7.2.3 结构化输出：四种 converter 体系

| 体系 | 代表 | 机制 |
|---|---|---|
| 策略对象派 | langchain/deepagents：`response_format` 四 overload（ToolStrategy/ProviderStrategy/AutoStrategy/raw dict） | 按 `ModelProfile` 能力元数据决定走 provider 原生 JSON mode 还是合成工具 |
| 严格 schema + 校验派 | openai-agents `AgentOutputSchema`（strict 默认开启、非对象类型自动包 `{"response":...}` 包装层、`validate_json` 脱敏报错）；spring-ai `BeanOutputConverter`（JSON Schema 生成 + 反序列化 + 2.0 `ThinkingTagCleaner` 清理思考标签）+ `StructuredOutputValidationAdvisor` 自纠错重试 | 把 schema 推到模型 + 失败进入修复回路 |
| 动态工具注入派 | agentscope `_GenerateStructuredOutput`（到期 `tool_choice` 强制调用 + `structured_output_grace_iters=5` 超限宽限，_config.py:373）；agentscope-java native `responseFormat` 不支持时回退注入 `generate_response` 合成工具（doFallbackStructuredCall:1340）；langchain ToolStrategy 同思路 | 结构化输出=一个被强制调用的工具 |
| 声明式/平台派 | langchain4j `ServiceOutputParser.parse` 按方法返回 Type（POJO/枚举/BigDecimal…）解析 + `ResponseFormat`；adk `output_schema`（Pydantic→Schema，且支持与 tools 并用 + `_model_response_finalizer` 兜底）；adk-java outputSchema 经 SchemaUtils 校验入 state；spring-ai-alibaba `Builder#outputType(Class)` → BeanOutputConverter；claude `output_format json_schema` → `--json-schema` 结果回 `ResultMessage.structured_output`；dify PARAMETER_EXTRACTOR 节点 + json-repair；MS `ChatOptions.response_format`（ADR-0036） | 类型声明由接口/节点参数承载 |

值得注意的工程细节：agentscope 结构化输出与预算的交互是独有设计——`max_iters` 用尽但结构化输出未完成时，还有 5 轮 grace（`tool_choice` 强制指定输出工具）；agentscope 模型层另有原生 `generate_structured_output` 失败降级策略 `_get_structured_output_fallback_exceptions`（含「关 thinking 重试」）。

### 7.2.4 步数/预算控制：超限是抛异常还是优雅收尾（二次核验表）

这是本维度语义差异最大的一块，17 家可归为三档：

| 框架 | 控制项（符号） | 默认值（二次核验） | 超限行为 |
|---|---|---|---|
| langgraph | `recursion_limit`（config） | 引擎自身 ensure_config 默认 **10007**（`_internal/_config.py:32`，env `LANGGRAPH_DEFAULT_RECURSION_LIMIT`；langchain-core LCEL 路径默认 25） | **抛 `GraphRecursionError`**（main.py:3011，含「调大 limit」提示）；节点内可经 `IsLastStepManager` 感知预算主动收敛 |
| langchain | recursion_limit（factory 显式设置） | **9_999**（factory.py:1831） | 继承 langgraph 抛异常；另有 `ModelCallLimitMiddleware`/`ToolCallLimitMiddleware` 限额 |
| deepagents | recursion_limit | **9_999**（graph.py:971） | 刻意近乎无限——靠上下文工程（摘要/驱逐/rubric）而非预算终止 |
| langgraph4j | `CompileConfig.recursionLimit` | 图引擎 Emitter 内 `++iteration > maxIterations` → **`IllegalStateException`**（CompiledGraph.java:871，二次核验：非类型化异常，直接进流错误通道） | 异常收尾 |
| spring-ai-alibaba | recursionLimit | 默认 25（CompiledGraph.java:90） | 异常收尾（继承 fork 自 langgraph4j 的图守卫） |
| openai-agents | `max_turns` | **10**（run_config.py:45） | 默认抛 `MaxTurnsExceeded`；**可经 `error_handlers["max_turns"]` 接管产出最终结果**（run_loop.py:1583-1605，二次核验）——混合式 |
| MS agent-framework | `max_iterations`（LLM 轮）/ `max_function_calls`（工具次）/ `max_duration_seconds`（墙钟） | 均 None（unbounded）可配 | **优雅降级**：触发后停工具「迫使模型产出文本回复」（_tools.py:1434-1475 docstring 明示 best-effort：批后检查、审批等待时间计入墙钟）；外层 harness `AgentLoopMiddleware` DEFAULT_MAX_ITERATIONS=10（_loop.py:124） |
| adk-python | `RunConfig.max_llm_calls` | **500**（run_config.py:37，env `ADK_MAX_LLM_CALLS`） | **硬停抛 `LlmCallsLimitExceededError`**（invocation_context.py:68 每次调用前强制，二次核验）；语义终止靠 `is_final_response`；LoopAgent 另有 max_iterations |
| adk-java | `RunConfig.maxLlmCalls` + per-agent `maxSteps` | 500 + None | 同 Python 硬停 |
| agentscope | `ReActConfig.max_iters` | **50**（_config.py:367） | **优雅收尾**：`cur_iter == max_iters` 时强制一次「总结收尾」调用（`tool_choice="none"` + system-reminder hint，_agent.py:3695），`>= max_iters` 标 EXCEED_MAX_ITERS 终态；另有 busy-loop 检测（ReplyEndEvent 两轮无进展即 raise）、`structured_output_grace_iters=5`、`ReplyBudgetControlMiddleware` token 预算 |
| agentscope-java | `maxIters` | **双默认值**：Builder 默认 10（ReActAgent.java:4565）vs `ReactConfig.DEFAULT_MAX_ITERS = 20`（ReactConfig.java:33）——二次核验确认不一致，易混淆 | **优雅收尾**：`summarizing()`（:3543）先给 pending 工具补 error 结果再生成总结 |
| crewai | `Agent.max_iter` | **25**（agents/agent_builder/base_agent.py:286，二次核验） | **优雅收尾**：`handle_max_iterations_exceeded` 再做一次 LLM 调用拿最终答案（agent_utils.py:384 docstring 明示） |
| claude-agent-sdk | `max_turns` + `max_budget_usd`（USD）+ `task_budget`（token，beta `task-budgets-2026-03-13`） | — | USD 超限返回 error_max_budget_usd 错误结果；唯一把**钱**做成一等预算的 |
| langchain4j | `maxToolCallingRoundTrips` / `LoopAgent.maxIterations` / `maxAgentsInvocations` | **100**（ToolService.java:133）/ **10**（declarative/LoopAgent.java:77）/ **10**（SupervisorAgentServiceImpl.java:31） | 三层护栏；LoopAgent 配 `ExitCondition` 谓词优雅退出 |
| llama_index | `max_iterations`（ctx.store） | **20**（base_agent.py:67） | 每步检查终止 |
| dify | ExecutionLimitsLayer（max_steps/max_time）+ AgentMaxIterationError | WORKFLOW_MAX_EXECUTION_STEPS 环境级 | 平台级限流（配合 CFS 时间片）；Agent 迭代上限抛错 |
| spring-ai | `ToolCallLimits`：每工具 40 / 全局 150 | 40/150（DefaultToolCallingManager.java:100/107，默认 `ToolCallLimitBehavior.THROW`） | **双策略**：THROW（异常带已执行工具清单）或 RETURN_ERROR_RESPONSE（跳过执行、拒绝信息回喂模型继续） |

三个档次：**硬停抛异常**（langgraph 系、adk、dify）——把失控当错误，交上层重试逻辑；**优雅收尾**（agentscope 双语、crewai、MS、spring-ai 的 RETURN_ERROR_RESPONSE）——超限后强制/诱导模型产出最终答案，把预算变成软约束；**混合**（openai-agents 默认异常 + handler 接管；spring-ai 可配置）。工程上最讲究的是 MS：三个正交预算轴（轮数/工具次数/墙钟）+ 明示 best-effort 语义（批后检查、20 个并行调用在 limit=10 时仍会全部执行）。adk-python 的 `_InvocationCostManager` 在**每次 LLM 调用前**检查（真正的先验硬停），与 MS 的批后检查形成对照。

### 7.2.5 推理模型支持：reasoning content 的透传

- **消息块一等公民**：agentscope `Msg` 块模型含 `ThinkingBlock`（message/_block.py:26）；langchain-core 有 `reasoning` 内容块类型（`type: Literal["reasoning"]`，messages/content.py:468）+ `create_reasoning_block` 工厂（:1363）+ `usage` 中 reasoning token 细分；openai-agents `Usage` 含 reasoning_tokens 并有 `models/reasoning_content_replay.py`（跨轮回放 reasoning item 以满足 Responses API 的 reasoning 复用要求）。
- **控制面参数化**：claude-agent-sdk 最全——`ThinkingConfig` 三态（adaptive 让 Opus 4.6+ 自决 / enabled+budget_tokens / disabled）+ `display: summarized|omitted` + `EffortLevel` 五档（low/medium/high/xhigh/max，types.py:37，二次核验）；openai-agents `ModelSettings.reasoning`（effort/summary）+ GPT-5.x 按模型名自动默认 effort；adk-python `BuiltInPlanner` 用 Gemini thinking_config。
- **分析与消费**：crewai `AgentReasoning`（utilities/reasoning_handler.py:107）把思考过程结构化为 ReasoningPlan/AgentReasoningOutput 供展示与评估；spring-ai 2.0 converter 家族加 `ThinkingTagCleaner`（清 `<think>` 类标签再解析结构化输出）；MS `_compaction.group_messages` 把 reasoning 消息与工具调用成组配对（防止压缩撕裂 thinking-tool 对）。
- **降级重试**：agentscope 结构化输出失败降级策略含「关 thinking 重试」——reasoning 模式与 JSON 输出的冲突已被显式处理。

## 7.3 跨语言对齐

| 对 | 维度 7 差异 | 证据 |
|---|---|---|
| langgraph ↔ langgraph4j | ReAct 预制对位（create_react_agent ↔ AgentExecutor/AgentEx）；两边高级规划范式都是示例级（examples ↔ how-tos）。差异在超限行为：Python 抛类型化 `GraphRecursionError`，Java 是裸 `IllegalStateException` 进流错误通道（CompiledGraph.java:871）。Java 多出工具审批预制（AgentEx.ApprovalNodeAction） | 二次核验两侧源码 |
| adk-python(2.9) ↔ adk-java(1.9) | Python 有 `planners/`（PlanReActPlanner/BuiltInPlanner 接 `LlmAgent.planner` 字段，核心内）；Java 规划器全在 contrib/planners 且 core 的 `planning` 布尔无消费（半成品）。Python 另有 GEPA 提示词优化（optimization/）Java 无。结构化输出两侧对齐（output_schema ↔ outputSchema）。预算护栏同构（max_llm_calls=500 双侧） | core/planners vs contrib/planners；LlmAgent.java:756 |
| agentscope(Python) ↔ agentscope-java | 循环骨架同构（三态分派 ↔ reasoning/acting 交替）。差异四点：① max_iters 默认 50 vs 10/20 双默认（Java 双轨易混淆）；② Python 有 `structured_output_grace_iters=5`，Java 无等价物但多 native responseFormat 直连路径；③ Python 有 GoalPipeline 反思循环，Java 无（对齐表「缺失」）；④ Java 多 PlanModeMiddleware + TodoTools 的 Claude Code 式规划模式 | _config.py:362-395 vs ReactConfig.java:30-40、ReActAgent.java:4565 |

## 7.4 取舍与趋势

1. **「显式规划」整体退潮，todo 工具成为残余形态**：deepagents 移除 write_todos 默认注入（按模型训练偏好按需装配）、langgraph/langchain 把 plan-and-execute 留在 examples/中间件、crewai 只做 kickoff 前一次性规划、openai-agents/spring-ai 完全不做——共同假设是「推理模型自带规划，框架强加计划结构反而干扰」。反例是 Java 阵营（langchain4j GOAP/BDI、adk-java contrib planners）：企业栈仍需要可审计的显式计划。
2. **预算从单一计数走向多维正交**：MS 三轴（轮/工具次/墙钟，且明示 best-effort 与审批计时语义）、claude 双轨（轮数 + USD 金额 + token task_budget）、spring-ai 双粒度（每工具 40/全局 150）——「防失控」从步数单一维度扩展为成本、时间、调用次数的组合治理。
3. **超限行为分化为「异常派 vs 收尾派」，收尾派在增多**：agentscope 双语、crewai、MS 的 graceful degradation 都选择「强迫模型给最终答案」而非抛异常——生产视角下异常丢失已产生价值的部分输出，收尾至少带回部分结果；langgraph/adk 坚持异常派，理由是失败应显式上浮（配合 checkpoint 重试）。
4. **结构化输出收敛到「工具注入 + 强制调用」与「provider 原生 + 降级」两条路**，且越来越多框架两者都做（agentscope 双路径、langchain 三策略、agentscope-java native+fallback）——因为 provider JSON mode 能力参差（ModelProfile 元数据化）与 reasoning 模式冲突（关 thinking 重试）都需要降级链。
5. **循环边界控制的「感知化」**：langgraph `IsLastStepManager`/`RemainingStepsManager` 让 agent 在最后一步主动收敛、agentscope 的迭代计数语义（全部工具结果到齐才计数）与 busy-loop 检测、adk 的 cost manager 前置检查——预算不再只是熔断器，而是注入循环的可观测状态。
6. **默认预算值差异巨大且无共识**：同为主流 agent 循环，默认上限从 10（openai-agents max_turns、agentscope-java builder）到 25（crewai、langchain-core LCEL）到 50（agentscope）到 100（langchain4j tool roundtrips）到 500（adk llm calls）到 9999/10007（langchain/deepagents/langgraph ensure_config）——反映「一轮」的定义本身不统一（turn / superstep / 工具轮 / LLM 调用），选型时必须按自家语义换算。
