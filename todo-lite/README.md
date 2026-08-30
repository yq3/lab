# todo-lite

轻量级桌面端 To Do List 管理 App（Windows / macOS），功能与交互参考 Microsoft To Do，
吸收 Apple 提醒事项亮点（优先级三级、标签、列表分区）。Tauri 2 + React + TypeScript +
SQLite，纯本地存储，无云同步、无账号。

## 功能

- **任务核心**：快速添加、行内编辑、完成动画、截止日期/提醒、重复任务（完成自动排下次）、
  子任务、备注、优先级、标签、旗标、拖拽排序、最近删除（30 天可恢复）
- **组织与视图**：智能列表（我的某天/重要/计划/已安排/无日期）、自定义列表（颜色/图标）、
  列表分组与分区、全局搜索（⌘/Ctrl+F）、五种排序切换、深色模式
- **系统集成**：桌面通知（到点提醒）、全局快捷键 ⌘/Ctrl+Shift+Space 唤起快速添加、
  系统托盘（关闭窗口最小化到托盘）

## 开发

环境要求：Node.js 18+、Rust 工具链（平台依赖见 Tauri 官方文档）。

```bash
npm install
npm run tauri dev    # 开发调试
npm run tauri build  # 本地打包（macOS 产出 .app/.dmg）
```

## 安装包

push tag `todo-lite-v*`（如 `todo-lite-v0.1.1`）触发 `.github/workflows/build.yml`，
GitHub Actions 构建双平台安装包（Windows `.msi`/`.exe`、macOS `.dmg`）并挂到 draft Release。

## 数据存储

SQLite 数据库位于系统应用配置目录（macOS
`~/Library/Application Support/com.todolite.app/`、Windows `%APPDATA%\com.todolite.app\`），
删除该目录即重置全部数据。

## 已知限制

- 桌面通知仅在 App 运行时有效（无后台常驻）；横幅显示需在系统通知设置中允许
- Windows 端未实机验证（开发环境为 macOS，仅交叉检查兼容点）

## 文档

- [DESIGN.md](./DESIGN.md)——技术方案（架构 / 数据模型 / 交互 / 里程碑）
- [TEST_CASES.md](./TEST_CASES.md)——验收用例
