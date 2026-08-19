# PulsePet

桌面宠物 App：监听 opencode agent 工作状态，用一只像素小猫实时呈现（9 行姿态 atlas 动画），配 token 本地统计、喝水/休息提醒（气泡 + 烟花）、轻量 todo 插件（派生提醒 / 完成联动庆祝）。

> POC 阶段，效果验证通过后可能拆仓独立演进。设计与范围见 [DESIGN.md](./DESIGN.md)、[DECISIONS.md](./DECISIONS.md)，验收依据见 [TEST-CASES.md](./TEST-CASES.md)。

## 技术栈

| 层 | 选型 |
|---|---|
| 桌面壳 | Tauri 2.x (Rust) |
| 前端 | React 19 + TypeScript + Vite |
| 状态管理 | Zustand |
| 本地存储 | SQLite（`rusqlite` 直连，`pulsepet.db`） |
| 系统集成 | 托盘（TrayIcon）、单实例锁、全局热键（tauri-plugin-single-instance / global-shortcut，均仅 Rust 侧使用） |
| i18n | 自研轻量字典（`src/lib/i18n.ts`，zh/en 双语，无第三方依赖） |

## 快速上手

```bash
# 安装依赖
npm install

# 开发模式（三窗口 + 托盘，每次启动加载最新代码）
npm run tauri dev

# 前端单测（纯逻辑：状态降级映射 / canvas 缩放 / i18n 字典等）
npm test

# 生产构建（.app / .dmg）
npm run tauri build
```

### 运行最新版

`npm run tauri build` 每次都会把最新产物覆盖写入同一路径（无需复制到 /Applications）：

```
src-tauri/target/release/bundle/macos/PulsePet.app
src-tauri/target/release/bundle/dmg/PulsePet_<version>_aarch64.dmg
```

- **推荐**：构建后直接 `open src-tauri/target/release/bundle/macos/PulsePet.app` —— 始终是最新版。
- **注意**：若你曾把旧版 `.app` 复制到 /Applications（或 ~/Applications），Launchpad / Finder 里的入口指向那份**副本**，不会随重新构建自动更新；需重新复制覆盖，或直接改用上面的 target 路径。
- 开发热更新用 `npm run tauri dev`。
- 确认是否最新：重新 `npm run tauri build` 后 `open` 一次 target 路径的 `.app` 即可。

> **改名清理说明**：productName 曾于 M8 由 `pulse-pet` 改为 `PulsePet`，`tauri build` 不会清理旧名产物——如果你的 `target/release/bundle/macos/` 下同时存在 `pulse-pet.app`（旧残留）与 `PulsePet.app`，Spotlight 会搜到两个应用，删除旧的 `pulse-pet.app` 即可（两者 identifier 相同，数据不受影响）。

---

## 连接 opencode（事件链路）

PulsePet 通过一个 **opencode 插件**感知 agent 状态：插件监听 opencode 的官方 hooks / 事件总线 → 归一化为 9 种状态 → POST 到本机 `127.0.0.1` 的 PulsePet HTTP 端点 → 宠物动画切换。全程本机回环，无需任何外网。

### 安装插件

```bash
cd pulse-pet/opencode-plugin

# macOS / Linux
./install.sh

# Windows（PowerShell）
.\install.ps1
```

安装脚本做两件事（来源：`install.sh` / `install.ps1` / `opencode-config.mjs`）：

1. 拷贝 `pulse-pet-hook.js` 到 `~/.config/opencode/plugins/`（Windows：`%APPDATA%\opencode\plugins\`，目录不存在时回退 `~/.config/opencode`）；
2. 在 opencode 配置（优先 `~/.config/opencode/opencode.json`，其次 `opencode.jsonc`，都没有则新建 `opencode.json`）的顶层 `plugin` 数组插入一项：

   ```jsonc
   {
     "plugin": [
       "./plugins/pulse-pet-hook.js" // --pulse-pet-managed
     ]
   }
   ```

   JSONC 感知（已有注释/尾逗号保留），**幂等**（重复安装不产生重复项），用户原有 plugin 项不动。

安装后**重启 opencode** 生效。依赖：`node` 仅用于安装期的 JSONC 合并；插件本体运行在 opencode 自带的 Bun 运行时。

### 手动安装（不想跑脚本时）

等价于上面两步：

1. 把 `opencode-plugin/pulse-pet-hook.js` 复制到 `~/.config/opencode/plugins/pulse-pet-hook.js`；
2. 在 `~/.config/opencode/opencode.json`（或 `.jsonc`）顶层加 `"plugin": ["./plugins/pulse-pet-hook.js"]`；
3. 重启 opencode。

### 如何确认生效

1. 先启动 PulsePet App（托盘出现小猫图标）；
2. 在 opencode 里随便跑一个任务（或发一条消息）；
3. 宠物应在数秒内切换姿态：发消息 → thinking（思考）；编辑文件 → editing；跑测试 → testing；请求权限 → waiting-permission；出错 → error；任务结束回 idle。

若宠物不动：确认 App 在运行（托盘有图标）；确认插件已安装且 opencode 重启过；排查见下文「故障排查」。

### 原理简述：token 与端口（用户无需手动配置）

- PulsePet 启动时在**本机回环** `127.0.0.1:47811` 起 HTTP 服务；端口被占用时自动换随机端口。
- 同时生成一次性随机 token，与当前端口一起写入 `~/.pulsepet/runtime/`（`update-token` + `endpoint` 两个文件；Windows 在 `%LOCALAPPDATA%\pulsepet\runtime\`）。token 文件权限 0600（POSIX）。
- 插件每次发请求前**读最新文件**（端口回退后无需重装插件）；无 token 的请求一律 401。事件内容只在内存中传递，**不落盘**。
- App 退出时清除 token/endpoint 文件；被强杀（如 SIGKILL）残留的文件会在下次启动时重新生成覆盖（死 token / 死端口不会造成持久影响）。

### App 未启动时插件的行为

静默：endpoint/token 文件缺失、连接拒绝、超时、401 一律不打日志、不报错给 opencode 终端，按指数退避（立即 → 1s → 2s → 5s → 30s 封顶）重试；App 启动后下一次事件即自动恢复，无需重启 opencode。

**紧急停用（killswitch）**：创建 `~/.pulsepet/runtime/hooks-disabled` 文件 → 插件整体跳过（不发任何请求）；删除该文件立即恢复，无需重启任何一方。

### 状态映射（插件归一化）

| opencode 信号 | 宠物状态 |
|---|---|
| `session.idle` / `session.status(idle)` | idle |
| `session.status(busy/retry)` | working |
| `chat.message`（你发了新消息） | thinking |
| `tool.execute.before`：edit/write/patch/apply_patch | editing |
| `tool.execute.before`：bash/shell/terminal（命令含 test/vitest/jest/pytest 等） | testing |
| `tool.execute.before`：其它工具 | working |
| `tool.execute.after`（工具完成） | working（瞬态复位主信号） |
| `permission.ask` / 总线 `permission.asked` | waiting-permission |
| `session.error` | error |

节流：思考/成功/错误类 20s、权限类 3s、反应类 10s 一条（同类中更高优先级状态可立即放行）；App 侧另有 30s 瞬态超时兜底（无事件自动回 working/idle）。

### 卸载插件

```bash
./install.sh --uninstall      # macOS / Linux
.\install.ps1 -Uninstall      # Windows
```

只移除带 `--pulse-pet-managed` 标记的项 + 删除插件文件；你自己的其它 plugin 项保留。

---

## 自定义宠物导入

PulsePet 使用 **codex atlas 格式**素材（社区仓库 petdex / awesome-codex-pet 均为此格式）：一个目录 = 一只宠物，内含 `pet.json`（元数据）+ `spritesheet`（精灵图，webp 或 png）。

### 放在哪里

App 按以下顺序寻找素材（来源：`src-tauri/src/atlas.rs` 的 `resolve_requested` / `scan_pets_in`）：

1. **用户选择**（App 设置页"选择宠物"指定的 id）——按 内置 → `~/.codex/pets/<id>/` → `~/.petdex/pets/<id>/` 顺序找这个 id；
2. **无选择（"自动"）**：内置小猫 `blinking-kitty`（默认）；
3. 最终兜底：内置小猫（编译期内嵌，永不吃紧）。

所以**导入社区宠物**只需：

```bash
# macOS / Linux：把素材目录放进 codex 或 petdex 的扫描路径（任选其一）
mkdir -p ~/.codex/pets
cp -r <下载解压出的宠物目录> ~/.codex/pets/<宠物id>
# Windows：路径为 %USERPROFILE%\.codex\pets\<宠物id> 或 %USERPROFILE%\.petdex\pets\<宠物id>
```

同名 id 时 codex 优先于 petdex。放好后打开设置页，下拉列表即出现（损坏项会标注不可选）。

### pet.json 格式

```jsonc
{
  "id": "my-pet",                    // 可选，缺省用目录名
  "displayName": "我的宠物",          // 可选，下拉显示名，缺省用目录名
  "spritesheetPath": "cat.webp",     // 可选，缺省按 spritesheet.webp → spritesheet.png 顺序找
  "cols": 8,                         // 可选；声明了就必须与实际网格一致，否则拒载
  "rows": 9                          // 可选；同上
}
```

`pet.json` ≤ 64KB、spritesheet ≤ 8MB、图像单边 ≤ 16384px、解码分配 ≤ 512MB（超限即拒载）。

### 网格标准（重要）

- **固定 8 列**；行数只接受 **9（v1）或 11（v2）**；
- 单帧宽高比必须 192:208（= 12:13），帧宽须为 12 的倍数——即标准图块 1536×1872（8×9）或 1536×2288（8×11），**干净缩放**（如 768×936、3072×3744）也可；
- 不满足（如 8×10、16×9、任意裁剪尺寸）→ **整只拒载**，不做按帧强行裁剪。

9 行姿态采用 **petdex 官方行序**（与 `src/lib/sprite.ts` 的 `PETDEX_ROWS` 一致）：

| 行号 | petdex 姿态名 | 对应 PulsePet 状态 |
|---|---|---|
| 0 | idle | idle |
| 1 | running-right | editing（向前推进） |
| 2 | running-left | testing（反向跑动） |
| 3 | waving | success（庆祝挥手） |
| 4 | jumping | **预留备用行，v1 不驱动**（无状态映射到此行） |
| 5 | failed | error |
| 6 | waiting | thinking（张望） |
| 7 | running | working（原地跑动） |
| 8 | review | waiting-permission（申请审批） |

做社区素材时按 petdex 行序排列即可（`running-right`/`running-left`/`waving` 等姿态语义与 petdex 社区通用）；v1 不读取帧时长表，按等帧播放。

### 损坏 / 非标准素材的行为

选中或自动落到一只损坏宠物时：**不崩溃**，回退内置小猫继续可用，设置页显示回退原因（如「该素材网格尺寸非标准：spritesheet 为 1536×2080，已回退内置占位 blinking-kitty」）。

### 切换与热替换

设置页下拉选择后**立即热替换**（无需重启 App，也无需重启 opencode）；选择持久化（重启保留）；选"自动"恢复默认小猫。

---

## 功能总览与使用

### 系统托盘（右键菜单五项，顺序固定）

| 菜单项 | 行为 |
|---|---|
| 显示/隐藏宠物 | 切换宠物窗口可见性 |
| 切换交互模式（穿透开/关） | 勾选项；同全局热键 ⌘/Ctrl+Shift+Alt+P |
| 打开控制面板 | 显示 900×640 面板窗口 |
| 暂停所有提醒 | 勾选项；暂停期间所有提醒不触发、周期规则倒计时顺延（恢复后**不补弹**）；状态重启保留 |
| 退出 | 退出 App（退出时自动保存宠物位置、清除 token/endpoint） |

**托盘左键**单击 = 显示/隐藏宠物（与第一项菜单同语义）。再次启动 PulsePet 时（单实例锁）：不会开第二个实例，而是唤起已运行实例的控制面板。

### 全局热键（系统级，任何 App 前台都有效）

| 热键 | macOS | Windows/Linux | 动作 |
|---|---|---|---|
| 唤起/隐藏面板 | ⌘⇧P | Ctrl+Shift+P | 切换控制面板可见 |
| 切换点击穿透 | ⌘⇧⌥P | Ctrl+Shift+Alt+P | 开/关穿透模式 |
| 调试烟花 | ⌘⇧⌥F | Ctrl+Shift+Alt+F | 手动放一束烟花（**仅开发构建**，正式版不注册） |

与 opencode TUI 默认快捷键（Ctrl+O 等）无冲突（全部含 Shift 修饰）。热键被其它应用占用时启动日志会有 `global shortcut register failed`，面板/托盘通道仍可用。

### 宠物交互

- **单击宠物**：手动轮换姿态（开发/演示用；气泡显示时单击 = 确认提醒）；
- **拖拽**：按住移动 ≥4px 进入原生窗口拖拽，跨显示器由系统处理；松开即停，位置持续记忆（含所在显示器，重启还原到原屏原位，屏幕不存在时回主屏）；
- **右键宠物**：菜单三项——设置…（直达设置页）/ 切换交互模式（穿透：开/关）/ 隐藏宠物；
- **点击穿透（纯展示模式）**：开启后鼠标事件全部透出——不可拖拽、无右键菜单，动画照常播放；经热键、托盘或宠物右键菜单切回。状态重启保留。用途：把宠物放在屏幕角落长期展示又不挡操作。

### 提醒（面板「提醒」页）

- **规则类型**：喝水 / 休息 / 自定义（含 1-140 字符自定义文案）；内置模板一键套用（喝水 30min / 休息 60min / 站立 90min）；
- **间隔与时间窗**：间隔 1-1440 分钟；可选起始/结束时间（HH:MM），支持跨午夜窗口（如 22:00-06:00）；
- **烟花模式**：单条勾选 = 该条到点放烟花（约 3-5s 全屏粒子）替代气泡；「全局烟花模式」开 = 未单独勾选的提醒也升级为烟花；
- **触发行为**：气泡 8 秒自动消失，或点宠物确认；历史（reminder_logs）按类型统计今日/累计；
- **去重**：同规则 3 分钟内不重复；系统睡眠错过的不补发；
- **暂停**：托盘「暂停所有提醒」（见上）；面板「试一试」可手动触发一次（同样受暂停与去重约束）；
- **修改即时生效**：增删改后调度器自动重载，无需重启。

### Todo（面板「Todo」页，内置插件）

- 任务字段：标题（必填 ≤140）/ 备注（≤2000）/ 优先级（无/低/中/高）/ 截止（日期或日期+时间）/ 提前提醒分钟数（0-10080）/ 标签（≤20 个，逗号分隔）；
- **派生提醒**：截止**带时间**且提前提醒 > 0 → 到点前宠物气泡「还有 X 分钟要完成「任务名」」（单次，触发后不再重复）；提前提醒 = 0 或纯日期 → 完全无提醒；改截止时间 → 重新计时提醒一次；
- **完成联动**：勾选完成 → 宠物挥手庆祝 + 气泡（今日全部完成时显示「今日完成 N 项」）；完成的任务派生提醒自动删除，历史日志保留；
- 列表 ↑↓ 拖序（立即生效并记忆）；两步删除确认（点"删除"再点"确认删除？"）。

### Token 统计（面板「Token」页）

- 数据源：只读查询 opencode 本地数据库（`~/.local/share/opencode/opencode.db`），不联网、不上传；
- 时间窗：近 7 天 / 近 30 天 / 自定义日期区间（含当天）；
- 维度：按天 / 按周 / 整段汇总；会话列表按用量排序可展开明细（input/output/reasoning/cache/cost）；
- 项目分布饼图 + KPI 卡（input / output / cache read / cost，USD）；
- **会话汇报气泡**：一个会话结束（idle）且有用量的 60 秒内，宠物气泡显示「本期用了 Xk input / Yk output / $ Z」并短暂进入 success 姿态（无用量/数字陈旧不出气泡）。

### 语言切换（面板「设置」页）

- 中文 / English 即时切换（含三窗口、托盘菜单、面板标题、气泡文案模板）；选择持久化，重启保留；
- 默认语言跟随系统（zh 开头 → 中文；其余含 en 之外的一律回退 English）；
- 不翻译：宠物状态技术名（idle/working…）、品牌名、你自己输入的提醒文案/任务标题。

---

## 数据存储与重置

| 数据 | 位置（macOS） | 说明 |
|---|---|---|
| 主数据库 `pulsepet.db` | `~/Library/Application Support/com.pulsepet.app/` | 设置/宠物选择/位置/穿透/提醒规则与历史/todo 全部在此（SQLite） |
| 运行时 token/endpoint | `~/.pulsepet/runtime/` | 每次启动重新生成、退出清除（Windows：`%LOCALAPPDATA%\pulsepet\runtime\`） |
| 插件文件 | `~/.config/opencode/plugins/pulse-pet-hook.js` | 由安装脚本管理 |
| 插件登记 | `~/.config/opencode/opencode.json` 的 `plugin` 数组 | 带 `--pulse-pet-managed` 标记 |
| 自定义宠物素材 | `~/.codex/pets/`、`~/.petdex/pets/` | 你自己放的，卸载 App 不动它们 |

**完全重置**：退出 App → 删除 `pulsepet.db` → 重启（所有设置/提醒/todo 回到初始状态；插件与素材不受影响）。

**只停用事件监听**：创建 `~/.pulsepet/runtime/hooks-disabled`（见上文 killswitch）。

---

## 已知限制与故障排查

### 已知限制

- **Windows 仅 CI 构建验证，未实机测试**（无实机；M8 范围定案）。透明窗口/托盘/热键等运行时行为在 Windows 实机上未验证；烟花透明窗口若有渲染异常，回退预案见 DESIGN §12。token 文件位于 `%LOCALAPPDATA%\pulsepet\runtime\`（Windows 无 POSIX 0600 语义，依赖单用户登录 + 默认 ACL）。atlas webp 解码在 CI `windows-latest` 可编译；若未来 CI 因 nasm 类工具链失败，回退方案是 atlas 仅接受 png。
- **多显示器场景未实机验证**（单屏开发环境）：位置记忆/还原、跨屏拖拽、烟花跟随所在屏均为代码级实现 + 单测钉住，多屏实机确认后移。
- **Rust 侧边缘错误文案仅中文**：前端校验先行拦截，仅"前端放过、Rust 拒绝"的边缘路径会看到中文错误串（v1 不做全量错误串双语）。

### 故障排查

| 症状 | 排查 |
|---|---|
| 宠物不随 agent 状态变化 | ① App 在运行吗（托盘有图标）② 插件装了吗、opencode 重启过吗 ③ `~/.pulsepet/runtime/` 下有 `endpoint`/`update-token` 文件吗（无 = App 未启动或刚退出）④ 有 `hooks-disabled` 文件吗（有 = killswitch 生效，删掉即恢复） |
| 端口 47811 被占用 | 无需处理：自动换随机端口并写入 endpoint 文件，插件每次读最新端口 |
| 下载的宠物不显示 / 显示"素材损坏" | 检查目录结构（`pet.json` + `spritesheet.webp`/`.png` 在**目录根**）、网格是否符合 8×9 / 8×11 标准（见上文）；损坏素材会回退内置小猫并提示原因 |
| 热键无响应 | 可能被其它应用占用（启动日志 `global shortcut register failed`）；用托盘菜单同名项替代 |
| 宠物不见了 | 托盘左键点一次（显示/隐藏）；或被移到了另一台显示器边缘（穿透模式下用热键/托盘切回再拖回） |
| 首次构建很慢 | 首次 `cargo` 编译从零构建 tauri 依赖（数百 crate），正常；受限网络下载 stall 时用 `CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false cargo fetch`（禁用 HTTP/2 多路复用） |

### 调试用环境变量（一般无需设置）

| 变量 | 默认 | 作用 |
|---|---|---|
| `PULSEPET_REMINDER_TICK_MS` | 60000 | 提醒调度器 tick 周期（实测可调短） |
| `PULSEPET_TRANSIENT_TIMEOUT_MS` | 30000 | 瞬态状态（editing/testing 等）超时回 working |
| `PULSEPET_IDLE_TIMEOUT_MS` | 30000 | 无事件回 idle |
| `PULSEPET_TOKEN_REPORT_MAX_LAG_MS` | 60000 | 会话汇报气泡的新鲜度阈值 |

---

## 国际化（i18n，M8）

- **双语**：中文（zh）/ English（en），v1 只此两种；默认语言跟随系统；
- **切换入口**：面板 → 设置 → 语言；持久化 `app_state` 键 `ui.language`；
- **生效范围**：三窗口 + 托盘菜单 + 面板标题 + 气泡文案模板 + 各页 UI 文案；切换即时（前端 `ui://language` 事件同步三窗口，Rust 侧托盘菜单原地重建，无需重启）。

## Windows 支持（已知限制）

见上文「已知限制」第一条。CI 构建链路已验证（下节）。

## CI 发布流程

- 仓库根 `.github/workflows/build.yml`（与本仓库 todo-lite 共用）：push tag 触发，pattern 同时匹配 `todo-lite-v*` 与 `pulse-pet-v*`，按 tag 前缀切换工作目录与产物命名；
- **发布 PulsePet**：`git tag pulse-pet-v0.1.0 && git push origin pulse-pet-v0.1.0` → GitHub Actions 矩阵（windows-latest + macos-latest）构建，产物（`PulsePet_<version>_<os-target>` 风格，如 `PulsePet_0.1.0_aarch64.dmg` / Windows 安装包）挂到 draft Release，手动核对后发布；
- todo-lite 既有 `todo-lite-v*` 触发不受影响（同 workflow，前缀分流）。

## 运行时视觉验证（供复验）

pet 是 macOS 透明合成窗口（`transparent` + `macOSPrivateApi` + `backgroundColor`）。**无头/后台自动化环境**可能因 WebKit 渲染进程被系统挂起（App Nap / 无前台激活）而得到"内容不渲染"的假阴性。可信验证步骤：

1. **在真实 GUI 会话启动**（`open <target 路径 .app>` 或 `npm run tauri dev`），避免 SSH/launchd 无头启动，等待 app 前台激活。
2. **用全屏截屏** `screencapture -x`（走 WindowServer 合成结果，包含透明窗口内容）；**不要用** `screencapture -l <windowID>`（单窗口离屏捕获对 WKWebView 跨进程合成内容不可靠，会得到全透明假象）。
3. **量化指标**（对 pet 窗口区域逐像素分析）：
   - 内容：猫毛白 `#f4f4f7` 像素数 > 0（约 5 万+）、`bright(>200)` 像素 > 0；
   - 透明：窗口边缘内外像素连续性（avg/median 色差 ≈ 0，无窗口框）。
4. **前置自检**：确认 WebContent 进程 CPU > 0（rAF 60fps 在跑）；AX 树里 `AXWebArea` 有 `AXChildren`（含 canvas）。若两者为 0，说明渲染进程被挂起，该次测量无效，换真实 GUI 会话重测。
5. 最终以**人工目验**为准（用户实测：宠物可见 + 周围透明）。

## 目录结构

```
pulse-pet/
├── src/                      # 前端 React（三窗口按 hash 路由：#/pet #/panel #/fireworks）
│   ├── pet/                  # 宠物 webview（PetCanvas 精灵渲染 / PetMenu 右键菜单 / Bubble 气泡）
│   ├── panel/                # 控制面板 webview（TokenStats / Reminders / Settings / plugins/Todo）
│   ├── fireworks/            # 烟花 webview（canvas 粒子引擎，无 UI 文案）
│   ├── lib/
│   │   ├── i18n.ts           # M8 国际化：zh/en 字典 + t() + 语言 store + 三窗口同步
│   │   ├── state.ts          # 归一化状态类型 + 降级映射
│   │   ├── reminders.ts / todos.ts   # 提醒 / todo 纯函数与 Rust 命令封装
│   │   └── ...（bubble/scale/atlas/token-stats/interaction 等桥与纯函数）
│   └── styles/global.css
├── src-tauri/
│   ├── src/
│   │   ├── main.rs / lib.rs  # 入口与 setup 接线（命令注册 / 事件链路 / 调度器）
│   │   ├── db.rs             # SQLite 事务化迁移（幂等）+ app_state 读写
│   │   ├── i18n.rs           # M8：Rust 侧语言位 + 托盘/标题/气泡文案 + ui_set_language
│   │   ├── http_server.rs    # 本地事件 HTTP（127.0.0.1 + token + 限流）
│   │   ├── reminder_scheduler.rs  # 提醒调度 + 烟花编排（显示器 bounds 计算）
│   │   ├── todos.rs / plugins.rs   # M7 todo 插件与派生提醒
│   │   ├── atlas.rs          # M5 atlas 加载（内置/codex/petdex + 网格校验）
│   │   └── windows.rs / tray.rs / hotkeys.rs / interaction.rs / token_stats.rs
│   ├── migrations/           # 001-init.sql / 002-m7-todo.sql
│   ├── capabilities/default.json  # M8 收敛：仅 core:event:default
│   └── Cargo.toml
├── opencode-plugin/          # opencode 插件（install.sh / install.ps1 + hook，详见其 README）
├── scripts/gen-assets.mjs    # 生成内置精灵素材 + 图标源
├── DESIGN.md / TEST-CASES.md / DECISIONS.md
└── README.md
```

## 里程碑进展（M1 → M8，v1 收尾）

- **M1** ✅ 三窗口骨架、占位精灵渲染、托盘 + 单实例锁、SQLite 迁移、位置记忆。
- **M2** ✅ tiny_http 事件链路（token/endpoint/killswitch + 限流/鉴权）+ opencode 插件（归一化/节流/退避/净化）+ 多 session 状态机。
- **M3** ✅ token 统计——只读聚合查询、panel Token 页（KPI / 时序 / 项目饼图 / 会话明细）、当前会话气泡汇报。
- **M4** ✅ 提醒（规则 CRUD / 调度器 / 气泡 + 烟花 / 历史统计 / 全局暂停）。
- **M5** ✅ atlas 加载（codex/petdex 素材 / 网格校验 / 损坏回退 / 双内置宠物 / 热替换）。
- **M6** ✅ 交互（拖拽 / 点击穿透 / 全局热键 / 右键菜单 / 位置记忆显示器维度）。
- **M7** ✅ 插件机制骨架 + 内置 todo（CRUD / tags / 派生提醒 / 完成联动 / 今日全清）。
- **M8** ✅ 收尾——i18n（zh/en）、Windows CI 级兼容（TC-CI-02）、capability 收敛 + TC-SEC 回溯、README/AGENTS 更新、遗留清偿（A1 迁移事务化 / A2 重武装边界 / A3 校验口径契约 / A4 静默吞错 / A5 pending 补发 watchdog / A6 install.ps1 BOM + permission.asked / A7 主屏兜底注释固化 / A8 不可达分支定案保留 / A9 烟花点位显示器 bounds 计算）。
- **后移项**：多屏实机验证（TC-APP-10/11、跨屏烟花）、Windows 实机验证（TC-DONE-03 等）——具备硬件时；心跳 / `/health` 限流豁免——v2（心跳引入时）；TC-DONE-01~09 综合验收——v1 Done 验收任务。

详见 [DESIGN.md §10](./DESIGN.md) 实施里程碑。

## M3 实测记录：opencode session 表写入时机（TC-TK-11）

2026-08-16，opencode 1.18.18 + 本机真实 `~/.local/share/opencode/opencode.db`（WAL 模式）：

- `session` 表的 `tokens_*` / `cost` 为**逐 message 增量写入**，非 session 结束聚合写——观测一个进行中的会话，5s 间隔两次采样 `tokens_input` 58263 → 58748，`time_updated` 跟随最近一次写入推进（滞后秒级）。
- `cost` 可能为 0（订阅/plan 模式无按量计费数据；观测到多个大用量会话 cost=0.0）。
- 据此气泡汇报只需新鲜度护栏：`time_updated` 与 `session.status=idle` 时间差 < 阈值（默认 60s，`PULSEPET_TOKEN_REPORT_MAX_LAG_MS` 可配）才显示，避免陈旧数字；无记录或全零不出气泡（TC-TK-12）。结论同时记录在 `src-tauri/src/token_stats.rs` 模块注释。
