# 维度 9：多 Agent（Multi-Agent）

> 本维度回答：多 agent 协作的三种模式——supervisor（主管调度）、handoff（控制权转移）、group-chat（群聊轮流发言）——分别由谁以什么形态实现；A2A（Agent-to-Agent）协议的 client/server 实现质量如何；agent 注册（registry）与跨框架互操作（interoperability）做到什么程度。17 框架总体格局：**handoff-as-tool 是多 agent 的最小公分母**（把控制流转移编码为工具调用，openai-agents/llama_index/adk/agentscope 系全都如此）；supervisor 要么是独立生态包（langgraph 系）、要么是编排库的正经抽象（langchain4j/MS Magentic）；group-chat 只活在 AutoGen 血统里（MS orchestrations）与平台插件里（dify Agent 策略）。A2A 已成 Java/企业阵营标配（agentscope-java、spring-ai-alibaba、langchain4j、adk 双语、crewai 全实现），Python 研究型框架反而滞后；跨框架互操作出现三条通道：adapter（crewai）、协议（A2A）、引擎桥（adk LangGraphAgent、langgraph RemoteGraph）。

## 9.1 总览矩阵

| 框架 | 评级 | 一句话实现 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|
| langchain | 🔶 | 仅 `name` 子图嵌套 + `run.subagents` 观测句柄；supervisor/handoff 刻意留白给生态（langgraph-supervisor / deepagents） | libs/langchain_v1/langchain/agents/factory.py#L861-L867（name 参数 docstring 明说 multi-agent 用途）；_subagent_transformer.py#SubagentTransformer:120 |
| langgraph | 🟡 | 原子能力内置（subgraph/Send/Command goto/PARENT）；supervisor/swarm 在官方独立仓（gh api 已验证仓库存在：langgraph-supervisor-py / langgraph-swarm-py，2026-07 仍活跃，代码未本地细读） | libs/langgraph/langgraph/pregel/main.py#get_subgraphs:1076；types.py#Command:799；examples/multi_agent/【示例】 |
| langgraph4j | 🔶 | 无 supervisor/handoff 核心抽象；supervisor 是 how-tos 手搭教程；spring-ai-agent 集成模块有 SubAgent 组合件 | how-tos/multi-agent-supervisor.ipynb【示例】；spring-ai/spring-ai-agent/.../SubAgent.java、SkilledReactSubAgent.java |
| langchain4j | ✅ | supervisor 全家桶（SupervisorPlanner+AgentsRegistry+ResponseScore 评分选优）+ A2A 客户端 + MCP 即 agent + 六种协作 pattern + 跨 agent 补偿 | langchain4j-agentic/.../supervisor/SupervisorPlanner.java；planner/AgentsRegistry.java#L20（二次核验）；langchain4j-agentic-a2a/.../DefaultA2AService.java |
| deepagents | ✅ | `task` 工具三类子代理（声明式/预编译/远端异步）+ 默认 general-purpose 子代理 + fork 继承父对话 + 状态白名单回传 | libs/deepagents/deepagents/middleware/subagents.py#_build_task_tool:577、CompiledSubAgent:220；middleware/async_subagents.py |
| agent-framework (MS) | ✅ | orchestrations 包（released）：GroupChat/Magentic(supervisor+ledger)/Handoff/Sequential/Concurrent + A2AExecutor 入图（AutoGen 血统） | python/packages/orchestrations/agent_framework_orchestrations/_group_chat.py#GroupChatOrchestrator:98（二次核验）、_handoff.py#HandoffAgentExecutor:202、_magentic.py#MagenticProgressLedger:308；packages/a2a/.../_a2a_executor.py#A2AExecutor:31 |
| adk-python | ✅ | 层级树 + transfer 工具（AutoFlow 注入 transfer_to_agent）+ AgentTool + A2A 双向（RemoteA2aAgent/to_a2a）+ LangGraphAgent 互操作桥 | src/google/adk/flows/llm_flows/auto_flow.py；tools/agent_tool.py#AgentTool:109；agents/remote_a2a_agent.py:625；a2a/utils/agent_to_a2a.py#to_a2a:79；agents/langgraph_agent.py#LangGraphAgent:84（二次核验） |
| adk-java | ✅ | transfer（AutoFlow + AgentTransfer 处理器，disallow 方向控制）+ AgentTool + A2A 双向独立模块（官方 io.a2a SDK） | core/.../flows/llmflows/AgentTransfer.java；a2a/.../RemoteA2AAgent.java、executor/AgentExecutor.java |
| openai-agents-python | ✅ | handoff() 原语（transfer_to_<name> 工具 + input_type 结构化参数 + input_filter + nest_handoff_history）+ Agent.as_tool + 实验性 hosted_multi_agent | src/agents/handoffs/__init__.py#handoff:260；agent.py#as_tool:583；extensions/experimental/hosted_multi_agent/model.py |
| claude-agent-sdk-python | ✅ | 声明式 `agents: dict[str, AgentDefinition]` 经 initialize 下发，CLI Agent(Task) 工具调度（含并行）；子代理转录可离线回读；跨会话 peer/coordinator 消息【文档】 | src/claude_agent_sdk/types.py#AgentDefinition:86-105；_internal/query.py#Query.initialize（request["agents"]）；_internal/sessions.py#list_subagents |
| crewAI | ✅ | hierarchical = manager agent + delegate_work/ask_question 委派工具（非调度器）+ LangGraph/OpenAI 双向 adapter + A2A 完整双向（含 agent 出卡片） | lib/crewai/src/crewai/crew.py:1521/_create_manager_agent；tools/agent_tools/agent_tools.py#AgentTools:16；agents/agent_adapters/langgraph/langgraph_adapter.py#LangGraphAgentAdapter:40（二次核验）；a2a/utils/agent_card.py:579 |
| dify | 🔶 | 图上可编排多 Agent 节点 + workflow_as_tool 互调（深度上限）；无 supervisor/handoff/A2A（二次核验：全仓 rg a2a 零真实命中，仅 uv.lock 哈希子串误报） | api/core/workflow/nodes/agent/agent_node.py#AgentNode；core/workflow/workflow_entry.py:139-141（WORKFLOW_CALL_MAX_DEPTH） |
| llama_index | ✅ | AgentWorkflow 原生多 agent：handoff 即 return_direct 工具 + can_handoff_to 静态白名单 + 运行时双重校验；orchestrator（子 agent 作工具）为文档化模式 | llama-index-core/.../agent/workflow/multi_agent_workflow.py#handoff:73、_get_handoff_tool:216（:84-86 白名单校验）；docs/.../agent/multi_agent.md |
| agentscope | ✅ | A2AAgent 有状态客户端适配器 + app 层 team/subagent 工具链（AgentCreate/TeamSay/TeamMemberLoopMiddleware 常驻循环）+ 每家 formatter 的 MultiAgent 变体 | src/agentscope/agent/_a2a_agent.py#A2AAgent:189（二次核验）；app/_tool/_team_create.py；app/middleware/_team_member_middleware.py |
| agentscope-java | ✅ | agent-as-tool（core）+ task/task_output 子代理（同步/后台/跨节点 RemoteSubagentStub）+ team + A2A client/server 扩展 + starter + 注册中心（admin/nacos/higress） | agentscope-core/.../tool/{AgentTool,subagent/SubAgentTool}.java；agentscope-extensions-protocol/agentscope-extensions-a2a/（二次核验目录）；admin starter AgentRegistry |
| spring-ai-alibaba | ✅ | flow 四件套（含 LlmRoutingAgent）+ agent-as-tool + 嵌套子图 + A2aRemoteAgent + Nacos 注册发现；supervisor/handoffs 在 examples | spring-ai-alibaba-agent-framework/.../agent/flow/agent/{Sequential,Parallel,Loop,LlmRouting}Agent.java；a2a/A2aRemoteAgent.java:40（二次核验）；starter-a2a-nacos/.../NacosAgentRegistry.java |
| spring-ai | ❌ | 无 supervisor/handoff/swarm/a2a 任何抽象（核心包 rg 零命中）；agent-as-tool 可用 @Tool 手工模拟 | 全仓 rg（spring-ai-model/client-chat/rag/advisors 无命中）；官方把多 agent 留给 spring-ai-alibaba 等衍生 |

评级说明：与档案一致。langgraph 维持 🟡——二次核验通过 gh api 确认 `langchain-ai/langgraph-supervisor-py`（1.6k stars）与 `langchain-ai/langgraph-swarm-py`（1.5k stars）存在且 2026-07-15 仍有推送，档案的 ⚠️「官方独立仓存在性」已解除（代码细节仍非本地源码结论）。

## 9.2 实现方式深析

### 9.2.1 三种协作模式的归属

**supervisor（主管调度）**：
- **作为正经核心抽象的两家**：langchain4j `SupervisorPlanner`——LLM 规划「下一步调哪个子 agent」，`maxAgentsInvocations=10` 防死循环，`ResponseAgent`+`ResponseScore` 对子 agent 答案评分选优（ResponseStrategy: LAST/SUMMARY），supervisor 上下文策略三选一（CHAT_MEMORY/SUMMARIZATION/两者），`AgentsRegistry`（planner/AgentsRegistry.java:20）管理可调度 agent 面；MS orchestrations 的 **Magentic 家族**（`MagenticProgressLedger` 任务分解 + 复盘重规划 + `MagenticManagerBase` LLM 选下一发言者）——名字与机制直接继承 AutoGen Magentic-One。
- **作为生态包**：langgraph 系——langchain 与 langgraph 仓库都刻意不做，官方放在独立仓 langgraph-supervisor-py / langgraph-swarm-py（gh api 验证存在）；spring-ai-alibaba 也只在 examples/multiagent-patterns/supervisor 给示例级实现。
- **作为「伪 supervisor」**：crewai 的 hierarchical 是**委派不是调度**——`_run_hierarchical_process`（crew.py:1516）造一个 manager agent 挂 `AgentTools` 委派工具（delegate_work/ask_question，描述模板带 coworkers 列表），仍走 `_execute_tasks` 顺序执行、executing_agent 换成 manager——多 agent 协作被建模为「工具化的人际委派」，与图调度器范式刻意不同（设计决策第 5 条原文）。

**handoff（控制权转移）**：
- **原语级实现（3 家）**：openai-agents `handoff()` 是教科书——生成 `transfer_to_<agent_name>` 工具、`on_invoke_handoff` 返回目标 agent 后 `run_state._current_agent` 切换（turn_resolution.py）、`input_type` 结构化交接参数（strict schema 校验）、`input_filter` 裁剪下游输入、`nest_handoff_history` 把上游历史折叠成嵌套摘要防上下文爆炸、`is_enabled` 动态启停。llama_index `handoff()` = return_direct 工具 + `can_handoff_to` **静态白名单**（构造时声明、运行时双重校验 multi_agent_workflow.py:84-86）——比自由 swarm 可审计。adk 双语的 transfer 是**可达性自动注入**：AutoFlow 挂 agent_transfer processor，为可达 agent 注入 `transfer_to_agent` 工具，支持 parent↔sub↔peer 方向及 `disallow_transfer_to_peers`（adk-java 无子 agent 时自动降级 SingleFlow，LlmAgent.java:605）；transfer 事件直接 `nextAgent.runAsync(context)` 接续流（BaseLlmFlow.java:488-504）——控制权在流内无缝转移。
- **子代理化变体（task 工具）**：deepagents `task` 工具 + `CompiledSubAgent`（预编译子图）/ `AsyncSubAgent`（远端后台任务：launch/check/update/cancel/list 五工具经 langgraph_sdk 连 Agent Protocol server）；说明词明言「多调用并行、默认无状态、报告不展示给用户需自行转述」。agentscope-java `SubAgentTool`/`SubagentsMiddleware` 同形态（同步+后台）。claude-agent-sdk 的 CLI Agent(Task) 工具是同一思想的闭源实现——SDK 侧只做声明下发（`options.agents` 恒经 initialize 控制请求，不走 CLI flag，subprocess_cli.py:716-717 注释）与转录回读（parent_tool_use_id/parent_agent_id 关联）。
- **隔离与继承语义最讲究的是 deepagents**：子代理继承父 tools/permissions/interrupt_on（可整体覆盖）；回传状态走白名单——`_EXCLUDED_STATE_KEYS` 与 PrivateStateAttr 私有字段不泄漏（subagents.py:687）；`mode="fork"`（实验）反向共享全部上下文且 fork 内再调 task 被拒（防递归 :771-772）——「隔离为默认、共享为显式」。

**group-chat（群聊）**：
- 只有两处正式实现：MS orchestrations 的 `GroupChatOrchestrator` / `AgentBasedGroupChatOrchestrator`（LLM 选下一发言者，_group_chat.py:98/:284）——**AutoGen 血统的直系保留**（仓内 README 直挂 AutoGen 迁移指南，samples/autogen-migration/ 对应）；dify 的群聊能力在 Agent 节点的策略插件里（PluginAgentStrategyResolver，策略由 plugin_daemon 提供，CoT/FC 是仓内仅有的两个 runner）——「群聊留插件」的平台解法。
- agentscope 的 v1 msghub 已删除，遗产收缩为**格式层**：每家供应商 formatter 的 `*MultiAgentFormatter` 变体（如 DashScopeMultiAgentFormatter，formatter/_dashscope_formatter.py:408）——多 agent 会话只保留消息格式适配，协作语义交给 team 工具/A2A。

### 9.2.2 A2A 协议：实现质量分层

A2A（Agent Card 发现 + 任务委派的开放协议）在 17 家中的覆盖（二次核验后）：

| 层次 | 框架 | 证据 |
|---|---|---|
| **client + server 双向完整** | agentscope-java（a2a-client + a2a-server 两个扩展模块 + `agentscope-a2a-spring-boot-starter` 自动暴露 A2aJsonRpcController/AgentCardController）；spring-ai-alibaba（A2aRemoteAgent 消费 + starter-a2a-nacos 的 GraphAgentExecutor/MultiAgentJsonRpcRouterProvider 暴露 + **Nacos 注册发现**）；crewai（wrap_agent_with_a2a_instance 委派远端 + inject_a2a_server_methods 让 agent 反向 `to_agent_card()` 出卡片 + streaming/polling/push_notifications 三种更新通道 + auth + 32 个 A2A 事件类型）；adk-python（RemoteA2aAgent 消费含 AgentCard 解析 + to_a2a() 产出 Starlette app + 事件↔任务转换器含 long_running_functions 映射 + `a2a_experimental` 装饰器显式标注实验态） | 各仓源码 |
| **client 强 / server 简或另置** | langchain4j（DefaultA2AService + `@A2AClientAgent` 把远端 A2A server 声明为本地 agent，含 tenantId/taskId/contextId 透传与 A2ATaskInterruptedException；server 侧依托 a2a-java-sdk-client）；adk-java（a2a 模块：RemoteA2AAgent 消费 + AgentExecutor 实现官方 io.a2a 的 agentexecution 暴露）；MS（A2AExecutor 入图 + A2AAgentSession/A2AContinuationToken 有状态会话；服务端在 hosting-a2a 包但 alpha） | 各仓源码 |
| **client only** | agentscope Python（A2AAgent 有状态客户端适配器：远端 Part 流 → 本地 AgentEvent 流，artifact append/last_chunk 语义映射到 block 事件；server 只有 examples/a2a/server.py 示例；a2a-sdk 是 optional extra） | agent/_a2a_agent.py |
| **无** | dify（二次核验：全仓 rg "a2a" 仅 uv.lock 哈希子串与无关 yaml 误报，真实零命中）、langgraph/langchain（跨进程走 RemoteGraph/Agent Protocol 而非 A2A）、openai-agents、claude-agent-sdk、llama_index、spring-ai、deepagents（AsyncSubAgent 走 langgraph_sdk 的 Agent Protocol，非 A2A） | rg 结果 |

值得注意的分工：**A2A 的第一梯队全是 Java/企业阵营 + crewai**——agentscope-java/spring-ai-alibaba 还叠加了注册中心（Nacos）与服务治理（aistio 流量连接器）；Python 阵营里 Google/MS 把 A2A 做进官方模块但标注 beta/experimental，研究型框架（llama_index）完全缺席。crewai 是 Python 侧唯一做满双向 + 更新通道 + 鉴权的。

### 9.2.3 Agent 注册（registry）

四种形态：
- **接口级**：langchain4j `AgentsRegistry`（supervisor 的可调度 agent 面管理）；MS `_harness` 无统一 registry 但 orchestrations 以 builder 组装参与者。
- **运行时动态建 agent**：agentscope app 层 `AgentCreate` 工具（支持 custom_subagent_templates）+ agentscope-java `DynamicSubagentsMiddleware`/`SubagentFactory`——agent 可以在运行中被另一个 agent 创建。
- **服务注册发现**：spring-ai-alibaba starter-a2a-nacos 的 `NacosAgentRegistry`（AgentCard 注册进 Nacos + `MultiAgentJsonRpcRouterProvider` 多 agent 路由）；agentscope-java admin starter `InMemoryAgentRegistry` + `CommandPlane` 管理命令面 + nacos/higress 扩展——把 Spring Cloud 服务治理模型搬到 agent 上。
- **跨节点注册**：agentscope-java `SubagentRegistry` + `SubagentGatewayBridge`（exposeSubagent 把本地子代理暴露为远端可调用，跨节点 RemoteSubagentStub + RemoteAskPolicy）。

### 9.2.4 跨框架互操作：三条通道

1. **Adapter（进程内包装）**：crewai `agents/agent_adapters/`——`LangGraphAgentAdapter`（:40）把 LangGraph agent 当 crewAI agent 用、`OpenAIAgentAdapter`（:51）同理，配套 ToolAdapter/ConverterAdapter 三件套（二次核验类清单）；agentscope-java `agentscope-extensions-agui`/`agent-protocol`、spring-ai-alibaba `starter-agentscope`（AgentScope agent 适配进自家 flow）——「我不懂的框架，包一层当我的 agent」。
2. **协议（跨进程标准）**：A2A（见 9.2.2）+ MCP 反向暴露——adk-python `_agent_to_mcp.py`（agent 变 MCP server）、MS hosting-mcp（agent/workflow 暴露为 MCP 工具）、langchain4j `@McpClientAgent`（MCP server 即 agent）、spring-ai MCP server starter——MCP 成为「agent 当工具」的通用语。
3. **引擎桥（执行语义级复用）**：adk-python `LangGraphAgent`（agents/langgraph_agent.py:84）把 compiled StateGraph 适配为 ADK agent——thread_id 由三元组派生、checkpointer 兼容，即 ADK 的服务/会话体系接管 LangGraph 图的状态；langgraph `RemoteGraph`（pregel/remote.py:118，PregelProtocol 实现）把远端部署图当本地节点；deepagents `AsyncSubAgent` 经 langgraph_sdk 连任何 Agent Protocol server（LangGraph Platform 或自托管）——后两者是「把别家的图当我的子图」。

## 9.3 跨语言对齐

| 对 | 维度 9 差异 | 证据 |
|---|---|---|
| langgraph ↔ langgraph4j | 两侧核心都不含 supervisor/handoff；Python 侧官方生态包齐（supervisor/swarm 独立仓 + deepagents 子代理 harness），Java 侧只有 how-tos 教程 + spring-ai-agent SubAgent——生态厚度差是主差 | gh api 验证 vs how-tos/multi-agent-supervisor.ipynb |
| adk-python(2.9) ↔ adk-java(1.9) | 概念对齐：transfer（AutoFlow/AgentTransfer）+ AgentTool + A2A 双向两侧都有；差异：① Python 的 `_TaskAgentTool` 配 FinishTaskTool 表达 A2A 任务语义，Java 无对应；② Python A2A 在 core（含 experimental 装饰器），Java 在独立 a2a 模块；③ Python 有 LangGraphAgent 互操作桥，Java 无 | agents/llm/task/、a2a/ 模块位置、langgraph_agent.py:84 |
| agentscope(Python) ↔ agentscope-java | 两侧都删了 v1 组合子并转向「A2A + team 工具」；Java **超出**：A2A 有 server 端扩展 + starter（Python 仅 client + 示例 server）、跨节点 RemoteSubagentStub/SubagentRegistry、注册中心生态（admin/nacos/higress）、aistio 流量治理——Python 侧则是 app 层 team 工具链先行（TeamSay/成员常驻循环） | 对齐表「多 Agent：已对齐/超出」 |

## 9.4 取舍与趋势

1. **handoff-as-tool 赢得了最小公分母地位**：openai-agents（transfer_to_*）、llama_index（handoff + return_direct）、adk（transfer_to_agent 自动注入）、deepagents/agentscope-java（task 工具）、claude CLI（Agent 工具）全部把控制流转移编码为工具调用——零新概念、复用工具调用协议、天然获得审批/观测/结构化参数（input_type/can_handoff_to）；代价是没有 supervisor 式全局视图，路由质量完全交给模型。
2. **supervisor 从框架核心外移**：只有 langchain4j 与 MS Magentic 把它当正经抽象；langgraph 系拆独立生态包、crewai 做成「委派工具」、saa 留 examples——行业共识是 supervisor 拓扑强耦合业务，做成框架抽象的维护成本高于收益（与维度 8「删组合子」同源）。
3. **group-chat 只剩血统传承**：AutoGen 的群聊遗产保留在 MS orchestrations（GroupChat/Magentic）与 dify 的策略插件里；agentscope 把 msghub 降级为消息格式层——「多轮自由发言」的多 agent 形态在生产中让位给结构化编排与显式交接。
4. **A2A 沿企业/Java 轴分布**：完整实现（双向+注册+治理）集中在 agentscope-java、spring-ai-alibaba（+Nacos/aistio）、crewai、adk 双语；Google/MS 的 Python 侧标 beta/experimental；研究型框架缺席。A2A 的价值主张（跨组织 agent 市场）天然面向有注册中心与服务治理诉求的栈——这是 Java 阵营罕见地领先 Python 阵营的维度。
5. **互操作从「包一层」进化到「共享状态语义」**：早期 adapter 模式（crewai agent_adapters）只统一调用签名；adk LangGraphAgent 连 checkpointer/thread_id 语义都桥接（ADK 会话体系接管 LangGraph 状态）、langgraph RemoteGraph 实现 PregelProtocol 让远端图像本地节点一样参与 superstep——互操作深度正从 API 兼容走向执行语义兼容。
6. **子代理的权限语义成为新战场**：deepagents 的状态白名单（PrivateStateAttr 不泄漏）+ fork 防递归、agentscope-java 的 RemoteAskPolicy（跨节点问询策略）、MS/claude 的子代理独立审批传递——多 agent 安全边界从「进程隔离」细化到「状态字段级 + 交接参数级」。
