# PulsePet 设计方案

桌面宠物 App，监听 opencode agent 工作状态并以宠物动画呈现，附带 token 消耗本地统计、喝水/休息提醒（气泡 + 可选烟花模式）、轻量 todo 插件。v1 仅支持 opencode，但架构上预留多 agent 扩展通道。

> 项目范围与决策依据见 [DECISIONS.md](./DECISIONS.md)，行业调研见 [desktop-pet-research.md](./desktop-pet-research.md)。本文只讲技术方案。

---

## 1. 目标与定位

- **核心体验**：opencode 一工作，宠物就开始动 / 跑 / 想；停下来，宠物就 idle。用户不用盯终端也知道 agent 在干啥。
- **POC 定位**：lab 下独立目录、自包含、可独立运行；效果稳定后再考虑拆仓。
- **v1 范围**：opencode 单 agent + 本地 token 统计 + 气泡/烟花提醒 + 轻量 todo 插件 + 渲染细节精致化。
- **跨平台**：macOS + Windows（Linux 非目标）。
- **明确不做**（v1）：用户排行榜（需后端）、双向权限审批 UI、对话入口、focus 模式（窗口屏蔽词检测）、多 pet 同屏、自动更新。

---

## 2. 技术架构

### 2.1 选型

| 层 | 选型 | 说明 |
|---|---|---|
| 桌面壳 | Tauri 2.x (Rust) | 与 todo-lite 同栈，跨 macOS/Windows 套件成熟 |
| 前端 | React 19 + TypeScript + Vite | 与 todo-lite 同栈，便于复用经验与 npm 包 |
| 状态管理 | Zustand | 轻量，与 todo-lite 一致 |
| HTTP server（Rust 侧） | `axum` 或 `tiny_http` | 接收 opencode 插件事件；倾向 `tiny_http`（零异步运行时依赖，体积小）|
| SQLite 读取（Rust 侧）| `rusqlite` + 只读连接 | 读 opencode.db 做统计，WAL 模式与运行时无冲突 |
| SQLite 本地存储 | `tauri-plugin-sql`（sqlite）| 存宠物设置、提醒配置、todo、token 缓存（可选） |
| 系统集成 | `tauri-plugin-notification` / `tauri-plugin-global-shortcut` / TrayIconBuilder | 系统通知、全局热键、托盘 |
| webp 解码（atlas）| `image` crate + `image-webp` | Rust 侧解码 webp atlas → 内存图块下发到 webview，避免前端解码 |

### 2.2 进程拓扑

三个角色，每个独立：

```
┌──────────────────────────────────────────────────────────────┐
│ opencode 进程（Bun 内）                                       │
│  └ PulsePet 插件（JS，~200 行）                              │
│     监听官方插件 hooks → 归一化事件 → POST /state            │
│     写入 ~/.config/opencode/opencode.json 的 plugin 数组     │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP 127.0.0.1:<port>  + x-pulsepet-token
┌──────────────────────▼───────────────────────────────────────┐
│ PulsePet 桌面 App 进程（Tauri/Rust main）                    │
│  ├ HTTP server（接收事件，多 session 状态机）                │
│  ├ opencode.db 只读连接（按需读取 token 聚合）               │
│  ├ Tray（显示/隐藏/设置/退出）                                │
│  ├ 宠物窗口（透明、无边框、置顶、可切换点击穿透）            │
│  ├ 控制面板窗口（普通窗口，设置/Token/Todo/提醒）           │
│  ├ 烟花窗口（全屏透明置顶，粒子动画播放后销毁）              │
│  └ 提醒调度器（Rust 侧定时器，到点发 Tauri event）           │
└────┬───────────────────────────────────────┬────────────────┘
     │ Tauri IPC                              │ Tauri IPC
┌────▼────────────┐                  ┌────────▼───────────┐
│ 宠物 webview     │                  │ 控制面板 webview    │
│  - pet canvas    │                  │  - 状态面板          │
│  - 气泡 UI       │                  │  - Token 报表        │
│  - 右键菜单      │                  │  - Todo 插件界面     │
└──────────────────┘                  │  - 提醒配置          │
                                       │  - 设置（宠物选择、  │
                                       │    穿透开关等）       │
                                       └──────────────────────┘
```

### 2.3 v1 三窗口分工

Tauri 一个 App 可挂多个 webview 窗口。v1 三个窗口：

| 窗口 | 用途 | 关键配置 |
|---|---|---|
| `pet` | 宠物精灵 + 气泡（主可见 UI） | `transparent:true`、`decorations:false`、`alwaysOnTop:true`、`skipTaskbar:true`、`resizable:false`、默认 `ignoreCursorEvents:true`（点击穿透），交互时临时设 false |
| `panel` | 控制面板（设置/Token/Todo/提醒） | 普通窗口、`visible:false` 默认隐藏，托盘"设置"或右键菜单唤起 |
| `fireworks` | 烟花粒子动画 | `transparent:true`、`decorations:false`、`alwaysOnTop:true`、`skipTaskbar:true`、`fullscreen:true` 或跨屏最大化；播放完成（约 3-5s）后 `hide`，下次 `show` |

理由：宠物窗口本身不带 chrome，塞复杂 UI 会破坏透明感；控制面板独立成普通窗口，UX 干净；烟花单独窗口是为了 pet 窗口保持小面积，避免 pet 窗口占屏影响其它操作。

---

## 3. 事件链路

### 3.1 opencode 插件（pulse-pet/opencode-plugin/pulse-pet-hook.js）

跑在 opencode 的 Bun 进程内的官方插件，~200 行 JS：

- **注册**：安装脚本把文件拷到 `~/.config/opencode/plugins/`、并把 `~/.config/opencode/opencode.json` 的 `plugin` 数组合并 `pulse-pet` 一项（带 `--pulse-pet-managed` 标记便于后续安全增删）。
- **监听 hooks**（opencode 官方）→ 归一化 → POST `/state`：

| opencode 事件 | 归一化 `kind` | 说明 |
|---|---|---|
| `session.status` 且 `status.type == idle` | `idle` | agent 空闲 |
| `session.status` 其它 | `working` | agent 工作中 |
| `chat.message` | `thinking` | 模型思考 |
| `tool.execute.before` 且工具为 `edit/write/patch/apply_patch` | `editing` | 写代码 |
| `tool.execute.before` 且工具为 `bash/shell/terminal` 且命令含 `test/vitest/jest/pytest/npm test` 等 | `testing` | 跑测试 |
| `permission.asked` | `waiting-permission` | 等待用户审批 |
| `session.error` | `error` | 出错 |
| `event`（自定义 bus 事件） | 透传分类 | 兜底 |

- **节流**（学习 openpets）：speech 20s / permission 3s / reaction 10s 冷却，原子写 JSON 状态文件防并发。
- **自忽略**：正则跳过 `pulsepet_status/say/react` 工具，防回环（openpets 已踩过的坑）。
- **消息净化**：气泡文案只能来自白名单语音池（thinking/success/error/permission/waiting 五类模板），**不展示原始 prompt/输出/路径/URL/secret 样式 token**。命令行具体内容仅用于归一化分类，**不发给宠物**。
- **token 文件**：`~/.pulsepet/runtime/update-token` mode 0600，由 Tauri App 启动时生成并写文件，插件每次启动读 token。App 退出时清除，下次启动重新生成。
- **端口文件**：`~/.pulsepet/runtime/endpoint` 存 `127.0.0.1:<port>`，端口冲突时 App 会换端口并更新此文件；插件每次发请求前先读最新端口。
- **killswitch**：`~/.pulsepet/runtime/hooks-disabled` 文件存在则插件整体跳过，便于排障。

### 3.2 HTTP server（Rust 侧，端口 + token 鉴权）

- **绑定**：`127.0.0.1:<port>`，端口固定首选 `47811`，冲突时回退随机端口写 endpoint 文件。
- **路由**（参考 petdex `hook_server.zig`）：

| 路由 | 方法 | 鉴权 | 用途 |
|---|---|---|---|
| `/health` | GET | 无 | 心跳探活 |
| `/whoami` | GET | token | 调试 |
| `/state` | POST | token | 收归一化事件，body 含 `{sessionId, kind, agent, project?, detail?}` |
| `/bubble` | POST | token | 直接发气泡（仅 agent 主动调用时用，v1 opencode 不主动调，留接口）|

- **限流**：共享 30 req/s，单次连接 `Connection: close`（一次性）。
- **超时**：连接 ~2s、响应 ~3s。
- **body 上限**：≤16KB。
- **session 区分**：每个请求带 `sessionId`（opencode 每会话唯一），App 端按 sessionId 维护独立状态机。
- **v1 return channel**：HTTP response 允许携带 `{action?}`，v1 服务端总返回 `{action:null}`；v2 加审批 UI 时启用。

### 3.3 多 session 状态机 + 优先级合并

- App 维护 `HashMap<SessionId, SessionState>`，每收事件更新对应 session。
- 显示状态用 clawd 式优先级合并：`error > waiting-permission > testing > editing > thinking > working > idle`。
- 多个 session 同时活跃时，单只宠物显示最高优先级状态（v1 不做多宠物）。
- 长时间无心跳的 session（30s 无事件 + 无 `/health` ping）回收为 `idle`。

### 3.4 AgentAdapter 抽象（v1 仅 opencode，留扩展接口）

```ts
// 前端 / TS 侧
interface AgentAdapter {
  id: string;                          // "opencode" / "claude-code" / ...
  normalizeRawEvent(raw: unknown): NormalizedEvent;  // 插件侧已归一化，此层兜底
  tokenSource: TokenSource;            // "opencode-sqlite" | "transcript-incremental" | "telemetry" | "estimate"
  iconSet: string;                     // "opencode" | "claude-code" | "codex" | ...
}
```

v1 只实现 `OpenCodeAdapter`，但模块边界清晰：将来加 `ClaudeCodeAdapter`（transcript 增量解析）只需新增文件不改主链路。AgentAdapter 在 TS 侧而非 Rust 侧——因为 opencode 插件归一化已在前端语义层完成（JS 写最顺），Rust 只负责 HTTP 接收和 SQLite 读取。

---

## 4. Token 统计

### 4.1 数据源（Rust 侧 rusqlite 只读）

- **路径探测**（启动时按优先级找）：

| 平台 | 候选路径 |
|---|---|
| macOS | `~/.local/share/opencode/opencode.db` → `~/.local/share/opencode/opencode-canary.db` |
| Windows | `%LOCALAPPDATA%\opencode\opencode.db` → `%LOCALAPPDATA%\opencode\opencode-canary.db` |

- 旧版本兜底（纯文件存储时代）：探测 `~/.local/share/opencode/storage/session/*.json`、`storage/message/*.json` —— v1 仅做"探测存在 + 报告版本不支持"，不做完整解析；提示用户升级 opencode。完整解析后置到 v1.1。
- **连接模式**：`OpenFlags::SQLITE_OPEN_READ_ONLY | SQLITE_OPEN_NO_MUTEX`，**不**用 WAL 也不写任何 journal；只读连接与 opencode 运行时连接互不冲突（WAL 模式允许 N 读 1 写）。
- **聚合查询**（按时间跨度 + 项目）：

```sql
-- by 会话
SELECT session_id, project_id, cost,
       tokens_input, tokens_output, tokens_reasoning,
       tokens_cache_read, tokens_cache_write,
       time_created, time_updated
FROM session
WHERE time_updated >= ? AND time_updated <= ?
ORDER BY time_updated DESC;

-- by 天
SELECT
  strftime('%Y-%m-%d', time_updated/1000, 'unixepoch', 'localtime') AS day,
  project_id,
  SUM(cost) AS cost,
  SUM(tokens_input) AS input, SUM(tokens_output) AS output,
  SUM(tokens_reasoning) AS reasoning,
  SUM(tokens_cache_read) AS cache_read, SUM(tokens_cache_write) AS cache_write
FROM session
WHERE time_updated >= ? AND time_updated <= ?
GROUP BY day, project_id
ORDER BY day DESC;
```

周 / 任意跨度由前端把 `from/to` 传给 Rust 计算，避免后端写一套固定维度。

### 4.2 Tauri 命令（暴露给 TS）

```rust
#[tauri::command]
fn token_stats_opencode_path() -> Result<Option<PathBuf>, String>;  // 探测路径，无则 None

#[tauri::command]
fn token_stats_query(from_ms: i64, to_ms: i64, group_by: String)
  -> Result<Vec<TokenRow>, String>;   // group_by: "session" | "day" | "week" | "range"

#[tauri::command]
fn token_stats_current_session(session_id: String) -> Result<Option<TokenRow>, String>;
```

### 4.3 展示（控制面板 Token 标签页）

- **顶部 KPI 卡**：所选时间跨度的总 input/output/cache_read/cost。
- **时间序列图**：默认按天柱状图（recharts 或自己画 SVG，倾向自画 SVG 避免 bundle 体积），可在 7d / 30d / 任意跨度切换。
- **项目分布**：选跨度内的项目占比饼图 + 列表。
- **会话列表**：跨度内的会话按 token 降序，单条可展开详情（input/output/reasoning/cache 分布）。
- **当前会话气泡汇报**：宠物收到 `session.status == idle` 事件且本会话有 ≥1 条 token 记录时，气泡显示"本期用了 Xk input / Yk output / $ Z"——这是 token 功能在宠物窗口里的直接体现。

### 4.4 v2 排行榜（不在 v1 实现）

仅本地聚合；上报 API（用户登录 + 数据上传）留 v2 单独设计。v1 端到端不引入后端服务、不请求网络权限。

---

## 5. 提醒（喝水 / 休息 + 烟花）

### 5.1 调度器（Rust 侧）

- v1 用 Tauri 的 `tokio` runtime + `tokio::time::interval` 最简实现：每 1 分钟 tick 一次，检查所有启用的提醒规则是否到点。
- 提醒规则持久化在脉冲内 SQLite（`pulsemet.db`）的 `reminders` 表。
- 到点：发送 Tauri event `reminder://trigger` 给前端，前端根据规则决定渲染气泡还是烟花。
- 调度器读 SQLite 表后做 in-memory 倒计时，避免每分钟查库；用户改设置后通过 Tauri command 通知调度器 reload。

### 5.2 气泡模式（默认）

- 宠物头顶气泡文案：`该喝水啦 💧` / `休息一下 ☕` / `站起来走走 🚶` 等（提醒规则可配文案）。
- 气泡有效时长 8s 自动消失；点击宠物可"已确认"提前消失；3 分钟内不重复提醒同一条。
- 文案净化同 §3.1 —— 提醒文案是用户自配或模板，防泄露敏感信息。

### 5.3 烟花模式（用户设置中开启）

- **触发**：用户在提醒规则上勾"烟花模式"或全局开关。
- **效果**：宠物位置为发射点，朝屏幕中心或随机方向发一束粒子烟花，3-5s 消散，粒子带渐变与拖尾，参考日本动漫烟花的"流光花瓣"质感。
- **实现选型**：HTML canvas 全屏透明窗口 + 粒子动画。理由：① 跨 macOS/Windows 一致（不用写两套平台原生）② Tauri 多窗口天然支持 ③ 体积小（不引入 pixi/three）④ canvas 2D 粒子配合 radial gradient + 拖尾即可达到动漫质感。
  - 粒子数 ~300-500；requestAnimationFrame 60fps；颜色用 HSL 渐变 + alpha fade；拖尾用上一帧叠加半透明黑（或透明 + globalCompositeOperation）。
- **音频**（可选，默认关）：可选"啾——砰"短音效，音频文件内置在 `src-tauri/resources/`，通过 Tauri audio API 播放。M5 阶段评估是否需要。

### 5.4 数据模型

```sql
CREATE TABLE reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,                  -- "hydration" | "rest" | "custom"
  label TEXT NOT NULL,                 -- 用户可配文案
  interval_minutes INTEGER NOT NULL,   -- 触发间隔
  start_time TEXT,                     -- 当日起始时间 HH:MM（如 "09:00"）
  end_time TEXT,                       -- 当日结束时间 HH:MM
  enabled INTEGER NOT NULL DEFAULT 1,
  use_fireworks INTEGER NOT NULL DEFAULT 0,  -- 单条覆盖全局开关
  last_triggered_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE reminder_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reminder_id INTEGER NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
  triggered_at TEXT NOT NULL,
  acked_at TEXT,                        -- 用户点击确认时间，可空
  dismissed_via TEXT                    -- "bubble" | "fireworks" | "auto"
);
```

历史统计（喝水次数 / 休息次数）从 `reminder_logs` 聚合。

---

## 6. 素材与精灵渲染

### 6.1 v1 内置占位精灵

- v1 起步用 1 张 PNG（128×128 单图，draw 几帧切换）打通链路。占位用一只简洁像素风小猫（姿势力求中性：坐姿 + 单眨眼），作者自备或用开源 CC0 素材（避免许可问题）。
- 渲染：canvas 2D，按 60fps 切帧（占位阶段帧切换极简，主要验证状态机驱动）。
- 占位精灵只覆盖最常用 5 状态：`idle / thinking / working / success / error`，其余状态映射到最近的同类（如 `waiting-permission→thinking`、`testing→working`）。

### 6.2 atlas 加载器（M5 补入）

- 素材格式标准：codex atlas（pet.json + spritesheet.webp，v1 8×9 = 1536×1872 / v2 8×11 = 1536×2288，单帧 192×208）。
- 加载顺序：用户配置的 `pet` → 内置占位 → 用户 `~/.codex/pets/` 扫描 → `~/.petdex/pets/` 扫描。
- 渲染帧时长表：直接照抄 petdex `sprite.zig` 的 9 状态帧时长表（TS 版本）。

| 状态 | atlas 行号 | 帧时长（petdex 值） |
|---|---|---|
| idle | 0 | 6 帧不规则眨眼 |
| running-right | 1 | uniform |
| running-left | 2 | uniform |
| waving | 3 | uniform |
| jumping | 4 | uniform |
| failed | 5 | uniform |
| waiting | 6 | uniform |
| running | 7 | uniform |
| review | 8 | uniform |

- webp 解码在 Rust 侧用 `image` + `image-webp`，避免前端起 worker 解大图；解码后下发 RGBA 图块数组到 webview，前端只做 canvas 切帧。
- atlas 加载器完成前，所有状态都用占位精灵；完成后切换为 atlas 帧时长表（pet.json 元数据 + 帧时长表）。

### 6.3 渲染细节精致化（M6）

- **拖拽**：webview 不直接处理鼠标（默认穿透），用 Tauri `window.startDrag()` API 或 Rust 侧手动监听 `WindowEvent::CursorMove` + `set_position`。拖拽时临时关闭穿透、释放恢复。
- **位置记忆**：宠物位置 + 所在显示器 id 写入 `pulsepet.db` 的 `app_state` 表，启动时还原。
- **跨显示器拖拽**：Tauri `availableMonitors()` API 计算屏幕边界，跨屏拖拽实时更新窗口位置。
- **启动定位**：上次所在显示器 + 上次坐标；若该显示器已不存在则回退主显示器。
- **点击穿透可切换**：右键菜单"切换交互模式" + 全局热键（默认 `Ctrl+Shift+P` for pet / `⌘+Shift+P` macOS，与 opencode 不冲突），穿透开 = 纯展示，穿透关 = 可拖拽 / 右键。
- **多显示器烟花**：v1 默认在主显示器播放；M6 后再评估是否跨屏烟花（Tauri 多窗口拼接或原生）。

---

## 7. 窗口与系统集成

### 7.1 窗口配置（tauri.conf.json 节选）

```jsonc
{
  "app": {
    "windows": [
      {
        "label": "pet",
        "url": "index.html#/pet",
        "title": "PulsePet",
        "width": 220, "height": 220,
        "transparent": true,
        "decorations": false,
        "alwaysOnTop": true,
        "skipTaskbar": true,
        "resizable": false,
        "visible": true,
        "shadow": false
      },
      {
        "label": "panel",
        "url": "index.html#/panel",
        "title": "PulsePet 控制面板",
        "width": 900, "height": 640,
        "visible": false
      },
      {
        "label": "fireworks",
        "url": "index.html#/fireworks",
        "transparent": true,
        "decorations": false,
        "alwaysOnTop": true,
        "skipTaskbar": true,
        "visible": false,
        "shadow": false,
        "maximized": true
      }
    ]
  }
}
```

`pet` 与 `fireworks` 默认 `ignoreCursorEvents=false`（关闭穿透），运行时通过 `setIgnoreCursorEvents` 动态切换。

### 7.2 托盘

- 图标 + 右键菜单：
  - 显示 / 隐藏宠物
  - 切换交互模式（穿透开 / 关）
  - 打开控制面板
  - 暂停所有提醒（v1 单一开关，便于"勿扰"）
  - 退出
- 左键单击：切换控制面板可见性。
- 注意：`TrayIconEvent::Click` 在 Down/Up 各触发一次，toggle 逻辑须判断 `button_state`（与 todo-lite 同坑）。

### 7.3 全局快捷键

| 热键 | macOS | Windows / Linux | 功能 |
|---|---|---|---|
| 唤起控制面板 | `⌘+Shift+P` | `Ctrl+Shift+P` | 切换 panel 可见 |
| 切换宠物穿透 | `⌘+Shift+Alt+P` | `Ctrl+Shift+Alt+P` | 切换 ignoreCursorEvents |
| 测试烟花 | `⌘+Shift+Alt+F` | `Ctrl+Shift+Alt+F` | 调试用：手动放一束烟花 |

避免与 opencode 默认热键冲突（opencode 用 `Ctrl+O` 等）；调试烟花热键 v1 release 时移除。

### 7.4 单实例锁

Tauri `tauri-plugin-single-instance` 插件。第二实例启动时把已运行实例的 panel 唤起并退出自身。

---

## 8. Todo 插件机制

### 8.1 v1 插件机制（参考 openpets 缩水版）

v1 实现"机制 + 仅挂 todo 一个插件"，不留完整 SDK 但留 manifest 槽位。

```jsonc
// pulsepet.db.plugins 表存元数据，插件包本身放目录
// ~/.pulsepet/plugins/todo/
//   ├── plugin.json
//   └── ...（v1 仅内置，不允许第三方安装）
```

`plugin.json`：

```jsonc
{
  "id": "built-in-todo",
  "name": "Todo",
  "version": "0.1.0",
  "manifestVersion": 1,
  "permissions": ["schedule", "notify", "ui:panel-tab"],  // 声明需要的权限面
  "configSchema": { ... },                                  // 控制面板自动渲染设置表单
  "panelTab": { "title": "Todo", "icon": "check-square" }   // 控制面板加一个 tab
}
```

权限面（v1 仅声明，不做运行时复检，因 v1 无沙箱、所有插件皆内置）：
`schedule`（用提醒调度器）、`notify`（弹气泡）、`ui:panel-tab`（控制面板注入 tab）、`todo:*`（读写内置 todo 表）。

### 8.2 Todo 数据模型

```sql
CREATE TABLE todos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  notes TEXT,
  priority INTEGER NOT NULL DEFAULT 0,    -- 0/1/2/3
  due_date TEXT,                          -- YYYY-MM-DD
  completed_at TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE todo_tags (
  todo_id INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,
  tag TEXT NOT NULL,
  PRIMARY KEY (todo_id, tag)
);
```

比 todo-lite 简化（无 lists/sections/groups），单层 todo 列表 + 标签 + 优先级 + 截止日期。够用为准。

### 8.3 Todo 与宠物的联动

- 任务到点前 X 分钟（用户可配，默认 5 min），宠物气泡显示"还有 X 分钟要完成「任务名」"。
- 任务完成时宠物播放 `waving` 动画 + 气泡"干得漂亮 🎉"。
- 完成今日全部任务，宠物头顶气泡显示今日完成数。
- 这些联动通过 §3 调度器 + 宠物 webview 的 Tauri event 走，不引入新通道。

---

## 9. 项目结构

```
lab/pulse-pet/
├── src/                               # 前端 React
│   ├── pet/                            # 宠物 webview
│   │   ├── PetCanvas.tsx              # canvas 精灵渲染（占位 + atlas 共用接口）
│   │   ├── Bubble.tsx                 # 气泡
│   │   ├── PetMenu.tsx                # 右键菜单
│   │   └── petStore.ts                # zustand: 当前 state / session 优先级合并
│   ├── panel/                         # 控制面板 webview
│   │   ├── Dashboard.tsx              # 当前状态总览
│   │   ├── TokenStats.tsx             # token 统计
│   │   ├── Reminders.tsx              # 提醒配置
│   │   ├── Settings.tsx               # 宠物选择 / 穿透 / 烟花全局开关
│   │   └── plugins/
│   │       └── Todo.tsx               # todo 插件 UI
│   ├── fireworks/                     # 烟花 webview
│   │   ├── Fireworks.tsx              # canvas 粒子动画
│   │   └── particles.ts               # 粒子系统
│   ├── lib/
│   │   ├── http-bridge.ts             # 收来自 Rust 的 Tauri event（事件→petStore）
│   │   ├── agent-adapter.ts           # AgentAdapter 抽象
│   │   ├── adapters/
│   │   │   └── opencode.ts            # opencode 归一化与图标集
│   │   ├── sprite.ts                  # atlas 帧时长表 + 切帧逻辑（照抄 sprite.zig）
│   │   ├── db.ts                      # 本地 SQLite 访问
│   │   └── token-stats.ts             # 调 Rust 命令取 token 数据
│   ├── store/                         # zustand stores
│   └── styles/
├── src-tauri/
│   ├── src/
│   │   ├── main.rs / lib.rs
│   │   ├── http_server.rs              # tiny_http 路由 + token 鉴权
│   │   ├── session_state.rs            # 多 session 状态机 + 优先级合并
│   │   ├── token_stats.rs              # rusqlite 只读 + 聚合查询
│   │   ├── reminders.rs                # 调度器（tokio interval）
│   │   ├── windows.rs                  # pet/panel/fireworks 窗口管理 + spawn
│   │   ├── tray.rs                     # 托盘
│   │   └── db.rs                       # 本地 SQLite 迁移
│   ├── capabilities/                   # 权限配置
│   ├── resources/
│   │   └── fireworks.mp3               # 可选音效
│   ├── icons/
│   ├── migrations/                     # 本地 SQLite 迁移
│   └── Cargo.toml
├── opencode-plugin/
│   ├── pulse-pet-hook.js               # opencode 插件本体（~200 行）
│   ├── install.sh / install.ps1        # 安装脚本
│   └── README.md
├── DECISIONS.md                        # v1 范围决策记录
├── desktop-pet-research.md             # 调研报告
├── DESIGN.md                           # 本文档
├── AGENTS.md                           # 项目级指令（pet 引导 + 项目说明）
└── README.md
```

---

## 10. 实施里程碑

> 时序为依赖关系；M2/M3/M4 可部分并行，M7 可穿插。

### M1 骨架（1 周）
- Tauri 2 + React + Vite 初始化
- 三窗口配置（pet/panel/fireworks）+ 路由
- 占位精灵 canvas 渲染（5 状态切换）
- 托盘 + 单实例锁 + 控制面板唤起
- 本地 SQLite（`pulsemet.db`）+ 基础表迁移
- `app_state` 表存位置 + 退出/启动恢复

### M2 事件链路（1 周）
- Rust 侧 `tiny_http` server + 路由 + token 鉴权 + 限流
- token 文件 / endpoint 文件 / killswitch 机制
- opencode 插件 JS 实现 + 安装脚本 + opencode.json 合并/卸载
- `session_state.rs` 多 session 状态机 + 优先级合并
- 前端 `http-bridge` + `petStore` + 状态驱动动画
- 端到端验证：开 opencode 跑任务 → 宠物切换 idle/thinking/working/success

### M3 Token 统计（1 周）
- Rust 侧 `token_stats.rs`：路径探测 + rusqlite 只读连接 + 聚合查询命令
- 前端 Token 标签页：KPI / 时序图（自画 SVG）/ 项目分布 / 会话列表
- 时间跨度切换：7d / 30d / 任意
- 当前会话气泡汇报（session idle + 有用量时显示）

### M4 提醒（1 周）
- `reminders` 表 + 控制面板提醒配置 UI
- Rust 侧调度器（tokio interval + in-memory 倒计时 + reload command）
- 气泡渲染 + 8s 自动消失 + 确认提前消失
- 烟花窗口 + canvas 粒子系统（动漫流光花瓣质感）
- 全局烟花开关 + 单条覆盖 + 提醒日志表

### M5 atlas 加载器（0.5-1 周）
- Rust 侧 webp 解码 + 图块下发
- 前端 `sprite.ts`：9 状态帧时长表 + atlas 切帧
- 用户 `~/.codex/pets/`、`~/.petdex/pets/` 扫描
- 控制面板"选择宠物"下拉
- 占位精灵切换为 atlas 后做完整 9 状态映射

### M6 渲染细节精致化（1 周）
- 拖拽（临时关穿透 + startDrag）
- 多显示器边界计算 + 跨屏拖拽
- 上次显示器位置记忆 + 启动恢复
- 右键菜单 + 全局热键
- 穿透可切换（包含调试烟花热键）

### M7 Todo 插件 + 插件机制骨架（1 周）
- 插件 manifest + 权限面（声明级，v1 不做运行时复检）
- todo 表 + 控制面板 Todo tab UI
- todo 与宠物联动（到点气泡 / 完成 waving）
- 提醒调度器复用（todo 截止日期到点提前提醒）

### M8 收尾（0.5 周）
- 国化（en/zh，v1 只双语）
- Windows 兼容验证（macOS 开发环境为主）
- Tauri capability 权限收敛 + 安全检查（消息净化回溯测）
- README + AGENTS.md

**v1 总工期粗估**：6-8 周（单人非全职）。

---

## 11. v1 Done 标准

满足下列全部即视为 v1 完成：

- [ ] M1-M6 全部跑通（核心链路、提醒、烟花、atlas、渲染交互全可用）
- [ ] M7 插件机制骨架 + todo MVP 可用
- [ ] macOS 全流程自测通过；Windows 在主流分辨率下能跑（边缘行为有已知限制可记入 README）
- [ ] 安装 opencode 插件后无人值守跑 30 分钟，宠物状态变化与实际 agent 状态吻合
- [ ] Token 统计数字与 opencode.db 直接查询对账一致（误差 ≤0.01 USD）
- [ ] 喝水提醒触发一次气泡 + 一次烟花，两次都按预期渲染与消失
- [ ] 控制面板关闭/重启 App 后设置/位置/历史提醒日志保留
- [ ] 消息净化测试：气泡不出现任何原始路径/URL/代码片段
- [ ] 自忽略测试：插件不会被自身工具回环

---

## 12. 风险与说明

- **opencode.db schema 变更**：v1 锁定当前已知 schema（session 表 cost/tokens_* 字段实测于 v1.18.11）；未来 opencode 升级若改 schema，启动时探测失败需提示用户升级 pulse-pet。建议 Rust 侧查询前做表的 `PRAGMA table_info(session)` 字段白名单检测。
- **WAL 模式只读连接**：rusqlite 只读 + 不开 WAL 模式 + open flags 仅 `READ_ONLY` 是文档安全用法；但 SQLite 在 wal 文件不存在时只读打开可能报 `unable to open database file`，需先冷启动一次 opencode 让 wal/shm 存在；v1 检测 wal 文件缺失时回退到 "数据库未运行/未初始化"提示。
- **HTTP 端口冲突**：固定 47811 占用则换随机端口写 endpoint 文件；插件每次发请求前读最新端口（与 petdex 一致策略）。
- **多 session 抢镜**：v1 单宠物优先级合并可能让"我最不关心的那个 session 报错时宠物一直显示 error"；M6 后视用户反馈再评估切换规则（如"最近 5s 有事件的 session 优先"）。
- **烟花在 Windows 透明窗口**：Tauri 2 在 Windows 上透明窗口的 `maximized + transparent + alwaysOnTop` 组合若有渲染问题，回退方案是 fireworks 窗口不透明、背景用接近桌面的深色 + 自适应 alpha 通道；M4 第一天先在 macOS 验证，第二天验 Windows。
- **webp 解码跨平台**：`image-webp` crate 在 Windows 上编译需 `nasm`；若 CI 复杂度上升，回退方案是 atlas 直接要求 png 格式（petdex 也接受 png），跳过 webp。
- **opencode 插件运行时**：opencode 插件 API 目前在演进，hooks 字段稳定但可能新增；v1 监听字段做存在性检测后兜底 `event` bus；安装脚本做"幂等合并 + `--pulse-pet-managed` 标记"保证卸载不误删用户原有插件。
- **Tauri 2 API 变化**：锁定最新稳定版，按文档调整（与 todo-lite 同策略）。
- **Windows 端实机验证延后**：v1 主要在 macOS 开发，Windows 在 M4/M8 阶段交叉验证。

---

## 13. 打包与 CI

- **macOS**：`npm run tauri build` 产出 `.app` + `.dmg`。
- **Windows**：通过 GitHub Actions 产出（同 todo-lite），触发方式：push tag `pulse-pet-v*`，矩阵 `windows-latest + macos-latest`，产出附到 draft Release。
- **opencode 插件**：随主包发布，也可独立 zip 发布（用户用 `install.sh/ps1` 安装，无需 Tauri app 也能尝试）。
- **包体积目标**：Tauri app ~10-20MB；atlas 加载器完成后，素材包不入主包，用户从 petdex/awesome-codex-pet 自取。

---

## 14. 下一步

进入 v1 实施：
1. 落地 `pulse-pet/` 项目骨架（M1：package.json / Cargo.toml / 三窗口路由 / 托盘 / 本地 SQLite 迁移 / 占位精灵）
2. 同步更新 `AGENTS.md`（项目级指令：opencode 看到 pulse-pet 工作时该不该驱动宠物，pet 与 pulse-pet 的边界）
3. PR 单独提交每里程碑到 develop 分支（POC 阶段不直接 push 主仓，按 AGENTS.md 约定）