# PulsePet v1 未完成事项清单（Open Items）

> 生成：2026-08-19（M8 收尾合入 develop 后、`pulse-pet-v0.1.0` tag 发布验证通过后）
> 来源：M1~M8 工作流检查点（`.opencode/workflows/task-pulsepet-m*.md`）遗留事项汇总 + DESIGN §11/§12 + TEST-CASES TC-DONE/TC-EV-22
> 性质：v1 功能开发（M1~M8）已全部收官并合入 develop；本清单为**实机验证、综合验收、小修、体验优化、v2 项**五类未了结事项。多数为"等硬件/等触发条件"，非阻塞缺陷。
>
> **2026-08-20 裁定**：本清单各条目去向已定——三/四全部 + 二（综合验收）→ **v0.1.3 维护版**（计划见本文 [§八](#八v013-维护版计划01x-线收尾)）；五-2（抢镜）→ **v2 M6**；五-1/3（心跳）→ **裁定不做**；七-1 随 v0.1.3 发版处置；七-2 拆仓 → **暂不拆**（v2 侧范围见 [V2-SCOPE.md](../v2/V2-SCOPE.md)）。各节内已逐条标注。
>
> **2026-08-22 补录**：新增 [§九](#九已修复严重缺陷插件钩子同步阻塞宿主-opencode2026-08-22)——0.1.x 线迄今最严重缺陷（插件钩子同步阻塞宿主 opencode）的完整记录：症状、源码级根因、主流设计对照、修复与回归保护、残余风险裁定。已修复，随 v0.1.3 发布（§8.1 已列入）。

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
> **状态（2026-08-22）**：开发完成（§8.4 定案全部落地）+ 三方验证通过（§8.5：developer 自测 / tester 验收 PASS / committer 评审 APPROVED）；待 commit 与发版（§8.5 前置条件）。

### 8.1 范围（对应本清单编号）

| 来源 | 事项 | 要点 |
|---|---|---|
| 三-1 | `settings.languageFail` 文案 key | 新增键替换语义错位的 `settings.passFail` 复用，~3 行 + 1 字典键 |
| 三-2 | GitHub Actions v4 升级 | `actions/checkout` / `setup-node` 升大版本；**与 todo-lite 共用 build.yml，需一起回归** |
| 四-1 | 设置页宠物下拉自动刷新 | 监听面板重新可见 / `panel://tab` 重新 `load()`，使 README「放好即出现」承诺无条件成立 |
| 四-2 | thinking 粘性窗口 | `chat.message` 投递 thinking 后 3-5s 内吞掉 reaction 桶的 working/idle（更高优先级状态照常穿透） |
| 四-3 | idle 节流豁免 | `bucketFor("idle")` 返回 null 永远放行（行为缺陷修复） |
| 四-4 | 流式心跳 | `classifyEvent` 增加流式事件 → working（定案主力载体为 `message.part.delta`，`message.updated` / `message.part.updated` 低频补充，见 §8.4 spike），防纯文本生成阶段静默超时回 idle |
| 四-5 | 烟花+气泡叠加 | 去掉二选一编排，烟花提醒同时展示气泡文案；原则：特效只叠加不替代气泡 |
| 二 | TC-DONE-01~09 综合验收 | 含 **TC-DONE-04 无人值守 30 分钟**（从未完整执行；顺带验证四-2/3/4 真实长会话效果） |
| 七-1 | draft Release 处置 | v0.1.3 发布时一并决定 v0.1.0 draft 的 publish 或丢弃 |
| 九 | §九 修复随版发布 | 修复已在 develop 工作区完成（无需开发）；发布说明**重点**提醒重跑 `install.sh`（插件副本在 `~/.config/opencode/plugins/`，不随 App 更新） |

### 8.2 设计约束

- **四-2 与四-4 必须联动设计**（§四-4 已注明）：粘性窗口吞 working 会减少计时刷新机会、加剧流式静默超时。初步方向：粘性窗口只吞 `session.status(busy)` 来源的 working，流式心跳类 working 照常投递（只刷新活性、不改变显示）——**已由 §8.4 定案取代**（量化后无需按来源区分）。
- **四-4 前置 spike**：实测 opencode 1.18 `message.updated` / `message.part.updated` 事件字段（联合类型中存在，字段未证实）——**已完成（2026-08-22），结论见 §8.4**（真正的心跳载体是 `message.part.delta`）。
- **与 §九 零阻塞契约联动（2026-08-22）**：四-2/四-4 均改 `classifyEvent` / `Throttle` / `bucketFor`（§九 修复保留了这些纯函数原实现），实现时**必须保持钩子 fire-and-forget**——`plugin-hook.test.ts`「全部 6 个钩子返回 undefined 且非 thenable」用例钉住该不变量，回归即红。四-4 落地后流式事件高频进入 `deliver`（killswitch `existsSync` 前置于节流），单次 ~µs 级仍可忽略；若实测有影响，届时评估 killswitch TTL 缓存（§九 9.6 R1）。

### 8.3 发版

- tag `pulse-pet-v0.1.3` 触发现有 CI（windows-latest + macos-latest 矩阵）；发布说明提醒用户重跑 `install.sh`（插件侧改动配套）。

### 8.4 设计定案（2026-08-22，实施依据）

> 含 S1 spike 实测结论。用例落 `TEST-CASES.md`（TC-EV-24~27 / TC-RM-17 / TC-APP-14 / TC-CI-05 及修订项）。

**S1 spike 结论（opencode 1.18.19 本机实测，2026-08-22，headless `opencode run` + 事件探针）**：

- `sessionID` 在所有相关事件的 `properties.sessionID`（现有插件取法正确，无需改提取路径）；
- **`message.part.updated` 非高频**：纯文本流式生成全程仅在 part 边界发（step-start / reasoning 首 / text 首 / text 尾…共 7 次）——**不能当心跳**（推翻 §8.2 初步假设中的载体）；
- **`message.part.delta` 才是高频流式事件**（实测 40 行文本 ~4s 生成 112 次 ≈ 28 次/s，TUI 打字机数据源）；
- `session.status(busy)` 仅在生成开始发一次，纯文本长生成期间总线静默——四-4 病因实锤。

**四-4 流式心跳（定案）**：`classifyEvent` 增加 `message.part.delta`（主力心跳）+ `message.updated` / `message.part.updated`（低频补充，同映射无害）三个 case → `working`。delta 高频到达、经 reaction 桶 10s 节流后天然形成 ~10s 一次心跳 POST，`apply_event` 刷新 `last_event_at`，30s `idle_timeout` 不再误触。**Rust / 协议 / 前端零改动**（心跳对 App 就是普通状态事件）。

**四-2 thinking 粘性窗口（定案）**：`STICKY_MS = 4000` 固定常量（不做配置）。机制：`deliver` 链在 throttle 检查**前**——`kind=thinking` 记 `stickyUntil[sid]=now+4s`；此后 4s 内同 session 的 `working`/`idle` 静默丢弃（不占节流桶、不重置冷却）；`editing`/`testing`/`waiting-permission`/`error`/`success` 优先级高于 thinking(3)，不在吞没集合、自然穿透。粘性在 speech 桶节流检查**前**记录：连续两条消息第二条 thinking 被 20s 节流吞掉也能续窗。**不做 §8.2 设想的"按来源区分 working"**：量化后不必要——窗口 4s « idle_timeout 30s（仅消耗活性预算 13%），窗口过后首个 delta 心跳（≤10s 节流间隔）即恢复刷新；"吞全部 working/idle" 4 行代码达同等效果，Rust 零改动。

**四-3 idle 节流豁免（定案）**：`bucketFor("idle")` 返回 null（从 `REACTION_KINDS` 移除）——idle 永远放行，会话结束信号即到即投；`session.idle` + `session.status(idle)` 双通道重复投递到 App 幂等覆盖，无害。

**三机制联动时间线（设计自检）**：发消息 → thinking 置粘性窗、显示 thinking → 0-4s 内 delta→working 被吞（显示保持）→ 窗口过期后首个心跳 working（≤10s）→ 显示 working（生成中，正确）→ 工具期 `tool.execute.before(edit)`→editing 穿透 → 纯文本长生成 delta 心跳 ~10s/次防误 idle → 会话结束 `session.idle` 豁免放行、即时回 idle。

**零阻塞契约保持（§9 联动约束）**：三机制全部在 `deliver` 内部，钩子仍 fire-and-forget；delta 高频下 `deliver` 前置的 killswitch `existsSync`（~µs 级，§9.6 R1）+ classify 开销可忽略。

**四-5 烟花+气泡叠加（定案）**：`reminder-bridge.ts` 的 if/else 重构为纯函数 `planReminderActions(t, nowMs) → { bubbleText, fireworks }`（todo 派生文案构造 + 净化内聚，落 `src/lib/reminders.ts`）；桥消费：无条件 `showReminderBubble(bubbleText)`，`fireworks=true` 时**额外** invoke 烟花。原则：**特效只叠加、不替代气泡**。文档同步 4 处：README 烟花模式措辞、DESIGN §5.1（到点编排句）/§5.3（叠加语义段）、TEST-CASES TC-RM-09/11。

**四-1 下拉自动刷新（定案）**：`Settings.tsx` 加 effect 监听 `tauri://focus`（面板重开必触发）+ `PANEL_TAB_EVENT`（目标=settings 时），任一触发重新 `load()`。双触发使「放好即出现」无条件成立（停在设置页重开面板无 tab 事件，靠 focus 兜住）。

**三-1 languageFail（定案）**：`i18n.ts` 加 `settings.languageFail`（zh：`切换语言失败：{msg}` / en 对应），`Settings.tsx` `onLanguage` catch（现误用 `settings.passFail`，L94 穿透路径不动）。

**三-2 Actions 升级（定案）**：`actions/checkout` / `actions/setup-node` 升当前最新大版本（实施时 `gh api` 查最新 major）；build.yml 与 todo-lite 共用，两项目路径各回归一次 CI。

**七-1 draft 处置（用户已裁定 2026-08-22）**：v0.1.0 draft **丢弃**（产物含 Windows 闪退缺陷 issue #9，发布徒增误导）——v0.1.3 发版时删除该 draft。

### 8.5 实施与三方验证记录（2026-08-22）

#### 8.5.1 开发实施（developer）

13 个文件，按 §8.4 定案落地，Rust 零改动：

| 分组 | 文件 | 内容 |
|---|---|---|
| 插件 | `opencode-plugin/pulse-pet-hook.js` / `.d.ts` | 流式心跳（delta/updated/part.updated→working + 缺 sessionID 丢弃）、`ThinkingSticky`（STICKY_MS=4000，节流前置、不占桶）、idle 移出 reaction 桶；头注补三机制段 |
| 插件测试 | `src/lib/plugin-hook.test.ts` | +17 用例（TC-EV-24 五子项/25 三子项/26 四子项/27 联动），2 处旧断言修订 |
| App | `src/lib/reminders.ts` + `reminder-bridge.ts` + `reminders.test.ts` | `planReminderActions` 纯函数 + 桥层叠加编排（+4 用例，TC-RM-17） |
| App | `src/panel/Settings.tsx` + `src/lib/i18n.ts` | `tauri://focus`+`panel://tab` 双触发下拉刷新；`settings.languageFail` 新键替换 passFail 误用 |
| 文档 | DESIGN §5.1/§5.3、TEST-CASES（新增/修订用例）、README（烟花叠加措辞）、本文件 §8.4 | 语义与实现同步 |
| CI | `.github/workflows/build.yml` | checkout / setup-node v4→v7（TC-CI-05 实跑待发版） |

自测（tester 已独立复验一致）：`npm test` **242/242**（基线 225+17）、`tsc --noEmit` 0 错、`npm run build` 通过、`cargo test` **163 passed + 1 ignored**（Rust 零改动基线确认）、`tauri build` 成功（版本号仍 0.1.2，bump 属发版步骤）。插件副本已重装（源/副本 md5 一致）；**长驻 opencode 会话需重启才加载新插件**（插件代码随宿主进程启动加载）。spike 探针与配置残留已清理恢复。

#### 8.5.2 tester 验收（2026-08-22 17:08–17:18，testedSha=9d57ca2 工作区）

**testVerdict: PASS**（0 缺陷，PENDING-USER 4 项 / SKIPPED 2 项不计 FAIL）：

- **独立回归**：npm test 242/242、tsc 0 错、vite/cargo/tauri build——与开发声明逐项一致。
- **用例↔测试映射审计**：TC-EV-24（5）/25（3）/26（4）/27/RM-17（4）全部子项在单测中有对应断言且语义一致（粘性不占桶、被 speech 节流仍续窗、60s delta 恰 6 次投递、缺 sessionID 不投、烟花开时 bubbleText 照常产出）；实现序核验（arm 在节流前、桥层无 if/else）。
- **TC-DONE 缩版实机**：04 真实 e2e——`opencode run` 纯文本生成 4.36s **零阻塞**（delta 高频链路上 §九修复的运行时证据）、宠物帧活性 A/B 交替、退出干净；05 DB 侧对账（今日 12 会话 $0.037079，对账单测 ≤0.01 USD 断言过）；06 实机烟花——fireworks 窗口 4s hide、`dismissed_via=fireworks` 记账无双写、用户 DB 备份恢复 md5 一致；07 实机重启 app_state 全保留（含宠物位置/语言/选择）。
- **HTTP 契约顺带**（TC-EV-11/12）：401/400/200/404 全符合。
- **PENDING-USER 4 项**（tester 无视觉通道）：TC-EV-27/DONE-04 姿态目视（thinking ≥4s、不闪 idle、结束 ≤10s 回 idle，完整 30 分钟版同此）；DONE-05 面板 UI 数值比对；DONE-06 烟花+气泡叠加目视；TC-APP-14 下拉刷新 GUI 验证。
- **SKIPPED**：TC-CI-05（需 push）、Windows 矩阵、版本 bump、draft 处置、tag 发版。
- 环境恢复：进程 0 残留、DB md5 一致恢复、仓库零测试残留、git 全程只读。

#### 8.5.3 committer 评审（2026-08-22，reviewVerdict: APPROVED）

- **P0/P1 = 0**；P2×2、P3×7（记录级）。可进入 commit / 发版流程。
- 重点量化核验通过：**三机制无饿死**——粘性窗过期后首个心跳最坏 ≤14s 到达（30s idle_timeout 余量 ≥16s）；连发消息极端场景由 speech 桶 20s 冷却承载活性（最长静默 20s < 30s）无误 idle。**idle 豁免无过载**（会话边界低频 + App 幂等覆盖）。**ThinkingSticky 无泄漏**。**无循环依赖**（reminders→todos 单向）。**Settings 双触发可靠**（Rust `show_panel` 必 `set_focus` → focus 必触发）。**零阻塞契约保持**（§九：同步前缀 µs 级、钉子用例双守护）。**i18n 完备**。**文档与实现一致**。
- **评审后已修**：P2-1（§8.4 两处索引错误 TC-CI-03→05、DESIGN §5.2→§5.1）+ P3-9（§8.1 四-4 行补 delta 主力载体）；链接校验 19/19 通过。
- 记录在案 P3（不处理）：短会话 idle 被吞（与旧行为等价非回归）；烟花先 dismiss 后点宠物的统计口径（既有行为）；桥层无自动化测试（与既有风格一致，纯函数已覆盖）；unlisten 注册间隙（无害）；`images/` 与 blog 草稿不入本次 commit。

#### 8.5.4 发版前置条件（交付把关）

1. **TC-CI-05**：push 后实跑 todo-lite + pulse-pet 双路径 CI（v4→v7 零实跑是唯一未验证面；失败回退 pin v4 单独评估）；
2. 版本 bump 0.1.2 → 0.1.3（`tauri.conf.json`）；
3. 4 项用户目视验收（§8.5.2 PENDING-USER，需在插件更新后**新起**的 opencode 会话中观察）；
4. 删除 v0.1.0 draft Release（七-1 已裁定丢弃）；
5. 发布说明**重点**提醒重跑 `install.sh`（插件副本不随 App 更新，§8.3/§九）。

### 8.6 后续维护版清单（0.1.x 线待办）

> v0.1.3 收尾后新发现的维护项落此处（0.1.x 线下一维护版承载；v2 期间发现的 v1 既有问题同样归此）。

| # | 事项 | 修法要点 | 来源 |
|---|---|---|---|
| 1 | **OBS-SIGTERM**：外部 kill（SIGTERM）不产生 `exit` 日志行（排障口径「有 exit 行 = 干净退出」失效），runtime token/endpoint 残留不清理（下会话启动才被覆盖；窗口期内 endpoint 仍可被旧 token 命中） | **SIGTERM 退出钩子**：注册信号处理器 → ①补写 `exit` 日志行（标注信号来源）②清理 runtime 目录的 token/endpoint ③**Windows 分叉说明**：Windows 无 SIGTERM，需走 console 事件（`SetConsoleCtrlHandler`）或 Tauri window close 事件路径，实现时分叉处理并注明验证口径 | task-pulsepet-v2-polish / v2-m6 OBS-SIGTERM（2026-08-27 记录；本轮只落文档不改代码） |

---

## 九、已修复严重缺陷：插件钩子同步阻塞宿主 opencode（2026-08-22）

> 定级：**0.1.x 线迄今最严重缺陷**——插件设计缺陷（非 opencode 缺陷），症状为宿主 opencode 全面卡顿。潜伏自 M2 插件诞生，2026-08-22 首次显性爆发并当日修复。
> 状态：**已修复 + 回归保护落地**（改动在 develop 工作区，未提交）；真实会话双场景验证待用户反馈（9.6）。

### 9.1 症状（2026-08-22 用户报告）

| # | 症状 | 触发 |
|---|---|---|
| 1 | 发送消息回车后，消息数秒不显示（偶发强度不同） | 每次发消息 |
| 2 | 所有工具调用（read/write/edit 等）执行缓慢 | 每次工具调用 |
| 3 | 权限弹窗出现前卡顿，点允许后续卡顿 | 每次权限询问 |
| 4 | 时快时慢；回退 opencode 1.18.21→1.18.19 无效；一度怀疑模型问题 | 退避指数/队列瞬时状态决定强度 |

共同前置条件：**PulsePet App 未运行**（`~/.pulsepet/runtime/` 无 endpoint/update-token 文件）。App 运行时无任何症状（成功投递使退避持续复位）——这正是"之前没遇到"的原因。

### 9.2 根因（源码级证据链；opencode v1.18.19 实测，1.18.21 相同）

**宿主侧**：插件钩子被同步 await 且无任何超时保护——

| 触发点 | 位置（v1.18.19） | 阻塞语义 |
|---|---|---|
| `chat.message` | `session/prompt.ts:999` | 用户消息**保存/推送 TUI 之前** await → 症状 1 |
| `tool.execute.before/after` | `session/tools.ts:106/121`（内置工具）、`175/208`（MCP 资源）、`402/420`（MCP 第三方工具） | **包夹**每次工具执行 → 症状 2；弹窗前 = before、点允许后 = after → 症状 3 |
| `command.execute.before` | `session/prompt.ts:1460` | slash 命令执行前 await |
| `event`（总线） | `plugin/index.ts:253-259` | 宿主侧 `void` 派发**不阻塞**（但旧插件在共享串行队列堆积退避，间接加重其它钩子） |
| `permission.ask` | v1.18.19 服务端无触发点（权限走总线 `permission.asked`） | 插件注册了但不生效，无风险 |
| 机制 | `plugin/index.ts:282-295` `trigger` 逐钩子 `yield* Effect.promise(...)` | 无超时；"钩子必须快"完全靠插件自觉（官方文档无警示，示例只 await 快速本地操作） |

**插件侧**：旧实现三个失误叠加——

1. 全部钩子 `await deliver(...)`，把宿主的同步等待传导进投递队列；
2. `postState` 用 `readFileSync(endpoint)` 读 runtime 文件，App 未运行时 ENOENT 抛错，与网络失败混为一谈；
3. 失败进 `await backoff.wait()`（1s→2s→5s→**30s 封顶**、失败不复位）且投递串行队列共享（P3-②）——一次"缺席"让后续所有钩子事件排在退避睡眠之后。

**爆发时序**：插件 2026-08-20 安装，App 停运时段症状累积；8-22 中午 runtime 目录清空后持续爆发。换 opencode 版本无效 = 阻塞源在插件而非 opencode/模型；"时快时慢" = 退避指数瞬时值（首次失败 0ms、其后递增，偶发感强、诊断成本高）。

### 9.3 主流设计对照（同类型遥测插件源码级调研，修复依据）

| 插件 | 热路径钩子内做什么 | 网络发送在哪 | 错误处理 |
|---|---|---|---|
| `@langfuse/opencode-observability-plugin`（Langfuse 官方） | 仅本地记账 | Langfuse SDK 后台批量导出 | `runHook` catchAll 全吞，仅日志 |
| `@langchain/langsmith-opencode`（LangChain 官方） | 写内存缓冲 | 仅 `session.idle` 时 `flush()`（天然允许延迟的时机） | 吞 |
| `@mastra/opencode`（Mastra 官方） | await 但 try/catch | 后台 | toast，错误不逃逸宿主 |

**公理**：热路径钩子（`chat.message` / `tool.execute.*`）零网络 I/O、错误不逃逸宿主、发送延迟到后台/idle 时机。钩子里合法 `await` 的只有变换型插件（改 output：命令转义、env 注入、消息 transform）。PulsePet 属纯观察型，适用全部约束；退避本身不是错，错在**退避睡眠发生在被宿主 await 的路径上**，且"下游缺席"被当作失败计退避（遥测语义应为"下游缺席→丢弃，永不伤害宿主"）。

### 9.4 修复内容（2026-08-22，双管齐下）

| # | 改动 | 文件 |
|---|---|---|
| 1 | 新增 `buildHooks(deliverer?)`：全部 6 钩子 **fire-and-forget**（不 await、不 return 投递 promise、内部吞错）；`default.server` 改 `async () => buildHooks()`；deliverer 可注入供单测 | `opencode-plugin/pulse-pet-hook.js` |
| 2 | `postState` 拆 `readRuntimeFile`：endpoint/update-token **ENOENT/空 → 返回 `null`**（App 未运行 = 快速通道，非错误）；网络/HTTP≥400 仍抛错走退避 | 同上 |
| 3 | `deliver`：结果为 `null` → 静默跳过（**不 reset、不消耗退避等级**） | 同上 |
| 4 | 头注补记根因与"零阻塞契约"（防未来维护者无意改回 await） | 同上 |
| 5 | `.d.ts` 同步：`buildHooks` 类型（钩子全部返回 `void`）、`postState` 返回 `unknown \| null` | `opencode-plugin/pulse-pet-hook.d.ts` |
| 6 | 测试 +4：① postState 空目录→null 且零请求；② null 不消耗退避等级（`nextDelay()` 仍 0）；③ deliver 永久挂起时钩子立即返回且分类/自忽略语义不变；④ **全部 6 钩子返回 `undefined` 且非 thenable**（防回归为 async/await 的不变量钉子，任何一种回归写法立即红） | `src/lib/plugin-hook.test.ts` |

行为差异（诚实记录）：fire-and-forget 后，PulsePet 刚启动瞬间理论上可能丢最早 1 条状态事件（对桌宠动画无实际影响，与 Langfuse/LangSmith 同语义）。

### 9.5 验证

- `npm test`：20 文件 / **225 用例全绿**（221 + 新 4）；`npx tsc --noEmit` 通过。
- node 冒烟（源文件 + `~/.config/opencode/plugins/` 安装副本）：App 未运行时 `postState` **2ms** 返回 null（旧实现此处抛错进退避）；6 钩子连发本体 **~1ms**。
- `./install.sh` 幂等重装，源/副本 md5 一致（`35c1f634…`），`opencode.jsonc` 无重复条目。
- 真实会话验证（步骤已交用户，待反馈）：① App 停运连续多发消息/工具/权限弹窗即时性；② App 运行状态推送无回归（thinking/editing 动画正常）。

### 9.6 残余风险裁定与后续事项

**裁定不修（2026-08-22，量级评估后用户裁定）**：

| # | 残余点 | 量级 | 裁定 |
|---|---|---|---|
| R1 | `deliver` 前置的 killswitch `existsSync`（`if (!kind) return` 早退在前，仅可分类事件到达；现网可分类事件均为低频状态跃迁） | ~1-5µs/次 | 不修；四-4 流式心跳落地后事件升频，届时实测再评估 TTL 缓存 |
| R2 | 后台队列内 `readFileSync`（同步 FS 跑在 opencode 事件循环上，但不在钩子路径，且被三桶节流约束频率） | ~10-100µs/次 | 不修 |

**后续事项**：

| # | 事项 | 状态 |
|---|---|---|
| 1 | 真实会话双场景验证（9.5 第 4 条） | 待用户反馈 |
| 2 | 随 v0.1.3 发布；发布说明**重点**提醒重跑 `install.sh`（插件副本在 `~/.config/`，不随 App 更新） | 待发版（§8.1 已列入） |
| 3 | 改动位于 develop 工作区未提交 | 遵循仓库约定，按需提交 |

---

## 附：v1 已清偿对照（简要备查）

- M2 同桶升级放行（M5 清偿）｜M3 P3 五条（M4 清偿）｜M1 fireworks 透明实测（M4 清偿）
- M4 P2②③④（M7 清偿）⑤（M5 清偿）⑥⑦ + M5 P2⑤⑥ + M6 P2②（M8 清偿）
- M5 P2①②③④（M6 清偿）｜M6 P2①（M6 R3 清偿）
- M7 P2①②④（M8 A1/A2/A3 清偿）③（回 spec 定案）
- M4 P2① cover_monitor 竞态（M8 A9 代码级清偿，实机确认归一.1）
- M8 过程项：productName 改名旧产物清理（方案 a）、README 行序表 P1 修复、时序图标题/校验串/编译期断言 P2×3、SIGTERM 说明等 P3 全闭环
