# Codex（OpenAI）解剖档案

> 基线：~/develop/opensource/codex @ ee6814bfa4 (2026-09-12)；canonical openai/codex；Apache-2.0。Rust 核心 `codex-rs/`（约 110 个 crate 的 workspace，Bazel+Cargo 双构建）+ TS 生态（`codex-cli` npm 启动器、`sdk/typescript|python`）。本档案属 C 组：维度 1-3 从简，火力在 4/5/6/7。docs/ 多为指向 developers.openai.com 的外链薄文档，能力结论以代码为准。无 agent-framework 交叉引用（自研 loop）。
>
> **与旧资料的差异提醒**：网上广为流传的三档 `suggest / auto-edit / full-access` 在当前基线已演进——代码里的权威枚举是 `AskForApproval{untrusted, on-request(默认), granular(…), never}` × `SandboxMode{read-only(默认), workspace-write, danger-full-access}` 双轴（见维度 5）。README/旧博客的三档说法是产品包装名。

## 1. 产品定位与形态（简）

- 定位：OpenAI 官方编码 agent。**单 Rust 二进制多入口**：`codex`（TUI 交互）、`codex exec`（headless 一次性，JSONL 流）、`codex app-server`（JSON-RPC 服务，供 IDE/桌面客户端）、`codex-linux-sandbox` / `codex-mcp` 等 helper 入口（`codex-rs/cli/src/main.rs` 分发；sandbox helper 经 `arg0` 自调用，`sandboxing/src/landlock.rs#CODEX_LINUX_SANDBOX_ARG0`）。
- TS 的 `codex-cli` 只是启动器：`codex-cli/bin/codex.js` spawn vendor 的平台二进制并转发信号；`sdk/typescript` 的 `exec.ts` 同样 spawn 二进制走 stdio JSONL（`sdk/typescript/src/exec.ts#CodexExec`）。
- 目标用户：开发者（CLI/IDE）；企业侧另有 cloud-tasks（远程任务）形态。

## 2. Agent 执行架构（简）

- **自研 loop**：`core/src/session/`（Session/turn/step_context）+ `codex_thread.rs`、`thread_manager.rs` —— 每 turn 流式请求 Responses API → 解析 ResponseItem（含 `LocalShellCall`/`FunctionCall`）→ 工具执行 → 回注。无图编排。
- 多 agent：`codex_delegate.rs`（委派）、InterAgentCommunication 项进 rollout；cloud-tasks 远程并行。上下文有 WorldState 抽象（`core/src/context/world_state/`，把环境事实与对话分离）。

## 3. 技术底座（简）

- Rust（tokio），协议 crate `protocol` 是核心枢纽：所有事件/请求/配置类型带 `Serialize/Deserialize/JsonSchema/ts_rs(TS)` 三派生——**Rust 类型即协议即 TS SDK 类型**，一条宏链路生成前端类型（`protocol/src/protocol.rs`）。
- 持久化：rollout JSONL（会话转录）+ SQLite state DB（线程索引、日志）。TS 侧零业务逻辑。

## 4. 状态与持久化 ★重点

### Rollout：append-only JSONL 会话转录（事实上的审计日志）

- 【核心】文件布局：`~/.codex/sessions/YYYY/MM/DD/rollout-YYYY-MM-DDThh-mm-ss-<uuid>.jsonl`（`rollout/src/list.rs` L436 注释明示）。
- 【核心】行结构：`history/src/lib.rs` —— `RolloutLine{timestamp, ordinal, item}`；`RolloutItem` 11 变体：`SessionMeta / ResponseItem(模型对话与工具调用) / InterAgentCommunication / Compacted / TurnContext / TokenUsageRecord / WorldState / SecurityRiskScore / RetainedContext / EventMsg / RealtimeItem`。**TokenUsageRecord 和 SecurityRiskScore 单独成持久化项**——成本与安全评分天然入档，审计友好。
- 持久化策略显式声明：`rollout/src/policy.rs#is_persisted_rollout_item`（哪些 ResponseItem/EventMsg 落盘，区分 history mode）。
- 工程细节：`writer_lock.rs`（并发写锁）、`ordinal.rs`（乱序恢复）、`compression.rs`（行级压缩）、`reverse_jsonl_scanner.rs` + `seekable_reader.rs`（**倒序扫描 + 可寻址读**：老会话列表/分页不必全量加载）、`session_index.rs`/`rollout_reference_index.rs`（索引）、`maintenance.rs`（归档/清理）、`rollout_budget.rs`（rollout 大小预算）。
- **审计接口**：`state/src/audit.rs#read_thread_state_audit_rows` —— 只读连接查 SQLite `threads` 表（id/rollout_path/archived/source/model_provider）做诊断审计，不开写池、不触发迁移。另有 `log_db.rs`：tracing 日志按 filter targets 落 SQLite——**运行日志可查询化**。

### Resume / Fork

- 【核心】`core/src/thread_manager.rs#resume_thread_from_rollout / resume_thread_with_history`；`history/src/lib.rs#InitialHistory{New, Cleared, Resumed(ResumedHistory), Forked(Vec<RolloutItem>)}` —— resume 与 fork（带历史分叉，`forked_from_id` 记录血统）是同构入口。会话内 `/clear` 走 Cleared（转录仍保留）。
- resume 后首 turn 与 rollout 的衔接靠 Compacted 项 + `RetainedContext`（跨压缩窗口保留的上下文事件）重建。

### 上下文压缩（compact）

- 【核心】`core/src/compact.rs`：`SUMMARIZATION_PROMPT` 生成摘要；**mid-turn 与 pre-turn 两种模式**——mid-turn 压缩后把 initial context 注入到「最后一条真实 user message 之前」（`InitialContextInjection::BeforeLastUserMessage`），因为模型被训练成期望摘要后紧跟上下文；pre-turn/手动压缩用 `DoNotInject`，下个常规 turn 全量重注入。摘要替换历史，但 `CompactedItem` 元数据（window_number/window_ids/compaction_model_hash）单独持久化——**可追溯是哪个模型在哪个窗口做的压缩**。
- 触发：配置 `model_auto_compact_token_limit`（+scope）与 overflow 兜底；`auto_compact_fallback_prompt/buffer_tokens` 提供无 LLM 兜底（`core/src/config/mod.rs`）。压缩前后有 Pre/PostCompact hook（`hook_runtime.rs`）。`compact_remote*.rs` 系列是服务端压缩协作（v2 含图片预算）。
- 输入侧截断：`utils/output_truncation`（approx_token_count + truncate_text），compact 用户消息上限 20k tokens。

### Checkpoint ⚠️

- 无 cline 式工作区快照/恢复系统；有 `core/src/turn_diff_tracker.rs`（逐 turn diff 追踪展示）与 git 集成（`git-utils`），但「一键回滚到 turn 前」未见实现 ❌。回滚语义主要靠 git 本身（用户操作）。

## 5. HITL 与风控 ★★最重

### 双轴权限模型：审批策略 × 沙箱模式（正交、显式组合）

- 【核心】`protocol/src/protocol.rs#AskForApproval`：`untrusted`（ UnlessTrusted：不信任项目，除非 execpolicy 显式放行一律审批）、`on-request`（**默认**，模型自行决定何时请求审批）、`granular`（细粒度开关 `GranularApprovalConfig{sandbox_approval, rules(execpolicy prompt), skill_approval, request_permissions, mcp_elicitations}`——**关掉=自动拒绝而非跳过询问**）、`never`（失败直接回给模型，绝不升级到人）。
- 【核心】`protocol/src/config_types.rs#SandboxMode`：`read-only`（**默认**）、`workspace-write`、`danger-full-access`。两轴在 CLI 组合出产品化的快捷档（如 full-auto = workspace-write + on-request；`--dangerously-bypass-approvals-and-sandbox` 同时置 never + full-access，`cli/src/main.rs` L2317-2329）。
- 环境级锁定：`protocol/src/environment.rs` —— 环境声明 `approval_policy=Never` 即不可被会话覆盖提升。

### 命令审批决策管线（决策点：命令执行前、策略引擎在进程内）

- 【核心】`core/src/exec_policy.rs#ExecPolicyManager#create_exec_approval_requirement_for_command`：
  1. 命令解析（`command_canonicalization.rs`，处理 shell 语法/别名）；
  2. **execpolicy 规则评估**：`execpolicy` crate —— Starlark 语法的前缀规则（`PrefixRule`/`NetworkRule`），决策 `Decision{Allow, Prompt, Forbidden}`（`execpolicy/src/decision.rs`）；策略经 `ArcSwap` 热更新（审批产生的修正案即时生效）；
  3. 未命中规则的 fallback 渲染 = `approval_policy × permission_profile × 危险命令启发式`（rm -rf、提权、管道到 shell 等，`dangerous_command` heuristics）；
  4. 产出 `ExecApprovalRequirement{Forbidden | NeedsApproval{…} | Skip}`（`core/src/tools/sandboxing/`）——Forbidden 直接拒绝并回注原因，NeedsApproval 走人工，Skip 沙箱内直跑。
- 逃生通道显式建模：沙箱拒绝后的重试带 `EscalationPermissions`（`AdditionalPermissionProfile` 追加或 `ResolvedPermissionProfile` 替换，`protocol/src/approvals.rs`）——「提权」是协议项而不是隐式行为。

### 审批交互协议（服务端定选项、可带修正案）

- 【核心】`protocol/src/approvals.rs#ExecApprovalRequestEvent`：完整命令审批事件——command/cwd/parsed_cmd、`proposed_execpolicy_amendment`（**前缀规则修正案**：批准本次=可顺带把「该前缀以后免批」写进策略）、`additional_permissions`、network 审批上下文（host/protocol/port）、**`available_decisions`（服务端指定客户端可展示的选项集**，老客户端 fallback 到字段推导）。
- 【核心】`ReviewDecision`：`Approved` / `ApprovedExecpolicyAmendment{…}`（批+记规则）/ `ApprovedForSession`（会话级缓存自动批）/ `NetworkPolicyAmendment` / `Abort`……——**「批准并记住」被产品化为一等公民**，且记住的是可审计的规则（规则文件有据可查），不是内存里的 yes 集合。
- 文件修改审批：`ApplyPatchApprovalRequestEvent{changes: HashMap<PathBuf, FileChange>, grant_root}` —— `grant_root` 批准后**本会话内该根可写**（递授权有边界、限会话）。
- 审批人侧事件也入 rollout（EventMsg 审批请求/Guardian 评估），事可回放。

### Guardian：LLM 风险审查层

- 【核心】`protocol/src/approvals.rs#GuardianAssessmentEvent/Action`：对 Command/Execve/WriteStdin/ApplyPatch/NetworkAccess/McpToolCall/RequestPermissions 七类动作做 LLM 评估，输出 risk_level（low→critical）、user_authorization（转写对动作的授权直接度）、rationale、Allow/Deny；触发原因枚举（Policy/FreshRequired/StaleScore/ElevatedRisk/IncompatibleCompaction…）。实现在 `core/src/guardian/` + `guardian_review.rs`。**人审之外多了道自动风险审查**，评分还写进 rollout（SecurityRiskScore 项）。

### OS 级沙箱实现（声明式策略 → 平台后端）

- 【核心】声明式输入：`protocol/src/permissions.rs#FileSystemSandboxPolicy{kind: Restricted/Unrestricted/ExternalSandbox, entries: Vec<{path, access: read/write/deny}>}` —— 语义签名含 readable_roots/writable_roots/unreadable_roots/unreadable_globs；**进程内也有执行**（`ReadDenyMatcher`，非法 glob fail-closed）——文件工具与 OS 沙箱共用同一份策略。
- 平台后端（`sandboxing/src/`）：
  - **macOS Seatbelt**：`seatbelt.rs` + 内嵌 SBPL 策略文件（`seatbelt_base_policy.sbpl`：`(deny default)` 起步、仿 Chrome 渲染器沙箱；网络/偏好/只读平台默认分开成独立 sbpl）；只认 `/usr/bin/sandbox-exec` 防 PATH 注入（L59-63 注释明说威胁模型）。
  - **Linux**：默认 **bubblewrap + seccomp**（`bwrap.rs`、`linux-sandbox/` 独立 helper 二进制，`--apply-seccomp-then-exec`；`landlock.rs` 提供 no_new_privs+seccomp 进程内原语；legacy Landlock 文件系统隔离作为兼容选项，`create_linux_sandbox_command_args_for_permission_profile` 把 PermissionProfile 序列化成 JSON 传给 helper）。
  - **Windows**：restricted token + ACL（`windows-sandbox-rs/src/acl.rs`）与 AppContainer 系（`mxc-sandbox`）双后端。
  - **网络**：`network-proxy/` crate —— 本地 MITM 代理（HTTP/HTTPS CONNECT/SOCKS5），按 host 出审批事件、attribution token 标记进程归属、凭据 broker 管认证——**网络不是开关而是按域名审批**（`NetworkDomainPermissions`、`NetworkPolicyDecision`）。
- 沙箱违规不静默：`violation.rs` 把文件/网络违规结构化上报（`record_filesystem_sandbox_violation`）。

### 终端（PTY）模型下的持续审批

- 【核心】`core/src/unified_exec/stdin_approval.rs`：长驻终端进程的 **stdin 写入也要过审批**（`ExecApprovalKind::WriteStdin`）；注释明示「权限快照归 host 所有：**已运行进程的沙箱不因早先的批准或策略变更而改变**」——运行中不提权。子命令审批经 execve 拦截（approval_id 区分子命令，approvals.rs 字段注释）。

## 6. 工具与业务系统集成 ★重点

- **命令执行**：`core/src/exec.rs` —— tokio spawn + 平台 shell；`DEFAULT_EXEC_COMMAND_TIMEOUT_MS=10s`（超时 exit code 124 惯例）；输出 cap `DEFAULT_OUTPUT_BYTES_CAP=1MB`（PTY 侧，`utils/pty`）+ `MAX_EXEC_OUTPUT_DELTAS_PER_CALL=10_000`；后台孙进程继承 fd 的管道悬挂有专门处理（L88-89 注释）。三种执行语义分级：shell 式（历史 cap/timeout）、internal helper（要完整输出但守 timeout/取消）、file helpers（另一套 SandboxManager 配置）。
- **文件读写**：`file-system` crate 按 `FileSystemSandboxPolicy` 执行（`ExecPermissionProfile`），读 deny glob fail-closed；与 OS 沙箱同源策略——**同一份权限声明两处执行**（工具层 + 系统调用层），纵深防御。
- **MCP**：`core/src/mcp.rs` + `mcp_tool_call.rs` + rmcp 客户端（`rmcp-client`）；MCP 工具调用审批走 Guardian/审批协议（`mcp_tool_approval_templates.rs` 渲染审批参数）；MCP elicitation 表单审批（`ElicitationRequestEvent`，userVerification/form/url 四形态）。**环境级 MCP 管控**：`protocol/src/mcp_policy.rs#EnvironmentMcpPolicy` —— 环境所有者可按 server 的 command/URL（exact/prefix/regex 匹配器）强制要求或限制 MCP server，适合企业托管环境。
- **Skills/插件**：skills 脚本执行有独立审批开关（`skill_approval`）；插件经 plugin/code-mode 沙箱进程跑。
- 业务系统集成本身（Jira/DB 等）不在仓库内——集成面=MCP server + connectors crate（`core/src/connectors.rs`）。
- 凭据：`keyring-store`/`secrets` crate 系统密钥库；ChatGPT 登录态 `login`/`chatgpt` crate。

## 7. 部署与产品化 ★重点（进程模型）

- **客户端-核心进程分离**：TUI/IDE 扩展/TS SDK 都不是核心——它们通过 `protocol` crate 的事件流+命令与 codex 核心进程通信。`app-server`（JSON-RPC over stdio，`app-server/src/lib.rs`：processor loop 处理 JSON-RPC 分发）服务 VS Code 扩展/桌面应用；`app-server-protocol` 带 `schema_fixtures.rs`/`precomputed_exports.rs`（**协议本身有 schema 快照测试**，跨语言契约不漂移）；`app-server-daemon`/`app-server-transport`（daemon 化与传输剥离）。`exec-server` 把 headless exec 也服务化。
- **headless 一等公民**：`codex exec` 输出 JSONL 事件流（`exec/src/event_processor_with_jsonl_output.rs`），`codex exec review` 专项跑代码评审（`exec/src/cli.rs` L157+）——CI/自动化集成入口；`--json` 事件即 protocol 类型序列化，与交互态同一套语义。
- TS 启动器只做发现/签名转发（`codex-cli/bin/codex.js`）；Python/TS SDK 都是对二进制的薄封装——**核心能力 100% 收敛在 Rust 单二进制**。
- 可观测：`analytics`（行为埋点，含 Compaction 事件全维度枚举）、`otel`/`otel-trace-websocket`（OTel 接入）、tracing 落 SQLite（见维度 4）。
- 多租户：❌ 本地单用户；云侧 cloud-tasks/backend-client 是 OpenAI 自有服务协议，非自托管多租户。

## 8. 对本项目的适用性

对照硬约束（Java / 独立部署+API / 图编排 / 财务合规审批审计）：

**可直接借鉴（模式→源码）**
1. **双轴权限模型 + 细粒度「拒绝而非询问」**：`protocol/src/protocol.rs#AskForApproval` × `config_types.rs#SandboxMode`。财务 agent 的对应物：审批策略（每步审/按需审/白名单免审/全拒）与数据访问模式（只读/工作区可写/全放开）**正交组合**，而不是一条滑动杆；`granular` 档的语义（关掉某类审批=自动拒绝，防审批疲劳导致全点同意）值得直接采纳。
2. **审批带修正案（approved + 记规则）**：`approvals.rs#ExecApprovalRequestEvent.proposed_execpolicy_amendment` + `ReviewDecision::ApprovedExecpolicyAmendment/ApprovedForSession`。财务场景：「批准本笔付款 + 以后该供应商 10 万以下自动过」——把「记住授权」变成**可审计的规则修订**（谁、何时、批了什么前缀），且服务端指定可用选项集（客户端不能自由发挥按钮语义）。
3. **声明式权限策略双处执行**：`protocol/src/permissions.rs#FileSystemSandboxPolicy`（同一份 entries 既喂 OS 沙箱又喂进程内文件工具 + deny glob fail-closed）。翻译到 Java：一份「可读/可写/禁读」资源声明，同时驱动服务层鉴权与外部系统（数据库 grant、文件系统 ACL）——单源真相避免两套权限漂移。
4. **rollout JSONL 作为审计底座**：`history/src/lib.rs#RolloutItem`（TokenUsageRecord/SecurityRiskScore 独立持久化项、ordinal/timestamp）+ SQLite 索引（`state/src/audit.rs` 只读审计查询）+ 倒序扫描分页。财务 agent 的会话留痕（谁批的、模型花了多少、风险分多少）按此结构直接设计，**append-only + 摘要不覆盖原文**。
5. **沙箱内直跑 / 需审批 / 禁止 三态预判**：`core/src/exec_policy.rs#ExecPolicyManager` 在命令执行**前**由策略引擎+启发式产出三态，而非先跑失败再问——对财务 agent 的 API 调用同理：先由规则判定放行/人工/禁止，禁止时把原因回注模型让其改道。

**不可迁移点**：OS 沙箱（Seatbelt/Landlock/bubblewrap）与 MITM 网络代理是 Rust 平台层能力，Java 侧无等价物（JVM 进程内可用 SecurityManager 已废弃/OS 层用容器或 gVisor 替代）；Guardian LLM 审查依赖模型供应商基础设施，可借鉴其「评分+rationale+stale 重估」协议但需自建；Responses API 深度绑定。

**避坑**：① 默认档是 read-only + on-request（模型自己决定何时问）——「模型决定」在合规场景不可接受，财务 agent 的默认应为「凡副作用必审批」（对应 cline 的强制 autoApprove:false 思路），untrusted 档语义才是合规友好的；② `never` + full-access 组合存在且 CLI 一 flag 可达，企业部署必须像 `environment.rs` 那样允许**环境级锁死不可覆盖**；③ granular 关闭=拒绝的设计说明：审批体系要防「问太多→人全点同意」的失效模式，规则引擎（execpolicy）承担第一道，人只接规则覆盖不到的灰区。
