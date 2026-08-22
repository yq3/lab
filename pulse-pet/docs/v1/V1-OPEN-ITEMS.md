# PulsePet v1 未完成事项清单（Open Items）

> 生成：2026-08-19（M8 收尾合入 develop 后、`pulse-pet-v0.1.0` tag 发布验证通过后）
> 来源：M1~M8 工作流检查点（`.opencode/workflows/task-pulsepet-m*.md`）遗留事项汇总 + DESIGN §11/§12 + TEST-CASES TC-DONE/TC-EV-22
> 性质：v1 功能开发（M1~M8）已全部收官并合入 develop；本清单为**实机验证、综合验收、小修、体验优化、v2 项**五类未了结事项。多数为"等硬件/等触发条件"，非阻塞缺陷。
>
> **2026-08-20 裁定**：本清单各条目去向已定——三/四全部 + 二（综合验收）→ **v0.1.3 维护版**（计划见本文 [§八](#八v013-维护版计划01x-线收尾)）；五-2（抢镜）→ **v2 M6**；五-1/3（心跳）→ **裁定不做**；七-1 随 v0.1.3 发版处置；七-2 拆仓 → **暂不拆**（v2 侧范围见 [V2-SCOPE.md](../v2/V2-SCOPE.md)）。各节内已逐条标注。

---

## 一、实机验证类（等硬件环境）

> **去向（2026-08-20）**：不进 v2 里程碑，维持观察项——等硬件环境顺带核对（[V2-SCOPE.md](../v2/V2-SCOPE.md) §5.6）。

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

> **去向（2026-08-20）**：→ v0.1.3 维护版（[§八](#八v013-维护版计划01x-线收尾)）；TC-DONE-04 无人值守 30 分钟顺带验证四-2/3/4 修复效果。

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

> **去向（2026-08-20）**：两条均 → v0.1.3 维护版（[§八](#八v013-维护版计划01x-线收尾)）。

| # | 事项 | 来源 | 规模 |
|---|---|---|---|
| 1 | Settings 语言切换失败提示复用 `settings.passFail` key（文案为"切换穿透失败"语义错位）→ 新增 `settings.languageFail` 键 | M8 R2 committer 裁定记录级接受、移交后续 | ~3 行 + 1 字典键 |
| 2 | `actions/checkout@v4` / `actions/setup-node@v4` Node 20 弃用警告（GitHub 平台级，目前强制 Node 24 运行无阻断）→ 升级 action 大版本 | 2026-08-19 CI 实跑发现 | workflow 一行级；todo-lite 共用同一 build.yml，改动影响两个项目需一起回归 |

---

## 四、体验优化项（非缺陷，增强现有行为）

> **去向（2026-08-20）**：#1~#5 全部 → v0.1.3 维护版（[§八](#八v013-维护版计划01x-线收尾)）；其中 #2 与 #4 联动设计、#4 需先 spike 流式事件字段（§8.2）。

| # | 事项 | 来源 | 规模 |
|---|---|---|---|
| 1 | Settings 页「选择宠物」下拉列表仅在组件挂载时拉取一次（`Settings.tsx` `useEffect` → `load()`）；面板窗口为隐藏/显示复用，若标签页一直停在「设置」，导入新素材后重新打开面板不会重新拉取 → 下拉看不到新宠物（临时绕过：切走再切回标签页强制重挂载）。优化方向：监听面板重新可见 / `panel://tab` 事件时重新 `load()`，或下拉旁加「刷新」按钮，使 README「放好后打开设置页即出现」的承诺无条件成立 | 2026-08-20 用户实测 petdex 素材导入发现（素材与目录结构均合规仍不显示，切 tab 重挂载后出现） | Settings.tsx 单文件 ~10-20 行 |
| 2 | thinking 状态视觉上几乎不可见：`chat.message` → thinking 与 `session.status(busy)` → working 几乎同时到达，且 App 侧同 session 后到覆盖（`session_state.rs` `apply_event` 直接 insert，`priority()` 仅用于多 session 合并）→ thinking 可见窗口仅几百毫秒，用户发消息后宠物直接变 working。优化方向：插件侧 thinking 粘性窗口——`chat.message` 投递 thinking 后 3-5s 内吞掉 reaction 桶的 working/idle（更高优先级的 editing/testing/waiting-permission 照常放行、自然穿透），效果为 thinking 稳定显示至真正开始干活 | 2026-08-20 用户观测发消息后看不到 thinking，排查确认链路正常（瞬态被快速覆盖，非缺陷） | `pulse-pet-hook.js` + `plugin-hook.test.ts` ~20-30 行 |
| 3 | 会话结束后宠物停在 working 约 30s（最长 ~60s）才回 idle：idle 被归入 reaction 节流桶（10s 冷却），而同桶升级放行只放行更高优先级——会话结束时最后投递的 working(1) 刚占桶，紧随的 `session.idle`/`session.status(idle)` → idle(0) 永远无法穿透冷却被吞 → 回归 idle 只能靠 App 侧 `idle_timeout` 30s 兜底（最后投递为瞬态时先 30s→working 再 30s→idle）。优化方向：idle 从 reaction 桶豁免（`bucketFor("idle")` 返回 null 永远放行）——idle 仅由真实会话边界事件触发、低频，双通道重复投递无害 | 2026-08-20 用户观测会话结束长时间停留 working，排查确认节流吞掉会话结束信号（行为缺陷，非环境问题） | `pulse-pet-hook.js` ~3 行 + `plugin-hook.test.ts` 补测试；改完需重跑 `install.sh` 重装插件 |
| 4 | 会话进行中（回答仍在流式输出）宠物却变成 idle：插件可感知信号仅「消息提交 / 状态切换 / 工具前后 / 权限」四类，模型纯文本生成阶段（长回答 / 长推理 / 慢 LLM 响应）无工具调用 → 事件静默 >30s → App 侧 `idle_timeout` 兜底回收（session_state.rs `tick` 只看事件静默时长，不看会话真实 busy）→ 显示 idle；工具密集阶段不受影响。优化方向：`classifyEvent` 增加对流式总线事件（`message.updated` / `message.part.updated`，1.18 事件联合类型中存在，字段需实测确认）的分类 → 投递 working，流式事件高频到达、经 reaction 桶 10s 节流后天然形成心跳维持活性（与 v2 心跳机制文档五-1 互补：那条管「结束信号被吞」、这条管「进行中无信号」）。**注意：与第 2 条（thinking 粘性窗口）需一起设计**——粘性窗口吞掉 working 会减少计时刷新机会、加剧本问题 | 2026-08-20 用户观测对话进行中宠物变 idle，排查确认事件静默超时所致（非缺陷，设计边界） | `pulse-pet-hook.js` ~10 行 + `plugin-hook.test.ts` 补测试；流式事件字段需先实测 |
| 5 | 勾选烟花的提醒触发时只有烟花、无气泡文案——用户看到烟花不知道提醒了什么。现状：`reminder-bridge.ts` 对 `reminder://trigger` 按 `usesFireworks(t)` 二选一编排（烟花分支完全不构造/展示气泡，README「烟花模式…替代气泡」即此语义）。优化方向：去掉 if/else，无条件走气泡路径（含 todo 派生文案构造 + 净化），`usesFireworks(t)` 时额外 invoke 烟花——气泡（pet 头上 8s）与烟花（全屏 ~3.8s）同时展示；记账天然安全（`ack_log`/`dismiss_log` 均带 `WHERE dismissed_via IS NULL`，先到先写、后到 no-op，无双写风险）。后续新增其它特效同样只「叠加」不「替代」气泡 | 2026-08-20 用户提出（烟花触发时无文案，信息缺失） | `reminder-bridge.ts` ~10 行 + petStore 测试补断言；同步 README 烟花模式描述、DESIGN §5.2/§5.3、TEST-CASES TC-RM-09/11 措辞；改完需重新构建 App 生效 |

---

## 五、v2 / 条件触发项（v1 明确不做）

> **裁定（2026-08-20，见 [V2-SCOPE.md](../v2/V2-SCOPE.md) §3/§4）**：#1/#3（心跳）→ **不做**（流式心跳落地后仅剩"探测插件进程存活"边缘用途）；#2（抢镜）→ **v2 M6**（用户确认真实多开，含多 agent 场景，气泡带 agent 标识）。

| # | 事项 | 触发条件 / 去向 |
|---|---|---|
| 1 | 心跳机制（插件周期 ping `/health`）+ 限流豁免 `/health`（当前限流计费含 /health 与 401） | ~~v2~~ → **裁定不做**（2026-08-20；原捆绑场景为双向审批，已一并裁定不做） |
| 2 | 多 session 抢镜切换规则（如"最近 5s 有事件的 session 优先"） | → **v2 M6**（最近活跃优先 + agent 标识） |
| 3 | 限流豁免 /health 与 401 计费优化 | 随 #1 → **裁定不做** |

---

## 六、观察项（非缺陷，记录不动 / 等环境顺带）

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

## 七、运营待办

> **裁定（2026-08-20）**：#1 → 随 v0.1.3 发版一并处置；#2 → **暂不拆仓**，v2 继续在 lab 下演进，时机后续再议。

| # | 事项 | 状态 |
|---|---|---|
| 1 | draft Release `pulse-pet-v0.1.0` 发布 | draft 状态（4 产物已挂）；v0.1.3 发布时一并决定 publish 或丢弃 |
| 2 | v1 拆仓独立演进评估 | **已裁定：暂不拆仓**（2026-08-20，[V2-SCOPE.md](../v2/V2-SCOPE.md) §1） |

---

## 八、v0.1.3 维护版计划（0.1.x 线收尾）

> 记录日期：2026-08-20（2026-08-22 自 V2-SCOPE §2 移入并改写引用）
> 身份：**0.1.x 发版线的维护收尾**——清偿本清单 v1 遗留（§8.1 各项），与 v2 开发并行；不是 v1 功能追加，也不是 v2 范围。v2 主体计划见 [V2-SCOPE.md](../v2/V2-SCOPE.md) §3。
> 来源：v1 收官（M8 + v0.1.0/v0.1.2 发版）后的实际使用反馈与范围讨论。

### 8.1 范围（对应本清单编号）

| 来源 | 事项 | 要点 |
|---|---|---|
| 三-1 | `settings.languageFail` 文案 key | 新增键替换语义错位的 `settings.passFail` 复用，~3 行 + 1 字典键 |
| 三-2 | GitHub Actions v4 升级 | `actions/checkout` / `setup-node` 升大版本；**与 todo-lite 共用 build.yml，需一起回归** |
| 四-1 | 设置页宠物下拉自动刷新 | 监听面板重新可见 / `panel://tab` 重新 `load()`，使 README「放好即出现」承诺无条件成立 |
| 四-2 | thinking 粘性窗口 | `chat.message` 投递 thinking 后 3-5s 内吞掉 reaction 桶的 working/idle（更高优先级状态照常穿透） |
| 四-3 | idle 节流豁免 | `bucketFor("idle")` 返回 null 永远放行（行为缺陷修复） |
| 四-4 | 流式心跳 | `classifyEvent` 增加 `message.updated` / `message.part.updated` → working，防纯文本生成阶段静默超时回 idle |
| 四-5 | 烟花+气泡叠加 | 去掉二选一编排，烟花提醒同时展示气泡文案；原则：特效只叠加不替代气泡 |
| 二 | TC-DONE-01~09 综合验收 | 含 **TC-DONE-04 无人值守 30 分钟**（从未完整执行；顺带验证四-2/3/4 真实长会话效果） |
| 七-1 | draft Release 处置 | v0.1.3 发布时一并决定 v0.1.0 draft 的 publish 或丢弃 |

### 8.2 设计约束

- **四-2 与四-4 必须联动设计**（§四-4 已注明）：粘性窗口吞 working 会减少计时刷新机会、加剧流式静默超时。初步方向：粘性窗口只吞 `session.status(busy)` 来源的 working，流式心跳类 working 照常投递（只刷新活性、不改变显示）——实现阶段定案。
- **四-4 前置 spike**：实测 opencode 1.18 `message.updated` / `message.part.updated` 事件字段（联合类型中存在，字段未证实）。

### 8.3 发版

- tag `pulse-pet-v0.1.3` 触发现有 CI（windows-latest + macos-latest 矩阵）；发布说明提醒用户重跑 `install.sh`（插件侧改动配套）。

---

## 附：v1 已清偿对照（简要备查）

- M2 同桶升级放行（M5 清偿）｜M3 P3 五条（M4 清偿）｜M1 fireworks 透明实测（M4 清偿）
- M4 P2②③④（M7 清偿）⑤（M5 清偿）⑥⑦ + M5 P2⑤⑥ + M6 P2②（M8 清偿）
- M5 P2①②③④（M6 清偿）｜M6 P2①（M6 R3 清偿）
- M7 P2①②④（M8 A1/A2/A3 清偿）③（回 spec 定案）
- M4 P2① cover_monitor 竞态（M8 A9 代码级清偿，实机确认归一.1）
- M8 过程项：productName 改名旧产物清理（方案 a）、README 行序表 P1 修复、时序图标题/校验串/编译期断言 P2×3、SIGTERM 说明等 P3 全闭环
