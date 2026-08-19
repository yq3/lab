# PulsePet v1 未完成事项清单（Open Items）

> 生成：2026-08-19（M8 收尾合入 develop 后、`pulse-pet-v0.1.0` tag 发布验证通过后）
> 来源：M1~M8 工作流检查点（`.opencode/workflows/task-pulsepet-m*.md`）遗留事项汇总 + DESIGN §11/§12 + TEST-CASES TC-DONE/TC-EV-22
> 性质：v1 功能开发（M1~M8）已全部收官并合入 develop；本清单为**实机验证、综合验收、小修、v2 项**四类未了结事项。多数为"等硬件/等触发条件"，非阻塞缺陷。

---

## 一、实机验证类（等硬件环境）

### 1.1 多屏实机（需外接显示器）

来源：M4/M6 检查点；2026-08-19 用户确认本机无外接屏，继续移交。

| # | 事项 | 说明 |
|---|---|---|
| 1 | TC-APP-10 显示器回退 | 拔屏后宠物回退主屏（逻辑单测 8 用例已过，拔屏实机未验） |
| 2 | TC-APP-11 跨显示器拖拽 | 平滑跨屏/不被边缘卡住/落点正确（实现走 OS 原生 start_dragging，DESIGN §6.3 已定口径） |
| 3 | 多显示器烟花绽放点 | 绽放点=宠物所在屏中轴 + 0.3 屏高，多屏判定链路（M4 代码级已验，实机未验）+ 跨屏烟花评估 |
| 4 | A9 修复的多屏实机确认 | cover_monitor 竞态已改 monitor bounds 直算（M8 代码级 + 5 单测），实机行为确认 |
| 5 | 拖拽钳制观察项 | 合成事件下右缘/下缘钳制不一致、跟随精度波动（+48/+80）——真实鼠标 1:1 行为确认 |

### 1.2 Windows 实机（需 Windows 设备）

来源：M2~M8 多次移交；2026-08-19 用户确认无 Windows 实机。CI 侧已清偿（见 1.3）。

> **2026-08-19 更新**：Windows 实机到位，v0.1.0 首测发现启动闪退（issue #9，根因 = tauri config 窗口早于 setup manage 创建 + WebView2 异步 IPC 竞态，v0.1.2 修复，DESIGN §7.1 定案）；**v0.1.2 实机验证通过，下表 1 已清偿**，其余条目随后续实机使用顺带核对。

| # | 事项 | 说明 |
|---|---|---|
| 1 | TC-DONE-03 / v1 Done 第 3 条 | ✅ 已清偿：v0.1.2 实机安装运行跑通（setup.exe；宠物/动画/拖拽/点击/右键/托盘正常，issue #9） |
| 2 | TC-SEC-05 | token 文件位于 `%LOCALAPPDATA%\pulsepet\runtime\`（实机核对位置；POSIX 0600 无效为已知文档口径）——实机已装，可顺带核对 |
| 3 | TC-TK-02 | opencode.db schema canary 在 Windows 实机验证（M3 仅代码级 + Windows cfg 代码级） |
| 4 | TC-SP-10 运行时验证 | webp 解码在 Windows 实机运行（编译侧已由 CI 验证，见 1.3）——v0.1.2 实机宠物动画正常，webp atlas 解码路径实际已跑通 |
| 5 | pet-drag 平台差异 | macOS 无 pointercancel 的 DragClickGuard 补丁逻辑在 Windows 行为核对（M6 R2 注：如遇差异只调 pet-drag.ts 单文件）——v0.1.2 实机拖拽正常，粗粒度已验 |

### 1.3 ✅ 已清偿（2026-08-19，此处仅记录备查）

- **TC-CI-02 CI 实跑**：`pulse-pet-v0.1.0` tag 触发 release workflow，windows-latest + macos-latest 双矩阵 **success**（8m17s），tag 前缀分流正确、todo-lite 触发不受影响、draft Release "PulsePet v0.1.0" 4 产物已挂（dmg 4.36MB / setup.exe 3.07MB / msi 4.4MB / app.tar.gz 4.34MB）。
- **TC-SP-10 编译侧**：image-webp 在 CI windows-latest 编译通过，无 png 回退。

---

## 二、v1 Done 综合验收（TC-DONE-01~09）

来源：M8 范围确认时用户裁定后移，去向 = v1 Done 验收任务（M8 后专项）。

各分项现状（多数已随里程碑分别验证，综合验收重点在全量回归编排 + 两项实跑）：

| 用例 | 内容 | 现状 |
|---|---|---|
| TC-DONE-01 | M1-M6 核心链路全量回归（TC-APP/EV/TK/RM/SP/WIN） | 各里程碑分别验证过；未做统一全量回归编排 |
| TC-DONE-02 | M7 TC-TD 全量回归 | M7 全量 PASS 过；随 01 一并编排 |
| TC-DONE-03 | 跨平台 | **已过（2026-08-19 v0.1.2 实机，issue #9）**——Windows 安装运行跑通；修复过程见 DESIGN §7.1/§12 |
| **TC-DONE-04** | **无人值守 30 分钟真实任务**（TC-EV-22 全量版） | **从未完整执行**——M2 仅做全链路 POST + 短时真实 e2e；需安装插件后无人值守跑 30 分钟核对状态吻合 |
| TC-DONE-05 | Token 对账（≤0.01 USD） | M3 验过（对账 diff 0）；随 01 复核 |
| TC-DONE-06 | 提醒双形态（气泡+烟花） | M4/M8 验过；随 01 复核 |
| TC-DONE-07 | 持久化保留 | M6/M7 验过；随 01 复核 |
| TC-DONE-08 | 消息净化 | M2/M8（TC-SEC-01 OCR 注入实测）验过 |
| TC-DONE-09 | 自忽略 | M2/M8 验过 |

---

## 三、代码级小修（无前置条件，可随时做）

| # | 事项 | 来源 | 规模 |
|---|---|---|---|
| 1 | Settings 语言切换失败提示复用 `settings.passFail` key（文案为"切换穿透失败"语义错位）→ 新增 `settings.languageFail` 键 | M8 R2 committer 裁定记录级接受、移交后续 | ~3 行 + 1 字典键 |
| 2 | `actions/checkout@v4` / `actions/setup-node@v4` Node 20 弃用警告（GitHub 平台级，目前强制 Node 24 运行无阻断）→ 升级 action 大版本 | 2026-08-19 CI 实跑发现 | workflow 一行级；todo-lite 共用同一 build.yml，改动影响两个项目需一起回归 |

---

## 四、v2 / 条件触发项（v1 明确不做）

| # | 事项 | 触发条件 / 去向 |
|---|---|---|
| 1 | 心跳机制（插件周期 ping `/health`）+ 限流豁免 `/health`（当前限流计费含 /health 与 401） | v2；2026-08-19 用户定案 v1 不引入心跳（DESIGN §3.1：/health 仅调试探活不参与回收） |
| 2 | 多 session 抢镜切换规则（如"最近 5s 有事件的 session 优先"） | DESIGN §12："M6 后视用户反馈再评估"——v1 优先级合并已实现，等实际使用反馈 |
| 3 | 限流豁免 /health 与 401 计费优化 | 随 1 一并（心跳引入时） |

---

## 五、观察项（非缺陷，记录不动 / 等环境顺带）

| # | 事项 | 来源 | 处置 |
|---|---|---|---|
| 1 | codex/petdex 无配置扫描分支实际不可达 | M5 tester / M8 A8 | 已注释定案保留（编译期内嵌素材损坏的防御层） |
| 2 | screencapture P3→sRGB 色彩偏移 ±1~14 | M5 tester | 环境问题；后续像素断言需容差 |
| 3 | idle 帧时长表 col0-col1 视觉相同 | M5 tester | 常驻单眼缝造型必然结果；恢复动态眨眼需重设计 |
| 4 | 合成输入噪声类（热键关 panel 时序、微信窗口不响应 CGEvent、激活后首个 plain click 不可靠） | M6 tester | 环境限制；多屏/实机时顺带复核 |
| 5 | todos 表 "Hello" 残留行 | M7 tester | 用户数据，按基线保留未动 |
| 6 | 原生 time input 前置拦截使校验错误串 GUI 不可构造 | M8 tester | 设计使然（前端拦截=前端校验先行），单测为权威验证路径 |
| 7 | pet 窗口 WebKit 后台挂起假阴性（App Nap） | M3/M8 tester | README「运行时视觉验证」已文档化；以真实 GUI 会话为准 |
| 8 | SIGTERM 强杀残留 runtime token/endpoint | M2/M8 tester | 已处置：M8 R2 README 补充说明（下次启动覆盖，无持久影响） |
| 9 | Rust 校验错误串不做全量双语 | M8 coder 裁定 | zh 措辞与 spec 钉住文案有测试守护；v1 收尾成本/收益裁定 |

---

## 六、运营待办

| # | 事项 | 状态 |
|---|---|---|
| 1 | draft Release `pulse-pet-v0.1.0` 发布 | draft 状态（4 产物已挂）；等用户检查产物后决定 publish 或保持 |
| 2 | v1 拆仓独立演进评估 | README/AGENTS 既有口径：POC 效果验证通过后可能拆仓；时机由用户定 |

---

## 附：v1 已清偿对照（简要备查）

- M2 同桶升级放行（M5 清偿）｜M3 P3 五条（M4 清偿）｜M1 fireworks 透明实测（M4 清偿）
- M4 P2②③④（M7 清偿）⑤（M5 清偿）⑥⑦ + M5 P2⑤⑥ + M6 P2②（M8 清偿）
- M5 P2①②③④（M6 清偿）｜M6 P2①（M6 R3 清偿）
- M7 P2①②④（M8 A1/A2/A3 清偿）③（回 spec 定案）
- M4 P2① cover_monitor 竞态（M8 A9 代码级清偿，实机确认归一.1）
- M8 过程项：productName 改名旧产物清理（方案 a）、README 行序表 P1 修复、时序图标题/校验串/编译期断言 P2×3、SIGTERM 说明等 P3 全闭环
