# C 组横向：编码 agent（横切工程专题）

> 输入：`profiles/` 下 cline、codex、gemini-cli、opencode、OpenHands、claude-code-sourcemap 六份档案（基线与证据等级见各档案头）。C 组不看产品功能看 harness 工程：六项目全是自研 loop（自研主循环）、无图编排——与 agent-framework 轮「编码 agent 不用框架」结论互证；但**权限审批、上下文压缩、会话恢复、执行隔离四个横切面的工程成熟度是 18 仓之最**，是本项目硬约束③（硬性审批/审计/合规）的主要模式来源。OpenHands 结论锚点为 git 历史 e8249f00a（经典 Python 架构）。

## 1. 组内形态图谱（含基线演进警告）

| 项目 | 交互形态 | 语言 | 会话存储 | 审批模型一句话 |
|---|---|---|---|---|
| cline | 三形态同核：VS Code 插件 + CLI(TUI) + SDK + hub daemon（WebSocket 多客户端共享会话） | TS（Bun monorepo） | 会话 JSON 文件（atomic tmp+rename）；任务/cron 另用 SQLite 分库 | 三段管线 beforeTool hook → ToolPolicy → 审批回调，回调未配置即拒绝（fail-closed） |
| codex | 单二进制多入口：TUI / `exec` headless(JSONL 流) / `app-server`(JSON-RPC) | Rust（~110 crate）+ TS 薄启动器 | rollout JSONL（append-only）+ SQLite 线程索引/日志 | 双轴（审批策略 × 沙箱模式）+ Starlark 规则引擎执行前预判三态 + Guardian LLM 风险评分层 |
| gemini-cli | ink/React TUI + a2a-server（A2A 协议 HTTP 服务化出口） | TS 多包单仓 | logs.json 全量读改写 + `/chat` tag 全量 JSON 快照 | 三态策略引擎 ALLOW/DENY/ASK_USER，TOML 五层优先级带 + 确认总线 correlationId 配对 |
| opencode | **server 即产品**：全部能力 REST API + SSE，TUI/Web/桌面/Slack 只是 client | TS + Effect-TS | SQLite 事件溯源（event 表 + aggregate_id/seq 唯一索引）+ 会话/消息/part 规范化三表 | pattern 三层装配（默认⊕agent 画像⊕用户覆盖），审批**完全外化**为 REST + SSE |
| OpenHands（经典 V0） | Web UI（socket.io）+ headless CLI，每会话一个 Docker 沙箱 | Python（FastAPI） | S3/本地事件文件（每事件一 JSON + 25 条页缓存），写时脱敏 | 动作级预确认协议：待确认动作先入事件流，批准后以 CONFIRMED 态重发 + 执行侧二次校验 |
| claude-code（sourcemap） | 终端 CLI（Ink）；SDK 经 stdio control_request 反调宿主 | TS（Bun 编译期 DCE） | JSONL parentUuid 链 + 旁挂 entry（文件快照/墓碑/压缩边界） | 有序求值管线 deny→ask→工具自评→**bypass 免疫**→mode→allow + 多渠道审批竞速 |

**基线演进警告（引用旧资料前必读）**：

- **cline 已 SDK 化**：现为 monorepo（apps/vscode + apps/cli + sdk 四包 + hub daemon），经典「插件单仓巨型 Task 类」「shadow git 隐藏目录快照」均已演进（快照现为同仓私有 index + 事务恢复），网上旧架构资料不可直接引用。
- **codex 已双轴化**：流传的三档 suggest/auto-edit/full-access 是产品包装名，代码权威枚举是双轴（§2.1）。
- **OpenHands 已清仓迁移**：HEAD 是 TS 版 Agent Canvas，经典架构只在 git 历史 e8249f00a；V1 核心拆至外部仓 software-agent-sdk（未验证）。
- **claude-code-sourcemap 全部【还原源码】**（npm v2.1.88），与 SDK 捆绑的 2.1.269 有版本漂移（hooks 事件 ~10 → 25+）；Anthropic 专有代码，只参考模式。
- **opencode、gemini-cli 双代并存**：opencode permission v1（pattern 模型）/ v2（action+resources+save+source）迁移态；gemini-cli 线性历史与 graph 节点图两代 context 架构并存——引用前先确认现役链路。

## 2. 专题一：权限与审批架构

### 2.1 规则引擎六方对比

| 项目 | 规则定义与表示 | 求值者与时机 | 决策粒度 | 「批准并记住」的持久化 | 防绕过（TOCTOU / 审批疲劳 / fail 语义） |
|---|---|---|---|---|---|
| cline | SDK 层 `ToolPolicy{enabled,autoApprove}`（默认双 true）+ 宿主五动作开关；命令黑名单 command-guard（自认可绕过，诚实声明） | agent 循环内三段：hook（可覆盖策略）→ resolveToolPolicy → requestToolApproval 回调；宿主回调**实时读最新设置**（防会话启动时策略快照过期） | 工具级（MCP 仅 per-server 开关）；命令级只到黑名单 | 宿主 settings（带版本号防写竞态）；无审批侧规则修正 | fail-closed 双保险（无回调/回调抛错=拒绝）；非交互会话直接拒；**审批绑定 approvedRevision：被审内容一改即撤销审批（防 TOCTOU）**，与磁盘 spec 对账不一致 fail-closed |
| codex | execpolicy 规则文件（Starlark 前缀规则）× 双轴枚举 × 环境锁 | 进程内 ExecPolicyManager，命令执行**前**产出 Forbidden/NeedsApproval/Skip 三态；Guardian LLM 对七类动作打风险分（low→critical） | 命令级（规范化+前缀规则）+ 网络按域名 + 文件 grant_root（限本会话） | **ApprovedExecpolicyAmendment（批准=可审计的规则修订，谁/何时/批了什么前缀有据可查）**/ ApprovedForSession 会话缓存 | 环境级锁死（deployment 声明 Never 不可被会话覆盖）；granular 档关掉某类审批=**自动拒绝而非跳过**（防审批疲劳全点同意）；stdin 写入也过审批；运行中进程沙箱不因早先批准而改变（无运行中提权） |
| gemini-cli | TOML 规则文件五层优先级带 Default<Extension<Workspace<User<**Admin**，层内再用小数优先级 | policy-engine.ts 进程内 + 确认总线；shell 命令拆子命令递归查、wrapper 剥壳再查，重定向把 ALLOW 强制降级 ASK 且永不升回 | 工具级 + argsPattern 正则（内容级）+ 子命令级 | ProceedAlways（会话内存规则）/ AndSave 写 TOML（串行队列防丢更新）；敏感工具强制收窄到 commandPrefix/argsPattern，不许放行整类 | Admin 层永远压过用户；disableAlwaysAllow 合规总开关；headless 下 ASK_USER 抛错不静默放行；解析失败回落默认决策不臆测放行 |
| opencode | 配置 permission：工具名→通配 pattern→ask/allow/deny；三层装配 defaults⊕画像⊕用户（findLast 双通配、最后命中胜，无命中默认 ask） | permission/index.ts#evaluate 进程内；`pattern=="*"&&deny` 的工具直接从发给 LLM 的工具列表**移除** | 工具级 × 资源 pattern；bash 经 web-tree-sitter 语法树提取命令前缀（BashArity 160 条词典归约为人类可读前缀） | always 写会话内存规则 + **自动批量解锁**同会话符合新规则的 pending；v2 saved 表持久授权（REST CRUD） | deny 附规则 JSON 回喂模型（知道自己为何被拒）；reject 级联拒绝同会话全部 pending；实例关闭 finalizer 把 pending 全部置拒 |
| claude-code | PermissionRule **八来源**（含企业 policySettings 位）× 规则文法 ToolName(content)；PermissionUpdate 六操作 × 五落盘目的地 | permissions.ts 有序管线（严格步骤号注释）；外层再按模式加工（auto 模式：规则快路径→白名单→LLM 分类器→拒绝计数熔断回落人工） | 工具级 + 内容级（Bash 前缀规则，tree-sitter AST 解析，子命令拆分上限 50 防指数 DoS） | PermissionUpdate 落盘 session/settings 等五目的地，热生效 + 多源磁盘同步 | **内容级 ask 规则与 safetyCheck 对 bypassPermissions 免疫**（用户显式 ask 的连 bypass 也要问、敏感路径自动放行被阻断）；dontAsk 把 ask 硬转 deny；DecisionReason 全链可解释 |
| OpenHands | 无规则文件：confirmation_mode 布尔 + SecurityAnalyzer 插件（invariant sidecar 容器策略引擎 / LLM 打分 / grayswan） | controller 在 _step 预确认；**runtime 执行侧二次校验**（AWAITING_CONFIRMATION 的动作拒绝执行）——纵深防御 | 动作级二值（confirm/reject），无 once/always/改输入（档案明示的局限，细粒度需自行补规则层） | ❌ 无会话级缓存、无规则热更新 | fail-safe：未配 analyzer=UNKNOWN=**一律询问**；审批动作本身入事件流可回放；controller 缺位时执行端仍守住 |

横向结论：

1. **表示法谱系**：布尔开关（cline ToolPolicy）< 三态枚举映射（opencode pattern / gemini PolicyRule）< 来源分层规则对象（claude-code 八来源）< 独立 DSL 策略文件（codex Starlark / gemini TOML 五层带）。财务场景应从右端起步——规则要可 diff、可评审、可集中下发（claude-code 避坑：新系统直接用结构化规则对象 JSON，人类可读 DSL 只做表层）。
2. **求值者几乎全部进程内**（agent 服务内嵌策略引擎），唯一外置先例是 OpenHands 的 InvariantAnalyzer sidecar（策略引擎独立容器、trace 逐事件喂入）——即 Java 侧 OPA/独立规则服务的形态。含义：**外化的是审批交互面（谁来答），不是鉴权决策（能做什么）**；规则引擎承担第一道，人只接规则覆盖不到的灰区（codex 档案结论）。
3. **粒度分水岭在命令/内容级是否上 AST（抽象语法树）**：opencode（web-tree-sitter）、claude-code（tree-sitter）、codex（命令规范化）都为复合命令/引号/子 shell 绕过上了语法树；cline 黑名单与 gemini 正则 argsPattern 是次一等。财务 agent 的对应物更简单：「调哪个业务 API + 什么参数」天然是结构化 JSON，内容级粒度在 API 场景比 shell 场景更易解。
4. **「批准并记住」三级形态**：内存规则（会话级，人人都有）→ 配置文件落盘（gemini AndSave / claude-code PermissionUpdate）→ **可审计规则修订（codex amendment，最高形态）+ 版本绑定（cline approvedRevision）**。财务场景两者都要：「批这版分录 + 以后该供应商 10 万以下自动过」= 规则修订事件而非内存 yes 集合；内容变更即撤销审批。
5. **fail 语义三向对照**：fail-closed 是共识底线（cline 无回调即拒 / gemini headless 抛错 / OpenHands 无 analyzer 即问）；「合法提权通道被滥用」由 codex 环境锁 + claude-code bypass 免疫位解决；审批疲劳只有 codex 正面设计（granular 关闭=拒绝）。

### 2.2 「外部审批服务接管」的三种先例

| 先例 | 机制 | 关键设计 |
|---|---|---|
| opencode（REST + SSE 全接管）★对本案最直接 | `POST /api/session/:id/permission` 建请求 → `GET /api/permission/request?location=` **跨会话待审总表**（审批工作台入口）→ `POST .../:requestID/reply`（once/always/reject+message）→ SSE `permission.v2.asked/replied` 推送；saved 持久授权 CRUD | 执行线程 Effect Deferred 挂起等外部回调；审批人与执行机**物理分离的完整闭环** |
| gemini-cli（a2a-server 桥） | 确认总线（进程内 correlationId 配对的 request/response 消息对）→ a2a-server 桥成 A2A `tool-call-confirmation` 事件 → 远端回 `ToolConfirmationResponse{outcome,callId}` 翻译回总线 | **TUI 只是总线的又一个订阅者**——审批 UI 与核心彻底解耦，任何订阅者（含未来审批微服务）都能实现审批面 |
| cline（hub approval 事件协议） | hub 生成 approvalId → `approval.requested` 事件（带 toolName/inputJson/policy）挂 pendingApprovals map → 客户端 `approval.respond` 回填 → 广播 resolved | **断线不丢：重订阅即重放 pending 审批**（无人在线不丢单不隐式作答）；审批是客户端 capability 声明（不是谁都能答）；非交互会话直接拒绝 |

三者共同结构——本项目审批服务的公约数：**审批请求是可重放的事件而非一次性 RPC**；执行端挂起等待（Java 对应 CompletableFuture/阻塞队列）；回复三元语义 once / always / reject(+feedback)，且 **reject 的 message 回喂模型**成为纠错信号（opencode CorrectedError）；always 产生规则副作用并批量解锁同类 pending。cline 另有第四条朴素通道（desktop 文件 IPC：写 request JSON 轮询 decision JSON，超时=拒绝），证明审批通道本身可插拔。

## 3. 专题二：上下文管理与压缩

| 项目 | 触发阈值 | 策略与降级 | 压缩后保留什么 |
|---|---|---|---|
| cline | 90% 触发（ratio 0.9）、目标压到 0.7、保留最近 20k tokens | **双策略注册表**：basic（确定性，不依赖 LLM）/ agentic（LLM 摘要）；**溢出恢复强制走 basic**——provider 刚拒绝过长请求时不能再赌一次 LLM 成功 | 最近 assistant 文本 + 工具活动摘要；canonical 转录不动，摘要旁挂 `.compaction.json` 且恢复前校验其覆盖前缀 hash |
| codex | model_auto_compact_token_limit 配置 + overflow 兜底 | **mid-turn / pre-turn 两模式**：mid-turn 把摘要注入到最后一条真实 user message 前（贴合模型训练预期），pre-turn 不注入、下轮全量重注入 | CompactedItem 元数据（窗口号/ids/**压缩模型 hash**——可追溯哪个模型压的哪窗口）+ RetainedContext 跨压缩窗口；另有无 LLM 的 fallback prompt |
| gemini-cli | 0.5×tokenLimit 触发；**保最近 30% 原文、压前 70%**，切分点只准落在非 functionResponse 的 user 消息边界 | 两段式 LLM 压缩 + Probe 自校验（用同一历史反问「漏了什么」再出改进版）；防膨胀检查（压完更大则判失败放弃）；曾失败则降级纯截断 | `<state_snapshot>` 固定 7 节（goal/constraints/knowledge/artifact/files/actions/**task todo 清单**）+ 防提示注入指令段 + 已批准 plan 强制保留段；工具输出反向预算：近期高保真、远期截为末 30 行+指针文件 |
| claude-code | 阈值数学：effectiveWindow − min(maxOutput, 20k) − 13k；**连续 3 次失败熔断**（曾致每天 25 万次无效 API 调用） | **两级压缩**：microcompact（只清旧工具结果换占位符）+ autocompact（8 段结构化摘要）；摘要请求自身超长则截头重试 | **状态恢复清单（最全）**：按时间戳恢复最近读过文件为 attachment、plan 文件、已用 skills、deferred 工具 delta 重放、compact boundary 元数据；todo 可从 transcript 反扫恢复 |
| opencode | overflow 自动（context limit − 输出预留）+ 手动 API；keep.tokens 可配 | select：从最新往旧累积到 keep.tokens，其前摘要、其后原文保留 | SUMMARY_TEMPLATE 固定 6 节（Objective/Constraints/Completed/Blocked/Next Move/**Relevant Files**）；增量合并规则显式声明（旧摘要未带入即丢、冲突以新为准） |
| OpenHands | Condenser 插件族（窗口/遗忘/LLM 摘要/注意力），ContextWindowExceededError 触发压缩请求 | condense 返回 View（裁剪视图）或 Condensation（**声明遗忘哪些 event id** + 可选摘要，作为事件回流再触发一步） | 遗忘声明本身是事件——压缩决策可审计、可回放 |

六方共识：① 阈值显式参数化且必有 overflow 兜底；② **确定性降级路径**（cline 强制 basic / gemini 降截断 / codex fallback prompt）——溢出恢复不能依赖再一次 LLM 成功调用；③ 摘要模板结构化固定节，goal/constraints/todo/files 是公约数（gemini 7 节、opencode 6 节、claude-code 8 段）；④ **原文不可变、摘要旁挂可校验**（cline hash / codex CompactedItem / OpenHands 遗忘声明入流）——审计要求下摘要永远可丢可重生成；⑤ 工具输出三招：反向预算（gemini）、头尾保留（cline 48k）、**落盘指针**（gemini 40K / opencode 50KB——全文写文件、上下文只留占位+路径按需取回，财务大报表场景直接可用）。

## 4. 专题三：会话持久化与恢复

| 路线 | 代表 | 结构要点 | 写并发 | 审计特性 |
|---|---|---|---|---|
| JSONL append-only | cline（canonical 转录）/ codex（rollout）/ claude-code（parentUuid 链） | codex 行={timestamp, ordinal, item} 且 **TokenUsageRecord/SecurityRiskScore 单独成持久化项**、倒序扫描+可寻址读（老会话分页不全量加载）；claude-code 链成员单一真相源 isChainParticipant（progress 不入链——#14373 事故教训）、墓碑式删除、旁挂快照 | codex 显式 writer_lock + ordinal 乱序恢复 + 行级压缩；claude-code 前缀跟踪续链 | append-only + 摘要不覆盖原文是审计正确姿势；claude-code 50MB 读上限 + portable head/tail 读 |
| SQLite 事件溯源（event sourcing） | opencode | event(aggregate_id, seq, type, data) + event_sequence 单调序列 + 唯一索引；会话/消息/part 规范化三表（每 part 一行，天然增量流式写）；成本列内嵌会话表 | **事务 + 唯一索引天然并发安全**，比文件锁可靠 | 回放=重放聚合序列；durable 事件子集有显式清单 |
| 对象存储事件文件 | OpenHands | 每事件一 JSON（sessions/{sid}/events/{id}.json）+ 25 条页缓存缓解远端读放大 + **写时脱敏**（secret 值持久化前统一替换） | 锁内分配单调 id；单线程事件循环 | Observation.cause 回指 Action id——**因果链在数据模型层**；事件级 llm_metrics/cost 挂载 |
| 全量 JSON 重写 | gemini-cli（logs.json 读改写全文件 + tag 快照） | checkpoint 保存全量历史 + authType（恢复校验认证方式一致，否则拒绝） | ❌ 并发弱（档案自认不适合服务端） | 非合规级审计链（靠 telemetry） |

resume / fork 语义对照：

- **codex 最规范**：InitialHistory{New, Cleared, Resumed, Forked} 四值同构入口，fork 记 forked_from_id 血统；resume 后靠 Compacted + RetainedContext 重建衔接。
- **claude-code 细节最重**：session id 与项目目录**原子配对**切换、复用原文件续追加；fork=复制重写新 JSONL 并**重播种 contentReplacement 记录**（漏了会缓存击穿——注释详述的真实事故）；todo/文件历史等运行时状态从 transcript 反扫恢复。
- **opencode resume=即续**：会话全量在库，对既有 sessionID 再发 prompt 即恢复；回滚是 **revert 两阶段**（stage 影子快照 → 人工确认 → commit 删区间，可 unrevert 反悔），忙碌时拒绝。
- **cline hub 形态**：会话归 daemon 所有，客户端随意 attach/detach 换端续流；根会话懒创建（首个被接受 turn 才落盘，无空历史垃圾）。
- **OpenHands**：attach 时从存储重建 EventStream + 重连已有容器；客户端带 latest_event_id 断点续传重放。

写并发结论：服务端多会话场景 **SQLite 事件溯源 > 带锁 JSONL > 无锁全量重写**；Java 侧主存直接选 event 表 + 聚合序列唯一索引（Spring Data 可直建），JSONL 适合做归档/导出/合规报送格式而非主存。

## 5. 专题四：沙箱与执行隔离

| 项目 | 隔离级别 | 机制与要点 |
|---|---|---|
| codex | **OS 级（最强）** | macOS Seatbelt（`deny default` 起步、只认绝对路径 sandbox-exec 防 PATH 注入）/ Linux bubblewrap+seccomp / Windows restricted token；**网络 MITM 代理按域名出审批**（网络不是开关而是按 host 审批）；同一份 FileSystemSandboxPolicy **双处执行**（进程内文件工具 + OS 系统调用层）纵深防御，deny glob fail-closed |
| OpenHands | 容器级 | 每会话一 Docker 容器（tini 收割僵尸、非 root 用户、overlay 只读挂载）；远程 runtime 默认 **gVisor** 隔离；所有动作在容器内 FastAPI 执行服务器执行（X-Session-API-Key 鉴权），宿主只持 HTTP 客户端 |
| gemini-cli | OS 级（同思路） | Seatbelt/bwrap 参数构造器；沙箱内命令申请额外权限走 sandbox_expansion 确认类型 |
| claude-code | 沙箱换免审 | 沙箱开启且命令可沙箱时 bash 自动放行（autoAllowBashIfSandboxed）；网络访问伪装成工具走同一审批协议——把信任从「人逐条批」转移到「沙箱兜底」 |
| cline | **无沙箱（纯审批）** | spawn 平台 shell 无隔离；防线=审批 + 黑名单（command-guard 自认拦不住 `python -c` 写文件）；文件边界 restrictToCwd 只管相对路径、绝对路径直通——档案结论「软约束+审批，非硬隔离」 |
| opencode | 无 OS 沙箱（主链路） | 靠 pattern 权限 + AST 命令前缀提取；containers 包存在但权限模型是第一道 |

**对财务场景的隔离分级**（约束「agent 只该调业务 API、不该执行任意代码」时，什么级别的隔离是必要的）：

1. **首选：能力面收窄，零沙箱成本**。不提供 shell/任意代码执行工具，工具面=业务 API 的受控封装。两个关键细节：opencode 的「deny 工具从发给 LLM 的工具列表**移除**」——模型看不见的能力不可被提示注入诱导调用；cline 的 executor 注入接缝——工具实现可整体替换为业务 API client。此级别下 OS 沙箱**非必要**，审批管线（§2）+ 执行侧二次校验（OpenHands 模式：业务 API 调用出口统一再查审批单状态，中间层缺位仍守住）已足。
2. **出口治理**：网络白名单只通业务 API 网关——codex「网络按域名审批」的服务端等价物是 egress 白名单/服务网格，或最简单：agent 进程无公网 outbound、一切外部调用经统一 API client 层。
3. **仅当确需执行分析代码**（对账脚本/批量核算）才引入容器隔离：OpenHands「每会话容器 + 容器内执行服务器 + session key」是 Java 生态最可平移的形态——JVM 内 SecurityManager 已废弃、Seatbelt/bubblewrap 无 Java 等价物，**Docker（+gVisor）是现实替代**。
4. codex 的**声明式策略双处执行**独立于沙箱也值得借鉴：一份「可读/可写/禁读」资源声明同时驱动应用层鉴权与基础设施（DB grant/网络策略）——单源真相防两套权限漂移。

## 6. 对本项目的启示清单

标注 ★ = 与 Java/Spring 生态映射最直接（概念无需转换）。

1. ★**审批三段管线 + fail-closed 回调**——来源：cline.md §5。工具调用前拦截器链（hook 可覆盖策略）→ 策略 → 审批回调，回调未配置/抛错即拒绝。Spring 映射：AOP/HandlerInterceptor 链 + `ApprovalCallback` 接口。**必须叠加宿主层「启动全 false + 回调内实时评估」**（策略快照过期是真踩过的坑）；cline SDK 默认 autoApprove=true 的「宿主负责安全」设计不可照搬。
2. ★**审批外化 API 组**——来源：opencode.md §5.3。建请求 / 跨会话待审总表 / reply(once/always/reject+message) / saved 授权 CRUD + SSE 推送 + 执行线程挂起（Java=CompletableFuture）。Spring MVC + SseEmitter 可一比一照抄端点语义；reject 带 feedback 回喂模型、always 批量解锁、实例关闭 pending 全拒——边界语义已被踩过。数据模型一步到位定 action/resources/save/source 四元组（避开 opencode v1/v2 双代坑）。
3. ★**审批作为可重放事件 + 断线不丢**——来源：cline.md §5 hub 层。approval.requested 挂 pending map、重订阅重放、非交互会话拒绝、审批是客户端 capability 声明。多审批端（Web 工单/移动端）场景映射 Spring 事件 + WebSocket/SSE 重放。
4. ★**双轴权限模型 + granular 关闭=拒绝**——来源：codex.md §5。审批策略（每步审/按需审/白名单免审/全拒）× 数据访问模式（只读/受限写/全放开）**正交组合**而非一条滑动杆；提供环境级锁死（部署档不可被会话覆盖）。Java 枚举组合即可，无生态障碍。
5. ★**有序求值管线 + bypass 免疫位 + DecisionReason**——来源：claude-code-sourcemap.md §4。deny→ask→工具自评→**硬合规判定（bypass 免疫）**→mode→allow 固定次序；超限额交易/敏感科目判定放在任何提权模式之前；每个决策附结构化理由（sealed interface + record 建模）供审计报表直接消费；fail-safe 默认（无策略引擎=ask）照抄 OpenHands。
6. ★**策略即数据 + 分层优先级带**——来源：gemini-cli.md §5.2。TOML 五层（Admin 永远最高）与 Spring PropertySource 顺序 + PolicySource 枚举排序同构；管理员层放硬合规 DENY 规则、用户层只许放宽到 ASK；disableAlwaysAllow 式合规总开关。always-allow 必须强制收窄到 pattern（gemini TOOLS_REQUIRING_NARROWING）。
7. ★**审批与被审内容版本绑定 + 审批修正案**——来源：cline.md §5（agenda approvedRevision）、codex.md §5（ApprovedExecpolicyAmendment）。批准后内容一改即撤销审批、与 spec 对账不一致 fail-closed；「批这版凭证 + 以后同类自动过」= 可审计的规则修订事件。财务场景两者都直接可抄。
8. ★**SQLite 事件溯源会话存储**——来源：opencode.md §4.1。event 表 + 聚合序列唯一索引 + 会话/消息/part 规范化——Spring Data/JPA 直接建模；成本/审批/风险作独立事件类型入流（codex TokenUsageRecord/SecurityRiskScore 先例）；写时脱敏放持久化适配器层统一做（OpenHands.md §4）。
9. **上下文压缩三件套**——来源：cline.md §4（双策略+确定性降级）、gemini-cli.md §4.1（七节模板+Probe 自校验+防膨胀）、claude-code-sourcemap.md §6（恢复清单+熔断）。阈值参数化 + overflow 兜底 + 溢出恢复不依赖 LLM；固定节摘要（目标/约束/待办/关键文件）+ 压缩后恢复清单（最近文件/计划/工具 delta）；连续失败熔断。
10. ★**工具输出落盘指针**——来源：gemini-cli.md §6、opencode.md §6。大结果集（报表/流水）超阈值全文落文件、上下文只留占位+路径按需取回——Java 侧对象存储 + 引用即可。
11. ★**revert 两阶段（stage→确认→commit）+ 事务式快照**——来源：opencode.md §4.2、cline.md §4（checkpoint 恢复前先 stash 现状可回滚）。对应财务「草稿/冲正」：回滚本身不破坏现场。
12. ★**执行侧二次校验**——来源：OpenHands.md §5。执行器收口处独立复核审批状态（只执行 CONFIRMED），与决策层形成纵深防御——Java 里即业务 API 调用出口统一再查审批单，防中间层缺位。
13. **能力面收窄优先于沙箱**——来源：opencode.md §5.1（deny 工具隐藏）、cline.md §6（executor 注入）、OpenHands.md §6（容器模式）。财务 agent 工具面=业务 API 封装，deny 的工具从模型工具列表移除；确需代码执行才上容器隔离（JVM 无 OS 沙箱等价物，Docker+gVisor 替代）。
14. ★**单服务多租户路由**——来源：opencode.md §7。location 中间件按请求 header 路由到 per-directory（=per-租户）服务实例——Spring HandlerInterceptor + 租户级 ServiceLocator 缓存同构。
15. **契约版本化与链单一真相源**——来源：claude-code-sourcemap.md §7 避坑、OpenHands.md §8。以内部格式为集成契约必须锁版本；transcript 链成员单一真相源 + 写前过滤；新增旁挂 entry 必须同步考虑 fork/resume 重播种——避免 OpenHands 式推倒重来（harness 核心契约做成稳定 API）。
