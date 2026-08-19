# PulsePet 项目级指令（AGENTS.md）

> 本文件是给在 `pulse-pet/` 目录内工作的 agent 的引导；仓库根指令见 `lab/AGENTS.md`。

## 这是什么

PulsePet 是一个桌面宠物 App（Tauri 2 + React + TS + Vite），监听 opencode agent 状态并用像素小猫动画呈现。v1 仅支持 opencode，架构上预留多 agent 扩展。

## 本目录技术栈与命令

- **前端**：React 19 + TypeScript + Vite + Zustand。`npm run dev`（Vite，端口 1430）、`npm run build`（tsc + vite build）、`npm test`（vitest）。
- **桌面壳**：Tauri 2（Rust）。`npm run tauri dev` / `npm run tauri build`。
- **本地存储**：SQLite，`rusqlite`（bundled）直连，数据库文件 `pulsepet.db` 位于 `app_config_dir()`（macOS 下 `~/Library/Application Support/com.pulsepet.app/`）。M4/M7 接入 `tauri-plugin-sql` 时复用同一路径（`sqlite:pulsepet.db`）。
- **无统一工具链**：不要假设与仓库内其它项目（如 todo-lite）共享构建脚本；先看本目录 `package.json` / `Cargo.toml`。
- **cargo 网络**：本机到 crates.io 的 HTTP/2 多路复用会 stall（`transfer too slow`），下载依赖时用 `CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false cargo fetch`。

## 关键约定

- **三窗口 label**：`pet`（透明 220×220 置顶无边框）、`panel`（900×640 默认隐藏）、`fireworks`（透明全屏置顶隐藏）。前端按 hash 路由：`#/pet`、`#/panel`、`#/fireworks`。
- **托盘左键**：切换 pet 可见性；`TrayIconEvent::Click` Down/Up 各触发一次，必须判断 `button_state`（只处理 `MouseButtonState::Down`），否则一次单击连切两次。
- **状态降级**：占位阶段只有 5 张画面（idle/thinking/working/success/error），8 种归一化状态按 `src/lib/state.ts` 的映射降级（waiting-permission→thinking、testing→working、editing→working）。M5 切 atlas 后改用完整 9 行映射。
- **迁移幂等**：`PRAGMA user_version` 控制，每步迁移（SQL + 版本提升）包在同一事务内（M8 A1：半途失败/崩溃自动回滚，重启可整步重跑）；新增表需在 `db.rs` 的 `MIGRATIONS` 表追加文件并 bump `SCHEMA_VERSION`（编译期断言防只改一处）。
- **位置记忆**：`app_state` 表 `pet.position.x` / `pet.position.y`；`Moved` 事件持续保存、退出时兜底保存、启动时恢复。
- **i18n（M8）**：zh/en 双语，自研轻量字典（`src/lib/i18n.ts` 的 `t(key, params)`，无第三方依赖）；语言持久化在 `app_state` 键 `ui.language`（Rust `i18n.rs` 持有全局语言位 + `ui_set_language` 命令：持久化 + 托盘菜单重建 + panel 标题 + `ui://language` 三窗口广播）。**文案 key 约定**：扁平键点分命名空间（`panel.*` / `reminders.*` / `todo.*` / `settings.*` / `menu.*` / `token.*`），en 与 zh 键集合必须一致（有字典完备性测试防漏译）；不翻译宠物状态名（idle/working…）与品牌名 PulsePet；纯函数文案接口带可选 `lang` 参数（缺省读当前 store，vitest 默认 zh 保证旧断言稳定）。Rust 侧托盘/标题/token 气泡/atlas 回退提示文案统一走 `i18n::current()`（zh 与既有 spec 钉住措辞逐字一致）。

## 与仓库其它项目的边界

- **独立目录、自包含**：PulsePet 不依赖 todo-lite 或其它 App，也不复用它们的存储/代码；SQLite 数据完全独立。
- **不耦合 todo-lite**：todo 功能未来是 PulsePet 内置的轻量插件（`plugins` 表 + 内置 `todo` 插件），不读 todo-lite 的 SQLite（见 DECISIONS §3.4）。
- **不读 opencode 原生 todo 表**：opencode 的 `todo` 表语义是"会话内子任务"，与用户日常待办无关。
- **事件来源**：M2 起由 opencode 插件经本地 HTTP（127.0.0.1 + token）上报；M1 阶段状态由前端 store 手动驱动（点击宠物循环切换）。
- **git 约定**：默认分支 `develop`，除非明确要求否则不 commit/push；push 用 SSH。

## 里程碑速览（DESIGN §10）

M1 骨架 ✅ → M2 事件链路 ✅ → M3 token 统计 ✅ → M4 提醒/烟花 ✅ → M5 atlas 加载 ✅ → M6 拖拽/穿透/热键/右键菜单 ✅ → M7 todo 插件 ✅ → M8 收尾（i18n / Windows CI 级兼容 / capability 收敛 + TC-SEC 回溯 / README+AGENTS / 遗留 A1~A9 清偿）✅。后移：多屏与 Windows 实机验证（具备硬件时）、心跳与 /health 豁免（v2）、TC-DONE-01~09（v1 Done 验收任务）。
