# PulsePet v2 设计方案

> 输入：[V2-SCOPE.md](./V2-SCOPE.md)（范围与裁定）、v1 [DESIGN.md](../v1/DESIGN.md)（既有架构基线）。
> 性质：v2 各里程碑的技术方案，**按里程碑增量撰写**——每个里程碑开工前补齐对应章节，已定稿章节不回改（勘误以「修订」标注）。
> 约定：v2 文档一律落 `docs/v2/`，不回改 `docs/v1/`；正文 `DESIGN §x` 指代 v1 设计文档。

---

## 1. M1：Claude Code 事件接入 + 接入管理（~1.5 周）

### 1.0 Spike 结论（2026-08-23，CC 2.1.240 本机实测 + 四产品源码核对）

> 本节为 §1.1 起所有设计的证据基线。来源：① 本机 claude 2.1.240 二进制内嵌文档与 zod schema 提取
> （`~/.npm-global/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe` 字符串考古，无需网络）；
> ② 四个参考产品浅克隆源码精读（openpets `packages/claude/src/`、petdex `petdex-desktop-native/src/agent_hooks.zig`、
> clawd-on-desk `hooks/`、agentpet `Sources/AgentPetCore/HookInstaller.swift`）。

#### 1.0.1 CC hooks 事实（二进制提取）

| # | 事实 | 证据 |
|---|---|---|
| S1 | 事件全集（2.1.240）：`PreToolUse / PostToolUse / PostToolUseFailure / PostToolBatch / Notification / UserPromptSubmit / UserPromptExpansion / SessionStart / SessionEnd / Stop / StopFailure / SubagentStart / SubagentStop / PreCompact / PostCompact / PermissionRequest / PermissionDenied / Setup / TeammateIdle / TaskCreated / TaskCompleted / Elicitation…` | 内嵌事件名数组 |
| S2 | `PermissionRequest` 真实存在：「Run before permission prompt」，matcher = Tool name | 内嵌 Hook Events 表 |
| S3 | `StopFailure` 真实存在：payload `{hook_event_name, error, error_details?, last_assistant_message?}`（V2-SCOPE 映射表成立） | zod schema |
| S4 | hook input（stdin JSON）基础字段：`{session_id, transcript_path, cwd, prompt_id?, permission_mode?, agent_id?, hook_event_name, + 事件专属字段}`。**`agent_id` 仅在子代理上下文出现**（彩蛋池「子代理感知」的免费数据源，M1 不消费） | zod base schema `YP` |
| S5 | hooks 配置结构：`settings.json → hooks.EVENT[].matcher + hooks[].{type:"command", command, timeout, statusMessage}`；matcher 是 tool 名正则（如 `"Edit|Write"`）；无 matcher = 全捕 | 内嵌 Hooks Configuration |
| S6 | **hooks 支持 `async: true`**（配置级 fire-and-forget，CC 不等待）+ `asyncRewake: false`；openpets 生产使用中。⚠️ 修正初判：首轮二进制 grep 漏检（"async" 字面量多为运行时库噪音），以 openpets `hook-settings.ts` 实证为准 | openpets `createHookCommandEntry` |
| S7 | hooks 默认同步（CC 等待 hook 完成，PreToolUse 可借返回值 block）；`timeout` 每 hook 条目可配（文档示例默认 60s） | 内嵌文档 |
| S8 | Windows：hooks 默认经 **Git Bash** 执行；可用 `"shell": "powershell"` 显式指定（pwsh/powershell 探测） | 二进制错误文案 |
| S9 | `settings.json` 注释容忍性**未确证**（auth 门槛挡住非交互实证；二进制含 JSONC 解析器但无法确认 settings 走哪条路）→ 设计绕开：标记放 command 数据内 + 结构化改写（见 §1.4），是否容忍注释无关紧要 | — |
| S10 | 本机环境：claude 2.1.240 npm 安装（node 22+ 在 PATH 必在）；`~/.claude/settings.json` 为纯 JSON、无 hooks 段、无注释；`env` 配第三方代理（ANTHROPIC_BASE_URL=127.0.0.1:15721 + deepseek 模型映射——V2-SCOPE §3.5「CC cost 不可信」坐实，M5 处理） | 实测 |
| S11 | CC 另有原生插件系统（`~/.claude/plugins/`、marketplace、插件可携带 hooks 自动注册）——**不采用**，理由见 §1.12 | `CLAUDE_PLUGIN_ROOT` 等字符串 |

#### 1.0.2 参考实现对照（四产品源码级）

| 维度 | openpets（1.0k★，CC 集成最深） | petdex（3.7k★） | clawd（5.8k★，19+ agent） | agentpet（300★，Swift） |
|---|---|---|---|---|
| hook 运行时 | **node CLI**：`node <app 内嵌绝对路径> hook --openpets-managed`，兜底 `npx -y @open-pets/claude hook` | **原生可执行** `~/.petdex/bin/petdex-hook bubble <phase> <agent>`（演化链：curl → petdex.js(node) → native；含三代 generation 迁移检测） | node 脚本（`hooks/*-hook.js`） | **App 二进制** `agentpet hook` |
| settings 修改 | 严格 JSON.parse → structuredClone → 增删 → stringify(2 空格) 重写；**写前备份**（`settings.json.openpets-backup-<ISO>.json`，0600）+ **原子写**（tmp + rename）；解析失败报 error 不落笔 | 同左（Zig JSON + `hook_obj.put("timeout",…)`） | 同左（JS） | 同左（Swift） |
| managed 标记 | command 内嵌 `--openpets-managed` CLI 参数（数据级） | command 含 petdex 路径特征 + phase 参数 | command 含 clawd 特征 | command 含 `"agentpet"`+`"hook"` |
| 零阻塞手段 | `async:true, asyncRewake:false, timeout:3` | `timeout:2` + **Unix shell 包装**：`if [ -f hooks-disabled ]; then drain; exit 0; fi; if [ -x hook ]; then exec hook …; fi; drain; exit 0`（缺席短路 + **stdin drain** 防管道悬挂）+ Windows `.cmd` 同义包装 | —（未见专门处理） | 无 timeout（吃默认 60s） |
| 注册事件 | UserPromptSubmit / PreToolUse / PermissionRequest / Notification / Stop / StopFailure（每事件一条无 matcher 条目） | claude_events：UserPromptSubmit / PreToolUse / PostToolUse / Notification / Stop（+qoder 专属 PostToolUseFailure；codex 用 PermissionRequest 替 Notification） | SessionStart / UserPromptSubmit / PreToolUse / PostToolUseFailure / Stop / StopFailure / SubagentStart / PreCompact / Notification | SessionStart / UserPromptSubmit / PreToolUse / Notification / Stop / SubagentStop |
| 关键映射 | prompt→thinking；permission→waiting；**Stop→success**；StopFailure→error；Edit/Write/MultiEdit→editing；Bash+test 正则→testing；**其余工具不映射**；Notification 注册但无反应 | phase 驱动 server 侧分类；**PostToolUseFailure 专门点亮 failed 行**（源码注释：the one event no other wired agent reports） | SessionStart→idle；PreToolUse→**working（全捕）**；PostToolUseFailure→**error**；Stop→attention；StopFailure→error | — |
| 客户端节流 | **文件级**（JSON 状态文件原子写：speech 20s / permission 3s / reaction-per-kind 10s）——因事件进程一次性、状态须出文件 | 无（server 邮箱 + 限流） | — | PerKeyThrottle（App 侧） |
| 其它安全 | stdin ≤64KB；退出码恒 0；错误吞（debug 模式 stderr 且**净化路径**）；项目级 settings.local.json 存在 openpets 项时全局项运行时让位（防双反应） | killswitch 前置于 shell 包装 | — | — |

**采纳结论**（用户裁定「参考其他知名插件/pet 产品」的落实）：

- **运行时 = node 脚本**（openpets 模式，`node <绝对路径> --pulse-pet-managed`）。理由：① CC 集成最深的参考即 node CLI；② classify/postState 与 opencode 插件同构、同语言可复用（双实现一致性）；③ 零入口改造（不动 main.rs / 单实例链路）；④ 作者环境 node 保证（S10）。petdex 式原生化为演进选项（§1.11 R3）。
- **settings 修改 = 严格 JSON 结构化改写**（四家一致；v1 的 opencode JSONC 文本合并器**不适用于此文件**）+ openpets 的备份 + 原子写。
- **零阻塞 = `async:true` + `timeout` + petdex shell 包装**三重防护（§1.3）。
- **shell 包装**（petdex 模式）：killswitch 前置检查、hook 文件缺席短路、stdin drain、恒 exit 0——脚本被删/未装/App 未运行时对 CC **完全静默**。

---

### 1.1 目标与范围

- Claude Code 会话状态驱动宠物动画（8 种归一化状态，与 opencode 同一套）。
- `waiting-permission` 单向展示（用户在终端审批，宠物经后续事件自动跟随——不做代答，V2-SCOPE §4 裁定不变）。
- session key 升级为 `(agent, sessionId)` 复合键（v1 预留的兑现：`/state` 协议 `agent` 字段 M1 起被消费）。
- 设置页新增「接入管理」区：opencode 插件 / Claude Code hooks 各自的状态显示 + 一键安装/卸载 + doctor（源自 petdex v1.0.0 模式）。
- 安装器 Rust 内置（用户裁定 2026-08-23）；`install.sh / install.ps1` 保留为 **opencode 接入的**无 App 手动通道——**M1 不扩展其覆盖 CC**（结构化 JSON 合并只在 Rust 实现一份，shell/node 复刻会造成双实现漂移；CC 用户必然装 App，App 内「接入管理」是唯一通道）。
- **不含**：CC token 统计（M5，transcript 增量解析）、气泡 agent 标识 UI（M2/M6；M1 仅打通数据通道）、子代理感知（彩蛋池，数据源 agent_id 已确认免费）、工具级气泡（M3）。

### 1.2 进程拓扑（M1 后）

```
opencode 进程（Bun）                        Claude Code 进程
  └ PulsePet 插件（常驻，v1 既有）             └ hooks：每事件 spawn 一次性进程
    classify → POST /state                      shell 包装 → node ~/.pulsepet/hooks/claude-code-hook.js
      （agent="opencode"）                        读 stdin JSON → classify → POST /state
                    │                              （agent="claude-code"）
                    └────────────┬──────────────────┘
                                 ▼  127.0.0.1:<port> + x-pulsepet-token（v1 既有）
                   PulsePet App（tiny_http /state）
                                 ▼
              SessionStateMachine：HashMap<"agent:sessionId", Record>
                                 ▼（优先级合并，v1 既有算法不变）
              pulsepet://state {kind, agent} → pet 窗口动画
```

与 v1 的差异只有三处：事件多一个来源进程形态（一次性 vs 常驻）、状态机 key 复合化、下发 payload 带 agent。

### 1.3 CC hook 脚本设计（`opencode-plugin/claude-code-hook.js`）

> 源文件放 `opencode-plugin/`（与 pulse-pet-hook.js 并列），由 App 内嵌
> （`include_str!`）写入 `~/.pulsepet/hooks/claude-code-hook.js`（Windows
> `%LOCALAPPDATA%\pulsepet\hooks\`；源文件名与落点名一致，对齐 v1 插件命名惯例）。
> 纯函数导出供 vitest 单测（与 pulse-pet-hook.js 同模式）。

#### 1.3.1 事件映射表（定案）

| CC 事件 | PulsePet kind | 参考 / 理由 |
|---|---|---|
| `SessionStart` | `idle` | clawd/agentpet 同款；`--resume` 时复位旧 session 残留状态，成本一行 |
| `UserPromptSubmit` | `thinking` | 三家一致 |
| `PreToolUse`（无 matcher 全捕，脚本内分类） | `tool_name ∈ {Edit, Write, MultiEdit, NotebookEdit}` → `editing`；`Bash` 且 `tool_input.command` 命中测试正则 → `testing`；其余 → `working` | editing/testing 粒度照 openpets（补 MultiEdit/NotebookEdit）；「其余 → working」照 clawd 与 **opencode 插件既有语义**（工具在跑=working，跨 agent 行为一致；openpets 的「不映射」分歧记录在案——他们无 working 复位语义） |
| `PostToolUse` | `working`（瞬态复位主信号） | 对齐 opencode `tool.execute.after → working`；petdex post phase 同义 |
| `PostToolUseFailure` | `error` | **petdex + clawd 双参考**（petdex 专门为它点亮 failed 行）。自愈路径：error 非瞬态本会停留 30s，但 Claude 重试的下一个 Pre/PostToolUse 事件秒级覆盖——实测观感预期是「红一下，动起来就消」 |
| `PermissionRequest` | `waiting-permission`（单向） | openpets 同款；matcher 留空全捕 |
| `Stop` | `idle` | **与 openpets(success)/clawd(attention) 的分歧记录**：PulsePet 的 success 是 token 汇报/庆祝专用的瞬态（v1 定案），且 M5 后 CC idle 同样触发 transcript 汇报注入 success+气泡——届时与 opencode 完全同构；attention 状态不存在于 9 行 atlas。Stop 语义=本轮回答结束，与 opencode `session.idle`（每轮边界）对齐 |
| `StopFailure` | `error` | openpets + clawd 一致 |
| `Notification` | **不注册** | openpets 注册但无反应；PermissionRequest 已覆盖权限等待；「60s 等输入」提醒是噪音，违反「静默陪伴」原则 |
| `SubagentStart` / `SubagentStop` | **不注册**（彩蛋池） | 数据源已确认：hook input 的 `agent_id` 字段 + 两个事件均存在，未来驱动 jumping 行几乎免费 |
| `SessionEnd` / `PreCompact` / `PostCompact` / 其余 | **不注册** | Stop 已覆盖轮边界；M1 最小事件集（8 个） |

**与 opencode 侧机制的对照（不需要移植的两个机制）**：

- **thinking 粘性窗**：不需要。opencode 侧粘性窗解决的是 `chat.message(thinking)` 与 `session.status(busy)→working` 几乎同时到达的覆盖竞争；CC 无 busy 类事件，`UserPromptSubmit` 后下一事件是 PreToolUse（通常秒级延迟）或 Stop——thinking 有天然可见窗口。
- **流式心跳**：无源可依。CC 无流式 hook 事件（S1 全集里无 message delta 类），纯文本长生成期事件静默由 App 侧既有超时兜底（thinking 30s → working → idle）。**已知边界**：CC 长回答期间宠物可能提前回 working/idle，Stop 到达后回归 idle；除非 CC 未来加流式 hook，无解也无害（记录在案）。

#### 1.3.2 脚本行为契约（零阻塞，三重防护）

每次事件 = 一个进程，生命周期：**spawn → 读 stdin（≤64KB）→ killswitch 检查 → 分类 → 读 runtime 文件 → POST（超时 1s）→ exit 0**。

1. **配置级**（安装器写入的 hook 条目属性）：`async: true, asyncRewake: false`（CC 不等待，S6）+ `timeout: 3`（async 被旧版 CC 忽略时退化为同步 + 3s 硬上限，双保险）。
2. **shell 包装级**（command 本体，petdex 模式，见 §1.4.2）：killswitch 前置、脚本文件缺席短路、**node 存在性检查**、stdin drain（防管道悬挂）、恒 exit 0——**hook 文件被删 / node 缺席 / App 未运行时对 CC 完全静默**（不向 transcript 喷错）。仅 Unix 形态；Windows 简化形态见 §1.4.4。
3. **脚本级**：任何异常 catch-all → exit 0；无 stderr 输出（除非 `PULSEPET_HOOK_DEBUG=1`，且错误文案净化路径，openpets 同款）；**无重试、无退避**——一次性进程不存在 v1 §九 的「退避睡眠阻塞宿主」路径，缺席=丢弃（endpoint/token 文件 ENOENT → 立即 exit 0，复用 v1 §9.4 快速通道语义）。

**POST 契约**：与 opencode 插件共用 `/state`（body `{sessionId, kind, agent:"claude-code"}`；session_id 取 hook input `session_id` 字段，缺号丢弃不落 default——较 opencode 侧更严：opencode 仅对流式心跳类事件缺号丢弃（v0.1.3 四-4），其余落 `"default"`；CC 侧全事件缺号丢弃，因 `session_id` 是 hook input 里唯一可靠的会话标识，缺号事件无从归属）。测试命令判定**复用 opencode 插件 `TEST_CMD_RE` 同款正则常量**（源码级共享：CC hook 脚本与 pulse-pet-hook.js 的正则定义保持逐字一致，`cargo test`/`go test` 等经 "test" 子串天然覆盖），防两处正则漂移。

**节流：不做**（M1 裁定）。理由：CC 事件天然低频（每 prompt/工具/轮次一次，无流式）；POST 为幂等状态覆盖，同 kind 重复无视觉变化；App 侧 30 req/s 限流兜底。与 openpets（文件级节流）的分歧原因：他们有 say() 语音气泡需防刷屏，M1 的 PulsePet 无 CC 侧气泡；M3 工具级气泡落地时按 V2-SCOPE 倾向统一在 **App 侧过滤**（届时一并设计）。

### 1.4 安装器设计（Rust 内置）

#### 1.4.1 命令集与文件布局

新增 `src-tauri/src/integrations.rs`：

| Tauri command | 行为 |
|---|---|
| `integrations_status() -> Vec<IntegrationStatus>` | 两个接入的完整状态（即 doctor） |
| `integrations_install(id)` / `integrations_uninstall(id)` | 安装/卸载；`id ∈ {"opencode", "claude-code"}` |

```jsonc
// IntegrationStatus（一条接入的健康快照）
{
  "id": "claude-code",
  "installed": true,            // 配置条目存在且与 canonical 形态一致
  "stale": false,               // 配置条目存在但形态过时（版本演进 / md5 不匹配）
  "version": "0.2.0",           // 内嵌脚本版本 = App 版本（env!("CARGO_PKG_VERSION")，脚本随 App 发布；
                                // V2-SCOPE「版本状态」的承载——是否升过级由 stale/md5 对账等价表达）
  "configPath": "/Users/x/.claude/settings.json",
  "hookFile": { "exists": true, "matchesBundled": true },  // md5 与 App 内嵌副本对账
  "nodeAvailable": true,        // CC 接入独有：spawn `node --version` 探测（每次 doctor 现测不缓存，~50ms）
  "lastEventAt": null,          // App 侧最近收到该 agent 事件的时间（运行时活性，内存跟踪见 §1.5）
  "message": "…"                // 人类可读诊断（zh/en 走 i18n.rs）
}
```

> 概念边界：`integrations`（外部 agent 接入管理，本模块）与 v1 既有 `plugins.rs`（PulsePet 内置插件机制，如 todo）是两个正交概念，无继承/依赖关系。

安装产物（两接入对等）：

| | opencode | claude-code |
|---|---|---|
| 脚本落点 | `~/.config/opencode/plugins/pulse-pet-hook.js`（既有） | `~/.pulsepet/hooks/claude-code-hook.js`（Windows `%LOCALAPPDATA%\pulsepet\hooks\`） |
| 脚本来源 | App 内嵌 `include_str!("../../opencode-plugin/pulse-pet-hook.js")` | 同左（claude-code-hook.js） |
| 配置文件 | `~/.config/opencode/opencode.json`（或 `.jsonc`，既有查找顺序） | `~/.claude/settings.json` |
| 配置形态 | `plugin` 数组一项 `"./plugins/pulse-pet-hook.js" // --pulse-pet-managed`（JSONC，v1 既有） | `hooks` 下 8 个事件键，各追加一组 matcher 省略（=全捕）的 matcher 组条目（§1.4.2） |
| 修改方式 | **JSONC 文本外科手术**（v1 `opencode-config.mjs` 算法移植 Rust，保注释/尾逗号） | **严格 JSON 结构化改写**（serde_json `preserve_order` feature，保键序）+ 备份 + 原子写 |
| managed 标记 | 行内注释 `--pulse-pet-managed`（JSONC 官方容忍） | command 字符串内嵌 `--pulse-pet-managed` 参数（数据级，S9 绕开注释问题） |

> serde_json 需开 `preserve_order`（Cargo.toml features）——用户 settings.json 的 `env` 等键顺序不被重排。这是对四家「stringify 重写」做法的等价实现。

> ⚠️ 与 v1 `install.sh` 的关系：Rust 内嵌 `include_str!` 后，**App 与脚本单一来源**（仓库源文件）；`install.sh/ps1` 继续从同一源文件拷贝，两者产物 md5 天然一致（doctor 对账基准 = 内嵌串）。手动通道保留，README 不变。

#### 1.4.2 claude-code 安装条目（canonical 形态）

每个事件键下追加一个 matcher 组（已存在的 pulse-pet 特征条目先移除再追加——升级即重装，openpets 同款）。**〔勘误 2026-08-24〕**初版把 pulse-pet 条目写成事件数组的直接元素（裸 command 对象），实机安装后 CC 报 `hooks.<Event>.0.hooks: Expected array, but received undefined`——CC zod schema 要求事件数组元素必须是 `{matcher?, hooks: [...]}` 组、command 条目在内层 hooks 数组（错误信息附官方示例），且为**文件级校验：一条错误整个 settings 文件被跳过**。S5 的事实提取 `hooks.EVENT[].matcher + hooks[].{...}` 本正确，§1.13 P2-5 修订时示例用错。正确定案：**matcher 组形态，外层省略 matcher = 全捕**（满足 PreToolUse 脚本内分类需求）：

```jsonc
{
  "hooks": {
    "UserPromptSubmit": [
      // 用户已有条目原样保留……
      { "hooks": [ { "type": "command", "command": "…", "timeout": 3, "async": true, "asyncRewake": false } ] }  // pulse-pet matcher 组（省略 matcher = 全捕）
    ]
    // … 共 8 个事件键：SessionStart / UserPromptSubmit / PreToolUse / PostToolUse /
    //    PostToolUseFailure / PermissionRequest / Stop / StopFailure
  }
}
```

pulse-pet 组内 hook 条目（command 为 Unix 形态；Windows 见 §1.4.4）：

```jsonc
{
  "type": "command",
  "command": "if [ -f \"$HOME/.pulsepet/runtime/hooks-disabled\" ]; then [ -t 0 ] || cat >/dev/null; exit 0; fi; if [ -f \"$HOME/.pulsepet/hooks/claude-code-hook.js\" ] && command -v node >/dev/null 2>&1; then exec node \"$HOME/.pulsepet/hooks/claude-code-hook.js\" --pulse-pet-managed; fi; [ -t 0 ] || cat >/dev/null; exit 0",
  "timeout": 3,
  "async": true,
  "asyncRewake": false
}
```

command 分解（petdex `canonicalCommandForTarget` 同构 + P2-2 修订的 node 存在性检查）：

1. killswitch 存在 → drain stdin → exit 0（排障通道，与 v1 opencode 接入共用同一 killswitch 文件）；
2. hook 文件存在 **且 node 在 PATH** → `exec node <script>`（exec 替换进程，少一层 shell 等待；`command -v node` 检查使 node 缺席也走兜底静默路径——否则 `exec node` 失败时 sh 以 127 退出并向 stderr 打 `node: command not found`，破坏静默契约）；
3. 兜底：drain stdin → exit 0（脚本被删/node 缺席时静默缺席，不向 CC 报错）。

`[ -t 0 ] || cat >/dev/null` 的 stdin drain：hook 的 stdin 是管道（CC 写入 payload 后关闭）；任何提前退出路径都必须**消费完 stdin**，否则 CC 侧写端可能 SIGPIPE / 管道缓冲压力（petdex 注释同义）。

#### 1.4.3 幂等 / 卸载 / 备份 / 原子写（对齐 openpets）

- **幂等判定**（P1-1 修订 + 2026-08-24 勘误适配）：逐事件键检查——遍历该事件键下全部 matcher 组（含省略 matcher 键的组）的 **hooks 数组内 command 条目**，pulse-pet 特征条目数恰为 1 且其 command 与 canonical 串完全一致 → `installed`；特征条目数 > 1，或存在任一特征条目形态不一致（含初版坏形态残留——**坏形态即 stale，重装即修复**）→ `stale`；无特征条目 → 未安装。「pulse-pet 特征」= command 字符串含 `--pulse-pet-managed` 或 pulsepet 路径（openpets `containsOpenPetsHook` 同构——存在性检测，与用户条目总数无关，用户自有条目共存不影响判定）。
- **安装** = 移除全部 pulse-pet 特征条目（含 matcher 组内，递归；所在组 hooks 空则整组移除）→ 逐事件追加 canonical matcher 组（事件数组缺失则建）→ 序列化写回。用户条目永不触碰。
- **卸载** = 移除全部 pulse-pet 特征条目（**与检测同口径递归进 matcher 组的 hooks 数组**；特征条目移除后所在组 hooks 空则整组移除）→ 事件数组空则删事件键 → `hooks` 对象空则删 `hooks` 键。
- **备份**：写前若文件存在，复制为 `settings.json.pulsepet-backup-<ISO时间戳>.json`（0600）；**写新备份前先清理旧 `settings.json.pulsepet-backup-*.json`**（时间戳文件名不会自然覆盖，显式清理保「仅保留最近 1 份」）。
- **原子写**：`settings.json.<pid>.tmp`（0600）→ rename（跨平台原子）。
- **解析失败防御**：JSON.parse 失败 / 顶层非对象 / `hooks` 非对象 → 报 error **不落笔**（openpets `readClaudeSettings` 同构）；文件不存在视为 `{}` 新建。
- **符号链接**：settings 路径为 symlink → 拒绝操作报错（openpets `assertSafeSettingsPath` 同构）。

#### 1.4.4 Windows 形态

- **command 用跨 shell 字面路径，不用包装语法**：

```text
node "C:\Users\<name>\.pulsepet\hooks\claude-code-hook.js" --pulse-pet-managed
```

  理由：§1.4.2 的 `if [ -f … ]` 是 POSIX sh 语法；Windows 上 CC 默认经 Git Bash 执行 hooks、可显式 `"shell": "powershell"`（S8），而 cmd / bash / PowerShell 三者的条件语法与 env var 展开互不兼容（`%USERPROFILE%` / `$USERPROFILE` / `$env:USERPROFILE`）——**唯一三 shell 通行的写法是字面绝对路径 + 双引号**（openpets 的 Windows hook 同样是字面路径）。代价：① 用户目录迁移后路径失效 → doctor 检测 + 重装即修复；② 缺席短路/stdin drain 包装缺失 → 脚本缺席时 `node <missing>` 会向 CC stderr 报一次错（openpets 等价行为，接受；doctor 钉住）。
- hook 条目追加 `"shell": "powershell"`（免 Git for Windows 依赖；pwsh/powershell 系统必有）。
- **killswitch 不依赖 shell 包装**：脚本自身启动即查 `hooks-disabled`（§1.3.2 契约第 3 层），Windows 下同样生效。
- **卸载/重装对已运行 CC 会话的生效时机**（P3-9）：hooks 配置读取时机未实证（逐事件读 vs 会话启动缓存，澄清-4）；保守假设**会话启动缓存**——Unix 包装因逐事件探测文件存在性，卸载后当前会话自愈静默；Windows 字面路径无此自愈，当前会话后续事件将报 `node <missing>` 错误直至新开会话。**卸载后建议新开 CC 会话**（写入 doctor 的卸载提示文案）。
- hooks 目录：`%LOCALAPPDATA%\pulsepet\hooks\`（与 runtime/plugins 平级，既有平台分支复用）。

#### 1.4.5 opencode 接入的 Rust 化（对等收口）

- 状态/安装/卸载逻辑并入 `integrations.rs`，`id="opencode"`：脚本落点/配置查找顺序与 v1 `install.sh` 完全一致（`opencode.json` → `.jsonc` → 新建 `.json`）。
- JSONC 合并 = `opencode-config.mjs` 的 tokenizer + 定位 + 文本插入算法**逐行移植 Rust**（`integrations/opencode_config.rs` 子模块，~250 行 + 单测）：保留注释/尾逗号/未知键，定位失败保守返回原文并报 doctor error。卸载同 v1（移除带标记项）。
- 备份 + 原子写防护两接入统一适用（JSONC 文本合并同样先写 tmp 再 rename）。

### 1.5 Rust 侧变更（事件链路）

| 模块 | 变更 | 说明 |
|---|---|---|
| `session_state.rs` | key 由 `sessionId` 改为 `format!("{agent}:{sessionId}")`（复合字符串） | opencode sessionID（`ses_*`）与 CC UUID 均不含 `:`，无歧义；**合并/回收算法不变**，仅 key 构造点变化。纯内存态无迁移问题（V2-SCOPE §5.5 预期兑现） |
| `session_state.rs` | `SessionRecord` 增 `agent: String` 字段；`display() → DisplayState { kind, agent }`（argmax 时记录归属，**归属来自字段而非反解析 key**） | 供 `pulsepet://state` payload 携带 agent（M6 抢镜的数据通道，M1 前端只存不显示）。注意 `DisplayNotifier` 现按 kind 去重——同 kind 换 agent 不发事件，M1 只存不显示可接受，**M6 消费前需改为 (kind, agent) 去重**。〔修订 2026-08-23（M2 评审 P1-1）：本行去重键改造已由 M6 **拉前至 M2 实施**，见 §2.4/§2.7〕 |
| `http_server.rs` | `agent` 字段从「校验但不消费」升级为**白名单消费**：`opencode` \| `claude-code`，未知值 400 | 防 typo 产生幽灵 session（如 `claude`）；新增 agent 时同步白名单与文档。`StateEvent.agent` 去 `dead_code` |
| `http_server.rs` + `integrations.rs` | 新增 **AgentActivity**（`Mutex<HashMap<agent, Instant>>`，managed state）：事件 apply 时更新 per-agent 最近事件时刻，`integrations_status` 读取为 `lastEventAt` | 数据源不能复用 `SessionRecord.last_event_at`（per-session 且回收即删，30s 后丢失）；「事件正常/最近无事件」新鲜度阈值 **10 分钟**（超阈显示 noEvent）。P2-3 补 |
| `lib.rs`（manage 时序，issue #9 铁律） | `AgentActivity` 与 integrations 相关 state **必须在窗口创建循环之前 `app.manage()`**（与既有 Connection/SessionStateMachine/RemindersState 同段） | issue #9 根因复现防线：Windows 上 WebView2 异步初始化期间前端 invoke 的 IPC 可早于 setup 闭包内后置的 manage 被派发 → `state()` panic 落在不可展开的 WndProc 内 → abort。绝不许「命令首次调用时惰性 manage」写法 |
| `integrations.rs`（线程模型与 panic 纪律，issue #9 同源） | ① 三个命令用 **`async fn`**（跑 tokio worker 线程），node 探测（spawn ~50-200ms）与安装文件 I/O 再经 `spawn_blocking`——不放主线程（同步命令在 Tauri 2 跑主线程 = Windows 消息泵所在，阻塞即 UI 冻结，#9「点击无响应」同源）；② 命令路径**零 panic 纪律**：全部 `Result<T,String>` 错误返回 + `plog!`，禁 `unwrap()/expect()`（panic 落 WndProc 上下文即 abort） | 现有代码库命令全同步但均为 µs-ms 级内存/DB 操作；node spawn 是新量级，必须挪出主线程 |
| `lib.rs` | `make_idle_hook(session_id)` → `make_idle_hook(agent, session_id)`：**仅 `agent=="opencode"` 走 token 汇报**（查 opencode.db）；CC idle M1 无动作（M5 接 transcript 汇报） | 防止 CC 会话 idle 误触发 opencode.db 查询（用 CC session_id 查 opencode 库必然空转，且未来 M5 后口径正确） |
| `lib.rs` | emit `pulsepet://state` payload `{kind, agent}`（向后兼容：前端旧解析只读 kind） | — |
| `integrations.rs`（新） | §1.4.1 命令集 + 安装器实现 + doctor | 命令注册进 `invoke_handler`；安装动作落 `plog!` |

**不改动**：状态优先级合并、瞬态/空闲超时、限流、token 鉴权、`/state` body 契约（`agent` 本就必填）。

### 1.6 前端变更

| 文件 | 变更 |
|---|---|
| `src/lib/adapters/claude-code.ts`（新） | `ClaudeCodeAdapter`：`id:"claude-code"`、`tokenSource:"transcript-incremental"`（M5 兑现）、`iconSet:"claude-code"`、`normalizeRawEvent` 处理 CC hook input JSON（兜底/测试用，与 `claude-code-hook.js` classify 一一对应） |
| `src/lib/http-bridge.ts` | `pulsepet://state` payload 解析增加可选 `agent` 字段 → `petStore.displayAgent`（只存不显示） |
| `src/pet/petStore.ts` | 新增 `displayAgent: string`（默认 `"opencode"`）；无 UI 消费（M6 抢镜/标识用）。已知缺口：`get_display_state` 启动查询只回 kind，启动初期的 displayAgent 可能错值停留至首个事件——M1 只存不显示无害，**M6 消费前需让 get_display_state 带回 agent**。〔修订 2026-08-23（M2 评审 P1-1）：本行 get_display_state 扩展已由 M6 **拉前至 M2 实施**（M2 状态芯片真实消费 agent），见 §2.4/§2.7〕 |
| `src/panel/Settings.tsx` | 新增「接入管理」区（§1.7） |
| `src/lib/i18n.ts` | 新增 `integrations.*` 命名空间键（§1.8） |

### 1.7 接入管理 UI（设置页区块）

```
┌ 接入管理 ────────────────────────────────────────────┐
│ opencode      ● 已安装 · 插件 v0.1.3    [卸载]       │
│   ~/.config/opencode/opencode.json · 事件正常         │
│ claude-code   ○ 未安装                   [安装]      │
│   ~/.claude/settings.json · node 已就绪               │
│   （stale 时：● 需更新 · 脚本已升级   [重新安装]）    │
└──────────────────────────────────────────────────────┘
```

- 每接入一行：状态点（已安装/未安装/需更新/错误）+ 关键路径 + doctor message + 动作按钮（安装/重新安装/卸载）；安装中 disabled + spinner。
- `stale` 判定源：§1.4.3 幂等检测 + hook 文件 md5 与内嵌副本不一致 → 「需更新」（一键重装 = 移除旧条目 + 落新脚本 + 写 canonical 条目）。
- doctor message 组装在 Rust 侧（`i18n.rs` 持有双语模板，对齐 v1 托盘文案模式）；`lastEventAt` 展示「事件正常/最近无事件」运行时活性（数据来自 App 侧内存，无需落盘）。
- M1 不做自动检测后台任务：进入设置页 / `tauri://focus` 时刷新（复用 v0.1.3 四-1 的双触发模式）。

### 1.8 i18n 键（`integrations.*`，zh/en 键集合一致，完备性测试守护）

```
integrations.title            接入管理 / Integrations
integrations.installed        已安装 / Installed
integrations.notInstalled     未安装 / Not installed
integrations.stale            需更新 / Needs update
integrations.error            检测失败 / Check failed
integrations.install          安装 / Install
integrations.reinstall        重新安装 / Reinstall
integrations.uninstall        卸载 / Uninstall
integrations.installing       安装中… / Installing…
integrations.nodeMissing      未检测到 node（CC 接入需要）/ node not found (required for claude-code)
integrations.nodeReady        node 已就绪 / node ready
integrations.lastEvent        事件正常 / Receiving events
integrations.noEvent          最近无事件 / No recent events
integrations.backupNote       修改前自动备份 / Changes are backed up automatically
integrations.opencodeDesc     opencode 插件 / opencode plugin
integrations.claudeDesc       Claude Code hooks / Claude Code hooks
integrations.fail             操作失败：{msg} / Operation failed: {msg}
```

（实施时按实际 message 模板微调增补，保持两语言键集合一致。）

### 1.9 数据库：零迁移

接入状态全部实时探测（配置文件 + 文件系统 + App 内存），不落 `pulsepet.db`——安装状态的事实源是用户目录里的文件本身，DB 缓存只会引入漂移（与 v1「调度器单一数据源」同一哲学）。`app_state` / `plugins` 表不动；M4 迁移 003 不受影响。

### 1.10 测试与验收（M1 Done 标准）

**单测**（`npm test` / `cargo test`，与既有套件同模式）：

| 域 | 用例 |
|---|---|
| `claude-code-hook.js` 纯函数（新 `src/lib/claude-code-hook.test.ts`） | 8 事件 × kind 映射；PreToolUse 工具分类（Edit/Write/MultiEdit/NotebookEdit→editing；Bash+test 正则含 cargo/go test→testing；Bash 普通/Read/Grep→working）；缺 session_id 丢弃；stdin >64KB 拒收；killswitch 跳过；endpoint/token ENOENT → null 快速通道（不 POST）；POST body `{sessionId, kind, agent:"claude-code"}`；全路径 exit 0 不抛错 |
| Rust `integrations.rs`（tempdir 注入） | settings.json 安装：空文件/无 hooks/有用户 hooks 各事件键/已有 stale 条目 → canonical 形态 + 用户条目保留 + 键序不变；**用户条目 + canonical 条目共存 → status 判定 installed**（P1-1）；**多个 pulse-pet 特征条目 / 形态不一致 → stale**；卸载：用户条目保留（含 matcher 组内递归移除）+ 空容器清理 + 幂等（二次卸载 no-op）；解析失败不落笔；备份文件产生 + 旧备份清理（仅留 1 份）+ 原子写；symlink 拒绝；opencode JSONC 合并移植用例 = `opencode-config.test.ts` 全量平移（注释保留/尾逗号/空 plugin/非法输入保守返回） |
| Rust `http_server.rs` | agent 白名单：未知 agent → 400；两合法 agent 各自复合 key 落状态机；**AgentActivity 更新（per-agent lastEventAt）**；**既有集成用例 agent 值修订**（现以 `"agent":"a"` 打 /state 的用例同步改合法值） |
| Rust `session_state.rs` | 同 id 不同 agent 互不覆盖；DisplayState 返回归属 agent；跨 agent 优先级合并（沿用既有断言模式） |
| `idle hook` 分流 | claude-code idle 不查 opencode.db（mock 断言零查询） |

**实机验收**（TC 用例实施时落 `docs/v2/V2-TEST-CASES.md`，编号启用 TC-INT-xx）：

1. 一键安装 claude-code → `settings.json` 出现 8 事件条目 + 备份文件 + `~/.pulsepet/hooks/claude-code-hook.js` md5 与 App 内嵌一致；**安装后用新开 CC 会话验证**（hooks 配置读取时机未实证，保守假设会话启动缓存，澄清-4）；
2. 真实 CC 会话：发消息 → thinking；编辑文件 → editing；跑 npm test → testing；普通命令 → working；制造权限弹窗 → review 姿态，**终端审批通过后经 PostToolUse → working 自愈**（单向语义完整闭环）；结束 → idle；（PostToolUseFailure/StopFailure 目视可选，单测已钉）；
3. opencode 与 CC 并行会话：互不串状态（复合 key）；优先级合并表现与 v1 一致；
4. App 退出后 CC 正常干活无卡顿（零阻塞实证——对 §九 的 CC 侧复验）；CC 未运行时启动 App 无异常；
5. 卸载 → settings.json 恢复（用户 hooks 保留）+ hooks 脚本删除 + doctor 显示未安装；重装幂等；**stale 态构造**（手改 command 一处）→ doctor 显示「需更新」+ 重装修复；
6. killswitch 文件对 CC 接入同样生效；
7. 双语：接入管理区 zh/en 切换即时。

### 1.11 风险与开放问题

| # | 风险/问题 | 处置 |
|---|---|---|
| R1 | `async:true` 在旧版 CC 的行为未知键（strip 或报错）；**`timeout:3` 与 async 的组合语义未实证**（timeout 是否对 async hook 生效/到点强杀——若强杀，node 冷启动 + 慢 POST 可能被 3s 截断丢事件） | timeout:3 兜底（strip→同步+3s 上限；zod schema 观察 non-strict，报错概率低）；实机首装用当前 2.1.240 验证 + **验收 item 4 顺带核对慢 POST 场景**（观察事件是否丢失）；openpets 生产在用，风险接受 |
| R2 | Windows 无 shell 包装：脚本缺席时 node 报错入 CC transcript；无 stdin drain | async:true 弱化等待问题；doctor 钉住缺席态；卸载后建议新开 CC 会话（§1.4.4）；实机验证挂观察项（与 V1-OPEN-ITEMS 一.2 Windows 实机同批） |
| R3 | node 进程冷启动开销（~50-100ms/事件） | async:true 下对 CC 无感；宠物事件延迟可忽略；若未来介意 → petdex 式原生 runner（App 二进制 `--hook` 入口 + 单实例转发）为演进选项，M1 不做 |
| R4 | 用户 settings.json 含注释（若 CC 容忍而用户在用）——**前提未实证（S9）：若 CC 实际不容忍注释，本条场景不存在，可删除** | 结构化改写会丢弃注释——备份先行（丢注释可从备份找回）+ doctor message 提示；openpets 同样行为，跟随参考 |
| R5 | CC 事件字段随版本演进（hook input schema 变化） | 脚本对字段做存在性防御（缺 session_id 丢弃）；doctor 显示最近无事件提示排查 |
| R6 | opencode 与 CC 同名 session_id 撞车 | 理论不可行（`ses_*` vs UUID）；复合 key 天然隔离，单测钉住 |
| R7 | 长回答期 CC 无事件 → 宠物提前回 idle（§1.3.1 已知边界） | 记录不修；CC 无流式 hook，无解也无害 |
| R8 | **一次性进程无跨进程投递排序 → 事件乱序覆盖**：v1 opencode 插件有串行投递队列（P3-②）保证 POST 有序；CC 每事件独立进程，`PreToolUse(editing)` 的 POST 可能晚于 `PostToolUse(working)` 到达（~100ms 冷启动窗口），宠物短暂停留旧瞬态 | CC 事件秒级间隔 + App 侧 30s 瞬态超时兜底使影响短暂自愈，接受不修；M3 工具级气泡落地时若乱序可感知再评估（届时同样 App 侧处理）；与 R3（冷启动）同根 |

### 1.12 不采用记录（含理由，防翻案无据）

| 项 | 理由 |
|---|---|
| CC 原生插件系统（`~/.claude/plugins/` + marketplace） | 演进中的生态机制、沙箱/分发语义未稳；hooks 直装 = 状态可对账（doctor md5/条目检测）、卸载边界干净、与 opencode 接入同模式（V2-SCOPE §3.1 裁定「照抄 opencode-plugin install 模式」）；个人工具不进市场 |
| App 二进制作 hook runner（agentpet 模式） | 需改 main.rs 入口 + 单实例转发链路，M1 最小复杂度不接受（R3 演进选项保留） |
| 文件级客户端节流（openpets 模式） | M1 无 CC 侧气泡，无刷屏面；App 侧幂等覆盖 + 限流已够；M3 气泡时统一 App 侧过滤（V2-SCOPE §3.3-H 倾向） |
| openpets 的项目级 hooks 让位机制 | PulsePet 无项目级安装计划，无双反应问题 |
| Notification 事件 | §1.3.1 已述（噪音源）；未来若需要「CC 等输入提醒」再评估 |
| CC 接入状态落 DB | §1.9 已述（事实源是文件系统，DB 缓存引入漂移） |

### 1.13 评审记录（2026-08-23，reviewer subagent）

> 评审对象：本章节初稿。评审基准：V2-SCOPE §3.1/§4/§5、v1 DESIGN §3、V1-OPEN-ITEMS §八/§九 + 现状源码核对。
> **verdict: NEEDS REVISION**（P1×1 / P2×5 / P3×10 / 澄清×4；无 P0）。
> 处置结论：**全部采纳**——P1/P2 已修订正文对应章节；P3 除 P3-7 部分采纳（验收增补 2 项、备份恢复验证降为记录级）外全部落实；澄清×4 以设计裁定 + 验收/风险补项消化。修订落点见各条「→」。

#### 问题清单（原文收录）与处置

**P1-1（已修，→ §1.4.3）**：§1.4.3 幂等判定「条目数 == 1」与「用户条目永不触碰」自相矛盾——用户自有 hook 条目与 canonical 条目共存时总条目数 > 1，落入 installed/stale/未安装/错误四态之外的未定义区，UI 无法渲染。建议改为「pulse-pet 特征条目数恰为 1 且 command 与 canonical 一致 → installed；> 1 或形态不一致 → stale」，并补「用户条目 + canonical 共存 → installed」单测。

**P2-1（已修，→ §1.4.1）**：V2-SCOPE §3.1 要求显示「版本」状态，`IntegrationStatus` 无 version 字段，UI 示意的「插件 v0.1.3」来源未定义。

**P2-2（已修，→ §1.4.2/§1.3.2）**：「node 缺席 → 对 CC 完全静默」声明与命令行为不符——hook 文件存在而 node 不在 PATH 时 `exec node` 失败，sh 以 127 退出并打印 `node: command not found`，「恒 exit 0」与「完全静默」同时被破。建议条件加 `command -v node`，或收窄声明。

**P2-3（已修，→ §1.5）**：改动清单缺失 `lastEventAt` 的数据来源——现网无 per-agent 最近事件时间跟踪（`SessionRecord.last_event_at` 是 per-session 且回收即删），§1.5 无对应行，实施必漏。

**P2-4（已修，→ §1.11 R8）**：风险清单遗漏「一次性进程无跨进程投递排序 → 事件乱序覆盖」——v1 插件有串行投递队列（P3-②），CC 每事件独立进程，PreToolUse(editing) 的 POST 可能晚于 PostToolUse(working) 到达。

**P2-5（已修，→ §1.4.2）**：§1.4.2 JSONC 示例把 pulse-pet 条目画成 matcher 组包裹形态，与紧随其后的 canonical 定义（数组直接元素）矛盾，误导实施。

**P3（记录级，均落实）**：
1. §1.5 「display()/tick() 算法零改动」与 display 返回类型变化表述冲突；agent 归属建议存 SessionRecord 字段而非反解析 key；DisplayNotifier 按 kind 去重则同 kind 换 agent 不发事件（M1 只存不显示可接受，M6 前需修）→ 已修 §1.5。
2. `get_display_state` 只回 kind，启动时 displayAgent 默认值可能错值（M1 无害）→ 已在 §1.6 标注 M6 前需扩展。
3. 「对齐 v0.1.3 四-4 防污染口径」引用不精确——opencode 侧仅流式心跳事件缺号丢弃，其余落 default；CC 侧全事件丢弃更严 → 已修 §1.3.1 措辞。
4. 测试正则未钉来源，应显式复用 opencode 插件 `TEST_CMD_RE` 同款常量防漂移 → 已修 §1.3.1。
5. 既有 http_server 集成测试以 `"agent":"a"` 打 /state，白名单落地后须同步改 → 已补 §1.10。
6. 备份名含 ISO 时间戳不会自然覆盖，需写明写前清理；卸载对 matcher 组内条目是否递归移除未明说 → 已修 §1.4.3。
7. 验收缺「审批通过后经 PostToolUse→working 自愈」闭环、stale/错误态 UI、备份内容可恢复 → 部分采纳：前两项补入 §1.10；备份恢复验证降为记录级（备份为逐字节复制，内容正确性由「复制 + rename」实现保证，不单列验收项）。
8. §1.8 缺 `nodeReady` 正面键 → 已补。
9. 卸载对已运行 CC 会话的生效时机未交代（Windows 字面路径无 Unix 包装的逐事件自愈）→ 已补 §1.4.4。
10. `nodeAvailable` 缓存失效时机未定义；`integrations` 与 v1 `plugins.rs`（todo 插件机制）命名邻近易混淆 → 已补 §1.4.1（不缓存，每次 doctor 现测）。

**澄清项（裁定消化）**：
1. install.sh/ps1 的 M1 覆盖范围 → **裁定：维持 opencode-only，不扩展**。CC hooks 安装走 App 内置安装器唯一通道（结构化 JSON 合并只在 Rust 实现一份，shell/node 复刻会造成双实现漂移；CC 用户必然装 App）。已在 §1.1 写明。
2. `async:true` 与 `timeout:3` 组合语义（timeout 是否对 async hook 生效/到点强杀）未实证 → 并入 R1 + 实机验收 item 4 顺带核对。
3. R4 前提（CC 是否容忍注释）与 S9 张力 → R4 已标注「前提未实证」。
4. CC hooks 配置读取时机（每事件 vs 会话启动缓存）未实证 → 实机验收 item 2 已写明用**新开会话**验证。

#### 修订汇总（2026-08-23，按评审意见）

§1.1 install.sh 范围澄清；§1.3.1 引用口径修正 + TEST_CMD_RE 复用声明；§1.3.2 静默声明收窄；§1.4.1 IntegrationStatus 增 version/nodeAvailable 探测时机/概念边界；§1.4.2 示例结构修正 + command 加 node 存在性检查；§1.4.3 幂等判定重写 + 备份清理 + 递归卸载口径；§1.4.4 卸载生效时机；§1.5 增 AgentActivity 行 + display 表述修正；§1.6 get_display_state 标注；§1.8 增 nodeReady；§1.10 测试行增补（共存→installed、stale 判定、递归移除、备份清理、AgentActivity、既有用例 agent 值修订）与验收增补（新开会话验证、审批闭环、stale 态构造）；§1.11 R1 补 timeout 交互、R4 标注前提、新增 R8。

**2026-08-23 追加（M2 评审拉前修订，P1-1）**：M2 的 agent 状态芯片真实消费 agent，原「M6 消费前」的两处前置改造——`get_display_state` 返回 `{kind, agent}`（§1.6）与 `DisplayNotifier` 改 `(kind, agent)` 去重（§1.5）——**拉前至 M2 实施**（M2 §2.4/§2.7 承接），两处已加〔修订〕标注；M6 章节届时不再重复。

#### 终审记录（2026-08-23，用户）

- **评审点全部认可**：§1.13 处置的全部 P1/P2/P3/澄清项（含事件映射两处偏差 `PostToolUseFailure→error` / `Stop→idle`、install.sh 维持 opencode-only、async×timeout 并入 R1+验收、R4 前提标注、issue #9/#12 复核修订）——照单定稿。
- **M1 定稿**（M2 同日定稿，见 §2.13 终审记录）。

#### v1 严重缺陷复核记录（2026-08-23，对 GitHub issue #9 / #12 的定向审计）

> 触发：用户要求复核 M1 设计是否复现 v1 两个严重问题（lab 仓库 issue #9 Windows 启动闪退、#12 插件钩子同步阻塞宿主 opencode）。

**#12（阻塞宿主）复核结论：无残留 hole。** §1.3.2 三重防护正是按该失效模式构造——①宿主等待：`async:true`+`timeout:3`（退化同步亦有界）；②热路径网络 I/O：POST 1s 超时、无重试无退避（一次性进程无「退避睡眠」载体，结构性消除）；③缺席≠失败：ENOENT 快速通道 exit 0；④错误不逃逸：包装恒 exit 0 + catch-all + stderr 仅 debug 且净化。R1/R2/R3/R8 挂账全部边界。

**#9（IPC 早于 manage / 主线程阻塞 / 不可展开上下文 panic）复核结论：发现 1 个真实缺口 + 1 个次级隐患，已修 §1.5：**

1. **缺口**：评审修订引入的 `AgentActivity` 是新增 managed state，但未声明 manage 时序——若实施者写成「命令首次调用时惰性 manage」或放在窗口创建循环之后，Settings 页 `integrations_status` 在 Windows 上即复刻 #9（IPC 早于 manage → `state()` panic → WndProc abort）。已补铁律：**窗口创建循环之前 manage**（AGENTS.md 既有约定，issue #9 血泪）。
2. **次级隐患**：`integrations_status` 的 node 探测（spawn ~50-200ms）与安装文件 I/O 若做同步命令则跑主线程（Tauri 2 语义）= Windows 消息泵所在，阻塞即 UI 冻结（#9「点击无响应」同源）；命令内 `unwrap()` panic 同样落在不可展开上下文。已补：命令 `async fn` + `spawn_blocking` + 零 panic 纪律（`Result` + `plog!`）。
3. 其余 #9 相关面核对无虞：M1 不新增窗口（三窗口 create:false + setup 创建的既有模式不变）；HTTP server 先于窗口启动，事件早到只进 Rust 内存状态机，无 panic 面；`get_display_state` 启动查询时 state 已 manage（既有时序）。

---

## 2. M2：前端 UI 基础（设计系统 + 面板壳 + 气泡排队 + tab 注册表）

### 2.0 设计输入与裁定（2026-08-23）

| 决策点 | 裁定 | 备注 |
|---|---|---|
| 设计语言 | **像素暖纸/冷炭双主题**：浅色 = 暖纸感 + 蜜橘强调（样例 a.html）；深色 = **冷炭底 + 项圈青强调**（样例 b-cool.html，2026-08-23 终审替换初版琥珀暖底——用户反馈「黄/暖比重过重，含背景」）；**默认跟随系统** | 三轮样例（a/b/b-rose/b-teal/b-orange/b-cool）归档 `docs/v2/mockups/`，权威样例 = a.html + b-cool.html，其余为过程稿；强调色取自猫精灵项圈像素（`#a0e2e2` 深化） |
| 样式技术 | **手写 CSS + CSS 变量 token**（零第三方依赖，~4MB 安装包亮点保住；现有 805 行 global.css 重构为 token 驱动） | 用户确认 |
| tab 注册表边界 | **核心三**（Token / 提醒（M4 改名定时任务）/ 设置）+ **插件 tab**（消费 plugins 表 `enabled` 列，今日 = Todo） | 用户裁定；核心不含「提醒」的替代案被否（与托盘全局暂停语义重叠易混淆） |
| 禁用语义 | 隐藏 tab + **停派生提醒**（kind='todo' 行不触发）+ 数据保留（DB 不动，重启用即恢复） | 同上裁定 |
| 气泡排队 | **单显示位 + 三级优先级队列**（critical/info/ambient；顶替回队；上限 3；同源合并 10s；悬停层暂停队列） | 用户裁定 |
| 导航形态 | **顶栏 tab**（6 tab × ~90px 在 900px 宽度内宽裕，垂直空间全留给内容） | 用户裁定 |

**范围约束**（V2-SCOPE §3.2 原文落实）：本里程碑只做「壳」——设计系统、面板壳、气泡组件与排队模型、tab 注册表/feature flag；功能增强（Token 看板、工具级气泡）拆入 M3/M4。**提醒 tab 只做轻量翻新**（落新设计系统，表单重做并入 M4）；**不含**宠物素材/动画、烟花引擎、托盘菜单样式（原生）。现有纯函数测试不破坏（bubble 文案/token-chart 等；petStore 单槽位断言将被排队模型**有意取代**，见 §2.6.4）。

**skill 可用性**（SCOPE §5.7 落实）：frontend-design（`.agents/skills/`）与 impeccable（`.opencode/skills/`）本机均已安装，实施阶段可直接使用；本节样例即 frontend-design 流程产物。

### 2.1 目标与范围

- 设计系统：token 层（色板双主题/字版/间距/圆角/阴影）+ 像素语言规则（2px 硬边框、位移阴影、等宽数字）。
- 面板壳重构：顶栏（签名 mini 猫 + 标题 + agent 状态芯片）+ tab 栏 + 内容区栅格。（2026-08-24 修订：mini 猫移除，顶栏 = 标题 + agent 状态芯片两段，见 §2.4 修订）
- 主题机制：设置页「外观」（跟随系统/浅色/深色），即时切换，持久化。
- tab 注册表 + feature flag：核心 tab 静态注册，插件 tab 消费 `plugins_list` 的 `enabled`；设置页「功能管理」区开关。
- 气泡组件重构 + 排队模型：`bubble-queue.ts` 纯函数 + petStore 改造；宠物右键菜单视觉同步翻新。
- 四个 tab 页全部落新 token（轻量翻新，不改信息架构——Token 页 KPI/图表/列表结构留 M3 重做）。

### 2.2 设计语言：像素暖纸 / 像素冷炭

**核心主张**：面板是「宠物世界的仪表台」——视觉语言从像素宠物本身衍生（猫毛白/墨黑线条/蜜橘强调），而非通用后台模板。像素语言的四条硬规则：

1. **2px 实线边框**（墨色），不用 1px 细线；分隔线用 1px 虚线（dashed）。
2. **位移式硬阴影**（`2-3px 位移 + 0 模糊`），不用扩散软阴影——像素游戏 UI 的纸片堆叠感。
3. **直角为主**（radius 0），仅输入框/小徽章用 2px；禁用大圆角卡片。
4. **数字一律等宽字体**（mono token），状态/日期/路径等技术字面量同。

**Token 定义**（`src/styles/tokens.css`，双主题两套值）。**权威规则：下表为唯一实施清单；权威样例 = `a.html`（暖纸浅色）+ `b-cool.html`（冷炭深色·项圈青），两者 `:root` 已与本表同步；其余样例（b.html 琥珀初版 / b-rose / b-teal / b-orange / c）为过程稿，不作实施依据。**

| Token | 暖纸（浅色） | 冷炭（深色） | 用途 |
|---|---|---|---|
| `--bg` | `#f7f4ee` | `#1e2227` | 面板底（暖白纸 / 冷炭，蓝灰倾向） |
| `--surface` | `#fffdf9` | `#252a30` | 卡片/控件面 |
| `--surface-2` | `#f0ece3` | `#2d333b` | 次级面（hover/详情底） |
| `--ink` | `#29241d` | `#e9edf3` | 主文字（墨 / 冷白） |
| `--ink-soft` / `--ink-faint` | `#7a7264` / `#a89f8e` | `#aeb8c4` / `#737e8c` | 次级/弱化文字 |
| `--line` | `#ddd5c6` | `#3b434e` | 边框线 |
| `--accent` | `#d96c2c`（蜜橘） | `#62c6c0`（项圈青，取自猫精灵项圈像素） | 强调色（选中/主按钮/今日高亮） |
| `--accent-ink` | `#b4531c` | `#8fd8d2` | 强调色上的深/浅文字 |
| `--ok` / `--danger` | `#4a7c59` / `#b3402f` | `#82b986` / `#e07263` | 成功/危险（深色 ok 黄绿倾向，与项圈青拉开） |
| `--chart-output/input/cache` | `#d96c2c` / `#9c6b3f` / `#d8ccae`（暖系） | `#62c6c0` / `#7286a5` / `#39414b`（冷系：青/灰蓝/深灰） | 堆叠柱图三段（M3 消费） |
| `--shadow-hard` | `2px 2px 0 var(--line)` | `2px 2px 0 rgba(0,0,0,.5)` | 控件硬阴影 |
| `--shadow-hard-lg` | `3px 3px 0 var(--line)` | `3px 3px 0 rgba(0,0,0,.4)` | 卡片硬阴影（首卡可换 accent 色） |

**宠物世界固定色**（不随主题，定义于 `:root` 主题块之外；气泡/右键菜单专用，§2.3/§2.6.3）：

| Token | 值（两主题同值） | 用途 |
|---|---|---|
| `--pet-world-surface` | `#f6efe2` | 气泡/菜单底（暖白纸片） |
| `--pet-world-line` | `#17130f` | 气泡/菜单 2px 边框（深墨） |
| `--pet-world-shadow` | `2px 2px 0 rgba(23,19,15,.8)` | 气泡/菜单硬阴影 |

字版：UI 文字系统 sans（-apple-system/PingFang SC 栈，现状不变）；数字/技术字面量 `--font-mono`（ui-monospace 栈，现状不变）。字号阶 10（仅图表刻度/详情微标签）/11/12/13/17/22（现状收敛，不再出现 14/15/16/20 混用）。

### 2.3 主题机制（外观选项）

- **UI**：设置页「外观」区，三选一分段控件：跟随系统（默认）/ 浅色 / 深色。
- **解析规则**：手动选择 > 系统偏好（`prefers-color-scheme`）；「跟随系统」时监听系统切换即时生效。
- **实现**：`<html data-theme="light|dark">` + tokens.css 的 `[data-theme="dark"]` 覆盖块；`resolveTheme(preference, systemDark)` 纯函数 + 单测。
- **持久化**：`app_state` 键 `ui.theme`（`"auto"|"light"|"dark"`，缺省 auto）；Rust 侧 `ui_get_theme` / `ui_set_theme` 两命令（照 `ui.language` 模式：持久化 + `ui://theme` 事件广播——**仅 panel 窗消费**，Rust 自身无主题消费面（托盘是原生的））。
- **作用域边界**（重要设计原则）：**主题只作用于 panel 窗口**。宠物窗口的气泡与右键菜单属「宠物世界物件」——固定暖白纸片（`--pet-world-*` token，2px 墨边 + 硬阴影 + 像素尖角，样例所见），**不随主题切换**：它们浮在任意桌面壁纸上，暖白在深浅桌面都可读（两套权威样例均如此呈现；冷炭主题下这抹暖白反而是冷暖对撞的主角），且保持「实体物件」而非「界面元素」的身份。fireworks 窗无文案不涉及。
- **已知体验边界**：`ui_get_theme` 为异步拉取，深色用户冷加载面板时可能先闪一帧浅色（FOUC）——接受（panel 为隐藏/显示复用窗口，仅首次冷加载明显；窗口级初始 background 缓解留待后续按需），记录不修。
- pet 窗口 body 背景保持 transparent（不变）。

### 2.4 面板壳重构

> **修订（2026-08-24，用户裁定）**：顶栏 mini 猫移除（用户目验：左上角"很小的活动的宠物"不需要，去掉）。删 `MiniCat.tsx` 与 `atlas_sheet_png` 命令及其单测（方案 A：唯一消费方消失即回收，不留无消费方代码）；顶栏改为**标题 + agent 状态芯片两段布局**；agent 状态芯片与 P1-1 前置拉前（`get_display_state` 扩展返回 `{kind, agent}` + `DisplayNotifier` `(kind, agent)` 去重）**保留**（芯片为其独立消费方）。下文 mini 猫相关条目（atlas_sheet_png / MiniCat.tsx / 帧映射）按此修订作废。

```
┌────────────────────────────────────────────────────────┐
│ [mini猫] PulsePet · 控制面板        [● claude-code · working] │  ← 顶栏：签名 + 状态芯片
├────────────────────────────────────────────────────────┤
│ [Token] [提醒] [Todo] [设置]                            │  ← tab 栏（2px 底线，激活 tab 橘色硬阴影）
├────────────────────────────────────────────────────────┤
│                                                        │
│  内容区（各 tab 页，卡片 = surface + 2px 墨边 + 硬阴影） │
│                                                        │
└────────────────────────────────────────────────────────┘
```

- **签名元素——mini 猫状态镜像**：顶栏 24×26 像素猫（`image-rendering: pixelated`），用当前 atlas 真实帧镜像 agent 状态（working→running 行跑动帧，error→failed 行等）。实现：
  - Rust 新命令 `atlas_sheet_png() -> Option<String>`：当前 atlas 解码图重编码为 PNG dataURL（image crate 已在依赖内），随 atlas 缓存于 AtlasState（热替换时失效重建）；~30-50KB，一次 IPC。
  - `src/panel/panelStore.ts`（新，zustand）：`{kind, agent}`——panel 初始化时 `get_display_state` 查询 + 监听 `pulsepet://state`（payload 含 agent，M1 已打通）。
  - `MiniCat.tsx`：canvas 24×26，帧行映射复用 `src/lib/sprite.ts`，**统一 120ms 固定步进取帧**（不复用帧时长表的不规则节拍——迷你尺寸只需示意性律动；rAF 节流）；atlas 缺失/加载失败时渲染占位方块（不崩，优雅降级）。
  - **agent 状态芯片**：`● {agent} · {kind}`，等宽字体；`displayAgent` 消费的第一个真实 UI（M6 抢镜在此基础上扩展）。
  - **前置拉前（P1-1 修订）**：`get_display_state` 扩展为返回 `{kind, agent}` + `DisplayNotifier` 去重键改为 `(kind, agent)`——M1 原推迟至 M6 的两处改造**提前到 M2 实施**（M1 §1.5/§1.6 已加修订标注）。不拉前的后果：面板初开只拿到 kind（agent 取默认值错显），且 kind 长期不变时（如整日 idle）事件因按 kind 去重不发，芯片 agent 错值**永久停留**。
- tab 栏：顶栏正下方，激活 tab 带 `box-shadow: 2px 2px 0 var(--accent)` 上浮效果（样例所见）。

### 2.5 tab 注册表 + feature flag

**数据结构**（`src/panel/registry.ts` 新）：

```ts
interface TabDef { id: string; kind: "core" | "plugin"; labelKey: string; render: () => JSX.Element; }
// 核心静态注册（顺序即渲染顺序）：token / reminders / [plugin…] / settings
// 插件 tab：由 plugins_list()（既有命令）返回的 enabled + manifest 的 panelTab 字段
//          （PluginInfo 序列化键为 panel_tab——无 serde rename，前端读 panel_tab）
//          动态生成，render 映射表 { "built-in-todo": Todo } 前端静态绑定（无动态代码加载，v2 无插件 SDK）
```

- **Panel.tsx 改造**：删除硬编码 `TABS`，改为 `useTabs()` hook（静态核心 + `plugins_list` 结果合并，插件按 name 排序插在 reminders 与 settings 之间）；`panel://tab` 直达逻辑保留，目标为禁用 tab 时回退首个可用 tab。
- **plugins_list 既有返回体已含 `enabled`**（`plugins.rs` PluginInfo，v1 起就有——无需改动）。
- **新命令 `plugins_set_enabled(id, enabled)`**（Rust）：写 `plugins.enabled` 列 + **触发提醒调度器 reload**（禁用停派生的执行面，见下）。
- **禁用语义实现**（裁定落实）：
  - 隐藏 tab：注册表过滤（前端）。
  - 停派生提醒（P2-2 修订，过滤位置定案）：调度器加载走**专用过滤查询** `load_active_rules(conn)`（`load_rules` 基础上排除 `kind='todo'` 且源插件 `enabled=0` 的行）；**`reminders_list` 照旧走 `load_rules`**——v1 提醒 tab 本就展示 todo 派生行（含锁定编辑/截止时刻展示），禁用后行**可见但惰性**，前端据注册表已知的插件状态给这些行加「已停用（插件关闭）」徽标（数据保留可见，用户不疑惑「我的 todo 提醒去哪了」）。
  - 数据保留：无任何 DELETE。
- **设置页「功能管理」区**：每个插件一行（**含已停用**——2026-08-24 committer 边界修订：原「每启用插件一行」字面致禁用后行消失无法重启用，与 TC-UI-07-4 矛盾；名称/版本/开关 toggle）；核心三 tab 不在此列（不可关）。
- **正在查看的 tab 被禁用**：立即切到首个可用 tab（注册表 hook 内处理）。

### 2.6 气泡组件重构 + 排队模型

#### 2.6.1 设计（裁定落实）

**单显示位 + 三级优先级队列**：

| 级别 | 来源（M2 时点 / M3/M4 预留） | dwell | 可交互 |
|---|---|---|---|
| `critical` | 提醒气泡（含 todo 派生）/ M4 定时任务结果 | 8s 或点宠物确认（v1 语义不变） | 是（ack → dismissed_via='bubble'） |
| `info` | token 会话汇报 / M3 今日累计追加 / todo 完成庆祝 | 6s | 否 |
| `ambient` | M3 工具级播报（预留，M2 无来源） | 4s | 否 |

规则：

1. **顶替**：高优先级到达立即顶掉显示中的低优先级（被顶者**回队首**，不丢失、不结案）；同级新条目按 FIFO 排队。
2. **同源合并**：同 `source`（见 2.6.2）+ 同级别 10s 内的新条目**原地替换**旧条目（含显示中的——文案刷新、dwell 重计时；也替换队列中的），不产生第二条。**合并仅作用于仍在显示或队列中的条目**（已离场过期的不复活，新条目独立入队）。
3. **队列上限与驱逐**（P2-1 修订；2026-08-24 committer 边界修订：原文「ambient → info 顺序」与「info 永不被驱逐」不可同时成立，定案为仅 ambient 可驱逐）：上限 3 指 **queue 数组长度（不含 current）**；入队/回队导致超限时**仅驱逐 ambient（自队尾优先）**；critical/info 永不被驱逐（queue 全为 critical/info 时允许临时超过 3）；被顶替回队的 ambient 若遇满队驱逐即丢弃（ambient 可丢语义）。提醒记账因此无漏账风险（critical 永不丢）。
4. **悬停层（M3 预留接口）**：悬停宠物今日汇总显示期间**暂停队列推进**（当前条目 dwell 冻结），移开恢复——作为特殊层实现，不进队列。（2026-08-25 R2 committer 定案补充）边界语义：冻结期间新上屏的条目（critical 顶替/队列推进上屏）恢复后 dwell 自恢复时刻按满额计（含冻结段溢记容差，方向为**偏长不偏短**——气泡多显示而非少显示，信息不丢、记账不早，对 M3 悬停层安全）。
5. **去重护栏沿用**：sanitizeBubbleText 净化后为空 → 直接按 auto 结案（v1 语义）。
6. **提醒记账语义不变**：只有最终离开显示（dwell 到期/确认）才回报 dismissed_via；被顶回队期间不结案。**critical 不会被 info/ambient 顶**（只有同级 critical 之间按 FIFO 或同源合并轮换）。已知边界：critical 尚在队列未显示时 App 退出 → 该 reminder_log 的 dismissed_via 永久 NULL（与 v1「显示中退出同样丢回报」同窗，无回归，记录在案）。

#### 2.6.2 数据结构

```ts
interface BubbleItem {
  id: number; text: string; level: "critical" | "info" | "ambient";
  source: string;          // 合并键："reminder:<logId>" | "token-report" | "celebration" | "tool:<tool>" …
  reminder?: { logId: number };  // critical 且来自提醒时携带（ack/记账，v1 字段）
  enqueuedAt: number;      // FIFO 稳定排序 + 合并窗口判定
}
// petStore: { current: BubbleItem | null, queue: BubbleItem[], hoverPaused: boolean }
```

- **`src/lib/bubble-queue.ts`（新，纯函数）**：`enqueue(state, item, now) → state`（含同源合并/上限丢弃/顶替回队）、`expireCurrent(state, now) → {state, dismissed}`（dwell 到期）、`ackCurrent(state) → {state, acked}`、`setHoverPaused(state, paused)`。全部可注入 `now`，vitest 直测。
- **petStore 改造**：`bubble: BubbleState | null` → `bubble: {current, queue}`；`showBubble(text)` → `pushBubble(item)`（桥层构造 source/level）；`showReminderBubble` → critical 路径；计时器从单一 8s 改为按 current.level 的 dwell；dwell 冻结支持（悬停层）。
- **桥层适配**：`http-bridge.ts` 的 `pulsepet://bubble` → info 级 source="token-report"；`reminder-bridge.ts` 的 `reminder://trigger` → critical（source="reminder:<logId>"，**`planReminderActions` 的烟花叠加编排原样保留**——「特效只叠加、不替代气泡」原则不变）；`todo-bridge.ts` 的 `todo://completed` → info 级 source="celebration"（waving 庆祝逻辑不动，P2-4 补）；M3/M4 新来源届时接入，不动队列内核。

#### 2.6.3 视觉（两处，固定暖白「宠物世界」配色，不随主题）

- 气泡：暖白底 + 2px 墨边 + `2px 2px 0` 硬阴影 + 像素尖角（45° 旋转小方块，样例所见）；critical 级左侧 4px 蜜橘色条区分（可交互暗示）；单行省略（现状净化约束不变）。
- 右键菜单：同语言翻新（暖白 + 2px 墨边 + 硬阴影 + 直角项），行为零改动（clamp/关闭逻辑保留）。

#### 2.6.4 测试迁移（有意取代，非破坏）

- 保留：`bubble.ts` 纯函数测试（sanitizeBubbleText/时长常量）与插件侧 `plugin-hook.test.ts` 的 pickBubble 用例各自不动（P3-1 修正归属）。
- 取代：`petStore.test.ts` 中单槽位断言（顶替即丢、8s 恒定）改写为排队语义（顶替回队、分级 dwell）——V2-SCOPE「不破坏」的边界是纯函数文案与 token-chart；petStore 行为测试随设计演进属预期修订，修订清单在设计内明示。
- 新增：`bubble-queue.test.ts` 全覆盖（合并/上限/顶替/冻结/记账时机）。

### 2.7 Rust 侧变更（汇总）

| 模块 | 变更 |
|---|---|
| `i18n.rs` 或新 `theme.rs` | `ui_get_theme` / `ui_set_theme`（app_state `ui.theme` + `ui://theme` 广播；照 ui.language 模式，无 Rust 消费面） |
| `plugins.rs` | 新命令 `plugins_set_enabled(id, enabled)`（写列 + 调 reminder_scheduler reload）；`plugins_list` 已含 enabled 无需改 |
| `reminder_scheduler.rs` | 新增 `load_active_rules`（调度器专用过滤：排除 kind='todo' 且源插件 disabled 的行；`reminders_list` 的 `load_rules` 不动，P2-2 定案）；reload 既有通道复用 |
| `atlas.rs` | 新命令 `atlas_sheet_png`（dataURL，AtlasState 内缓存，热替换失效；**async fn + spawn_blocking**——1536×1872 重编码 ~50-200ms 不占主线程，沿 M1 §1.5 线程纪律）——**2026-08-24 修订：随 mini 猫移除作废（见 §2.4 修订）** |
| `http_server.rs` + `lib.rs` | **M1 前置拉前（P1-1）**：`get_display_state` 返回 `{kind, agent}`；`DisplayNotifier` 去重键改 `(kind, agent)`（M1 §1.5/§1.6 已加修订标注） |
| `lib.rs` | 命令注册；**无新 managed state**（theme 走 app_state 读写，AtlasState 复用）——issue #9 铁律自动满足 |

### 2.8 前端文件变更（汇总）

| 文件 | 变更 |
|---|---|
| `styles/tokens.css`（新） | 双主题 token 全量定义（含 `--pet-world-*` 固定色组）；`global.css` 重构为消费 token 的组件层（BEM 命名不变，值全部 token 化——**pet 窗气泡/右键菜单除外**，其「宠物世界」色统一走 `--pet-world-*`，不随 data-theme，P2-3 修订） |
| `panel/registry.ts` / `panelStore.ts` / `MiniCat.tsx`（新） | §2.4/2.5（2026-08-24 修订：MiniCat.tsx 随 mini 猫移除删除；panelStore 保留供 agent 芯片） |
| `Panel.tsx` | 注册表驱动 + header 重构 + 主题 data-theme 挂载点 |
| `lib/bubble-queue.ts`（新）+ `pet/petStore.ts` + `pet/Bubble.tsx` + `lib/http-bridge.ts` + `lib/reminder-bridge.ts` + `lib/todo-bridge.ts` | §2.6（todo-bridge 的完成庆祝调用迁移至 pushBubble，P2-4 补） |
| `pet/PetMenu.tsx` + `lib/pet-menu.ts` | 菜单视觉翻新（行为不变） |
| `panel/TokenStats.tsx` / `Reminders.tsx` / `plugins/Todo.tsx` | 轻量翻新（token 化 + 字号阶收敛；信息架构不动） |
| `panel/Settings.tsx` | 新增「外观」区 + 「功能管理」区（M1「接入管理」区已在，统一翻新） |
| `lib/i18n.ts` | 新键：`settings.theme*`（外观/跟随系统/浅色/深色/切换失败）、`plugins.manage*`（功能管理/开关标签/已停用徽标）、`panel.statusAria`（状态芯片 aria-label——agent/kind 字面量按约定不翻译，P3-5 修订） |

### 2.9 数据库：零迁移

`ui.theme` 落既有 `app_state` 键值表；`plugins.enabled` 列 v1 已建。无 schema 变更（M4 迁移 003 不受影响）。

### 2.10 测试与验收（M2 Done 标准）

**单测**：`bubble-queue.test.ts`（合并/合并仅限在显在队/上限与驱逐序（ambient 先逐出、critical/info 永不、全满时允许超 3）/顶替回队/被顶 ambient 满队即丢/冻结/记账时机/净化空结案）；`resolveTheme` 纯函数（auto+系统深浅/手动覆盖）；`registry` 逻辑（禁用过滤/回退/插件插位/panel_tab 键读取）；i18n 字典完备性（新键 zh/en 一致）；既有 `bubble.ts`/`token-chart` 套件不红；`petStore.test.ts` 排队语义改写；Rust：`plugins_set_enabled`（禁用后 `load_active_rules` 过滤派生行、`reminders_list` 仍全量、重启用恢复）、`ui_get_theme`/`ui_set_theme`（缺省 auto、非法值拒绝/回退、写入后 `ui://theme` 广播断言，P2-6 补）、`atlas_sheet_png`（非空 dataURL/热替换失效）——**2026-08-24 修订：随 mini 猫移除作废**。

**实机验收**（TC-UI-xx，实施时落 V2-TEST-CASES.md）：

1. 主题：三档切换即时生效（panel 全控件跟随）；「跟随系统」下改系统外观即时联动；重启保留；**气泡/右键菜单不随主题变**（暖白恒定）；
2. mini 猫：随 agent 状态切行（working 跑动/error 倒下）；atlas 热替换后 mini 猫同步换装；atlas 损坏回退时 mini 猫降级占位不崩；状态芯片 agent 正确跟随（含 kind 不变期 agent 切换——验证 (kind,agent) 去重拉前生效）；**（2026-08-24 修订：mini 猫移除，本项仅保留「状态芯片 agent 正确跟随（含 (kind,agent) 去重拉前生效）」半句验收）**；
3. tab 注册表：禁用 Todo → tab 消失 + 当前正查看时自动切走 + 派生提醒不再触发（到期无气泡）+ **提醒列表中 todo 派生行显示「已停用（插件关闭）」徽标** + 数据完好；重启用全恢复；`panel://tab` 直达禁用 tab 回退首个；
4. 气泡排队：提醒显示中收到 token 汇报 → 不顶替（critical 优先）；token 汇报显示中提醒到达 → 立即顶替、汇报回队首随后重现；同源 10s 合并；队列上限与驱逐（M2 无 ambient 真实来源，用测试驱动器验证或留 M3 补验）；确认记账 dismissed_via 语义不变；
5. 四 tab 页视觉落新系统（对比样例 a/b 目验）；深色下图表/表格可读性目验；硬编码色清零核对（grep `#[0-9a-f]{3,8}` 与 `rgba(`，未列入 token 的即清理对象）。

### 2.11 风险与开放问题

| # | 风险/问题 | 处置 |
|---|---|---|
| R1 | `atlas_sheet_png` 大 dataURL IPC（~30-50KB base64）一次开销 | 启动/换装各一次，面板显示时才拉取（懒加载）；可接受；如实测卡顿改 `convertFileSrc` 临时文件方案（2026-08-24 修订：随 mini 猫移除，风险不再存在） |
| R2 | 深色主题下既有 Token 图表配色可读性（旧图表色硬编码） | M2 轻翻新时图表色 token 化（三段 chart token）；精细打磨在 M3（柱图本就要重做） |
| R3 | 悬停层（M3）与 dwell 冻结接口 M2 先行实现但无消费方 | 接口极小（setHoverPaused），测试钉住；M3 直接用 |
| R4 | `plugins_set_enabled` 与调度器 reload 的并发（reload 时正在触发） | 复用 v1 既有 reload 通道语义（增删改同样场景），无新竞态面 |
| R5 | 主题切换时 panel 内 canvas（mini 猫/图表）重绘 | data-theme 变化触发 React 重渲染自然重绘；无缓存像素需要失效（2026-08-24 修订：mini 猫移除后仅剩图表） |
| R6 | petStore 排队改造回归风险（M3~M6 都压在它上面） | bubble-queue 纯函数 100% 覆盖 + 桥层适配层最小化；M2 验收 item 4 全链路目验；已知边界（critical 在队未显示时退出 → dismissed_via NULL）见 §2.6.1 规则 6 |
| R7 | **805 行 global.css 重构无自动化视觉回归手段**（纯函数测试不覆盖 CSS） | 验收 item 5 目验 + 轻翻新不换信息架构以降低面；重点核对深色下所有卡片/表格/输入控件/滚动条/hover/disabled 态 |
| R8 | **双主题下硬编码颜色清理清单**（漏一处 = 深色下白底刺眼） | 以 grep 色值字面量（`#[0-9a-f]{3,8}` / `rgba(`）为准绳做全量清单，未列入 token 表的即清理对象；验收 item 5 含核对步骤 |
| R9 | 深色用户冷加载面板 FOUC（先闪一帧浅色） | 接受（§2.3 已记录）；仅首次冷加载明显，后续窗口复用无感 |

### 2.12 不采用记录

| 项 | 理由 |
|---|---|
| Tailwind / headless 组件库 | 用户裁定手写 CSS + token；包体积敏感、组件少、风格强定制（像素语言）三重因素 |
| 深色主题暖棕底 + 琥珀强调（初版 B，`b.html`） | **用户终审否决（2026-08-23）**：「整个页面黄色的比重还是太重了，包括背景色」——暖炭底/暖表面/琥珀强调全族替换为冷炭底 + 项圈青（`b-cool.html`）；过程稿留档不改 |
| 气泡双槽堆叠（petdex 邮箱式） | 220px 窗口高度紧张；单显示位 + 队列已满足信息不丢；「一次说一件事」更像陪伴宠物 |
| 侧栏图标导航 / 溢出折叠 | 顶栏 6 tab 宽裕（用户裁定）；折叠属过度设计 |
| 气泡/菜单随主题切换 | 「宠物世界物件」原则（§2.3）：浮在任意桌面上，暖白恒定可读，保持实体感 |
| 主题三窗联动（pet/fireworks 也切） | pet 窗只有气泡/菜单（固定配色）；fireworks 无文案——无消费面 |
| 插件 tab 动态代码加载 | v2 无插件 SDK（V2-SCOPE §4 裁定）；前端静态 render 映射表够用 |
| 设置页放「重置所有数据」等新功能 | 超出 M2 壳范围，未在 SCOPE 内 |

### 2.13 评审记录（2026-08-23，reviewer subagent）

> 评审对象：本章节初稿。评审基准：V2-SCOPE §3.2/§5.7/§5.9、v1 DESIGN/V1-OPEN-ITEMS §8.4、M1 章节（上游）、AGENTS.md + 仓库现状源码逐条核对（含 mockups 样例）。
> **verdict: NEEDS REVISION**（P1×2 / P2×6 / P3×11 / 澄清×2；无 P0）。
> 处置结论：**全部采纳**——P1/P2 全部修订正文；P3 全部落实（P3-9 以「M2 沿 M1 纪律」方式消化：atlas_sheet_png 改 async + spawn_blocking）；澄清-1 允许（按文首约定以「修订标注」改 M1，已加）、澄清-2 由设计侧裁定（调度器专用过滤 + 列表可见惰性 + 徽标）。评审人总体评价：「M2 章节整体扎实……与 SCOPE §3.2 范围切分准确、对仓库现状的声明基本属实、issue #9 铁律经代码核对成立、atlas_sheet_png 估算与实测吻合」。

#### 问题清单（原文收录）与处置

**P1-1（已修，→ §2.4/§2.7 + M1 修订标注）**：agent 状态芯片消费了 M1 明确推迟到 M6 的两个前置（`get_display_state` 只回 kind；`DisplayNotifier` 按 kind 去重、同 kind 换 agent 不发事件）——芯片 agent 值会在 kind 不变期永久错显。修法 (a)：两处改造拉前至 M2。

**P1-2（已修，→ §2.2 + mockups 同步）**：token 表与自称权威来源的样例 a/b.html 存在三处不一致（`--accent-ink` vs 样例 `--accent-deep`；`--font-mono` vs 样例 `--mono`；`--danger`/`--shadow-hard(-lg)` 表有样例无、气泡阴影样例有表无）。修法：样例 `:root` 已与本表同步（改名 + 补齐 + 气泡统一 `--pet-world-*`，视觉不变）；权威规则改为「本表为唯一实施清单，冲突以表为准」。

**P2-1（已修，→ §2.6.1 规则 3）**：队列上限与顶替回队交互未定义（上限是否含显示位、第 4 条 critical 到达丢不丢、被顶 ambient 回队遇满队如何）。修法：上限指 queue 数组不含 current；驱逐序 ambient→info 从队尾；critical/info 永不驱逐（允许超 3）；ambient 满队即丢。

**P2-2（已修，→ §2.5 + §2.10 验收 3）**：禁用过滤的实现位置（load_rules 为调度器与 reminders_list 共用）决定列表表现，未交代。裁定：调度器专用 `load_active_rules` 过滤；列表照旧全量 + 「已停用（插件关闭）」徽标。

**P2-3（已修，→ §2.8）**：「值全部 token 化」与「宠物世界固定色」原则冲突。修法：§2.8 加例外条款 + `--pet-world-*` token 收敛。

**P2-4（已修，→ §2.6.2/§2.8）**：桥层适配漏 todo-bridge（todo 完成庆祝列在 info 来源但清单缺席，实施必漏）。补 source="celebration" 迁移行。

**P2-5（已修，→ §2.11 R7/R8）**：风险清单缺 805 行 CSS 重构回归与硬编码色清理两大类。补 R7（目验 + 降面）/R8（grep 清单准绳）。

**P2-6（已修，→ §2.10）**：测试清单缺主题机制 Rust 侧单测（缺省/非法值/广播）。补。

**P3（记录级，均落实）**：① §2.6.4 pickBubble 归属修正（在 plugin-hook.test.ts 非 bubble.ts）；② reminder-bridge 烟花叠加分支显式声明保留；③ manifest.panelTab 序列化键实为 panel_tab，前端读键已写明；④ 字号阶补 10px（仅图表刻度/微标签）；⑤ panel.agent.* 键改为单个 panel.statusAria（agent/kind 不翻译）；⑥ MiniCat 定案 120ms 固定步进（不复用帧时长表）；⑦ FOUC 记录（§2.3 + R9）；⑧ 合并仅作用于在显在队条目（§2.6.1 规则 2）；⑨ atlas_sheet_png 线程纪律沿 M1（async + spawn_blocking，§2.7）；⑩ skill 可用性确认（§2.0：本机均已安装）；⑪ critical 在队未显示时退出的记账 NULL 边界（§2.6.1 规则 6 + R6）。

**澄清项裁定**：① 允许以修订标注方式触碰 M1 章节（文首约定明示「勘误以修订标注」）——M1 §1.5/§1.6 两处已加「拉前至 M2」标注；② 列表策略见 P2-2。

#### 终审记录（2026-08-23，用户）

- **评审点全部认可**：§2.13 处置的全部 P1/P2/P3/澄清项（含 P2-2「可见但惰性 + 已停用徽标」、气泡参数 dwell 8/6/4s / 合并窗 10s / 队列上限 3、mini 猫 + agent 芯片签名元素、install.sh 不扩展 CC、M1 前置拉前）——照单定稿。
- **设计语言修订**：深色主题按用户反馈去暖化——初版暖炭底 + 琥珀强调整体否决（黄/暖比重过重，含背景），替换为**冷炭底（#1e2227 系）+ 项圈青强调（#62c6c0，取自猫精灵项圈像素）**；浅色主题保持暖纸感（用户裁定不同步冷化）；默认主题 = **跟随系统**。§2.0/§2.2 token 表已按此更新，权威样例 = `a.html` + `b-cool.html`（含四色切换器过程稿）。
- **M2 定稿**。M1 同日定稿（见 §1.13 终审记录）。

#### 修订汇总（2026-08-23，按评审意见）

§2.0 skill 可用性；§2.2 权威规则改表为准 + `--pet-world-*` 组 + 10px 字阶；§2.3 FOUC 记录；§2.4 前置拉前声明 + MiniCat 120ms 定案；§2.5 panel_tab 键名 + 过滤位置定案 + 徽标；§2.6.1 驱逐规则（规则 3 重写）+ 合并作用域 + 退出记账边界；§2.6.2 todo-bridge + 烟花保留声明；§2.6.4 归属修正；§2.7 拉前两行 + atlas_sheet_png 线程纪律 + load_active_rules；§2.8 pet-world 例外 + todo-bridge + statusAria；§2.10 驱逐/主题/徽标用例与验收增补；§2.11 R7/R8/R9。样例 mockups a/b.html `:root` 同步（改名 accent-ink/font-mono、补 danger/shadow/pet-world、气泡统一 pet-world token，视觉不变）。M1 §1.5/§1.6 加修订标注（前置拉前至 M2）。

## 3. M3：Token 看板增强 + 工具级气泡

### 3.0 Spike 结论（2026-08-23，本机真实 opencode.db 实测）

> 数据源：`~/.local/share/opencode/opencode.db`（138 session，WAL 只读连接）。A 项 SQL 设计的证据基线。

| # | 事实 | 数据 | 设计含义 |
|---|---|---|---|
| S1 | session 表列：`title` / `model` / `directory` 均真实存在（v1 白名单只锁了 10 列） | `PRAGMA table_info` | 白名单补 `model`、`title`；project 表路径列名为 **`worktree`**（非 path） |
| S2 | model 列为 JSON `{id, providerID, variant}`，近 30 天 15 种组合 → 按 `$.id` 归并 8 种 | `json_extract` GROUP | SCOPE「仅按模型 id 归并」可行；`deepseek-v4-flash@max` 带后缀 id 实存（2 条），按原样归并（SCOPE 已裁定） |
| S3 | model NULL 率 = 0（全表/近 30 天均 0） | `SUM(model IS NULL)` | 防御性回退仍设计（「未知模型」合并），但实际不触发 |
| S4 | `probe-model`（providerID=mock）4 条，**token 全 0 / cost 0** | 聚合查询 | **裁定过滤**（用户 2026-08-23）：`WHERE COALESCE(json_extract(model,'$.providerID'),'') <> 'mock'`，统计零影响、模型列表更干净 |
| S5 | title 质量：空 0 条；`New session*` 回退 11/138（8%） | 采样近 10 条全部语义良好（中文标题） | 首列直接用 title；回退行按原样显示（SCOPE G 裁定）；NULL 防御回退 session id 前缀 |
| S6 | 项目分布（近 30 天窗口，123 session）：lab 107（87%）、global（`/`）12、其余 4 | JOIN project | 砍饼图依据坐实（SCOPE F 的 ~97% 为早期 token 加权观测，**权威口径以本 spike 的 session 数 87% 为准**）；global → 专属回退标签（非哈希） |
| S7 | 今日量级：6 会话 / in 2.1M / out 133K / cacheRead 39.7M / $0.163 | localtime 0 点起 | 「今日累计 T」格式参考：总量 ~42M |
| S8 | rusqlite 0.40 bundled（SQLite ≥3.45，JSON1 内置）；chrono 已在依赖 | Cargo.toml | `json_extract` 可直接用，零新增依赖 |

### 3.1 目标与范围

V2-SCOPE §3.3 A~H 全项落地，落 M2 设计系统与气泡排队模型之上。裁定汇总：

| 项 | 裁定 |
|---|---|
| detail 协议 | **模板 ID 协议**（用户 2026-08-23）：插件只发 `tplId:param`，App 白名单校验 + i18n 渲染 |
| probe-model | 过滤 mock（S4） |
| 工具气泡 agent 范围 | **仅 opencode**（用户裁定）；CC hook 携带 detail 留 M5（已知不一致边界，记录在案） |
| 其余 | SCOPE 已裁定项照单：默认今日、reasoning 不计汇总、砍饼图、模型筛选仅作用柱图、KPI 首卡总量、会话列表改造 |

**不含**：CC transcript 数据（M5）、agent 筛选实现（M5——UI 预留位具体落 §3.5）、M4 定时任务。

### 3.2 数据层（Rust `token_stats.rs`）

**TokenRow 扩展**（serde 同步）：

```rust
pub struct TokenRow {
    // …既有 10 字段不变…
    pub model_id: Option<String>,      // json_extract(model,'$.id')；NULL/解析失败 → None（前端「未知模型」合并）
    pub project_name: Option<String>,  // basename(project.worktree)；global（"/"）或 JOIN 未命中 → None（前端回退标签）
    pub title: Option<String>,         // 会话标题（by-session 独有；聚合行 None）
}
```

**查询改造**：

| 查询 | 变更 |
|---|---|
| `query_by_session` | SELECT 增 `json_extract(model,'$.id') AS model_id, title`；`LEFT JOIN project ON session.project_id = project.id` 增 `project.worktree`，**basename 在 Rust 侧切**（`Path::file_name`，跨平台稳妥；`/` → None）；ORDER BY 不变 |
| `query_grouped`（day/week） | `GROUP BY day_expr, model_id`（替换原 `day, project_id`——饼图已砍、KPI 由前端跨行 SUM 不受分组影响，模型筛选需要 per-day-per-model 数据）；SELECT 增 model_id；**project_id 从聚合行移除** |
| `query_by_range` | 同 grouped 口径（GROUP BY model_id；SCOPE E 的筛选作用域仅柱图，range 维度无柱图但口径统一） |
| 全部查询（含 `query_current_session` idle 汇报链路） | 追加 `AND COALESCE(json_extract(model,'$.providerID'),'') <> 'mock'`（S4 裁定；mock 行 token 本为 0，统一口径防漂移） |
| `SESSION_REQUIRED_COLUMNS` | + `model`、`title`（缺失 → 既有 schema-mismatch 错误码路径） |

> **§14 修订（2026-08-29，V2-OPEN-ITEMS §十四）**：day/week/range/today 四类聚合已**下沉 message 级**——`FROM message`、按消息 `time_created` 归天/过滤（**day 归属 = 消息产生时间**，跨天会话每天各得各的；原 session 级行为整会话归最后活跃日且首日贡献消失）；五维/cost/model 从 `data` JSON 提取（`$.tokens.{input,output,reasoning,cache.read,cache.write}` / `$.cost` / `$.modelID`，会话中途换模型也能分对）；行筛选 `json_valid(data) AND $.tokens IS NOT NULL`（实测 user 行 0% 带 tokens——等价只取 assistant 行，防零值组）+ mock 过滤（`$.providerID`）。`MESSAGE_REQUIRED_COLUMNS`（id/session_id/time_created/data）入 open_checked 白名单，缺表/缺列 → schema-mismatch（用户裁定：严格报错不静默口径漂移）。by-session 视图与气泡「本期会话」保持 session 表会话累计语义不动。

project 表缺失的场景不做白名单防御（LEFT JOIN 对不存在表直接 SQL 报错 → 既有 query 错误码）；个人工具 opencode 库长期有 project 表，记录于风险 R2。

**新命令 `token_stats_today`**：

```rust
#[tauri::command]  // async fn + spawn_blocking（沿 M1 §1.5 线程纪律；sqlite 查询 ~ms 级但保持纪律）
pub async fn token_stats_today() -> Result<TodayStats, String>
// TodayStats { input: i64, output: i64, cache_read: i64, cost: f64 }
// from = chrono::Local 现在 0 点，to = now；复用 detect/open/check_session_schema/
// mock 过滤全套错误处理（no-database/legacy-storage/schema-mismatch 原样透传）
```

三层快捷查看（§3.4）共享此命令，单一数据源。

**idle 汇报追加今日累计**：`build_idle_report` 保持本期数字逻辑不变；`make_idle_hook`（lib.rs）在气泡文案末尾追加 ` · 今日 {format_tokens_k(total)}`——**total = in + out + cache_read**（reasoning 不计，对齐 SCOPE D 与 TodayStats 口径）；同连接顺带 SUM 当日聚合（一次查询，同连接复用）；新鲜度护栏 60s 口径不变；今日聚合失败（如跨午夜边界竞态）时静默省略追加段（本期数字照常显示）。**仅 `agent=="opencode"`**（M1 已分流的 idle hook 内实现）。追加段文案模板入 `i18n.rs`（`token_report_today` 后缀，zh/en 键集合一致，zh 与既有汇报措辞钉住逐字一致——M8 约定沿用）。**§十二 F1 修订（2026-08-28）**：本期文案改单总量口径——「本次会话消耗 token {total}」（total = in+out+cache_read，与 KPI 同口径），input/output/cost 明细模板与 CC 无 cost 双模板（S4）收敛为统一 `token_report(total)`；cost 段去除、`format_cost_usd` 清退（见 V2-OPEN-ITEMS §十二 F1）。

### 3.3 今日 preset 与面板默认

- `RangePreset` 增 `"today"`；`rangeForPreset("today")` → from = 本地今天 0 点、to = now。
- 面板默认选中 `"today"`（原 `"7d"`）；分段控件首位插入「今日」。
- 悬停层/右键菜单（§3.4）不走 preset（走 `token_stats_today`），但数值口径一致（同 0 点起点 + mock 过滤）。

### 3.4 三层快捷查看今日 token

> **〔修订 2026-08-25 用户裁定〕主动层 ②（悬停宠物 500ms 今日汇总卡）实际体感差，已删除**——三层降为两层（① 被动层 + ③ 入口层）；HoverToday 组件及 PetCanvas 悬停接线不保留；`token_stats_today` 与 pet 桥层 30s 缓存仍由入口层 ③ 独享消费；M2 `setHoverPaused` 冻结接口为 M2 交付物保留（无运行时消费方，测试保留）。下表 ② 行与「② 悬停层细节」段留档原貌不作实施依据。

| 层 | 触发 | 呈现 | 数据 |
|---|---|---|---|
| ① 被动层 | 会话 idle + 有用量（既有护栏） | 既有 token 汇报气泡（M2 info 级 source="token-report"）末尾追加 ` · 今日 42M` | idle hook 追加（§3.2） |
| ~~② 主动层~~〔已移除〕 | ~~悬停宠物 **500ms**（非穿透态）~~ | ~~悬停层卡片~~ | ~~`token_stats_today`，pet 桥层缓存 30s~~（现由 ③ 独享） |
| ③ 入口层 | 宠物右键菜单 | 信息项「今日 token：42M」（数据未到 `…`、无库/错误 `—`）；点击 → `openPanel("token")`（默认即今日，无缝衔接） | 菜单打开时 invoke + 30s 缓存 |

**② 悬停层细节**（M2 排队模型对接）〔**已移除 2026-08-25，本段留档原貌不作实施依据**〕：

- PetCanvas `onPointerEnter` → 500ms 定时器到点显示；`onPointerLeave` → **立即**取消定时器/隐藏（SCOPE §5.10 防抖口径：进入防抖、离开即时）。
- 显示期间调 M2 `setHoverPaused(true)`：队列推进暂停、当前气泡 dwell 冻结；悬停层**视觉替换**当前气泡位置渲染（底层 current 不销毁），移开后恢复显示并续走剩余 dwell。
- **卡片落点固定**：与气泡同位（宠物上方贴顶居中），current 为 null 时同位；卡片为多行（总量大字 + 三行明细）。
- **与右键菜单互斥（后开者胜）**：悬停显示中右键 → 菜单打开且悬停卡隐藏（**菜单打开即 `setHoverPaused(false)` 解除冻结**，队列恢复推进——N4 定案）；菜单打开中悬停 500ms 到点 → 不显示（pointer 已被菜单捕获）。220×220 窗口内两者永不重叠。
- **穿透切换兜底（N14）**：悬停卡组件订阅既有 `pulsepet://pass-through` 广播（pet 桥已订阅该事件）——穿透开启（经热键/托盘，webview 收不到后续 pointer 事件、无 leave 信号）即**取消 500ms 计时器/隐藏卡片/`setHoverPaused(false)`**（对齐 PetMenu 的 `passThrough → return null` 先例）；切回非穿透不自动恢复（重新进入悬停再显）。
- **全零数据**（in/out/cacheRead 均 0，如刚过午夜）：照常显示卡片，数字为 0（诚实呈现，不伪装成错误态）。
- 错误（no-database 等）：悬停层显示一行「暂无数据」（i18n），不闪错误码。
- 已知限制（SCOPE §3.3 C 原文）：穿透模式下 pointer 事件透出，**②③ 均不可达**（仅 ① 被动层与面板可用）；不改穿透语义。

**③ 右键菜单扩展**：`buildPetMenuItems` 签名扩展为 `(passThrough, todayToken: TodayTokenState, lang?)`（`TodayTokenState = {status:"loading"} | {status:"ok", text:string} | {status:"error"}`）→ 增第 0 项 `{ id: "today-token", label: t("menu.todayToken", {v}) }`（v = `…`/`42M`/`—` 三态，**42M 式文案由桥层用既有 `formatTokens` 生成（与 idle 追加段 `format_tokens_k` 同口径）**——N11）；`PetMenuAction` 联合类型增 `"today-token"`；`PetMenu.tsx` `act()` 增分支 → `openPanel("token")`。信息项与行为项混合（点击也执行动作），视觉上加分隔线样式区分。菜单 clamp 逻辑不动（现状 3 项 + 新 1 项 = **4 项**；menuH 估值 104→130 同步调整）。

### 3.5 堆叠柱状图 + 模型筛选（Token 页主区）

- **`computeStackedBars(rows, selectedModels, opts)` 纯函数**（新，`token-chart.ts`；删除 `computeBars`/`pieSlices` 及其测试——柱图与饼图唯一消费方均在本页）：
  - 输入 day/week 聚合行（含 model_id）+ 勾选模型集合；输出每日一柱、柱内三段自底向上 **output → input → cache read**（SCOPE D 裁定；reasoning 不参与汇总口径）；
  - 未勾选模型的行直接剔除后聚合；selectedModels 为空集 → 空态文案（不渲染柱）；
  - **opts 预留 `agentFilter?: ReadonlySet<string>` 参数位**（M3 声明类型不传值——M5 接入时填实现，签名与调用点均不变；N3 措辞修正，弃「never 收窄」说法）。
- **agent 筛选 UI 预留位（SCOPE H「避免二次返工」的落实）**：筛选 chip 行设计为**可容纳多组筛选的容器**（`<div class="filter-row">` 内模型组为第一组）；M5 时 agent 组作为第二组 chip 插入同一容器（数据维度到来前不渲染空组、不留空位）——布局与组件结构按两组设计，M3 只渲染模型组。〔注：M5 实施时（2026-08-27 R2 修订）agent 筛选最终改为标题右侧 tab 单选 + 模型复选联动，未按"第二组 chip"形态落地；本预留位由 `computeStackedBars`/`computeModelChips` 的 agentFilter 参数位与 filter-row 容器继续承载，见 §5.6 修订注记。〕
- **渲染**：SVG/DOM 三段矩形（色值 = M2 `--chart-output/input/cache` token；柱内堆叠顺序维持自底向上 output → input → cache read 不变）；悬浮 **HTML tooltip**（日期 + 三项数值 + 占比 + 总量；三项数值行**自上而下 cache read → input → output**〔用户 2026-08-25 裁定修订，与柱内堆叠顺序独立〕）；图例三项（仅说明，不可交互——避免与模型筛选语义混淆）。
- **模型筛选**：柱图上方复选 chip 列表（水平 wrap），来源 = 当前跨度聚合行的 distinct model_id（按总量降序）；默认全勾；作用域**仅柱图**（KPI/会话列表不联动，SCOPE E 裁定）。probe-model 已在 SQL 层过滤（S4）。
- **KPI 首卡**：`总量 = input + output + cache_read`（`sumRows` 增 total 字段；reasoning 不计）；卡片顺序：**总量 / cache read / input / output** 四卡（cost 卡移除，cache read 升独立第二卡，首卡无副行小字）〔用户 2026-08-25 裁定修订，取代原「总量/input/output/cost + cache read 副行小字」布局；cost 数据仍在会话详情与 TodayStats 中存在，仅不作 KPI 卡展示〕。
- range 维度无柱图：隐藏柱图与筛选区，仅 KPI + 会话列表（现状语义不变）。

### 3.6 会话列表改造 + 砍饼图

- **删除**：`ProjectPie` 组件、`pieSlices`、`PROJECT_COLORS`、`.token-columns` 双栏布局——会话列表升为全宽。
- **列改造**（SCOPE G）：首列 = **title**（flex 省略；`title` 属性 tooltip = 完整标题 + session id + 本地时间）；`New session*` 回退行按原样显示；title NULL → session id 前 8 位。项目列 = `project_name` basename（`global`/未命中 → 回退标签 `t("token.project.global")` / `t("token.project.unknown")`）；展开详情追加「模型」行（model_id，None → 「未知模型」）。
- 排序不变：**token 总量降序（前端既有 `sortedSessions` 重排保留**；Rust 侧 ORDER BY time_updated DESC 为传输序，前端重排后才是展示序——两行为均维持现状）。

### 3.7 工具级气泡（宠物从「状态灯」升级「播报员」）

#### 3.7.1 协议（模板 ID，用户裁定）

插件在投递状态事件时按需携带 `detail = "<tplId>:<param>"`（String，复用 /state 既有字段，v1 已校验未消费）：

| tplId | 触发（opencode 工具） | param 提取（插件侧） | zh / en 模板 |
|---|---|---|---|
| `read` | read/listfile 类 | file path → **basename** | 正在读 {p} / Reading {p} |
| `edit` | edit/write/patch/apply_patch | file path → basename | 正在编辑 {p} / Editing {p} |
| `bash` | bash/shell/terminal | command → **先剥离行首连续 `KEY=value` 赋值段，再取首词；首词含 `/` 或 `\` 时取 basename**（与 read/edit 同口径——P1-4 修订：防绝对路径命令 `/opt/homebrew/bin/npm test` 与 env 赋值命令 `FOO=secret npm test` 击穿净化） | 正在跑 {p} / Running {p} |
| `search` | grep/glob | pattern → **净化后原样**（≤40 字符；含 `/` 或 `\` 时取末段） | 搜索 {p} / Searching {p} |
| `web` | webfetch/websearch | URL → **hostname** | 访问 {p} / Fetching {p} |

- **携带事件范围（澄清-3 裁定）**：仅 `tool.execute.before`（工具开始 = 播报正当时）；`tool.execute.after`（复位）与 `command.execute.before`（slash 命令，低频）不携带。
- **args 来源**：`tool.execute.before` 的 `output?.args`（与既有 `classifyToolBefore` 同源，签名第二参数）。
- **切分规则（P2-3）**：`detail = "<tplId>:<param>"` 按**首个** `:` 切分（param 可含 `:`，macOS 文件名/grep pattern 均合法）；切分点在 **pet 桥层**（Rust 原样透传 detail 字符串，不做解析——http_server 只透传回调）；tpl 不在白名单或 param 为空/纯空白 → 丢弃（不发气泡事件）。
- 插件侧 `extractDetailParam(tool, args)` 纯函数 + 单测（含绝对路径命令/env 赋值命令用例，P1-4）；**TC-SEC 净化口径**：绝不携带路径原文/参数原文/URL 全文。已知残余张力（P3-16 记录）：`search` 的 pattern 由用户输入、经 40 字符截断 + 路径段剥离后上气泡——属用户自己的查询词非数据泄露，接受。
- 插件侧**节流（澄清-1 背书：独立桶解读）**：detail 携带走**独立 detail 桶**（`Throttle` 新实例、全局单桶、20s——与 speech 桶同参数；SCOPE「speech 桶 20s 节流」的意图是防刷屏，状态事件走 reaction 桶、气泡 detail 走 detail 桶，两者独立）。**冷却消耗时机**：桶判定在 deliver 内 reaction 检查**之后**——状态事件被 reaction 桶吞掉时 detail 桶不消耗（状态事件通过 reaction 桶放行（postState 入队前）且 detail 桶放行时才附加 detail 并消耗冷却——网络成败不回滚冷却，N7 措辞精确化）。

#### 3.7.2 App 侧（渲染 / 开关 / 队列对接）

- Rust `http_server` 收到**含非空 detail 的状态事件**（Rust 仅字符串非空校验，tpl 合法性由桥层判——N8）→ lib.rs **`emit_to("pet", "pulsepet://tool-bubble", {detail})`**（定向 pet 窗，原样透传字符串；**App 侧过滤，Rust 不判开关**）。
- pet 桥层（新 `tool-bubble-bridge.ts`）：① 按 §3.7.1 切分规则解析 + 校验 tplId ∈ 白名单、param 再净化（单行、≤40 字符、去控制字符）；② 查**开关 store**；③ 通过 → `pushBubble({level:"ambient", …})`（dwell 由 M2 按级派生 4s；source=`"tool:<tplId>"`，10s 同源合并/可顶可丢均按 M2 ambient 语义）。
- 气泡文案经 i18n `toolb.<tplId>` 渲染（语言随 App 即时）。
- **开关的跨窗口机制（P1-3 修订，照 pass-through 模式）**：panel 与 pet 是两个独立 webview、zustand store 不共享——
  - Rust 新命令 `tool_broadcast_get` / `tool_broadcast_set`（读写 app_state 键 `bubble.toolBroadcast`，缺省 true；set 后 `emit_to("pet", "pulsepet://tool-broadcast", {enabled})` 广播）；
  - pet 桥启动时 get 初始化 store 位 + 订阅广播实时更新；开关判定只读 store 位（零 IPC 热路径）；**panel 设置页开关自身的初始显示值同样经 get 初始化**（照 pass-through 双窗 init 模式，N13）；
  - 设置页切换 → set → 广播 → pet 桥即时静默/恢复（验收「无需重启」由此成立）。
- **开关 UI 位置（P2-4 修订）**：设置页**「宠物与播报」区**（与「点击穿透」开关同区的 `settings-check` 形态，新增小节标题）——**不放 M2「功能管理」区**（该区语义已定稿为「插件启停」，工具播报是核心功能非插件，机制也不同源（app_state vs plugins.enabled），混放破坏 M2 §2.5 语义）。
- **插件改动发布联动**：`pulse-pet-hook.js` 变更 → 发布说明提醒重跑 `install.sh`（v0.1.3 同模式）。

### 3.8 Rust 变更汇总

| 模块 | 变更 |
|---|---|
| `token_stats.rs` | TokenRow +3 字段；SESSION_REQUIRED_COLUMNS +2 列；by-session/day/week/range 四查询改造（JOIN/model_id 分组）；**mock 过滤覆盖全部查询含 query_current_session（仅加过滤，无 JOIN/分组——N5 措辞精确化）**；`token_stats_today`（async+spawn_blocking）；~~`build_idle_report` 不动（追加在 lib.rs hook）~~〔实施修订：为满足 §3.2「同连接顺带 SUM（一次查询）」，旧 `build_idle_report` 重构为 `build_idle_report_with_today`（同连接一次查询，本期数字逻辑不变），旧单函数无调用方已删——2026-08-25〕 |
| `lib.rs` | idle hook 追加今日累计段（agent 分流内）；`emit_to("pet", "pulsepet://tool-bubble")` 接线；**`tool_broadcast_get`/`tool_broadcast_set` 命令**（app_state `bubble.toolBroadcast` + `pulsepet://tool-broadcast` 定向广播；〔实施修订：两命令实际落位 `interaction.rs`——crate root 泛型 command 与 tauri 宏冲突，行为与注册不变，2026-08-25〕）；命令注册 |
| `http_server.rs` | `StateEvent.detail` 从「校验不消费」→ 透传回调（不落盘不变，内存传递；不做解析） |
| `i18n.rs` | `token_report_today` 追加段模板（zh/en） |
| db.rs | 无 schema 迁移（app_state 键值即可） |

### 3.9 前端变更汇总

| 文件 | 变更 |
|---|---|
| `lib/token-stats.ts` | RangePreset+today；TokenRow+3 字段；sumRows+total；fetchTodayStats 封装（含错误透传） |
| `lib/token-chart.ts` | computeStackedBars 新增；computeBars/pieSlices 删除（测试同步） |
| `panel/TokenStats.tsx` | 默认今日；三段柱图+HTML tooltip+图例；模型 chip 筛选；删饼图/双栏；会话列表列改造 |
| ~~`pet/PetCanvas.tsx` + `pet/HoverToday.tsx`（新）~~ | ~~悬停 500ms 防抖/离开即消/缓存 30s/setHoverPaused 对接/菜单互斥~~ **〔HoverToday 已移除 2026-08-25；PetCanvas 悬停接线移除，今日数据经 `pet/todayToken.ts` 30s 缓存由右键菜单独享〕** |
| `lib/pet-menu.ts` + `pet/PetMenu.tsx` | `buildPetMenuItems(passThrough, todayToken, lang?)` 签名扩展；「今日 token」三态信息项（分隔线样式）+ 点击直达；menuH 估值调整 |
| `lib/tool-bubble-bridge.ts`（新） | detail 切分/白名单校验/param 再净化/开关 store（get 初始化 + 广播订阅）/ambient 入队 |
| `opencode-plugin/pulse-pet-hook.js` | `extractDetailParam`（含 env 赋值剥离/路径 basename 强化）+ detail 独立 20s 节流（reaction 后判定）+ 仅 tool.execute.before 携带 |
| `panel/Settings.tsx` + `lib/i18n.ts` | 「宠物与播报」区（工具播报开关）；新键（`token.preset.today`、`token.kpi.total`、`token.col.model`、`token.project.global/unknown`、`menu.todayToken`、`toolb.read/edit/bash/search/web`、`settings.toolBroadcast*`、`settings.sectionPet*`；~~`token.todayUnavailable`~~〔随悬停卡移除清退 2026-08-25〕；「未知模型」/空勾选空态/title tooltip 等细项实施时按模板微调增补，zh/en 键集合一致——N6） |

### 3.10 数据库：零迁移

`bubble.toolBroadcast` 落 app_state 键值表；无 schema 变更。

### 3.11 测试与验收（M3 Done 标准）

**单测**：

| 域 | 用例 |
|---|---|
| Rust 数据层 | row 映射（model_id 提取/JSON 损坏→None/title/project JOIN/global→None）；mock 过滤（mock 行不出现）；grouped 行含 model_id 且不含 project_id；`token_stats_today` 0 点边界（注入固定时刻）；idle 追加段格式与失败省略 |
| `token-chart` | computeStackedBars 三段顺序/勾选剔除/空集/空行；**不传 agentFilter 时行为 = 不过滤（等价全量，预留参数位钉子，N12）**；pieSlices/computeBars 删除后旧测试清退 |
| `token-stats.ts` | today preset 边界；sumRows total |
| `pet-menu` | 4 项构建/三态 label/点击直达 id（N1 同步 §3.4） |
| 插件（plugin-hook.test.ts） | extractDetailParam 各工具族（basename/首词/hostname/pattern 净化/无参→无 detail；**绝对路径命令 `/opt/homebrew/bin/npm test`→`npm`；env 赋值命令 `FOO=x npm test`→`npm`**，P1-4）；detail 20s 节流（冷却期状态照发 detail 省略；状态被 reaction 桶吞时 detail 桶不消耗）；detail 不影响状态节流桶；仅 tool.execute.before 携带 |
| `tool-bubble-bridge` | 首个 `:` 切分（param 含冒号）；tpl 白名单拒绝/param 空·纯空白丢弃/param 再净化；开关关闭静默；ambient 入队参数（source/level；dwell 由级派生）；广播事件更新 store 位 |
| Rust `tool_broadcast` | get 缺省 true/非法值回退；set 持久化 + `emit_to("pet")` 广播断言 |
| i18n | 新键 zh/en 完备性 |

**实机验收**（TC-M3-xx，落 V2-TEST-CASES.md）：

1. Token 页默认今日；切 7d/30d/自定义行为不回归；柱图三段自底向上 output→input→cache read；tooltip 内容（日期+三值+占比+总量）；模型 chip 取消勾选仅柱图变化、KPI/会话列表不动；probe-model 不出现在 chip 列表；
2. 饼图与双栏布局消失；会话列表首列为标题（悬停 tooltip 完整标题+id）、项目列 basename、展开有「模型」行；New session 回退行原样；
3. 真实会话结束 → 汇报气泡末尾「· 今日 XM」；~~悬停宠物 500ms 出汇总卡（四行）、移开即消、期间提醒气泡冻结恢复；穿透模式悬停不可达；悬停显示中切穿透 → 卡即消 + 队列冻结解除（N14）~~〔悬停卡已移除 2026-08-25，本段悬停部分作废〕；穿透模式右键菜单不可达（已知，仅被动层与面板可用）；右键菜单「今日 token」三态 + 点击直达 Token 页（默认今日）；**口径交叉断言（两层，原三层随悬停卡移除调整）**：口径一致（同 0 点起点 + mock 过滤 + reasoning 不计），**会话静止窗口内**两处数值相等（面板今日 KPI 总量 = 菜单显示值——活跃会话持续写入下秒级差异属正常，N2）；
4. 工具级气泡默认开：opencode 编辑文件 →「正在编辑 X.md」ambient 4s 自动消失；连续工具调用 20s 节流；设置页关闭开关后立即静默（无需重启，广播生效）；气泡不含任何路径/参数/URL 原文（TC-SEC 口径目验）；**ambient 排队语义实机补验**（承接 M2 §2.10 item 4 遗留）：提醒（critical）显示中触发工具播报 → 排队不顶替；连续不同工具产生多条 ambient → 队列上限驱逐可观察；
5. 深浅主题下柱图三段色可读（token 化色值）。

### 3.12 风险与开放问题

| # | 风险/问题 | 处置 |
|---|---|---|
| R1 | `json_extract` 依赖 JSON1——bundled SQLite ≥3.45 内置（S8），但**旧版 opencode.db 的 model 列若非 JSON**（理论不存在；S2 实测 0 NULL） | json_extract 对非 JSON 值返回 NULL → model_id=None →「未知模型」合并，天然降级不崩 |
| R2 | project 表缺失/结构变更 → JOIN SQL 失败 | 走既有 query 错误码（面板显示查询失败）；不做白名单防御（个人工具库长期稳定，防御成本>收益），记录在案 |
| R3 | ~~悬停层高频 invoke~~ 〔已失效 2026-08-25：悬停层移除，30s 缓存现仅服务右键菜单（低频）〕 | ~~30s 缓存（pet 桥层），最坏 2 次/分钟~~ |
| R4 | detail 白名单双端漂移（插件 tplId ↔ App i18n 键） | 白名单数组两处定义 + 交叉单测（插件测试 import App 侧清单?不可行——跨包；改为双侧各自测试钉同一常量表，文档 §3.7.1 为唯一权威） |
| R5 | 会话标题超长/含特殊字符 | title 属性天然转义；列表 flex 省略；气泡不消费标题（无净化面） |
| R6 | grouped 查询丢 project_id 后 `token.project.unknown` 等旧文案消费方 | KPI/柱图/会话列表三处复查（饼图已删）；实施时 grep 确认无残余消费 |
| R7 | 工具气泡 CC 侧缺席（仅 opencode） | 用户裁定；M5 接入（协议已定型，届时 CC hook 照抄 param 提取） |
| R8 | **App 侧 param 再净化为格式级**（单行/≤40/去控制字符），路径/参数剥除责任完全在插件提取层（N9 记录：与 v1 气泡白名单模板同一信任模型——/state 有 token 鉴权，事件源可信） | 记录边界；M5 CC hook 接入时复核此边界（照抄 param 提取即继承同等责任） |

### 3.13 不采用记录

| 项 | 理由 |
|---|---|
| detail 直发自然语言文案 | 语言死在插件、净化面扩大——模板 ID 协议（用户裁定）严格优 |
| KPI/会话列表联动模型筛选 | SCOPE E 裁定：口径各自独立 |
| range 维度渲染柱图 | 现状语义（range = 汇总无时序），无新需求 |
| 图例可点击（同步三段显隐） | 与模型筛选语义混淆；图例仅说明 |
| 悬停层进气泡队列 | M2 定案：特殊层 + 冻结队列，不占队列槽 |
| CC hook 同步携带 detail（M3） | 用户裁定仅 opencode；避免 M3 范围膨胀 + 未实施先改的风险 |
| Rust 侧判工具气泡开关 | 前端 store 过滤更简单且即时生效（SCOPE 倾向 App 侧过滤的落实）；开关读写/广播在 Rust（§3.7.2 完整机制） |

### 3.14 评审记录（2026-08-23，reviewer subagent）

> 评审对象：本章节初稿。评审基准：V2-SCOPE §3.3/§5.10/§5.11、M1 §1.5、M2 §2.2/§2.5/§2.6（上游定稿）、v1 现状源码逐点核对 + 本机 opencode.db 只读复核（S1~S8 全部实证属实，活库窗口漂移已注明）。
> **verdict: NEEDS REVISION**（P1×4 / P2×5 / P3×16 / 澄清×4；无 P0）。
> 处置结论：**全部采纳**——P1/P2 全部修订正文；P3 全部落实；澄清×4 以设计裁定消化。评审人总体评价：「数据层 SQL 改造、三层快捷查看与 M2 排队模型对接、spike 事实核实质量较高，问题集中在协议细节与范围承诺的落实完备性」。

#### 问题清单（摘要）与处置

**P1-1（已修，→ §3.4）**：穿透模式可用性误述——「②不可达（①③可用）」与 SCOPE §3.3 C 原文（仅被动层+面板可用）及代码现实（TC-WIN-04：穿透态右键菜单不可达）双重矛盾。改为「②③均不可达」。

**P1-2（已修，→ §3.1/§3.5）**：SCOPE H 要求的「agent 筛选预留位」只有一句空话承诺。落实：`computeStackedBars` opts 预留 `agentFilter` 参数位 + 筛选 chip 行按多组容器设计（M5 插第二组）。〔注：M5 实施时（2026-08-27 R2 修订）agent 筛选最终改为标题右侧 tab 单选 + 模型复选联动，未按"第二组 chip"形态落地；agentFilter 参数位预留价值不变，见 §5.6 修订注记。〕

**P1-3（已修，→ §3.7.2/§3.8）**：工具播报开关缺跨窗口机制（panel/pet 双 webview 不共享 store，「立即静默」不可实现）。补齐：`tool_broadcast_get/set` 命令 + `pulsepet://tool-broadcast` 定向广播 + pet 桥 get 初始化/广播订阅（照 pass-through 模式）。

**P1-4（已修，→ §3.7.1）**：bash「首词」规则击穿 TC-SEC——绝对路径命令首词 = 完整路径、env 赋值命令首词 = `FOO=secret`。强化：剥离行首 KEY=value 段 + 首词含路径分隔符取 basename + 补两类单测。

**P2（均落实）**：P2-1 会话列表排序澄清（前端 token 降序重排保留，两行为均维持现状）；P2-2 ambient 排队语义实机补验（承接 M2 §2.10 遗留，验收 item 4）；P2-3 detail 切分规则定案（首个 `:`、pet 桥层切分、Rust 只透传）；P2-4 开关 UI 移出「功能管理」区（该区语义=M2 定稿的插件启停；工具播报放设置页「宠物与播报」区，与穿透开关同形态）；P2-5 三层口径交叉断言（验收 item 3）。

**P3（16 条均落实）**：S6 窗口标注 + 87% 为权威口径（SCOPE ~97% 系早期 token 加权观测）；菜单 4 项（非 5）；`buildPetMenuItems` 签名扩展 + `PetMenuAction` 增员 + 信息项分隔线；「SCOPE D 口径」引用修正；range 维度表述清理；dwell 记法改「level 派生」；detail 桶语义定案（全局单桶、reaction 后判定消耗）；args 来源 = `output?.args`；query_current_session 同口径 mock 过滤；追加段口径 in+out+cacheRead；i18n.rs 模板补；`emit_to("pet")` 定向；悬停卡/右键菜单互斥（后开者胜）；全零数据显示 0；i18n 键名补全路径；search pattern 残余张力记录。

**澄清项裁定**：① detail 独立桶（与 speech 桶同参数非复用）——作者背书，SCOPE 意图为防刷屏；② lab 占比权威口径 = spike 87%（session 数/30 天）；③ detail 仅 `tool.execute.before` 携带；④ 悬停卡固定贴宠物上方同气泡位，与右键菜单后开者胜互斥。

#### 修订汇总（2026-08-23，按评审意见）

§3.0 S6 窗口+口径标注；§3.1 预留位指向；§3.2 current_session 过滤/追加段口径/i18n 模板；§3.4 穿透修正/卡片落点/互斥/全零/签名扩展/4 项；§3.5 agent 预留位落实（opts 参数 + 多组容器）/SCOPE D 引用/range 表述/键名；§3.6 排序澄清；§3.7.1 bash 强化/切分规则/携带范围/args/桶语义/残余张力；§3.7.2 开关全机制/设置区归属/emit_to/dwell 记法；§3.8 tool_broadcast 命令行 + i18n 行；§3.9 键名与文件行补全；§3.11 三处验收与单测增补。

#### 终审记录（2026-08-23，用户）

- **评审点全部认可**：五类工具气泡模板与中英文案（含 search pattern 上气泡的残余张力，接受）、悬停层四细节（500ms 防抖/后开者胜互斥/dwell 冻结/全零显示 0）、工具播报开关位置（设置「宠物与播报」区）与默认开、KPI 首卡布局（cache read 降副行小字）、会话回退行原样显示——照单定稿。
- **四条澄清裁定背书**：① detail 独立 20s 节流桶（SCOPE「speech 桶」解读为同参数防刷屏意图）；② lab 占比权威口径 = spike 87%（session 数）；③ detail 仅 `tool.execute.before` 携带；④ 悬停卡固定贴宠物上方 + detail 按 `:` 首切在 pet 桥层。
- **M3 定稿**（M1/M2 已于同日定稿，见 §1.13/§2.13）。

#### 复审记录（2026-08-23 第二轮，同 reviewer 续会话；M4 定稿后回调）

> 复核第一轮 29 项（P1×4/P2×5/P3×16/澄清×4）：**全部正确落实**，修订未引入与 M1/M2/M4/SCOPE/源码的新矛盾。
> **verdict: APPROVED WITH COMMENTS**——新发现 P2×3 + P3×11，均为文档精度与边界补强，「不影响方案成立，建议在实施前顺手吸收（尤其 N1 与 N14）」。
> 处置：**全部采纳并已修**——N1 §3.11 单测表「5 项」→「4 项」同步；N2 交叉断言加时序限定（口径一致 + 会话静止窗口内相等）；**N14 穿透切换兜底**（悬停卡订阅 `pulsepet://pass-through`，穿透开启即取消计时器/隐藏/解除冻结，对齐 PetMenu 先例）+ 验收补用例；N3 agentFilter 弃「never 收窄」改 `ReadonlySet<string>` 声明参数位；N4 菜单打开即解除 hoverPaused；N5 §3.8 汇总括注精确化；N6 i18n 键细项增补注；N7 冷却消耗措辞（reaction 放行即消耗、网络成败不回滚）；N8「含非空 detail」；N9 新增 R8（App 侧格式级兜底边界，M5 复核）；N10 中性化措辞；N11 菜单 v 值 formatTokens 口径；N12 agentFilter 预留位单测钉子；N13 panel 开关初始值 get 初始化。

## 4. M4：定时任务（动作泛化：notify / exec）

### 4.0 Spike 结论与裁定（2026-08-23）

> Spike：`opencode run` 非交互权限行为（SCOPE §5.8 前置），opencode 1.18.19 本机二进制源码考古 + 真实运行实测。

| # | 事实 | 证据 | 设计含义 |
|---|---|---|---|
| S1 | **`opencode run` 遇权限请求不卡死**：默认打印 `permission requested: …; auto-rejecting` + 自动 `reply:"reject"`，agent 收到拒绝结果后继续执行（跳过该工具或改道），任务正常结束 | run 客户端事件循环（二进制 @65205804）+ 实测（写文件任务 7s 完成，bash 自动放行无需审批） | SCOPE 担心的「卡死还是跳过」定论：**不卡死**；超时只需防模型慢/长任务，非防审批悬挂 |
| S2 | **`--auto` flag**（公开，官方 describe "auto-approve permissions that are not explicitly denied (dangerous!)"）+ 隐藏别名 `--yolo` / `--dangerously-skip-permissions`：开启时权限请求自动 `reply:"once"` 放行 | 二进制 yargs 配置 @65078270 | opencode 模板提供「自动放行权限」可选项（用户裁定 2026-08-23，默认**不勾**） |
| S3 | run 支持 `--dir`（工作目录）/ `--title`（会话标题，token 统计可见）/ `--model` / `--format json` | `opencode run --help` | 模板拼命令的素材；`--title "pulsepet 例程: <任务名>"` 让例程会话在 Token 页可辨识 |
| S4 | 例程会话的 agent 细粒度状态（thinking/editing/testing）经既有插件事件链路正常上报（spawn 的 opencode run 加载同一 pulse-pet-hook.js）；会话进 opencode.db → token 统计口径自洽 | 架构推演（SCOPE §3.4 原文「零新开发」） | 宠物状态 agent 层免费 |

**裁定汇总**：exec 超时**可配置（1–120 分钟）、默认 10 分钟**；opencode 模板提供 `--auto` 可选项（默认不勾）；**15 分钟补跑窗 notify/exec 同窗**（用户裁定 2026-08-23——**有意偏离 SCOPE §3.4 原文的「仅任务补跑」自然解读**：用户明确选择单一口径，提醒类 daily/once 同样补跑；interval 类维持 v1 不补）；暂停语义对齐 SCOPE 字面（**不跑不补、记 skipped**——恢复后不补，见 §4.3）；其余 SCOPE 已定项照单（直接执行无前置确认、「跳过本次」手动通道、snooze 稍后 10 分钟、执行历史、合并 tab）。**工期口径：~1.5-2 周，macOS 先行、Windows 分支（powershell/taskkill）同构实现 + 实机验证挂观察项**。

**分层定调（用户 2026-08-23）**：底层能力 = **执行命令行（exec）**；`opencode run` 只是建于其上的一等模板（表单辅助拼命令，执行层不感知 opencode）。

### 4.1 目标与范围

- `reminders` 表迁移 003：`action_type`（notify 默认 / exec）+ `action_params`（JSON 载荷）+ `schedule_kind`（interval / daily / once）+ 定点时刻/星期列。
- ActionExecutor（Rust）：`validate(params)` + `run(params) -> ActionOutcome`；exec = spawn 命令行（cwd/超时/输出尾部捕获）。
- 定点调度：daily（可选星期过滤）+ once；补跑宽限窗 15 分钟（超窗记 skipped）；暂停不跑不补记 skipped。
- 执行历史：`action_logs` 表（exec 型每次运行：状态/退出码/输出尾部/起止时刻/原定时刻）。
- 宠物状态两层：通用层（working/success/error，伪 session 注入）+ agent 层（免费）既有优先级合并。
- UI：提醒 + 定时任务合并为「定时任务」tab（一张列表 + 动作徽标 💧/⚡，表单按 action_type 条件显隐，落 M2 设计系统）；提醒 snooze（气泡按钮「稍后 10 分钟」）。
- **不含**：webhook/平台自动化等未来动作类型（SCOPE §4）、对话入口、M2 已完成的气泡排队（消费 M2 critical 级）。

### 4.2 数据模型（迁移 003）

`src-tauri/migrations/003-m4-tasks.sql`（`MIGRATIONS` 表追加 + `SCHEMA_VERSION` = 3，事务化同 A1 约定）：

```sql
-- 定时任务泛化（V2-SCOPE §3.4：只加枚举值不动表结构）
ALTER TABLE reminders ADD COLUMN action_type TEXT NOT NULL DEFAULT 'notify';   -- 'notify' | 'exec'
ALTER TABLE reminders ADD COLUMN action_params TEXT;                            -- JSON；exec = {"command","cwd?","timeout_minutes?","opencode_auto?"}
ALTER TABLE reminders ADD COLUMN schedule_kind TEXT NOT NULL DEFAULT 'interval'; -- 'interval' | 'daily' | 'once'
ALTER TABLE reminders ADD COLUMN schedule_at TEXT;        -- daily → "HH:MM"；once → "YYYY-MM-DDTHH:MM"；interval → NULL
ALTER TABLE reminders ADD COLUMN schedule_weekdays TEXT;  -- JSON "[1,3,5]"（1=周一…7=周日）；仅 daily 消费；NULL/空 = 每天
ALTER TABLE reminders ADD COLUMN snooze_until TEXT;       -- RFC3339；snooze 顺延终点；触发时清空
ALTER TABLE reminders ADD COLUMN last_skipped_at TEXT;    -- RFC3339；skipped 判定时刻（P3-2：与 last_triggered_at 分离，
                                                           -- 防 skipped 写入使 3min 内「试一试」被 dedup 拒绝——醒来手动补跑场景）

-- exec 执行历史（notify 维持 reminder_logs 既有记账，不双写）
CREATE TABLE action_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reminder_id INTEGER NOT NULL,      -- 悬空引用允许（历史保留，同 002 迁移 reminder_logs 语义）
  action_type TEXT NOT NULL,         -- 冗余存快照（规则删除后类型仍可读）
  status TEXT NOT NULL,              -- 'running' | 'ok' | 'failed' | 'skipped'
  summary TEXT NOT NULL,             -- 一句话结果（气泡/列表直接消费）
  output_tail TEXT,                  -- stdout+stderr 合并尾部（≤2KB）
  exit_code INTEGER,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  scheduled_at TEXT                  -- 原定触发时刻（补跑/skipped 溯源）
);
```

> **004 修订（2026-08-30，routine-exec.md Part A）**：action_logs 追加三快照列 `label` / `command` / `executed_command`——执行历史的语义 = **执行时点的任务内容快照**（规则改名/改命令/删除后历史仍可回查当时内容；`label` 沿用来源列同名；`executed_command` 仅 running 写、skipped 恒 NULL = 未执行；迁移前旧行三列 NULL → 前端「未记录」）。
>
> **005 修订（2026-08-30，routine-exec.md Part C）**：快照字段集合演进为 **任务名 / 命令 / 工作目录**——`+cwd TEXT`（当时执行目录时点实录）；`DROP COLUMN executed_command`（命令串逐字节原样传给 sh/powershell、目录经进程属性生效，实录与配置**恒同值**，冗余列删除——004→005 存量行该列与 command 同值，零信息损失；SCHEMA_VERSION=5）。

**与 SCOPE §3.4 的差异（4 枚举 → 3 枚举）**：`weekly-at` 并入 `daily` 的 `schedule_weekdays` 过滤（判定逻辑同为「下一个匹配日的 HH:MM」），枚举更少语义不减；未来「每月 X 日」等加列或并入 weekdays 语义扩展，不动既有列。

**存储约定（P2-6）**：daily/once 行 `interval_minutes` **恒为 0**（validate 强制）；既有代码全部 `interval_minutes > 0` 分派点（暂停顺延/触发推进/force_fire_one）**改按 `schedule_kind == "interval"` 分派**——行为对 daily/once 天然「暂停不顺延、触发后按 kind 推进」。kind 切换（interval↔daily↔once）时 validate 重置无关字段（interval 行清 schedule_at/weekdays；daily/once 行清 start_time/end_time 窗口——防遗留窗口使 collect_due 的 in_window 判定卡住导致误 skipped）。once 的 `schedule_at` 为过去时刻 → validate 拒绝（防创建即意外触发执行命令）。

**todo 派生行不动**：`kind='todo'`（M7 语义：interval=0 + start_time 绝对时刻）行为与 `once` 等价，**不迁移**——避免动 M7 已验逻辑；两者在 `collect_due` 各走分支，未来如统一需另行裁定。

**v1 数据兼容**：既有行自动获得默认值（action_type='notify' / schedule_kind='interval'），v1 行为零变化（interval 判定分支既有逻辑不变）。

### 4.3 调度扩展（reminder_scheduler.rs）

**`compute_next_due` 按 schedule_kind 分派**（纯函数，扩展非重写）：

| kind | next_due 计算 |
|---|---|
| `interval` | 既有逻辑不变（last_triggered/created 锚点 + interval；**错过不补**，v1 语义保留——提醒无害） |
| `daily` | 下一个匹配日的 `schedule_at` HH:MM（匹配 = schedule_weekdays 含今天星期，NULL=每天）；当日时刻已过则次日（跳过不匹配日） |
| `once` | `schedule_at` 绝对时刻；触发/跳过后 `i64::MAX`（v1 todo 模式同款终态） |

**补跑宽限窗**（新常量 `CATCHUP_WINDOW_MS = 15min`，daily/once 两 kind、notify/exec 两动作同窗——用户裁定单一口径，偏离 SCOPE「仅任务补跑」字面）：

- tick 时 `now >= next_due && now - next_due <= 窗口` → **正常触发**（补跑一次，last_triggered_at 记实际触发时刻）；
- `now - next_due > 窗口` → **skipped**：exec 型写 `action_logs(status='skipped', summary='错过补跑窗（15 分钟）', scheduled_at=原定时刻)`，推进 next_due（daily → 下个匹配日；once → MAX）；notify 型 skipped 不落库（错过无害）；**不触发气泡/烟花**。**skipped 记账闭环（N1 修订；P3-2 精化）**：两来源（超窗/暂停）的 skipped 判定均同步写**新列 `last_skipped_at` = skipped 判定时刻**（与 last_triggered_at 分离——skipped 不是触发，且防「醒来发现超窗 skipped、3 分钟内点试一试手动补跑」被 force_fire_one 的 dedup（判定源 last_triggered_at）拒绝）；同样三点收益：① reload 错过检测（比较 max(last_triggered, last_skipped) 与 schedule_at）对已 skipped 规则不再误报；② once 的 MAX 终态跨重启成立（compute_next_due 按 max(last_triggered, last_skipped) 判定已处理）；③ 防暂停期每 tick 重复判定。**collect_due 返回值扩展**：`Vec<ReminderRule>` → `(fired: Vec<…>, skipped: Vec<…>)`，skipped 列表随 fired 一起返回调用方落库（v1 collect_due 是纯内存函数无 conn——落库在 spawn_scheduler 的 tick 处理段，与既有 mark_triggered/insert_log 同位）。
- **App 关闭/CRUD reload 的错过检测（P2-5）**：`reload` 重建 next_due 时，daily/once 检测「上次加载后本周期 schedule_at 已过且 `last_triggered_at` 早于该时刻」→ 同补跑窗判定（窗内补跑 / 超窗 skipped 记录）——「今早跑了没」在重启后仍可对账；once 因 next_due=schedule_at（过去）天然走补跑窗，daily 由本检测覆盖。
- 与系统睡眠的配合：`MissedTickBehavior::Skip`（既有）+ 醒后首个 tick 用 now − next_due 差值精确判定（SCOPE §5.8「Skip 之上的精确判定」落实）。
- 暂停期间（collect_due 暂停分支，对齐 SCOPE 字面「不跑不补、记 skipped」——P2-4 修订）：daily/once 到期规则**不顺延、不触发**，到期即记 skipped（exec 落 action_logs；notify 不落库；**记后同样推进 next_due**——daily 下个匹配日/once MAX，防恢复前每 tick 重复判定，落库路径同 N1 的 skipped 列表返回；**记 skipped 时同款清空未过期 snooze_until**——P3-5，防 10min 内重启 + 暂停组合下的重复判定）；恢复后**不补跑**（暂停语义 = 完全冻结）；interval 类维持 v1 顺延不变。

**snooze**（SCOPE §3.4 末条；**仅 notify**——exec 触发无气泡、结果气泡无 reminder 载荷，永不显示 snooze 按钮，P3-5 显式钉住）：

- 气泡按钮「稍后 10 分钟」（M2 critical 提醒气泡扩展第二按钮，与「点宠物=确认」并存）→ invoke `reminders_snooze(log_id)`；
- **语义 = 重发本次（P1-1 修订）**：`snooze_until = now + 10min` 写表（持久化，重启保留）+ 当前 log 结案 `dismissed_via='snooze'` + 内存 `next_due = snooze_until`；**`compute_next_due` 中 snooze_until 未过期时优先于常规计算**（非 max——触发后常规 next_due 已是未来，max 会吞掉 snooze；只有「直接置为」才能重发）；
- **重发后的推进**：重发触发时清空 snooze_until，next_due 按各 kind 常规推进——interval：锚点顺延链整体后移 10min（重发时刻为新 last_triggered_at）；daily：下个匹配日；once：`i64::MAX`（重发即终态，「明晚 9 点开会」snooze 一次后结束）；
- 与去重交互：重发距 snooze 点击 10min > 3min 去重窗，天然无冲突；与暂停交互：暂停期内 snooze_until 到点 → interval 类被暂停顺延吞没（无 skipped 概念）；daily/once 类按暂停语义记 skipped（N6 措辞修正）。已知边界（N3）：snooze 后 App 重启时若 snooze_until 已过期 → 优先级判定不生效、重发静默丢弃（notify 无害，接受——验收 7 的「重启仍有效」仅限 snooze 窗口 10min 内重启）。

**「跳过本次」**（表单/列表手动通道）：内存 `next_due` 即时推进（interval → +interval；daily → 下个匹配日；once → MAX），不触发不记录（操作本身在 UI 可见）；**若该规则 snooze_until 未过期则一并清空（N2 修订——防后续 reload 因 snooze 优先级复活被跳过的重发；清空需写表 + 内存同清，P3-4）**。已知边界（P3-4）：once 跳过后若在补跑窗内重启 App → reload 检测会补跑（跳过标记未持久化）——接受，记录在案（跳过是即时动作，为它加列不值）。

### 4.4 ActionExecutor（Rust 新模块 `action_exec.rs`）

```rust
pub struct ActionOutcome {
    pub status: ActionStatus,        // Ok | Failed | Skipped
    pub summary: String,             // 一句话（i18n.rs 模板：成功/失败(退出码 N)/超时被终止/…）
    pub output_tail: Option<String>, // ≤2KB
    pub exit_code: Option<i32>,
}
pub trait ActionExecutor { fn validate(&self, params: &Value) -> Result<(), String>; async fn run(&self, params: &Value, ctx: RunCtx) -> ActionOutcome; }
```

- `NotifyExecutor`：触发即 ok（气泡/烟花编排走既有 reminder://trigger 链路，ActionExecutor 对 notify 是薄壳——保持三功能共享调度器的统一接口）。
- `ExecExecutor`：
  - `validate`：command 非空 ≤2000 字符；cwd 可选（存在则须为目录）；timeout_minutes 1–120（缺省 10）；`opencode_auto` bool（仅校验，不改变命令——模板拼接已在 UI 完成）；
  - `run`：`sh -c <command>`（Unix）/ `powershell -NoProfile -Command <command>`（Windows，pwsh 不保证存在；SCOPE §5.8 Windows 差异定案）；cwd 生效；**进程组 kill**（Unix `setsid` + kill −pgid；Windows `taskkill /T /F`——防 `sh -c` 只杀壳留孤儿子进程）；
  - 输出捕获：stdout+stderr 合并攒 buffer，超 2KB 保尾部（截尾标记 `…(已截断)`）；退出后截尾入 outcome；
  - 超时：到时杀进程组 → status=Failed，summary「超时（N 分钟）被终止」，output_tail 仍取已捕获部分；
  - **async + tokio 进程**（P2-8 修订；N5 收敛）：`tokio::process`（Cargo tokio features 增 `process`）+ **新增 `libc` 依赖**（Unix `setsid`/`kill(-pgid, SIGKILL)` 杀组——无需 tokio `signal` 特性；Windows 走 `taskkill /T /F` 不需 libc）——tokio/libc 均为 tauri 依赖树既有 crate，体积影响趋零；执行跑独立 spawn 任务（调度器 tick 不等待——并行任务互不阻塞）；`RunCtx` 携带 action_log_id 供完成时回写；**完成/超时回写时先从运行句柄登记表移除，Exit 只处置仍在登记表的句柄**（N7——防完成路径与退出路径竞写同一 action_log 行）。
- 分派注册表：`action_type → Box<dyn ActionExecutor>`（HashMap 常量，未来类型只加条目）。
- **「试一试」对 exec 行**（P3-9 定案）：与 notify 同语义——**真实执行一次**命令（`force_fire_one` 既有路径接 ActionExecutor 分派），受暂停/去重约束；结果气泡同正常触发。手动通道预览执行语义是「定时任务」的试跑（用户裁定直接执行模型，无前置确认）。

### 4.5 exec 执行链（到点 → 执行 → 汇报）

```
tick 判定到期（daily/once，补跑窗内）
  → insert action_logs(status='running', started_at, scheduled_at,
      label/command/cwd 快照)           ← spawn 时刻写（004/005：执行时点任务内容快照，routine-exec.md Part A/C）
    （并发满 2 时：任务进内存等待队列（RemindersState 新字段 pending_execs），
      不写 running；空位出现（完成回调通知调度器）时出队 spawn；
      排队中无进程无 running 行——App 退出/崩溃时排队任务自然消失无残留）
  → 通用层状态：apply_event("task:<log_id>", Working) + notify   ← 伪 session 注入
  → spawn 执行任务（async tokio；期间每 15s 重 apply Working + notify —— 心跳保鲜，
    防既有 30s idle 回收（P2-9：15s = 30s 的 1/2，裕量 15s；Working 非瞬态，
    生效机制是 idle 回收而非瞬态回退）；零状态机改动）
  → 完成/超时
  → update action_logs(status/summary/exit_code/output_tail/finished_at)
    （004/005：快照列 insert 时已写，终态 update 不动）
  → 通用层终态：exit 0 → apply Success；非 0/超时 → apply Error（30s 后自然回收）
  → 结果气泡：emit_to("pet", "pulsepet://task-result", {text, logId, status})
    → 桥层 pushBubble({level:"critical", source:"task:<log_id>"})
    （text = 任务名 + summary，lib.rs 拼接；summary 用 i18n 模板键按当前语言渲染——P3-3 补）
```

- **结果气泡独立事件（P1-3 修订）**：`pulsepet://bubble` 已被 M2 冻结为 info 级 token-report 桥层映射，复用会导致 level/dwell/source 全错——新事件 `pulsepet://task-result` + 前端桥层（reminder-bridge 内扩展）按 M2 critical 入队；**无 reminder 载荷**（非提醒气泡）：点宠物即消、不写 reminder_logs、不显示 snooze 按钮（M2 气泡组件的 snooze 按钮条件 = critical 且 `reminder` 载荷，天然不满足）。
- **伪 session 定义（P2-7）**：session key = `"task:<log_id>"`（复合 key 首段 agent = **常量 `"task"`**，与 HTTP 白名单 `opencode|claude-code` 互不冲突——伪 session 走 Rust 内部直连 `apply_event`，不经 http_server 白名单）；M2 状态芯片对 `agent=="task"` 显示「定时任务」文案（i18n 键 `panel.agentTask`）；注入/心跳/终态每次 apply 后**必须调 `DisplayNotifier::notify`**（对齐 HTTP 路径行为，否则宠物动画不变）；**不更新 AgentActivity、不触发 idle_hook**（伪 session 非真实 agent 事件，接入管理活性统计与 token 汇报均与其无关）。
- **agent 层免费**：spawn 的 `opencode run` 加载 pulse-pet-hook.js，thinking/editing/testing 细粒度状态经 HTTP 正常上报（真实 session key），与伪 session 平等参与优先级合并——「agent 层优先、通用层兜底收尾」的 M4 落地即**纯优先级合并**（伪 session 的 working(1)/success(2) 天然低于手头会话的 editing(4)/testing(5)；task 的 error(7) 抢镜一次可接受——失败本就该被看见；M6 引入最近活跃优先后再精化，SCOPE §3.6 预告的协同届时定）。已知双 emit（P3-7 记录）：例程结束时真实会话 idle 注入 Success 与伪 session 终态 Success 同优先级先后到达，(kind,agent) 去重下芯片在 opencode/task 间闪一次——接受。
- **并发上限 2**（P3-2 细节如上流程图）：等待队列在 RemindersState；完成回调经 channel 通知调度器出队。
- **例程会话 token 口径**：例程进 opencode.db → Token 页可见（`--title` 前缀「pulsepet 例程:」标识）；来源标注（区分例程/手办）留 M5 agent 维度一并定（SCOPE §3.5 原文）。

### 4.6 例程模板注册表（UI 辅助，执行层不感知；原「opencode 一等模板」，Part B 泛化 2026-08-30）

表单动作类型选「执行命令」时出现「例程模板」快捷块——**多 agent 模板注册表**（`lib/routine-templates.ts` 前端单侧，每 agent 一行 `{agentId, matches, build, flags[]}`；加新 agent 例程 = 一行 + i18n 键对，UI 零改动）：

```jsonc
// opencode 行填充结果（纯字符串拼接，执行层只认 command）
{
  "command": "opencode run --title \"pulsepet 例程: <任务名>\" --auto? \"<指令>\"",
  "cwd": "<项目目录，可选>",
  "timeout_minutes": 10,
  "tpl_agent": "opencode",          // Part B：选中模板 + flags 持久化
  "tpl_flags": { "auto": true }     //（保存一律新格式；旧键 opencode_auto 读兼容）
}
// claude-code 行：claude -p "<指令>" [--dangerously-skip-permissions]
//（任务名只进 PulsePet label 不进命令——CC 无 --title，会话无 ⚡ 徽标，接受边界）
```

- UI：chips 单选（默认预选 OpenCode，切换重置 flags、command 不因切换而变）+ 共享指令框 + 当前模板声明式 flags 行（danger 勾选 + 警示）+ 一键填充（**恒可点**——空指令填骨架命令、输入指令后自动重拼，保留高级用户「先填充骨架、后手改 command」口子；2026-08-30 用户目验修订，推翻实施时采纳的「指令空禁用」处置，见 routine-exec.md §3.7 修订段）；chips 文案复用 agents.ts `labelKey`；
- flag 语义（`--auto` / `--dangerously-skip-permissions` 同款）：默认不勾——只读任务几乎不触发权限；勾选时危险色警示（无人值守副作用命令）；Rust validate 宽松校验 `tpl_agent`（字符串）/ `tpl_flags`（对象 + 值全布尔）；
- 自动重拼启发式 = 注册表 `matches()`（`startsWith` 前缀形态，比 `includes` 严——复合命令不重拼；**重拼只看 command，不看选中态**）+ 空指令守卫（编辑回填 tplInstruction 恒空，不以空指令覆盖原 command）；
- 模板仅填表辅助：用户可自由改 command（模板产物与手写命令无差异）；`--dir` 不用（cwd 字段就是工作目录）。

### 4.7 UI：合并「定时任务」tab + snooze 按钮

- **tab 改名**：核心 tab「提醒」→「定时任务」（`panel.tab.tasks`；M2 注册表核心三之一，位置不变）；i18n 键沿用 `reminders.*` 存量 + 新增 `tasks.*`（合并表单/徽标/历史/模板）。
- **（2026-08-25 R1 后用户裁定修订）**：① tab 中文显示名「定时任务」→「例程」（en 建议Routines，实施定）；「Todo」tab 中文显示名→「待办」（en 保持 Todo）——仅改 i18n 值，labelKey（`panel.tab.tasks` / `panel.tab.todo`）不变，页面内与 tab 名直接联动的标题文案同步「例程」；② 表单标题「新建提醒」→「新建例程」；③ 「新建」按钮从单独一行移至表单块**右下角**并换非默认色（与 M2 token 协调，实施定色）；④ 表单动作类型分段按钮去图标（「提醒」不带 💧、「执行命令」不带 ⚡；列表行徽标 💧/⚡ 保留不动）。
- **（2026-08-25 二次修订）**：⑤ 状态芯片 `panel.agentTask` 文案「定时任务」→「例程」（en 建议 Routine，实施定）——与 tab 名统一；⑥ 「新建」按钮再上移：**不占单独动作行，与表单最后一行字段同行对齐**（右随字段行），③ 的"表单块右下角"精化为"最后一行字段行右端"。
- **（2026-08-30 修订，routine-exec.md Part A）**：⑦ 执行历史分页 50→15 + 常量收归 `ACTION_LOG_PAGE_SIZE` 单点（原局部 `PAGE_SIZE` 与常量双份维护有失配风险）；⑧ 迁移 004 三快照列（`label`/`command`/`executed_command`）——历史展示全读快照、不关联当前配置（行内任务名 + 展开区「存储命令（当时配置）/ 实际执行命令」双块；skipped →「未执行」、旧行 →「未记录」）；⑨ 分页控件（页码 + 上一页/下一页）移历史块底部居中，筛选下拉独占顶部。
- **（2026-08-30 修订，routine-exec.md Part B）**：⑩ §4.7 表单行的「opencode 模板块」字样同步——exec 表单任务名行之下为**例程模板注册表块**（chips 多模板，§4.6 Part B 重写）；`--auto` 勾选项成为 opencode 模板声明的 flag 之一（claude-code 行对应 `--dangerously-skip-permissions`）。
- **（2026-08-30 修订，routine-exec.md Part C）**：⑪ 快照字段集合演进为 任务名/命令/工作目录——迁移 005 `+cwd`（当时执行目录）/ `−executed_command`（实录与配置恒同值，冗余列删除）；展开区「存储命令/实际执行命令」双块 → **「命令（当时）」单块 +「工作目录（当时）」块**（cwd 未配置 →「继承 App 进程目录」占位）；skipped 行「未执行」语义由状态色点/文案承载。
- **列表**（一张，现有提醒列表扩展）：每行动作徽标（🔔 notify / ⚡ exec，title 属性说明——§十二 F10 修订 2026-08-28：💧→🔔）+ 类别列（§十二 F11 修订：todo 派生行同渲染「📋 待办」，原条件排除已删）+ 名称 + 调度摘要（「每 30 分钟 · 09:00-18:00」/「每天 09:00」/「周三、五 09:00」/「一次 · 08-25 21:00」）+ 启用开关 + 行操作（编辑/试一试/跳过本次/删除两步确认——均既有交互模式扩展）；todo 派生行保持 M2 展示（可见惰性 + 徽标；§十二 F12 修订：行内烟花勾选项移除，烟花随全局总开关 OR 语义；§十二 F14 修订：页底「历史统计」区移除，reminder_logs 记账保留）。
- **表单**（M2 只做了轻翻新，本里程碑完整重做，SCOPE 预告的归属）：动作类型分段（notify/exec）→ 条件显隐：
  - notify：kind（hydration/rest/custom）/ 文案 / 调度（interval 分钟 + 时间窗 ‖ daily HH:MM + 星期 ‖ once 日期时间）/ 烟花；
  - exec：任务名 / 例程模板注册表块（§4.6 Part B：chips 多模板 + 声明式 flags）/ command（等宽多行）/ cwd / 超时分钟 / 调度（同上三分支）/ 模板 flags 随勾选；
  - 校验：Rust `validate` 为权威（前端同规则预检，v1 模式）。
- **执行历史区**（列表下方折叠面板）：action_logs 倒序（时间 / 徽标 / **任务名（`label` 快照，不关联当前 rules）** / summary / 状态色点 ok 绿·failed 红·skipped 灰·running 蓝）；行展开显示 **「命令（当时）」单块（实录与配置恒同值——命令串逐字节原样传给 sh/powershell）+「工作目录（当时）」块（`cwd` 快照；未配置 →「继承 App 进程目录」占位）**（005 起，Part C；旧行 command NULL →「未记录」）+ output_tail（等宽，2KB 内）+ scheduled_at 与 started_at 差（补跑延迟可见）；命令 `action_logs_list(reminder_id?)` 分页（**15 条/页，2026-08-30 裁定；页码 + 上一页/下一页在块底部居中，筛选下拉独占顶部**）。
- **snooze 按钮**：M2 气泡组件扩展——critical 且 `reminder` 载荷时，气泡右侧小按钮「稍后 10 分钟」（hover 才浮现，不喧宾）；点击 invoke `reminders_snooze` → 气泡即消；点宠物仍 = 确认（两动作并存，M2 记账语义：snooze 结案 via='snooze'）。

### 4.8 Rust 变更汇总

| 模块 | 变更 |
|---|---|
| `migrations/003` + `db.rs` | §4.2 五列 + action_logs 表；SCHEMA_VERSION=3 |
| `migrations/004` + `db.rs` | action_logs +3 快照列（label/command/executed_command，§4.2 修订注）；SCHEMA_VERSION=4（2026-08-30，routine-exec.md Part A） |
| `migrations/005` + `db.rs` | action_logs +cwd 快照列、−executed_command（§4.2 修订注）；SCHEMA_VERSION=5（2026-08-30，routine-exec.md Part C） |
| `Cargo.toml` | tokio features + `process`；新增 `libc`（Unix setsid/kill(-pgid) 杀组，无需 signal——P3-1 同步 §4.4） |
| `action_exec.rs`（新） | ActionExecutor trait + Notify/Exec 实现 + 分派注册表 + 运行任务句柄登记表（`HashMap<log_id, ChildHandle>`，供退出处置）；命令 async（issue #9 纪律） |
| `reminder_scheduler.rs` | ReminderRule struct/row_to_rule/load_rules SELECT +5 列；compute_next_due 按 kind 分派 + snooze_until 优先 + reload 错过检测；collect_due 补跑窗 + 暂停分支按 schedule_kind 分派（interval 顺延 / daily-once 记 skipped）+ 触发推进按 kind；触发分派 notify/exec；等待队列（pending_execs）+ 完成出队；新命令 `reminders_snooze` / `tasks_skip_once` / `action_logs_list` |
| `lib.rs` | `pulsepet://task-result` emit_to；伪 session 注入 + notify 接线（agent="task"，不更新 AgentActivity/idle_hook）；**`RunEvent::Exit` 任务处置（P1-2）：遍历运行句柄 → kill 进程组 + action_logs 补写 failed（i18n 模板键 `App 退出中断`）**；启动时 running 态幂等清理（崩溃残留）；命令注册 |
| `i18n.rs` | summary 模板（ok/failed(N)/timeout/skipped/退出中断——**存模板键，展示时按当前语言渲染**，P3-3），zh/en |

**不改动**：状态机模块（伪 session 复用既有 apply_event/回收/合并，零改动）、HTTP 链路、todo 模块。

### 4.9 前端变更汇总

| 文件 | 变更 |
|---|---|
| `panel/Reminders.tsx` → `panel/Tasks.tsx`（改名重构） | 合并列表 + 条件表单 + 模板块 + 历史区 + 跳过本次；落 M2 设计系统 |
| `panel/registry.ts` / `Panel.tsx` | 核心 tab id `reminders` → `tasks`（labelKey `panel.tab.tasks`；`panel://tab` 直达兼容旧值映射） |
| `lib/reminders.ts` | ReminderRule 类型 +5 字段；ActionInput 校验纯函数（与 Rust validate 同规则）；调度摘要文案纯函数（`tasks.summary*`） |
| `lib/reminder-bridge.ts` | snooze 按钮动作 + `dismissed_via='snooze'` 结案回报；**`pulsepet://task-result` 监听 → M2 critical 入队**（P1-3） |
| `pet/Bubble.tsx` | critical snooze 按钮（hover 浮现） |
| `lib/i18n.ts` | `tasks.*` 命名空间（表单/徽标/摘要/历史/模板/snooze）+ `panel.tab.tasks` + **`panel.agentTask`（状态芯片「定时任务」文案，N4 归位——芯片在前端渲染）**；`reminders.*` 存量保留 |

### 4.10 数据库迁移注意

- 003 为**加列 + 新表**，无重建表语句（002 的 DROP/RENAME 模式不重演）——全部可事务化，A1 约定满足；
- 既有行默认值兼容（v1 行为零变化）；
- `action_params` 为 JSON 文本，Rust 侧 serde_json 解析失败 → validate 拒绝保存（存量行不可能有，新写路径全过 validate）。

### 4.11 测试与验收（M4 Done 标准）

**单测**：

| 域 | 用例 |
|---|---|
| 调度纯函数 | daily next_due（当日未到/当日已过/跳过不匹配星期/weekdays NULL=每天）；once（未来时刻/已触发→MAX/schedule_at 过去→validate 拒绝）；补跑窗边界（差 14m59s 触发/15m01s skipped）；**snooze 重发语义（once 重发后回 MAX；daily 重发后下个匹配日；interval≥10min 重发链顺延——触发时 max() 无效的回归钉子，P1-1）**；snooze_until 优先级（触发后 next_due 已是未来仍被 snooze 覆盖）+ 触发清空；reload 错过检测（App 关闭跨过 schedule_at：窗内补跑/超窗 skipped；last_triggered_at 已晚于 schedule_at 不误报）；interval 分支 v1 断言全量保留（回归） |
| collect_due | daily/once 到期触发；超窗 skipped（exec 写 action_logs·notify 不写；**两来源 skipped 均写 last_triggered_at + 推进 next_due——暂停多 tick 只记一次、skipped 后 CRUD reload 不重复、once skipped 后重启仍 MAX，N1**）；**跳过本次清空未过期 snooze_until（N2：reload 不复活被跳过的重发）**；暂停分支：interval 顺延（v1 回归）/ daily-once 记 skipped 且恢复后不补跑（SCOPE 字面）；并发上限（第 3 个任务入等待队列不写 running；完成出队） |
| `action_exec` | validate 全规则（command 空/超长/cwd 非目录/timeout 越界/kind 切换字段重置）；run：exit 0 → ok；exit 非 0 → failed(N)；超时 → killed 进程组 + failed(timeout) + output_tail 保留；输出超 2KB 截尾；skipped 构造（inject 时钟） |
| 伪 session | apply+notify 成对调用；agent="task"；心跳 15s 周期（注入时钟：正常心跳不回收；心跳延迟 >15s 时回收可观察）；不触发 AgentActivity/idle_hook（mock 断言零调用） |
| 集成（tempdir DB） | 迁移 003 幂等（版本 2→3 / 3 跳过）；v1 存量行默认值；action_logs 增删查 + 启动 running 幂等清理；snooze 全链路（写列/结案/next_due 覆盖）；**Exit 处置：kill 进程组后子进程不存在（waitpid 断言）+ action_logs 补写 failed** |
| i18n | tasks.* 键 zh/en 完备性；summary 模板键双语渲染 |

**实机验收**（TC-M4-xx）：

1. 合并 tab：v1 提醒数据升级后原样可见可编辑（v1 行为零变化）；notify 新建（三种调度）触发行为与 v1 等价（interval 窗口/去重/烟花叠加）；
2. daily 任务（设 1 分钟后 HH:MM）到点执行；once「明晚 9 点」类创建 → 触发后列表显示已完结；星期过滤（设今天+1 的星期 → 下周才触发）；
3. exec：`echo ok` 秒级成功 → 历史 ok + 气泡「任务完成」；`exit 3` → failed(3)；`sleep 600` + 超时 1 分钟 → 被终止 + output_tail；输出洪水（yes 循环）→ 截尾 2KB 不内存膨胀；
4. opencode 模板：拼出命令正确（--title/--auto 可选）；真实例程（如「数一下仓库有几个 md 文件」）执行 → 宠物细粒度状态随 agent 层变化（thinking/editing）→ 结束 success/failed + 气泡 + Token 页出现「pulsepet 例程:」会话；
5. 权限行为：模板不带 --auto 跑一个会触发权限的任务 → 例程不卡死、警告行进 output_tail、任务按拒绝结果继续/失败（S1 实证复验）；带 --auto → 放行执行；
6. 补跑：任务设在睡眠窗口内（合盖）→ 醒后 15 分钟内补跑一次 / 超窗列表出现 skipped 记录；**App 关闭跨过 schedule_at 后重启 → 同口径（reload 错过检测）**；暂停期间到期 → 记 skipped、恢复后不补跑（SCOPE 字面）；
7. snooze：提醒气泡点「稍后 10 分钟」→ 10 分钟后重现（重启 App 仍有效——snooze_until 持久化）；once 型 snooze 重发后完结；点宠物确认语义不变；
8. 跳过本次：daily 任务行操作「跳过本次」→ 本周期不触发、下个匹配日正常；
9. **退出处置（P1-2）**：`sleep` 型任务运行中退出 App → 子进程组被终止（`ps` 断言无残留）+ 历史区出现「App 退出中断」failed 记录；
10. 双语 + 深浅主题：新表单/徽标/历史/气泡按钮全量目验；状态芯片任务执行期显示「定时任务」。

### 4.12 风险与开放问题

| # | 风险/问题 | 处置 |
|---|---|---|
| R1 | 补跑窗内连环补跑（睡眠错过多个 daily 任务……daily 每天一次天然只有一个错过点；interval 不补；实际连环面小） | 并发上限 2 + once/daily 单错过点，风险可控；观察项 |
| R2 | `sh -c` 子进程树残留（kill 时机与组语义边界，如任务自身 daemonize） | setsid+组 kill 覆盖常规；自 daemonize 的任务属用户明确意图，不强收；记录 |
| R3 | Windows PowerShell 参数转义（引号/特殊字符） | validate 阶段对 command 做字符白名单外的警告提示（不阻止）；实机验证挂观察项（Windows 实机同批；**工期口径 macOS 先行、Windows 分支同构实现**，§4.0） |
| R4 | 例程会话把「今日 token」推高（例程本身的消耗计入） | 口径自洽（SCOPE 原文：例程会话进统计是特性非缺陷）；M5 来源标注后可分辨 |
| R5 | 伪 session 遗留（App 在执行中被强杀 → action_logs 永久 running） | 启动时幂等清理（status→failed，**summary 存 i18n 模板键按语言渲染**，P3-3）；正常退出走 Exit 处置（R8） |
| R6 | task error 抢镜（例程失败压过手头工作显示） | M4 接受（失败应被看见，30s 自然回收）；M6 最近活跃优先后精化 |
| R7 | `--auto` 放行危险命令（无人值守全自动） | 模板默认不勾 + 危险色警示 + 文档明示（个人工具，命令自写明文可见——SCOPE 原文信任模型） |
| R8 | **App 退出时运行中任务成为孤儿进程**（副作用命令继续后台执行；残留孤儿 + 下次重跑 = 双份执行；违反优雅降级） | `RunEvent::Exit` 遍历运行句柄 kill 进程组 + action_logs 补写 failed（P1-2，§4.8/§4.5）；崩溃强杀路径无 Exit → 孤儿进程残留为已知边界（R5 清日志、进程由用户/系统收；记录在案） |
| R9 | 「agent 层免费」为架构推演非实证（S4） | 实施首日用 `opencode run "echo hi"` + 事件探针验证（TC-M4-4 覆盖）；降级预案：插件不加载 → 两层合并退化为纯通用层（working/success/error 粗粒度），功能仍可用 |

### 4.13 不采用记录

| 项 | 理由 |
|---|---|
| schedule_kind 四枚举（weekly-at 独立） | weekly = daily × weekdays 过滤，判定逻辑同构；3 枚举语义不减、代码更少（§4.2 差异说明） |
| todo 派生行迁移到 once | M7 已验逻辑不动；行为等价双轨并存，统一另行裁定 |
| notify 型写 action_logs | 提醒记账已有 reminder_logs（气泡确认/烟花回报语义完整），双写徒增漂移面；执行历史语义属 exec |
| exec 前置确认（到点先问再跑） | SCOPE 裁定直接执行（个人工具、命令自写明文可见）；「跳过本次」是手动通道 |
| 补跑窗按动作类型分长 | 用户裁定维持 15 分钟单一口径（简单 > 精细） |
| 提醒错过也记 skipped | v1 语义（错过无害不记录）保留；skipped 记录专属「有信息损失」的 exec 型 |
| 定时任务独立 tab（不合并） | SCOPE 用户裁定（2026-08-20 两并一留）；列表徽标 + 条件表单承载差异 |
| 调度器并发改多线程重写 | 现有单线程 tick + 内存状态已满足（并发上限 2 在分派层排队）；重写无收益 |

### 4.14 评审记录（2026-08-23，reviewer subagent）

> 评审对象：本章节初稿。评审基准：V2-SCOPE §3.4/§5.8、v1 DESIGN §5、reminder_scheduler.rs/db.rs/migrations 全文、M1/M2/M3 上游定稿章节。
> **verdict: NEEDS REVISION**（P1×3 / P2×7 / P3×9 / 澄清×2；无 P0）。
> 处置结论：**全部采纳**——P1×3 全部修订正文；P2×7 全部落实；P3×9 全部落实；澄清×2 裁定消化（① notify/exec 同窗为用户既有裁定、标注偏离 SCOPE 字面；② 暂停行为对齐 SCOPE 字面「不跑不补记 skipped」，恢复后不补）。

#### 问题清单（摘要）与处置

**P1-1（已修，→ §4.3）**：snooze 用 `max(next_due, snooze_until)` 在主流场景是 no-op——触发时 next_due 已推进（interval → +interval；daily → 次日；once → MAX），snooze 永不生效，与验收 7 直接矛盾。修法：snooze = 重发本次，snooze_until **优先于**常规计算，next_due 直接置为 snooze_until；各 kind 重发后续推进逐一定义。

**P1-2（已修，→ §4.5/§4.8/§4.12 R8）**：exec 任务与 App 退出交互未设计——孤儿进程继续执行副作用命令 + 残留孤儿与重跑双份执行。修法：`RunEvent::Exit` 遍历运行句柄 kill 进程组 + action_logs 补写 failed；崩溃路径为已知边界（R8）。

**P1-3（已修，→ §4.5/§4.8/§4.9）**：结果气泡复用 `pulsepet://bubble` 与 M2 冻结桥层映射冲突（会被渲染成 info 级 token-report）。修法：新事件 `pulsepet://task-result` + 桥层 critical 入队；无 reminder 载荷（不写 reminder_logs/无 snooze 按钮）显式钉住。

**P2（7 项均落实）**：P2-4 暂停×补跑对齐 SCOPE 字面（不跑不补记 skipped，恢复后不补；删除错误引文）+ interval×snooze×暂停语义说明；P2-5 reload 错过检测（App 关闭/CRUD 跨过 schedule_at → 补跑窗判定/skipped 记录，「今早跑了没」重启后可对账）；P2-6 daily/once 行 interval_minutes 恒 0 + 全部 `>0` 分派点改按 schedule_kind + kind 切换字段重置；P2-7 伪 session agent="task" + 芯片「定时任务」文案 + apply 后必须 notify + 不污染 AgentActivity/idle_hook；P2-8 依赖落实（tokio +process/+signal、libc）；P2-9 心跳 15s（30s idle 回收的 1/2，裕量 15s）+ 措辞改「idle 回收」；P2-10 工期 1.5-2 周 + macOS 先行口径。

**P3（9 项均落实）**：S4 降级预案（R9）；并发队列细节（spawn 时刻写 running、排队无残留）；R5 summary 存 i18n 模板键；跳过×once×重启边界记录；snooze 仅 notify 显式；数据面改造行（struct/SELECT +5 列）；双 Success 双 emit 记录；once 过去时刻 validate 拒绝；「试一试」exec 行 = 真实执行定案。

**澄清项裁定**：① notify/exec 同窗补跑 = 用户 2026-08-23 既有裁定（Recommended 选项原文「notify/reminders 维持 15 分钟」），偏离 SCOPE「仅任务补跑」字面已在 §4.0 标注；② 暂停行为对齐 SCOPE 字面（不跑不补）。

#### 修订汇总（2026-08-23，按评审意见）

§4.0 工期口径 + 暂停/补跑裁定修正；§4.2 interval_minutes 存储约定 + kind 切换重置 + once 过去时刻拒绝；§4.3 补跑窗（notify/exec 同窗 + reload 错过检测 + 暂停对齐 SCOPE）/snooze 重写（重发语义 + 各 kind 后续）/跳过边界；§4.4 依赖 + 试一试定案；§4.5 流程图重写（等待队列/心跳 15s/task-result 事件/伪 session 定义/双 emit 记录）；§4.8 Cargo/数据面/Exit 处置/i18n 模板键行；§4.9 桥层行；§4.11 单测五行增补 + 验收 6/7/9/10 修订；§4.12 R3/R5 修订 + R8/R9 新增。

#### 复审记录（2026-08-23 第二轮，同 reviewer 续会话）

> 复核上轮 21 项：**19 项正确落实、澄清 2 项已消化**；P2-4/P2-5 落实但有残留缺陷（skipped 记账未闭环，升级为新 P1）。新增 N1(P1)/N2(P2)/N3-N7(P3)。
> **verdict: NEEDS REVISION**（仅 N1/N2 需改，均为一行文字钉住的设计补洞）。
> 处置：**全部采纳并已修**——N1：skipped（超窗/暂停）同步写 `last_triggered_at` + 推进 next_due + collect_due 返回 `(fired, skipped)` 由调用方落库（防重复记账/once 终态跨重启丢失）；N2：跳过本次清空未过期 snooze_until；N3：snooze 过期重启静默丢弃边界记录；N4：`panel.agentTask` 键移至前端 i18n 行；N5：去掉 tokio `signal` 冗余特性；N6：snooze×暂停措辞按 interval/daily-once 分开；N7：完成回写先移登记表 + Exit 只处置在表句柄（防竞写）。§4.3/§4.4/§4.8/§4.9/§4.11 已同步修订。

#### 三轮复审记录（2026-08-23 第三轮，同 reviewer 续会话）

> N1-N7 逐条核验：**全部正确落实**（N1 的三个重点交互推演自洽：skipped×reload 检测、暂停推进×恢复不补、snooze×错过检测）；N5 在 §4.8 变更表残留一处旧文（章内矛盾）。
> **verdict: APPROVED**——无新 P1/P2，剩余 5 项 P3 记录级微项「可在实施时顺手消化、无需再评审」。
> 处置（终轮微修，均已落正文）：P3-1 §4.8 Cargo 行同步（去 signal 残留）；P3-2 采纳方案 a——**新增 `last_skipped_at` 列**（skipped 判定与 last_triggered_at 分离，防「醒来手动补跑被 3min dedup 拒绝」，§4.2/§4.3 同步）；P3-3 结果气泡 text 拼接职责补位（lib.rs 拼接 + i18n 模板渲染，§4.5）；P3-4 跳过清 snooze 注明写表+内存同清；P3-5 暂停记 skipped 同款清 snooze_until。
>
> **M4 评审流程闭环：三轮（NEEDS REVISION → NEEDS REVISION → APPROVED）**，待用户终审定稿。

#### 终审记录（2026-08-23，用户）

- **评审点全部认可**：snooze 重发语义（once 重发后完结/daily 回轨道/interval 链顺延）、暂停 = 完全冻结（记 skipped 恢复后不补，与睡眠补跑的有意区分）、退出 App 杀运行中任务进程组 + 记「App 退出中断」、试一试对 exec = 真实执行、任务失败抢镜 30s（M6 精化）、`last_skipped_at` 独立列、并发上限 2、once 过去时刻拒绝、「pulsepet 例程:」标题前缀、工期 1.5-2 周 macOS 先行——照单定稿。
- **M4 定稿**（M1/M2/M3 已定稿；v2 六章已完成四章，余 M5/M6 待设计）。

## 5. M5：Token by agent（CC transcript 解析 + 统一视图，~1-1.5 周）

### 5.0 Spike 结论与裁定（2026-08-23，本机真实 transcript 实测）

> Spike：`~/.claude/projects/*.jsonl` 字段结构（SCOPE §5.1 前置），本机真实数据逐行解析验证。

| # | 事实 | 数据 | 设计含义 |
|---|---|---|---|
| S1 | 文件布局：`~/.claude/projects/<munged-cwd>/<sessionId>.jsonl`，**一文件一会话**（Windows 同结构 `%USERPROFILE%\.claude\projects\`） | ls 实测 | 扫描 = 递归一层目录 *.jsonl；sessionId = 文件名（与 CC hook input `session_id` 同源，汇报气泡可直连） |
| S2 | assistant 行含 `message.model` + `message.usage`；字段映射齐备：`input_tokens`→input、`output_tokens`→output、`cache_creation_input_tokens`→cache_write、`cache_read_input_tokens`→cache_read、`output_tokens_details.thinking_tokens`→reasoning | 逐行解析 | 与 TokenRow 同构，五维全量可得 |
| S3 | **重复写行陷阱**：同一 `message.id` 多次写行（thinking/text 两类事件行，usage 相同；实测 6 行 assistant → 去重后仅 3 条 message） | 去重验证 | **聚合必须按 `message.id` 去重、按行序取最后一条**（勿按 timestamp——尾行可能无 ts，见 S6）——不去重则 token 直接翻倍，本 spike 最大发现 |
| S4 | **无 cost 字段**（全文件零出现） | grep 验证 | cost 口径裁定依据（见下） |
| S5 | timestamp 为 **UTC ISO8601 带 Z 后缀**（`2026-08-22T23:49:25.856Z`） | 实测 | 与 opencode.db 的 epoch-ms-local 不同——聚合到本地日需 chrono 时区转换（`DateTime<Utc> → Local`） |
| S6 | **事件行**（user/assistant/attachment/system）富上下文：`cwd`（项目目录，basename 即项目名）、`gitBranch`、`isSidechain`（**子代理标记**，彩蛋池免费数据源再+1）、`parentUuid` 链；**非事件行（mode/permission-mode/file-history-snapshot/last-prompt 等）无 timestamp/cwd**（实测 25 行中 7 行）——时间戳/项目提取必须只看含字段的事件行 | 字段全集 + 逐行验证 | 项目维度免费；isSidechain 行照常计入（子代理 token 属会话用量）；P1-1 依据 |
| S7 | 本机体量：1 项目 1 会话 24KB/25 行（CC 刚启用）——**文件级缓存足矣，无需字节级 offset 增量** | du/wc | 解析策略：按 `(mtime, size)` 缓存解析结果，未变文件不重解析（agentpet 字节偏移方案降级为文件级，个人体量下等价） |
| S8 | user 行 `message.content` 有 string（真实 prompt）与 tool_result 数组两种；首条 string prompt 可作会话标题（CC 官方 UI 同做法） | 实测 | 标题来源裁定依据 |

**裁定汇总**（用户 2026-08-23）：**CC 侧省略 cost**（KPI 费用卡计 opencode 真实值、CC 行显示 `—`——第三方 API key 下单价表永远不准，诚实优于假精确）；**CC 会话标题 = 首条用户 prompt 截断**（回退 sessionId 前 8 位）；**例程来源标注 = 识别 M4「pulsepet 例程:」标题前缀 + ⚡ 徽标**（零 schema 改动）。其余 SCOPE 已定项照单：统一视图 + agent 筛选、CC 会话汇报气泡、CC hook 工具级气泡接入（M3 R7 预留）。

### 5.1 目标与范围

- Rust 新模块 `transcript.rs`：CC transcript 扫描/解析/文件级缓存，产出与 TokenRow 同构的会话行。
- `token_stats_query` 双源化：opencode SQL + CC 解析结果合并，`TokenRow` 增 `agent` 字段；day/week/range 聚合增 agent 维度。
- `token_stats_today` 双源化（M3 三层快捷查看自动覆盖 CC）。
- Token 页：agent 筛选两级交互（标题右侧 tab 单选 + 模型复选联动，R2 修订口径，M3 预留位落实）、会话列表 agent 标识列 + 例程 ⚡ 徽标、费用区「仅 opencode」注释小字。
- CC 会话汇报气泡：M1 idle 分流预留位兑现（CC idle → transcript 聚合 → 气泡）。
- CC hook 工具级气泡：M3 协议照抄接入（detail 携带）。
- **不含**：M6 抢镜（气泡 agent 标识 UI 属 M6，M5 只备数据）、子代理感知（彩蛋池，S6 数据已留）、单价表配置面（裁定不做）。

### 5.2 数据层：`transcript.rs`（Rust 新模块）

**扫描与解析**（纯函数 + 注入目录，tempdir 单测）：

```
transcript_scan(dir) → Vec<SessionFile>            // 递归一层 *.jsonl；排除 memory/ 子目录
                                                      //（CC 自有目录，非会话数据——P3-5）
parse_session(path) → Option<CcSessionRow>          // 单文件解析（坏行跳过不崩）
  - 逐行 JSON：type=="assistant" 的行收集 (message.id, 快照)
  - 按 message.id 去重、**按行序取最后一条**（S3；id 缺失的行按行级顶层 uuid 兜底去重，
    两者皆缺则独立计入——P3-4）
  - SUM 五维 usage → CcSessionRow
  - model 取最后一条 message.model（纯字符串，非 JSON——spike 复核注；会话内换模型罕见，末值代表）
  - title = 首条 type=="user" 且 content 为 string 的行截断（**chars().take(60)**，中文按字符不按字节
    ——P3-13；S8）；无 → sessionId 前 8 位
  - project = **首条含非空 cwd 的行**的 cwd → basename（CC 会话内 cwd 恒定，首值与众数等价且不受
    file-history-snapshot 等无 cwd 行稀释——P2-6 修订）；全无 cwd → None（回退标签）
  - time_created/time_updated = **首/末条含 timestamp 的行**（事件行）的 timestamp
    （UTC → epoch ms 本地口径统一转换，S5/S6——P1-1 修订：mode/last-prompt 等非事件行无 ts，
    按字面「首末行」取值会得 None → CC 行被时间过滤剔除、汇报气泡永不触发；
    分组/过滤用 time_updated **不受附件行影响**、护栏只看 assistant 行——两口径分离，N-7 注）
  - **last_assistant_ts** = 末条 assistant 行 timestamp（N-1：护栏专用字段——分组/过滤用
    time_updated（含附件/系统行），新鲜度护栏只看 assistant 行（对齐 opencode「最后 message
    写入时间」语义；实测本机末条 system 行晚于末条 assistant 3 分钟，护栏若用 time_updated
    会误判静置会话为新鲜）；附件行晚于末条 assistant 的差异由此字段天然分离）
```

**文件级缓存**（S7 裁定）：`TranscriptCache`（**managed state，窗口创建循环之前 manage `Arc<Mutex<TranscriptCache>>`**——issue #9 铁律 + N-5：spawn_blocking/thread::spawn 闭包需 `'static + Send`，Arc 包裹供后台线程 clone，照 session_state 的 Arc 模式，与 M3 token_stats_today 同款细节）：`Mutex<HashMap<PathBuf, (mtime, size, CcSessionRow)>>`（P2-1——查询命令与 CC idle hook 双方访问，同步原语设计层钉住）+ **`HashMap<String, PathBuf>` sessionId 索引**（P2-2——idle hook 只有 (agent, session_id)，从事件无法推导 munged 项目目录路径，靠二级索引定位文件）；查询时 mtime+size 未变直接用缓存，变了重解析。无常驻 watcher（查询驱动懒解析，与 opencode.db 即开即查同模式）。缓存缺失时（首查/idle 先于查询）由 scan 补建。

**目录探测**：`~/.claude/projects`（Windows `%USERPROFILE%\.claude\projects`）；目录不存在 → CC 源整体缺席（**静默**——CC 未安装/未使用是常态，不报错不提示，Token 页自然只显示 opencode）。

**双源容错（C1 裁定：部分源错误不整体遮蔽）**：opencode 源报错（no-database/legacy-storage/schema-mismatch）而 CC 源有数据时，`token_stats_query`/`token_stats_today` **降级返回 CC-only 结果**；**承载方式定案（N-4）**：返回体**包装为 `{rows: Vec<TokenRow>, degraded: Option<String>}` / `{today: TodayStats, degraded: Option<String>}`**——形状变化由同版本前后端锁步发布消化（兼容承诺修正为「**单源场景行为不变**」：CC 缺席时 rows/degraded 行为与 M3 单测钉住的原样一致，degraded 仅在 CC 有数据时为 Some）；**呈现范围**：degraded 横幅**仅 panel**（TokenStats.tsx 顶部细横幅），pet 侧三层（悬停卡/菜单/追加段）**静默显示 CC-only 数值、不呈现 degraded**（宠物不打扰原则）。双源全缺才走既有错误路径（M3「无库→—」语义保留给全缺态）。

**CC 行字段**：`agent: "claude-code"`（常量）、`cost: 0.0`（S4 口径：数据层恒 0，展示层 CC 显示 `—`）、`model_id`、`title`、`project_name`、五维 token、时间戳——与 opencode 会话行同构。

### 5.3 查询双源化与 agent 维度

| 查询 | 变更 |
|---|---|
| `query_by_session`（opencode） | TokenRow 增 `agent` 字段（恒 `"opencode"`）；与 CC 缓存的会话行合并（时间倒序统一排序） |
| `query_grouped`（day/week） | opencode SQL `GROUP BY day_expr, agent, model_id`（agent 恒单值，列+分组保持形状统一）；CC 侧在 Rust 内存按 `day × agent × model_id` 聚合（本地日转换 S5）；**week 标签复刻 SQLite `%Y-W%W` 语义**（自定义纯函数：周一起始的日历年周号——**勿用 chrono `iso_week()`**，ISO 年周与 `%W` 在跨年边界分叉会导致双源同周拆柱，P2-4）；两源 concat 返回 |
| `query_by_range` | CC 侧按 `agent × model_id` 聚合（无 day 维，与 opencode range 行形状一致——P3-6 明示） |
| `token_stats_today` | 双源合计（opencode SQL 当日聚合 + CC 缓存当日过滤求和）；M3 三层快捷查看（悬停卡/菜单/idle 追加段）自动覆盖 CC 用量 |
| `build_idle_report` | 不动（opencode 专用）；CC 汇报走新函数（§5.4） |

> **§14 修订（2026-08-29，V2-OPEN-ITEMS §十四）**：CC 侧 day/week/range/today 同步下沉 message 级——`transcript.rs` 的 `SessionState.usage_by_key` 值扩展为 `(usage5, 行 timestamp)`（去重语义不变），`finalize_state` 按 `local_day_label(ts)` 分桶产出 `CcSessionRow.by_day` 明细（ts 缺失兜底归会话 time_updated 日；桶 `first_ts` 取桶内最早消息时刻）；`cc_group_rows` day/week/range 与 today 改按桶聚合（窗口过滤在桶级 first_ts——custom 窗口双侧按天对齐故精确，preset 窗口 to=now 下桶内消息时刻不可能晚于已落盘解析时刻、同样精确；**不再以会话 time_updated 整行进/出窗**，跨天会话首日贡献不再消失/窗口漏计修复）。model 归属保持会话级（末条 assistant 的 model——只改时间归属）；session 视图与 `last_assistant_ts` 护栏不变；增量解析路径（方案 α）随 SessionState 值类型扩展自动继承（`alpha_incremental_matches_full_reparse` 逐字段对账自动覆盖 by_day）。

**前端聚合影响**：M3 的 buckets/KPI 在 grouped 行上 SUM——双源合并后自动是全 agent 合计；模型 chip 来源 distinct(model_id) 自动含 CC 模型（`deepseek-v4-pro` 等双源同模型自然归并——模型维度跨 agent 合法，与 GLM 平台心智一致）。

**AgentAdapter 收口（SCOPE §5.4 遗留，本里程碑裁定：不收口）**：token 源实现留在 Rust（token_stats.rs=opencode / transcript.rs=claude-code），TS `AgentAdapter.tokenSource` 维持声明性——强行收口需在 TS 建平行解析层或 Rust 建 adapter trait，双方案都增层级不减复杂度；记录于不采用（§5.10）。

### 5.4 CC 会话汇报气泡（M1 预留位兑现）

M1 §1.5 idle hook 分流预留（`agent=="claude-code"` 无动作）本里程碑填充：

```
CC hook Stop 事件 → /state(idle, agent=claude-code)
  → idle_hook 分支（http_server 请求线程仅做派发，解析在后台线程）：
     经 TranscriptCache 的 sessionId 索引定位文件（P2-2）→
     std::thread::spawn 线程内直接完成「解析（缓存未命中时 scan 补建）→ 护栏判定 →
     apply + emit」（AppHandle/State 的 Arc 均 Send 可移入——N-3：不 join 回 http 线程，
     免阻塞派发初衷；CC idle 低频、线程开销可忽略）
  → 新鲜度护栏：末条 assistant 行 timestamp 距 idle 事件 < 60s（对齐 opencode 口径）
  → 会话五维有非零用量 →
     ① 注入 success 状态：apply_event（**复合键 `claude-code:{sessionId}`**——M1 §1.5 键构造，
        同 v1 idle hook 伪路径 lib.rs make_idle_hook 先例，P2-5）+ notify
     ② 气泡「本次会话消耗 token Xk」（§十二 F1 修订：单总量口径 = in+out+
        cache_read，原「Xk input / Yk output」无 cost 双模板已收敛，与 opencode 同模板）
        + 「 · 今日 T」追加段（token_stats_today 双源合计，与 opencode 同模板）
  → 无记录/全零/陈旧 → 静默跳过（对齐 TC-TK-12 口径）
```

- 气泡经 `pulsepet://bubble`（info 级 source="token-report"——与 opencode 汇报同源同级，M2 同源合并 10s 窗口自然防双发刷屏）；
- **竞态诚实口径（P2-3 修订）**：护栏只防「陈旧」，不防「尾行未 flush」——Stop 事件先于 transcript 尾行落盘时，解析结果可能**欠计最后一条 message**（对齐 R3「截至上次快照」口径，接受；对齐 opencode 逐 message 增量的同语义）；文件缺席/无 assistant 行/全零才静默跳过。可选增强（实施时按实测决定）：idle 后延迟 1-2s 再查一次，低成本消除欠计。

### 5.5 CC hook 工具级气泡接入（M3 R7 兑现）

M3 协议（`detail="tplId:param"`，§3.7.1）照抄到 `claude-code-hook.js`：

| CC 事件 | 工具 | tpl | param 提取 |
|---|---|---|---|
| PreToolUse | Edit/Write/MultiEdit/NotebookEdit | `edit` | file_path → basename |
| PreToolUse | Bash | `bash` | command → 剥 KEY=value + 首词 basename（M3 强化规则同款） |
| PreToolUse | Read | `read` | file_path → basename |
| PreToolUse | Grep/Glob | `search` | pattern → 净化 ≤40 |
| PreToolUse | WebFetch/WebSearch | `web` | url/query → hostname |

- 一次性进程无进程内节流状态——**App 侧 10s 同源合并（M2 ambient）即节流**，CC hook 不做文件级冷却（与 M1 §1.3.2「不做节流」裁定延续，先例说明在彼）；detail 桶概念仅存在于 opencode 常驻插件。
- 发布联动：CC hook 变更随 App 重装（M1 安装器内嵌单一来源），无手动重装负担（与 opencode 插件不同）。

### 5.6 Token 页 UI（M3 预留位落实）

> **口径修订（2026-08-27，用户反馈 R1 偏差后方案 A 终审）**：agent 筛选由原设计的「filter-row 第二组复选 chip」改为「标题右侧 tab 单选 + 模型复选框联动」两级交互——用户意图是两级筛选（先 agent 维度、再模型维度），R1 按本节原文实现的两组复选框并排属需求偏差，R2 已按修订口径交付（commit `ca2b600`）。验收口径见 V2-TEST-CASES TC-M5-04/TC-M5-10 修订注记。

- **agent 维度 tab（分段单选）**：置于「Token 时序（按天/按周）」标题 `<h3>` 右侧同一行（`.token-chart-head` flex 布局）；交互照抄 Settings 主题三档 `theme-seg` 模式（`role="radiogroup"` + 每项 `role="radio"` + `aria-checked` + `seg active`）。选项 = **「全部」（`token.agent.all`，恒显，默认选中）** + 仅有数据的 agent（无数据不渲染；仅一个 agent 有数据时「全部」仍并列恒显）；数据刷新后所选 agent 无数据 → 回落「全部」。
- **模型复选框联动收窄**：`filter-row` 只保留模型组（唯一一组复选）；`computeModelChips` 增可选 `agentFilter` 参数——选中「全部」= 所有 agent 的模型并集（原行为）；选中具体 agent = 收窄为该 agent 有数据的模型；**切换 tab 时模型勾选重置为全选**（不保留跨 tab 隐性勾选）。作用域**仅柱图**（与模型筛选一致，M3 E 口径，KPI/会话列表不随 tab 变化）；`computeStackedBars` 的 `agentFilter` 参数位填实现（具体 agent = 单元素集 /「全部」= 不传，M3 N12 钉子语义保持）。原 noAgents 空集空态随单选交互不可达（`token.chart.noAgents` 键 zh/en 已清退；模型空集空态口径不变）。
- **会话列表**：增 agent 标识微列（`oc` / `cc` 等宽小字徽标，i18n title 提示全名）；**例程 ⚡ 徽标**：`title.startsWith("pulsepet 例程:")` → 标题前 ⚡ 图标（title 属性「定时任务例程」）；CC 行标题 = 首 prompt（§5.2）。
- **费用口径标注**：M4 R1 用户裁定移除 cost KPI 卡后，「仅 opencode」标注以 **KPI 区注释小字**（`token-kpi-note`）承载（CC 恒 0 口径标注）；会话列表 CC 行 cost 列显示 `—`。
- 深浅主题：新增元素全走 token（M2 系统）。

### 5.7 Rust / 前端变更汇总

| 模块 | 变更 |
|---|---|
| `transcript.rs`（新） | §5.2 全部（解析纯函数 + TranscriptCache managed state + 目录探测）；`cargo test` 单测主战场 |
| `token_stats.rs` | TokenRow + `agent` 字段（serde 同步）；四查询 agent 维度（§5.3）；`token_stats_today` 双源；CC idle 汇报函数（`build_cc_idle_report`）；**`token_stats_query`/`token_stats_today` 改 `async fn` + transcript 扫描/解析进 `spawn_blocking`**（P2-1——IPC 契约不变（签名/返回体兼容），主线程不承 IO；opencode SQL 同入 blocking 池顺带统一）；双源容错 degraded 字段（C1） |
| `lib.rs` | TranscriptCache manage（窗口创建前）；idle hook 分支派发 CC 汇报（http 线程只派发、解析在后台线程，P2-2）；命令注册（签名不变，返回体 +agent/+degraded 向后兼容） |
| `opencode-plugin/claude-code-hook.js` | §5.5 detail 携带（extractDetailParam 照抄 M3 规则） |
| `lib/token-stats.ts` | TokenRow +agent 字段；CC 类型常量；**fetchTokenRows/fetchTodayStats 解析 `{rows,degraded}`/`{today,degraded}` 包装**（N-4） |
| `panel/TokenStats.tsx` | agent tab 两级筛选（标题右侧单选 + 模型复选联动，R2 修订口径）/会话列表 agent 列 + ⚡ 徽标/费用区注释小字/CC cost `—`/**degraded 细横幅**（仅 panel；pet 三层静默显示 CC-only 数值，§5.2 定案） |
| `lib/token-chart.ts` | `agentFilter` 实现（参数位已在） |
| `lib/i18n.ts` + `i18n.rs` | `token.agent.*`（chip/列徽标）、`token.costOpencodeOnly`、`token.taskBadge`、CC 汇报气泡模板（zh/en；Rust 侧 build_cc_idle_report 模板入 i18n.rs） |

**数据库：零迁移**（TranscriptCache 纯内存；无新表新列）。

### 5.8 测试与验收（M5 Done 标准）

**单测**：

| 域 | 用例 |
|---|---|
| `transcript.rs`（tempdir 注入） | **message.id 去重**（6 行含 thinking/text 重复行 → 3 条 SUM，按行序取末条——S3 回归钉子）；五维映射；坏行/空文件/非 JSON 行跳过不崩；**首末行无 timestamp（mode/last-prompt 包夹）→ 时间戳取自首/末条含 ts 事件行**（P1-1 钉子）；UTC→本地日转换（跨日边界注入时区）；**week 标签复刻 %W 语义**（2026-12-28/2027-01-01/2027-01-04 跨年对齐断言，P2-4）；title 首 prompt 截断（**中文 60 字符**）/无 prompt 回退；**首条含 cwd 行取 basename**（含无 cwd 的 snapshot 行稀释 fixture，P2-6）；mtime+size 缓存命中/失效；sessionId 索引定位；memory/ 子目录排除；目录不存在 → 空结果 |
| `token_stats.rs` | grouped 行 agent 维度（opencode 恒单值 + CC 内存聚合合并）；today 双源合计；`build_cc_idle_report`（新鲜度护栏/**last_assistant_ts 字段消费**（N-1）/全零静默/无 cost 段文案）；**degraded 双源容错**（opencode 错×CC 有数据 → Ok(CC-only)+degraded=Some；双源全缺 → 既有错误码透传；CC 缺席 → rows 原样 + degraded=None（M3 回归），N-4） |
| `token-chart` | agentFilter 实现用例（具体 agent 单元素收窄/不传=全量——M3 N12 钉子扩展） |
| 前端 | CC cost `—` 渲染；例程前缀匹配 ⚡；agent tab 单选 + 模型复选框联动逻辑 |
| `claude-code-hook.js` | extractDetailParam CC 工具族五类（basename/首词剥赋值/hostname——M3 用例平移） |
| i18n | 新键 zh/en 完备性 |

**实机验收**（TC-M5-xx，N-6 重排）：

1. 真实 CC 会话（本机 DataAgent 项目已有存量）→ Token 页今日/7d 出现 CC 会话行（首 prompt 标题 + `cc` 徽标 + cost `—`）；KPI 总量含 CC；费用区「仅 opencode」注释小字可见（M4 后形态）；**M3 三层交叉断言双源复验**（悬停卡 = 面板今日 KPI = 菜单，会话静止窗口内——P3-10；悬停/菜单在 degraded 态静默显示 CC-only 数值）；
2. agent tab：切具体 agent → 柱图剔除其它 agent 数据、模型复选框收窄为该 agent 模型且重置全选，KPI/会话列表不变（E 口径）；双源同模型（deepseek）在模型 chip 自然归并（tooltip 跨源说明实施时对齐，P3-11）；agent 空集空态随单选交互不可达（`token.chart.noAgents` 已清退，原 P3-12 口径作废留注）；
3. CC 会话结束 → 宠物气泡「[cc] 本次会话消耗 token Xk · 今日 T」（§十二 F1 修订：单总量口径，原 input/output 双模板收敛）；opencode 会话结束气泡无回归（双发时同源合并）；
4. CC 工具级气泡：CC 会话内编辑文件/跑命令 →「正在编辑 X」/「正在跑 npm」（与 opencode 同模板同 ambient 行为）；开关对双 agent 统一生效；
5. 例程徽标：M4 定时任务跑一次 opencode run → Token 页新会话带 ⚡（前提 = M4 验收 4 回填，R8）；
6. **CC 目录改名/删除（模拟未安装）**→ Token 页安静回退 opencode-only，无错误横幅（单源场景行为不变——N-4 兼容口径）；
7. **双源容错（C1）**：临时改名 opencode.db 模拟缺席 → Token 页显示 CC-only 数据 + 「opencode 源不可用」细横幅（不遮蔽内容）；恢复后正常；
8. 深浅主题/双语全量目验。

### 5.9 风险与开放问题

| # | 风险/问题 | 处置 |
|---|---|---|
| R1 | CC transcript 格式随版本演进（字段改名/新增行类型） | 解析防御式（未知行类型跳过、usage 缺字段按 0）；坏文件不崩（优雅降级）；CC 升级后字段变化属外部依赖 breaking，doctor 不可达——靠静默空结果 + 用户反馈发现 |
| R2 | 大 transcript 文件（长会话 MB 级）首次全量解析延迟 | 文件级缓存后仅首次；~MB JSONL 解析 <100ms 量级；查询异步（spawn_blocking 沿 M3 纪律）；观察项 |
| R3 | 会话进行中查询：transcript 尾部仍在写（部分用量） | 展示口径=「截至上次快照」——与 opencode.db 逐 message 增量同语义（TC-TK-11），无一致性义务 |
| R4 | mtime 缓存与 CC 原子写（tmp+rename）的交互 | rename 落位的是**新写的 tmp 文件**（mtime 为新）→ 缓存自动失效，无窗口问题（P3-8 措辞修正） |
| R5 | CC 会话无 project 概念差异（cwd 首值 vs opencode project 表——N-2 措辞同步 §5.2） | 两源 project_name 语义统一为「目录 basename」；global/未知回退标签复用 M3 |
| R6 | CC hook detail 与 opencode detail 双源并发 | App 侧同源合并键 `tool:<tpl>` 跨 agent 共桶——双 agent 同工具 10s 内只出一条（可接受：同工具播报本就同义）；记录在案 |
| R7 | 时区口径边缘：SQLite `'localtime'` 受 TZ 环境变量影响、chrono `Local` 走系统探测，TZ 显式设置时可能分叉（P3-7） | 本机场景大概率一致；观察项（不一致症状=双源同日拆柱，易发现） |
| R8 | 例程 ⚡ 徽标的可行性前提：opencode `--title` 是否被自动摘要覆盖（C2——M3 S5 实测 title 为自动摘要生成） | **前提 = M4 §4.11 验收 4 实测确认 `--title "pulsepet 例程: …"` 保留**（显式指定优先于自动摘要是 opencode 语义，但需实证回填）；若失效：备选 = 例程识别改「M4 记录 spawn 时间窗 + cwd」粗匹配（精度降级可接受），M5 实施时按 M4 验收结果二选一 |

### 5.10 不采用记录

| 项 | 理由 |
|---|---|
| CC 自配单价表估算 cost | 用户裁定省略（第三方 key 下永远不准；诚实优于假精确） |
| 字节偏移增量解析（agentpet 方案） | 文件级 mtime+size 缓存在个人体量下等价（S7），实现减半；文件增长到影响查询时再升级（观察项 R2） |
| AgentAdapter 收口 token 源实现（SCOPE §5.4） | Rust 双模块（token_stats/transcript）+ TS 声明性 tokenSource 已是最简分层；收口需建平行抽象层，复杂度净增 |
| transcript 文件 watcher 常驻 | 查询驱动懒解析与既有模式一致；常驻 watcher 增后台线程无收益 |
| CC 会话气泡区分 agent 标识 | 气泡 agent 标识 UI 属 M6（SCOPE §3.6）；M5 数据已备（displayAgent/事件 payload） |
| 子代理（isSidechain）单独统计 | 彩蛋池；数据已留（S6），统计口径（计入会话）已定 |
| 双源同名项目 basename 的歧义处理 | CC cwd basename 与 opencode basename(worktree) 同口径同缺陷（两项目同名合并显示），双源表现一致无新问题（P3-16 记录）；命中时靠会话行 agent 徽标区分 |

### 5.11 评审记录（2026-08-23，reviewer subagent）

> 评审对象：本章节初稿。评审基准：V2-SCOPE §3.5/§5.1/§5.4、M1-M4 上游定稿预留位、现状源码、本机 transcript 只读复核（S1-S8，发现 S6 有重要出入）。
> **verdict: NEEDS REVISION**（P1×1 / P2×6 / P3×16 / 澄清×2；无 P0）。
> 处置结论：**全部采纳**——P1/P2 全部修订正文；P3×16 全部落实；澄清×2 裁定消化（C1 双源容错降级；C2 例程徽标以 M4 验收 4 为可行性前提 + 失效备选，R8 承载）。评审人总体评价：「范围与前置全部落实、上游预留位引用基本准确、message.id 去重方案经实测验证正确、不采用记录完备。修订成本低（P1 为一句话措辞 + 单测补钉），修复后可直接进入实施」。

#### 问题清单（摘要）与处置

**P1-1（已修，→ §5.0 S6/§5.2/§5.4）**：「首末行 timestamp」被 spike 自身数据证伪——实测 25 行中 7 行（mode/permission-mode/atis-latch/file-history-snapshot×3/last-prompt）无 timestamp，首行末行均在其中；按字面实现 CC 行 time_updated=None → 全查询时间过滤剔除 + 汇报气泡永不触发。修法：时间戳取自**首/末条含 timestamp 的事件行**；S6 改「事件行富上下文」；护栏口径统一「末条 assistant 行」；单测补钉。

**P2（6 项均落实）**：P2-1 `token_stats_query/today` 改 async fn + spawn_blocking 落变更表（IPC 契约不变）+ TranscriptCache 加 Mutex；P2-2 sessionId→PathBuf 二级索引 + http 线程只派发解析在后台线程；P2-3 竞态改诚实口径（护栏只防陈旧不防尾行未 flush，欠计接受对齐 R3；可选延迟 1-2s 复查增强）；P2-4 CC week 标签复刻 SQLite %Y-W%W（勿用 ISO 周）+ 跨年单测；P2-5 apply_event 复合键 `claude-code:{sessionId}` + 引用改 v1 先例；P2-6 cwd 众数 → 首条含非空 cwd 行（snapshot 行稀释防御）。

**P3（16 项均落实）**：M1 §1.3.2 引用修正；不采用节号修正；S3 机制措辞（thinking/text 双行，按行序取末条）；uuid 兜底键明确（行级顶层）；memory/ 子目录排除；range 维度明示 agent×model；TZ 分叉观察项（R7）；R4 措辞；标题补工期；三层交叉断言双源复验；model chip tooltip；agent 空集空态复用；title chars().take(60) 中文单测；三组单测补钉；S1 括号；同名 basename 记录。

**澄清项裁定**：C1 双源容错——opencode 源错误 × CC 有数据时**降级返回 CC-only + degraded 横幅**（部分源错误不整体遮蔽；双源全缺才走既有错误路径，M3「无库→—」语义保留）；C2 例程徽标可行性前提 = M4 验收 4 实测 `--title` 保留，失效备选 = spawn 时间窗 + cwd 粗匹配（R8 承载）。

#### 修订汇总（2026-08-23，按评审意见）

§5.0 标题工期/S1 括号/S3 措辞/S6 事件行限定；§5.2 时间戳规则重写/uuid 兜底/memory 排除/首 cwd 行/chars(60)/缓存 Mutex+sessionId 索引/双源容错段；§5.3 week 复刻 %W/range 明示/不采用节号；§5.4 后台线程派发/复合键/竞态诚实口径；§5.7 async 化落表/idle 派发行；§5.8 单测六项补钉/验收 1/6/6b 增补；§5.9 R4 措辞/R7 时区/R8 例程前提；§5.10 同名 basename；M1 §1.3.2 引用修正。

#### 复审记录（2026-08-23 第二轮，同 reviewer 续会话）

> 复核第一轮 25 项：**全部正确落实**（§5.11 处置声明与正文一致无出入）；重点推演确认——「事件行 time_updated × assistant 行护栏」双口径分离**是正确选择**（实测末条 system 行晚于末条 assistant 3 分钟，护栏若用 time_updated 会误判静置会话为新鲜）；async 化 IPC 兼容成立；索引维护时机覆盖；C1 回归安全（CC 缺席 = M3 行为原样）。
> **verdict: APPROVED WITH COMMENTS**——新发现 P2×1（N-4：degraded 承载方式与「返回体兼容」声明矛盾 + 前端变更表漏行）+ P3×6（N-1/N-2/N-3/N-5/N-6/N-7），「均为可在一轮微修内消化的实施前补钉，不影响方案成立，无需再开新评审轮次」。
> 处置：**全部采纳并已修**——N-4 degraded 承载定案 `{rows,degraded}` 包装（兼容承诺修正为「单源场景行为不变」）+ pet 三层静默呈现界定 + 前端两行补全 + 单测三用例；N-1 `last_assistant_ts` 字段补入解析清单（护栏专用，勿改用 time_updated）；N-2 R5 措辞同步；N-3 spawn 线程内直接完成 apply+emit（不 join）；N-5 manage 形态 `Arc<Mutex<…>>`（照 session_state 模式）；N-6 验收重排 1-8 + item 6 拆分；N-7 附件行口径分离注记。
>
> **M5 评审流程闭环：两轮（NEEDS REVISION → APPROVED WITH COMMENTS）**，待用户终审定稿。

#### 终审记录（2026-08-23，用户）

- **评审点全部认可**：CC cost `—` + 费用卡仅 opencode（用户裁定）、双源容错降级 + pet 三层静默呈现（C1/N-4）、返回体 `{rows,degraded}` 包装与「单源场景行为不变」兼容口径、CC 竞态欠计接受（可选延迟复查）、例程 ⚡ 徽标前提挂 M4 验收 4 回填 + 失效备选（R8）、`last_assistant_ts` 护栏专用字段、AgentAdapter 不收口 / 文件级缓存 / 同工具播报共桶等不采用取向——照单定稿。
- **M5 定稿**（M1-M4 已定稿；v2 六章余 M6 待设计）。

## 6. M6：多 agent × 多 session 抢镜（~0.5-1 周）

### 6.0 设计输入与裁定（2026-08-23，用户）

| 决策点 | 裁定 |
|---|---|
| 活跃窗口 | **10s**（对齐 opencode 流式心跳实际节奏——插件 reaction 桶 10s 冷却 → 生成中会话约每 10s 一事件；活跃语义 =「正在产出」；SCOPE 原文示例值 5s 太严会让生成中会话掉窗） |
| 合并算法 | **两层**：①窗口内有事件的 session 间按既有优先级合并；②窗口空时显示**最近活跃 session** 的状态（不做全量优先级合并——陈旧 error 会复活抢镜） |
| 气泡 agent 标识 | **前置等宽徽标 `[oc]`/`[cc]`/`[task]`**（token 汇报/工具播报携带；提醒不加——非 agent 来源；task 结果气泡用 `[task]` 自身徽标） |
| 悬停卡 | 今日汇总卡追加 **agent 分布行**「oc 39M · cc 3M」（双 agent 有数据才显示）〔注：本表为定稿时点裁定留档；悬停卡后随 M3 2026-08-25 裁定移除，分布行呈现面已改右键菜单子行——见 §6.2 修订注记〕 |

SCOPE §3.6 其余照单：与 M4 例程会话的抢镜协同随本章定（§6.1 场景表）；落 M2 重构后的新气泡组件。

### 6.1 合并算法（`session_state.rs` display() 改造）

**现状**：`display()` = 全量 `max_by_key(priority)`（v1；M2 已扩展返回 `DisplayState{kind, agent}`）。

**M6 两层算法**（纯函数，`ACTIVITY_WINDOW_MS = 10_000`）：

```
fn display(&self, now: Instant) -> DisplayState:
  ①活跃集 = sessions 中 last_event_at >= now - 10s
  ②活跃集非空 → 活跃集内 max_by_key(priority)（既有优先级表不变）；
    **同 priority 平局（= 同 kind 不同 agent/session）取 last_event_at 最新者**
    （与 fallback 互为镜像的字典序：活跃集按 (priority, last_event_at) 取最大、
    fallback 按 (last_event_at, priority) 取最大——否则 HashMap 迭代序任意决定胜者，
    芯片 agent 无因跳变，P2-2）
  ③活跃集空 → 全量 sessions 中 last_event_at 最大者（平局取 priority 高者）
  ④sessions 空 → Idle（v1 语义）
```

**行为对照**（设计自检）：

| 场景 | v1 | M6 |
|---|---|---|
| 会话 A working（事件每 10s）+ 会话 B error（10s 前出错后静默） | error 持续抢镜至 B 被回收 | B 掉窗后 A 的 working 立即接管（**核心修复**） |
| A 与 B 同时活跃（均在窗内），B error | error 显示（优先级） | 同左——正在发生的 error 本就该被看见 |
| 单会话长生成（CC 无流式事件、静默 40s） | 状态机兜底链 thinking→working→idle | 同左（掉窗后 fallback = 自己最近活跃，显示不变） |
| M4 例程伪 session（15s 心跳）× 手头会话（10s 事件） | 例程 error 抢镜 30s（M4 R6 接受） | **精化（有前置条件，P1-1/P2-1 修订）**：手头会话窗内持续有事件时，例程 error 在窗内显示 ≤10s 让位、working(1) 压不过手头 editing/testing；心跳 15s > 窗口 10s 的系统性交互——心跳间隙例程掉窗但 fallback 仍选它（最近活跃）→ **手头静默期间（相邻两事件之间，含 >10s 长间隙）例程 working 连续显示（fallback 消除心跳节律闪烁）**，手头事件到达即夺回——整体呈随手头事件节律的周期性交替（见 R1），「手头优先、例程兜底」在此语义下成立 |
| **solo error 边界（P1-1）**：例程失败时无其他会话/其他会话均更旧 | error 显示 30s（至回收） | **同左，有意行为**——fallback（最近活跃）仍选中它，显示至 30s 回收；「失败应被看见」（M4 R6 语义），与 v1 无回归无改善，非本里程碑问题域 |
| 例程结束 success(2) × 手头 working(1) 同窗 | success 抢镜 | 同左（完成闪光一现，掉窗即回；可接受） |

**归属与兜底**：`DisplayState.agent` 取胜者的 `SessionRecord.agent`（M1 §1.5 已备）；sessions 空 → Idle 时 agent 为空，前端芯片降级不显示。display 成为时间函数后，**无事件时**的显示切换（掉窗让位瞬间）依赖既有 1s 后台循环的 notify 兜底（延迟 ≤1s）——该循环对 M6 语义不可或缺，注释防未来被优化掉（P3-6）。

**改造面**：`display(&self)` → `display(&self, now: Instant)`（注入时钟保单测）；生产调用点两处适配传 `Instant::now()`——`DisplayNotifier::notify` 与 lib.rs `get_display_state` 命令（P2-3）；tick 回收/瞬态超时/优先级表**零改动**。

**已知边界**：窗口翻转会带来更频繁的显示状态切换（v1 一场 error 停 30s，M6 可能 error→working→error 交替——仅当双 session 事件交错时发生，节流（插件侧/事件驱动）天然限频；观察项）。

### 6.2 气泡 agent 标识 + 今日 agent 分布行

> 〔修订注记 2026-08-27：本节原按 M6 定稿时点写「悬停卡 agent 分布行（M3 HoverToday 扩展）」；HoverToday 已随 M3 2026-08-25 用户裁定移除（§3.4 修订留档，晚于 M6 定稿 08-23）。M6 实施按后裁定优先——**数据层照本节设计原样实现**（`by_agent` 落 TodayStats/同口径/降序/零数据省略），**呈现层落右键菜单「今日 token」信息项子行**（`lib/pet-menu.ts` + `pet/PetMenu.tsx`，经 `pet/todayToken.ts` 30s 缓存）；i18n 键名 `token.hoverAgent` 按定稿保留（名实轻微不符，裁定不改）。下文本段已按实际落点改写，其余小节不受影响。〕

**气泡徽标**（M6 为 M2 气泡组件新增 `agent?: string` 可选字段）：

| 气泡来源 | 徽标 | 实现 |
|---|---|---|
| token 会话汇报（opencode） | `[oc]` | Rust `pulsepet://bubble` payload 补 `agent` 字段（M1 事件已带，透传即可） |
| token 会话汇报（CC，M5） | `[cc]` | 同上（M5 build_cc_idle_report 补字段） |
| 工具级播报（双 agent） | `[oc]`/`[cc]` | **`pulsepet://tool-bubble` payload 补 agent**（`/state` 请求已带 agent，Rust 透传——M3 设计时事件未带，本里程碑补齐） |
| 定时任务结果（M4） | `[task]` | `pulsepet://task-result` payload 补 `agent:"task"`（字段已隐含，显式化） |
| 提醒气泡（reminder/todo 派生） | 无 | 非 agent 来源，不加 |

- **实现载体（P2-4）**：`agent` 是 **`BubbleItem` 新增可选字段**（M2 §2.6.2 结构本无此字段，M6 新增）——随条目顶替回队/同源合并流转（**合并键不含 agent，徽标以幸存新条目为准**，P3-4）；渲染在 Bubble.tsx 前置等宽小字（`[oc] `），i18n 不翻译（技术名约定）；`task` 映射 `[task]`（与 M4 芯片「定时任务」文案并存——徽标极简、芯片全称）。**徽标形态与 M5 会话列表无括号 `oc`/`cc` 刻意不同**（气泡=[oc] 终端习惯、列表=oc 列徽标），勿「统一」（P3-2）。
- CC hook detail 排放（M5 §5.5）payload 天然可带 agent（hook 进程自知身份），无额外改动。

**今日 agent 分布行**（~~悬停卡 M3 HoverToday 扩展~~〔修订 2026-08-27：HoverToday 已移除，呈现面 = 右键菜单信息项子行〕）：

- `token_stats_today` 返回体**在 TodayStats 结构内追加 `by_agent: Vec<{agent, total}>`**（落 TodayStats 内非顶层——M5 N-4 包装 `{today, degraded}` 的 today 即此结构，P3-3；有数据的 agent 降序；**total 口径 = 今日总量同口径**——in+out+cacheRead、不含 reasoning、mock 过滤（M3/M5 一致），三层数值交叉断言由此成立）；
- 右键菜单「今日 token」信息项在数值下追加子行 `oc 39M · cc 3M`（单项时**不显示**——单 agent 无辨识需求）；30s 缓存口径不变。

### 6.3 变更汇总

| 模块 | 变更 |
|---|---|
| `session_state.rs` | `display(now)` 两层算法 + `ACTIVITY_WINDOW_MS`；单测新增（两层的全部场景对照表）+ 既有 display 断言修订（同刻事件下行为不变，跨时刻用例改注入时钟） |
| `http_server.rs` | `/state` 事件透传链路把 agent 带进 tool-bubble 回调（M3 只透传 detail，本里程碑 +agent） |
| `lib.rs` | `pulsepet://bubble`/`tool-bubble`/`task-result` 三事件 payload 补 agent 字段；**`get_display_state` 适配 display(now)**（P2-3） |
| `token_stats.rs` | `token_stats_today` 返回体 +`by_agent` |
| `pet/Bubble.tsx`（M2 组件） | `agent` 可选字段 → 前置徽标渲染 |
| `pet-menu.ts` + `PetMenu.tsx` + `todayToken.ts` | 今日 agent 分布行（菜单信息项子行，双 agent 才显示）〔修订 2026-08-27：原写 `pet/HoverToday.tsx`，随 §3.4 悬停卡移除改落此三文件〕 |
| **`lib/bubble-queue.ts` + 三桥层（P2-4）** | BubbleItem 新增 `agent?: string`（随回队/合并流转）；`http-bridge.ts`/`tool-bubble-bridge.ts`/`reminder-bridge.ts` 三桥层 payload 解析 agent 传入条目 |
| `lib/i18n.ts` | 少量键（分布行标签 `token.hoverAgent` 等〔键名按定稿保留，名实注记见 §6.2 修订注记〕）；徽标不翻译 |

**数据库：零迁移。**

### 6.4 测试与验收（M6 Done 标准）

**单测**：

| 域 | 用例 |
|---|---|
| `session_state` 两层算法 | 活跃集内优先级合并（双活跃 error>working）；**同 priority 平局取 last_event_at 最新者（双 agent 同 kind，P2-2）**；掉窗让位（error 10s 前事件 vs working 2s 前 → working）；窗口空 fallback 最近活跃（平局 priority）；**solo error 经 fallback 显示至 30s 回收（P1-1 钉子）**；空 map → idle；跨 agent（opencode/claude-code/task 同权参与）；伪 session 15s 心跳的掉窗-接管时序（手头静默期例程连续显示不闪变）；**waiting-permission 掉窗让位（P2-5 语义钉子）**；既有 v1 断言修订（display 注入时钟，同刻事件行为等价） |
| `token_stats` | today by_agent 分组（单源单行/双源双行/零数据省略） |
| 前端 | 徽标渲染（agent 缺省不显示徽标——提醒气泡回归）；分布行（菜单子行）单 agent 隐藏 |
| i18n | 新键完备性 |

**实机验收**（TC-M6-xx）：

1. 双开实测：opencode + CC 并行干活 → 宠物随两侧事件切换归属（panel 芯片 agent 同步变化）；一侧 error 后静默 → ≤10s 让位另一侧（v1 抢镜问题消除）；
2. 气泡徽标：双 agent 各触发一次会话结束/工具播报 → `[oc]`/`[cc]` 正确前置；提醒气泡无徽标（回归）；任务结果 `[task]`；
3. 今日 agent 分布行（右键菜单「今日 token」信息项子行〔修订 2026-08-27：原写悬停卡，呈现面随 §3.4 移除改菜单子行〕）：双 agent 有数据 → 分布行显示；单 agent 日 → 无分布行；数值与 panel 一致（M3 交叉断言延续，两层口径）；
4. M4 协同：例程执行中**手头会话窗内持续有事件** → 手头状态优先；例程失败 × 手头持续活跃 → error ≤10s 让位（M4 R6 精化实证）；例程失败 × 无并发会话（或所有其他会话最后事件均早于 error——fallback 最近活跃语义实证点）→ error 显示至 30s 自然回收（solo 边界，有意行为）；手头静默期例程 working 连续显示（兜底语义）；
5. 重启/主题/双语回归目验。

### 6.5 风险与开放问题

| # | 风险/问题 | 处置 |
|---|---|---|
| R1 | 窗口翻转导致显示状态交替——**伪 session 固定 15s 心跳 × 手头事件稀疏（间隔 >10s）时呈周期性交替，非极端节奏**（P2-1 归因修正）；双真实会话交错为次要面 | 事件驱动天然限频（插件节流/CC 低频）；「例程兜底」显示（§6.1 M4 行推演）在静默期是稳定而非闪烁；观察项，实测烦扰再加 2s 显示滞回（hysteresis）——预设计不实现 |
| R2 | 10s 窗口对 CC 长生成不友好（无流式事件，掉窗靠 fallback） | fallback 语义已兜住（显示不跳 idle）；与 M1 §1.11 R7（CC 长回答提前回 idle）同根，无新增伤害 |
| R3 | 三事件 payload 补字段对旧前端的理论不兼容 | 同版本锁步发布（M5 N-4 同口径），无跨版本运行场景 |
| R4 | **waiting-permission（优先级 6）掉窗让位**：CC 权限请求 >10s 未审批且手头会话活跃 → review 姿态让位（与 M1「提醒用户看终端」意图的张力） | **接受 + 记录**（P2-5 裁定）：终端权限弹窗本身持续可见（CC 弹窗阻塞会话，不依赖宠物二次提醒）；10s 提醒窗口已覆盖「刚发生」的最重要时段；单测钉住「掉窗让位」语义防实施困惑 |

### 6.6 不采用记录

| 项 | 理由 |
|---|---|
| 5s 窗口（SCOPE 示例值） | opencode 生成中会话两心跳间隔即掉窗，窗口价值减半（用户裁定 10s） |
| 显示滞回（hysteresis）防交替 | 预防性设计无实证需求；R1 观察后再加 |
| 气泡尾部/颜色标识 agent | 前置等宽徽标最贴近终端习惯（[oc]/[cc]），视觉侵入最小 |
| per-session 宠物（多 pet 同屏） | v1 DECISIONS 维持不做；单宠抢镜即本里程碑的全部问题域 |
| 提醒气泡也加来源徽标 | 非 agent 来源（App 自身），无辨识需求 |

### 6.7 评审记录（2026-08-23，reviewer subagent）

> 评审对象：本章节初稿。评审基准：V2-SCOPE §3.6、M1-M5 上游定稿、session_state.rs/lib.rs/http_server.rs/插件源码逐条核对（reaction 桶 10s 冷却、display 两处调用点等事实均属实）。
> **verdict: NEEDS REVISION**（P1×1 / P2×5 / P3×7 / 澄清×2；无 P0）。
> 处置结论：**全部采纳**——P1/P2 全部修订正文；P3 全部落实；澄清×2 裁定消化。评审人总体评价：「算法骨架与上游预留位引用整体扎实、事实依据经源码逐条核实；工期/零迁移/核对通过项均确认」。

#### 问题清单（摘要）与处置

**P1-1（已修，→ §6.1/§6.4）**：「error ≤10s 让位」无条件承诺与算法自相矛盾——solo error（无其他会话/均更旧）经 fallback（最近活跃）仍选中，显示至 30s 回收。修法：承诺加前置「手头窗内持续有事件」；场景表补 solo 边界行（有意行为，与 v1 无回归）；验收 4 双分支改写；单测钉子。

**P2（5 项均落实）**：P2-1 伪 session 15s 心跳 × 窗口 10s 的系统性交互推演（心跳间隙掉窗但 fallback 连选 → 手头静默期例程连续显示不闪变；R1 归因修正「周期性交替非极端节奏」）；P2-2 活跃集平局取 last_event_at 最新（防 HashMap 序任意决定胜者）+ 单测；P2-3 `get_display_state` 调用点适配落表；P2-4 徽标载体 = BubbleItem 新增 agent 字段（随回队/合并流转）+ 三桥层解析行 + 措辞改「新增」（M2 结构本无此字段）；P2-5 waiting-permission 掉窗接受 + R4 记录 + 单测钉子。

**P3（7 项均落实）**：协同引用错节（§6.2→§6.1）；徽标形态与 M5 列表刻意不同注（防顺手统一）；by_agent 落 TodayStats 内 + total 口径钉（三层数值断言依赖）；合并键不含 agent 徽标随新条目注；DisplayState.agent 归属与芯片降级；1s notify 循环对 M6 不可或缺注；单测三补钉。

**澄清项裁定**：① solo error 30s = **有意行为**（失败应被看见，M4 R6 语义；与 v1 无回归无改善，非本里程碑问题域）；② waiting-permission 掉窗 = **接受 + 记录**（终端弹窗本身持续可见阻塞会话；10s 已覆盖最重要时段）。

#### 修订汇总（2026-08-23，按评审意见）

§6.0 引用修正；§6.1 平局规则/solo 边界行/M4 行精确推演/归属与兜底段/改造面调用点写全；§6.2 BubbleItem 载体/徽标形态注/by_agent 落点口径/合并交互；§6.3 lib.rs 调用点行/bubble-queue+三桥层行；§6.4 单测四补钉/验收 4 双分支；§6.5 R1 归因修正/R4 新增。

#### 复审记录（2026-08-23 第二轮，同 reviewer 续会话）

> 复核第一轮 15 项（P1×1/P2×5/P3×7/澄清×2）：**全部正确落实**——三处前置条件/solo 边界/平局规则/BubbleItem 载体/R1 归因/R4 裁定与 §6.7 处置声明全部自洽，修订未引入结构性矛盾；「已定稿章节不回改」约定下的 M6 章内声明 BubbleItem 新增字段（不回改 M2）被确认为正确处理。
> **verdict: APPROVED WITH COMMENTS**——仅余 4 条 P3 措辞精度项，「可在实施时顺手消化、无需再开评审轮次」。
> 处置：**4 项均已顺手消化**——P3-① 验收 4 第二分支补「（或所有其他会话最后事件均早于 error）」子情形（fallback 语义实证点）；P3-② M4 行改「静默期间连续显示 + 整体呈周期性交替（见 R1）」与 R1 口径互释；P3-③ 平局规则改「互为镜像字典序 (priority, last_event_at) / (last_event_at, priority)」精确表述；P3-④ §6.2 表头改「M6 新增」消误读。
>
> **M6 评审流程闭环：两轮（NEEDS REVISION → APPROVED WITH COMMENTS）**，待用户终审定稿。

#### 终审记录（2026-08-23，用户）

- **评审点全部认可**：solo error 显示 30s = 有意行为（失败应被看见；仅手头会话活跃时 ≤10s 让位）、waiting-permission 掉窗让位接受（终端弹窗本身持续可见）、手头静默期例程 working 连续显示（兜底不闪变，整体呈随手头事件节律交替）、平局镜像字典序 (priority, last_event_at) / (last_event_at, priority)、气泡前置 [oc]/[cc]/[task] 徽标（与 M5 列表形态刻意不同）、悬停卡 agent 分布行、10s 活跃窗口——照单定稿。
- **M6 定稿。v2 六章（M1-M6）全部定稿，v2 设计方案完成**——实施基线即本文档。
