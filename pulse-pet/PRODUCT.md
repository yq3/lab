# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

（Tauri 2 桌面壳内的 web 前端：React 19 + TS + Vite + Zustand，三窗口按 hash 路由 `#/pet` `#/panel` `#/fireworks`。原生壳只提供托盘/热键/窗口能力，设计语言按 web 走。）

## Users

- **主要用户（当前唯一）**：开发者本人——在日常编码中使用 opencode agent 工作的人。PulsePet 常驻其桌面，随时反映 agent 状态。
- 阶段定位：先自用验证 POC。是否面向 opencode 用户社群 / 桌面宠物素材社群发布，是**未定项**（不预设方向）。

## Product Purpose

桌面宠物 App：通过 opencode 插件监听 agent 工作状态，用像素小猫动画（9 行姿态 atlas）实时呈现；配 token 本地统计、喝水/休息提醒（气泡 + 烟花）、轻量 todo 插件（派生提醒 / 完成联动庆祝）。

成功的定义（用户确认）：

1. POC 验证通过——「agent 状态可视化 + 宠物陪伴」这个效果成立；
2. 日常长期自用——自己每天都开着用，稳定、不打扰。

## Positioning

与 opencode 深度联动的**本地** agent 状态桌面宠物。组合了三类邻位产品都不具备的机制：

- 通用桌面宠物（petdex / codex-pet 素材生态）没有 agent 事件集成；
- agent 监控面板 / 仪表盘没有陪伴形态与常驻桌面的存在感；
- 官方插件事件链路（hooks → 9 状态归一化映射 → 本机回环上报）+ 只读 `opencode.db` 的 token 统计，这一链路是 PulsePet 特有的。

## Operating Context

- 用户在终端使用 opencode CLI；插件装在 `~/.config/opencode/plugins/`，登记于 `opencode.json` 的 `plugin` 数组（带 `--pulse-pet-managed` 标记，幂等装卸）。
- App 常驻系统托盘；宠物窗口可拖拽至任意位置（含跨显示器，位置记忆）、可开点击穿透纯展示；全局热键唤起面板 / 切穿透。
- token 统计只读查询 `~/.local/share/opencode/opencode.db`（WAL）；会话结束 60s 内有用量的会触发宠物气泡汇报。
- 三窗口：`pet`（透明 220×220 置顶）、`panel`（900×640 控制面板）、`fireworks`（透明全屏）。
- 语言：zh / en 双语即时切换，默认跟随系统。

## Capabilities and Constraints

**硬约束（用户确认，未来任何版本不得违反）**

- 全程本机：事件链路仅走 `127.0.0.1` 回环，**永不联网**；
- agent 事件只在内存中传递，**不落盘**；
- 一次性随机 token 鉴权（无 token 请求一律 401），token/endpoint 文件随启动生成、退出清除。

**功能事实（v1 = 0.1.x，范围见 `docs/v1/DECISIONS.md`）**

- 9 种归一化 agent 状态（idle/working/thinking/editing/testing/waiting-permission/success/error）映射到 petdex 官方 9 行姿态行序；事件节流 + 30s 瞬态超时兜底。
- 自定义宠物素材：codex atlas 格式（`pet.json` + spritesheet），固定 8 列 × 9 或 11 行，帧宽高比 192:208（帧宽为 12 的倍数）；不满足**整只拒载**，回退内置小猫 `blinking-kitty`（编译期内嵌兜底），设置页显示回退原因。扫描路径：内置 → `~/.codex/pets/` → `~/.petdex/pets/`。
- 提醒：喝水/休息/自定义，间隔 1–1440 分钟，时间窗支持跨午夜；烟花 + 气泡叠加；同规则 3 分钟去重；暂停期间不触发、恢复后不补弹。
- Todo 内置插件：派生提醒（截止带时间且提前 > 0 才提醒，单次）、完成联动庆祝、今日全清汇总。
- 静默性：App 未启动时插件静默（不报错、不打日志），指数退避重试，App 启动后自动恢复；killswitch 文件可紧急停用。

**已知边界**

- Windows 仅 CI 构建验证，未实机测试；多显示器场景未实机验证（两者待有硬件时清偿）。
- Rust 侧边缘错误文案仅中文（v1 不做全量错误串双语）。
- v2 范围另见 `docs/v2/V2-SCOPE.md`；v1 线文档冻结于 `docs/v1/`。
- 本项目是 POC：效果验证通过后可能拆仓独立演进，目录保持自包含。

## Brand Commitments

- 名称 PulsePet；品牌名与宠物状态技术名（idle/working…）**不翻译**。
- 内置默认小猫 `blinking-kitty` 是最终兜底，任何素材故障下 App 必须保持可用。

## Evidence on Hand

- 设计/验收/决策全套文档：`docs/v1/`（DESIGN、TEST-CASES、DECISIONS、V1-OPEN-ITEMS、历史评审留档、调研）与 `docs/v2/V2-SCOPE.md`。
- 实测记录：M3 对 opencode 1.18.18 本机真实 `opencode.db` 的 session 表写入时机观测（结论同时钉在 `src-tauri/src/token_stats.rs` 模块注释）。
- 前端纯逻辑测试套件（`npm test`：状态降级映射 / canvas 缩放 / i18n 字典完备性等）。
- 内置精灵与图标生成脚本 `scripts/gen-assets.mjs`。
- **缺失（未来工作不得虚构）**：无外部用户反馈、下载量、证言或社区使用数据——项目尚无任何外部用户。

## Product Principles

1. **本地与隐私优先**：数据不出本机，agent 事件只在内存传递，永不联网——硬约束，优先级高于任何功能机会。
2. **静默陪伴，不打扰**：宠物反映状态而非索取注意力；失败静默退避、提醒不补弹、绝不向 opencode 终端输出噪音——宿主工作流永远优先。
3. **优雅降级，永不崩溃**：素材损坏回退内置小猫、端口占用自动迁移、App 未启动插件静默——任何一侧故障不影响另一侧可用。
4. **自包含轻量**：依赖极简（自研 i18n 字典、单 SQLite 文件、无云服务），保持 POC 可随时拆仓独立演进。
5. **尊重宿主生态**：只读 opencode 数据、插件幂等装卸且不碰用户原有配置、兼容 petdex 社区素材标准与行序。
