# todo-lite 设计方案

轻量级桌面端 To Do List 管理 App（Windows / macOS），功能与交互参考 **Microsoft To Do**（主体），吸收 **Apple 提醒事项** 的亮点（优先级三级、标签、列表分区）。

## 1. 目标与定位

- 轻量级：安装包几 MB、内存占用低、启动快
- 纯本地：SQLite 存储，无云同步、无账号
- 单机单用户，POC 定位：效果验证通过后可拆仓演进

## 2. 技术架构

| 层 | 选型 | 说明 |
|---|---|---|
| 桌面壳 | Tauri 2.x (Rust) | 一套代码跨 Win/Mac，体积小 |
| 前端 | React 18 + TypeScript + Vite | 生态成熟 |
| 状态管理 | Zustand | 轻量 |
| 存储 | SQLite（tauri-plugin-sql） | 纯本地；数据访问集中在前端 `src/lib/db.ts`（SQL 全部收敛于此，不另写 Rust CRUD 命令，避免双份数据访问路径） |
| 拖拽排序 | @dnd-kit | 任务/列表手动排序 |
| 桌面通知 | tauri-plugin-notification | 提醒到点弹通知（前端 30s 轮询触发） |
| 全局快捷键 | tauri-plugin-global-shortcut | ⌘/Ctrl+Shift+Space 唤起窗口 + 快速添加 |
| 系统托盘 | Tauri 内置 TrayIconBuilder | 显示/隐藏、新建任务、退出；关闭窗口最小化到托盘 |

开发验证：当前 Mac 环境开发；Windows 需 WebView2（Win10/11 自带）+ MSVC 工具链，POC 阶段最后验证。

## 3. 数据模型

```sql
-- 列表分组（侧栏）
CREATE TABLE list_groups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0
);

-- 列表
CREATE TABLE lists (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  color TEXT NOT NULL DEFAULT '#2563EB',
  icon TEXT,
  group_id INTEGER REFERENCES list_groups(id),
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 列表内分区
CREATE TABLE sections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0
);

-- 标签
CREATE TABLE tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  color TEXT NOT NULL DEFAULT '#6B7280'
);

-- 任务
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  list_id INTEGER REFERENCES lists(id) ON DELETE SET NULL,
  section_id INTEGER REFERENCES sections(id),
  parent_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE, -- 子任务自引用
  title TEXT NOT NULL,
  notes TEXT,
  priority INTEGER NOT NULL DEFAULT 0,   -- 0无 / 1低 / 2中 / 3高
  flagged INTEGER NOT NULL DEFAULT 0,    -- 旗标
  my_day_date TEXT,                      -- 我的某天
  due_date TEXT,                         -- YYYY-MM-DD
  due_time TEXT,                         -- HH:MM
  reminder_at TEXT,                      -- 完整提醒时间
  repeat_rule TEXT,                      -- JSON: {type: daily|weekdays|weekly|monthly|yearly, interval}
  sort_order INTEGER NOT NULL DEFAULT 0,
  completed_at TEXT,
  deleted_at TEXT,                       -- 软删除（30 天清理）
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 任务-标签（多对多）
CREATE TABLE task_tags (
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (task_id, tag_id)
);
```

智能列表（我的某天 / 重要 / 计划 / 已安排 / 无日期 / 已完成）用 SQL 查询实现，不建表。软删除任务 30 天后物理清理。

## 4. MVP 功能清单

### A. 任务核心
- 快速添加（顶部输入框 + 回车）
- 任务标题行内编辑
- 完成 / 取消完成（划线动画）
- 截止日期（今日 / 明日 / 下周 / 自定义）
- 提醒时间
- 重复任务（每日 / 工作日 / 每周 / 每月 / 每年；完成时计算下次发生时间自动重开）
- 子任务（可折叠 + 进度）
- 备注
- 优先级：无 / 低 / 中 / 高
- 标签（打标 + 按标签筛选）
- 旗标
- 拖拽手动排序
- 最近删除（30 天恢复）

### B. 组织与视图
- 智能列表：我的某天 / 重要 / 计划 / 已安排 / 无日期
- 自定义列表 + 颜色 / 图标
- 列表分组
- 列表分区
- 全局搜索
- 排序切换：重要性 / 截止日期 / 创建时间 / 字母顺序 / 手动
- 已完成 / 未完成切换
- 深色模式

### D. 系统集成
- 桌面通知：前端 30s 轮询检查 `reminder_at`（90s 匹配窗口防漏），localStorage 去重；权限未授权时自动请求。注意：`reminder_at` 存**本地时间**（用户设置时由前端写入），轮询比较同用本地时间，勿用 SQLite `datetime('now')`（UTC）混用
- 全局快捷键（⌘/Ctrl+Shift+Space：唤起窗口并聚焦快速添加框）
- 系统托盘（左键点击显示/隐藏窗口、右键菜单：显示/隐藏、新建任务、退出；关闭窗口时隐藏到托盘而非退出）。注意：TrayIconEvent::Click 在 Down/Up 各触发一次，toggle 逻辑须判断 button_state

### 明确不做（可后续迭代）
自定义智能列表规则、时间线视图、附件、云同步 / 多设备、共享协作、位置提醒、消息提醒

## 5. UI 布局与交互

参考 To Do 布局（侧栏 + 任务列表双栏），吸收提醒事项的列表分区；**任务详情为右侧悬浮面板**（360px，点击任务打开，✕/Esc 关闭，点击侧栏项自动关闭，不挤占任务列表宽度）：

```
┌─────────┬─────────────────────┐
│ 侧栏     │  任务列表            │
│ 智能列表 │  [标题/排序/搜索]     │
│ 我的列表 │  分区标题             │
│ 分组     │  □ 任务  ★ 今日       │
│ 底部快捷 │  手动拖拽排序         │
│ 主题切换 │                     │
└─────────┴─────────────────────┘
   ┌──────────────────────┐
   │ 详情面板（悬浮，可关闭）│
   │ 优先级/标签/备注/…    │
   └──────────────────────┘
```

交互要点：
- 任务项右键菜单：优先级 / 标签 / 旗标 / 日期快速操作
- 任务行 hover 显示垃圾桶图标（最右侧），点击软删除任务（含子任务级联）；最近删除视图内为"恢复/永久删除"按钮
- `+` 快速添加框
- Esc 关闭详情面板 / 关闭搜索
- 收起详情面板：✕ 按钮 / Esc / 点击中间栏空白处 / 点击面板自身空白处（交互控件除外）/ 点击侧栏其他项
- 键盘导航（window 级监听）：↑↓ 选择、Enter 打开详情、Space 完成、⌘/Ctrl+F 搜索、⌘/Ctrl+T 快速添加
- 空状态插画：按视图区分配置（搜索🔍 / 最近删除🗑️ / 其余🎉），附"添加任务"CTA
- 全局搜索：⌘F 聚焦，标题 LIKE 匹配，跨所有列表/智能列表（最近删除内搜索也支持），搜索时禁用拖拽
- 主题切换：侧栏底部按钮循环 跟随系统 → 浅色 → 深色

## 6. 项目结构

```
lab/todo-lite/
├── src/                # React 前端
│   ├── components/     # Sidebar / TaskList / DetailPanel / modals
│   ├── store/          # zustand: tasks / lists / ui
│   ├── lib/            # db.ts（全部 SQL 数据访问）、repeat.ts（重复规则）
│   └── styles/
├── src-tauri/          # Rust: main.rs / db.rs（迁移 + 查询）
├── migrations/         # SQL 迁移文件
├── DESIGN.md           # 本文档
└── README.md
```

## 7. 实施里程碑

1. **M1 骨架**：Tauri + React + Vite 初始化，SQLite 建库 + 迁移跑通
2. **M2 数据层**：类型定义 + `lib/db.ts` 数据访问层（全部 SQL：CRUD / 智能列表查询 / 重复规则 / 软删除恢复）+ zustand store（tasks / lists / ui）
3. **M3 核心 UI**：三栏布局、侧栏、任务列表（分区 / 排序 / 完成动画）
4. **M4 详情面板**：优先级 / 标签 / 备注 / 子任务 / 日期 / 重复 / 删除
5. **M5 增强**：全局搜索（⌘F）、最近删除（单个恢复/永久删除/清空）、深色模式开关、键盘导航、空状态打磨、详情面板刷新修复
6. **M6 系统集成**：通知（30s 轮询）、全局快捷键（唤起+快速添加）、托盘（隐藏/新建/退出）
7. **M7 收尾**：Mac 全流程自测 → 交叉检查 Windows 兼容点

## 8. 风险与说明

- 桌面通知仅在 App 运行时有效（无后台常驻），开机启动已移除——POC 可接受；通知横幅显示依赖系统通知设置（系统设置 → 通知 → todo-lite 开启横幅样式）
- Tauri 插件 API 变化较快，锁定最新稳定版，按文档调整
- 重复任务策略：完成时计算下一次发生时间，自动重开任务
- Windows 端未实机验证（当前 Mac 环境），M7 阶段交叉检查

## 9. 打包与 CI

- **macOS**：`npm run tauri build` 产出 `.app` + `.dmg`
- **Windows**：macOS 上无法交叉打包（需 MSVC + NSIS/WiX），通过 GitHub Actions 产出：
  - `.github/workflows/build.yml`（tauri-action，windows-latest + macos-latest 矩阵）
  - 触发方式：push tag `todo-lite-v*`，或 GitHub Actions 页面手动触发
  - 产出：Windows `.msi`/`.exe` 安装包、macOS `.dmg`，自动附加到 draft Release
