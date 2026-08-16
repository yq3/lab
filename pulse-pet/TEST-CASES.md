# PulsePet 测试用例

> 依据：`DESIGN.md`（技术方案）、`DECISIONS.md`（范围决策）、`DESIGN-REVIEW.md`（评审记录，A 组矛盾 / B 组缺口 / C 组建议均已纳入用例）、`desktop-pet-research.md`（行业调研）。
> 用途：v1 各里程碑（M1-M8）与 v1 Done 标准的验收依据。用例编号按模块前缀，可在里程碑结束时逐条勾验。
> 评审：本文件评审见 [TEST-CASES-REVIEW.md](./TEST-CASES-REVIEW.md)；2026-08-10 已按其 P0/P1/P2 项修订合并。

## 编号约定

| 前缀 | 模块 | 对应里程碑 |
|---|---|---|
| TC-APP | 应用骨架 / 窗口 / 托盘 / 单实例 | M1 |
| TC-EV | 事件链路（插件 / HTTP / 状态机） | M2 |
| TC-TK | Token 统计 | M3 |
| TC-RM | 提醒（气泡 / 烟花 / 调度器） | M4 |
| TC-SP | 素材与精灵渲染（占位 / atlas） | M1 / M5 |
| TC-WIN | 窗口交互（拖拽 / 穿透 / 热键 / 位置记忆） | M6 |
| TC-TD | Todo 插件 | M7 |
| TC-SEC | 安全与隐私（净化 / 鉴权） | M2 / M8 |
| TC-CI | 打包与 CI | M8 |
| TC-DONE | v1 Done 标准综合验收 | 收尾 |

---

## 一、TC-APP 应用骨架与系统集成

### TC-APP-01 三窗口启动

- **前置**：App 首次启动，无历史状态。
- **步骤**：启动 App。
- **预期**：
  1. `pet` 窗口显示（220×220、**视觉透明**——截屏/目视确认窗口区域除宠物像素外背景透出桌面内容，非白/灰/黑底、无窗口框感、无边框、置顶、不在任务栏、不可 resize、无阴影）；
  2. `pet` 初始运行时非穿透（`ignoreCursorEvents` 非 tauri.conf.json 配置字段，运行时默认 `false` 可拖拽/右键；对应 DESIGN-REVIEW A1 修正后的默认值，运行时查询确认）；
  3. `panel` 窗口隐藏（`visible:false`）；
  4. `fireworks` 窗口隐藏；
  5. 托盘图标出现；
  6. **pet 画布无任何文字渲染、无状态圆点**（M1 R4 已移除状态文字；M2 起移除状态圆点，画布仅显示宠物本身；状态通过动画表现，DESIGN §6.1）。

### TC-APP-02 单实例锁

- **前置**：App 已运行。
- **步骤**：再次启动第二个实例。
- **预期**：第二实例立即退出；已运行实例的 panel 窗口被唤起显示；不产生第二个托盘图标、不出现重复宠物。

### TC-APP-03 托盘左键切换宠物可见性

- **前置**：App 运行中，pet 可见。
- **步骤**：左键单击托盘图标 → 再左键单击。
- **预期**：第一次单击 pet 隐藏；第二次单击 pet 恢复显示。**注意**：`TrayIconEvent::Click` 在 Down/Up 各触发一次，toggle 逻辑须判断 `button_state`，否则一次单击会连续切换两次（与 todo-lite 同坑）。

### TC-APP-04 托盘右键菜单

- **前置**：App 运行中。
- **步骤**：右键托盘图标。
- **预期**：菜单含：显示/隐藏宠物、切换交互模式（穿透开/关）、打开控制面板、暂停所有提醒、退出。

### TC-APP-05 托盘菜单项动作

- **前置**：App 运行中；先配置一条 1 分钟间隔的提醒并启用。
- **步骤**：依次点击菜单项：
  1. "打开控制面板"；
  2. "显示/隐藏宠物"；
  3. "暂停所有提醒"；
  4. "退出"。
- **预期**：
  1. panel 显示；
  2. pet 可见性切换；
  3. 暂停生效：等待 90 秒（超过 1 个提醒周期）无任何气泡/烟花；
  4. App 完全退出，托盘图标消失，进程结束。

### TC-APP-06 全局热键唤起控制面板

- **步骤**：App 运行中，依次按 `⌘+Shift+P`（Mac）/ `Ctrl+Shift+P`（Win）两次。
- **预期**：第一次 panel 显示，第二次 panel 隐藏；与托盘唤起状态同步（若 panel 已由托盘打开，热键应关闭它）。

### TC-APP-07 全局热键切换穿透

- **前置**：M6 之后实现穿透切换。
- **步骤**：按 `⌘+Shift+Alt+P`（Mac）/ `Ctrl+Shift+Alt+P`（Win）。
- **预期**：pet 窗口在"可交互（可拖拽/右键）"与"纯展示（鼠标穿透）"间切换；切换后宠物仍可见且动画正常；穿透态下鼠标事件完全透出（点宠物不会命中窗口）。

### TC-APP-08 热键避免冲突

- **步骤**：与 opencode 默认热键（`Ctrl+O` 等）对照检查。
- **预期**：PulsePet 三个全局热键不与 opencode 及常见 IDE 默认热键冲突。

### TC-APP-09 位置记忆与启动恢复（M6+）

- **前置**：拖动宠物到次显示器（若有多显示器）的某坐标。
- **步骤**：退出 App → 重启。
- **预期**：宠物出现在上次所在显示器 + 上次坐标；位置与显示器 id 已写入 `pulsepet.db` 的 `app_state` 表。

### TC-APP-10 位置记忆的显示器回退（M6+）

- **前置**：上次宠物在某个外接显示器（记录其 id）。
- **步骤**：拔掉该显示器 → 重启 App。
- **预期**：宠物回退到主显示器显示，不崩溃、不显示在屏幕外。

### TC-APP-11 跨显示器拖拽（M6+）

- **前置**：多显示器环境，M6 实现跨屏拖拽后。
- **步骤**：拖动宠物从当前显示器跨越到另一显示器。
- **预期**：宠物平滑跨屏，位置实时更新；跨屏过程中不被边缘卡住；落点坐标记录正确。

### TC-APP-12 设置持久化（M1 基线 / M5+ 扩展）

- **前置**：M1 基线只改穿透开关、烟花全局开关、提醒规则；M5 起追加改宠物选择。
- **步骤**：
  1. M1 基线：在 panel 改穿透开关 / 烟花全局开关 / 提醒规则若干项；
  2. M5 起追加：在 panel 改宠物选择一项。
  3. 关闭 App → 重启 → 打开 panel 核对。
- **预期**：所有设置保留（存于本地 SQLite）；宠物位置、提醒日志同样保留（对应 v1 Done 标准第 6 条）。

### TC-APP-13 首启引导

- **前置**：干净环境（无 `pulsepet.db`）。
- **步骤**：启动 App。
- **预期**：本地 SQLite 自动迁移创建全部基础表（`app_state` / `reminders` / `reminder_logs` / `todos` / `todo_tags` / `plugins`），无迁移报错；后续启动跳过迁移。

---

## 二、TC-EV 事件链路

### TC-EV-01 插件安装（macOS）

- **前置**：opencode 已安装；`~/.config/opencode/opencode.json` 存在（或可创建）。
- **步骤**：运行 `install.sh`。
- **追加步骤**：在用户 `opencode.json` 的 plugin 段前后加注释行与尾逗号 → 再次运行 install.sh。
- **预期**：
  1. `pulse-pet-hook.js` 拷贝到 `~/.config/opencode/plugins/`；
  2. `opencode.json` 的 `plugin` 数组合并 `pulse-pet` 一项，带 `--pulse-pet-managed` 标记；本地项为路径 spec（如 `./plugins/pulse-pet-hook.js`，裸名会被 opencode 当 npm 包——M2 实测修正）；
  3. 用户原有 plugin 项保留不误删；
  4. 重复安装幂等（不产生重复项）；
  5. JSONC 感知：注释行与尾逗号保留，合并后文件仍为合法 opencode 配置（参考 openpets `opencode-config.ts`）。

### TC-EV-02 插件卸载

- **前置**：插件已安装，且用户另有自己的 plugin 项。
- **步骤**：运行卸载流程。
- **预期**：只移除带 `--pulse-pet-managed` 标记的项；用户原有插件项保留；插件文件删除。

### TC-EV-03 插件安装（Windows）

- **前置**：Windows 环境。
- **步骤**：运行 `install.ps1`。
- **预期**：同 TC-EV-01 效果（路径为 `%APPDATA%` 体系下的 opencode 配置目录）。

### TC-EV-04 事件归一化全集

- **前置**：插件已装、App 已启动，构造以下 opencode 场景（真实跑任务）。
- **步骤**：依次触发：agent 空闲 → 用户发消息（模型思考）→ 写文件工具 → 跑测试命令 → 触发权限请求 → 报错 → 任务完成 idle。
- **预期**：宠物状态按表依次切换：

| opencode 事件 | 宠物状态 |
|---|---|
| `session.status` 且 `status.type == idle` | idle（状态复位主信号） |
| `session.status` 其它 | working |
| `chat.message` | thinking |
| `tool.execute.before` + `edit/write/patch/apply_patch` | editing |
| `tool.execute.before` + `bash/shell/terminal` + 命令含 test/vitest/jest/pytest/npm test | testing |
| `permission.asked` | waiting-permission |
| `session.error` | error |
| 其它 `event`（自定义 bus 事件） | 按分类透传 |

### TC-EV-05 状态复位（M2 补充验证项①）

- **前置**：真实 opencode 跑完整任务。
- **步骤**：M2 期间实测：
  1. `tool.execute.after` 事件是否存在？字段如何区分？
  2. `chat.message` 完成事件是否存在？
- **预期**：记录实测结论并选定"主复位信号 + 兜底信号"（设计默认：`tool.execute.after` → working 为主，`session.status` 非 idle 兜底；若 opencode 无 after 事件则反之）。

### TC-EV-06 状态复位（M2 补充验证项③）

- **前置**：插件已装。
- **步骤**：跑一个完整任务，观察宠物在 editing/thinking/testing/waiting-permission 上的停留时间。
- **预期**：任一瞬态在 N 秒（默认 30s，可配）内无新事件 → 回退 `working`；再无事件 30s → 回退 `idle`；宠物不会卡在瞬态超过 30s。

### TC-EV-07 App 未启动时插件静默

- **前置**：App 未启动（或已退出）。
- **步骤**：在 opencode 里跑任意任务触发事件。
- **预期**：
  1. opencode 终端无任何报错、无日志输出（静默跳过）；
  2. 插件不因连接拒绝/超时/401 崩溃；
  3. 指数退避生效（首次立即重试 1 次，之后 1s→2s→5s→30s 封顶）——**观察方式**：插件模块级单测 mock 时间断言退避序列（静默要求下集成层无法直接观测间隔）；集成层仅验证"静默跳过 + 恢复后立即投递"。可选：测试期设 `PULSEPET_DEBUG=1` 输出退避时间戳（仅测试期临时机制，不随 release 发布）。
- **恢复**：启动 App 后，下一个事件立即恢复正常投递（endpoint/token 文件重新出现即恢复）。

### TC-EV-08 token 文件生命周期

- **前置**：App 运行中。
- **步骤**：
  1. 检查 `~/.pulsepet/runtime/update-token`（POSIX 端；Windows 端见 TC-EV-08b）；
  2. 退出 App；
  3. 再次启动。
- **预期**：
  1. 文件存在，mode 0600，内容是随机 token；
  2. App 退出时文件被清除；
  3. 再次启动生成**新** token（每次会话轮换）。

### TC-EV-08b token / endpoint / killswitch 文件路径（Windows）

- **前置**：Windows 环境，App 运行中。
- **步骤**：
  1. 检查 `%LOCALAPPDATA%\pulsepet\runtime\update-token` 与 `endpoint`；
  2. 退出 App → 再次启动；
  3. 创建 `hooks-disabled` → 触发事件 → 删除。
- **预期**：
  1. 两文件位于 `%LOCALAPPDATA%\pulsepet\runtime\`，内容与 POSIX 端一致（随机 token / `127.0.0.1:<port>`）；
  2. 退出时 token 文件清除、重启后重新生成（新 token）；
  3. killswitch 同目录生效（行为同 TC-EV-10）。

### TC-EV-09 endpoint 文件与端口冲突回退

- **前置**：App 运行中，端口 47811 空闲。
- **步骤**：
  1. 检查 `~/.pulsepet/runtime/endpoint` 内容；
  2. 占用 47811 端口 → 重启 App；
  3. 再检查 endpoint 文件。
- **预期**：
  1. 首选端口为 `127.0.0.1:47811` 且写入文件；
  2. 冲突时自动换随机端口并更新 endpoint 文件；
  3. 插件每次发请求前读到的是最新端口（改端口后无需重装插件即可恢复）。

### TC-EV-10 killswitch

- **前置**：插件已装、App 已启动。
- **步骤**：创建 `~/.pulsepet/runtime/hooks-disabled` → 跑任务触发事件 → 删除该文件 → 再跑任务。
- **预期**：文件存在期间插件整体跳过（不 POST、不发事件）；删除后立即恢复；无需重启 opencode。

### TC-EV-11 HTTP 鉴权

- **前置**：App 运行中。
- **步骤**：
  1. 不带 token 直接 `curl -X POST 127.0.0.1:47811/state`；
  2. 带错误 token；
  3. 带正确 token（读 endpoint/token 文件）。
- **预期**：
  1. 401；
  2. 401；
  3. 200（`{action:null}`）。

### TC-EV-12 HTTP 路由表

- **步骤**：对以下路由分别请求：
  - `GET /health`（无鉴权）；
  - `GET /whoami`（需 token）；
  - `POST /state`（需 token，body `{sessionId, kind, agent, project?, detail?}`）；
  - `POST /bubble`（需 token）。
- **预期**：/health 返回 200；/whoami 返回 200 且能标识当前实例；/state、/bubble 带 token 返回 200；未知路由返回 404。
- **body 契约校验**（追加）：
  1. body 缺 `sessionId` → 400；
  2. body 缺 `kind` → 400；
  3. body 缺 `agent` → 400（`sessionId/kind/agent` 必填，`project`/`detail` 可缺省）；
  4. `kind` 为 8 种归一化取值之外的非法值 → 400；
  5. 合法 body（含缺省 `project`/`detail`）→ 200。

### TC-EV-13 限流

- **前置**：App 运行中。
- **步骤**：快速并发 POST /state 超过共享 30 req/s。
- **预期**：超出部分的请求被拒绝（429 或连接拒绝），不超过的请求正常处理；限流为全局共享而非 per-session。

### TC-EV-14 超时与连接语义

- **步骤**：模拟慢连接与长响应（可用测试客户端拖慢）：
  1. 连接建立后迟迟不发请求；
  2. 请求后迟迟不读响应。
- **预期**（M2 实测后措辞）：服务端 accept 周期 2s（`recv_timeout`，保证线程不阻塞、抗慢连接打挂）；响应超时由插件侧 `AbortSignal.timeout(3000)` 客户端兜底（服务端处理为纯内存操作无慢路径）；单次连接 `Connection: close`（一次性，响应后连接关闭，同 socket 复用被拒）。

### TC-EV-15 body 上限

- **步骤**：POST /state 带超过 16KB 的 body。
- **预期**：请求被拒（413 或 400），服务不崩溃；≤16KB 正常处理。

### TC-EV-16 多 session 状态机

- **前置**：同一台机器开两个 opencode 会话（不同项目）。
- **步骤**：交替触发事件：会话 A `editing`、会话 B `error`、会话 A `idle`、会话 B `working`。
- **预期**：单只宠物按优先级合并显示最高优先级状态：`error > waiting-permission > testing > editing > thinking > working > idle`；B 报 error 时宠物显示 error，即使 A 正在 editing。

### TC-EV-17 session 回收

- **前置**：某 session 最近有事件。
- **步骤**：停止该 session 的事件 30s+，另一 session 继续发事件。
- **预期**：无事件 session 回收为 idle（30s 无 `/state` 事件）；其状态不再影响宠物显示；`/health` 不参与回收判定。

### TC-EV-18 节流

- **前置**：高频事件环境；kind → 冷却分类映射按 DESIGN §3.1 定案表（speech：thinking/success/error；permission：waiting-permission；reaction：working/editing/testing/idle）。
- **步骤**：连续快速触发：
  1. thinking / success / error 各 5 次（speech 类）；
  2. waiting-permission 5 次（permission 类）；
  3. working / editing / testing / idle 各 5 次（reaction 类）。
- **预期**：speech 20s / permission 3s / reaction 10s 冷却生效；冷却期内同类事件被丢弃；冷却结束后恢复；三类冷却互不干扰（如 waiting-permission 只占 permission 冷却，不占 speech 冷却）。

### TC-EV-19 自忽略（防回环）

- **前置**：插件已装，App 运行中。
- **步骤**：人工模拟（或让 agent 调用）`pulsepet_status/say/react` 工具，随后触发工具执行事件。
- **预期**：以 `pulsepet_status/say/react` 为工具名的事件被正则跳过，不产生任何宠物状态变化/气泡（防回环）；其它工具事件正常。

### TC-EV-20 消息净化（插件侧）

- **前置**：真实跑一个任务。
- **步骤**：任务包含：带路径的报错、带 URL 的输出、敏感样式 token（如 `sk-...`）、长代码片段；跑完检查气泡与宠物收到的所有文案。
- **预期**：气泡文案只来自白名单语音池（thinking/success/error/permission/waiting 五类模板）；不出现任何原始 prompt / 输出文本 / 路径 / URL / secret 样式 token；命令行具体内容只用于分类，从未进入气泡；waiting 类为 PulsePet 在 openpets 四类（thinking/success/error/permission）基础上的扩展模板，独立定义、非照搬。

### TC-EV-21 气泡文案长度与单行约束

- **步骤**：触发各类气泡。
- **预期**：文案单行、1-140 字符（对齐 openpets 安全语音池约束）；超长模板被截断或丢弃。

### TC-EV-22 事件→气泡的展示一致性

- **前置**：App + 插件就绪。
- **步骤**：无人值守跑 30 分钟（真实任务），同步观察终端与宠物。
- **预期**：宠物状态变化与实际 agent 状态吻合；无卡死、无错乱（对应 v1 Done 标准第 3 条）。

### TC-EV-23 AgentAdapter 抽象存在性

- **步骤**：代码审查 + 编译验证。
- **预期**：存在 `AgentAdapter` 接口（id / normalizeRawEvent / tokenSource / iconSet）；v1 仅实现 `OpenCodeAdapter`；新增 ClaudeCodeAdapter 不需要改主链路（文件级别验证）。

---

## 三、TC-TK Token 统计

### TC-TK-01 数据库路径探测（macOS）

- **前置**：opencode 已用过（存在 `~/.local/share/opencode/opencode.db`）。
- **步骤**：启动 App → panel → Token 标签页。
- **预期**：探测到主库路径；`token_stats_opencode_path` 返回 `Some(path)`。

### TC-TK-02 数据库路径探测（canary / Windows）

- **步骤**：
  1. 主库不存在、`opencode-canary.db` 存在（macOS）；
  2. Windows 上 `%LOCALAPPDATA%\opencode\opencode.db` 存在。
- **预期**：分别探测到 canary 库 / Windows 库路径。

### TC-TK-03 数据库不存在时的处理

- **前置**：opencode 未初始化（无 db、无 wal/shm）。
- **步骤**：启动 App → Token 标签页。
- **预期**：`token_stats_opencode_path` 返回 `None`；UI 显示"数据库未运行/未初始化"类提示，不崩溃。

### TC-TK-04 旧版本兜底探测

- **前置**：仅存在旧格式 `~/.local/share/opencode/storage/session/*.json`。
- **步骤**：启动 App → Token 标签页。
- **预期**：探测到旧格式存在并提示"请升级 opencode"；不做完整解析；不崩溃。

### TC-TK-05 只读连接与 opencode 并发

- **前置**：opencode 正在跑任务（WAL 模式写入中）。
- **步骤**：同时在 panel 反复查询 Token 数据。
- **预期**：查询正常返回，无锁冲突、无 "database is locked" 错误；opencode 不受影响；连接为只读（对 opencode.db 无任何写入）。

### TC-TK-06 聚合查询准确性

- **前置**：opencode.db 有真实数据。
- **步骤**：直接对 opencode.db 执行设计中的两条 SQL（by session / by day），与 UI 结果核对。
- **预期**：by session 行数与字段一致；by day 的 `strftime` 天维度、SUM 聚合一致（对账误差 ≤0.01 USD，对应 v1 Done 标准第 4 条）。

### TC-TK-07 group_by 维度

- **步骤**：切换 `session / day / week / range` 四种 group_by。
- **预期**：每种返回结构正确的 TokenRow 集合；week 与任意 range 由前端传 from/to 到 Rust 计算；不出现后端写死维度的情况。

### TC-TK-08 时间跨度切换

- **步骤**：panel Token 页切换 7d / 30d / 任意跨度。
- **预期**：KPI 卡、时序图、项目分布、会话列表随之更新；时间边界正确（含当天）。

### TC-TK-09 展示组件

- **步骤**：查看 Token 页各区块。
- **预期**：
  1. 顶部 KPI 卡：跨度内总 input / output / cache_read / cost；
  2. 时序图：默认按天柱状图（自画 SVG，不依赖重依赖库）；
  3. 项目分布：占比饼图 + 列表；
  4. 会话列表：按 token 降序，单条可展开详情（input/output/reasoning/cache 分布）。

### TC-TK-10 当前会话气泡汇报（正向）

- **前置**：本会话有 ≥1 条 token 记录。
- **步骤**：任务结束收到 `session.status == idle`。
- **预期**：气泡显示"本期用了 Xk input / Yk output / $ Z"；数字来自 opencode.db。

### TC-TK-11 当前会话气泡汇报（M3 补充验证项①）

- **前置**：M3 期间实测。
- **步骤**：验证 opencode `session` 表 `cost` / `tokens_*` 的写入时机（逐 message 写还是 session 结束聚合写）。
- **预期**：记录结论；若进行中数字滞后/为零，气泡仅在 `time_updated` 与 `session.status=idle` 时间差 < 阈值时显示，避免陈旧数字。

### TC-TK-12 无记录不出气泡（M3 补充验证项②）

- **前置**：正在跑的 session 在 session 表无记录（0 行）。
- **步骤**：该 session idle 时观察。
- **预期**：前端不弹 token 气泡（无记录则不出）；不显示 0/陈旧数字。

### TC-TK-13 schema 白名单检测（风险项）

- **前置**：构造一个缺少 `tokens_*` 列的旧 schema 副本（或模拟未来 opencode 升级改 schema）。
- **步骤**：启动 App 查 Token。
- **预期**：查询前 `PRAGMA table_info(session)` 字段白名单检测生效；字段缺失时给出"请升级 pulse-pet"类提示，不崩溃、不查错列。

---

## 四、TC-RM 提醒

### TC-RM-01 调度器整点语义

- **前置**：配置一条每 30 分钟一次的喝水提醒。
- **步骤**：观察 1 小时。
- **预期**：到点触发（Tauri event `reminder://trigger` → 前端渲染气泡）；间隔正确；未到点不触发。

### TC-RM-02 睡眠恢复不补发（C10）

- **前置**：提醒已启用；调度器已显式 `MissedTickBehavior::Skip`。
- **步骤**：让系统睡眠 10 分钟（跨过多个 tick）→ 唤醒。
- **预期**：唤醒后不瞬间连弹多次提醒；错过的不补发，等下一个正常 tick。

### TC-RM-03 气泡展示与自动消失

- **步骤**：触发一条气泡提醒。
- **预期**：宠物头顶出现气泡（默认文案如"该喝水啦 💧"）；8s 后自动消失。

### TC-RM-04 点击确认提前消失

- **步骤**：触发气泡 → 2s 时点击宠物。
- **预期**：气泡立即消失（视为"已确认"）；`reminder_logs` 记录 `acked_at` 时间、`dismissed_via='bubble'`。

### TC-RM-05 同规则 3 分钟不重复

- **步骤**：触发一条提醒 → 立即再次触发（模拟重复 tick / 手动触发）。
- **预期**：3 分钟内同一条不重复提醒；3 分钟后再触发正常。

### TC-RM-06 跨午夜窗口（C15）

- **前置**：规则 `start_time=22:00, end_time=06:00`（跨日窗口）。
- **步骤**：
  1. 21:59、22:00、23:59、00:00、05:59、06:00 分别观察；
  2. 配置规则 `start_time=09:00, end_time=18:00`（非跨日）对照。
- **预期**：跨日规则仅在 [22:00, 24:00) ∪ [00:00, 06:00) 内进入倒计时并触发；区间外不触发；非跨日规则不受影响。

### TC-RM-07 提醒规则 CRUD 与持久化

- **步骤**：panel 提醒页增/改/删规则，重启 App 后核对。
- **预期**：规则写入 `reminders` 表；重启后保留；删除后不再触发；修改后调度器 reload 生效（无需重启 App）。

### TC-RM-08 暂停所有提醒

- **步骤**：托盘"暂停所有提醒"开启 → 等到原本会触发的时刻。
- **预期**：任何提醒都不触发；取消暂停后恢复。

### TC-RM-09 烟花模式触发（可断言部分）

- **前置**：某规则勾选烟花模式（或全局开关开）。
- **步骤**：触发该提醒。
- **预期**：
  1. `fireworks` 窗口显示（全屏透明置顶、无边框、无任务栏项）；
  2. 3-5s 内窗口自动 `hide`；
  3. 无重复 show、无残留帧。
- **目视验收项**（不进自动回归）：发射点位于宠物位置；**绽放点位于宠物当前所处屏幕（显示器）的中轴线上、高度为屏幕从上往下 0.3 倍处（中间偏上）**（无论宠物在屏幕哪个位置，烟花都绽放于该点，多显示器取宠物所在屏）；粒子数 ~300-500、HSL 渐变 + 拖尾；60fps 流畅。

### TC-RM-10 烟花结束后可复用

- **步骤**：连续触发两次烟花提醒。
- **预期**：第一次播放完成 hide 后，第二次 show 可正常重新播放（不残留上一帧、不报错）。

### TC-RM-11 单条规则覆盖全局开关

- **前置**：全局烟花开关关，某条规则开烟花。
- **步骤**：触发该条与其它规则。
- **预期**：勾选规则放烟花；其它规则仅气泡（`use_fireworks` 单条覆盖生效）。

### TC-RM-12 烟花音频（可选）

- **前置**：M5 评估后若启用音频。
- **步骤**：开启音频 → 触发烟花。
- **预期**：播放"啾——砰"短音效（资源文件 `src-tauri/resources/fireworks.mp3`）；默认关闭时无声音。

### TC-RM-13 提醒日志与历史统计

- **步骤**：产生若干次提醒（部分点击确认、部分自动消失）。
- **预期**：`reminder_logs` 逐条记录（triggered_at / acked_at / dismissed_via）；喝水/休息历史次数聚合正确。

### TC-RM-14 自定义提醒文案

- **步骤**：新建 custom 规则并自定义文案 → 触发。
- **预期**：气泡显示自定义文案；文案同样经过净化规则（不自带原始命令/路径等）。

### TC-RM-15 提醒文案净化

- **步骤**：自定义文案含 `<script>` 或 markdown 链接或敏感字符 → 触发。
- **预期**：以纯文本渲染，无注入执行；不展示原始路径/URL/secret 样式 token（对应 v1 Done 标准第 7 条）。

### TC-RM-16 烟花窗口 Windows 兼容（风险项）

- **前置**：Windows 环境（M4 第二天验证）。
- **步骤**：触发烟花。
- **预期**：若 `maximized + transparent + alwaysOnTop` 组合渲染异常，按回退方案：fireworks 窗口不透明、背景接近桌面的深色 + 自适应 alpha 通道；至少保证烟花可见、不崩。

---

## 五、TC-SP 素材与精灵渲染

### TC-SP-01 占位精灵 5 状态

- **前置**：M1-M4 占位阶段（内置 1 张 PNG 128×128）。
- **步骤**：依次驱动 idle / thinking / working / success / error。
- **预期**：5 种状态均有对应画面；占位阶段每状态渲染单帧（单图 PNG，无多帧可切），状态切换时画面立即更换；rAF 循环按 60fps 维持动画时序；状态降级映射单独验证见 TC-SP-01b。
- **追加（M1 R4 用户意见 / M2 P2-7 定案）**：画布无任何文字渲染、无状态圆点（状态文字 M1 已移除；状态圆点 M2 移除）——状态只通过动画/画面表现，正式 UI 不显示调试徽标。

### TC-SP-01b 占位阶段状态降级映射

- **前置**：占位阶段（5 状态精灵）。
- **步骤**：逐一驱动全部 8 种归一化状态。
- **预期**：idle / thinking / working / success / error 直接渲染对应画面；`waiting-permission→thinking`、`testing→working`、`editing→working` 降级到最近同类渲染；全程无空白画面、无崩溃。

### TC-SP-02 canvas 缩放（C11）

- **步骤**：在 HiDPI（2×）与普通（1×）显示器分别查看宠物。
- **预期**：canvas 内部分辨率 = 220 × `window.devicePixelRatio`（2×→440），CSS 尺寸固定 220×220；帧图按 `min(canvasW/frameW, canvasH/frameH)` 居中绘制、保持比例不裁剪；宠物显示大小视觉一致、不模糊。

### TC-SP-03 dpr 变化重设

- **步骤**：把 pet 窗口（或系统显示设置）从 1× 拖到 2× 屏。
- **预期**：`window.matchMedia` 监听触发，画布尺寸重设，宠物不模糊、不拉伸。

### TC-SP-04 atlas 加载成功

- **前置**：存在标准 8×9 atlas（1536×1872，单帧 192×208）。
- **步骤**：启动 App（M5 后）或重启选择该宠物。
- **预期**：Rust 侧 `image` + `image-webp` 解码成功；RGBA 图块下发 webview；按帧时长表播放（idle 6 帧不规则眨眼、其余 uniform）；无前端解码。

### TC-SP-05 atlas 网格尺寸校验（C19）

- **前置**：准备一个非标准网格（如 8×10 或 16×9）的素材。
- **步骤**：选择该素材。
- **预期**：`pet.json` 的 cols/rows 与实际图块尺寸比对失败 → 加载器报错；控制面板提示"该素材网格尺寸非标准（如 8×9 / 8×11 之外）"；**不做按单帧强行裁剪**；回退到上一可用素材或内置占位。

### TC-SP-06 atlas 素材加载顺序

- **前置**：同一 pet id 同时存在于 用户配置 → 内置占位 → `~/.codex/pets/` → `~/.petdex/pets/`。
- **步骤**：按序检查实际加载来源。
- **预期**：加载顺序为用户配置的 pet → 内置占位 → `~/.codex/pets/` 扫描 → `~/.petdex/pets/` 扫描；找不到时逐级回退，最终必落到内置占位。

### TC-SP-07 8 状态 → 9 行完整映射（B17）

- **步骤**：M5 切 atlas 后逐一驱动 8 种归一化状态。
- **预期**：

| 归一化状态 | atlas 行 | 行为 |
|---|---|---|
| idle | 0 idle | 直映 |
| working | 7 running | 原地踏步式跑动 |
| thinking | 6 waiting | 待机/张望 |
| editing | 1 running-right | 向前推进 |
| testing | 2 running-left | 反向跑动 |
| waiting-permission | 8 review | 申请审批画面 |
| error | 5 failed | 直映 |
| success | 3 waving | 庆祝挥手 |

### TC-SP-08 二级庆祝预留行

- **步骤**：检查 jumping（第 4 行）驱动条件。
- **预期**：v1 中 jumping 无驱动事件（预留 todo 完成全清等二级庆祝），占位阶段和 atlas 阶段均不误触。

### TC-SP-09 素材缺失回退

- **前置**：`~/.codex/pets/<pet>` 目录存在但 pet.json 损坏 / spritesheet.webp 缺失。
- **步骤**：启动 App 选择该宠物。
- **预期**：加载失败 → 回退内置占位；控制面板有提示；App 不崩溃。

### TC-SP-10 webp 解码跨平台（风险项）

- **前置**：Windows CI 环境。
- **步骤**：验证编译链。
- **预期**：`image-webp` 在 Windows 上可编译（需 nasm）；若 CI 复杂度上升，按回退方案 atlas 直接要求 png 格式跳过 webp。

### TC-SP-11 选择宠物下拉（M5）

- **前置**：M5 实现后；`~/.codex/pets/` 与 `~/.petdex/pets/` 各有素材、内置占位可用。
- **步骤**：打开 panel → 设置 → "选择宠物"下拉。
- **预期**：
  1. 下拉列出：用户配置 pet → 内置占位 → `~/.codex/pets/` 扫描结果 → `~/.petdex/pets/` 扫描结果（与加载顺序一致，见 TC-SP-06）；
  2. 切换后宠物立即重新加载并热替换 webview 帧（无需重启 App）；
  3. 选中素材损坏/非标准网格时，下拉项旁有回退提示（回退到上一可用素材或内置占位，见 TC-SP-05）；
  4. 所有可选项均能被渲染，无空白宠物。

---

## 六、TC-WIN 窗口交互（M6）

### TC-WIN-01 拖拽

- **前置**：pet 窗口非穿透态（运行时默认，可交互）。
- **步骤**：鼠标按住宠物拖动。
- **预期**：窗口跟随移动（`window.startDrag()` 或 Rust 侧监听生效）；松开停止。

### TC-WIN-02 穿透态下不可拖拽

- **前置**：穿透开启（M6 后）。
- **步骤**：尝试拖动宠物。
- **预期**：鼠标事件全部透出，无法拖动（符合设计：穿透态下只能通过托盘/热键切回非穿透态再拖，不做"临时关穿透"路径）。

### TC-WIN-03 右键菜单可达性

- **前置**：非穿透态。
- **步骤**：右键宠物。
- **预期**：弹出右键菜单（PetMenu.tsx），含"设置/切换交互模式"等入口。

### TC-WIN-04 穿透态下右键菜单不可达但托盘可达

- **前置**：穿透开启。
- **步骤**：右键宠物 → 托盘右键。
- **预期**：宠物上右键无反应（事件透出）；托盘右键菜单仍正常（系统级菜单），"切换交互模式"可切回非穿透态。

### TC-WIN-05 切换交互模式双通道

- **步骤**：分别通过全局热键与托盘菜单切换穿透。
- **预期**：两条通道都能切换且状态同步（穿透开 = 纯展示；关 = 可拖拽/右键）。

### TC-WIN-06 宠物窗口配置核对

- **步骤**：对照 tauri.conf.json 检查三窗口。
- **预期**：pet（220×220、transparent、decorations:false、alwaysOnTop、skipTaskbar、resizable:false、visible:true、shadow:false、url `#/pet`；`ignoreCursorEvents` 非配置字段、运行时默认 false 非穿透）；panel（900×640、visible:false、url `#/panel`）；fireworks（transparent、decorations:false、alwaysOnTop、skipTaskbar、visible:false、shadow:false、maximized:true、url `#/fireworks`）。

### TC-WIN-07 调试烟花热键

- **步骤**：按 `⌘+Shift+Alt+F`（Mac）/ `Ctrl+Shift+Alt+F`（Win）。
- **预期**：手动放一束烟花；v1 release 构建中该热键已移除。

---

## 七、TC-TD Todo 插件

### TC-TD-01 插件清单与注册

- **前置**：M7 实现后。
- **步骤**：检查 `~/.pulsepet/plugins/todo/plugin.json` 与 `plugins` 表。
- **预期**：manifest 含 id / name / version / manifestVersion:1 / permissions（`schedule, notify, ui:panel-tab, todo:*`）/ configSchema / panelTab（"Todo"、check-square 图标）；控制面板出现 Todo tab。

### TC-TD-02 todo CRUD

- **步骤**：panel Todo 页新建/编辑/删除任务。
- **追加步骤**：
  1. 建立带 2 个 tag 的 todo → 删除其中 1 个 tag；
  2. 调整若干 todo 的 `sort_order`（拖拽或表单）；
  3. 核查列表顺序。
- **预期**：`todos` 表正确读写；字段含 title/notes/priority(0-3)/due_date/remind_before_minutes/completed_at/sort_order/created_at/updated_at；tag 增删即时反映到 `todo_tags`（删除 todo 时级联删除）；列表按 `sort_order` 排序显示，修改后顺序立即更新；UI 与库一致。

### TC-TD-03 到点提前提醒（B16 定案通道）

- **前置**：新建任务，`due_date` 带时间、`remind_before_minutes=5`。
- **步骤**：等待到截止前 5 分钟。
- **预期**：宠物气泡显示"还有 X 分钟要完成「任务名」"；提醒经由 `reminders` 表 `kind='todo'` 派生行触发（todo 写入/修改时 Rust 侧同步 upsert，`interval_minutes=0`、`start_time = due_date - remind_before_minutes`、`source_todo_id` 反向引用），调度器统一消费，不另查 todos 表。

### TC-TD-04 todo 完成联动

- **步骤**：完成一个任务。
- **预期**：宠物播放 waving 动画 + 气泡"干得漂亮 🎉"；`completed_at` 写入；派生 reminder 级联删除/不再触发。

### TC-TD-05 今日全清庆祝

- **步骤**：完成今日全部任务（最后一个完成时）。
- **预期**："今日"按用户本地时区自然日（00:00 起）统计 `completed_at`（DESIGN §8.3 定案）；完成今日全部任务时气泡显示今日完成数（如"今日完成 N 项"）；可触发二级庆祝（jumping 预留位，v1 不做强制）。

### TC-TD-06 非周期提醒只触发一次

- **前置**：todo 派生提醒触发过。
- **步骤**：等待超过其预定时间继续观察。
- **预期**：`kind='todo'` 仅触发一次（非周期）；调度器根据 `reminders.last_triggered_at` 与当前时间判断不再重发（**唯一防重来源**，DESIGN §5.4 定案）；`todos.remind_last_triggered_at` 保留字段 v1 不写入不读取，不作为防重依据。

### TC-TD-07 删除/完成级联清理

- **步骤**：删除一个带派生提醒的 todo；再新建一个完成它。
- **预期**：两种情况下对应 `reminders` 行均被级联删除；`reminder_logs` 历史保留（ON DELETE CASCADE 仅作用于 reminders 行）。

### TC-TD-08 remind_before_minutes=0

- **步骤**：新建任务 `remind_before_minutes=0`，`due_date` 带时间；等待到点。
- **预期**：`0 = 不派生 reminder`——`reminders` 表中**不出现**该 todo 的 `kind='todo'` 行（完全无提醒，不提前也不到点）；随后若修改 `due_date` 且 `remind_before_minutes>0`，才 upsert 派生行（语义与 DESIGN §5.4 一致）。

### TC-TD-09 权限面声明（无运行时复检）

- **步骤**：代码审查。
- **预期**：v1 权限面仅声明（manifest 内），无运行时复检逻辑；v1 无沙箱、所有插件皆内置（第三方安装入口不存在）。

---

## 八、TC-SEC 安全与隐私

### TC-SEC-01 消息净化端到端（v1 Done 标准第 7 条）

- **前置**：真实任务环境（含路径/URL/代码/secret 的报错与输出）。
- **步骤**：跑任务 → 观察所有气泡与宠物文案。
- **预期**：气泡不出现任何原始路径/URL/代码片段/secret 样式 token（对 DESIGN-REVIEW B7/C13 与 §3.1 净化的回溯验证）。

### TC-SEC-02 自忽略端到端（v1 Done 标准第 8 条）

- **步骤**：agent 主动调用 pulsepet 自身工具（或模拟回环场景）跑 10 分钟。
- **预期**：插件不会被自身工具回环（无循环 POST、无状态抖动）。

### TC-SEC-03 本地 HTTP 安全边界

- **步骤**：
  1. 从本机其它端口/进程访问 127.0.0.1:47811；
  2. 从外网/局域网地址尝试访问。
- **预期**：仅绑定 127.0.0.1（不暴露局域网）；无 token 全部 401；服务不响应局域网请求。

### TC-SEC-04 token 文件权限（POSIX）

- **步骤**：`ls -la ~/.pulsepet/runtime/update-token`。
- **预期**：mode 0600，owner 为当前用户。

### TC-SEC-05 Windows token 保护说明

- **步骤**：Windows 端核对运行时目录位置。
- **预期**：token 文件位于 `%LOCALAPPDATA%\pulsepet\runtime\`（DESIGN §3.1 定案）；文档已知 mode 0600 无效（无 POSIX 语义），依靠单用户登录 + ACL 默认仅本用户可见（v1 不实装 ACL 强化，无测试失败项，仅核对位置正确）。

### TC-SEC-06 隐私：事件不明文落盘

- **步骤**：全流程结束后检查 `~/.pulsepet/runtime/` 与插件侧。
- **预期**：事件仅经内存 HTTP 传递，无事件明文文件落盘（对比 PawPause JSONL 方案的差异点成立）。

---

## 九、TC-CI 打包与 CI

### TC-CI-01 macOS 打包

- **步骤**：`npm run tauri build`。
- **预期**：产出 `.app` + `.dmg`；包体积目标 ~10-20MB。

### TC-CI-02 CI 触发与产物（C12）

- **前置**：`.github/workflows/build.yml` 已修改为同时匹配 `todo-lite-v*` 与 `pulse-pet-v*`。
- **步骤**：push tag `pulse-pet-v0.1.0`。
- **预期**：矩阵（windows-latest + macos-latest）触发构建；据 tag 前缀切换工作目录 `pulse-pet/` 与产物命名 `PulsePet-<version>-<os>`；产物挂到 draft Release；todo-lite 既有触发不受影响。

### TC-CI-03 插件独立分发

- **步骤**：直接下载插件 zip（不经 Tauri app）→ 运行 install.sh/install.ps1。
- **预期**：无 Tauri app 也能安装尝试（未启动 App 时静默、启动后恢复，符合 TC-EV-07）。

### TC-CI-04 素材不入主包

- **步骤**：检查构建产物。
- **预期**：atlas 素材包不在主包内（用户从 petdex/awesome-codex-pet 自取）。

---

## 十、TC-DONE v1 Done 标准综合验收

> 以下逐条对应 DESIGN.md §11 的 v1 Done 标准。

### TC-DONE-01 M1-M6 核心链路全可用

- **步骤**：按 TC-APP / TC-EV / TC-TK / TC-RM / TC-SP / TC-WIN 全量回归。
- **预期**：核心链路（事件→状态→动画）、提醒、烟花、atlas、渲染交互全部可用。

### TC-DONE-02 M7 插件机制 + todo MVP

- **步骤**：按 TC-TD 全量回归。
- **预期**：插件机制骨架 + todo MVP 可用。

### TC-DONE-03 跨平台

- **步骤**：macOS 全流程自测 + Windows 主流分辨率下跑通。
- **预期**：macOS 通过；Windows 能跑（边缘行为已知限制记入 README）。

### TC-DONE-04 无人值守 30 分钟一致性

- **步骤**：安装插件后无人值守跑 30 分钟真实任务。
- **预期**：宠物状态变化与实际 agent 状态吻合（对应 TC-EV-22）。

### TC-DONE-05 Token 对账

- **步骤**：UI 数字 vs 直接查 opencode.db。
- **预期**：一致，误差 ≤0.01 USD（对应 TC-TK-06）。

### TC-DONE-06 提醒双形态验证

- **步骤**：触发一次气泡提醒 + 一次烟花提醒。
- **预期**：两次都按预期渲染与消失（气泡 8s 自动消失；烟花 3-5s 消散 hide）。

### TC-DONE-07 持久化保留

- **步骤**：控制面板关闭 → 重启 App → 核对。
- **预期**：设置 / 位置 / 历史提醒日志保留（对应 TC-APP-12 / TC-RM-13）。

### TC-DONE-08 消息净化

- **步骤**：TC-SEC-01 通过。
- **预期**：气泡不出现任何原始路径/URL/代码片段。

### TC-DONE-09 自忽略

- **步骤**：TC-SEC-02 通过。
- **预期**：插件不会被自身工具回环。

---

## 附：评审项 → 测试用例对照表

| 评审项（DESIGN-REVIEW.md） | 用例 |
|---|---|
| A1 穿透默认值自相矛盾 | TC-APP-07 / TC-WIN-05（实现按"默认非穿透"执行） |
| A2 右键菜单与穿透冲突 | TC-WIN-04 |
| A3 DB 命名不统一 | TC-APP-13（统一为 `pulsepet.db`） |
| B4 状态机缺少复位 | TC-EV-05 / TC-EV-06 |
| B5 30s 回收条件 | TC-EV-17（无 /health 分支参与回收） |
| B6 App 退出时插件行为 | TC-EV-07 |
| B7 token 汇报时序 | TC-TK-11 |
| B8 无记录不出气泡 | TC-TK-12 |
| C9 NO_MUTEX 跨线程 | TC-TK-05（每次查询新建只读连接） |
| C10 睡眠恢复 Burst | TC-RM-02 |
| C11 canvas 缩放 | TC-SP-02 / TC-SP-03 |
| C12 CI 共享文件 | TC-CI-02 |
| C13 Windows mode 0600 | TC-SEC-05 |
| C14 AgentAdapter 职责分裂 | TC-EV-23（接口存在 + 新增 adapter 不改主链路；DESIGN §3.4 已承认此边界） |
| C15 跨午夜窗口 | TC-RM-06 |
| B16 todo→调度器通道 | TC-TD-03 |
| B17 atlas 映射表 | TC-SP-07 |
| C18 托盘左键 | TC-APP-03（左键作用于 pet 主窗口） |
| C19 网格尺寸 | TC-SP-05 |
