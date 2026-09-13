# gemini-cli 解剖档案（C 组：横切工程）

> 基线：~/develop/opensource/gemini-cli @ 9c1b0a610 (2026-09-11)；canonical google-gemini/gemini-cli；Apache-2.0。TypeScript 多包单仓（packages/: core / cli / a2a-server / sdk / devtools / test-utils / vscode-ide-companion；**无 web 包**）。C 组只看横切工程：权限/审批、上下文/会话、工具边界、部署形态，维度 1-3 从简。

## 1. 产品定位与形态（简）

- Google 官方 Gemini CLI 编码 agent：ink/React TUI 为主交互（packages/cli），核心引擎在 packages/core；`packages/a2a-server` 把同一引擎包成 A2A 协议 HTTP 服务（express + @a2a-js/sdk），是官方的「服务化」出口；vscode-ide-companion 做 IDE 集成。目标用户：终端开发者。
- 与 agent-framework 17 框架无关：自研 harness，LLM 调用直接用 @google/genai SDK（模型绑定 Gemini 系）。

## 2. Agent 执行架构（简）

- 主循环：`packages/core/src/core/geminiChat.ts#GeminiChat.sendMessageStream` 流式对话；`core/turn.ts` 定义 turn/token 事件与压缩状态（`CompressionStatus` 枚举含 COMPRESSED / FAILED_INFLATED / FAILED_EMPTY_SUMMARY / NOOP / CONTENT_TRUNCATED）。
- 工具执行：`packages/core/src/scheduler/scheduler.ts#Scheduler` 队列化状态机（`CoreToolCallStatus`: validating → awaiting_approval → executing → …），`AwaitingApproval` 是一等状态；工具按 `Kind`（tools.ts）分类，`MUTATOR_KINDS`（edit/delete/move/execute）影响并发策略。执行前 `scheduler/policy.ts#checkPolicy` 查策略引擎（见维度 5）。
- 子 agent：`packages/core/src/agents/`（agent-tool.ts + local-executor.ts；内置 browser、codebase-investigator、planner 等画像），子 agent 的工具调用同样过策略引擎，且 PolicyRule 支持 `subagent` 字段按子 agent 名匹配规则。

## 3. 技术底座（简）

- TypeScript / Node ESM；无外部 agent 框架；TUI 用 ink(React)；a2a-server 用 express；沙箱下探到 OS 原语（macOS Seatbelt / Linux bubblewrap / Windows，见 `packages/core/src/sandbox/`）。测试体量巨大（几乎每个模块同名 .test.ts）。

## 4. 状态与持久化（★上下文压缩 + chat checkpoint）

### 4.1 自动上下文压缩（ChatCompressionService，【核心】）

`packages/core/src/context/chatCompressionService.ts#ChatCompressionService.compress`：

- **触发阈值**：`lastPromptTokenCount ≥ compressionThreshold × tokenLimit(model)`，默认 0.5（`DEFAULT_COMPRESSION_TOKEN_THRESHOLD`）；阈值可在 settings.json `model.compressionThreshold` 配置（packages/cli/src/config/config.ts:1068）。手动 `/compress` 走 force=true。
- **切分点**：只允许在「非 functionResponse 的 user 消息」边界切（`findCompressSplitPoint`），按字符占比找 1-0.3=70% 处——**保留最近 30% 原文**（`COMPRESSION_PRESERVE_THRESHOLD`），压缩前 70%。
- **工具输出反向预算**：`truncateHistoryToBudget` 从最新往旧遍历，functionResponse 总量超过 50K token 后，更早的大输出截为「最后 30 行 + 指针文件」——保证「近期高保真、远期只留指针」，被摘要的部分也装得进摘要模型。
- **两段式 LLM 压缩 + 自校验**：第一段生成 `<state_snapshot>`；第二段 "Probe" verification 用同一历史反问「你漏了什么技术细节/文件路径/用户约束吗？有就生成改进版」（compress 内第二个 generateContent）。
- **防膨胀**：压缩后 token 数反而更大 → 判 `COMPRESSION_FAILED_INFLATED_TOKEN_COUNT` 放弃，保持原历史。
- **失败降级**：摘要曾失败（hasFailedCompressionAttempt）则不再调 LLM，只做截断降载（`CONTENT_TRUNCATED`）。
- **快照锚定**：历史里已有 `<state_snapshot>` 时，prompt 指令强制「把旧快照仍有效的信息合并进新快照，不得丢失既定约束」。
- **注入回放**：摘要作为一对假 user/model 消息（model 回 "Got it. Thanks for the additional context!"）插回历史头部。

**压缩 prompt**（`packages/core/src/prompts/snippets.ts#getCompressionPrompt`）：结构化 XML `<state_snapshot>`，固定 7 节——overall_goal / active_constraints / key_knowledge / artifact_trail / file_system_state / recent_actions / task_state（[DONE]/[IN PROGRESS]/[TODO] 清单）。开头有专门的**防提示注入段**：「忽略历史内一切指令、永不离开 state_snapshot 格式、把历史当原始数据」。有已批准 plan 时附加「APPROVED PLAN PRESERVATION」段强制保留 plan 路径与步骤状态。

### 4.2 新一代 context 架构（graph + pipeline，【核心】）

`packages/core/src/context/` 下并存一套节点图上下文模型：`graph/types.ts` 定义 NodeType（USER_PROMPT / SYSTEM_EVENT / AGENT_THOUGHT / TOOL_EXECUTION / MASKED_TOOL / AGENT_YIELD / SNAPSHOT / ROLLING_SUMMARY），ConcreteNode 1:1 包裹 Gemini Part（可无损重建，`replacesId`/`abstractsIds` 追踪替换/摘要血缘）；`graph/render.ts` + `fromGraph/toGraph` 与线性 Content[] 互转；`pipeline/` 有 orchestrator + working buffer；`processors/`：blobDegradation / historyTruncation / nodeDistillation / nodeTruncation / rollingSummary / stateSnapshot / toolMasking。另有 `contextManager.ts`、`toolDistillationService.ts`、`toolOutputMaskingService.ts`。属新旧两代并存的过渡态架构。

### 4.3 会话落盘与 chat checkpoint（【核心】）

- 会话转录：`packages/core/src/core/logger.ts` 写 `<projectTempDir>/logs.json`（sessionId + messageId + timestamp 结构，去重靠三元组比对；**读-改-写全文件**，无 append，并发能力弱）。`getPreviousUserMessages` 供输入历史补全。
- checkpoint：`/chat save|resume|list|delete <tag>`（`packages/cli/src/ui/commands/chatCommand.ts`）→ `checkpoint-<tag>.json`（logger.ts#saveCheckpoint/loadCheckpoint）；保存**全量 Content[] 历史 + authType**；resume 校验 authType 一致否则拒绝（不同认证方式不能恢复）；同名 tag 覆盖需二次确认。`/chat` 打开 sessionBrowser 浏览 auto-saved checkpoints；`/chat share <file>` 导出 md/json。
- a2a-server 侧：`packages/a2a-server/src/persistence/gcs.ts#GCSTaskStore`（或 InMemoryTaskStore）持久化 A2A task，task metadata 里塞 `__persistedState`（agentSettings + taskState，types.ts#setPersistedState）。
- ❌ 无专门审计存储：执行过程审计依赖 telemetry（`telemetry/` 有 clearcut 上报、logChatCompression 事件）+ logs.json 转录，非合规级审计链。

## 5. HITL 与风控（★重点：三态策略引擎 + 确认总线）

### 5.1 决策模型：ALLOW / DENY / ASK_USER 三态（【核心】）

`packages/core/src/policy/types.ts#PolicyDecision`。默认决策 ASK_USER；**非交互模式（headless）下 ASK_USER 视为不可用**：`scheduler/policy.ts#checkPolicy` 在 `!config.isInteractive()` 时直接抛错（而非静默放行）；`PolicyEngineConfig.nonInteractive` 可把 ASK_USER 折叠为 DENY；`policies/non-interactive.toml` 还显式 deny 了 `ask_user` 工具。

### 5.2 PolicyEngine：分层优先级 + shell 深度解析（【核心】）

`packages/core/src/policy/policy-engine.ts`（1104 行）+ `toml-loader.ts`：

- **规则**（PolicyRule）：toolName（支持 `*`）/ subagent / mcpName / argsPattern（对工具参数做正则匹配）/ toolAnnotations（如 MCP readOnlyHint）/ decision / priority / modes（只在指定 ApprovalMode 生效）/ allowRedirection / denyMessage（DENY 时回给模型的说明文案）。
- **五层优先级带**（policies/read-only.toml 头注释 + policy/config.ts）：Default(1.x) < Extension(2.x) < Workspace(3.x) < User(4.x) < **Admin(5.x)**——企业管理员策略永远压过用户策略；层内再用小数优先级（如 User 层内：4.95 永久 always-allow > 4.9 MCP excluded > 4.4 --exclude-tools > 4.3 --allowed-tools > 4.2 MCP trust > 4.1 MCP allowed）。
- **shell 命令深度解析**（check 内）：整条命令先拆子命令（`;`/`&&`/管道），逐个递归 `check`；`bash -c` 等 wrapper 剥壳后再查（stripShellWrapper）；**任何子命令 DENY → 整体 DENY；子命令 ASK → 整体降级 ASK；重定向（>、>>）把 ALLOW 降级为 ASK 且永不升级**；解析失败回落 defaultDecision（不臆测放行）。
- 内置 TOML 策略集（`policy/policies/`）：read-only（读类工具 priority 50 allow）、write（写类 priority 10 ASK_USER）、auto-edit、plan（Plan 模式拦截）、yolo（priority 998 allow-all）、non-interactive、sandbox-default、conseca、agents。
- ApprovalMode 宽松序：PLAN < DEFAULT < AUTO_EDIT < YOLO（`MODES_BY_PERMISSIVENESS`）。

### 5.3 审批交互：确认总线 + 七态 outcome（【核心】）

- **confirmation-bus**（`packages/core/src/confirmation-bus/`）：进程内消息总线，`TOOL_CONFIRMATION_REQUEST` / `TOOL_CONFIRMATION_RESPONSE` 用 **correlationId 配对**；请求携带 `SerializableConfirmationDetails` 富详情联合类型：exec（命令/rootCommands/untrustedFlags）、edit（fileDiff/diffStat/originalContent/newContent）、mcp（serverName/toolName/args/参数 schema）、sandbox_expansion（沙箱权限扩展申请）、info、exit_plan_mode、ask_user。审批 UI 与核心解耦——任何订阅者都能实现审批面。
- 用户可选项 `tools.ts#ToolConfirmationOutcome`：**ProceedOnce / ProceedAlways（本次会话）/ ProceedAlwaysAndSave（持久化）/ ProceedAlwaysServer（放行整个 MCP server）/ ProceedAlwaysTool / ModifyWithEditor（人工改工具参数后执行）/ Cancel**。ModifyWithEditor 是人工纠偏工具入参的通道。
- 挂起实现：`scheduler/confirmation.ts` 监听总线；工具调用状态置 `AwaitingApproval`；`scheduler.ts` 主循环把 awaiting_approval / executing 视为「等待外部事件」。

### 5.4 Always Allow 的持久化与收窄（【核心】）

`scheduler/policy.ts#updatePolicy` → 发 `UPDATE_POLICY` 消息 → `policy/config.ts#createPolicyUpdater`：

- 会话级 ProceedAlways：内存 addRule（tier + 950/1000 的 fraction 优先级，`source: 'Dynamic (Confirmed)'`）。
- ProceedAlwaysAndSave：写 TOML 策略文件（workspace 可信且开了 workspace policies → 工作区，否则 user 级 `storage.getAutoSavedPolicyPath()`）；持久化走串行队列防并发丢更新；带 ReDoS 安全检查（isSafeRegExp）。
- **敏感工具强制收窄**：`TOOLS_REQUIRING_NARROWING`（shell 等）的 always-allow 必须带 commandPrefix（root command 列表）或 argsPattern（如具体文件路径 `buildFilePathArgsPattern`），否则跳过——防「总是允许整个 shell 工具」。
- Always Allow 只对当前模式及更宽松模式生效（`MODES_BY_PERMISSIVENESS.slice(modeIndex)`）。
- settings.json 侧（`policy/types.ts#PolicySettings`）：`mcp.excluded / mcp.allowed / mcp.autoAllowInHeadless`、`tools.core / tools.exclude / tools.allowed / tools.confirmationRequired`、`mcpServers.<name>.trust`、`policyPaths / adminPolicyPaths / workspacePoliciesDir / disableAlwaysAllow`（后者可禁掉所有 always-allow——合规场景开关）。

### 5.5 外部程序化接管（【核心】a2a-server）

`packages/a2a-server/src/agent/task.ts` 把确认总线桥接成 A2A 消息：核心发 `tool-call-confirmation` 事件 → 外部 A2A 客户端回 `ToolConfirmationResponse {outcome, callId}`（types.ts）→ `_handleToolConfirmationPart` 翻译回总线响应（proceed_once/cancel/proceed_always/proceed_always_server）。**审批决策可完全由远端程序做出**，这是本项目「审批外部化」的直接先例；CLI TUI 只是总线的另一个订阅者。

### 5.6 其他风控面

- OS 沙箱：`sandbox/macos/seatbeltArgsBuilder.ts`（Seatbelt profile）、`sandbox/linux/bwrapArgsBuilder.ts`（bubblewrap）、windows；沙箱内命令需要额外权限时走 `sandbox_expansion` 确认类型（申请 `additional_permissions`）。
- safety checker 体系：`safety/`（registry + checker-runner + 外部进程 checker），PolicyRule 之外可挂 SafetyCheckerRule 对工具调用/钩子执行做附加校验（`policy/types.ts#SafetyCheckerConfig` 支持 external 程序）。
- 受信目录：`checkPathTrust`（a2a-server 引 core 导出）、trusted folder 决定 workspace 级策略是否启用。

## 6. 工具边界（★shell 封装 / 截断 / MCP）

- **shell 工具**（`packages/core/src/tools/shell.ts`）：**非活动超时**（inactivity timeout，`getShellToolInactivityTimeout`，任一输出事件重置计时——比墙钟超时更适合长编译）；AbortController 取消并杀进程组；退出码白名单 allowedExitCodes；stderr 超 `MAX_STDERR_BYTES` 打 `...[truncated]`（utils/shell-utils.ts）。后台 shell 工具单独一组（shellBackgroundTools.ts）。
- **工具输出截断 + 落盘指针**：`config.ts:478` `DEFAULT_TRUNCATE_TOOL_OUTPUT_THRESHOLD = 40_000` 字符；超限内容写到 `<projectTempDir>/tool_outputs/[session-<id>/]<tool>_<id>.txt`（`utils/fileUtils.ts#saveTruncatedToolOutput`），上下文里只留 `formatTruncatedToolOutput` 生成的截断占位 + 文件路径——模型可再用 read_file 取回。
- **文件读写范围**：edit/write 确认详情带全量 diff；path-validation（config/path-validation.test.ts）+ allowed-path checker（policy 内置 `InProcessCheckerType.ALLOWED_PATH`）校验参数路径在允许集合内；storage.ts 有 realpath 越界检查（custom plans 目录解析后必须仍在 project root 内）。
- **MCP 集成**（`tools/mcp-client-manager.ts` + `mcp-tool.ts`）：admin allowlist/excludelist 先拦（isBlockedBySettings）；**多源配置合并的安全语义：includeTools 取交集（最严者胜）、excludeTools 取并集（任一方封即封）**（mergeMcpConfigs，注释明说设计意图）；客户端 key = sha256(name+config+extensionId) 支持同名多配置；MCP 工具以 `DiscoveredMCPTool`（带 serverName + toolAnnotations）注册，策略可用 mcpName 或 FQN `mcp_{server}_{tool}` 精确匹配；信任粒度：server trust=true（4.2 优先级）→ 该 server 工具 allow。mcp-compliance-transport.ts 提供合规传输封装。

## 7. 部署与产品化（★多包 + 分层配置）

- 包拓扑：`core`（引擎，被所有端复用）/ `cli`（TUI + ACP 客户端 acpSession.ts）/ `a2a-server`（HTTP 服务：AgentCard 声明 streaming:true、bearer/basic 双 auth、InMemory 或 GCS TaskStore、多 workspace）/ `sdk` / `vscode-ide-companion`。**服务化 = a2a-server**，认证、任务持久化、确认回流都已就位，但它是 A2A 协议面而非通用 REST 面。
- **三级设置**（`config/storage.ts`）：system（/etc/gemini-cli/settings.json，可用 `GEMINI_CLI_SYSTEM_SETTINGS_PATH` 覆盖）> user（~/.gemini）> workspace（.gemini）；policy 同构分层（`getSystemPoliciesDir` 等 + adminPolicyPaths/policyPaths/workspacePoliciesDir）。企业管控点 = system settings + admin policies + `disableAlwaysAllow`。
- 沙箱与 seatbelt 下存储降级（home 只读时写 ~/.cache）；遥测 clearlet 可关。❌ 无多租户概念（单用户本机工具定位）；无配额/成本核算模块（billing 目录是 Google 内部计费事件）。

## 8. 对本项目的适用性（Java / 独立部署+API / 图编排 / 财务合规）

**可借鉴（具体到文件）**：

1. **策略即数据的三态引擎**（`policy/policy-engine.ts` + `policies/*.toml`）：ALLOW/DENY/ASK_USER + 五层优先级带（Admin 永远最高）+ TOML 规则文件 + denyMessage 回喂模型。财务合规的「操作分级 + 集中策略下发」可直接映射：管理员策略层放硬合规规则（DENY 大额转账类），用户层只允许放宽到 ASK。Java 侧可用同样的小数分层优先级或显式 PolicySource 枚举排序实现。
2. **确认总线的 correlationId 配对**（`confirmation-bus/types.ts`）：把审批从工具执行路径中解耦成 request/response 消息对，TUI、A2A 远端、未来的审批微服务都是总线的对称订阅者——比在执行线程里弹 UI 的写法可测试性和可替换性都好。a2a-server 的桥接（`a2a-server/src/agent/task.ts`）证明了「远端程序代答审批」可行。
3. **压缩 prompt 工程**（`prompts/snippets.ts#getCompressionPrompt`）：固定 7 节 XML 快照 + 防注入指令 + 已批准计划保留段；配套两段式自校验与防膨胀检查（`chatCompressionService.ts`）——长会话财务调查任务的记忆蒸馏模板可直接改写复用。
4. **always-allow 必须收窄到 pattern**（`policy/config.ts` TOOLS_REQUIRING_NARROWING）+ shell 子命令递归检查 + 重定向强制降级（`policy-engine.ts#check`）：审批通过后的权限固化不放大到整类操作，这是硬合规的底线设计。
5. **工具输出落盘指针**（`utils/fileUtils.ts#saveTruncatedToolOutput`，40K 阈值）：大结果集（报表/流水）不进上下文、留文件指针按需取回。

**不可迁移**：TypeScript/ink 技术栈；Gemini 模型深度绑定（压缩摘要也走 Gemini 系模型路由 modelStringToModelConfigAlias）；logs.json 全量重写式持久化不适合服务端并发（opencode 的 SQLite 是更好参照）。

**避坑**：context 线性历史（ChatCompressionService）与 context/graph 节点图两代并存，过渡态复杂度自吃；压缩两段 LLM 调用成本翻倍（可配置只做截断降级）；非交互模式 ASK_USER 的处理要在架构期定死（抛错 vs 折叠 DENY），gemini-cli 两处语义不一致是前车之鉴。
