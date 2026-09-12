# Dify 框架档案

> 基线：~/develop/opensource/dify @ 79effdd498 2026-09-12；版本 1.17.1（api/pyproject.toml / web/package.json）
>
> **视角声明**：Dify 是平台而非库。本档案把 `api/` 的 workflow 引擎当「框架核心」评级；`web/`（Next.js 控制台）只用于维度 15（管理平面）。引擎本体已抽为外部库 `graphon==0.7.0`（api/pyproject.toml:48，PyPI 包，本机未安装，其内部结论以 dify 侧导入面为证据）。

## 1. 定位

开源 LLM 应用开发平台：用可视化 Workflow 画布 + 知识库 + 模型网关 + Agent 节点拼装生成式应用，DSL 导入导出可迁移。目标用户是应用构建者/企业 IT 团队（低代码优先），而非框架开发者。形态是完整服务栈：Flask API + Celery worker + Next.js 控制台 + plugin_daemon + sandbox + agent_backend，docker-compose 拉起 10+ 服务（docker/docker-compose.yaml）。1.17 版架构大迁移：图引擎/基础节点/model_runtime 全部外置为 graphon 库，Agent 运行时独立为 dify-agent（基于 pydantic-ai 的"agenton"框架）+ dify-agent-runtime（Go 的 PTY 沙箱），主仓库变薄。

## 2. 仓库结构与核心包

| 目录 | 内容 | 证据 |
|---|---|---|
| api/ | Python 3.12 Flask + Socket.IO + Celery 后端 | api/app_factory.py、api/pyproject.toml（requires-python 3.12） |
| api/core/workflow/ | 引擎编排层：节点注册表、平台节点、入口组装 | api/core/workflow/workflow_entry.py |
| api/core/agent/ | 经典 Agent 策略（CoT-ReAct / Function Calling） | api/core/agent/cot_agent_runner.py |
| api/core/rag/ | RAG 全管道（extractor/splitter/index_processor/retrieval/rerank/data_post_processor/datasource/vdb） | api/core/rag/ 目录树 |
| api/core/tools/ | 工具引擎：builtin/custom/api/mcp/plugin_tool/workflow_as_tool | api/core/tools/ 目录树 |
| web/ | Next.js 控制台 + WebApp（pnpm monorepo，packages/ 共享 TS 包） | web/package.json（next: catalog） |
| dify-agent/ | 独立 Agent 运行时：pydantic-ai-slim>=2.30，包名 agenton（Layer 组合 + Compositor） | dify-agent/pyproject.toml |
| dify-agent-runtime/ | Go 编写的 shell/PTY 沙箱执行器 | dify-agent-runtime/go.mod |
| docker/ | compose 服务：api、api_websocket、worker、worker_beat、web、postgres、redis、sandbox（dify-sandbox:0.2.15）、plugin_daemon、agent_backend、ssrf_proxy、nginx、local_sandbox | docker/docker-compose.yaml:510-549 |

关键外部依赖：`graphon==0.7.0`（图引擎、基础节点、VariablePool、model_runtime 抽象）；trace 提供者为独立包（dify-trace-opik 为 workspace 成员，api/pyproject.toml:105；langfuse/langsmith/arize 走 PyPI）。

## 3. 核心抽象清单

| 符号 | 路径 | 一句话说明 |
|---|---|---|
| WorkflowEntry | api/core/workflow/workflow_entry.py#WorkflowEntry | 平台侧引擎入口：组装 GraphEngine（线程池 min/max workers + 缩放阈值）并挂 Debug/Limits/Observability 层 |
| DifyNodeFactory | api/core/workflow/node_factory.py#DifyNodeFactory | NodeFactory 实现：从注册表解析节点类并注入平台依赖（模型访问、代码沙箱、HITL callback、工具运行时） |
| register_nodes() | api/core/workflow/node_factory.py#register_nodes | 双注册：graphon.nodes（引擎内置节点）+ core.workflow.nodes（平台节点）自注册到 Node 类注册表 |
| BuiltinNodeTypes | graphon.enums（经 node_factory.py:60 导入） | LLM/START/TOOL/CODE/HTTP_REQUEST/IF_ELSE/ITERATION/LOOP/TEMPLATE_TRANSFORM/QUESTION_CLASSIFIER/PARAMETER_EXTRACTOR/DOCUMENT_EXTRACTOR/HUMAN_INPUT/ANSWER/VARIABLE_AGGREGATOR/LIST_OPERATOR/DATASOURCE/AGENT |
| AgentNode | api/core/workflow/nodes/agent/agent_node.py#AgentNode | 经典 Agent 节点：策略经 AgentStrategyResolver 由插件提供 |
| DifyAgentNode | api/core/workflow/nodes/agent_v2/agent_node.py#DifyAgentNode | 新版 Agent 节点：绑定 dify-agent 后端（pydantic-ai 运行时），支持 ask_human HITL 与会话 workspace |
| TimeSliceLayer | api/core/app/layers/timeslice_layer.py#TimeSliceLayer | GraphEngineLayer 装饰器：CFS 时间片调度，资源超限发 PAUSE 命令 |
| PauseStatePersistenceLayer | api/core/app/layers/pause_state_persist_layer.py#PauseStatePersistenceLayer | 暂停状态（含响应流位置）持久化，支撑断点续跑 |
| WorkflowPersistenceLayer | api/core/app/workflow/layers/persistence.py#WorkflowPersistenceLayer | 引擎事件 → workflow_runs/workflow_node_executions 落库 |
| CotAgentRunner | api/core/agent/cot_agent_runner.py#CotAgentRunner | ReAct 策略：AgentScratchpadUnit 循环、Observation stop 词 |
| FunctionCallAgentRunner | api/core/agent/fc_agent_runner.py#FunctionCallAgentRunner | Function Calling 工具循环 |
| ModelManager / ModelInstance | api/core/model_manager.py#ModelManager(822)/#ModelInstance | 模型实例管理：凭据解析、负载均衡调用、配额 |
| DatasetRetrieval | api/core/rag/retrieval/dataset_retrieval.py#DatasetRetrieval | 检索编排：单库/多库、FunctionCall/ReAct 路由、混合检索、并行多库 |
| DataPostProcessor | api/core/rag/data_post_processor/data_post_processor.py#DataPostProcessor | 重排（模型重排 or 向量/关键词加权）+ reorder |
| TokenBufferMemory | api/core/memory/token_buffer_memory.py#TokenBufferMemory | 会话历史 token 窗口裁剪（默认 max_token_limit=2000） |
| ToolEngine | api/core/tools/tool_engine.py#ToolEngine | 工具统一调用引擎（含 DatasetRetrieverTool） |
| WorkflowGenerator | api/core/workflow/generator/runner.py | LLM 生成工作流：ROUTER→PLANNER→并行 BUILDERS→POSTPROC（web 端 cmd+K `/create`） |
| SkillPackageService | api/services/agent/skill_package_service.py | 校验 .zip/.skill 包：SKILL.md（Anthropic 约定）frontmatter、zip-slip 防护、规范化 |
| HumanInputForm | api/models/human_input.py#HumanInputForm | HITL 表单模型：收件人、审批通道、上传令牌、状态机 |
| Workflow / WorkflowRun / WorkflowNodeExecutionModel / WorkflowNodeExecutionOffload / WorkflowPause / ConversationVariable | api/models/workflow.py:177/790/969/1217/2112/1521 | 草稿/发布版本、运行记录、节点执行（大字段卸载二级表）、暂停状态、会话变量 |
| Conversation / Message | api/models/model.py:1124/1463 | 会话与消息（answer、usage、total_price/currency） |
| OpsTraceManager | api/core/ops/ops_trace_manager.py#OpsTraceManager | 按租户可插拔 trace：配置加解密 + LRU 缓存 + legacy/unified 双注册表 |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | model_runtime 抽象（graphon）+ 供应商全插件化（plugin_daemon）+ 错误感知冷却负载均衡 | api/core/model_manager.py#_round_robin_invoke |
| 2 | 上下文工程 | ✅ | 三级 prompt transform（simple/advanced/agent history）+ Jinja2 模板 + token 窗口裁剪 | api/core/memory/token_buffer_memory.py#TokenBufferMemory |
| 3 | 记忆 | ✅ | 会话/消息持久化 + 会话变量 + 标注回复相似匹配；无跨会话长期记忆/用户画像 | api/models/workflow.py#ConversationVariable |
| 4 | RAG | ✅ | 全管道：抽取/分块/索引/10+ 向量库/混合检索/加权与模型重排/多库路由/引用溯源 | api/core/rag/retrieval/dataset_retrieval.py#DatasetRetrieval |
| 5 | 工具系统 | ✅ | builtin/api/mcp/plugin/workflow_as_tool/dataset 六类工具源 + 独立沙箱服务 + 凭据权限管理 | api/core/tools/tool_engine.py#ToolEngine |
| 6 | Skill 机制 | ✅ | 直接采纳 Anthropic SKILL.md 约定：工作区 Skill 草稿/发布版本/Agent 绑定，执行下沉 agent 后端 | api/services/agent/skill_package_service.py |
| 7 | 规划推理 | ✅ | ReAct（CoT）/FC 双策略 + 参数抽取/问题分类节点 + LLM 自动生成工作流（planner） | api/core/agent/cot_agent_runner.py#CotAgentRunner |
| 8 | 编排 | ✅ | graphon 图引擎：循环/迭代/分支/并行 + 层装饰器扩展点 + 可视化画布（DSL 即代码） | api/core/workflow/workflow_entry.py#WorkflowEntry |
| 9 | 多 Agent | 🔶 | 图中可编排多个 Agent 节点、workflow 互为工具（深度上限）；无内置 supervisor/handoff/swarm 抽象 | api/core/workflow/nodes/agent/agent_node.py#AgentNode |
| 10 | 持久化 | ✅ | 草稿/发布双态版本 + 运行/节点执行（大字段 offload）+ 暂停状态 + Redis 命令通道恢复 | api/models/workflow.py#WorkflowPause |
| 11 | HITL | ✅ | human_input 表单节点 + Agent ask_human 延迟工具映射到同一表单路径 + 超时任务 + 多通道投递/恢复 | api/core/workflow/nodes/human_input/（+ agent_v2/ask_human_hitl.py） |
| 12 | 观测评估 | ✅ | trace 按租户可插拔（langfuse/langsmith/opik/arize-phoenix + OTel 核心内置）；eval 仅 hit-testing/标注，无批量评测框架 | api/core/ops/ops_trace_manager.py#OpsTraceManager |
| 13 | 安全治理 | ✅ | 输入/输出 moderation + SSRF 代理 + 沙箱隔离 + RBAC + 凭据加密与权限（企业审计闭源 🟡） | api/core/moderation/input_moderation.py、api/core/rbac/ |
| 14 | 部署运行时 | ✅ | docker-compose 10+ 服务 + Celery 分级队列/beat + webhook/定时触发节点；Helm 在外部仓库 ⚠️待确认 | docker/docker-compose.yaml、api/tasks/async_workflow_tasks.py |
| 15 | 管理平面 | ✅ | Next.js 控制台：应用/知识库/插件市场/工作区 Skill/成员 RBAC/负载均衡配置 + 云端计费 API | web/app/(commonLayout)/、api/controllers/console/ |

## 5. 维度证据明细

### 1 模型接入 ✅
- 【核心】model_runtime 抽象（LLMResult/LLMResultChunk/LLMUsage/PromptMessage 族）现居 graphon：api/core/agent/fc_agent_runner.py:21-28 从 `graphon.model_runtime.entities` 导入。
- 【核心】供应商全走插件守护进程：api/core/plugin/impl/model.py、model_runtime.py（api 侧为代理）；官方模型插件在外部仓库 dify-official-plugins（边界=plugin_daemon 协议）。
- 【核心】负载均衡+故障转移：ModelInstance._round_robin_invoke 循环 fetch_next，RateLimit 冷却 60s、Authorization/Connection 冷却 10s 后换下一凭据（api/core/model_manager.py:429-478）；LoadBalancingManager.fetch_next（:1036）。
- 【核心】LB 配置有控制台管理面：api/controllers/console/workspace/load_balancing_config.py、services/model_load_balancing_service.py。
- 【核心】流式（LLMResultChunk 生成器贯穿 agent runner）、usage/成本落 Message 表（models/model.py:1498-1499 total_price/currency）；QuotaManagedModelInstance 做配额结算（core/model_manager.py:496）。
- 缓存：凭据多层 Redis 缓存（ops 侧 LRU + 加解密双检锁，core/ops/ops_trace_manager.py:346-360 为同类模式）；LLM 语义缓存 ❌ 未见表级实现。

### 2 上下文工程 ✅
- 【核心】prompt 组装分层：api/core/prompt/（simple_prompt_transform / advanced_prompt_transform / agent_history_prompt_transform + prompt_templates）。
- 【核心】历史裁剪：TokenBufferMemory.get_history_prompt_messages 按 max_token_limit（默认 2000）+ message_limit 双限（core/memory/token_buffer_memory.py:124-232）。
- 【核心】模板渲染走代码沙箱的 Jinja2（CodeExecutorJinja2TemplateRenderer，core/workflow/template_rendering.py）；变量插值为 `{{#node.var#}}` 选择器语义（node_factory.py:539-541 经 VariablePool 取值）。
- LLM 节点支持环境级模型选择器（llm_environment_variable.py：workflow 变量动态换模型），是平台特色的上下文注入。

### 3 记忆 ✅（会话级；长期记忆 ❌）
- 【核心】Conversation/Message 全量持久化（models/model.py:1124/1463），dialogue_count 驱动窗口（advanced_chat/app_generator.py 取 thread messages 长度）。
- 【核心】工作流会话变量：ConversationVariable（models/workflow.py:1521，表 workflow_conversation_variables）+ 持久化层 ConversationVariablePersistLayer（core/app/layers/conversation_variable_persist_layer.py）。
- 【核心】标注回复（相似问命中直接回放答案）：api/services/annotation_service.py（score_threshold 相似度阈值）。
- agent_v2 有 workspace 会话存储：nodes/agent_v2/session_store.py（WorkflowAgentWorkspaceStore）。
- 跨会话长期记忆/用户画像/遗忘机制 ❌（无对应抽象）。

### 4 RAG ✅
- 【核心】索引管道：extractor（含 notion/website 等）/splitter/index_processor + 异步任务化（api/core/indexing_runner.py、tasks/document_indexing_task.py 等 15+ 索引任务）。
- 【核心】向量库抽象：core/rag/datasource/vdb/vector_base.py + vector_factory/vector_backend_registry，compose 可选 weaviate/qdrot/milvus/pgvector/es 等（docker/docker-compose.yaml 可选向量库段）；租户级 group 隔离。
- 【核心】检索编排：DatasetRetrieval 单库/多库（multiple_retrieve 并行线程 + 线程安全包装，dataset_retrieval.py:783-870）；多库路由 FunctionCallMultiDatasetRouter / ReactMultiDatasetRouter（:675-686）。
- 【核心】混合检索+重排：DataPostProcessor 组装 RerankRunnerFactory（模型重排 or weight_rerank 向量/关键词加权）+ ReorderRunner（data_post_processor/ 目录）。
- 【核心】引用溯源：retriever_resources 落 Message 并在响应管道回放（core/app/task_pipeline/easy_ui_based_generate_task_pipeline.py:336）；LLM 节点 retriever 附件加载带 segment 访问校验（node_factory.py:684-714）。
- 【核心】RAG 本身也被编排为 Workflow：services/rag_pipeline/rag_pipeline.py（Pipeline 实体 + PipelineGenerator）。

### 5 工具系统 ✅
- 【核心】工具源六类：core/tools/{builtin_tool,custom_tool,mcp_tool,plugin_tool,workflow_as_tool} + DatasetRetrieverTool（知识库即工具）。
- 【核心】MCP 客户端/服务端双栈：core/mcp/（client、server、auth、session）。
- 【核心】workflow_as_tool：工作流发布为工具，调用深度上限 WORKFLOW_CALL_MAX_DEPTH（core/workflow/workflow_entry.py:139-141，防递归）。
- 【核心】沙箱：独立服务 langgenius/dify-sandbox:0.2.15，CodeExecutor POST /v1/sandbox/run（core/helper/code_executor/code_executor.py:81）；agent_v2 另有 local_sandbox/dify-agent-runtime（Go PTY，compose :548-549）。
- 【核心】凭据管理：models/credential_permission.py（CredentialPermission）+ services/credential_permission_service.py + LB 配置内联校验（model_manager.py:450-464）；工具 OAuth 客户端（models/tools.py:34-72）。
- 工具调用超时/截断在 plugin_daemon 协议侧，api 侧未见统一 timeout 抽象 ⚠️待确认。

### 6 Skill 机制 ✅
- 【核心】Skill 包校验：services/agent/skill_package_service.py——`.zip`/`.skill` 必含 SKILL.md（Anthropic 约定：YAML frontmatter name+description），含 zip-slip 防护、200MB/1MB/5000 条目上限。
- 【核心】工作区 Skill 生命周期：models/skill.py（Skill / SkillDraftFile / SkillVersion / AgentSkillBinding + 快照）——草稿可改、发布版本不可变（manifest 带 hash）、Agent 绑定读绑定表而非快照。
- 【核心】服务层：services/skill_management_service.py（发布生成版本 hash 审计）。
- 执行侧在 agent 后端（agenton layers），api 只校验不执行——渐进披露（progressive disclosure）逻辑随运行时 ⚠️（dify-agent/src 内未见显式 SKILL.md 加载器，绑定经 agent_skill_bindings）。

### 7 规划推理 ✅
- 【核心】CoT/ReAct：CotAgentRunner（scratchpad 单元 + Observation stop + cot_output_parser）；FC：FunctionCallAgentRunner（工具消息循环）（core/agent/）。
- 【核心】结构化输出：PARAMETER_EXTRACTOR 节点（graphon 内置，api 侧注入模型访问）；json-repair 依赖（graphon 依赖树含 json-repair）。
- 【核心】QUESTION_CLASSIFIER 节点做语义路由。
- 【核心】工作流自动生成：core/workflow/generator/runner.py——ROUTER（大工具目录裁剪）→PLANNER（高层节点表）→并行 BUILDERS→POSTPROC（布局/去重/结构校验），产品入口 cmd+K `/create`。
- 最大步数/时限：ExecutionLimitsLayer（max_steps=WORKFLOW_MAX_EXECUTION_STEPS、max_time，workflow_entry.py:178-181）；Agent 迭代上限 AgentMaxIterationError（core/agent/errors.py）。

### 8 编排 ✅
- 【核心】引擎本体 graphon：GraphEngine + GraphEngineConfig（min/max workers、scale_up/down 阈值——动态线程池并行）、VariablePool、GraphRuntimeState（workflow_entry.py:40-49 导入面）。
- 【核心】节点清单（BuiltinNodeTypes 使用统计）：LLM/START/TOOL/CODE/HTTP_REQUEST/IF_ELSE/ITERATION/LOOP/TEMPLATE_TRANSFORM/QUESTION_CLASSIFIER/PARAMETER_EXTRACTOR/DOCUMENT_EXTRACTOR/HUMAN_INPUT/ANSWER/VARIABLE_AGGREGATOR/VARIABLE_ASSIGNER/LIST_OPERATOR/DATASOURCE/AGENT——循环、迭代、分支、并行全内置。
- 【核心】平台扩展点=层装饰器：TimeSliceLayer（CFS）/SuspendLayer/PauseStatePersistenceLayer/ConversationVariablePersistLayer/TriggerPostLayer（core/app/layers/）+ ObservabilityLayer/WorkflowPersistenceLayer（core/app/workflow/layers/）。
- 【核心】子图：无 SUBWORKFLOW 节点 ❌，嵌套经 workflow_as_tool + call_depth；单节点调试 single_step_run（workflow_entry.py:201-232）。
- 【核心】可视化：web/app/components/workflow/（画布组件树）；DSL 导入导出（services/app_dsl_service.py#export_dsl:745 / #import_app:168，含依赖检查）。

### 9 多 Agent 🔶
- 【核心】Agent 节点可多枚共存于一张图（编排=工作流图本身）；Agent 策略插件化（PluginAgentStrategyResolver，nodes/agent/plugin_strategy_adapter.py:14）。
- 【核心】agent 间协作只能靠图连线 / workflow 互调工具 / 变量传递；无 supervisor/handoff/swarm/group chat 原语 ❌。
- 【核心】dify-agent 的 agenton 是"层组合"（Layer/Deps/Compositor 单 Agent 多层能力叠加，dify-agent/src/agenton/layers/base.py），非多 Agent 会话。
- 群聊/角色协作示例：examples 未见 ❌。

### 10 持久化 ✅
- 【核心】Workflow 草稿/发布双态：version='draft' 单副本 + 发布版本号单调递增（models/workflow.py:186-259）；恢复发布快照到草稿（services/workflow_restore.py）。
- 【核心】运行持久化：WorkflowRun(:790) / WorkflowNodeExecutionModel(:969) + WorkflowNodeExecutionOffload(:1217) 大字段卸载二级表防主表膨胀。
- 【核心】暂停/恢复：WorkflowPause(:2112) + PauseStatePersistenceLayer（含 ResponseStreamFilter 流位置）；Redis 命令通道（GraphEngineManager 经 execution_coordinator.py:215 发 stop；graphon command_channels）。
- 【核心】触发器：trigger_webhook/trigger_schedule 节点 + WorkflowTriggerLog（models/trigger.py）。
- 存储：postgres（mysql 可选）+ redis（队列/缓存）+ 对象存储扩展（extensions/ext_storage.py）。

### 11 HITL ✅
- 【核心】HUMAN_INPUT 节点（graphon 内置类型 + Dify 侧运行时）：表单/审批实体 HumanInputNodeData/FormInputConfig/UserActionConfig（nodes/human_input/entities.py），DifyHITLCallback 注入（node_factory.py:590-604）。
- 【核心】表单模型：HumanInputForm/Recipient/UploadToken/UploadFile（models/human_input.py:28-314），审批通道 ApprovalChannel 与投递面权限矩阵（core/workflow/human_input_policy.py：SERVICE_API/CONSOLE/OPENAPI 各自允许的收件人）。
- 【核心】Agent 内 HITL：dify.ask_human 延迟工具调用→翻译为外层工作流同一表单暂停路径（nodes/agent_v2/ask_human_hitl.py 模块头注释 ENG-636；ask_human_resume.py 回填工具结果）。
- 【核心】超时：tasks/human_input_timeout_tasks.py（节点级/全局级超时判定后自动处置）。
- 【核心】恢复入口：service_api workflow_paused 事件流 + resume SSE（controllers/service_api/app/workflow_events.py）、human_input_form.py 双端（console+webapp+service_api）。

### 12 观测评估 ✅（trace 强；eval 弱）
- 【核心】OpsTraceManager：按租户 trace 配置加密存储 + LRU 解密缓存；provider 注册表 legacy + unified 双轨（core/ops/ops_trace_manager.py:345-366 _get_dispatch_entry）。
- 【核心】OTel 内置开关：ENABLE_OTEL 或插件开关时挂 ObservabilityLayer（workflow_entry.py:184-185）；extensions/otel/、core/telemetry/、ext_app_metrics.py。
- 🟡 提供者生态：dify_trace_langfuse/langsmith/opik/arize_phoenix 独立包（opik 为 workspace 成员 api/pyproject.toml:105）；trace 异步落盘 tasks/ops_trace_task.py。
- 🔶 eval：hit_testing_service.py（检索命中测试）+ 标注/feedback；无数据集批量评测运行器（无 model-based eval 框架）❌。

### 13 安全治理 ✅
- 【核心】内容审查：input_moderation/output_moderation（keywords 内置 + openai_moderation API，core/moderation/）。
- 【核心】网络防护：SSRF 代理服务（compose ssrf_proxy:3128，sandbox 与出站请求强制经代理；core/helper/ssrf_proxy.py graphon_ssrf_proxy 同源）。
- 【核心】执行隔离：dify-sandbox 独立容器跑 Code 节点；agent_v2 的 Go PTY local_sandbox；输出文件租户校验（nodes/agent_v2/file_tenant_validator.py）。
- 【核心】RBAC：core/rbac/ + initialize_created_app_rbac_access_task、flask_admission（controllers/console/flask_admission.py）。
- 【核心】凭据：加密存储 + CredentialPermission 权限策略 + 运行时合规复检（model_manager.py:450-464）。
- 🟡 审计事件导出/企业 trace 在闭源 api/enterprise/；SSO/OAuth 外部包。PII 专项 ❌。

### 14 部署运行时 ✅
- 【核心】docker-compose 全家桶：api/api_websocket/worker/worker_beat/web/postgres/redis/sandbox/plugin_daemon/agent_backend/ssrf_proxy/nginx/local_sandbox（docker/docker-compose.yaml）。
- 【核心】Celery 分级队列 + CFS：PROFESSIONAL/TEAM/SANDBOX 三队列（tasks/async_workflow_tasks.py:53-90）+ AsyncWorkflowCFSPlanScheduler + TimeSliceLayer 资源超限暂停——工作流级公平调度。
- 【核心】定时/事件驱动：worker_beat（ext_celery.py beat_schedule）+ trigger_schedule/trigger_webhook 节点 + tasks/trigger_processing_tasks.py。
- 【核心】运行形态：gunicorn 多 worker Flask（gunicorn.conf.py）+ Socket.IO 实时通道；优雅停机 extensions/workflow_warm_shutdown.py。
- Helm：仓库内无 chart ⚠️（社区 dify-kubernetes 独立仓库，未本地验证）；水平扩展依赖 postgres/redis 无本地状态。

### 15 管理平面 ✅
- 【核心】控制台 API：api/controllers/console/（admin、workspace/members/rbac、billing、datasets、plugins、snippets、workflow_run_archive…）。
- 【核心】Web 控制台：web/app/(commonLayout)/（apps、datasets、tools、plugins、marketplace、skills、integrations、installed、explore、templates）——含工作区 Skill 管理页与插件市场。
- 【核心】多租户：tenant_id 贯穿全部业务表；工作区成员角色解析 services/workspace_member_role_resolver.py。
- 🟡 计费：BillingService 调外部计费 API（BILLING_API_URL，services/billing_service.py:219-221；自托管社区版退化为免费额度 quota_service）；企业版闭源。
- 【核心】开放 API 面：service_api（App Key 鉴权，含 workflow 暂停/恢复/SSE）+ inner_api（插件回调）。

## 6. 设计决策要点

1. **引擎外置 graphon**：图引擎、基础节点、model_runtime 抽成 PyPI 库（0.7.0），平台侧只剩节点引导注册 + DifyNodeFactory 依赖注入 + 层装饰器——引擎可独立演进，平台关注点（配额/租户/审计）以 GraphEngineLayer 横切注入而非侵入引擎。
2. **一切皆插件**：模型供应商、工具、Agent 策略、trace 提供者全部经 plugin_daemon / 独立包接入，核心仓库极薄；官方资源外置 dify-official-plugins。
3. **Agent 运行时二分化**：经典策略（CoT/FC，api 内 1000 行级 runner）与新代 agent_v2（独立 dify-agent 服务，pydantic-ai + agenton 层组合 + Go PTY 沙箱）并存，节点级 discriminator 切换（is_dify_agent_node_data）。
4. **错误感知冷却负载均衡**：round-robin + 按错误类型差异化 cooldown（RateLimit 60s / Auth+Connection 10s），比简单重试更适合多凭据池。
5. **资源公平调度**：Celery 按订阅级别分队列 + 引擎内 CFS 时间片层，工作流颗粒度的 QoS——框架库极少做平台级资源治理，Dify 平台属性使然。
6. **大字段卸载 + 草稿/发布双态**：节点执行明细 offload 二级表控制主表膨胀；草稿单副本可改、发布版本不可变可回滚，是"应用即代码"的数据库形态（配合 DSL 导入导出）。
7. **直接采纳 Anthropic Skill 约定**：SKILL.md 包校验/版本化/绑定独立建模，api 只管生命周期不管执行（执行在 agent 后端）——与 Claude 生态技能格式互认。
8. **会话即工作流**：RAG 管道、Agent 应用最终都收敛到 Workflow 引擎执行（RagPipeline=Pipeline=Workflow），单一执行语义。

## 7. 跨语言对齐

不适用（dify 无官方跨语言对等实现；web/ 为前端而非对等框架）。
