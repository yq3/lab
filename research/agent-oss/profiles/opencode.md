# opencode 解剖档案（C 组：横切工程）

> 基线：~/develop/opensource/opencode @ 95daf90670 (2026-09-11)；canonical anomalyco/opencode（2026 年从 sst/opencode 迁移 org，引用以 anomalyco 为准）。TypeScript 超大多包单仓（packages/ 30+：opencode[主引擎] / core / server / protocol / schema / tui / web / desktop / sdk / sdk-next / slack / enterprise / control-plane / containers …），**Effect-TS 全家桶**（Layer DI、Schema、HttpApi），Bun+Node 双运行时。C 组焦点：server 的 API 形态、审批外化、会话持久化。维度 1-3 从简。

## 1. 产品定位与形态（简）

- 开源编码 agent，多端（TUI / Web / desktop / IDE / Slack）；**核心形态是 client/server 分离**：server 是完整引擎，全部能力以 Effect HttpApi 声明式暴露（自动生成 OpenAPI，`/openapi.json`）；TUI 只是一个 client——`packages/opencode/src/cli/tui/worker.ts` 在 worker 进程内运行 server，经 RPC 转发 `fetch()` 走**同一套 HTTP API**（不起 socket 也能跑）。「UI 只是 API 的第一个消费者」是本项目最有价值的架构立场。
- `opencode serve`（`cli/cmd/serve.ts`）一键 headless 服务化：未设 `OPENCODE_SERVER_PASSWORD` 时打明文警告。面向开发者和企业（enterprise / control-plane 包）。

## 2. Agent 执行架构（简）

- 主循环：`packages/opencode/src/session/prompt.ts`（约 1600 行，`loop` 内 `while(true)` + step 计数、abort 处理、重试）；消息/part 流式加工在 `session/processor.ts`（SessionProcessor）。子 agent 走 task 工具 + 预置 agent 画像。
- agent 画像即权限画像：`agent/agent.ts` 内置 build（默认）/ plan（禁编辑）/ general（子任务）/ explore（只读）四类，每个画像是一份 permission ruleset（见维度 5）。
- 会话内插件钩子：`session/prompt.ts` 触发 `tool.execute.before`(:308) / `tool.execute.after`(:390) / `chat.message`(:1000) / `experimental.chat.messages.transform`(:1255)——扩展与审计的切面。

## 3. 技术底座（简）

- TypeScript + Effect（schema-first API / Layer 依赖注入 / 结构化错误）；SQLite（drizzle ORM + 自研 effect-drizzle-sqlite 桥）；shell 解析用 web-tree-sitter（bash + PowerShell WASM 语法树）；SST 基础设施（sst.config.ts）部署云端组件。无 agent 框架依赖，LLM 层自研 provider 抽象。交叉引用：不在 agent-framework 17 框架清单内。

## 4. 状态与持久化（★SQLite 事件溯源 + revert + share）

### 4.1 SQLite 事件溯源存储（【核心】）

`packages/core/src/database/schema.gen.ts`（drizzle 生成）：

- **事件表**：`event(aggregate_id, seq, type, data)` + `event_sequence(aggregate_id → seq 单调序列)` + 唯一索引 `(aggregate_id, seq)`——按聚合根分序列的事件溯源（event sourcing）；只有 durable 子集事件入库（`schema/src/durable-event-manifest.ts`），事件带 `durable: {aggregateID, seq, version}` 元数据（protocol/groups/event.ts）。
- **会话规范化三表**：`session`（含 cost、tokens_input/output/reasoning/cache_* 成本列、`revert`、`permission`、`time_compacting`、parent_id 支持子会话树）→ `message` → `part`（每 part 一行，独立时间戳，天然增量流式写入）。
- **会话附属**：`session_context_epoch(baseline, snapshot, baseline_seq)`（上下文纪元基线）、`session_input(admitted_seq / promoted_seq)`（输入排队与提升）、`todo`（任务板）、`permission`（持久化授权，见维度 5）、`session_share`（分享元数据）。
- 旧 v1 JSON 文件存储（`packages/opencode/src/storage/storage.ts`：`storage/session/message/*/*.json` 每消息一文件）与迁移逻辑并存（migration 用 git rev-list 找 project 根，跨大版本搬迁的真实工程痕迹）。
- **resume = 即续**：会话全量在库，对既有 sessionID 再 `POST /api/session/:id/prompt` 即恢复；`GET /api/session/:id/context`、`/history` 可检视上下文与历史，`POST /api/session/:id/wait` 等待本轮跑完（同步语义的补位）。

### 4.2 revert：会话+文件双状态检查点（【核心】）

`packages/opencode/src/session/revert.ts` + `snapshot/index.ts`：

- **影子 git 仓**做文件快照：gitdir = `Global.Path.data/snapshot/<project>/<hash(worktree)>`，work-tree = 项目目录（`--git-dir ... --work-tree ...` 直调 git）——**不污染用户仓库**的旁路版本控制。
- revert(messageID/partID)：定位消息/part，收集其后所有 `patch` part；首次 revert 先 `snap.track()` 存快照（再次 revert 复用同一快照，`session.revert?.snapshot ?? track()`）；`snap.revert(patches)` 逆序回滚文件；diff 统计回写 session 摘要。unrevert：恢复快照（撤销回滚）。cleanup（=commit）：真正删除被回滚区间的 message/part。
- HTTP 三步：`POST /api/session/:id/revert/stage | /revert/clear | /revert/commit`（protocol/groups/session.ts）——**stage → 人工确认 → commit** 的两阶段模式，忙碌时拒绝（`assertNotBusy`）。

### 4.3 上下文压缩（compaction，【核心】）

`packages/core/src/session/compaction.ts`（新代）+ `packages/opencode/src/session/compaction.ts`（装配）：

- **触发**：上下文 overflow 时自动（`compactAfterOverflow`，比较模型 context limit - 预留输出）；配置 `compaction: {auto, buffer, keep.tokens}`。`POST /api/session/:id/compact` 手动触发。
- **选择算法**（`select`）：从最新往旧按 token 累积到 `keep.tokens` 为止，其前的进 head 被摘要、其后的 recent 原文保留——与 gemini-cli 的「保最近 30%」同思路但按配置 token 数。
- **摘要格式**：固定模板 SUMMARY_TEMPLATE 六节——Objective / Constraints / Completed / Blocked / Next Move / Relevant Files（规则：保留精确文件路径、符号、命令、错误串、URL；不得提及压缩过程）；**增量合并**：已有 `<prior-summary>` 时给 SUMMARY_UPDATE_INSTRUCTIONS（旧摘要丢弃，未带入的信息即丢失；冲突以新会话为准；完成项移入 Completed）。
- 序列化时工具输出超 2000 字符截断；skill 工具输出保护（PRUNE_PROTECTED_TOOLS）；摘要经 LLM 流式生成（tools: [] 纯文本），产出 `Compaction.Started/Ended` 事件（含 summary + recent 全文）落事件流。

### 4.4 share（【核心】）

`packages/opencode/src/share/session.ts` + `share-next.ts`：上传会话到 opncd.ai（或 `enterprise.url` 自托管），本地 `session_share` 表存 id/secret/url；`config.share = "disabled" | "auto"` 可禁/自动分享；unshare 撤销。会话 URL 落在 session.share_url 列。

### 4.5 事件流（【核心】）

- `GET /api/event`（全局 SSE，HttpApiSchema.StreamSse）+ `GET /api/session/:id/event`（会话级 SSE）+ WebSocket 通道（server.ts WebSocketTracker）。
- 事件目录类型化（`schema/src/event-manifest.ts`：session.*/compaction.*/permission.v2.asked|replied/question.*/ide.*/mcp.*/pty.*…），插件可注册自定义事件定义进同一目录（makeEventGroup(definitions)）。

## 5. HITL 与风控（★审批完全外化为 REST API）

### 5.1 权限配置与求值（【核心】）

- **配置格式**（`packages/core/src/v1/config/permission.ts`）：`permission: {"bash": "allow"}` 或 `{"bash": {"git *": "allow", "rm *": "deny"}, "read": {"*.env": "ask"}, "*": "allow"}`——工具名 → (通配 pattern → ask|allow|deny)；`~`/`$HOME` 展开；解析时**保留用户 key 顺序**（propertyOrder: "original"）。
- **求值**（`packages/opencode/src/permission/index.ts#evaluate`）：rulesets 拍平后 `findLast(Wildcard.match(permission, rule.permission) && Wildcard.match(pattern, rule.pattern))`——**双通配匹配（工具名 × 资源 pattern），最后命中者胜**；无命中默认 `{action: "ask"}`。「后写的覆盖先写的」使同一份配置内可先宽后窄精准打洞。
- **分层装配**（`agent/agent.ts:100-215`）：`Permission.merge(defaults, 画像overlay, user配置)`，user 永远最后（最高优先级）。defaults 值得逐条抄：`"*": "allow"` 基线 + `doom_loop: ask`（死循环检测也要人批）+ `external_directory: ask`+白名单 + question/plan_enter 默认 deny + **`read: {"*.env": "ask", "*.env.example": "allow"}`（镜像 Node.gitignore 拦密钥文件）**。画像 overlay：plan agent `edit: {"*": deny, 计划文件: allow}`；explore 子 agent `"*": deny` 只开 grep/glob/list/bash/read/webfetch；general 子 agent 禁 todowrite。运行时还有 session 级 ruleset 覆盖（`session/tools.ts:87` merge(agent.permission, session.permission)）。
- **工具隐藏**（`permission/index.ts#disabled/visibleTools`）：`pattern === "*" && action === "deny"` 的工具直接从发给 LLM 的工具列表里移除——模型根本看不到被禁能力，而不是执行时报错。

### 5.2 ask/reply 执行流（【核心】）

`permission/index.ts`：

- `ask({permission, patterns[], always[], metadata})`：逐 pattern 求值——**deny 立即抛 DeniedError（错误信息里附相关规则 JSON 回喂模型，让它知道为什么被拒）**；全 allow 直接过；否则创建 pending 请求（`PermissionV1.ID.ascending()` 单调 ID）+ **Effect Deferred 挂起当前工具调用** + 发布 `Event.Asked` 进事件流。
- `reply({requestID, reply: once|always|reject, message?})`：
  - reject + message → `CorrectedError(feedback)`——**拒绝原因成为模型可见的纠错反馈**（改写重试的信号）；同时**级联拒绝同 session 其余全部 pending**（避免排队放行下一个危险操作）。
  - once → 单次放行。
  - always → 把 `always[]` patterns 写进会话内存 approved 规则，然后**自动检查同 session 其他 pending：凡新规则下全 allow 的自动放行**（批量解锁）。
  - 实例关闭 finalizer 把所有 pending 置 RejectedError（不留悬挂 Promise）。
- 审批富上下文：metadata 携带命令原文 / edit 的完整 diff / 涉及目录列表（tool/edit.ts、tool/shell.ts 的 ask 调用点）。

### 5.3 审批外化 API（【核心】★本项目最直接参照）

`packages/protocol/src/groups/permission.ts`（Effect HttpApi，自动进 OpenAPI）：

- `POST /api/session/:sessionID/permission`——创建/评估授权请求（action + resources + save + metadata + source）
- `GET /api/session/:sessionID/permission`、`GET .../:requestID`——列/查 pending
- `POST /api/session/:sessionID/permission/:requestID/reply`——回复（reply + message）
- `GET /api/permission/request?location=...`——**跨会话 pending 总表**（审批工作台入口）
- `GET /api/permission/saved`、`DELETE /api/permission/saved/:id`——持久授权 CRUD
- 配套事件 `permission.v2.asked` / `permission.v2.replied` 走 SSE 推送；持久授权落 SQLite `permission` 表（`core/src/permission/saved.ts`，project_id 关联）。

**外部审批服务可「订阅 SSE + 回复 REST」完全接管审批**，agent 进程内 Deferred 挂起等待——审批人与执行机物理分离的完整闭环。注意两代并存：工具执行走 v1（opencode/src/permission，permission+patterns 模型），HTTP 新面是 v2（core/src/permission.ts，action+resources+save+source 模型，含 agent 维度与缺省全拒的 missingAgentPermissions）——迁移过渡态。

### 5.4 bash 权限的 AST 级提取（【核心】）

`packages/opencode/src/tool/shell.ts`：**web-tree-sitter 解析 bash/PowerShell 语法树**后逐 command 节点提取：命令文本作 pattern（`source(node)` 含重定向语句）；文件操作命令（FILES/CMD_FILES 词典）的路径参数解析为绝对路径、cwd 外的触发**单独的 `external_directory` 权限**（按目录 glob ask，含 `$()` 等动态构造检测——动态则不展开只按命令问）；`BashArity`（permission/arity.ts，LLM 生成的 160 条命令前缀元数词典）把命令归约为人类可读前缀（`git checkout main` → `git`，`npm run dev` → `npm run`），always 模式即「`git *` 一律放行」。比正则/前缀字符串匹配 robust（复合命令、引号、子 shell 都在树上）。

## 6. 工具边界（★shell 封装 / 截断 / 外部目录）

- **shell 执行**（tool/shell.ts）：默认 2min 超时（`flags.bashDefaultTimeoutMs ?? 2*60_000`）；输出**流式累积限内存**（keep = maxBytes×2，超限转 writeStream sink 落盘）；返回取尾部 N 行/N 字节（`tail()` 从尾往头拼，UTF-8 多字节边界安全处理）；detached 进程组（POSIX）；PowerShell 用 `-NoLogo -NoProfile -NonInteractive`；`plugin.trigger("shell.env")` 允许插件注入环境变量。
- **通用截断服务**（`tool/truncate.ts`）：MAX_LINES=2000 / MAX_BYTES=50KB（config `tool_output.max_lines/max_bytes` 可调），超限全文写文件、上下文留截断段+路径。
- **文件读写范围**：read/edit/write/apply_patch 以**相对 worktree 路径为 pattern** 请求 `read`/`edit` 权限（edit metadata 带全 diff）；`tool/external-directory.ts` + read 内 `assertExternalDirectoryEffect` 拦 cwd 外访问；BOM/行尾检测处理（edit.ts 的 Bom.split）。
- **MCP**：`mcp/` 目录 + `tool/mcp-websearch.ts`；MCP 工具权限按 server 名匹配；`list_mcp_resources`/`read_mcp_resource` 归并为 `read` 权限语义（permission/index.ts#disabled）。
- 凭据：`credential` 表 + CredentialGroup API（API key 集中管理，而非散落环境变量）。

## 7. 部署与产品化（★server 即产品）

- **API 面**（protocol/groups/*.ts）：session（prompt/compact/wait/revert/context/history/events/interrupt/agent/model 切换）、message、permission、question（ask_user 式问答也是 API）、fs、pty（终端流）、command、skill、credential、integration、reference、project-copy、health、event（SSE）。全部 schema-first 声明，OpenAPI 自动生成。
- **认证**：ServerAuth basic（username 固定 opencode + `OPENCODE_SERVER_PASSWORD`）；`Authorization` 中间件挂在 API 顶层（api.ts `.middleware(Authorization)`）。
- **多项目路由**（`packages/server/src/location.ts`）：每请求按 `x-opencode-directory` header（或 query、缺省 cwd）解析 Location.Ref → 注入该项目的 LocationServices（惰性建实例）——**单 server 进程服务多项目/多目录**，会话/配置/权限按 project 隔离（SQLite project 表 + project_directory）。这是「agent 服务独立部署、按租户路由」的现成模型。
- 进程拓扑：TUI = worker 进程内嵌 server（RPC fetch 同 API）；`opencode serve` = 常驻 headless（端口 4096 优先，0 则随机；mDNS 局域网发布；graceful shutdown 1s + 强杀连接）；web/desktop/slack 都是同一 API 的 client；sdk/sdk-next 供第三方集成。
- sync 包（`opencode/src/sync/`）：事件总线向「单写入者」同步模型演进（schema 类型化 + 向后兼容 Bus）。
- 可观测性：session 表内置 cost/token 核算列；事件全量可订阅即天然审计流。enterprise/control-plane 包面向组织管理（SSO、策略下发方向，本次未深挖）。

## 8. 对本项目的适用性（Java / 独立部署+API / 图编排 / 财务合规）

**可借鉴（具体到文件）**：

1. **审批外化 API 组**（`packages/protocol/src/groups/permission.ts`）：`POST /permission`（建请求）+ `GET /permission/request?location=`（跨会话待审列表）+ `POST /:requestID/reply`（once/always/reject+message）+ SSE `permission.asked/replied` 事件 + saved 表。Java 服务可直接照抄这组端点语义（Spring + SSE + 审批人 Web/工单系统），配 `permission/index.ts` 的 Deferred 挂起模式（Java 对应 CompletableFuture/阻塞队列）：执行线程挂起等外部审批回调，reject 带 feedback 回喂模型、always 写规则并批量解锁、实例关闭时 pending 全部 fail——这些边界语义都替你踩过了。
2. **SQLite 事件溯源做审计**（`core/src/database/schema.gen.ts`：event + event_sequence 按 aggregate 分序列 + 唯一索引）：会话/消息/part 规范化三表 + durable 事件子集，回放=重放聚合序列。财务合规要的「可回放执行轨迹」用这个模式，比 JSONL append 文件可靠（有约束、有事务）。
3. **revert 两阶段 + 影子 git 快照**（`session/revert.ts` + `snapshot/index.ts`）：stage（先快照、可反悔）→ 人工确认 → commit 的 API 三步 + 会话与文件双状态一致回滚。对应财务 agent 的「草稿/冲正」设计。
4. **分层 ruleset + findLast 语义**（`agent/agent.ts` defaults⊕画像⊕用户、`permission/index.ts#evaluate`）：「默认基线（拦 .env 级敏感资源）→ 角色画像（plan/explore 最小权限）→ 用户覆盖」三段装配 + 后写胜出；deny 的工具从 LLM 工具列表隐藏。
5. **location 中间件**（`server/src/location.ts`）：按请求 header 路由到 per-directory 服务实例——单 agent 服务进程多业务线/租户的轻量隔离，Java 里即一个 per-tenant 的 ServiceLocator/Layer 缓存。
6. **TUI 内嵌 server 走同一 API**（`cli/tui/worker.ts`）：消灭「本地直调/远程 HTTP」双路径，测试与部署形态天然一致。

**不可迁移**：Effect-TS 生态（Java 无直接对应；但其 schema-first HttpApi + OpenAPI 自动生成的思路可用 springdoc 等价实现）；Bun 运行时；opncd.ai 分享云。

**避坑**：v1/v2 双代 permission、session、storage 并存，迁移期代码量近翻倍——自研应一步到位定好审批数据模型（action/resources/save/source 四元组 + agent 维度）；30+ 包 monorepo 的组织成本；SSE 与 WebSocket 双通道并存同样是为了兼容过渡。
