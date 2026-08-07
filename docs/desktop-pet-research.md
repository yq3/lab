# 开源 Agent 桌宠调研报告

> 调研日期：2026-08-06 ｜ 调研方式：GitHub API 整仓源码精读（openpets / petdex / clawd-on-desk / oc-claw / agentpet / cc-haha / PawPause / awesome-codex-pet）
> 目标：为自研"桌面宠物"（agent 状态上报 + token 消耗统计 + 喝水/休息提醒 + todo 管理 + 对话入口）评估复用资产与可借鉴架构。

---

## 1. 结论先行

| 需求 | openpets | petdex | clawd-on-desk | agentpet | oc-claw | PawPause | cc-haha |
|---|---|---|---|---|---|---|---|
| agent 状态→宠物 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| opencode 一等支持 | ✅ 官方插件+MCP | ✅ 自带插件文件 | ✅ 插件+权限气泡 | ✅ | ✅ | ✅ 插件写 JSONL | ✅ |
| **token 消耗统计** | ❌ | ❌ | 半（订阅额度环） | ✅ token+成本+养成 | ✅ token 图表 | ❌ | 部分 |
| 休息/喝水提醒 | ✅ 官方插件 | ❌ | ❌ | 半（休息提醒） | ❌ | ✅ 喝水+休息+专注 | ✅ 定时任务 |
| todo 管理 | 半（插件可写） | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 对话入口 | ✅ AI gateway | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 插件/扩展机制 | ✅ SDK v3 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 素材生态复用 | ✅ 支持 codex pet | ✅ 生态核心 | ✅ 支持导入 | ✅ 画廊 | ✅ | ✅ PetDex 格式 | 部分 |
| 运行时体重 | Electron 全家桶 | Zig 原生（最轻） | Electron | 原生 Swift | Tauri | Electron | Electron |
| 许可 | MIT | MIT | AGPL-3.0 | MIT | MIT | MIT | MIT |

**一句话定位**：

- **petdex** = 素材生态 + 最精致的 agent 状态宠物运行时（原生、极轻），但无扩展机制，桌面端仅 macOS；
- **openpets** = 功能平台（插件 SDK + 喝水/休息/番茄钟/todo 类能力 + AI 对话 + 五路 agent 集成），Electron 全家桶；
- **clawd-on-desk** = 覆盖面最广的"盯 agent"宠物（19+ agent、权限审批气泡、会话仪表盘、移动端镜像），AGPL 许可需注意；
- **agentpet** = 养成向（token→XP→进化）+ 菜单栏监控，Swift 原生；
- **oc-claw** = Tauri 栈的 notch 岛宠物（与 todo-lite 同技术栈，最适合作为自研起点参照）；
- **PawPause** = 与自研目标最贴近的产品形态（休息+喝水+专注+agent 上报四合一），事件链路用 JSONL 文件总线（最简单）；
- **cc-haha** = agent 工作台全家桶，桌宠只是其中一角，对"纯桌宠"过重。

---

## 2. Codex Pet 生态（素材标准）

Codex（OpenAI 桌面应用）内置宠物功能（Settings → Pets），并衍生出社区素材生态。这是整个桌宠圈的**事实素材标准**。

### 2.1 宠物包格式

一个宠物 = 目录下两个文件：

```text
pets/<pet-id>/
├── pet.json             # 元数据
└── spritesheet.webp     # 动画雪碧图（atlas）
```

`pet.json`（awesome-codex-pet 实际样例）：

```json
{
  "id": "firefly--lingxiaotian",
  "displayName": "流萤",
  "description": "……",
  "spritesheetPath": "spritesheet.webp"
}
```

### 2.2 Atlas 规范（社区互通）

| 版本 | 尺寸 | 网格 | 用途 |
|---|---|---|---|
| v1 | 1536×1872 | 8 列 × 9 行 | 标准动画（老格式） |
| v2 | 1536×2288 | 8 列 × 11 行 | 标准动画 + 16 个注视方向 |

- 单帧 192×208 px；
- **每行 = 一个动画状态**。社区命名：`idle, wave, run, failed, review, jump, extra1, extra2`；
- petdex 桌面端实际用 9 状态：`idle / running-right / running-left / waving / jumping / failed / waiting / running / review`，每状态独立帧时长表（idle 有 6 帧不规则的眨眼节拍）；
- Codex 将这些状态映射到它的 agent 活动 hooks（思考/工作/等待/审查/失败）；
- ChatGPT 桌面应用 `/pet` 可直接生成该格式的宠物（v2 规格），Codex 的 "Hatch Pet" 是 AI 辅助的 v1→v2 转换流程。

### 2.3 社区画廊

| 项目 | Stars | 内容 | 许可 |
|---|---|---|---|
| `legeling/awesome-codex-pet`（codexpet.top） | 569 | 178+ 宠物、11 类、一键安装脚本（写入 `~/.codex/pets/`） | 代码 MIT、素材 CC BY-NC 4.0 |
| `crafter-station/petdex`（petdex.dev） | 3699 | 画廊 + CLI + 桌面端，与 Codex 格式互通 | MIT（素材归提交者） |

> ⚠️ 素材许可注意：awesome-codex-pet 素材为 **CC BY-NC 4.0**（非商用）；petdex 素材归各提交者所有、许可自选。自用无碍，发布需逐一核对。

---

## 3. 重点项目深挖

### 3.1 openpets（alvinunreal/openpets）—— 功能最全的平台型选手

- **Stars / 许可**：1024★ / MIT
- **技术栈**：pnpm + TypeScript monorepo，Electron 桌面应用 + npm 包集合，Windows / macOS / Linux
- **定位**："带插件和 agent 集成的桌面伴侣平台"

#### 3.1.1 运行时拓扑（三个世界）

1. **桌面应用** `apps/desktop/`：Electron main process（唯一长驻进程），持有状态、宠物窗口、托盘、**插件运行时**、**本地 IPC server**；
2. **agent 侧集成** `packages/*`：短命进程，随 agent 启动/退出（Claude Code hooks、MCP server、OpenCode 插件、Cursor 配置、Pi 扩展、CLI），把 agent 活动翻译成宠物命令走本地 IPC；
3. **Web 目录源** `openpets.dev`：宠物/插件目录（catalog v3）+ R2 上的 ZIP。

```
coding agent ──(hook/MCP/plugin event)──▶ @open-pets/client
                                              │ 本地 IPC（Unix socket / 命名管道 / 私有 TCP）
                                              ▼
                                    桌面应用 main process
                                      ├─ lease manager → 宠物窗口
                                      ├─ 插件运行时 + SDK bridge
                                      └─ catalog / 安装（HTTPS → openpets.dev）
```

#### 3.1.2 本地 IPC 协议（`@open-pets/client` + `local-ipc.ts`）

- 传输：macOS/Linux **Unix domain socket**、Windows **命名管道**、跨平台/WSL 用**私有网段 TCP**（仅允许 loopback/10/8/172.16/12/192.168/16/link-local，拒绝主机名与公网）；
- 发现机制：app 写 **discovery 文件**（含 endpoint + 随机 token），客户端校验文件权限/符号链接后连接；消息为**行分隔 JSON**，单条 ≤16KB，连接 ~2s / 响应 ~3s 超时；
- 请求面：`hello / status / pets.list / pets.install / pets.install-local / pet.react / pet.say / pet.showMedia / lease.acquire / lease.heartbeat / lease.release`；
- **Lease 模型**：15s TTL 的短租约，心跳续租；命令路由到"默认宠物"或"显式 agent 宠物"（首个租约拉起宠物窗口，最后一个租约释放则关闭）；客户端身份 = PID + 每进程随机 nonce，防 PID 复用误继承；周期探活回收孤儿会话；
- 安全：每个请求带 token；消息尺寸/超时上限；客户端两侧 contract 文件在测试套件中防协议漂移。

#### 3.1.3 OpenCode 集成（`@open-pets/opencode`）——自研最值得抄的部分

- **配置**（`opencode-config.ts`，JSONC 感知）：管理 opencode 配置（项目 `.opencode/` 或全局 `~/.config/opencode/`，从 `config.json` / `opencode.json` / `opencode.jsonc` 选实际生效文件，保留用户数组）的 `mcp`、`instructions`、`plugin` 三段；指令文件用 `<!-- OPENPETS:START/END -->` 标记；提供 prepare/write/remove/doctor 生命周期；
- **运行时插件**（`opencode-plugin-runtime.ts`，插件 id `open-pets-opencode`）：注册 opencode 插件 hooks：

```ts
export type OpenCodeHooks = {
  readonly event: (input: { event: unknown }) => void;              // bus 事件
  readonly "chat.message": (input, output) => void;                  // 消息 → thinking
  readonly "tool.execute.before": (input: { tool?: string }, output: { args?: unknown }) => void;
  readonly "tool.execute.after": (input, output) => void;            // 暂静默
};
```

- **事件分类**（关键！）：

| opencode 事件 | 反应 |
|---|---|
| `permission.asked` | waiting + permission 语音 |
| `session.error` | error |
| `session.status` 且 status.type == idle | success |
| `chat.message` | thinking |
| `tool.execute.before` 且工具名匹配 `edit/write/patch/apply_patch` | editing |
| `tool.execute.before` 且 `bash/shell/terminal` 且命令含 test/vitest/jest/pytest/npm test 等 | testing |

- **节流**：语音 20s / 权限 3s / 反应 10s 冷却（JSON 状态文件，原子写）；排除项 `excludeReactions` 插件配置可提前丢弃指定反应；
- **安全语音**（`@open-pets/agent-events`）：自动消息只能来自经过验证的语音池（thinking/success/error/permission 四类），单行、1–140 字符、拒绝代码/URL/路径/secret 样式 token——**原始 prompt/输出文本永远不会进气泡**；
- **自忽略**：正则跳过 openpets 自己注册的 `openpets_status/say/react` 工具，防止回环。

#### 3.1.4 其他 agent 集成

- **Claude Code**（最深入）：注册 MCP server + 命令 hooks（`UserPromptSubmit/PreToolUse/PermissionRequest/Notification/Stop/StopFailure`），映射 prompt→thinking、permission→waiting、stop→success、stop-failure→error、Edit/Write/MultiEdit→editing、bash 测试→testing；条目带 `--openpets-managed` 标记可安全增删；项目级 `.claude/settings.local.json` 覆盖时全局 hook 让位；内存文件 `~/.claude/openpets.md` 教 Claude 用宠物；
- **MCP server**（`@open-pets/mcp`，任何 MCP 客户端可用）：三个工具 `openpets_status / openpets_react / openpets_say`，Zod 校验、幂等注解、stdio 传输、5s 心跳、退出恰好释放一次租约；`--pet <id>` 可指定宠物（未安装则静默回退默认并桌面通知）；
- **Cursor**：纯文件管理（`mcp.json` + 项目规则 `.cursor/rules/openpets.mdc`），严格 JSON、尺寸上限、符号链接拒绝、拒绝 `@latest` 未固定版本；
- **Pi**：扩展 + `/openpets` 斜杠命令，MVP 仅默认宠物。

#### 3.1.5 插件 SDK v3（自研扩展机制的参考蓝图）

- 清单 `openpets.plugin.json`：`manifestVersion: 3`、`permissions`、`configSchema`（生成无 JSON 设置表单）、`assets`、`commands / status / panels / network.hosts / timer 触发`、`$t:` i18n；
- **沙箱**：JS 插件运行在沙箱 BrowserWindow host 内（`plugin-js-host.ts`），只能通过**权限检查的 SDK bridge** 与宿主对话；
- **权限面**：`timer/schedule, pet:*, pets:*, audio, events, ui:*, notify, bus, ai, secrets, voice:*, auth, files, system:*, clipboard, network:*`——声明→用户安装时批准→**每次 SDK 调用复检**（纵深防御：清单校验 + 用户批准 + 运行时检查 + 配额）；
- **网络**：`ctx.net.fetch/stream`，host 必须在 `manifest.network.hosts` 且经用户批准，防 DNS rebinding；`network:local` 为增量权限；
- **AI gateway**：宿主统一 AI 提供商（Anthropic / OpenAI / Ollama / MiniMax，OpenAI 兼容 API），插件不接触 API key → 对话类插件（如 ai-chat 模板）成为可能；
- **官方插件阵容**（你要的功能大半在这里）：`reminders`（可 snooze 通知）、`water-reminder`（喝水）、`day-routine`（日常习惯+拉伸）、`focus-buddy`（番茄钟）、`calendar-airmail`（日程信件投递）、`mood-check-in`（心情）、`virtual-pet`（电子宠物养成）、`fortune-cookie`、`magic-8-ball`、`launch-buddy`（快捷命令）；社区：`spotify-buddy`、`walkabout`（足迹）、`higgsfield-watch` 等。

#### 3.1.6 渲染与宠物管理

- `pet-window.ts`：透明、无边框、置顶窗口；**CSS sprite 动画**渲染 atlas；
- `pet-motion-engine.ts`：**单一共享 ticker（~60fps）** 驱动所有宠物窗口，每宠物独立 `MotionState`，位置锁步推进；重力+弹跳漫游（`pet-roaming-controller.ts`），支持多显示器；插件可注入运动向量/物理参数/跟随光标；
- Reactions → 动画映射用户可配置（映射表持久化）；`waving` 覆盖 attention/notification 类反应；等待动画循环时长 Normal 1010ms / Relaxed 2200ms；
- 支持导入 **Codex pets**（`~/.codex/pets/`）；`pet.showMedia` 可在气泡内展示本地图片（10MB 上限、白名单扩展名、可配 clickUrl）；
- Control Center（React/Tailwind）、托盘、7 语言 i18n、ZIP 安全解压（防穿越/符号链接逃逸）、实验性 LAN 多主机宠物会面。

#### 3.1.7 评价

- **优点**：功能覆盖最全；插件 SDK 是现成"todo/喝水/休息/对话"扩展蓝本；opencode 集成为官方维护的一等公民；文档完整（docs/ 下 16 篇架构文档 + 测试契约）；
- **缺点**：Electron 全家桶（资源占用大）；插件系统成熟度高但学习曲线陡；生态依赖其服务器目录（openpets.dev）。

---

### 3.2 petdex（crafter-station/petdex）—— 最精致的 agent 状态宠物本体

- **Stars / 许可**：3699★ / MIT（素材归提交者）
- **技术栈**：三件套——Web 画廊（Next.js 16 / React 19 / Drizzle / Postgres / Redis / Clerk / R2）、CLI（Bun + TS，单文件 bundle）、**桌面端（Zig + vercel-labs/native SDK，macOS 原生，无 WebView / 无 Node sidecar）**
- **定位**："浏览器、安装、提交宠物，一条命令" + 桌面宠物实时响应 agent 活动

#### 3.2.1 CLI 与安装流

```bash
npx petdex login        # Clerk OAuth + PKCE，token 存系统 keychain
npx petdex list         # 浏览画廊
npx petdex install boba # 写入 ~/.petdex/pets/boba/ 和 ~/.codex/pets/boba/
npx petdex submit ./my-pet/  # 提交（zip → presigned R2 PUT，60s TTL，10 次/24h）
```

- 校验规则：`pet.json` + `spritesheet.webp`（或 png），必须 8×9（1536×1872）或 v2 8×11（1536×2288）或干净缩放；
- v1.0.0 起 `hooks/init/up/down` 等命令移除，agent hook 安装统一收进桌面 App 设置界面（每 agent 一键）。

#### 3.2.2 桌面端（Zig，`packages/petdex-desktop-native/`）

- 技术：vercel-labs/native（macOS 原生 SDK），无 WebView、无 JS 运行时；当前为"V1 切片"：运行时加载真实 atlas 的无边框窗口；路线图 V5 才计划 vendored libwebp 跨平台；
- **进程内 HTTP hook server**（`hook_server.zig`，取代 Node sidecar 的 127.0.0.1:7777）：
  - 端点：`POST /state`、`POST /bubble`（token 门控：header `x-petdex-update-token`，token 文件 `~/.petdex/runtime/update-token` mode 0600，每次会话重新生成）；`/health /whoami /state /bubble /init-status` 读取端；
  - 共享限流 30 请求/s；一次性连接（`Connection: close`），agent hooks 每次事件 curl 一次；
  - 无分配器热路径：server 线程只解析/校验/镜像，写入**邮箱**（mutex 保护，max 50 待处理），app 线程 poll timer 消费并独占显示逻辑（dwell、合并、左右跑动交替）；
  - 气泡并发上限 8；bubble 字段：text(200B)、title(96B)、agent(24B)、session(64B，会话归属，空串=单气泡兼容老 CLI/MCP)；
- **动画状态机**（`sprite.zig`）：9 状态 `idle / running-right / running-left / waving / jumping / failed / waiting / running / review`，每个状态=atlas 行号 + 帧时长表（idle 6 帧不规则眨眼；其余 uniform）；
- 素材来源：扫描 `~/.petdex/pets` + `~/.codex/pets`（`PETDEX_PET=<dir>` 覆盖）。

#### 3.2.3 opencode 集成（`opencode-plugin.js`，仓库自带资产）

由 `petdex hooks install` 自动生成的 opencode 插件（官方插件格式，运行在 opencode 的 Bun 进程内）：

```js
const SIDECAR_URL = "http://127.0.0.1:7777/state";
const SIDECAR_BUBBLE_URL = "http://127.0.0.1:7777/bubble";
// token 从 ~/.petdex/runtime/update-token 读；killswitch 文件 hooks-disabled
```

- 工具类型归一化：read / edit(multiedit) / write / bash(shell) / grep / glob / webfetch(websearch) / task(agent) / unknown；
- 气泡文案模板：`Read/Reading <basename>`、`Edited/Editing X`、`Ran/Running <命令首个词>`、`Searched "pattern"`、`Listed pattern`、webfetch 取 hostname；
- 提供可编辑的 **STATE_MAP**，自定义"事件→状态"映射；
- 支持 agent 图标集：opencode / claude-code / codex / gemini / kimi-code / omp / qoder / antigravity / codebuddy / fallback；
- 另有 MCP server（`packages/petdex-cli/src/hooks/mcp-server.ts`）与 bubble-runner。

#### 3.2.4 生态与 built-with

- 官网宣称 21 个开源/源可用项目构建在其格式之上（`petdex.dev/built-with`）；
- 与 ChatGPT `/pet` 导出、Codex pets、awesome-codex-pet 素材全互通。

#### 3.2.5 评价

- **优点**：核心体验（状态→动画+气泡）打磨最精致；运行时最轻（Zig 原生）；素材生态最大之一；协议与实现都简洁（几十 KB 级别可读）；
- **缺点**：**无插件/扩展机制**（喝水/todo/对话都装不进去，扩展=fork Zig 端）；桌面端当前仅 macOS（repo 内无 Win/Linux 实现）；登录/提交深度绑定其服务器生态（Clerk/R2/petdex.dev，网络受限环境安装会卡）；素材版权需自核。

---

### 3.3 clawd-on-desk（rullerzhou-afk/clawd-on-desk）—— 覆盖面最广的盯 agent 宠物

- **Stars / 许可**：5845★ / **AGPL-3.0**（商用/闭源需注意）
- **技术栈**：Electron + 原生 JS（无前端框架），依赖极简：`electron-updater / htmlparser2 / jsonc-parser / koffi(win32 FFI) / markdown-it / ws / @larksuiteoapi(飞书)`；Windows NSIS x64+arm64、macOS dmg、Linux
- **定位**："像素桌宠盯着 Claude Code、Codex、Cursor 等 agent，省得你盯"
- **支持 19+ agents**：Claude Code / Codex / Copilot / Gemini / Antigravity / Cursor / CodeBuddy / WorkBuddy / Kiro / Kimi / Qwen / ZCode / CodeWhale / Reasonix / **opencode** / MiMo / Pi / OpenClaw / Hermes / Qoder + **自定义 HTTP agent**（任意本地可执行程序 POST `/state`）

#### 3.3.1 核心机制：agent 配置驱动的事件→状态映射

每个 agent 一个 `agents/<agent>.js` 配置：

```js
module.exports = {
  id: "opencode",
  processNames: { win: ["opencode.exe"], mac: ["opencode"], linux: ["opencode"] },
  eventSource: "plugin-event",          // hook | plugin-event | log-poll
  eventMap: {                           // 统一 PascalCase 事件名 → 动画状态
    SessionStart: "idle", UserPromptSubmit: "thinking",
    PreToolUse: "working", PostToolUseFailure: "error",
    Stop: "attention", StopFailure: "error",
    SubagentStart: "juggling", PreCompact: "sweeping", Notification: "notification",
  },
  capabilities: { httpHook, permissionApproval, notificationHook, sessionEnd, subagent },
  pidField: "claude_pid",
};
```

- **opencode 集成**：插件写进 `~/.config/opencode/opencode.json` 的 `plugin` 数组（安装器 `hooks/opencode-install.js` → `opencode-family-install.js`）；共享插件 `hooks/opencode-family-plugin/core.mjs`（跑在 opencode 的 Bun 进程内）把原生事件（session.* / message.part.updated / permission.asked）翻译成上述 PascalCase 事件 POST 给 Clawd，并且**权限气泡反向桥接**：Clawd 气泡 → host REST 回复 → 回传 Allow / Always / Deny；
- **Claude Code**：命令 hooks + HTTP permission hooks（允许/拒绝/规则/Always 全支持）；
- **Codex**：官方 hooks + JSONL 兜底（轮询 `~/.codex/sessions/`）；
- **Gemini**：telemetry/log 轮询；**OpenClaw**：JSONL session 文件轮询；
- 状态归一化后由 `state.js` 做**多会话状态优先级合并**（哪个 agent 最"活跃"显示哪个动画）。

#### 3.3.2 特色功能

- **权限审批气泡**：悬浮卡片一键 Allow/Deny + `Always` 规则，全局热键 Ctrl+Shift+Y/N，多请求堆叠，终端先答则气泡自动消失，per-agent 开关；
- **12 个动画状态**：idle / thinking / typing / building / subagent-groove / multi-subagent-juggling / error / happy / notification / sweeping / carrying / sleeping（对应带 3 个内置主题：像素螃蟹 Clawd / 三花猫 Calico / 云宝 Cloudling）；
- **Codex Pet 导入**：Settings→Theme 直接导入 codex pet zip 并适配成受管主题；
- **会话智能**：多会话跟踪、子代理感知（1 个→耳机律动、2+→三球杂耍）、会话 Dashboard + HUD、订阅额度环（读 Claude 官方 status-line `rate_limits`，非爬取）、终端焦点跳转、进程存活检测、启动恢复；
- **移动端 PWA 镜像**：手机实时看 agent 状态（只读，LAN-only + token 轮换；另有 Android 原生 fork `clawd-on-mobile`）；
- 交互：眼睛跟踪光标、60s 睡眠序列（哈欠→瞌睡→睡，鼠标惊扰）、双击戳一下/四连击扑腾、任意状态拖拽、Mini mode（贴边隐藏+悬停窥视）、节日配饰、点击穿透、位置记忆、单实例锁。

#### 3.3.3 评价

- **优点**：agent 覆盖最广（含自定义 HTTP agent）；权限审批是独有杀器；会话仪表盘/配额/移动端都是完整产品级；
- **缺点**：AGPL-3.0（若商业发布需开源同许可）；Electron 体积；无插件 SDK（定制=改源码）；代码量大（1200+ 文件级别）。

---

### 3.4 agentpet（ntd4996/agentpet）—— 养成向 + 菜单栏监控

- **Stars / 许可**：297★ / MIT
- **技术栈**：**Swift / SwiftUI 原生 macOS（notarized）** + Tauri（Windows/Linux），自动更新
- **定位**："宠物吃你真烧的 token 长大"——agent 监控 + 电子宠物养成

- **菜单栏监控**：每 agent 状态点、所属项目、正在做什么、实时计时器；有 agent 等待输入时图标变橙带计数；agent 完成/要输入时系统通知+音效；
- **养成**：真实 token 消耗 + 完成会话（含子代理）→ XP → 5 阶段进化（Hatchling→Companion→Scout→Hero→Legend），14 个成就（首个会话/升级/1M·10M·50M token/连续喂食/夜猫子…），每宠物独立等级；Stats HUD（等级/XP/饥饿/7 日消耗图/连续天数/Claude·Codex 订阅额度直读）；
- **按项目养宠物**：项目文件夹→专属宠物，XP 归属该项目；Split pet 支持多宠物同屏；
- **Break reminder**（休息提醒，默认关）；
- **11 个 agent + universal wrapper**；session 历史 90 天本地留存；可选云（GitHub 登录 web profile + 排行榜 + 跨设备恢复，向前合并）；
- 架构（`AgentPetCore`）：`AgentHooks / HookInstaller / EventSocketServer`（hook 事件→本地 socket 推送）、`BreakClock`（休息时钟）、`PetCare / PetMood / ModelPricing`（token 计价）、`ProjectPetResolver / QuestionDetector / PendingApprovalRegistry / PerKeyThrottle`；
- **评价**：产品完成度高的独立开发者作品；但无插件扩展，macOS 亲儿子（Win/Linux 为 Tauri 移植）；token 计量思路对"自研养成玩法"有参考价值。

---

### 3.5 oc-claw（rainnoon/oc-claw）—— Tauri 栈的 notch 岛宠物

- **Stars / 许可**：344★ / MIT
- **技术栈**：**Tauri v2 + React + TypeScript + Rust**（与 todo-lite 同栈！），macOS（notch 岛）/ Windows（任务栏）
- **定位**："趴在 macOS 灵动岛上的 agent 监控宠物"，设计灵感来自 Notchi / Vibe Island

- 数据流（README 明确）：

```
OpenClaw  → JSONL session 文件 → 健康轮询 → Activity state
Claude Code / Codex / Cursor / Gemini → Hooks → Event parser → Activity state
Hermes → Plugin → Event parser → Activity state
                                           ↓
                      动画精灵 ← 状态机 ← 音效
```

- 功能：notch 悬停展开会话详情面板、会话列表/聊天历史、每日调用与 token 图表、SSH 远程连接 OpenClaw/Hermes、自定义角色动画、按 agent 配对角色、岛屿背景裁剪、完成/等待音效；
- 内置宠物即 codex-pet 格式（`doro.codex-pet` 等，pet.json + spritesheet.webp）；
- **评价**：与你的 todo-lite 技术栈完全一致，作为"自研 Tauri 桌宠"的**架构参照最合适**（虽然功能体量小）；Rust 侧可做系统集成（窗口定位、SSH、API 通信）。

---

### 3.6 cc-haha（NanmiCoder/cc-haha）—— 全家桶，桌宠只是其中一角

- **Stars / 许可**：13948★ / MIT
- **技术栈**：Electron + TypeScript，macOS / Windows / Linux
- **定位**："桌面 Claude Code 工作台"：多会话工作区、全局搜索、分支/Worktree 启动、diff 审查、内置浏览器预览、**GUI 权限审批**、任意模型（Claude/ChatGPT/Grok/本地端点）、图像生成、视觉 MCP 与 SubAgent 管理器、模型 trace、Computer Use、技能市场、主题、**桌面宠物**、H5 远程访问、微信/飞书/DingTalk/Telegram/WhatsApp IM 接入、定时任务
- **评价**：桌宠（task-aware pets）只是其中一个特性；`adapters/` 里 IM 接入架构（ws-bridge、session-recovery、adapter-client）对"宠物作为对话入口"有借鉴价值，但整体是重工作台，不适合作为桌宠起点。

---

### 3.7 PawPause（angziii/PawPause）—— 与自研目标最贴近的产品形态

- **Stars / 许可**：52★ / MIT（素材许可另计，见 ASSET_LICENSE.md）
- **技术栈**：Electron 43 + electron-vite 5 + React 19 + TypeScript，electron-store 持久化，vitest 测试；macOS / Windows；9 语言 i18n；电子打包带 notarize 脚本
- **定位**："本地优先的像素伴侣：休息、专注、喝水、agent 活动提醒"——**正是你目标清单的现成组合**（基于 PawPal 桌宠基础 + PetDex 格式启发，单作者小项目）

#### 3.7.1 Agent 事件链路：JSONL 事件文件总线（四种方案之外的第四种形态）

- **opencode 集成**（`integrations/opencode/pawpause-agent-hook.js`，约 100 行官方 opencode 插件）：

```
mkdir -p ~/.config/opencode/plugins
cp integrations/opencode/pawpause-agent-hook.js ~/.config/opencode/plugins/
```

插件把事件归一化后 **append 一行 JSON** 到 `~/.local/share/pawpause/agent-events/opencode.jsonl`（`PAWPAUSE_AGENT_EVENTS` 可覆盖）；app 侧 watch 该文件（多候选路径：Windows `%APPDATA%` / `%LOCALAPPDATA%`、macOS `.local/share` / `Library/Application Support` / userData）。

事件分类表：

| opencode 事件 | 归一化 kind / progressKind |
|---|---|
| `session.status` idle/complete/done/stop | complete |
| `session.status` 其它 | working / thinking |
| `session.next.step.started` / `reasoning.started` / `text.started` | working / thinking |
| `session.next.tool.called` / `tool.input.started` | working / tool（bash→script） |
| `session.next.shell.started` / `command.execute.before` | working / script（带 command 原文） |
| `permission.asked` / `question.asked` | needs-review / permission·choice |
| `session.error` / `step.failed` | failed |
| `chat.message` | working / thinking |

**优点**：app 与 agent 彻底解耦——app 没开事件也不丢、可回放；无 token、无 HTTP/IPC 服务；实现最简单；多 agent 各写各的文件天然分流。**缺点**：文件轮询有延迟；事件明文落盘（隐私）；并发 append 需幂等去重。

#### 3.7.2 其余 agent 接入（零侵入优先）

- **Claude Code**：不装任何 hook！直接解析 `~/.claude/projects/*.jsonl` 会话记录（`parseClaudeLogRecord`）：assistant 消息含 `tool_use`→working，`stop_reason` 为 `end_turn` / `stop_sequence`→response；代价是看不到 permission/notification 等细粒度状态；
- **DeepSeek TUI**：读 `~/.deepseek/sessions` + 审批事件 `~/.deepseek/audit.log`；
- **Hermes**：插件写 JSONL（`~/.hermes/plugins/`）+ 会话文件兜底；支持 WSL→Windows 跨机路径对接；
- **Codex**：支持本地事件（README 声称，含完成/失败/review/进度提醒）。

#### 3.7.3 休息 / 喝水 / 专注（你要的自定义功能现成实现）

- **Break intervention**：可选"全屏遮挡"强制休息模式——提醒被无视时的强干预手段；
- **Hydration**：喝水提醒 + 每日/历史统计；
- **自定义提醒**：宠物倒计时，到期前才出现在界面上，可选到期宠物放大（`breakPrompt→review` 动画）；
- **Focus mode**：macOS 活动窗口检测（需 Accessibility 权限）→ 被屏蔽 app / 关键词触发全屏干扰提醒（`focusGuard→review`、`focusAlert→failed`）；
- 提醒状态 → PetDex 动画映射表（`spriteStates.ts`）：thinking→waiting、breakPrompt→review、hydrationDone→waving、sad→failed 等。

#### 3.7.4 素材

- 完全复用 **PetDex 格式**（192×208 帧、1536×1872 atlas、9 状态行），`PETDEX_STATES` 帧时长表与 petdex `sprite.zig` 参数一致；
- 自动扫描 `~/.codex/pets`（`npx petdex install xxx` 装的直接可见），app 内可导入文件夹/zip；
- 大型素材包不入库（仓库保持小）。

#### 3.7.5 评价

- **优点**：产品形态与你目标重合度最高（休息/喝水/专注/agent 上报全有）；事件链路实现最简单（JSONL 文件总线）；Claude Code 零侵入解析是独门技巧；MIT 且代码量小（main 进程单文件 ~4k 行），易读；
- **缺点**：52★ 单作者项目、无插件机制、Electron 体重、无 todo 能力；JSONL 明文事件有隐私代价。

---

## 4. 核心机制横评（自研最关心的事）

### 4.1 agent → 宠物的事件链路：五种方案

| 方案 | 原理 | 代表 | opencode 是否支持 | 特点 |
|---|---|---|---|---|
| **A. hook / 插件事件** | agent 官方事件系统（JSON stdin 或插件回调） | openpets（opencode 插件 / Claude hooks）、petdex（opencode-plugin.js）、clawd（插件+hooks） | ✅ 插件 API（`event / chat.message / tool.execute.before/after`） | 事件最丰富（含 permission.asked、session.error）；opencode 插件需写进 `opencode.json` 的 `plugin` 数组 |
| **B. MCP 工具** | agent 作为 MCP client 调 `react/say/status` | openpets、petdex | ✅ opencode 支持 MCP server | 通用性最好（任何 MCP agent 可用），但**只有 agent 主动调用才触发**（配合指令文件引导） |
| **C. 日志/会话文件轮询** | 轮询 `~/.codex/sessions/`、JSONL、telemetry | clawd（codex JSONL）、oc-claw（OpenClaw JSONL）、PawPause（Claude 会话记录） | 部分（opencode 无官方会话 JSONL 习惯） | 零侵入，但粒度粗、有延迟 |
| **D. PTY/终端包装** | 包一层 CLI 解析输出 | （clawd 早期方案，已弃） | — | 侵入式，不推荐 |
| **E. JSONL 事件文件总线** | 插件/钩子把归一化事件 **append 到 JSONL**，app 侧 watch 文件 | PawPause（opencode/hermes 插件写 `agent-events/*.jsonl`） | ✅（官方插件写文件即可） | 实现最简单：无 token、无服务、app 关闭不丢事件可回放；缺点：轮询延迟、事件明文落盘、多写者需去重 |

> **opencode 生态结论**：一等方案是 **A（hook 插件）+ B（MCP）+ 指令文件引导**，三者 openpets 全做了，petdex 做了 A，clawd 做了 A+权限桥。自研最小可行 = 一个类似 petdex `opencode-plugin.js` 的插件（约 100 行 JS）POST 本地 HTTP；若想更省事，用 PawPause 的 **E（JSONL 文件总线）**——agent 侧只 append，Tauri 侧 fs watch 即可，Tauri 下无需起 HTTP server。

### 4.2 传输与安全

| 项目 | 传输 | 鉴权 | 备注 |
|---|---|---|---|
| openpets | Unix socket / 命名管道 / 私有 TCP，行分隔 JSON | discovery 文件 + 每次请求 token | 消息 ≤16KB，超时上限 |
| petdex | 本地 HTTP `127.0.0.1:7777` | header token（文件 0600，每会话轮换） | 30/s 限流，一次一连接 |
| clawd | 本地 HTTP `/state`、`/bubble` | 自有 token/权限规则 | 支持权限气泡双向桥接 |
| agentpet | 本地事件 socket | — | HookInstaller 写入 agent 配置 |
| PawPause | **无传输**：JSONL 文件总线（插件 append，app watch） | 无（文件系统权限本身） | 最简单；明文落盘；可回放 |

### 4.3 状态模型与动画

- openpets：**reactions 闭集**（thinking/editing/testing/waiting/success/error/idle…）→ 用户可配置映射到动画状态（idle/review/running/waiting/waving/jumping/failed）→ 本地化语音池；
- petdex：9 状态状态机（atlas 行号 + 帧时长表）；
- clawd：12 动画状态 + 多会话优先级合并；
- 渲染：openpets 用 CSS sprite animation（Electron），petdex 用 Zig 直接画帧（原生），oc-claw/agentpet 用 Tauri canvas/SwiftUI；**自研 Tauri 用 canvas 帧播放 atlas 即可，与格式无关**。

### 4.4 消息安全（共通的坑，但严格度不一）

- openpets / clawd：自动消息只能来自白名单语音池（或模板化），拒绝原始输出/路径/URL/secret——防止宠物气泡泄露敏感信息；
- PawPause：事件里会带工具名/命令原文（截断 120 字符），**明文落盘**——这是文件总线方案在隐私上的明确代价，气泡显示前同样应做净化；
- 自研必须照做净化，并权衡"事件文件是否落盘"。

### 4.5 Token 消耗统计：数据从哪来（自研新增需求）

七个项目里只有 **agentpet / oc-claw / clawd** 做了用量统计，且数据来源各不相同；**openpets / petdex / PawPause 完全不统计**。自研要做的第一件事是搞清楚 token 数字从哪来：

| 来源 | 原理 | 代表 | 精确度 | 备注 |
|---|---|---|---|---|
| **读 agent 自己的用量记录** | agent 官方把每次调用的 token 数落盘 | **opencode 原生 SQLite**（见下）、Claude Code JSONL transcript、Codex/OpenClaw JSONL session | 精确 | 首选，零侵入 |
| **解析 transcript 增量** | hook 只告诉 transcript 路径，app 侧按字节偏移增量解析 JSONL，汇总 input+output | agentpet `TranscriptReader.newUsageTokens()`（还跟踪会话中 `/model` 切换，成本按模型分别计价） | 精确 | Claude Code 专用 |
| **订阅额度（非 token）** | 官方 status-line 把额度用占比塞进 stdin | clawd：Claude Code `rate_limits`（v2.1.80+ 官方 statusline 字段 `five_hour/seven_day.used_percentage` + `resets_at`，无需额外 API 调用）；Codex 同理 | 额度百分比 | 适合"配额环"展示，不是 token 数 |
| **本地 telemetry/审计文件** | 轮询 agent 自带统计 | oc-claw：Gemini telemetry、OpenClaw JSONL 里的 usage 字段 | 精确 | agent 支持才有 |
| **估算（无真实数字时兜底）** | 按文本/工具输入粗估 | agentpet `ModelPricing.costUSD()`：per-million USD 单价表（haiku 1/5、sonnet 3/15、opus 15/75 美元；cache write 1.25×、cache read 0.1×） | 估算 | 真实数字缺失时的兜底 |

#### ⭐ opencode 原生自带精确 token 统计（自研可直接白嫖）

opencode（sst/opencode）把每次模型调用的用量直接写进自己的 SQLite（`packages/core/src/database/migration/20260510033149_session_usage.ts` 证实，已在本机 opencode v1.18.11 实测验证）：

- 表结构：`session` + `message`（另有 part/project/todo 等表），message.data 为 JSON；**每条 assistant 消息**带：
  - `data.cost`（USD 成本，opencode 自己算好的）
  - `data.tokens.input / output / reasoning / cache.read / cache.write`
- `session` 表聚合列：`cost, tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write`（实测样例：本会话 `tokens_input=897803, tokens_output=42834, tokens_cache_read=20027008, cost=0.20`）
- `time_created / time_updated` 为毫秒时间戳，可按时间/项目（`project_id`）聚合出每日/每周报表；顺带一提：schema 里还有原生 `todo` 表，与你的 todo 功能可互通
- **数据库路径（跨平台一致，XDG data 语义）**：

| 平台 | 路径 |
|---|---|
| macOS / Linux | `~/.local/share/opencode/opencode.db`（**不是** `~/Library`！实测 v1.18.11） |
| **Windows** | **`%LOCALAPPDATA%\opencode\opencode.db`**（xdg-basedir 在 win32 映射到 LOCALAPPDATA） |
| 非稳定 channel | 同名但带渠道后缀：`opencode-{channel}.db`（如 canary） |

- **读取注意**：① 库是 **WAL 模式**（运行时存在 `-wal/-shm` 文件），宠物侧用**只读连接**即可，opencode 运行中也无冲突；Windows 上 Tauri 用 rusqlite / sqlx（plugin-sql）打开只读连接即可；② 早期版本（纯文件存储时代）没有 SQLite，需读旧格式 `storage/session/*.json` / `storage/message/*.json`，或要求升级 opencode；③ 建议按 opencode 版本检测库文件存在与否，做双路径兼容。

**结论**：自研宠物直接读 opencode 的 SQLite（session 表按时间/项目聚合），即可拿到精确的 token 数、缓存命中、美元成本——**macOS / Linux / Windows 三端同路径语义、同表结构**，不需要插件配合、不需要估算；顺带也拿到了"当前会话用了多少"做气泡汇报。Claude Code 用户则用 transcript 增量解析（agentpet 已验证可行，注意 Windows 上 transcript 路径同样来自 hook payload）。

---

## 5. 对自研的启示与建议

### 5.1 素材：直接复用，别自己画

- 用 codex atlas 格式（pet.json + spritesheet.webp，8×9 / 8×11）作为宠物包标准；
- 素材来源：awesome-codex-pet（178+ 个，CC BY-NC 4.0 注意非商用）、petdex 画廊、ChatGPT `/pet` 生成；
- Tauri 渲染：canvas 按帧时长表播放行序列即可（petdex 的 `sprite.zig` 帧表可直接照抄成 TS 版本）。

### 5.2 agent 状态上报：照抄 openpets 的 opencode 集成

1. **插件**：注册到 `~/.config/opencode/opencode.json` 的 `plugin` 数组；hooks：`event`（permission.asked→waiting、session.error→error、session.status idle→success）+ `chat.message`→thinking + `tool.execute.before`→editing/testing；
2. **传输**：本地 HTTP（127.0.0.1 随机端口或固定 + token），Tauri 侧起一个 tiny HTTP server 或 Unix socket；
3. **节流**：speech 20s / permission 3s / reaction 10s 冷却 + 自身工具回环忽略；
4. **MCP 兜底**：`opencode.json` 的 `mcp` 段注册自建 server（react/say/status 三工具）——这也让 Claude Code 等其它 MCP agent 顺带可用；
5. **指令文件**：`AGENTS.md`/项目指令中声明"有新进展时用 react/say 汇报"，让 agent 主动驱动宠物。

### 5.3 功能扩展：把 openpets 插件 SDK 缩水成自己的模块

- 不一定要做沙箱插件系统；把权限面（schedule/pet:*/ai/notify/network）映射成 Tauri 命令 + 配置清单即可；
- 喝水/休息提醒 = schedule + notify；todo 管理 = 直接对接 todo-lite 的 SQLite（或通过自定义 IPC/HTTP）；对话入口 = 调 opencode 后台会话的入口（如 spawn `opencode run` 或复用其 server API），气泡内展示回复；
- 休息/喝水/专注的现成实现参考 **PawPause**：休息强制全屏遮挡、喝水每日/历史统计、到期宠物放大、macOS 活动窗口检测专注模式；
- 养成/成就（agentpet 思路）可作为差异化玩法。

### 5.4 技术选型

- **自研起点推荐 Tauri v2 + React + TS**（与 todo-lite 同栈，oc-claw 已验证此栈可做宠物）；
- 窗口：透明、无边框、置顶、点击穿透（Tauri `transparent` + `setIgnoreCursorEvents`）；多显示器定位参考 openpets `display.ts`；
- 事件链路选型建议：Tauri 侧用 **fs watch + JSONL 文件总线**（PawPause 方案，最省事）起步，需要细粒度状态（permission/会话错误）或双向控制时再升级为本地 HTTP + token（petdex 方案）；
- **token 统计选型**：直接读 opencode SQLite（session/message 表有精确 tokens + cost），Claude Code 走 transcript 增量解析（agentpet 方案），两者都不需要 agent 配合；额度环展示参考 clawd 的 status-line 方案；
- 若只想"马上有个好用的宠物"：macOS 直接装 petdex App + 挂 opencode 插件（零代码）；想功能全选 openpets 现成平台；想要"休息+喝水+专注+agent 上报"一体化可先试用 PawPause 成品。

---

## 附录 A：项目档案速查

| | openpets | petdex | clawd-on-desk | agentpet | oc-claw | PawPause | cc-haha |
|---|---|---|---|---|---|---|---|
| GitHub | alvinunreal/openpets | crafter-station/petdex | rullerzhou-afk/clawd-on-desk | ntd4996/agentpet | rainnoon/oc-claw | angziii/PawPause | NanmiCoder/cc-haha |
| Stars | ~1.0k | ~3.7k | ~5.8k | ~300 | ~350 | ~50 | ~14k |
| 许可 | MIT | MIT | AGPL-3.0 | MIT | MIT | MIT | MIT |
| 平台 | Win/mac/Linux | mac（桌面端） | Win/mac/Linux | mac 原生+Win/Linux | mac/Win | mac/Win | Win/mac/Linux |
| 语言/框架 | Electron+TS | Zig+Next.js | Electron+JS | Swift/SwiftUI+Tauri | Tauri+React+Rust | Electron+React | Electron+TS |
| opencode 集成 | 插件+MCP+指令 | 插件文件 | 插件+权限桥 | 通用 wrapper | hooks 监听 | 插件写 JSONL | 工作台内置 |
| 扩展机制 | 插件 SDK v3 | 无 | 无 | 无 | 无 | 无 | 无 |

## 附录 B：调研信息源

- 各项目 README / docs（openpets 的 architecture.md、agent-integrations.md、ipc.md、plugins.md、pets.md；petdex 的 README + `petdex-desktop-native` 源码；clawd-on-desk README + `agents/*.js` + `hooks/opencode-install.js`；oc-claw / agentpet / PawPause README + 源码树）
- 关键源码：`opencode-plugin-runtime.ts`（openpets）、`opencode-plugin.js` / `sprite.zig` / `hook_server.zig`（petdex）、`opencode-family.js`（clawd）、`pawpause-agent-hook.js` / `claudeEvents.ts` / `spriteStates.ts`（PawPause）、`TranscriptReader.swift` / `ModelPricing.swift` / `ClaudeHookPayload.swift`（agentpet）、`claude-rate-limits.js` / `codex-rate-limits.js`（clawd）
- Token 统计来源（opencode）：`packages/core/src/database/migration/20260510033149_session_usage.ts`（session/message 表 usage+cost 字段）、`packages/core/src/database/database.ts`（DB 文件名 `opencode.db`、channel 后缀规则）、`packages/core/src/global.ts` + xdg-basedir（路径：macOS/Linux `~/.local/share/opencode`、Windows `%LOCALAPPDATA%\opencode`）；本机 opencode v1.18.11 实测验证（session 聚合列含 cost/tokens_*）
- 素材规范：awesome-codex-pet README（atlas v1/v2、pet.json 样例、安装脚本）
