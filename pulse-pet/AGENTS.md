# PulsePet 项目级指令（AGENTS.md）

> 本文件是给在 `pulse-pet/` 目录内工作的 agent 的引导；仓库根指令见 `lab/AGENTS.md`。

## 这是什么

PulsePet 是一个桌面宠物 App（Tauri 2 + React + TS + Vite），监听 coding agent（opencode / Claude Code）状态并用像素小猫动画呈现。v1 仅 opencode；v2 起多 agent 注册表收敛（见下「新增 agent」条），接入新 agent 见 `docs/v2/agent-onboarding.md`。

## 文档地图（2026-08-22 起按版本归档于 `docs/`）

- `docs/v1/`——**0.1.x 发版线**文档：`DESIGN.md`（技术方案）、`TEST-CASES.md`（验收用例）、`DECISIONS.md`（v1 范围决策）、`V1-OPEN-ITEMS.md`（v1 遗留清单，**§八 = v0.1.3 维护版计划**）、`DESIGN-REVIEW.md` / `TEST-CASES-REVIEW.md`（历史评审，留档原貌）、`desktop-pet-research.md`（调研）。0.1.x 线的维护性文档修订（如 v0.1.3 改 TEST-CASES 措辞）仍落此处。
- `docs/v2/`——**v2** 范围与设计：`V2-SCOPE.md`（范围决策）、`V2-DESIGN.md`（M1~M6 方案设计与评审记录）、`V2-TEST-CASES.md`（v2 验收用例）、`V2-OPEN-ITEMS.md`（v2 运行时问题 / 反馈批次 / 追加特性，§一~§二十五）、`agent-registry.md`（多 agent 注册表设计与实施记录）、`agent-onboarding.md`（新 agent 接入操作手册）、`pet-size.md`（宠物大小档位与归一化）、`routine-exec.md`（例程 exec 批次：执行历史快照化 + 多 agent 例程模板注册表 + 执行上下文增补——快照字段 = 任务名/命令/工作目录，Part A/B/C 均 2026-08-30 实施）；后续新文档落此目录，**不回改 docs/v1/ 文档**。
- 正文中的 `DESIGN §x` / `TEST-CASES §x` 等纯文字引用指 `docs/v1/` 下同名文件；`V2-DESIGN §x` / `V2-TEST-CASES §x` / `V2-SCOPE §x` 指 `docs/v2/` 下同名文件。

## 本目录技术栈与命令

- **前端**：React 19 + TypeScript + Vite + Zustand。`npm run dev`（Vite，端口 1430）、`npm run build`（tsc + vite build）、`npm test`（vitest）。
- **桌面壳**：Tauri 2（Rust）。`npm run tauri dev` / `npm run tauri build`。
- **本地存储**：SQLite，`rusqlite`（bundled）直连，数据库文件 `pulsepet.db` 位于 `app_config_dir()`（macOS 下 `~/Library/Application Support/com.pulsepet.app/`）；前端一律经 Tauri invoke 走 Rust 侧 rusqlite（未引入 tauri-plugin-sql）。
- **无统一工具链**：不要假设与仓库内其它项目（如 todo-lite）共享构建脚本；先看本目录 `package.json` / `Cargo.toml`。
- **cargo 网络**：本机到 crates.io 的 HTTP/2 多路复用会 stall（`transfer too slow`），下载依赖时用 `CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false cargo fetch`。

## 关键约定

- **三窗口 label**：`pet`（透明置顶无边框，尺寸档位 184/220/280 逻辑像素、缺省 220——见下「宠物大小档位」）、`panel`（900×650 默认隐藏）、`fireworks`（透明全屏置顶隐藏）。前端按 hash 路由：`#/pet`、`#/panel`、`#/fireworks`。
- **托盘左键**：切换 pet 可见性；`TrayIconEvent::Click` Down/Up 各触发一次，必须判断 `button_state`（只处理 `MouseButtonState::Down`），否则一次单击连切两次。
- **状态映射**：归一化 8 态（`src/lib/state.ts`：idle/thinking/working/editing/testing/waiting-permission/success/error）；atlas 路径用完整 9 行姿态映射（waiting-permission→review 行等，v1 M5 起），仅占位 PNG 兜底路径走 DEGRADE 降级到 5 画面（waiting-permission→thinking、testing/editing→working）。
- **迁移幂等**：`PRAGMA user_version` 控制，每步迁移（SQL + 版本提升）包在同一事务内（M8 A1：半途失败/崩溃自动回滚，重启可整步重跑）；新增表需在 `db.rs` 的 `MIGRATIONS` 表追加文件并 bump `SCHEMA_VERSION`（编译期断言校验 `MIGRATIONS` 末位版本 == `SCHEMA_VERSION`，只改一处即编译报错）。
- **位置记忆**：`app_state` 表 `pet.position.x` / `pet.position.y`；`Moved` 事件持续保存、退出时兜底保存、启动时恢复。
- **宠物大小档位（docs/v2/pet-size.md）**：`app_state` 键 `pet.size`（small=184 / medium=220 / large=280 逻辑像素，缺省 medium）；Rust 权威（`pet_size.rs`，照 theme 模式）+ `pet://size` 广播，前端 `PET_SIZES`（size-bridge.ts）与 Rust `logical_of` **锁步**；启动时序铁律 **set_size → restore → show**（order_nails 钉子）；归一化常开（`pet-scale.ts`：idle 行逐帧原点并集锚定"内置猫现状"，**帧尺寸**做防裁剪上限——勿改回全表包围盒，奔跑行动画会使其失效；atlas 模式 nearest 插值）。
- **窗口创建时序（issue #9）**：`tauri.conf.json` 三窗口必须保持 `"create": false`，由 `lib.rs` setup 闭包在**全部 managed state 就绪后**经 `WebviewWindowBuilder::from_config` 创建——config 窗口默认在用户 setup 闭包之前创建，Windows 上 WebView2 异步初始化期间前端 invoke 的 IPC 会早于 `manage` 被派发，命令内 `state()` panic 且在 WndProc 内 abort 闪退（v0.1.0/0.1.1 Windows 闪退根因，DESIGN §7.1）。新增窗口照此模式；新增 managed state 必须在窗口创建循环之前 manage。pet 窗口 config 另保持 `"visible": false`，`restore_pet_position` 之后无条件 `show()`（issue #20 R5——防 Windows 启动左上角闪现）。
- **运行日志（DESIGN §7.5）**：一律用 `plog!`（`use crate::plog;`；lib.rs 为 crate 根免 import），**不要新增 `eprintln!`**——Windows release GUI 子系统下 eprintln 完全静默，plog! 落文件（`~/.pulsepet/pulsepet.log` / Windows `%LOCALAPPDATA%\pulsepet\pulsepet.log`，超 1MB 轮转 `.old` 一代）+ stderr 双写。setup 关键步骤与退出（`exit` 行）有标记；panic 由 `logging::init()` 装的 hook 落文件。排障口径：日志末行 = 死前最后完成步骤；有 exit 行 = 干净退出。
- **i18n（M8）**：zh/en 双语，自研轻量字典（`src/lib/i18n.ts` 的 `t(key, params)`，无第三方依赖）；语言持久化在 `app_state` 键 `ui.language`（Rust `i18n.rs` 持有全局语言位 + `ui_set_language` 命令：持久化 + 托盘菜单重建 + panel 标题 + `ui://language` 三窗口广播）。**文案 key 约定**：扁平键点分命名空间（`panel.*` / `reminders.*` / `todo.*` / `settings.*` / `menu.*` / `token.*`），en 与 zh 键集合必须一致（有字典完备性测试防漏译）；不翻译宠物状态名（idle/working…）与品牌名 PulsePet；纯函数文案接口带可选 `lang` 参数（缺省读当前 store，vitest 默认 zh 保证旧断言稳定）。Rust 侧托盘/标题/token 气泡/atlas 回退提示文案统一走 `i18n::current()`（zh 与既有 spec 钉住措辞逐字一致）。品牌名显示层规范大小写 `OpenCode` / `Claude Code`（V2-OPEN-ITEMS §21），技术字面量（wire id / CLI 命令 / 文件名）豁免不改。
- **面板与 tab 注册表（v2 M2）**：设计系统「像素暖纸 / 像素冷炭」+ 主题三档（浅/深/跟随系统，`theme.rs` + `app_state` 键 `ui.theme`，仅面板生效——气泡与右键菜单不随主题变）；tab 由注册表驱动（`src/panel/registry.ts`：核心三 tab Token / 例程 / 设置 不可关，插件 tab 按 `plugins` 表 `enabled` 动态生成）；功能管理停用插件 = 隐藏 tab + 停派生提醒 + 数据保留。
- **例程（v2 M4，面板「例程」页）**：提醒与定时任务合并为一张列表（动作徽标 🔔 notify / ⚡ exec / 📋 todo 派生）；`reminders` 表迁移 003（`action_type` + `action_params` JSON + `schedule_kind` interval/daily/weekly/once）；exec 由 `action_exec.rs` spawn 命令，以 `task` **伪 agent** 驱动宠物状态（HTTP agent id 不得为 `"task"` 的根源）；daily/once 睡醒补跑宽限窗 15 分钟（`CATCHUP_WINDOW_MS`）；提醒气泡「稍后 10 分钟」snooze；托盘全局暂停期间 notify 不触发不补弹、exec 不跑不补（记 skipped）。
- **气泡（v2 M2/M6）**：排队模型（`bubble-queue.ts`——优先级抢占 + 同源 dwell 合并 + 并发上限）；agent 来源气泡带短名徽标 `[oc]`/`[cc]`/`[task]`（`shortOf` 查表；**合并键不含 agent**，同源合并时徽标以幸存新条目为准）；工具级气泡走 `/state` `detail` 字段（`"tplId:param"` 白名单模板 + basename/命令首词净化，TC-SEC 口径），App 侧按开关过滤、插件照发。
- **抢镜（v2 M6）**：多 agent × 多 session 的显示状态 = **最近活跃优先**叠加原优先级合并（`session_state.rs` `display()`）；例程（task）会话让位于手头 agent 会话。
- **token 口径（v2 §14 起，V2-OPEN-ITEMS §十四）**：day/week/range/today 四类聚合按**消息产生时间**归天（opencode message 表 `time_created` / CC 行 timestamp → `CcSessionRow.by_day`）——跨天会话每天各得各的；by-session 视图与「本次会话」气泡仍为会话累计；KPI 总量 = input+output+cacheRead（reasoning 不计任何汇总）；CC cost 恒 0（列显「—」）；opencode 旧库无 message 表 → `schema-mismatch` 严格报错。

## 与仓库其它项目的边界

- **独立目录、自包含**：PulsePet 不依赖 todo-lite 或其它 App，也不复用它们的存储/代码；SQLite 数据完全独立。
- **不耦合 todo-lite**：todo 功能是 PulsePet 内置的轻量插件（`plugins` 表 + 内置 `todo` 插件，M7 起落地、v2 起可经功能管理停用），不读 todo-lite 的 SQLite（见 DECISIONS §3.4）。
- **不读 opencode 原生 todo 表**：opencode 的 `todo` 表语义是"会话内子任务"，与用户日常待办无关。
- **事件来源**：双 agent 经同一本地 HTTP（127.0.0.1 + token）上报——opencode 常驻插件（运行在 opencode 自带 Bun）+ Claude Code hooks（每事件 spawn `claude-code-hook.js`，stdin JSON）；session 状态机按 `(agent, sessionId)` 复合键。两家接入的安装/卸载/doctor 在设置页「接入管理」（Rust 内置安装器，managed 标记 + 幂等 + 写前备份）。
- **git 约定**：默认分支 `develop`，除非明确要求否则不 commit/push；push 用 SSH。
- **新增 agent（v2 registry）**：agent 注册的事实源是两端注册表——Rust `src-tauri/src/agents.rs` 的 `AGENTS` 表 + 前端 `src/lib/agents.ts` 的 `AGENTS` 表（include_str! 测试互钉 id/short 一致）；**接入操作手册见 `docs/v2/agent-onboarding.md`**（双链清单 + checklist，v0.2.3 基线；两端各一行注册 + hook 脚本三件套 + i18n 键 + 接 codex 时 7 处既有拒绝钉翻转，勿再散落 if/switch/三元分支），设计依据与实施记录见 `docs/v2/agent-registry.md`。

## 里程碑速览

**v1（DESIGN §10，0.1.x 线）**：M1 骨架 ✅ → M2 事件链路 ✅ → M3 token 统计 ✅ → M4 提醒/烟花 ✅ → M5 atlas 加载 ✅ → M6 拖拽/穿透/热键/右键菜单 ✅ → M7 todo 插件 ✅ → M8 收尾 ✅。后移：TC-DONE-01~09 综合验收与多屏实机（日常使用顺带核对）；心跳 / `/health` 限流豁免已裁定不做（V1-OPEN-ITEMS §五）。

**v2（V2-SCOPE/V2-DESIGN，2026-08 完成）**：M1 Claude Code 事件接入 + 接入管理 ✅ → M2 前端 UI 基础（设计系统 / 主题 / tab 注册表 / 气泡排队）✅ → M3 Token 看板增强 + 工具级气泡 ✅ → M4 例程（动作泛化 notify/exec）✅ → M5 Token by agent（CC transcript）✅ → M6 多 agent 抢镜 ✅；收尾批次见 V2-OPEN-ITEMS §十一~§二十一（宠物大小三档 / 反馈批次 F1~F16 / token 跨天归天 / Windows 图标 tile / 统计源状态行 / 品牌名统一等，均已实施）。后移：多屏与 Windows 剩余实机批次（V2-OPEN-ITEMS §六）、第三 agent 接入（codex，手册 `docs/v2/agent-onboarding.md`）。
