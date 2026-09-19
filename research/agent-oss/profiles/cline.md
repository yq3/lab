# Cline 解剖档案

> 基线：~/develop/opensource/cline @ cfe9cadab (2026-09-11)；canonical cline/cline；Apache-2.0（apps/vscode 部分另有 VS Code marketplace 条款）。**仓库形态剧变提示**：当前基线已不是经典的「VS Code 插件单仓 + `src/core/task/index.ts` 巨型 Task 类」——已重构为 monorepo（`apps/vscode` 插件 + `apps/cli` + `sdk/packages` 四个 npm 包 `@cline/shared|llms|agents|core`），核心 agent 循环抽成了**可独立嵌入的 SDK**，并新增常驻 **hub daemon**（detached WebSocket 服务，多客户端共享会话）。网上流传的旧架构资料（shadow git 仓库快照等）与当前代码已不一一对应，本档案以基线代码为准。本档案属 C 组：维度 1-3 从简，火力在 4/5/6/7（横切工程）。无 agent-framework 交叉引用（自研 loop，不在 17 框架清单内）。

架构地图（【核心】`sdk/ARCHITECTURE.md`【文档】+ 代码验证）：

```
sdk/packages/shared   类型/hook 契约/存储路径（无状态底层）
sdk/packages/llms     provider 网关（AI SDK 风格 handler 注册表）
sdk/packages/agents   ★无状态 agent 循环（agent-runtime.ts，工具编排，不碰存储）
sdk/packages/core     ★有状态编排：会话生命周期/持久化/compaction/hub daemon/cron
apps/vscode           VS Code 宿主（extension host 内嵌 SDK；webview 经 protobuf 消息）
apps/cli              CLI 宿主（OpenTUI）
```

分层纪律明写：`agents` 不持有会话持久化/provider 设置存储/宿主审批（ARCHITECTURE.md "Keep agents Stateless"）——循环与宿主环境彻底解耦。

## 1. 产品定位与形态（简）

- 定位：通用编码 agent。当前基线实际是**三形态同核**：VS Code 插件（主产品）、CLI（`apps/cli`）、SDK（`@cline/core` 供第三方嵌入）+ hub daemon（本地 detached 常驻进程，CLI/桌面/浏览器客户端共享同一会话运行时）。
- 交互形态：IDE 面板（webview React/Vite）、终端 TUI、WebSocket 多客户端。
- 目标用户：开发者；SDK 面向集成方。

## 2. Agent 执行架构（简）

- **自研单循环**：`sdk/packages/agents/src/agent-runtime.ts` —— 流式拉取模型输出 → 解析工具调用 → beforeTool hook → 工具策略/审批 → 执行 → 工具结果回注 → 迭代。无图编排（与 agent-framework 轮结论一致：编码 agent 全是自研 loop）。
- 多 agent：`spawn_agent` 一次性委派 + agent teams（`sdk/packages/core/src/extensions/tools/team/`），子会话与根会话同存储、`rootOnly` 过滤展示（`session services` 的 listSessionHistory）。
- 循环有「连续犯错熔断」：`apps/vscode/src/sdk/sdk-interaction-coordinator.ts#handleConsecutiveMistakeLimitReached` —— 达到阈值直接停 run（发 error 消息、状态回 running 可续），不阻塞式提问。

## 3. 技术底座（简）

- TypeScript 全栈（Bun workspace）；provider 层 `@cline/llms` 自研网关（handler 注册表，非 LangChain 等框架）。
- 持久化：会话=JSON 文件（atomic tmp+rename）；agenda 任务/cron=SQLite（`tasks.db`、`cron.db` 与会话分库）。webview React+Vite+Tailwind。
- VS Code 插件与 webview 间通信用 **protobuf 定义**（`apps/vscode/proto/cline/*.proto`，18 个服务域），经 postMessage 承载的类 gRPC request/response（`src/core/controller/grpc-handler.ts` + `grpc-request-registry.ts`）——UI 与核心之间是显式契约而非散装 postMessage。

## 4. 状态与持久化 ★重点

### 会话持久化：懒创建 + 全保真转录

- 【核心】`sdk/packages/core/src/session/services/file-session-service.ts` + `models/session-manifest.ts`：`SessionManifest{version:1, messages_path?}` + sessions 索引 JSON；写入走 `atomicWriteJson`（`.tmp` + rename）。**根会话持久化是懒的**：启动只分配 session ID 不落盘，首个被接受的用户 turn 才建记录（ARCHITECTURE.md "Root-session persistence is lazy"）——避免空历史垃圾行。
- **canonical 转录 append-only 全保真**，compaction 状态另存 `${sessionId}.compaction.json`，恢复时先校验其覆盖的 canonical 前缀 hash，再拼接 compaction 边界之后的消息（ARCHITECTURE.md §Context Compaction；`session/models/session-compaction.ts`）。**审计视角这是正确姿势：摘要可丢、原文不可变**。
- 会话来源双事实分离：`StartSessionInput.source`（客户端 vscode/desktop/cli）与 `mode`（user/automation/subagent/team）都进持久化 envelope——自动化运行必须显式 `mode:"automation"`，事后可区分人机发起。

### 上下文压缩（compaction）：策略在 core、接缝在 agents

- 【核心】`sdk/packages/core/src/extensions/context/`：
  - 触发参数：`compaction-shared.ts` —— `COMPACTION_TRIGGER_RATIO=0.9`（估token 达上下文 90% 触发）、`DEFAULT_TARGET_RATIO=0.7`、`DEFAULT_PRESERVE_RECENT_TOKENS=20_000`、`DEFAULT_MAX_INPUT_TOKENS=128_000`。
  - **双策略注册表**：`basic-compaction.ts`（确定性：保留最近若干 assistant 文本 + 工具活动摘要，**不依赖 LLM**）与 `agentic-compaction.ts`（调 LLM 生成摘要，有独立 summarizer 配置与输入预算投影 `budget-projection/`）。
  - **溢出恢复强制走 basic**：`compaction.ts` 的 `overflowRecovery` 注释明说「provider 刚拒绝过长请求时，恢复不能依赖再一次成功的 LLM 调用」——降级路径确定性设计。
  - 接缝：`@cline/agents` 只暴露 prepare-turn 投影钩子（可改写发给模型的 history/systemPrompt），运行时转录保持 append-only；压缩策略归 core。跨 agent 导入的会话（`metadata.importedFrom`）首 turn 必摘要，模型永不重放外源 agent 的工具调用。
- 工具输出进入上下文前的统一闸门：`extensions/tools/executors/output-limits.ts` —— 命令输出 48k chars（UTF-16 计）头尾保留、中段省略并嵌提示「用 grep/head/tail 收窄」；读文件 2000 行/行 2000 chars/窗口 48k；截断通知固定放头尾（防 provider 侧二次中切把恢复提示切掉）。

### Checkpoint：私有 git index 快照 + 事务式恢复

- 【核心】`sdk/packages/core/src/hooks/checkpoint-hooks.ts`（710 行）：每个 user turn 起 git 快照，但**不动用户工作区**——用私有 index 文件（写在用户 `.git` 内、跨 turn 持久）+ `git commit-tree` 组树；untracked 文件单独组树作为第三父（镜像 `stash create --include-untracked` 语义）。有崩溃恢复（stale `index.lock` 清理）、快照退化（HEAD fallback）遥测 `checkpoint.snapshot`。
- 【核心】`session/checkpoint-restore.ts`：**恢复是事务**——`beginWorktreeRestoreTransaction` 先 `git stash push --include-untracked` 把当前工作区存到私有 ref（`refs/cline/restore-transactions/<uuid>`，立即从用户可见 stash 列表移除），恢复出问题可 rollback；正常 commit 才清 ref。恢复前有「工作区忙」闸（依赖会话 status 真实性，不伪造 running）。
- VS Code 侧 `apps/vscode/src/core/controller/checkpoints/checkpointRestore.ts` 只是薄委托到 SDK `restoreCheckpoint`。
- ⚠️ 经典 cline 的「shadow git（隐藏目录建独立裸仓）」在当前基线已演进为上述「同仓私有 index」方案，旧资料不可直接引用。

### 审计/回放

- hook 审计：`sdk/packages/core/src/hooks/hook-file-hooks.ts#createHookAuditHooks` —— 每个生命周期 hook 事件追加 JSONL（ts+payload）到 `hooks.jsonl`（可用 `CLINE_HOOKS_LOG_PATH` 重定向）。这是**事件级审计底座**（虽面向调试）。
- UI 协议回放：`apps/vscode/src/core/controller/grpc-recorder/` 录制 webview↔host 全部 protobuf 请求/响应（env 门控 `GRPC_RECORDER_ENABLED`），可回放调试。
- 遥测：OTel 通用配置从 remote-config bundle 派生（ARCHITECTURE.md）；`task.completed` 锚定显式完成工具 `submit_and_exit` 而非进程退出，单一 teardown 收口防重复/遗漏。

## 5. HITL 与风控 ★★最重

### 审批决策点：循环内三段管线

【核心】`sdk/packages/agents/src/agent-runtime.ts`（prepareToolExecution，~L1745-1763）每个工具调用前：

1. **beforeTool hooks**（PreToolUse）：可 `skip` 阻断、改写 input、**覆盖策略**（policyOverride）、附加上下文、stop 控制——host 可注入组织级拦截逻辑的官方接缝。
2. **工具策略**：`resolveToolPolicy(toolName, config.toolPolicies)` → `ToolPolicy{enabled?, autoApprove?}`（`sdk/packages/shared/src/llms/tools.ts`，**默认 enabled=true / autoApprove=true**——SDK 裸用时全放行，安全与否是宿主责任）。策略表支持通配 `"*"`（yolo preset 用，`extensions/tools/presets.ts#createToolPoliciesWithPreset`）。
3. **审批回调**：`autoApprove!==true` 时调 `config.requestToolApproval`（宿主注入）。**fail-closed 双保险**：未配置回调=拒绝执行（"requires approval but no approval callback is configured"）；回调抛错=拒绝。

### VS Code 宿主的 auto-approve 接线（经典「设置分档」的现役实现）

- 用户设置面：`apps/vscode/src/shared/AutoApprovalSettings.ts` —— `actions{readFiles, editFiles, executeSafeCommands, useBrowser, useMcp}` 五个动作开关（`executeAllCommands`/`readFilesExternally` 等为 legacy 字段），带版本号防写竞态。
- 【核心】`apps/vscode/src/sdk/sdk-tool-policies.ts`：**双层评估设计**——`buildToolPolicies()` 把所有受管工具（含每个 MCP 工具 `serverName__toolName`）在会话启动时**全部强制 `autoApprove:false`**交给 SDK；真正的放行判断放在审批回调里用 `isToolAutoApproved()` **实时读最新设置**。注释明说动机：用户在任务中途切换 AutoApproveBar 开关也要立即生效，不受会话启动时策略快照限制。MCP 只有全局开关、无 per-tool opt-in（代码注释明示）。
- UI 确认流：【核心】`apps/vscode/src/sdk/sdk-interaction-coordinator.ts#handleRequestToolApproval`：自动批准检查 → （编辑类）**先开 diff 预览再渲染 Approve/Reject 按钮**（审批点拿到了完整工具输入，是唯一的前置展示时机）→ 发 ask 消息进 webview → `setTurnPhase("awaiting_approval")` → 返回 pending Promise，由 webview 按钮经 `resolvePendingToolApproval` resolve。**用户不答先发消息**：路由为排队 follow-up，审批保持 pending（不强迫先批准/拒绝才能说话）。

### Hub 层审批代理（独立部署形态的审批协议）

【核心】`sdk/packages/core/src/hub/server/handlers/approval-handlers.ts`：

- 运行时会话需审批时：hub 生成 `approvalId`，发 `approval.requested` 事件（带 toolName/inputJson/policy/agendaTaskId），挂 `ctx.pendingApprovals` map；客户端用 `approval.respond` 命令回填，hub resolve 挂起的 Promise 并广播 `approval.resolved`。
- **断线不丢、不隐式作答**：`pendingApprovalEvents()` 把 pending 审批事件**重放给（重）订阅的客户端**——审批挂起期间无人在线、或客户端断线重连，请求都重新可见。
- **非交互会话 fail-closed**：`state?.interactive === false` 直接拒绝（"Tool approval requires an interactive session"）。
- automation 语义：`auto_start` 档等有 tool-approval 能力的客户端连上才启动、保守逐工具审批；`unattended` 档才无头自动批准启用工具（ARCHITECTURE.md Agenda 节）。审批能力是**客户端能力声明**（capability），不是所有人都能答。

### 外接审批程序（文件 IPC）

【核心】`sdk/packages/core/src/runtime/tools/tool-approval.ts#requestDesktopToolApproval`：审批决策走文件系统——写 `<sessionId>.request.<id>.json`，轮询 `<sessionId>.decision.<id>.json`（200ms 间隔，默认 5 分钟超时，超时=拒绝并清理）。**外部程序（desktop 壳）实现审批 UI 的进程间协议**，token 字符白名单消毒。对「审批服务外置」是现成参考（虽然轮询朴素）。

### 命令级防线与产品化审批

- plan 模式命令黑名单：【核心】`extensions/tools/command-guard.ts` —— POSIX/PowerShell 写类命令（rm/mv/cp/git add|commit|push…、npm/pip/cargo 安装子命令）+ 输出重定向拒绝；heredoc/引号/注释做掩码预处理防误报。**文档自认边界**：是黑名单不是 shell 解释器，拦不住 `python -c "open(...,'w')"`——诚实的安全声明。
- Agenda 任务审批（版本绑定防 TOCTOU）：【核心】`sdk/packages/core/src/tasks/` —— 每个任务 `pending_approval` 起步，审批绑定 `approvedRevision`；**执行相关编辑即 bump revision 并撤销旧审批**；审批/执行与磁盘上的 canonical Markdown spec 同步对账，不一致 fail-closed；agent 建的任务默认不自动获批（`applyToAgentCreated`）。「批准的是哪个版本」被显式建模——财务场景直接可抄。

### 转写时的行为

- 审批 ask 期间聊天输入 → follow-up 排队（不隐式批准）；取消会话 → pending 审批 resolve false（TOOL_REJECTION_SUFFIX 回注模型，模型知道被拒原因继续）。

## 6. 工具与业务系统集成 ★重点

- **工具面按 preset 组合**：`extensions/tools/presets.ts` —— act/plan/search/minimal/yolo 五档布尔组合（enableReadFiles/enableBash/enableEditor/…）；plan 档保留 bash 供只读调查但配 command-guard。工具执行器与定义分离：`executors/`（bash/editor/file-read/search/web-fetch/apply-patch），宿主可注入自定义 executor（SDK 文档示例直接演示替换 readFile/webFetch）——**业务系统集成的官方接缝是 executor 注入**。
- **命令执行封装**：【核心】`extensions/tools/executors/bash.ts` —— `node:child_process.spawn` + 平台默认 shell（无 OS 沙箱、无容器，**纯审批制**）；detached 命令日志 10MB 上限/24h 保留，PID+进程代 start-token 防 PID 复用误判，完成标记区分静默活进程与已退出；输出 48k chars 截断（见维度 4）；进度 48ms 合并上报。挂起命令可 `proceed_while_running`：释放 abort/timeout 所有权、带当前有界输出 resolve 工具调用、继续排水到日志文件——**长任务与对话解耦**。
- **文件读写边界**：`executors/editor.ts#resolveFilePath` —— `restrictToCwd`（默认 true）只约束**相对路径**必须落在 cwd 内（`path.relative` 校验），**绝对路径直通**；读文件无路径限制只有输出 cap。结论：cline 的文件边界是「软约束+审批」，不是硬隔离。
- **MCP**：`extensions/mcp/`（manager/client/tools/policies/config-loader）+ VS Code 侧 `apps/vscode/src/services/mcp/McpHub.ts`（含 OAuth `McpOAuthManager`、StreamableHttp 重连）。工具命名 `serverName__toolName` 进统一策略表（per-tool `enabled:false` 可禁用，`policies.ts`）；审批归一到 `useMcp` 单开关（宿主层），SDK 层与其他工具同一 ToolPolicy 通道。远程 MCP 有 remote-proxy。
- **凭据**：MCP OAuth 有专门管理器；provider API key 存 VS Code SecretState（`apps/vscode/src/services/`）⚠️未逐文件核验。hub 本地认证：per-process 随机 token + owner-only 权限 discovery 文件 + 常数时间比较（ARCHITECTURE.md，本地多进程信任边界）。
- 业务系统（Jira/数据库等）无内置连接器；集成路径=MCP 或自写 executor/hook（`extensions/plugin/` 沙箱子进程插件，30min 空闲回收，pending 请求绑定子进程代防误杀）。

## 7. 部署与产品化 ★重点（进程模型）

- **同一 SDK 三种宿主进程**：
  1. **VS Code extension host 进程内嵌**（`apps/vscode`，经 `SdkController`/`vscode-session-host.ts` 适配）；
  2. **CLI 进程**（`apps/cli`，启动不等待 daemon，本地 runtime 兜底保首帧渲染）；
  3. **hub daemon**（detached 常驻：WebSocket `/hub` + 本地 discovery 文件认证；会话归 daemon 所有，客户端可随意 attach/detach，**换客户端续流**；daemon 崩了由下次使用重建）。
- **RuntimeHost 统一执行边界**：【核心】`sdk/packages/core/src/runtime/host/runtime-host.ts` —— `LocalRuntimeHost`/`HubRuntimeHost`/`RemoteRuntimeHost` 三实现同接口，`ClineCore` 统一委派不分支（ARCHITECTURE.md §Runtime Host Boundary）；`RuntimeSessionConfig` 传输中立，宿主本地差异收在 `localRuntime`。**这是「agent 核心与部署形态解耦」的教科书 seam**：同一会话逻辑既进程内跑、又可挪到远端 hub 跑，审批/事件/工具执行器全部代理穿透（客户端贡献的 tool executor 经 hub capability 请求代理）。
- 升级治理：SDK 构建嵌入源码+依赖指纹与 build epoch，两个并发安装的 hub 收敛到最新构建而非互相替换（ARCHITECTURE.md）。
- 可观测：注入式 `BasicLogger`（宿主映射到 pino/OutputChannel）；OTel 事件（task.completed 等）；usage 双桶（root vs aggregate 含队友/子 agent）——**多 agent 成本归因**先例。
- 自动化/调度：`core/src/cron/`（Markdown frontmatter spec + SQLite 队列 + 原子 claim + 并发/链深/每小时护栏 + 运行报告 md）与 Agenda 任务系统（见维度 5）——**无人值守运行的完整工程化样例**（取消语义、lease 丢失、终端状态先持久化再写报告等）。
- 多租户/配额：❌ 无（单用户本地产品）。远程 hub 形态留了口子（RemoteRuntimeHost + HTTP header 认证解析器），但无租户隔离实现。

## 8. 对本项目的适用性

对照硬约束（Java / 独立部署+API / 图编排 / 财务合规审批审计）：

**可直接借鉴（模式→源码）**
1. **审批三段管线 + fail-closed 回调**：`agents/src/agent-runtime.ts`（beforeTool hook → ToolPolicy → requestToolApproval 注入回调，未配置即拒绝）。翻译成 Java：工具调用前拦截器链（hook 可覆盖策略）+ `ApprovalCallback` 接口由审批服务实现；默认拒绝而非默认放行（注意 cline SDK 裸默认是 autoApprove=true，**必须学 VS Code 宿主那层「强制全 false + 回调内实时评估」**，`sdk-tool-policies.ts`——策略快照过期问题是真踩过的坑）。
2. **审批作为事件 + 断线重放**：`hub/server/handlers/approval-handlers.ts` —— `approval.requested` 事件挂 pending map、重订阅重放、`approval.respond` 命令、非交互会话拒绝。对「agent 服务独立部署、审批走 API」是最贴身的参考：审批请求是**可重放的事件**而非一次性 RPC，审批人掉线不丢单也不默认放行。
3. **审批与被审内容版本绑定**：`core/src/tasks/agenda-task-manager.ts` 的 `approvedRevision`（编辑即撤销审批、spec 对账 fail-closed）——财务场景「批的是这版凭证分录/这笔付款」的同构物，防批准后内容被偷换。
4. **compaction 双策略 + 溢出恢复确定性**：`extensions/context/compaction.ts`（0.9 触发/0.7 目标/保留最近 20k；LLM 摘要失败或上下文溢出时降级到确定性 basic）+ canonical 转录 append-only、摘要旁挂带 hash 校验——审计要求「原始记录不可变」时照抄这个分离。
5. **checkpoint 事务**：`session/checkpoint-restore.ts`（恢复前先把现状 stash 到私有 ref，可 rollback）——「agent 改错可回滚」且回滚本身不破坏现场。

**不可迁移点**：VS Code webview/proto 消息层（依赖插件宿主）；git 快照强绑代码场景（财务数据快照需另设计，但「私有 ref + 事务」思想可移）；TS/Bun 生态。

**避坑**：① cline 无 OS 级沙箱，命令防线=审批+黑名单，黑名单自认可绕过（command-guard.ts 头注释）——若财务 agent 允许执行任意命令，必须另加真隔离（参照 codex 档案）；② SDK 默认 autoApprove=true 是「宿主负责安全」的设计，直接嵌 SDK 不改策略=裸奔；③ `enabled` 与 `autoApprove` 两个正交开关的语义要分清（禁用工具 vs 需审批）。
