# claude-code-sourcemap 解剖档案（C 组：横切工程）

> 基线：~/develop/opensource/claude-code-sourcemap @ a8a678c (2026-03-31)；canonical ChinaSiro/claude-code-sourcemap（非官方）。
> **证据等级特别声明**：全部结论为**【还原源码】**——由 npm 包 `@anthropic-ai/claude-code` v2.1.88 的 `cli.js.map#sourcesContent` 还原（仓库 README：4756 文件，含 1884 个 .ts/.tsx），符号名/结构可能失真，且不代表 Anthropic 内部仓库结构。**Anthropic 专有代码，仅供模式参考，不得逐字复用。**
> **交叉引用**：`research/agent-framework/profiles/claude-agent-sdk-python.md`（SDK 0.2.152 捆绑 CLI **2.1.269**）。本档案所据 CLI **2.1.88**（更旧），两侧互证时已注明：SDK 的 can_use_tool/PermissionResult/PermissionUpdate/SessionStore 类型与本文 CLI 侧实现一一对应；SDK 档案中「执行在 CLI【文档】」的各条（权限求值次序、压缩、持久化格式）在此得到【还原源码】级印证或修正。2.1.88 已含 SDK 未提及的实验内部模式 `'bubble'`（swarm worker 权限上抛）与 coordinator 模式。

## 1. 产品定位与形态（从简）

Claude Code CLI（终端交互式编码 agent）的内部实现还原：Ink（React for terminal）渲染 + 主查询循环 + 30+ 内置工具 + MCP 接入 + 权限/审批子系统 + JSONL 会话持久化。目录骨架（`restored-src/src/`）：`tools/`（每工具一目录：AgentTool、BashTool、FileEdit/Read/Write、SkillTool、MCPTool…）、`services/`（compact、mcp、analytics…）、`utils/permissions/`（权限引擎）、`components/permissions/`（审批 UI）、`hooks/toolPermission/handlers/`（审批分发）、`query.ts`/`QueryEngine.ts`（主循环）、`coordinator/`+`buddy/`+`swarm`（实验多 agent 形态）。另含大量 ant（Anthropic 内部）feature flag 死代码（`feature('TRANSCRIPT_CLASSIFIER')` 等，`bun:bundle` DCE）。

## 2. Agent 执行架构（从简）

主循环 `query.ts` / `QueryEngine.ts`：用户消息 → LLM 流式响应（AssistantMessage）→ 对每个 tool_use 走 `services/tools/toolExecution.ts#runToolUse`：zod `inputSchema.parse`（失败即 `<tool_use_error>` 回给模型）→ `tool.validateInput` → 投机启动 bash 分类器 → **PreToolUse hooks**（可改输入/给权限决策/叫停）→ `canUseTool`（权限管线，§4）→ deny 则 tool_result(is_error)，allow 则 `tool.call()`（流式 progress）→ **PostToolUse / PostToolUseFailure hooks** → tool_result 消息入链。子 agent 是递归 query（§7）。无图编排原语。

## 3. 技术底座（从简）

TypeScript + Bun 构建（`feature()` 编译期 DCE，多 ant-only 分支）+ React/Ink 终端 UI + zod schema + @anthropic-ai/sdk；分析事件统一 `tengu_*` 前缀（statsig/OTel）；权限/压缩等横切全在 `utils/`、`services/` 平铺目录，UI 与引擎通过 `ToolUseContext`（含 getAppState/setAppState/abortController/readFileState 等回调面）解耦——SDK 宿主与终端 UI 消费同一引擎。

## 4. 权限规则引擎（★★★ 与 SDK 互证的核心）

### 4.1 类型系统（`types/permissions.ts`，441 行）

- `PermissionBehavior = 'allow' | 'deny' | 'ask'`，另有工具自评用的 `'passthrough'`（交给通用管线）。
- `PermissionRule = { source, ruleBehavior, ruleValue: { toolName, ruleContent? } }`；**八种来源**：userSettings / projectSettings / localSettings / flagSettings / **policySettings** / cliArg / command / session（policySettings 为企业托管策略位）。
- `PermissionUpdate` 六操作（addRules / replaceRules / removeRules / setMode / addDirectories / removeDirectories）× 五落盘目的地（userSettings/projectSettings/localSettings/session/cliArg）——与 SDK `types.py#PermissionUpdate` 完全同构（SDK 侧另有运行时 `PermissionUpdateDestination` 相同枚举）。
- 模式：外部五值 `acceptEdits / bypassPermissions / default / dontAsk / plan` + 内部 `auto`（feature('TRANSCRIPT_CLASSIFIER') 门控）+ `bubble`；SDK 档案记录的六模式（含 auto）在 2.1.88 已有雏形。
- **可解释性内建**：每个决策带 `PermissionDecisionReason`（type: rule(带规则)/mode/subcommandResults/permissionPromptTool/hook/classifier(带理由)/safetyCheck/asyncAgent/sandboxOverride/workingDir/other）——审批为什么发生可被 UI（`PermissionDecisionDebugInfo.tsx`）与 OTel 直接消费。

### 4.2 规则文法（`utils/permissions/permissionRuleParser.ts`）

`ToolName` 或 `ToolName(content)`；content 中 `\(` `\)` `\\` 转义；`Bash()`/`Bash(*)` 归一为整工具规则；**遗留工具名别名表**（Task→Agent、KillShell→TaskStop 等）保证旧规则/旧 transcript 兼容。Bash 前缀规则形如 `Bash(npm install:*)`（`:*` 前缀语义在 `tools/BashTool/bashPermissions.ts` 的匹配里实现）。

### 4.3 求值管线（`utils/permissions/permissions.ts#hasPermissionsToUseTool` → `hasPermissionsToUseToolInner`，1486 行）

内层**严格有序**（代码注释带步骤号）：
1a 整工具 deny 规则 → deny；1b 整工具 ask 规则 → ask（**例外**：Bash 且沙箱开启且 `autoAllowBashIfSandboxed` 且命令可沙箱 → 落到工具自评放行）；1c `tool.checkPermissions(parsedInput, context)` 工具自评（Bash 的实现在 §4.4）；1d 工具自评 deny → deny；1e `requiresUserInteraction()` 的工具 ask 直通（bypass 也不免）；**1f 内容级 ask 规则 bypass 免疫**（用户显式配 `Bash(npm publish:*)` ask 时连 bypassPermissions 也要问）；**1g safetyCheck bypass 免疫**（.git/.claude/.vscode/shell 配置等敏感路径，`checkPathSafetyForAutoEdit`）；2a `bypassPermissions`（或 plan 模式但会话始于 bypass）→ allow；2b 整工具 allow 规则 → allow；3 passthrough → ask。

外层包装再按模式二次加工：`dontAsk` 把 ask 硬转 deny（收尾处理防早退绕过）；`auto` 模式依次：非可分类 safetyCheck 保持 ask → acceptEdits 快路径重放（对非 Agent/REPL 工具以 acceptEdits 模式重跑 checkPermissions，省分类器调用）→ 安全工具白名单 → **yoloClassifier LLM 分类器**（`classifyYoloAction`，带 allow/deny/ask 描述集，可给出理由）→ 连续/累计拒绝计数（`denialTracking.ts`）超限回落人工问询或 headless 直接 AbortError；`shouldAvoidPermissionPrompts`（后台/headless）时先跑 PermissionRequest hooks，无人接手则自动 deny。

### 4.4 Bash 匹配（`tools/BashTool/bashPermissions.ts`，2621 行）

tree-sitter 解析 AST（`utils/bash/ast`）而非纯正则：命令前缀提取（跳过安全 env 赋值前缀、剥安全包装器）、复合命令拆分为子命令逐一匹配（上限 `MAX_SUBCOMMANDS_FOR_SECURITY_CHECK=50`，防指数拆分 DoS）、`BINARY_HIJACK_VARS`（LD_/DYLD_/PATH）拦截、输出重定向提取、sed 专门校验；`checkCommandAndSuggestRules` 在 ask 时给出「精确命令/前缀」两种建议规则；**投机分类器**（`startSpeculativeClassifierCheck`）在权限对话弹出前并行跑 LLM 刷绿允许。`shadowedRuleDetection.ts` 复刻了 SDK 侧 CanUseToolShadowedWarning 的同类检测。

## 5. 工具审批流（★★★）

- **ask 的去处由三 handler 分流**（`hooks/toolPermission/handlers/`）：interactiveHandler（主线程终端 UI）、coordinatorHandler/swarmWorkerHandler（实验多 agent 把权限上抛主协调者）。
- **interactiveHandler**（536 行）：向 ToolUseConfirm 队列压入待审批项（onAllow/onReject/onAbort/recheckPermission/onUserInteraction 回调面，各工具的 `*PermissionRequest` 组件渲染专属卡片），**resolve-once + claim() 原子守卫**防多次解决；四路竞速——本地对话框、**Bridge（claude.ai 远程审批，任意工具通用 modal，可回传 updatedInput）**、**Channel 通知（手机侧 `yes abc123` 回复）**、bash 允许分类器自动放行（用户开始交互后 200ms 宽限即取消）；审批期间模式切换等触发 `recheckPermission()` 重评。
- **放行的副作用**：onAllow 可携带 `updatedInput`（改输入）与 `PermissionUpdate[]`（「总是允许」落盘到 session 或 settings），经 `applyPermissionRulesToPermissionContext` 热生效 + `syncPermissionRulesFromDisk` 保持多源同步——**运行时策略可变**。
- **SDK/headless 通道**（与 SDK 档案互证）：`cli/structuredIO.ts` 把 ask 决策经 stdio 的 **can_use_tool control_request** 反调 SDK 宿主（`permissionPromptToolResultToPermissionDecision` 转换；本地先解决时发 control_cancel_request 撤销）；沙箱网络请求也伪装成工具 `SandboxNetworkAccess` 走同一协议。SDK 档案 §11 的 can_use_tool 回调签名/PermissionResultAllow(updated_input/updated_permissions) 即此协议对端。
- **审计面**：OTel `tool_decision` 事件带 source 词表（config / hook / user_permanent / user_temporary / user_reject，`toolExecution.ts#decisionReasonToOTelSource`）；PreToolUse hook 决策产出 attachment 消息入 transcript。

## 6. 上下文自动压缩（★★）

- **阈值数学**（`services/compact/autoCompact.ts`）：`effectiveWindow = contextWindow − min(maxOutputTokens, 20k)`（可被 `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 压低）；`autoCompactThreshold = effectiveWindow − 13k`；warning/error 线 = threshold − 20k；人工兜底阻塞线 = effectiveWindow − 3k；`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` 测试覆写。开关链：`DISABLE_COMPACT` / `DISABLE_AUTO_COMPACT` / 用户设置 `autoCompactEnabled`。
- **熔断**：连续 3 次压缩失败即停（`MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES=3`，注释：曾致全局每天 25 万次无效 API 调用）；递归防护（compact/session_memory 自身的 fork 不再触发）。
- **压缩流程**（`services/compact/compact.ts#compactConversation`，1705 行）：**PreCompact hooks**（trigger auto/manual，可注入 customInstructions 合并进 prompt）→ 结构化 8 段摘要 prompt（`prompt.ts#BASE_COMPACT_PROMPT`，要求 `<analysis>` 思考标签 + Analysis/CLI Commands/Files/TODOs/Key Learnings 等 8 节）→ 摘要请求本身 prompt_too_long 时**截头重试**（`truncateHeadForPTLRetry` 按最老 API 轮组丢弃）→ 成功后：readFileState 清空并按时间戳**恢复最近读过的文件为 attachment**（token 预算内，`createPostCompactFileAttachments`）、plan 文件 attachment、invoked_skills attachment、plan 模式指令续载、deferred 工具/agent 列表/MCP 指令的 delta 重放、**SessionStart hooks（source=compact）**、写 **compact boundary 消息**（含 preCompactTokenCount、preCompactDiscoveredTools 元数据）、摘要作为 user 消息（isCompactSummary + isVisibleInTranscriptOnly）。刻意**不**重注入 skill_listing（约 4k token 纯 cache_creation 浪费，注释明言）。
- **microcompact**（`services/compact/microCompact.ts`）：轻量档——只清旧工具结果（Read/Bash/Grep/Glob/WebSearch/WebFetch/Edit/Write），占位 `[Old tool result content cleared]`，按 token + 时间双触发（`timeBasedMCConfig`）；ant 内部另有基于 `cache_edits` 的原位缓存清除变体。
- 实验分支：session-memory 压缩优先尝试、reactive-only（等 API 413 再压）、context-collapse（90% commit/95% blocking 的滚动折叠，与 autocompact 互斥门控）。
- SDK 侧对应：`get_context_usage()` / PreCompact hook / `ContextUsageResponse.isAutoCompactEnabled` 字段（SDK 档案 §2），本侧为其后端实现【还原源码】。

## 7. JSONL 会话持久化与 resume（★★）

- **格式与路径**（`utils/sessionStorage.ts`，5105 行）：`~/.claude/projects/<sanitized-cwd>/<sessionId>.jsonl`（与 SDK `sessions.py` 的路径复刻互证）；子 agent 侧链在 `<session>/subagents/agent-{id}.jsonl` + `agent-{id}.meta.json` sidecar（parent 归属），workflow 组可再套 `subagents/workflows/<runId>/`；读取上限 `MAX_TRANSCRIPT_READ_BYTES = 50MB`，墓碑重写上限 50MB。
- **Entry 联合**：user / assistant / attachment / system（`isTranscriptMessage` 是链成员的唯一真相源）+ 队列操作、file-history 快照、attribution 快照、content-replacement 记录、context-collapse commit 等旁挂类型；**parentUuid 链**由 `isChainParticipant`（排除 progress）维护——progress 是纯 UI 态，历史混入 progress 的旧文件在加载时做链桥接（#14373/#23537 教训注释）。
- **写入**：`recordTranscript` 前缀跟踪（已写消息只更新 startingParentUuid，压缩后 messagesToKeep 出现在新摘要之后也能正确续链）→ `insertMessageChain` 追加；删除走墓碑 `removeTranscriptMessage`；`sessionStoragePortable.ts` 提供 lite head/tail 读与 `SKIP_PRECOMPACT_THRESHOLD`（跳过压缩前消息省内存——resume 只需恢复到最近边界）。
- **resume 重建**（`utils/sessionRestore.ts`，551 行）：`processResumedConversation`——session id 与 sessionProjectDir **原子配对**切换（`switchSession`）、`adoptResumedSessionFile` 复用原文件继续追加、恢复 cost 状态/asciicast 改名/会话元数据；`restoreSessionStateFromLog` 重建四类运行时状态：fileHistory（文件编辑回滚锚点）、attribution、contextCollapse 提交日志、**TodoWrite 待办直接从 transcript 反扫最后一个 tool_use 块恢复**（`extractTodosFromTranscript`）；`restoreAgentFromSession` 恢复 agent 定义与 model override（用户显式 --agent 优先）；`restoreWorktreeForResume` 回到退出时所在 worktree。`--fork-session`：保留新 id，靠 recordTranscript 把源消息拷入新 JSONL，并**重新播种 contentReplacement 记录**（否则工具结果被误判 FROZEN 全量重发，缓存击穿——注释详述）。另有跨项目 resume（`crossProjectResume.ts`）与 agentic 会话搜索。
- 与 SDK 档案 §10 对齐：SDK 的 fork/resume/SessionStore 镜像正是消费这套磁盘格式；SDK 侧 `resume_session_at`/`resume_drops_turn` 的截断点语义在此对应 parentUuid 链上任意节点截断。

## 8. subagent / hooks / skills（★★）

- **AgentTool（Task 工具）派生子 agent**（`tools/AgentTool/runAgent.ts#runAgent`，973 行 generator）：新 agentId（transcript 路由到 subagents/ 侧链）→ 上下文 fork（`forkContextMessages` + `filterIncompleteToolCalls` 清掉不完整 tool_use 防 API 400；可选 `useExactTools` 产出字节级相同前缀吃 prompt cache）→ 工具池按 agent 定义裁剪，`allowedTools` 若给出则**整体替换**会话 allow 规则（父会话的临时授权不泄漏给子 agent）；**权限模式继承规则**：agent 定义可带 permissionMode，但父在 bypassPermissions/acceptEdits/auto 时父优先；async agent 置 `shouldAvoidPermissionPrompts`（§4.3 的自动 deny 路径）+ `setAppStateForTasks` 共享根 store（嵌套 async→async 时 setAppState 是 no-op 的坑有专门通道）；读文件状态缓存按 agent 隔离（cloneFileStateCache）；**token 优化固化**：Explore/Plan 只读 agent 剔除 CLAUDE.md 与 gitStatus（注释给出每周数十 G token 的节省数据）；SubagentStart/Stop hooks、Perfetto 层级注册、`killShellTasksForAgent` 退出清理、resumeAgent/forkSubagent 复用通道。progress 经 ProgressMessage 流回父 UI，产出以 tool_result 回父链。
- **hooks 事件点与 matcher**（`utils/hooks.ts`，5022 行）：**25+ 事件**——PreToolUse/PostToolUse/PostToolUseFailure/**PermissionRequest**/**PermissionDenied**/Stop/StopFailure/SessionStart/SessionEnd/Setup/PreCompact/PostCompact/Notification/SubagentStart/SubagentStop/UserPromptSubmit/TeammateIdle/TaskCreated/TaskCompleted/Elicitation/ElicitationResult/ConfigChange/CwdChanged/FileChanged/InstructionsLoaded/WorktreeCreate/WorktreeRemove/StatusLine（比 SDK 档案记录的 10 种多一倍以上，2.1.88 已扩容；SDK 侧 HookMatcher 对应此处 `getMatchingHooks` 的 matcher 语义）。**matcher 文法**（`matchesPattern`）：纯字母数字下划线竖线 = 精确或管道多选（带遗留名归一）；否则按 **正则** 解释（非法正则记日志不炸）；matchQuery 按事件取 tool_name/source/trigger/agent_type/file basename 等不同字段。hooks 可来自 plugin（pluginRoot/pluginId）与 skill（skillRoot）自带 hooks 和 SKILL.md frontmatter 注册（`registerFrontmatterHooks`）；PreToolUse 可回 permissionDecision（allow/deny/ask）+ updatedInput + stop——是外部策略/审计的标准接入点（企业可用 policySettings 强制）。
- **skills 渐进披露**（`utils/attachments.ts#getSkillListingAttachments` + `tools/SkillTool/SkillTool.ts`）：一级——`skill_listing` attachment 只注入 name+description，按上下文窗口预算格式化（`formatCommandsWithinBudget`），`sentSkillNames` 每 agent 增量跟踪（首包 initial、后续 dynamic delta，resume 时抑制防重发）；二级——SkillTool 调用时才读完整 SKILL.md（parseFrontmatter 取 name/description/allowed-tools/model/context），剥 frontmatter 后作为 meta user 消息直接注入（`$ARGUMENTS` 插值）；`context: fork` 的 skill 走 forked subagent 执行；压缩后 invoked_skills attachment 保留已用技能内容（skill_listing 不重注入）；实验 skill search：turn-0 阻塞式 discovery + 写操作 pivot 预取 + 远端 canonical skill（`_canonical_<slug>` 从 AKI/GCS 缓存加载）。SDK 侧「skills 是上下文过滤器而非沙箱」的 docstring 在此印证：未列出的 skill 对模型隐藏但文件仍可被 Read/Bash 读到。

## 9. 对本项目的适用性（Java + 独立部署 + 图编排 + 财务合规）

**可借鉴模式**：
1. **权限求值的有序管线 + bypass 免疫位**（§4.3）：deny→ask→工具自评→safety 免疫→mode→allow 的固定次序，把「用户显式 ask 规则」「敏感对象 safetyCheck」放在 bypass 之前——财务场景的硬合规位（超限额交易、敏感科目）应做成同样的 bypass 免疫判定，且 fail-safe 默认（无策略引擎 = ask）。
2. **DecisionReason 全链可解释**：每个 allow/deny 附结构化理由（规则/模式/分类器/hook/子命令）——审计报表直接消费，Java 侧用 sealed interface + record 建模即可。
3. **审批竞速 + resolve-once 守卫**（§5）：本地 UI / 远程（手机、Web） / 自动分类器四路竞速、claim() 原子性、审批中重评（recheckPermission）、「总是允许」即时落盘 PermissionUpdate——适合多渠道审批（柜面/移动端/自动风控）的 Java 实现；auto 模式的「便宜快路径（规则重放/白名单）先行、LLM 分类器兜底 + 拒绝计数熔断回落人工」是成本与安全的均衡范本。
4. **压缩状态恢复清单**（§6）：阈值数学（窗口 − 输出预留 − 缓冲）、熔断、压缩后恢复文件态/计划/待办/delta 重放、microcompact 分层（工具结果级清理 vs 全量摘要）——长会话财务 agent 的上下文管理可直接套两级结构。
5. **JSONL append-only + parentUuid 链 + 旁挂快照**（§7）：会话真相源一行一 JSON（Java 用 Jackson streaming 追加），业务状态（对账游标、凭证快照）作旁挂 entry；resume 只重放链上节点 + 旁挂快照恢复运行态；fork 通过复制重写而非原地分叉。
6. **hooks 作为治理扩展点**：PermissionRequest/PermissionDenied/PreCompact 等事件 + 「精确/正则」matcher 文法 + plugin/policy 来源分级——Java 侧可映射为 Spring 事件 + SpEL/正则 matcher 的合规插件位。

**不可迁移点**：Bun `feature()` 编译期 DCE 与 ant 内部 flag 体系；Ink/React 终端 UI；Anthropic 专有 prompt 文案与 tengu 分析协议（版权）；bash AST 解析绑定 tree-sitter 生态（Java 需换 shell 解析库或降级为前缀匹配）。

**避坑**：
- 还原代码注释自曝的大量事故（progress 入链导致 resume 分叉 #14373、压缩后 contentReplacement 未播种致缓存击穿、复合命令指数拆分 DoS、1 秒高频 progress 写盘）说明：**transcript 链成员要单一真相源 + 写前过滤**；新增旁挂 entry 必须同步考虑 fork/resume 的重播种。
- 版本漂移实证：2.1.88 与 SDK 捆绑的 2.1.269 之间 hooks 事件从 ~10 扩到 25+、auto 模式从 flag 到正式——**以 CLI 内部格式为集成契约的方案（如 SDK 直读 JSONL）必须锁版本**，自研系统对外契约应显式版本化。
- 权限规则文法（转义括号、遗留别名）是历史包袱，Java 新系统应一开始用结构化规则对象（JSON）而非字符串文法，仅在需要人类可读写配置时做一层 DSL。
