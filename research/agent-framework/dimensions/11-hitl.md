# 维度 11：HITL（人机协同，Human-in-the-Loop）

> 本维度回答：**agent 停下来等人的机制是什么、审批到什么粒度、人答完怎么续、要不要转人工/收表单**。17 框架中 16 家具备某种 HITL（唯 spring-ai 官方刻意留白），但中断原语分四种范式：**异常式 interrupt**（langgraph 系，节点从头重放）、**终态式**（agentscope-java PERMISSION_ASKING、MS IDLE_WITH_PENDING_REQUESTS——把"等人"做成一次调用的正常返回值）、**事件往返式**（agentscope Require 事件、llama_index wait_for_event、MS request_info）、**回调审批式**（claude-sdk can_use_tool 反向 RPC）。往细看有两条清晰合流：审批暂停正在与持久化合流（pending 审批进 checkpoint/session，人机协同与容错同通道）；粒度正从工具级下沉到参数级/路径语义级，并配套绕过防御与粘性授权。

## 11.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| langchain | ✅ | HumanInTheLoopMiddleware 按工具名 intercept + when 谓词 + approve/edit/reject/respond 四决策；底层透传 langgraph interrupt | libs/langchain_v1/langchain/agents/middleware/human_in_the_loop.py#HumanInTheLoopMiddleware(:219)、#DecisionType(:51，已核实) |
| langgraph | ✅ | `interrupt()` 异常冒泡 + PregelScratchpad 顺序匹配 + `Command(resume=)` 回填；静态 interrupt_before/after（含 `"*"`） | libs/langgraph/langgraph/types.py#interrupt(:851)；_internal/_scratchpad.py#PregelScratchpad(:9)；graph/state.py:1183-1264 |
| langgraph4j | ✅ | interruptBefore/After/**interruptBeforeEdge** + 接口式 InterruptibleAction + AgentEx 审批预制节点 + GraphResume 恢复 | langgraph4j-core/.../CompileConfig.java:63-125；agent/AgentEx.java#ApprovalNodeAction；action/InterruptibleAction.java:60 |
| langchain4j | ✅ | 双形态：responseProvider 同步注入 + AgenticSystemSuspendedException 挂起检查点/恢复（支持嵌套挂起） | langchain4j-agentic/.../workflow/HumanInTheLoop.java；scope/AgenticSystemSuspendedException.java；AgenticScope.java#completePendingResponse(:191，已核实) |
| deepagents | ✅ | interrupt_on 透传 + permissions=interrupt 自动合成 when 谓词（exact/bulk 工具语义、堵 path="." 与 glob 绕过） | libs/deepagents/deepagents/middleware/_fs_interrupt.py:31（`ToolScope = Literal["exact","bulk"]`，:38-41 工具表已核实）；graph.py:916-921 |
| agent-framework | ✅ | ctx.request_info() + IDLE_WITH_PENDING_REQUESTS 终态 + run(responses=) 续跑；pending 请求入 checkpoint；工具审批三层 | python/packages/core/agent_framework/_workflows/_events.py:88；_checkpoint.py#pending_request_info_events(:92，已核实)；_harness/_tool_approval.py#ToolApprovalRule(:86) |
| adk-python | ✅ | NodeInterruptedError(BaseException) 节点中断 + request_confirmation 处理器（adk_request_confirmation 工具）+ resume_inputs 恢复 + UiWidget | workflow/_errors.py:22；flows/llm_flows/request_confirmation.py:259；runners.py#_extract_resume_inputs(:605，已核实)；events/ui_widget.py:25 |
| adk-java | ✅ | adk_request_confirmation 函数调用 + 工具级 requireConfirmation 构造参数 + RequestConfirmationLlmRequestProcessor 从历史接管 + 长任务暂停 | core/.../flows/llmflows/Functions.java:71；tools/FunctionTool.java:58；events/ToolConfirmation |
| openai-agents-python | ✅ | needs_approval 覆盖全部工具面 → interruptions 中断列表 → RunState.approve/reject/**always_approve 粘性决策**跨序列化存活 | src/agents/items.py#ToolApprovalItem(:556)；run_state.py#approve(:1295，已核实)；docs/human_in_the_loop.md |
| claude-agent-sdk-python | ✅ | can_use_tool 审批回调（可改输入 updatedInput、运行时增删权限规则 updatedPermissions）+ 6 种 permission_mode + PreToolUse hook allow/deny/ask/**defer** | types.py#_configure_can_use_tool、#PermissionResultAllow(:116-197)；#DeferredToolUse(:1279)；query.py#_handle_control_request(:478) |
| crewai | ✅ | human_input **答案后反馈循环**（非前置审批）+ HumanInputProvider Protocol 可换企业审批通道 + Flow 级 LLM 辅助人审蒸馏 | lib/crewai/src/crewai/agents/crew_agent_executor.py:1625；core/providers/human_input.py#HumanInputProvider(:60)；flow/human_feedback.py#DistilledLessons(:226) |
| dify | ✅ | HUMAN_INPUT 表单节点 + Agent ask_human 延迟工具映射同一表单路径 + 超时任务 + 多通道投递/恢复（SSE） | api/core/workflow/nodes/human_input/；nodes/agent_v2/ask_human_hitl.py（ENG-636 模块头已核实）；models/human_input.py#HumanInputForm(:28) |
| llama_index | ✅ | InputRequiredEvent/HumanResponseEvent 内置事件对 + ctx.wait_for_event(requirements 匹配) 阻塞等待审批 | llama-index-core/llama_index/core/workflow/events.py:6-7；docs/…/agent/human_in_the_loop.md |
| agentscope | ✅ | 全事件化：RequireUserConfirm/RequireExternalExecution/UserInterrupt 三类挂起事件 + Result 事件重入 + parked 跨进程恢复 + AskUser 多选题工具 | src/agentscope/event/_event.py:443/:456（已核实）；app/_service/_session.py#derive_parked_status(:212，已核实)；tool/_builtin/_ask_user.py#AskUser(:150) |
| agentscope-java | ✅ | 权限 ASK → ToolSuspendException → **PERMISSION_ASKING 终态**返回；二次 call 携 ConfirmResult 校验续跑；dataplane 跨进程审批协调 | agentscope-core/.../ReActAgent.java:2803/:2910（已核实）；tool/ToolSuspendException.java；event/ConfirmResult.java；service-dataplane/.../ToolConfirmationCoordinator.java |
| spring-ai-alibaba | ✅ | 图层 interruptsBefore/After+withResume；agent 层 HumanInTheLoopHook 三态反馈（APPROVED/EDITED 改参/REJECTED）+ 可替换 Handler | spring-ai-alibaba-graph-core/.../CompiledGraph.java:429-443；agent-framework/.../hook/hip/HumanInTheLoopHook.java:99-106（三态已核实）；hip/HumanInteractionHandler.java |
| spring-ai | ❌ | 无 interrupt/approve/resume 任何抽象；最接近物是 MCP 协议层 @McpElicitation（server 向 client 征询，非流程级） | 全仓 rg `human.in.the.loop\|interrupt\|approval` 零命中；mcp/mcp-annotations/.../McpElicitation.java |

评级全部沿用档案（本维度无存疑项；adk-java/agentscope-java 的关键符号已逐一回源码核实）。

## 11.2 实现方式深析

### 范式一：异常式 interrupt + scratchpad（langgraph 系）

**langgraph** 是该范式定义者：节点内调 `interrupt(value)`（types.py:851）首次抛 `GraphInterrupt`（errors.py:102）冒泡终止整个 run；恢复时 resume 值经 `Command(resume=...)` 传入，**节点从头重放**、多次 interrupt 按**任务内顺序**匹配——当前实现走 `PregelScratchpad`（_internal/_scratchpad.py:9，interrupt_counter + resume 列表），1.x 已从早期 `__resume__` 保留 channel 方案演进。两个隐含契约：强依赖 checkpointer（interrupt 文档明言）；节点必须确定性可重放。静态打断是编译期参数 `compile(interrupt_before=/interrupt_after=)`（graph/state.py:1183-1264，支持 `"*"` 全节点）。

**langchain** 在其上做产品化包装：`HumanInTheLoopMiddleware`（human_in_the_loop.py:219）按工具名 intercept，`when: Callable[[ToolCallRequest], bool]` 谓词(:195)过滤，决策集 `DecisionType = Literal["approve","edit","reject","respond"]`（:51，已核实）——edit 直接改写工具参数后放行。MCP elicitation（服务器向人要输入）复用同一 interrupt 语义按序匹配（mcp/elicitation.py:23）。

**deepagents** 的增量在**谓词合成的语义正确性**：`permissions` 的 interrupt 模式自动合成 `interrupt_on`，每文件工具按语义分 `exact`（read_file/write_file/edit_file 按精确路径）与 `bulk`（ls/glob/grep 按搜索子树与规则锚点是否相交；无 path 参数无条件触发）（_fs_interrupt.py:31-41 工具表已核实）。绕过防御成体系：`path="."` 归一为 `/` 防跳过(:119-125)、glob 绝对 pattern 可改搜索根故单独 gate(:126-135)、相对 pattern 含 `..` 视为触发(:140-153)。决策集四项全开，人类始终是授权门(:169-174)。

**spring-ai-alibaba** 双层：图层沿用 langgraph4j 的 interruptsBefore/After + withResume；agent 层 `HumanInTheLoopHook`（@HookPositions(AFTER_MODEL)）按 toolCall 处理三态——APPROVED 放行 / EDITED 改参重写（用 `RemoveByHash` 精确替换消息）/ REJECTED 注入拒绝说明的 ToolResponse（HumanInTheLoopHook.java:99-115，已核实）。反馈通道 `ReactAgent#interrupt()` 写 threadId→INTERRUPTION_FEEDBACK_KEY，`InterruptionHook`（BEFORE_MODEL）消费；交互端 `HumanInteractionHandler`/`ConsoleInteractionHandler` 可替换。

**langgraph4j** 三层粒度独有一档：编译期 interruptBefore/interruptAfter/**interruptBeforeEdge**（CompileConfig:124，边求值前中断——Python 无此独立开关）；节点内 `InterruptibleAction#interrupt(nodeId,state,config)` 返回 InterruptionMetadata（接口 opt-in 式而非异常式）；预制 `AgentEx.ApprovalNodeAction` 把工具审批做成图节点（APPROVAL_RESULT channel + approvalOn(builder) 逐工具配置）。

### 范式二：request_info 事件 + 终态续答（agent-framework）

**微软 agent-framework** 把 HITL 统一为可持久化暂停点：executor 内 `ctx.request_info()` + `@response_handler`（_request_info_mixin.py）→ 事件流 request_info 事件 → Workflow 状态 `IDLE_WITH_PENDING_REQUESTS`（_events.py:88）→ 调用方 `run(responses={request_id: ...})` 续跑（_workflow.py:746 统一入口，与 `run(checkpoint_id=...)` 可组合）。关键设计：**pending 请求写入 checkpoint**（_checkpoint.py:92 pending_request_info_events，已核实）——审批暂停与崩溃恢复走同一条通道，跨进程/跨重启等人都不丢。工具审批独立三层：`@tool(approval_mode=...)`（默认 never_require）→ harness `ToolApprovalRule`（always/scope/**参数级匹配**，_tool_approval.py:86）→ 审批决定持久化 `ToolApprovalState`（:158，存进 AgentSession.state[source_id]，_save_state :268 已核实——粘性决策随会话存活）；MCP 专项 `MCPSpecificApproval`（_mcp.py:86）。orchestrations 另有 `AgentApprovalExecutor`（:169）把审批做成图上执行器节点。

### 范式三：PERMISSION_ASKING 终态（agentscope-java）

**agentscope-java** 的审批不是回调阻塞而是**正常返回值**：权限引擎求值到 ASK → 工具抛 `ToolSuspendException` → 本轮以 `GenerateReason.PERMISSION_ASKING` 终态返回（ReActAgent.java:2803-2910，已核实）——天然适配 HTTP/进程边界（调用方拿到"我在等你批"的明确终态而非超时）。恢复 = **第二次 `call` 携带 ConfirmResult**（event/ConfirmResult.java），resume payload 严格校验「当前正 ASKING 的工具」（:1838）——伪造/错位即拒绝，这是 HITL 恢复面少见的显式防伪造设计。中断另有 `InterruptControl`（USER/SYSTEM 源）挂 AgentState，`agent.interrupt(userId,sessionId,msg)` 精准中断指定会话，每轮 `checkInterrupted` 检查点。服务层再升级为跨进程审批协调：dataplane `ToolConfirmationCoordinator`/`PendingHandsToolService`——审批流在独立进程流转。

### 范式四：can_use_tool 反向 RPC 回调（claude-agent-sdk）

**claude-agent-sdk** 的审批是 stdio 控制协议上的反向调用：CLI 权限规则评估为 "ask" 时经 control_request(can_use_tool) 反调 SDK（query.py:478-530）；返回 `PermissionResultAllow(updated_input/updated_permissions)` 或 `PermissionResultDeny(message/interrupt)`——**审批时可以同时改写工具输入并动态增删权限规则/切模式/加目录**（types.py:116-197，PermissionUpdate 六种变更：addRules/replaceRules/removeRules/setMode/addDirectories/removeDirectories，四个落盘目的地 userSettings/projectSettings/localSettings/session）。工程细节：互斥校验把回调改写为 `--permission-prompt-tool stdio`（types.py:1896-1919）；`_warn_if_can_use_tool_shadowed` 复刻 CLI 规则解析器预判哪些工具会在回调前被自动放行并发 CanUseToolShadowedWarning——用 advisory 而非 raise 承认"故意只管部分工具"的合法用法。挂起语义另有协议级一档：PreToolUse hook 可回 `permissionDecision: defer`，运行停止、待决调用进 `ResultMessage.deferred_tool_use`（types.py:1279-1291）——把"挂起等人工"做成一等消息。permission_prompt_tool_name 还可把审批路由到自定义 MCP 工具（审批通道本身可插拔）。

### 范式五：事件往返（agentscope Python / llama_index / adk / dify / openai / langchain4j / crewai）

- **agentscope（Python）**：HITL 全事件化——`RequireUserConfirmEvent`/`RequireExternalExecutionEvent`/`UserInterruptEvent` 三类挂起事件 + 对应 `*ResultEvent` 重入（event/_event.py:443/:456，已核实）；agent 停在 awaiting 态，跨进程由 SessionService 记 **parked 状态**（`derive_parked_status` 从持久化 context 反推当前挂在哪个 pending 工具调用上，_session.py:212，已核实）。`is_external_tool` 工具把执行移交外部进程/人工；`AskUser` 内置工具（_ask_user.py:150）做多选题/表单式收集，answer 结构化；`stop_on_reject` 配置被拒后停或继续。
- **llama_index**：审批即事件往返——工具内 `ctx.wait_for_event(HumanResponseEvent, waiter_event=InputRequiredEvent(...), requirements={...})` 阻塞等待，调用方从 `handler.stream_events()` 捕获后 `handler.ctx.send_event(...)` 恢复；requirements 匹配保证多挂起并存的正确路由。事件类型定义在外部 llama-index-workflows 包（core 为 shim）⚠️内部实现不可本地回源，与 checkpoint 组合可跨进程挂起。
- **adk-python**：`NodeInterruptedError(BaseException)`（基类防被框架 except 吞掉）为中断原语，Workflow 收集 WAITING 节点中断、resume 时恢复（_workflow.py:331 `_collect_remaining_interrupts`）。工具级审批走 `request_confirmation` 请求处理器：注入 `adk_request_confirmation` 工具，模型调用它发起确认；**确认回执 = 用户消息携带 function_response**（按 function_call id 关联，request_confirmation.py:259 起，已核实），`Runner._extract_resume_inputs`（runners.py:605）从消息提取 `{fc_id: response}` 续跑挂起调用，且校验新消息不得混排文本与 FR（_validate_new_message）。富交互 `UiWidget` 随事件下发前端组件意图。
- **adk-java**：同概念——`REQUEST_CONFIRMATION_FUNCTION_CALL_NAME`（Functions.java:71）+ `ToolConfirmation` 结构化确认请求 + `RequestConfirmationLlmRequestProcessor`（在历史中发现 pending 确认调用时接管请求）；工具级 `requireConfirmation` 是 FunctionTool 构造参数(:58)。
- **dify**：HITL = 平台级表单审批流。HUMAN_INPUT 节点（表单/审批实体 HumanInputNodeData/FormInputConfig/UserActionConfig）+ 表单模型 HumanInputForm/Recipient/UploadToken（models/human_input.py:28-314）+ 投递面权限矩阵（human_input_policy.py：SERVICE_API/CONSOLE/OPENAPI 各自允许的收件人）+ 节点级/全局级超时自动处置（tasks/human_input_timeout_tasks.py）+ 恢复入口（service_api workflow_paused 事件流 + resume SSE + 双端表单提交）。最有辨识度的是 **agent 内 HITL 与工作流表单同轨**：Agent 后端 run 结束带 `dify.ask_human` 延迟工具调用时，翻译层把它映射到外层工作流同一条表单暂停路径（复用表单仓/投递通道/提交端点，ask_human_hitl.py 模块头 ENG-636 已核实）——两套 HITL（节点式与工具式）收敛到一条审批管道。
- **openai-agents-python**：审批面=声明+中断列表+快照三段。`needs_approval`（bool 或 callable）覆盖 function_tool、Agent.as_tool、ShellTool、ApplyPatchTool；本地 MCP 用 `require_approval`、HostedMCPTool 用 `tool_config`。暂停时 `RunResult.interruptions` 携带 `ToolApprovalItem`（agent.name/tool_name/arguments），流式同样支持；决策 `state.approve(item)` / `state.reject(...)` / **`always_approve=True` 粘性决策**（按 call_id 或工具身份记忆，存进 RunState 跨序列化存活，run_state.py:1295 已核实）→ `Runner.run(agent, state)` 原地续跑。另有程序化即时审批回调 `on_approval` 与审批前护栏 `pre_approval_tool_input_guardrails`。
- **langchain4j**：双形态。同步 `HumanInTheLoop` record + `responseProvider(Function<AgenticScope,?>)`——非中断型，问答当场发生；挂起式 `AgenticSystemSuspendedException`（javadoc：系统状态已 checkpoint、线程释放），恢复 = `AgenticScope#completePendingResponse(responseId, value)`（:191，已核实）后以相同 memoryId 重调 agent 方法；嵌套挂起有集成测试（NestedSuspensionIT/SuspensionResumeIT）。
- **crewai（唯一的"答案后反馈"形态）**：`Task.human_input` → 执行器在 **LLM 已给出答案之后**调 `_handle_human_feedback`（crew_agent_executor.py:1625）循环收集反馈直到满意——不是任务前审批，与 interrupt/resume 范式正交。通道抽象 `HumanInputProvider` Protocol（setup_messages/post_setup_messages/handle_feedback）+ 控制台实现，企业可换 Web 审批；Flow 级 `human_feedback` 装饰器 + HumanFeedbackConfig/PreReviewResult/**DistilledLessons**（LLM 把人审反馈蒸馏为可复用经验反哺记忆）+ 异步人审（flow/async_feedback/）。

### 审批粒度与恢复机制对照

| 粒度 | 代表实现 |
|---|---|
| 工具级（默认档） | openai needs_approval、adk-java requireConfirmation、langchain4j approvalOn、langchain HITLM（按工具名+when 谓词）、MS approval_mode |
| **参数级** | MS ToolApprovalRule（参数匹配）；deepagents 路径规则（exact/bulk + 绕过防御）；claude `Bash(ls:*)` 规则文法；agentscope PermissionEngine match_rule（命令子串/通配、文件 glob） |
| 节点/边级 | langgraph interrupt_before/after（`"*"`）、langgraph4j **interruptBeforeEdge**、saa interruptsBefore/After、MS AgentApprovalExecutor（审批即图节点）、crewai Flow human_feedback 步骤级 |
| **消息级** | claude PreToolUse `defer`（待决调用进 ResultMessage.deferred_tool_use，宿主决定何时 resume） |

| 恢复机制 | 代表实现 |
|---|---|
| `Command(resume=)` | langgraph（节点从头重放 + scratchpad 顺序匹配）；langchain/deepagents 透传 |
| `run(responses=)` | agent-framework（request_id 关联，与 checkpoint 恢复可组合） |
| **二次 call 带 ConfirmResult** | agentscope-java（resume payload 校验当前 ASKING 工具，防伪造） |
| Result 事件重入 | agentscope Python（parked 状态反推挂起点） |
| function_response 回执 | adk-python resume_inputs（按 fc_id）/ adk-java RequestConfirmation 处理器接管 |
| **粘性审批** | openai always_approve（随 RunState 序列化存活）；MS ToolApprovalState（存 AgentSession）；claude updatedPermissions（六种变更、四落盘目的地） |
| 表单状态机 | dify（resume SSE + 双端表单 + 超时任务） |
| 答案后反馈循环 | crewai（human_input + Provider 可替换） |

### 转人工（escalation）与表单（form）

- **agentscope 表单已删（双语同步）**：v1 的 FormFillingAgent 在 Python v2 与 Java v2 均已删除（两侧档案均核实 src 无 form 模块）——替代物是 `AskUser` 多选题工具（结构化 answer）+ web_ui 的 SchemaForm.tsx（schema 驱动表单，json_schema_extra 提示字段呼应）。
- **dify ask_human 延迟工具**：agent 运行时的 ask_human 是延迟工具调用（deferred tool call），落回工作流表单通道——工具语义与节点语义在存储层合流（见范式五）。
- **adk UiWidget**：事件携带前端组件意图（events/ui_widget.py:25），把"渲染什么给用户看"做成事件流一等公民。
- **claude 审批通道可插拔**：permission_prompt_tool_name 把 can_use_tool 路由到任意自定义 MCP 工具（比如企业审批系统实现成 MCP server）。
- **crewai 转人工即学习**：DistilledLessons 把人审反馈沉淀为记忆——escalation 的产出不是状态迁移而是知识资产。

## 11.3 跨语言对齐

| 对 | Python 侧 | Java 侧 | 差异判断 |
|---|---|---|---|
| langgraph ↔ langgraph4j | `interrupt()` 函数式异常 + `Command(resume=)` 恢复值回填 + prebuilt HumanInterruptConfig 决策 UI 类型 | 无函数式 interrupt 等价 API（接口式 InterruptibleAction opt-in）；静态三档（Before/After/**BeforeEdge**，Java 多边粒度）；AgentEx 审批预制节点（Python 需手工搭） | **风格分叉、能力对等**：Python 胜在零侵入节点代码；Java 胜在粒度开关与审批预制件 |
| adk-python(2.9) ↔ adk-java(1.9) | request_confirmation 处理器 + resume_inputs 提取 + UiWidget 富交互 + NodeInterruptedError 图级中断 | 同名 adk_request_confirmation + requireConfirmation 参数 + RequestConfirmationLlmRequestProcessor 接管；无 UiWidget/无通用 workflow 图级中断（1.x 无 workflow 包，版本差） | **核心语义对齐**（确认工具 + function_response 回执），Python 外围（组件意图、图级中断）领先 |
| agentscope ↔ agentscope-java | Require 事件族 + Result 事件重入 + parked 状态推导 + AskUser 工具 + stop_on_reject | PERMISSION_ASKING 终态 + 二次 call ConfirmResult（防伪造校验）+ InterruptControl 精准中断 + dataplane 跨进程协调 + AG-UI starter | **语义等价、边界取向不同**：Python 事件流对前端友好；Java 终态+续跑对 HTTP 服务友好且防伪造更严 |

## 11.4 取舍与趋势

1. **中断原语收敛为"重放式 vs 终态式"之争**：异常式 interrupt（langgraph 系）换来零侵入，但强绑 checkpointer 且要求节点确定性可重放；终态式（agentscope-java PERMISSION_ASKING、MS IDLE_WITH_PENDING_REQUESTS、adk 确认工具回执）把"等人"做成一次调用的正常返回，天然适配无状态 Web 服务——服务化框架（MS/agentscope-java/dify）全部选择终态或事件式，不是巧合。
2. **HITL 与持久化合流**：pending 审批进 checkpoint/session 已是四种独立实现的事实——MS pending_request_info_events（随 checkpoint 跨进程）、openai RunState（版本化快照含审批状态）、agentscope parked（从持久化 context 反推）、dify WorkflowPause（含流位置）。"等人"与"崩溃恢复"共享同一条持久化通道，是本维度最强的结构性趋势。
3. **审批粒度下沉到参数/路径语义，且绕过防御成标配**：deepagents 为 7 个文件工具逐个定义 exact/bulk 语义并堵 `path="."`、`..`、绝对 glob 三类绕过；agentscope-java 校验 resume payload 必须命中当前 ASKING 的工具（防伪造审批回执）；MS ToolApprovalRule 做到参数级匹配。审批已从"这个工具要不要批"进化为"这次调用的这组参数要不要批"。
4. **粘性授权（sticky approval）成为差异化卖点**：openai always_approve 随快照序列化、MS ToolApprovalState 存会话、claude 审批时动态改写权限规则并落盘四个目的地——共同方向是把"逐次审批"升级为"可治理的授权生命周期"。
5. **表单范式的退潮与回归**：agentscope v2 双语删除 FormFillingAgent（细粒度表单 API 生命周期短的又一实证），但富交互以新形态回归——AskUser 多选题工具、dify 表单节点（含权限矩阵与超时处置）、adk UiWidget 组件意图——从"框架级表单状态机"退到"事件载荷 + 前端 schema 渲染"。
6. **crewai 的"答案后反馈"是唯一非闸门形态**：human_input 在产出后收集反馈、DistilledLessons 把人审蒸馏为记忆——把人当教师而非审批员；代价是没有前置硬闸门（危险操作拦截要靠 guardrail 维度），与"审批=安全边界"的主流假设形成方法论分叉。spring-ai 则代表另一极：官方立场完全留白（连 interrupt 都不做），把 HITL 推给 spring-ai-alibaba 等衍生层——17 家中唯一 ❌。
