# OpenHands 解剖档案（C 组：横切工程）

> 基线：~/develop/opensource/OpenHands @ 60877198a (2026-09-12)；canonical OpenHands/OpenHands（2026 迁移 org）。
> **重要档案说明**：该基线 HEAD 已是 **TypeScript 版「Agent Canvas」**——2026-07-27 提交 cb9138caf「clear repository for Agent Canvas migration (#15397)」清空了全部 Python 代码，仓库根目录现为 npm 包 `@openhands/agent-canvas` 的源码（React + Vite + Electron + Node CLI）。经典 Python 架构（事件流 + Docker runtime sandbox）只存在于 git 历史。
> **本文解剖锚点**：`e8249f00a`（2026-04-18，agenthub/controller/events/runtime/server 完整共存的最后提交；2026-04-19 fd014e8e2 移除 agenthub，2026-04-24 180a35f01 移除 V0 controller，代码文件自带 "IMPORTANT: LEGACY V0 CODE - Deprecated since version 1.0.0, scheduled for removal April 1, 2026" 头）。V1 的 agentic core 已拆到外部仓库 OpenHands/software-agent-sdk（未克隆，不下源码级结论）；V1 app server 曾在本仓库 `openhands/app_server/`（ee9e78b7d 2026-07-25 仍在）。引用格式：`openhands/…#符号` 均相对 e8249f00a 的仓库根；HEAD 上的文件单独注明。

## 1. 产品定位与形态（从简）

- 经典形态（解剖对象）：**自主软件工程 agent 平台**——Web UI（React）+ Python 后端（FastAPI + socket.io）+ 每 session 一个 Docker 沙箱 runtime；另有 headless CLI（`openhands/core/main.py`，`headless_mode: bool = True`）与 GitHub resolver（`openhands/resolver`）。
- 现形态（HEAD 60877198a）：**Agent Canvas**——自托管编码 agent 控制中心，可驱动 OpenHands 自家 agent 或任意 ACP 兼容第三方 agent（Claude Code、Codex、Gemini），后端可切换 local / Docker / VM / cloud，支持定时与 webhook 触发的 automations（Slack/GitHub/Linear 集成）【文档，README.md】。发布为 `ghcr.io/openhands/agent-canvas:1.18.0` Docker 镜像。

## 2. Agent 执行架构（事件流核心）

经典架构是一个**以 EventStream 为中心的单线程事件循环**（非图编排，无 DAG 原语）：

- **事件模型**：`openhands/events/event.py#Event` 基类（id/timestamp/source/cause/timeout/llm_metrics/tool_call_metadata），两大子类 `events/action/`（CmdRunAction、IPythonRunCellAction、FileRead/Write/EditAction、BrowseInteractiveAction、MCPAction、AgentDelegateAction、AgentFinishAction、MessageAction、CondensationAction…，均有 `runnable` ClassVar）与 `events/observation/`（CmdOutputObservation、ErrorObservation、AgentDelegateObservation、RejectObservation…）。每个 Observation 通过 `_cause` 回指触发它的 Action id（`runtime/base.py#_handle_action` 里 `observation._cause = event.id`）——因果链在数据模型层可追溯。
- **EventStream**（`openhands/events/stream.py#EventStream`，继承 EventStore）：
  - `add_event(event, source)`：锁内分配单调递增 id → `event_to_dict` → **写时脱敏**（`_replace_secrets` 把所有 secret 值替换为 `<secret hidden>`，顶层系统字段豁免）→ 逐事件写 FileStore（`sessions/{sid}/events/{id}.json`）→ 满 25 条攒成页缓存 `event_cache/{start}-{end}.json` → 入内存 queue；防重放守卫（事件已带 id 即抛错，防 handler 内回灌造成循环）。
  - 订阅者枚举 `EventStreamSubscriber`：AGENT_CONTROLLER / RUNTIME / SERVER / MEMORY / RESOLVER / MAIN / TEST，按 key 排序分发；**每个 (subscriber, callback_id) 一个单 worker ThreadPoolExecutor + 独立 asyncio loop**（`subscribe()` 里 `ThreadPoolExecutor(max_workers=1, initializer=_init_thread_loop)`）——一个订阅者的慢回调不阻塞其他订阅者，同一订阅者内保序。专用 queue 线程 `_process_queue` 轮询分发。
- **AgentController 循环**（`openhands/controller/agent_controller.py#AgentController`，1392 行）：
  - 仅根 controller 订阅流（delegate 不订阅，由父转发）；`on_event → _on_event → _handle_action/_handle_observation`，再由 `should_step(event)` 决定是否 `_step()`（用户 MessageAction、非 Null 的 Observation、CondensationAction 等触发）。
  - `_step()`：检查 RUNNING 状态与 `_pending_action`（防并发重入）→ StuckDetector → 控制旗标（iteration/budget）→ `agent.step(state)`（CodeActAgent 在 `agenthub/codeact_agent/codeact_agent.py#step` 里先 `condenser.condensed_history(state)` 取压缩视图，再 LLM completion，`response_to_actions` 可产出多 action 队列）→ 若 runnable 且需确认则置 AWAITING_CONFIRMATION（见 §5）→ `event_stream.add_event(action)`。
  - Runtime（同样订阅事件流）收到 Action → 在沙箱执行 → 把 Observation 加回事件流 → controller 收到 Observation 再次 step。**整个 agent 循环 = 两三个订阅者对同一 append-only 日志的反应式消费**，天然获得完整审计轨迹。
- **Delegate 子 agent**（多 agent 机制）：`_handle_action` 遇 `AgentDelegateAction` → `start_delegate()` 创建子 AgentController（`is_delegate=True`，不订阅流；`start_id=最新事件id+1` 即「从流顶起步」；共享 metrics 与 iteration 旗标）→ 父 `on_event` 把事件转发给活跃 delegate，delegate FINISHED/ERROR/REJECTED 后 `end_delegate()` 产出 `AgentDelegateObservation` 回流。
- **上下文压缩（Condenser）**：`openhands/memory/condenser/condenser.py#Condenser.condense → View | Condensation` 二态返回——返回 View（裁剪视图）则正常继续，返回 Condensation 则作为事件回流（`CondensationAction` 声明遗忘哪些 event id + 可选摘要），controller 收到后再 step 一次。实现族：conversation_window / amortized_forgetting / browser_output / llm_attention / llm_summarizing / pipeline（`memory/condenser/impl/`）。上下文超限时 `_step` 捕获 ContextWindowExceededError 发 `CondensationRequestAction`（`agent_controller.py:951-957`）。

## 3. 技术底座（从简）

Python 包 `openhands_ai`；web 层 FastAPI + **socket.io（AsyncServer，ASGI 挂载）**；LLM 接入 **litellm**（`openhands/llm/`，LLMRegistry 共享给 delegate）；沙箱内执行服务器 FastAPI（`runtime/action_execution_server.py`）；shell 会话 **tmux（libtmux）**；浏览器自动化 runtime 子模块；Docker SDK。无 LangGraph/框架依赖——自研事件循环。前端 React。与 agent-framework 档案的交叉引用：不对应任何已调研框架，属自研 harness。

## 4. 状态与持久化（★）

- **事件即真相源（event sourcing）**：会话 = 事件文件序列 + 元数据，全在 FileStore 抽象上（`openhands/storage/files.py#FileStore`；实现 local.py / s3.py / google_cloud.py / memory.py）。路径布局（`storage/locations.py`）：`sessions/{sid}/events/{id}.json`、`metadata.json`、`agent_state.pkl`（State pickle）、`llm_registry.json`、`conversation_stats.pkl`、`event_cache/{start}-{end}.json`；多租户前缀 `users/{user_id}/conversations/{sid}/…`。
- **EventStore 读路径**（`events/event_store.py#EventStore`）：`cur_id` 惰性从文件列表计算；`search_events(start_id, end_id, reverse, filter: EventFilter, limit)` 迭代器 + 25 条页缓存（远端 FileStore 逐文件读太慢，页化批量）。
- **会话恢复**：`server/conversation_manager/standalone_conversation_manager.py#attach_to_conversation`——若本地无活跃会话则重建 EventStream（从存储读回事件）+ StateTracker `_init_history` 从流恢复 history + `set_initial_state(initial_state)`；runtime 侧 `_attach_to_container` 重连已有容器。
- **审计与回放**：每个事件带 source/timestamp/cause/llm_metrics（`_prepare_metrics_for_frontend` 把累计成本挂到 action 上）；`ReplayManager`（`controller/replay.py`）支持按录制的轨迹重放 action（评测用）；`get_trajectory` 导出轨迹；secret 写时脱敏保证日志可外发。
- **并发模型**：单进程多会话。StandaloneConversationManager 持 `_active_conversations`（引用计数元组）、`_detached_conversations`（客户端断开但保活）、`_local_agent_loops_by_sid`（每 sid 一个 Session/agent loop）；`_cleanup_stale` 协程周期清理：超过 `sandbox.close_delay` 且非 RUNNING、无连接的会话统一关闭（`standalone_conversation_manager.py:189-238`）。另有 DockerNestedConversationManager（沙箱内再开 OpenHands 的嵌套场景，709 行）。

## 5. HITL 与风控（★★核心）

经典 confirmation mode 是**动作级预确认协议**，全链路落在事件流上：

1. **触发**（`agent_controller.py#_step` 978-1022）：`state.confirmation_mode` 开启且 action 属于可确认类型（CmdRun/IPython/Browse/FileEdit/FileRead/FileWrite/MCP）时先过 `_handle_security_analyzer`：
   - 配了 SecurityAnalyzer → `security_risk(action)` 打分；**未配置则 fail-safe 置 UNKNOWN，等价于一律询问**（注释明言 "fail-safe approach that ensures confirmation is required"）。
   - `security_risk == HIGH` 或 `UNKNOWN 且无 analyzer` → `action.confirmation_state = AWAITING_CONFIRMATION`，controller 转 `AgentState.AWAITING_USER_CONFIRMATION`，action 以待确认态写入事件流（UI 可渲染待审批卡片）。
2. **审批**：前端经 socket.io `oh_user_action` 发 `ChangeAgentStateAction(user_confirmed / user_rejected)`（`server/listen_socket.py#oh_user_action` → `Session.dispatch` → `event_from_dict` → 以 USER source 写入流）。
3. **放行**（`agent_controller.py#set_agent_state_to` 700-711）：把 `_pending_action.confirmation_state` 改为 CONFIRMED/REJECTED、**清掉 id 后重新 add_event**——被批准的动作作为新事件再走一遍流（runtime 只执行 CONFIRMED 的 runnable action）；REJECTED 则回落 AWAITING_USER_INPUT。审批动作本身也是事件 → 审计链完整。
4. **执行侧二次校验**：runtime 的 `runtime/impl/action_execution/action_execution_client.py:303-317` 对 `AWAITING_CONFIRMATION` 的 action 拒绝执行（返回 ErrorObservation）——纵深防御，controller 缺位时沙箱仍守住。
5. **SecurityAnalyzer 插件体系**（`openhands/security/`，e8249f00a 尚在，2026-04-21 被移除）：ABC `security/analyzer.py#SecurityAnalyzer`（`security_risk(action)` + `handle_api_request`）；注册表 `security/options.py`：`invariant`（**InvariantAnalyzer**：sidecar 起 `ghcr.io/invariantlabs-ai/server:openhands` 容器跑策略引擎，trace 逐事件喂入）、`llm`（LLM 打分）、`grayswan`。
6. 其他控制：`StuckDetector`（`controller/stuck.py`）循环检测 + LoopRecoveryAction 三选一恢复（回滚到 loop 前/复用最后用户消息/停止，`agent_controller.py:613-630`）；max_iterations / `budget_flag`（USD 预算）超限转 ERROR；RATE_LIMITED 状态 + 流量控制提示；`ChangeAgentStateAction` 支持 PAUSED 等任意状态迁移（Ctrl-P 暂停同路径）。

⚠️ 注意：这是 V0 实现。V1（software-agent-sdk 外部仓 + app_server）的确认语义未在本仓库验证。

## 6. 工具与业务系统集成（★沙箱）

- **Runtime 抽象**：`runtime/base.py#Runtime`（1345 行，订阅事件流执行 Action）→ `ActionExecutionClient`（HTTP 客户端）→ 具体实现 `impl/docker`、`impl/remote`、`impl/local`、`impl/cli`、`impl/kubernetes`。**所有动作执行都发生在沙箱内的执行服务器**，宿主只发 HTTP。
- **沙箱内执行服务器**（`runtime/action_execution_server.py`，容器内 FastAPI）：
  - 鉴权：`X-Session-API-Key` 头中间件统一校验（`/alive`、`/server_info` 豁免）；`SESSION_API_KEY` 未设则放行（本地模式）。
  - 端点：`/execute_action`（**统一 action 端点**，收 Action dict 反序列化执行）、`/update_mcp_server`、`/upload_file`、`/download_files`、`/list_files`、`/server_info`（uptime/idle_time/资源——供回收决策）、`/vscode/connection_token`。
  - Bash 会话：`runtime/utils/bash.py#BashSession` 用 libtmux 维持持久 shell（命令拆分 `split_bash_commands`、转义、超时、`is_input` 向运行中进程输入）。
  - MCP：`MCPProxyManager` 把 MCP 工具代理挂载进沙箱内 app（同 session key 鉴权），工具变更经 `/update_mcp_server` 热更新。
- **DockerRuntime**（`impl/docker/docker_runtime.py`）：每 session 一容器（名 `openhands-runtime-{sid}`），`containers.run(init=True)`（tini 收割僵尸进程），端口分区：执行服务器 30000-39999 / VSCode 40000-49999 / app 50000-59999（Windows 缩半），`runtime_binding_address` 控制绑定网卡；镜像按 `runtime/utils/runtime_templates/Dockerfile.j2` 动态构建（非 root 用户 `openhands`、可注入 `runtime_extra_deps`）；workspace 以 volume 挂载 + overlay mounts（只读下层 + per-container COW，`_process_overlay_mounts`）；`docker_runtime_kwargs` 透传任意容器参数；退出监听器 `stop_all_containers` 收割。
- **RemoteRuntime**（`impl/remote/remote_runtime.py`）：远程沙箱集群，默认 **gvisor** 隔离 runtime（`remote_runtime_class`：None/gvisor→gvisor-runc、sysbox→支持容器内 docker），经独立 remote-runtime-api 服务编排（`sandbox.remote_runtime_api_url`）。
- **凭据边界**：宿主持 provider tokens（GitHub 等），`base.py#_export_latest_git_provider_tokens` 检测 action 引用 provider token 时才刷新并注入沙箱 env（`expose_env_vars` + `.bashrc` 持久化）；workspace setup 脚本 `.openhands/setup.sh` 与 pre-commit hook 注入（`maybe_run_setup_script`/`maybe_setup_git_hooks`，保留用户已有 hook）。
- ⚠️ 文档宣称的「端口封锁/进程数限制」在 Docker 代码路径未见硬编码（无 pids_limit/mem_limit/cap_drop），资源限制走 `docker_runtime_kwargs` 透传与 remote runtime 的 gvisor/sysbox；以此为准。

## 7. 部署与产品化

- **服务形态**：`openhands/server/listen.py`——uvicorn + `socketio.ASGIApp(sio, other_asgi_app=base_app)`；中间件：LocalhostCORSMiddleware、CacheControlMiddleware、RateLimitMiddleware（InMemoryRateLimiter 10 req/s）；可选 SPA 静态托管。客户端连 socket 时带 `latest_event_id` 做**事件流断点续传重放**（`listen_socket.py#connect` 逐事件 emit，AgentStateChangedObservation 压轴）；连接级鉴权 `conversation_validator.validate`（cookie/Authorization）+ 可选 SESSION_API_KEY。
- **headless**：`openhands/core/main.py`（`run_agent` headless_mode）无 UI 跑单任务；GitHub resolver 用它做 issue 修复。
- **多租户**：user_auth（`server/user_auth/`）、user_id 贯穿存储路径与 EventStore；conversation 所有权校验（如 `_update_v0_conversation` 403）。
- **观测**：`server/monitoring.py`（无关 OTel 的轻量 monitoring）、ConversationStats 聚合、结构化日志带 session_id/user_id extra、`LOG_ALL_EVENTS` 开关。
- **V1/HEAD 形态**：Agent Canvas 以 npm/Docker 分发，`agent-canvas --frontend-only/--backend-only` 拆分进程；helm/ 目录提供 K8s 部署；多后端（local/remote/cloud）与 ACP agent 接入【文档】。

## 8. 对本项目的适用性（Java + 独立部署 + 图编排 + 财务合规）

**可借鉴模式**（均可在 Java 复刻）：
1. **事件溯源式会话**（`events/stream.py#EventStream` + `event_store.py`）：append-only 事件日志为唯一真相源，controller/runtime/UI 都是其订阅者——财务场景的审计/回放天然满足；Observation.cause 回指 Action 的因果链 + 事件级 llm_metrics/cost 是合规留痕的好骨架。订阅者隔离（每订阅者单线程池保序、互不阻塞）可直接映射 Java 的 per-subscriber single-thread executor。
2. **写时脱敏**（`EventStream._replace_secrets`）：secret 值在持久化前字符串替换——财务数据进审计日志前的 PII/凭据掩码可套用同一位置（持久化适配器层统一做，而非各工具自查）。
3. **审批 = 状态迁移 + 事件重放**（§5 的 AWAITING_CONFIRMATION → 用户事件 → 重发 CONFIRMED 动作）：审批语义在事件流中一等公民，待批动作先入流（可展示）再以确认态重发执行，加上执行侧二次校验——双层防绕过，适合硬审批要求。fail-safe 默认（无分析器 = 一律询问）值得照抄。
4. **可插拔风险分析器**（`security/options.py` 三实现，尤其 Invariant sidecar 策略引擎模式）：Java 侧可做成独立策略服务（OPA/Camunda DMN 或规则引擎容器），controller 只消费 risk 等级。
5. **沙箱即服务**（容器内 FastAPI 执行服务器 + session API key + 统一 /execute_action）：agent 服务与业务服务 API 通信的约束下，把「危险动作执行」隔离进每会话容器、宿主只持 HTTP 客户端，与「agent 服务独立部署」正交可叠加；`server_info.idle_time` 驱动的回收与 detached/active 会话生命周期管理可平移到 agent 会话池。
6. **远端存储页缓存**（25 条/页 event_cache）：事件存对象存储（如 S3/OSS）时的读放大解法。

**不可迁移点**：tmux/libtmux 持久 shell（Java 需另选进程管理）；socket.io（换 WebSocket/SSE 即可，语义可平移）；agent_state.pkl 用 pickle（Java 应 JSON/Protobuf，且 pickle 有反序列化风险，本就是反模式）；`asyncio.get_event_loop().run_until_complete` 在回调里嵌套事件循环的写法脆弱（Java 线程模型下无此问题）。

**避坑**：
- 该架构的确认粒度是**整动作二值**（confirm/reject），没有 Claude Code 式「允许一次/总是/改输入」与规则热更新——财务场景若需细粒度策略，需自行补规则层（见 claude-code-sourcemap 档案 §5）。
- 每事件一个文件的存储在长会话下文件数爆炸（靠页缓存缓解）；若用 DB，单表追加 + 页化物化视图更稳。
- 版本断层风险的真实样本：V0→V1 大迁移把 controller/agenthub 整体拆走，本仓库 HEAD 已无 Python——**引用本档案结论时务必注明 e8249f00a 锚点**；自研系统应把 harness 核心契约（事件模型）做成稳定 API，避免此类推倒重来。
- 委托子 agent 共享同一事件流（delegate 用 start_id 切片区分），多 agent 并发写流时审计归属要靠 start_id/事件区间推断，不如显式 span/correlation-id 清晰。
