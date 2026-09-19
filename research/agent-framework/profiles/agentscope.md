# AgentScope（Python）框架档案

> 基线：~/develop/opensource/agentscope @ b82253ba 2026-09-11；版本 2.0.8（`src/agentscope/_version.py`，pyproject `dynamic = ["version"]`）

## 1. 定位

阿里通义实验室（SysML team）的「灵活而健壮的多智能体平台」，既是一个 Python **库**（`Agent` 单类 + 中间件 + 事件流，pip 安装即用），又自带**平台化服务层**（`agentscope.app.create_app` FastAPI 工厂，可 standalone 或 mount 进现有服务）。v2 做了破坏性重构：v1 的 pipeline 组合子 / msghub / UserAgent / InMemoryMemory 已整体删除，转向「单一 Agent 类 + 配置 + 中间件 + 事件协议 + app 服务层」；多 agent 协作从进程内图编排转向 A2A 协议与 team/subagent 服务化工具。目标用户既包括写脚本的研究者，也包括要部署带权限管控、渠道接入（钉钉/飞书/Discord）、定时调度和企业存储的企业团队。

## 2. 仓库结构与核心包

- 单包 `src/agentscope/`（约 469 个 py 文件，25 个子模块）：`agent/`（含 `_realtime` 子包）、`model/`（11 家供应商子包，每家 `_model.py` + `_models/*.yaml` 模型卡目录，如 dashscope 15 张卡）、`formatter/`（11 家消息格式适配 + MultiAgent 变体）、`middleware/`（含 `_longterm_memory/`、`_tracing/`、`_rag.py`、`_budget.py`）、`state/`、`permission/`、`tool/`（`_builtin/` 内置工具、`_task/` 任务工具）、`mcp/`、`skill/`、`rag/`、`workspace/`（沙箱后端）、`sop/`、`pipeline/`、`event/`、`credential/`、`embedding/`、`tts/`、`realtime/`、`tui/`、`console/`、`app/`（服务层：`_router/` 17 个路由、`_service/`、`storage/`、`message_bus/`、`channel/`、`hub/`、`access/`、`_manager/`、`_tool/` team 工具、`middleware/` app 级中间件）。
- pyproject 构建证据：主依赖即含 `anthropic` / `dashscope` / `openai` / `mcp<2.0.0` / `opentelemetry-*`（OTLP）/ `json_repair[schema]` / `tree_sitter` / `jsonschema`；optional extras 分组：`model-gemini/ollama/xai`、`service`（fastapi/uvicorn/apscheduler/ag-ui-protocol）、`storage-redis/sql/s3`、`channel`（lark/discord/dingtalk）、`workspace-docker/e2b/daytona/k8s/opensandbox`、`tools`（ripgrep）、`tui`（textual）、`a2a`（a2a-sdk）、`vdb-qdrant/milvus/mongodb/elasticsearch`、`rag`（office/pdf 解析器）、`memory-mem0/reme`（mem0ai>=2.0、reme-ai）。requires-python >=3.11。
- `examples/`：a2a / agent_service / console / long_term_memory / pipeline / rag / realtime / tui / web_ui（React+Vite+shadcn 全栈管理界面）/ workspace。

## 3. 核心抽象清单

| 符号 | 路径 | 一句话说明 |
|---|---|---|
| `Agent` | src/agentscope/agent/_agent.py#Agent | 唯一的 agent 类（3915 行单文件），ReAct 行为全靠 config + 中间件 |
| `ReActConfig` / `ContextConfig` / `InjectionConfig` / `ModelConfig` | src/agentscope/agent/_config.py | max_iters=50、压缩阈值 0.8/0.1/0.2、运行态注入、模型 fallback |
| `_GenerateStructuredOutput` | src/agentscope/agent/_agent.py + agent/_structured_output_tool.py | 动态注入的结构化输出工具，到期 tool_choice 强制调用 |
| `Msg` 块模型 | src/agentscope/message/__init__.py | TextBlock/ThinkingBlock/ToolCallBlock/ToolResultBlock/DataBlock/HintBlock + Usage |
| `AgentEvent`（29 个事件类） | src/agentscope/event/_event.py | 流式/HITL/中断/提示统一为 pydantic 事件 |
| `ChatModelBase` | src/agentscope/model/_base.py | retryable-exceptions 重试 + 流式累加器 + context_size + 结构化输出降级 |
| `Toolkit` / `ToolBase` / `ToolGroup` | src/agentscope/tool/_toolkit.py、_base.py、_tool_group.py | 工具注册/分组激活/schema 生成/权限 hook |
| `PermissionEngine` | src/agentscope/permission/_engine.py | 5 模式权限引擎（Claude Code 式） |
| `AgentState` | src/agentscope/state/_state.py#AgentState | context/summary/reply/permission/tool/tasks 全量可序列化状态 |
| `WorkspaceBase` / `SandboxedWorkspaceBase` | src/agentscope/workspace/_base.py、_sandboxed_base.py | 本地 + 7 种沙箱后端，经沙箱内 MCP gateway 执行 |
| `MCPClient` | src/agentscope/mcp/_mcp_client.py | stdio/SSE/streamable-http 统一 MCP 接入 |
| `Skill` / `SkillLoaderBase` | src/agentscope/skill/_base.py | frontmatter 技能卡 + 加载器（progressive disclosure） |
| `KnowledgeBase` / `VectorStoreBase` | src/agentscope/rag/_knowledge.py、_vdb/_vector_store.py | 检索入口 + 4 种向量库后端 |
| `GoalPipeline` / `PipelineProtocol` | src/agentscope/pipeline/ | executor+verifier 循环验证（v1 编排组合子仅存此二者） |
| `SOPEngine` / `SOP` | src/agentscope/sop/_engine.py、_schema.py | 步骤化 SOP 状态机，断点续跑、每步 attempt 预算 |
| `A2AAgent` | src/agentscope/agent/_a2a_agent.py | 有状态 A2A 客户端适配器（远程 agent 当本地 agent 用） |
| `create_app` | src/agentscope/app/_app.py#create_app | FastAPI 工厂：17 路由 + scheduler + channel worker + index worker |
| `SessionService` | src/agentscope/app/_service/_session.py#SessionService | 会话/team/agent/schedule 生命周期 + parked HITL 状态推导 |
| `MessageBus` | src/agentscope/app/message_bus/_base.py#MessageBus | in-memory/Redis 活消息总线（跨 session 投递 + idle wakeup） |
| `TracingMiddleware` | src/agentscope/middleware/_tracing/_trace.py | OTel tracing（gen_ai 语义约定，reply/model/tool span） |
| 长期记忆三中间件 | src/agentscope/middleware/_longterm_memory/__init__.py | AgenticMemory（自研文件式）/ Mem0 / ReMe |

## 4. 15 维度评级总表

| # | 维度 | 评级 | 一句话 | 关键证据 |
|---|---|---|---|---|
| 1 | 模型接入 | ✅ | 11 家 ChatModel + 11 家 formatter，重试/流式/usage/模型卡齐全；fallback 在 agent 层，无 router | model/__init__.py；model/_base.py#ChatModelBase.__call__；agent/_agent.py#_call_model |
| 2 | 上下文工程 | ✅ | 分层压缩：buffer 提醒→自压缩工具→结构化摘要→截断兜底；工具结果与图片独立限额 | agent/_agent.py#compress_context；agent/_config.py#ContextConfig |
| 3 | 记忆 | ✅ | 会话=AgentState.context+summary；长期记忆 3 套中间件（自研 Agentic + mem0/reme 生态依赖） | state/_state.py#AgentState；middleware/_longterm_memory/__init__.py |
| 4 | RAG | ✅ | KnowledgeBase+4 向量库+7 种解析器+app 层 KB 服务/索引 worker；无 rerank/hybrid | rag/_knowledge.py#KnowledgeBase；rag/_vdb/；app/_router/_knowledge_base.py |
| 5 | 工具系统 | ✅ | Toolkit+分组+工具中间件洋葱链+MCP+内置 Bash/Read/Write/Edit/Grep/Glob/AskUser+沙箱超时截断 | tool/_toolkit.py#Toolkit；tool/_base.py#ToolBase；tool/_builtin/_bash.py#Bash.call |
| 6 | Skill 机制 | ✅ | Claude 式两级渐进披露：清单进系统提示 + SkillViewer 工具按需读全文，含技能 hub | tool/_toolkit.py#get_skill_instructions；tool/_builtin/_skill.py#SkillViewer |
| 7 | 规划推理 | ✅ | ReAct 状态机（max_iters=50+强制总结收尾+结构化输出宽限 5 轮）；任务工具+GoalPipeline 验证循环+token 预算 | agent/_agent.py#_next_action；agent/_config.py#ReActConfig；middleware/_budget.py |
| 8 | 编排 | ✅ | 仅 2 个高层模式：GoalPipeline（执行者-验证者循环）与 SOPEngine（步骤状态机）；无通用 graph/DAG（v1 组合子已删） | pipeline/_goal_pipeline.py#GoalPipeline；sop/_engine.py#SOPEngine |
| 9 | 多 Agent | ✅ | A2A 协议客户端 A2AAgent + app 层 team/subagent 工具链（AgentCreate/TeamSay+成员循环中间件）；a2a-sdk 为 optional extra | agent/_a2a_agent.py#A2AAgent；app/_tool/_team_create.py；app/middleware/_team_member_middleware.py |
| 10 | 持久化 | ✅ | AgentState 全量可序列化 + app 层 Storage（SQL/Redis/S3 blob）+ MessageBus；无增量 checkpoint | state/_state.py#AgentState；app/storage/_base.py#StorageBase；app/_service/_session.py#SessionService |
| 11 | HITL | ✅ | 全事件化：确认/外部执行/中断 3 类 Require 事件 + Result 事件重入，parked 状态跨进程恢复，AskUser 多选题工具 | event/_event.py#RequireUserConfirmEvent；agent/_agent.py#_reply_impl；tool/_builtin/_ask_user.py#AskUser |
| 12 | 观测评估 | ✅ | OTel TracingMiddleware（主依赖含 OTLP exporter）+ 29 事件类全链路流；无 eval/dataset 模块 | middleware/_tracing/_trace.py#TracingMiddleware；event/_event.py |
| 13 | 安全治理 | ✅ | 5 模式权限引擎（bypass 免疫 safety ASK + 自动规则建议）+ 危险路径表 + 沙箱全家桶 + 资源访问策略；无内容安全/PII 模块 | permission/_engine.py#PermissionEngine.check_permission；tool/_constants.py；app/access/_policy.py |
| 14 | 部署运行时 | ✅ | create_app FastAPI 工厂（可 mount 进现有服务）+ cron 调度器 + 渠道 worker（钉钉/飞书/Discord）+ Redis 总线 | app/_app.py#create_app；app/_router/_schedule.py；app/channel/ |
| 15 | 管理平面 | 🟡 | 核心 REST 管理 API（session/model/credential/kb/hub/schedule 全覆盖）；Web UI 为示例级（React 管理台在 examples/web_ui） | app/_router/（17 个 router）；examples/web_ui/frontend/ |

## 5. 维度证据明细

### 1) 模型接入【核心】
- 11 家 `*ChatModel`：OpenAIChat / OpenAIResponse（Responses API）/ DashScope / Anthropic / Gemini / Ollama / DeepSeek / Moonshot / Volcengine / XAI（`model/__init__.py`）；gemini/ollama/xai 走 optional extras，anthropic/dashscope/openai 是主依赖（pyproject）。
- 重试：`ChatModelBase.__call__`（`model/_base.py:182`）按 `_get_retryable_exceptions()`（各供应商声明可重试异常）重试 `max_retries`（默认 3）次、`retry_delay` 间隔；`asyncio.CancelledError` 转成 `FinishedReason.INTERRUPTED` 响应而非异常。
- fallback：agent 层 `ModelConfig.fallback_model` + `_call_model`（`agent/_agent.py:3281`）双模型链，每个模型各自 max_retries；无请求级 router/负载均衡（rg "router" 在 model/ 无命中）。
- 流式默认开（`stream=True`），`_StreamAccumulator` 吸收 usage-only 空 chunk；`ChatUsage`（`model/_model_usage.py`）含 input/output/时间及 cache_creation/cache_input tokens。
- 模型卡：`ModelCard.from_yaml` + 各供应商 `_models/*.yaml`（`list_models`，dashscope 15 张：qwen3.8-max、glm-5.2、deepseek-v4-pro 等）。
- 另有独立 `embedding/`（含缓存基座）、`tts/`、`realtime/`（dashscope/openai/gemini/xai 语音实时）三个模型域。

### 2) 上下文工程【核心】
- `compress_context`（`agent/_agent.py:386`）+ `ContextConfig`：`trigger_ratio=0.8` 触发硬压缩、`reserve_ratio=0.1` 保留近期、`context_buffer_ratio=0.2` 缓冲带；压缩用结构化摘要 `SummarySchema`（task_overview/current_state/important_discoveries/next_steps/context_to_preserve 五段，`agent/_config.py:9`）。
- 压缩 prompt 明确要求「相对时间转绝对、指针全限定、记录后台任务」（自包含摘要，为多次压缩设计）。
- `compression_fallback_to_truncation=True`：摘要生成失败回退截断最旧消息并插入 HintBlock（`_agent.py:680-705`）。
- 自压缩工具：`compression_tool_enabled` 时注册 `CompressContext` 工具（永久 ALLOW 权限，`_agent.py:205`），agent 可在硬阈值前主动压缩。
- `tool_result_limit=50000` token 截断工具结果（`_split_tool_result_for_compression`）；`max_image_num=5` 超限图片先 offload 到 workspace 再替换 HintBlock（`_limit_context_images`，`:774`）。
- 运行态注入（`InjectionConfig` + `_inject_runtime_state`，`:1358`）：当前时间（时区/格式可配）、任务状态、上下文水位、同参工具连续失败 N 次的纠错 hint，经 `<system-reminder>` 模板注入。

### 3) 记忆【核心+生态】
- v2 无 `Memory` 类 / `InMemoryMemory`（src 内 rg 无命中）：会话记忆 = `AgentState.context`（原始消息）+ `AgentState.summary`（压缩摘要），随 state 整体持久化。
- 长期记忆全部走 middleware（`middleware/_longterm_memory/`）：`AgenticMemoryMiddleware`（自研，`_agentic_memory/_middleware.py:359`，文件式 memory.md + frontmatter + 清单注入系统提示 + 相关文件检索）；`Mem0Middleware` / `ReMeMiddleware`（第三方，extras `memory-mem0`（mem0ai>=2.0）/`memory-reme`，pyproject 注释写明针对 mem0 v2 架构钉版）。
- 无显式 user profile / user_state 概念（rg `user_state|UserState` 无命中）；会话持久化在 app 层 `SessionService` + `StorageBase`。

### 4) RAG【核心】
- `rag/KnowledgeBase`（`_knowledge.py:44`）：`retrieve` 返回 `(document_id, chunk_index)` 去重、按 score 降序、`top_k=5`、`score_threshold` 过滤；无 rerank / hybrid search / citation 抽象。
- 向量库 4 后端：qdrant / milvus-lite / mongodb / elasticsearch（`rag/_vdb/`，均 optional extras）+ `VectorStoreBase` 抽象。
- 解析器 7 种（`rag/_parser/`：text/pdf/word/excel/ppt/image）+ `ApproxTokenChunker`（token 近似分块）。
- app 层完整 KB 服务：`_router/_knowledge_base.py`（上传/管理 REST）+ `app/rag/`（blob_store（Local/S3）/ index_worker 异步索引 / knowledge_base_manager）+ `enable_index_worker` 开关。
- 检索也可作为 middleware 挂到 agent（`middleware/_rag.py`）。

### 5) 工具系统【核心】
- `Toolkit`（`tool/_toolkit.py:66`）：唯一工具源（tools/MCP/skills 统一注册）、`get_tool_schemas`、`ToolGroup` 分组按 session 激活（`tool/_tool_group.py:10`）。
- `ToolBase`（`tool/_base.py:99`）声明式属性：`is_read_only` / `is_concurrency_safe` / `is_external_tool`（外部进程执行）/ `is_state_injected` / `is_mcp`；hook：`check_permissions` / `match_rule`（Bash 命令子串/通配、文件 glob）/ `generate_suggestions`（自动生成可加的白名单规则）。
- 内置工具（`tool/_builtin/`）：Bash（timeout 默认 120s、上限 600s，`:685-699`）、Read/Write/Edit/Glob/Grep（Grep 由 ripgrep extra 供二进制）、PowerShell、AskUser、SkillViewer；任务工具 TaskCreate/Get/List/Update（`tool/_task/`）。
- 工具级中间件 `ToolMiddlewareBase` 洋葱链（`tool/_base.py:41`），流式/非流式统一为 chunk 生成器。
- MCP（`mcp/_mcp_client.py#MCPClient`）：stdio/SSE/streamable-http 统一、运行时 header 注入（`:260`）、`list_tools` 直接产出 `ToolBase`；主依赖钉 `mcp<2.0.0`。
- 沙箱 workspace（`workspace/`）：`WorkspaceBase` 统一接口 + Local / bubblewrap / docker / e2b / daytona / k8s / opensandbox / applecontainer 八种实现；沙箱内经 MCP gateway 执行（`_sandboxed_base.py#SandboxedWorkspaceBase`）；workspace 兼任上下文 offloader（图片/工具结果外置）。

### 6) Skill 机制【核心】
- `Skill` dataclass（name/description/dir/markdown/updated_at，frontmatter 解析依赖 python-frontmatter）+ `SkillLoaderBase` + `LocalSkillLoader`（`skill/`）。
- 两级渐进披露：`Toolkit.get_skill_instructions`（`_toolkit.py:431`）只把技能清单（名/描述/目录）注入系统提示；agent 需要时调 `Skill` 工具（`tool/_builtin/_skill.py#SkillViewer`，read-only、state 注入）读全文 markdown。
- 生态：`app/hub/_skill`（`SkillHubBase` + `ClawHub` 技能市场拉取）；workspace 初始化可 seed 本地技能目录（`workspace/_base.py` seed_skills）；技能也可作为服务资源经 `_router/_skill.py` 管理。

### 7) 规划推理【核心】
- ReAct 主循环 `_reply_impl`（`agent/_agent.py:1017`）：while 循环内 `_next_action`（`:3491`）返回 `Reasoning | Acting | Exit` 三态分派；一轮 reasoning+acting 全部工具调用有结果才 `cur_iter += 1`。
- 终止语义精细：文本终稿退出（COMPLETED）；`cur_iter == max_iters` 时强制一次「总结收尾」调用（`tool_choice="none"` + system-reminder hint，`:3695`）；`>= max_iters` 标 EXCEED_MAX_ITERS；结构化输出未完成时 `tool_choice` 强制指定 `_GenerateStructuredOutput` 并有 `structured_output_grace_iters=5` 宽限（`:3570-3623`）。
- 防呆：中间件吞掉 ReplyEndEvent 两轮无进展即 raise RuntimeError（busy-loop 检测，`:1147-1156`）；同参工具连续失败达 `tool_retries_limit` 注入纠错 hint。
- 计划：TaskCreate/Get/List/Update 工具 + 任务状态随运行态注入（`InjectionConfig.task_tool_names`）。
- 反思式验证：`GoalPipeline`（executor 报告 → verifier 判 pass/fail/impossible，max_iters=10、每 agent 结构化输出 max_retries=3，HITL 恢复不重置预算）。
- 预算：`ReplyBudgetControlMiddleware`（`middleware/_budget.py:21`）按 reply token 预算控制。
- 结构化输出双路：模型原生（`generate_structured_output` + 失败降级策略 `_get_structured_output_fallback_exceptions`，含关 thinking 重试）与工具注入路（schema 动态注册进 toolkit）。

### 8) 编排【核心（窄带）】
- v1 的 sequential/branch/switch pipeline 组合子与 msghub 在 v2 全部删除；`pipeline/` 仅存 `PipelineProtocol`（duck-typing 协议：有 `reply_stream` 者皆 agent）与 `GoalPipeline`。
- `SOPEngine`（`sop/_engine.py:24`）：SOP=步骤列表（`SOPStep`，可 subclass 自带状态类型），`SOPPhase` 状态机 + `SOPRunState` 断点续跑 + 每步 attempt 预算 + 步骤间 handover；SOPRunState 可序列化校验（步骤数变更即报错）。
- 无通用 graph / DAG / branch / parallel / subgraph / 可视化编排（对应检索无命中）；并行只存在于工具并发批（`_execute_concurrent_tool_calls`）。

### 9) 多 Agent【核心 + 生态 extra】
- `A2AAgent`（`agent/_a2a_agent.py`）：有状态 A2A 客户端适配器，把远程 A2A agent 的 Part 流转成本地 AgentEvent 流（A2A artifact append/last_chunk 语义映射到 block 事件）；a2a-sdk>=1.1.1 为 optional extra。服务端示例 `examples/a2a/server.py`。
- app 层 team 机制（`app/_tool/`）：`AgentCreate`（动态建 sub-agent，支持 `custom_subagent_templates`）、`TeamCreate/TeamSay/TeamDelete/AgentInvite`；`TeamMemberLoopMiddleware`（成员 agent 常驻循环，吞普通 ReplyEndEvent 直到 TeamSay 回报）。
- 多 agent 消息格式：每家供应商 formatter 都有 `*MultiAgentFormatter` 变体（如 `DashScopeMultiAgentFormatter`，`formatter/_dashscope_formatter.py:408`，v1 msghub 的遗产收缩为格式层）。
- 无 supervisor/handoff/graph 原语；编排语义由 SOP（handover）与 team 工具承担。

### 10) 持久化【核心】
- `AgentState`（`state/_state.py:209`）：session_id / summary / context / reply_context（含 cur_iter、structured_schema）/ permission_context / tool_context（read cache）/ tasks_context 全量 pydantic 可序列化，含旧格式迁移 validator；无增量 checkpoint / time-travel。
- app 层 `StorageBase`（`app/storage/_base.py:29`）+ 实现：async SQLAlchemy（aiosqlite/asyncpg/aiomysql 任选 + alembic 迁移，`_sql/`）、Redis（`_redis_storage.py`）、S3 blob（aioboto3 extra）。
- `MessageBus`（in-memory / Redis）与 storage 解耦：持久化可用 SQL、传输用 Redis（`create_app` docstring 明示此设计意图）；bus 承载跨 session inbox 投递与 idle-session wakeup（`app/_bus_ops.py`）。
- `SessionService`（`app/_service/_session.py:98`）：session/team/agent/schedule 生命周期、parked HITL 状态推导（`derive_parked_status` 从 context 反推）、删除级联清理。

### 11) HITL【核心】
- 事件即协议：`RequireUserConfirmEvent` / `RequireExternalExecutionEvent` / `UserInterruptEvent` 三类挂起事件 + 对应 `*ResultEvent` 重入（`event/_event.py:443-533`）；agent 停在 awaiting 态（`_next_action` 返回无 exit_events 的 Exit），跨进程由 SessionService 记 parked 状态，恢复时带 Result 事件重新进入 `reply_stream`。
- `is_external_tool` 工具：执行移交外部进程/人工（RequireExternalExecutionEvent 携带调用参数，结果经 ExternalExecutionResultEvent 回填）。
- `AskUser` 内置工具（`tool/_builtin/_ask_user.py:150`）：多选题/表单式向用户收集信息，answer 结构化。
- 拒绝语义：`stop_on_reject` 配置工具被拒后是停止等待用户还是继续；`UserInterruptEvent` 短路返回 INTERRUPTED 终态。
- 消费端：`console/`（终端交互确认 Ctrl+C 中断处理）、`tui/_ask_user.py`（textual UI）、web_ui `SchemaForm.tsx`/`AgentFormFields.tsx`（schema 驱动表单，与 `json_schema_extra={"format": "textarea"}` 等提示字段呼应）。

### 12) 观测评估【核心】
- `TracingMiddleware`（`middleware/_tracing/_trace.py:117`）：OTel 全链路 span（reply / model-call / tool 执行，外部执行工具补合成 execute_tool span），遵循 gen_ai 语义约定（SpanAttributes/OperationNameValues，`_attributes.py`）；未配置时零开销短路；OTLP exporter 在主依赖。
- 事件流本身即观测载体：29 个 pydantic 事件类覆盖文本/思考/工具调用/工具结果增量的 Start/Delta/End 三段式。
- 日志 rich 格式化（`_logging`）；`ReplyBudgetControlMiddleware` 提供 token 消耗治理。
- eval / dataset / 离线评估：❌ 无对应模块。

### 13) 安全治理【核心】
- `PermissionEngine`（`permission/_engine.py:17`）+ 5 模式（DEFAULT/EXPLORE/ACCEPT_EDITS/BYPASS/DONT_ASK，各模式独立 `_check_<mode>` 方法）；DEFAULT 求值序：deny 规则 → ask 规则 → 只读快路径 → 工具自检（bypass-immune 的 safety ASK 不可被 allow 规则覆盖，如 `rm -rf /`）→ allow 规则 → 默认 ASK；EXPLORE 模式下 allow 规则被有意跳过（只读保证不可让渡）。
- `PermissionDecision.suggested_rules`：拒绝/询问时自动生成可添加的白名单规则建议（`ToolBase.generate_suggestions`）。
- 危险路径防护：`DEFAULT_DANGEROUS_FILES/DIRECTORIES` 常量 + `_is_dangerous_path`（`tool/_base.py:437`）。
- 沙箱执行（workspace 八后端）+ 凭证隔离（`credential/` 独立模块，CredentialBase 各供应商）。
- app 层 `ResourceAccessPolicyBase`（`app/access/_policy.py:79`）：跨 owner 资源访问策略抽象 + `DenyAllResourceAccessPolicy` 默认拒绝。
- 内容安全 / PII / guardrail 专用模块：❌。

### 14) 部署运行时【核心】
- `create_app`（`app/_app.py:78`）：FastAPI 应用工厂，注入 storage/message_bus/workspace_manager/kb/blob_store/hubs/credentials/policy/channels；可 standalone `uvicorn.run` 也可 `root.mount("/agentscope", app)` 嵌入现有服务；lifespan 统一管理后端生命周期。
- 17 个 router（`app/_router/`）：health/session/chat/agent/channel/credential/embedding_model/hub/knowledge_base/mcp/model/schedule/skill/tts_model/workspace + `_schema`。
- 调度：`_router/_schedule.py`（cron 表达式 + 时区校验，改 cron 即重排）+ `app/_manager/_scheduler`（apscheduler）。
- 渠道 worker：`app/channel/`（dingtalk/feishu/discord + dispatcher/decision/routing/credential binding），`enable_channel_worker` 开关。
- 后台设施：`_background_task_manager` / `_chat_run_registry` / `_cancel_dispatcher` / `_wakeup_dispatcher`（idle 唤醒）/ index worker（KB 异步索引）。
- 分布式：无自研 RPC，靠 MessageBus(Redis) + A2A 协议；HA 由 Redis/SQL 后端承载。Docker/Helm：❌ 仓库内未见部署清单。

### 15) 管理平面【🟡 核心 API + 示例级 UI】
- 核心 REST 管理 API 完整：session/model/credential/knowledge_base/hub（MCP/技能市场）/schedule/workspace 全部有管理端点（`app/_router/`）【核心】。
- Web 管理台：`examples/web_ui/`（React + Vite + shadcn + streamdown，前端依赖官方 npm 包 `@agentscope-ai/agentscope` ^0.0.15），组件含 chat/hub/knowledge/form（SchemaForm）/tour【示例】。
- `console/`（`_console.py` + `ConsoleRenderer`）是终端调试入口而非管理台【核心】；tenant/billing/多租户：❌。

## 6. 设计决策要点

1. **单一 Agent 类消灭继承树**：v2 把 ReActAgent 等子类压成一个 3915 行的 `Agent`，行为差异全部交给 `ReActConfig/ContextConfig/InjectionConfig/ModelConfig` 四个配置对象 + 7 个 hook 点的中间件洋葱链（reply/reasoning/check_permission/acting/model_call/system_prompt/compress_context）——扩展靠组合，代价是单文件巨石（与 Java 版 5400 行 ReActAgent 同病）。
2. **事件即协议**：流式增量、HITL 挂起、用户中断、运行态注入统一为 29 个 pydantic 事件类；回复契约 = 事件流 + 终态 Msg 收尾。HITL「parked」状态可跨进程持久化后用 Result 事件恢复，前端/服务层直接消费同一套事件。
3. **分层防御的上下文管理**：水位缓冲带提示（0.6 起）→ agent 自主压缩工具 → 0.8 硬阈值结构化五段摘要（自包含摘要 prompt：相对时间绝对化、指针全限定、后台任务登记）→ 失败截断兜底；图片 offload 到 workspace、工具结果独立 50k token 限额——单维度做到了同类框架最深。
4. **Claude Code 式权限引擎进核心库**：5 模式 + 确定性求值序 + bypass 免疫 safety ASK + 拒绝时自动建议白名单规则，把 CLI agent 的权限模型产品化给服务端多用户场景。
5. **编排的减法**：v1 的 pipeline 组合子/msghub 被整体删除，v2 只留 GoalPipeline（目标-验证循环）与 SOP 引擎两个高层模式，通用多 agent 协作改走 A2A 协议 + app 层 team/subagent 工具——「编排 API 过细生命周期短」的实证案例。
6. **核心库 / 服务层分层**：库层零服务器依赖（fastapi 在 `service` extra），企业能力（session 存储、调度、渠道、KB、hub、访问策略）全放 `agentscope.app`，经 `create_app` 组装并可 mount 进既有 FastAPI——库与平台一套代码两个形态。
7. **模型层用 YAML 模型卡目录而非硬编码**：`list_models` 从各供应商子包 `_models/*.yaml` 读 ModelCard（dashscope 已含 glm/deepseek 竞品卡），用户可扩 `custom_yaml_dir`。
8. **Skill 渐进披露对齐 Anthropic 规范**：清单入 system prompt + `Skill` 工具按需读全文 + hub 市场（ClawHub）+ workspace seed，一级公民实现。

## 7. 跨语言对齐

不适用：本档案为 Python 版（agentscope）；Java 版见独立档案 `agentscope-java.md`（基线 c5db8f72 / v2.0.2+144）。两侧共享设计语言（事件驱动、权限引擎、middleware、HITL parked 语义、v2 删除 v1 pipeline），Python 侧新概念（SOP 引擎、GoalPipeline、分层压缩、web_ui）落地更快，Java 侧则以 Spring starter 矩阵和三进程 service 层见长；逐维度差异在 Java 档案中对齐。
