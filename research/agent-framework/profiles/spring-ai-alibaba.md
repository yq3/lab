# Spring AI Alibaba 框架档案

> 基线：~/develop/opensource/spring-ai-alibaba @ f82da0b50 2026-08-25；版本 1.1.2.2（父 pom `<revision>`；基于 Spring AI 1.1.2，JDK 17+，Maven 多模块）

## 1. 定位

Spring 生态上的「Agentic + Workflow + Multi-agent」一体框架（README.md 自述 "A production-ready framework for building Agentic, Workflow, and Multi-agent applications"）。分四层：graph-core 是 LangGraph 概念的 Java 图运行时（源自 langgraph4j fork，见第 7 节）；agent-framework 在其上提供 ReactAgent / 流程型多 Agent / hook+interceptor 上下文工程治理库；studio 与 admin 是本地调试 UI 和一站式可视化平台；模型接入完全复用 Spring AI（DashScope 由外置 starter 提供，不在本仓库）。目标用户是 Java/Spring 企业开发者，从 PoC（MemorySaver）到生产（JDBC/Redis saver + Nacos + A2A）平滑升级。

## 2. 仓库结构与核心包

根 pom `<modules>`（pom.xml）：

```
spring-ai-alibaba-bom
spring-ai-alibaba-graph-core        # 图运行时（203 java）：state/strategy、checkpoint/savers（10 后端）、
                                     #   store、skills、observation、scheduling、streaming、diagram
spring-ai-alibaba-agent-framework   # Agent 层（160 java）：agent/{flow,hook,interceptor,a2a,node,tool,tools,extension}
spring-ai-alibaba-studio            # 本地调试 UI（Spring MVC controller + 内嵌 agent-chat-ui 静态资源）
spring-ai-alibaba-sandbox           # 沙箱工具（browser/fs/mcp），复用 io.agentscope runtime 1.0.2
spring-boot-starters/
  ├─ spring-ai-alibaba-starter-a2a-nacos        # A2A JSON-RPC server + Nacos 注册发现
  ├─ spring-ai-alibaba-starter-config-nacos     # prompt/model/tools/MCP 的 Nacos 中心化注入
  ├─ spring-ai-alibaba-starter-graph-observation# Micrometer 装配
  ├─ spring-ai-alibaba-starter-builtin-nodes    # 16+ Dify 风格节点（QuestionClassifier/Iteration/Code...）
  └─ spring-ai-alibaba-starter-agentscope       # AgentScope Java SDK 桥接
spring-ai-alibaba-admin/            # ⚠️独立聚合 pom（server-core/server-runtime/openapi/server-start + frontend），
                                    #   不在根 <modules>，也不在 CI build（.github/workflows 仅 PR title lint 提及）
examples/                           # chatbot / deepresearch / documentation / multiagent-patterns（pipeline、
                                    #   handoffs-{multi,single}agent、routing、skills、subagent、supervisor、workflow）/
                                    #   multimodal / voice-agent / agentscope —— 仅作【示例】级证据
```

DashScope 边界：本仓库**无** DashScope ChatModel 源码。`spring-ai-alibaba-starter-dashscope` 是外部 artifact（agent-framework pom 中为 test 依赖）；根 pom 只管理 `dashscope-sdk-java 2.15.1`；admin 内有 `DashScopeChatClientFactory`、`DashscopeReranker` 消费方。⚠️ starter 源码仓位置未在本仓库内确认（文档指向 java2ai.com/integration/chatmodels/dashScope）。

## 3. 核心抽象清单

| 符号 | 路径 | 一句话 |
|---|---|---|
| `StateGraph` | spring-ai-alibaba-graph-core/.../graph/StateGraph.java | 建图 API：addNode/addEdge/addConditionalEdges/addParallelConditionalEdges/subgraph/compile |
| `CompiledGraph` | .../graph/CompiledGraph.java | 编译产物+运行入口：invoke/stream/updateState/getStateHistory/schedule |
| `OverAllState` + `KeyStrategy` | .../graph/OverAllState.java、KeyStrategy.java、state/strategy/ | 状态 + 按 key 的 Reducer（Append/Merge/Replace + RemoveByHash/ReplaceAllWith）＝LangGraph channels |
| `RunnableConfig` | .../graph/RunnableConfig.java | threadId/checkPointId/withResume（断点续跑） |
| `BaseCheckpointSaver` 家族 | .../graph/checkpoint/savers/ | Memory/VersionedMemory/FileSystem/H2/Mysql/Postgres/Oracle/Mongo/Redis + AbstractJdbc |
| `Store` 家族 | .../graph/store/stores/ | 跨线程 KV store（Memory/FileSystem/Redis/Mongo/Database） |
| `ReactAgent` | agent-framework/.../agent/ReactAgent.java | ReAct 图 = AgentLlmNode+AgentToolNode+动态织入的 hook 节点 |
| `Agent` / `BaseAgent` | .../agent/Agent.java、BaseAgent.java | 抽象基类；`asNode()` 把任意 agent 变成图节点（agent 即 graph） |
| `Hook` / `HookPosition` | .../agent/hook/Hook.java、HookPosition.java | BEFORE/AFTER × AGENT/MODEL 四象限切点（含 @HookPositions 注解 + Prioritized 排序） |
| `HumanInTheLoopHook` | .../agent/hook/hip/HumanInTheLoopHook.java | HITL：APPROVED/EDITED/REJECTED 三态反馈 |
| `Interceptor` / `InterceptorChain` | .../agent/interceptor/ | Model/Tool/Streaming 三类拦截器（fallback、retry、PII、todolist…） |
| `FlowAgent` 四件套 | .../agent/flow/agent/{Sequential,Parallel,Loop,LlmRouting}Agent.java | 内置编排模式 |
| `AgentTool` | .../agent/AgentTool.java | agent-as-tool（转 Spring AI ToolCallback） |
| `A2aRemoteAgent` | .../agent/a2a/A2aRemoteAgent.java | 远程 AgentCard 适配为本地 BaseAgent/节点（io.a2a SDK） |
| `AsyncToolCallback` 等 | .../agent/tool/ | StateAware/Cancellable + CancellationToken（工具取消） |
| `SkillRegistry` / `SpringAiSkillAdvisor` | graph-core/.../graph/skills/ | Claude 风格 SKILL.md 注册表 + 渐进披露 advisor |
| `NacosModelInjector` 等 | starter-config-nacos/.../nacos/ | Nacos 下发 prompt/model/tools/MCP 并注入 agent |
| `ScheduledAgentTask` | graph-core/.../graph/scheduling/ | 图的定时触发 |
| `GraphObservationDocumentation` | graph-core/.../graph/observation/graph/ | graph/node/edge/metric 四组 Micrometer 埋点 |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据（仓库相对路径#符号） |
|---|---|---|---|---|
| 1 | 模型接入 | 🟡 | provider 全交给 Spring AI 生态（DashScope starter 外置 ⚠️），框架自身做 fallback/retry/limit 治理 | spring-ai-alibaba-agent-framework/.../agent/interceptor/modelfallback + node/AgentLlmNode.java#chatClient |
| 2 | 上下文工程 | ✅ | summarization/contextediting/token 预算/return-direct 等 hook+interceptor 策略库开箱 | .../agent/hook/summarization/SummarizationHook.java |
| 3 | 记忆 | ✅ | 会话=messages key（AppendStrategy）+ checkpoint；跨线程 Store；无长期用户画像 | .../graph/checkpoint/savers/（10 后端）、store/stores/ |
| 4 | RAG | 🟡 | 核心无 RAG 抽象；starter 的 KnowledgeRetrievalNode + admin 知识库（仅 ES，DashscopeReranker）；DashVector ❌ | spring-boot-starters/spring-ai-alibaba-starter-builtin-nodes/.../KnowledgeRetrievalNode.java |
| 5 | 工具系统 | ✅ | Spring AI ToolCallback 之上加 Async/StateAware/Cancellable+取消令牌；MCP 三路接入 | .../agent/tool/CancellableAsyncToolCallback.java、starter-builtin-nodes/.../McpNode.java |
| 6 | Skill 机制 | ✅ | Claude 风格 SKILL.md：classpath/filesystem 注册表 + 渐进披露 advisor（Java 生态罕见） | graph-core/.../graph/skills/SpringAiSkillAdvisor.java |
| 7 | 规划推理 | ✅ | ReAct 循环 + LoopAgent 策略 + TodoList 规划拦截器 + TaskTool 子代理 + outputType 结构化 | .../agent/interceptor/todolist/TodoListInterceptor.java、tools/task/TaskTool.java |
| 8 | 编排 | ✅ | LangGraph 全概念：conditional/parallel/subgraph/interrupts + Mermaid/PlantUML 导出 + 定时 | graph-core/.../graph/StateGraph.java、CompiledGraph.java |
| 9 | 多 Agent | ✅ | flow 四件套 + agent-as-tool + 嵌套子图 + A2A 远程 agent；supervisor/handoffs 在 examples | .../agent/flow/agent/、a2a/A2aRemoteAgent.java（supervisor/handoffs 仅 examples/【示例】） |
| 10 | 持久化 | ✅ | CheckpointSaver 10 后端 + threadId/checkPointId/withResume 断点续跑 | graph-core/.../CompiledGraph.java#invoke（resume 语义 javadoc） |
| 11 | HITL | ✅ | 图层 interruptsBefore/After+resume；agent 层 HITL hook（批准/编辑/拒绝）+可替换 Handler | .../agent/hook/hip/HumanInTheLoopHook.java |
| 12 | 观测评估 | ✅ | graph/node/edge/metric Micrometer 观测（核心）+ starter 装配；评估仅 admin（🔶） | graph-core/.../observation/graph/GraphObservationDocumentation.java |
| 13 | 安全治理 | 🟡 | PII 检测/脱敏 hook（核心）+ 沙箱复用 AgentScope Runtime；无统一 guardrail/RBAC 体系 | .../agent/hook/pii/PIIDetectionHook.java |
| 14 | 部署运行时 | 🟡 | Spring Boot 应用即部署单元；A2A JSON-RPC server + Nacos 注册 + 定时调度 + Docker 代码沙箱 | starter-a2a-nacos/.../core/server/GraphAgentExecutor.java |
| 15 | 管理平面 | 🟡 | admin 一站式平台（可视化编排/Dify DSL 迁移/评估/MCP 管理，独立构建 ⚠️）+ studio + Nacos 注入 | spring-ai-alibaba-admin/.../dsl/adapters/DifyDSLAdapter.java、frontend/packages/spark-flow |

⚠️ 待确认 2 项：① DashScope starter 源码仓位置；② admin 模块的发布/构建方式（不在根 modules 与 CI build 中）。

## 5. 维度证据明细

**1 模型接入**【核心+⚠️】
- `AgentLlmNode` 直接持有 Spring AI `ChatClient`：`.stream().chatResponse()`（AgentLlmNode.java:224）与 `.call()`（:267），流式经 `InterceptorChain.applyStreamingInterceptors`（:241）。任何 Spring AI ChatModel（OpenAI/DeepSeek/DashScope…）即插即用。
- 模型治理为核心拦截器：`interceptor/modelfallback`、`interceptor/modelretry`、`hook/modelcalllimit`（模型调用预算）。
- DashScope：本仓库仅消费方证据——admin `DashScopeChatClientFactory`、`DashscopeReranker`；`dashscope-sdk-java 2.15.1` 在根 pom dependencyManagement。starter 源码不在仓内 ⚠️。
- 结构化输出：`Builder#outputType(Class)` → `DefaultBuilder` 用 `BeanOutputConverter`（DefaultBuilder.java:109-110）。

**2 上下文工程**【核心】
- `SummarizationHook`（token 计数超阈值触发历史压缩，SummarizationHook.java:114）+ `TokenCounter`。
- `interceptor/contextediting`（上下文编辑）、`hook/returndirect`、`interceptor/toolselection`（动态工具选择）、`hook/toolcalllimit`（ToolCallLimitHook.java:40）。
- Nacos prompt 注入：`NacosPromptInjector`（starter-config-nacos），支持 `cipher-kms-aes-256-` 前缀加密 dataId。
- README「Context Engineering」官方卖点：HITL、compaction、editing、model & tool call limit、tool retry、planning、dynamic tool selection。

**3 记忆**【核心】
- 无独立 ChatMemory 抽象：会话即 `messages` state key（AppendStrategy 累加）+ checkpoint 持久化，thread 由 `RunnableConfig.threadId` 标识。
- saver 矩阵：`savers/{Memory,VersionedMemory,FileSystem,H2,Mysql,Postgres,Oracle,Mongo,Redis}Saver + AbstractJdbcCheckpointSaver`（目录核实）。
- 跨线程长期 KV：`store/stores/{Memory,FileSystem,Redis,Mongo,Database,Base}Store`（namespace+key，BaseStore.java）。
- 长期记忆/用户画像/遗忘策略：❌ 未见（rg long-term/user-profile 无业务命中）。

**4 RAG**【核心无，生态承载】
- agent-framework/graph-core：❌ 无 retriever/rerank 抽象。
- starter-builtin-nodes `KnowledgeRetrievalNode`（🟡 官方 starter）；admin server-core `core/rag/`（KnowledgeBaseService/IndexPipeline/splitter/DashscopeReranker/vectorstore，VectorStoreType.java:28 枚举仅 ELASTICSEARCH）。
- DashVector / 混合检索 / citation：❌ 未见。

**5 工具系统**【核心】
- 基于 Spring AI `ToolCallback` 扩展：`AsyncToolCallback`、`StateAwareToolCallback`（读写图状态）、`CancellableAsyncToolCallback`+`CancellationToken`（agent/tool/）。
- MCP 三路：① builtin-nodes `McpNode`（HttpClientSseClientTransport+McpSyncClient 直连）；② config-nacos `NacosMcpGatewayToolCallback`（MCP 网关）；③ sandbox `SaaMCPTool`（沙箱内 MCP）。
- 代码执行：builtin-nodes `code/`（DockerCodeExecutor/LocalCommandlineCodeExecutor + java/js/python 模板）。
- Claude Code 式工具在主包：`tools/{ShellTool,WebFetchTool,GlobSearchTool,GrepSearchTool,WriteTodosTool}`、`extension/tools/filesystem/{ReadFile,WriteFile,EditFile,Glob,Grep,ListFiles}Tool`。
- 工具异常/重试/仿真：`interceptor/{toolerror,toolretry,toolemulator}`。
- GraalVM polyglot（pom 依赖）仅测试用 `PythonTool`：🔶。

**6 Skill 机制**【核心】
- `graph/skills/SkillMetadata`：明确注释 "Claude-style Skill"，解析 SKILL.md+frontmatter（SkillMetadata.java:94-118，`allowedTools` 字段）。
- `SkillRegistry`（classpath/filesystem 两实现）：reload/search（按 name 前缀分级打分）/disable（AbstractSkillRegistry.java:80-105）。
- `SpringAiSkillAdvisor`：注释 "following progressive disclosure pattern"——轻量元数据注入 system prompt + `read_skill` 工具按需读全文。
- 配套：`advisors/SkillPromptAugmentAdvisor`、`hook/skills`、`interceptor/skills`、examples/multiagent-patterns/skills【示例】。

**7 规划推理**【核心】
- ReAct 主循环：ReactAgent.initGraph 组 `AGENT_MODEL_NAME`→`AGENT_TOOL_NAME` 循环图（ReactAgent.java:311-405）。
- 步数预算：`CompileConfig.recursionLimit`（CompiledGraph.java:90 默认 25）。
- 规划：`TodoListInterceptor`（system prompt 注入 todo 指引 + WriteTodosTool）；`LoopAgent.loopStrategy` 条件续跑（LoopAgent.java:58-）。
- 任务分解委托：`tools/task/TaskTool`（"Launch a specialized sub-agent…"，BackgroundTask/TaskRepository/AgentSpec 驱动，deepagents 风格）。
- 路由决策结构化：`flow/node/RoutingNode` 用 `BeanOutputConverter<RoutingDecision>`（RoutingNode.java:91）。
- 独立 planner/reflect 抽象：❌（以 hook/interceptor 组合替代）。

**8 编排**【核心】
- node/edge/conditional：`StateGraph#addNode/addEdge/addConditionalEdges`（StateGraph.java:244-475，条件路由 `AsyncCommandAction`+mappings，即 LangGraph Command 路由）。
- 并行：`addParallelConditionalEdges`（AsyncMultiCommandAction 多路分发，StateGraph.java:491）→ 编译期织入 `ConditionalParallelNode`/`ParallelNode`（CompiledGraph.java:154-253；强制单一汇聚点 :179-189）。
- 子图：`addNode(id, StateGraph|CompiledGraph)`（StateGraph.java:327/353）+ `ResumableSubGraphAction`；agent 子图共享 checkpoint 时 threadId 拼接 `parentId_subGraphId`（ReactAgent.java:1121-1125）。
- 中断：`interruptsBefore/After`（CompiledGraph.java:120-129 校验，:429-443 判定）；`StreamMode.{VALUES,SNAPSHOTS}`（:785）。
- 可视化导出：`DiagramGenerator`（Mermaid/PlantUML，StateGraph#getGraph）。
- 定时：`CompiledGraph#schedule` → `ScheduledAgentTask`（CompiledGraph.java:705）。

**9 多 Agent**【核心】
- 流程型：`SequentialAgent`/`ParallelAgent`（fan-out+`DefaultMergeStrategy`，ParallelAgent.java:346）/`LoopAgent`/`LlmRoutingAgent`（均 extends `FlowAgent`）。
- 组合原语：`BaseAgent#asNode()`（BaseAgent.java:49）、`AgentTool.create(agent)`（agent-as-tool，AgentTool.java:75）、`AgentSubGraphNode`（ReactAgent.java:1140）。
- 跨进程：`A2aRemoteAgent`（io.a2a AgentCard → 本地节点，A2aRemoteAgent.java:40）+ starter-a2a-nacos（`NacosAgentRegistry` 注册 AgentCard、`MultiAgentJsonRpcRouterProvider` 多 agent 路由、`GraphAgentExecutor` 执行）。
- supervisor/handoffs/swarm：❌ 核心无专门抽象，examples/multiagent-patterns/{supervisor,handoffs-*} 有【示例】级实现。

**10 持久化**【核心】
- `RunnableConfig`：threadId/checkPointId（RunnableConfig.java:69-71）、`withResume()`（:235）。
- resume 语义有 javadoc 明确：`invoke(Map.of(), config.withResume())` 从最近 checkpoint 的 next node 续跑（CompiledGraph.java:646-663）。
- `updateState(config, values, asNode)`：外部改状态并指定续跑节点（CompiledGraph.java:310-338）。
- saver 家族见维度 3；`getStateHistory` 列全部快照（:257）。

**11 HITL**【核心】
- 图层：interruptsBefore/After + resume（维度 8/10）。
- agent 层：`HumanInTheLoopHook`（@HookPositions(AFTER_MODEL)，实现 `InterruptableAction`；按 toolCall 处理 APPROVED/EDITED（改参重写）/REJECTED（注入拒绝 ToolResponse 说明原因）三态，HumanInTheLoopHook.java:99-115；用 `RemoveByHash` 精确替换消息）。
- 反馈通道：`ReactAgent#interrupt()/updateAgentState()` 写 threadId→INTERRUPTION_FEEDBACK_KEY（ReactAgent.java:233-265，线程安全 javadoc）；`InterruptionHook`（BEFORE_MODEL）消费。
- 交互端可替换：`HumanInteractionHandler`/`ConsoleInteractionHandler`；studio 有 `ToolRequestConfirmMessageDTO` + `AgentResumeRequest`；builtin-nodes `HumanNode`（🟡）。

**12 观测评估**【核心(admin 部分 🔶)】
- graph-core `observation/{graph,node,edge,metric}` 四组：`GraphObservationDocumentation` 等 Micrometer `ObservationDocumentation` 枚举。
- starter-graph-observation：`GraphObservationAutoConfiguration` + `SpringAiAlibabaChatModelObservationConvention`。
- 评估：仅 admin（server-start `EvaluatorDO/EvaluatorTemplateDO/ExperimentResultDO/Mapper`，🔶；admin 独立构建）。

**13 安全治理**【核心 PII + 🟡 整体】
- `hook/pii`：PIIDetectionHook + PIIDetectors/PIIType/RedactionStrategy/PIIMatch（消息出/入脱敏）。
- 沙箱：sandbox 模块复用 `io.agentscope:agentscope-runtime-sandbox-core:1.0.2`，提供 browser/fs/mcp 沙箱工具族（SaaBrowser* 一族）。
- 工具权限/RBAC/audit：❌ 未见（shell 工具有 `hook/shelltool` 治理）；依赖 Spring Security 兜底。

**14 部署运行时**【🟡】
- 无独立 server 进程模型：Spring Boot 应用即部署单元；A2A starter 提供 JSON-RPC 端点（`A2aServerAutoConfiguration`/`A2aRequestHandler`/`GraphAgentExecutor`）并注册 Nacos。
- 定时：`scheduling/`（ScheduledAgentTask + DefaultScheduledAgentManager）。
- 沙箱容器：Docker（DockerCodeExecutor、agentscope runtime）。
- 官方 HA/queue/temporal：❌ 未见。

**15 管理平面**【🟡】
- admin（⚠️独立聚合）：frontend `main`+`spark-flow`（可视化编排画布）+ `difyConverter.ts`；后端 22 个 `NodeDataConverter` + `DifyDSLAdapter/StudioDSLAdapter/DSLDialectType`（Dify DSL 迁移与代码导出）；`MCPManager`；评估；账号域（Account* 枚举，租户/计费深度未验证）。
- studio（核心 modules 内）：Agent/Graph 双 REST API、threads、resume（ThreadController/AgentResumeRequest）、内嵌 agent-chat-ui；`ConfigAgentWatcher` 热加载。
- Nacos 配置面：`NacosModelInjector`（反射替换 ChatClient chatOptions，NacosModelInjector.java:46-49）、`NacosPromptInjector`、`NacosMcpToolsInjector`、`NacosPartnerAgentsInjector`、`NacosReactAgentBuilder`。

## 6. 设计决策要点

1. **站在 langgraph4j 肩膀上做平台**：graph-core 直接 fork 自 bsorrentino/langgraph4j（LICENSE 明示，见第 7 节），类名/概念一一对应；差异在于其上长出了 agent-framework、studio、admin 三层产品化壳。
2. **Agent 即 Graph，hook 织入即节点**：ReactAgent 不重写执行循环，而是把每个 hook 按 BEFORE/AFTER × AGENT/MODEL 四象限编译成图节点（ReactAgent.java:345-405）——上下文工程策略（压缩/PII/HITL/限额）零侵入可插拔。
3. **模型层零锁定**：不自带 provider，全走 Spring AI ChatClient；自身只做治理（fallback/retry/limit/PII）与 Nacos 配置注入；DashScope 反而是外置 starter——「阿里框架不强绑阿里模型」。
4. **记忆=状态+checkpoint，而非独立 ChatMemory**：与 Spring AI 官方 ChatMemory 并行存在两条路线；换来的是 saver 矩阵（内存→文件→H2→MySQL/PG/Oracle/Mongo/Redis）下的断点续跑与持久化。
5. **Claude 系遗产进主包**：SKILL.md 渐进披露（graph-core/skills）、Claude Code 式文件/终端工具族、TodoList 规划、TaskTool 子代理委托——Java 框架中最接近 coding-agent 形态的一套。
6. **沙箱与 AgentScope 互通**：不自研隔离层，直接消费 `io.agentscope` runtime（Docker 内 python/shell/浏览器），并反向提供 starter-agentscope 把 AgentScope agent 适配进自家 flow。
7. **平台与框架分层交付**：studio 进主构建（开发者本地），admin 独立构建（企业平台，含 Dify DSL 迁移以吸收存量低代码用户）——框架库与平台解耦的刻意取舍。

## 7. 与 Apache langgraph4j 的同源关系

- **直接法律证据**：仓库根 LICENSE:209 —— "For the module spring-ai-alibaba-graph-core, it has files originally from a project located at https://github.com/bsorrentino/langgraph4j, licensed under the terms of the: MIT License (Copyright (c) 2024 bsorrentino)"。
- **残留痕迹**：`checkpoint/savers/h2/H2Saver.java:111` 默认 JDBC URL 仍为 `jdbc:h2:mem:langgraph4j`。
- **概念对照（本仓 vs 本地克隆 langgraph4j v1.9.0-beta6）**：`StateGraph`/`CompiledGraph`/`OverAllState`/`RunnableConfig`/`KeyStrategy`(Reducer)/`MemorySaver`/`interruptsBefore/After` 命名体系完全一致；spring-ai-alibaba 在 fork 上新增：skills、observation（Micrometer）、scheduling、store 家族、streaming（GraphFlux/ParallelGraphFlux）、多 Command 并行边（AsyncMultiCommandAction+ConditionalParallelNode）、Studio/Admin 平台层与 agent-framework。
- 结论：可视为「langgraph4j 的企业化延伸分支 + Agent 层重写」；langgraph4j 是 Apache 孵化项目，本仓以 MIT 合规方式吸收其核心。
