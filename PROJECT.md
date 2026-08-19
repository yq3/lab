# Lab Projects

本仓库中各实验项目的概述索引。每个项目在根目录下独立成目录，自包含、可独立运行。

## 项目列表

### [todo-lite](./todo-lite)
轻量级桌面端 To Do List 管理 App（Tauri 2 + React + SQLite，跨 Win/Mac），参考 Microsoft To Do 与 Apple 提醒事项，纯本地存储无云同步。技术方案见 [todo-lite/DESIGN.md](./todo-lite/DESIGN.md)。

### [pulse-pet](./pulse-pet)
桌面宠物 App，监听 opencode agent 工作状态并以宠物动画呈现，附带 token 消耗本地统计、喝水/休息提醒（气泡 + 可选烟花模式）、轻量 todo 插件。v1 仅支持 opencode，但架构上预留多 agent 扩展通道（Claude Code / Codex / 自研 agent）。技术栈与 todo-lite 一致（Tauri 2 + React + TS），跨 macOS / Windows。调研报告见 [pulse-pet/desktop-pet-research.md](./pulse-pet/desktop-pet-research.md)，v1 范围决策见 [pulse-pet/DECISIONS.md](./pulse-pet/DECISIONS.md)。
