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

# 开发模式（三窗口 + 托盘）
npm run tauri dev

# 前端单测（纯逻辑：状态降级映射 / canvas 缩放）
npm test

# 生产构建（.app / .dmg）
npm run tauri build
```

> 首次 `cargo` 编译会从零构建 tauri 依赖（约数百 crate），耗时较长；若在受限网络下 `cargo` 下载 stall，可尝试 `CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false cargo fetch`（禁用 HTTP/2 多路复用）。

## 目录结构（M1 子集）

```
pulse-pet/
├── src/                      # 前端 React
│   ├── pet/                  # 宠物 webview
│   │   ├── PetCanvas.tsx     # canvas 精灵渲染（占位 5 状态 + 眨眼 + 状态徽章）
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
