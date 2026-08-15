# PulsePet

桌面宠物 App：监听 opencode agent 工作状态，用一只像素小猫实时呈现（idle / thinking / working / success / error），并规划 token 本地统计、喝水/休息提醒（气泡 + 烟花）、轻量 todo 插件。

> POC 阶段，效果验证通过后可能拆仓独立演进。设计与范围见 [DESIGN.md](./DESIGN.md)、[DECISIONS.md](./DECISIONS.md)，验收依据见 [TEST-CASES.md](./TEST-CASES.md)。

## 技术栈

| 层 | 选型 |
|---|---|
| 桌面壳 | Tauri 2.x (Rust) |
| 前端 | React 19 + TypeScript + Vite |
| 状态管理 | Zustand |
| 本地存储 | SQLite（`rusqlite` 直连，`pulsepet.db`） |
| 系统集成 | 托盘（TrayIcon）、单实例锁（tauri-plugin-single-instance） |

## 如何运行

```bash
# 安装依赖
npm install

# 开发模式（三窗口 + 托盘，每次启动加载最新代码）
npm run tauri dev

# 前端单测（纯逻辑：状态降级映射 / canvas 缩放）
npm test

# 生产构建（.app / .dmg）
npm run tauri build
```

> 首次 `cargo` 编译会从零构建 tauri 依赖（约数百 crate），耗时较长；若在受限网络下 `cargo` 下载 stall，可尝试 `CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false cargo fetch`（禁用 HTTP/2 多路复用）。

### 如何运行最新版

`npm run tauri build` 每次都会把最新产物覆盖写入同一路径（无需复制到 /Applications）：

```
src-tauri/target/release/bundle/macos/pulse-pet.app
src-tauri/target/release/bundle/dmg/pulse-pet_<version>_aarch64.dmg
```

- **推荐**：构建后直接 `open src-tauri/target/release/bundle/macos/pulse-pet.app` —— 始终是最新版。
- **注意**：若你曾把旧版 `.app` 复制到 `/Applications`（或 `~/Applications`），Launchpad / Finder 里的入口指向那份**副本**，不会随重新构建自动更新；需重新复制覆盖，或直接改用上面的 target 路径。
- 开发热更新用 `npm run tauri dev`。
- 确认是否最新：重新 `npm run tauri build` 后 `open` 一次 target 路径的 `.app` 即可。

## 运行时视觉验证（供复验）

pet 是 macOS 透明合成窗口（`transparent` + `macOSPrivateApi` + `backgroundColor`）。**无头/后台自动化环境**可能因 WebKit 渲染进程被系统挂起（App Nap / 无前台激活）而得到"内容不渲染"的假阴性。可信验证步骤：

1. **在真实 GUI 会话启动**（`open <target 路径 .app>` 或 `npm run tauri dev`），避免 SSH/launchd 无头启动，等待 app 前台激活。
2. **用全屏截屏** `screencapture -x`（走 WindowServer 合成结果，包含透明窗口内容）；**不要用** `screencapture -l <windowID>`（单窗口离屏捕获对 WKWebView 跨进程合成内容不可靠，会得到全透明假象）。
3. **量化指标**（对 pet 窗口区域逐像素分析）：
   - 内容：猫毛白 `#f4f4f7` 像素数 > 0（约 5 万+）、`bright(>200)` 像素 > 0；
   - 透明：窗口边缘内外像素连续性（avg/median 色差 ≈ 0，无窗口框）。
4. **前置自检**：确认 WebContent 进程 CPU > 0（rAF 60fps 在跑）；AX 树里 `AXWebArea` 有 `AXChildren`（含 canvas）。若两者为 0，说明渲染进程被挂起，该次测量无效，换真实 GUI 会话重测。
5. 最终以**人工目验**为准（用户实测：宠物可见 + 周围透明）。

## 目录结构（M1 子集）

```
pulse-pet/
├── src/                      # 前端 React
│   ├── pet/                  # 宠物 webview
│   │   ├── PetCanvas.tsx     # canvas 精灵渲染（占位 5 状态 + 眨眼 + 状态圆点，无文字）
│   │   └── petStore.ts       # zustand：当前 raw/sprite 状态
│   ├── panel/Panel.tsx       # 控制面板 webview（M1 占位）
│   ├── fireworks/Fireworks.tsx # 烟花 webview（M1 占位）
│   ├── lib/
│   │   ├── state.ts          # 归一化状态类型 + 8→5 降级映射
│   │   └── scaling.ts        # canvas HiDPI 缩放策略
│   └── styles/global.css
├── src-tauri/
│   ├── src/
│   │   ├── main.rs / lib.rs
│   │   ├── db.rs             # SQLite 迁移（幂等）+ app_state 读写
│   │   ├── windows.rs        # pet/panel/fireworks 窗口管理 + 位置保存/恢复
│   │   └── tray.rs           # 托盘（左键切换 / 右键菜单）
│   ├── migrations/001-init.sql # 基础表 schema
│   ├── capabilities/
│   └── Cargo.toml
├── public/placeholder-cat.png # 128×128 占位精灵（自绘 CC0）
├── scripts/gen-assets.mjs    # 生成占位精灵 + 图标源
├── DESIGN.md / TEST-CASES.md / DECISIONS.md
└── README.md
```

## M1 范围与后续

- **M1（当前）**：三窗口骨架、占位精灵 5 状态渲染、托盘 + 单实例锁、SQLite 迁移（6 表）、位置记忆。
- **未实现**：HTTP server / opencode 插件（M2）、token 统计（M3）、提醒与烟花逻辑（M4）、atlas 加载（M5）、拖拽/穿透/热键/右键菜单（M6）、todo 插件机制（M7）。

详见 [DESIGN.md §10](./DESIGN.md) 实施里程碑。
