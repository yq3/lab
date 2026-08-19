---
taskId: task-pulsepet-m4
target: pulse-pet/
coderTaskId: ses_ff6f97ff3ffeNn0WreEwk4iEbm
testerTaskId: ses_ff649d6dbffe2kYZmZa6gmpDi5
committerTaskId: ses_ff608f5e9ffe8TnQVyqXIJ5yLC
status: approved
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 1bfc549
reviewedSha: 1bfc549
filesChanged: [pulse-pet/src-tauri/src/reminder_scheduler.rs, pulse-pet/src/fireworks/engine.ts, pulse-pet/src/fireworks/engine.test.ts, pulse-pet/src/lib/reminders.ts, pulse-pet/src/lib/reminders.test.ts, pulse-pet/src/lib/reminder-bridge.ts, pulse-pet/src/panel/Reminders.tsx, pulse-pet/src-tauri/Cargo.toml, pulse-pet/src-tauri/Cargo.lock, pulse-pet/src-tauri/src/lib.rs, pulse-pet/src-tauri/src/tray.rs, pulse-pet/src-tauri/src/windows.rs, pulse-pet/src-tauri/src/token_stats.rs, pulse-pet/src/lib/token-stats.ts, pulse-pet/src/lib/token-stats.test.ts, pulse-pet/src/panel/TokenStats.tsx, pulse-pet/src/pet/petStore.ts, pulse-pet/src/pet/petStore.test.ts, pulse-pet/src/pet/PetCanvas.tsx, pulse-pet/src/fireworks/Fireworks.tsx, pulse-pet/src/main.tsx, pulse-pet/src/panel/Panel.tsx, pulse-pet/src/styles/global.css]
endReason: null
createdAt: 2026-08-16T13:16:46+0800
updatedAt: 2026-08-16T18:06:23+0800
---

# task-pulsepet-m4: pulse-pet M4 提醒（气泡 / 烟花 / 调度器）

## 任务原文

在 `lab/pulse-pet/`（M3 已落地，HEAD=affe86a + 回 spec 39cddf1 已合入 develop，见 task-pulsepet-m3 检查点）开发 M4 提醒。依据 DESIGN.md §10.2 里程碑 M4、§5 提醒（调度器 / 气泡 / 烟花 / 数据模型）、TEST-CASES.md TC-RM 章节对应用例。开发分支 `develop_opencode`（coder 固定提交分支，提交前先同步 origin/develop）。

**M4 范围（DESIGN.md §10.2 + §5，1 周）**：
1. **Rust 侧调度器**（§5.1，`src-tauri/src/reminder_scheduler.rs` 或等价模块）：
   - Tauri 的 tokio runtime + `tokio::time::interval` 最简实现：每 1 分钟 tick，检查所有启用的提醒规则是否到点
   - **显式 `MissedTickBehavior::Skip`**（macOS 睡眠恢复不补发，TC-RM-02）
   - 规则持久化在 `pulsepet.db` 的 `reminders` 表（M1 已建，schema 与 DESIGN §5.4 一致，无需迁移）
   - 读表后做 in-memory 倒计时，避免每分钟查库；用户改设置后通过 Tauri command 通知调度器 reload（TC-RM-07）
   - 到点：发送 Tauri event `reminder://trigger` 给前端（含规则信息），前端决定渲染气泡还是烟花
   - 跨午夜窗口语义（TC-RM-06，C15）：`start_time > end_time` 视为跨日窗口——当前时刻在 `[start_time, 24:00) ∪ [00:00, end_time)` 内进入倒计时并触发；区间外不触发；非跨日规则不受影响
   - 同规则 3 分钟不重复（TC-RM-05）：`last_triggered_at` 判断
   - 暂停所有提醒（TC-RM-08）：全局暂停开关（托盘菜单项 + app_state 持久化），暂停期间任何提醒不触发，取消恢复
   - kind='todo' 语义预留：`interval_minutes=0` 非周期、仅触发一次（DESIGN §5.4 约定，todo 插件 M7 实现；M4 调度器消费该 kind 时不误重复触发即可，不实现 todo→reminders upsert）
2. **控制面板提醒配置 UI**（`src/panel/Reminders.tsx`，panel 已有 reminders tab 占位）：
   - 提醒规则 CRUD：增/改/删，字段按 §5.4（kind/label/interval_minutes/start_time/end_time/enabled/use_fireworks）
   - 内置模板：喝水（hydration）/ 休息（rest）/ 自定义（custom）；文案可配
   - 全局烟花开关（settings 或 reminders 页顶部，DESIGN §10.2"全局烟花开关 + 单条覆盖"；TC-RM-11：全局关 + 单条 use_fireworks=1 → 该条仍放烟花）
   - 修改后调度器 reload 生效（无需重启 App）；重启后规则保留（TC-RM-07）
3. **气泡渲染**（§5.2，复用 M3 Bubble 组件）：
   - 宠物头顶气泡，默认文案模板 `该喝水啦 💧` / `休息一下 ☕` / `站起来走走 🚶` 等，规则可配文案（TC-RM-14）
   - 8s 自动消失（TC-RM-03）；点击宠物"已确认"提前消失（TC-RM-04：`reminder_logs` 记 `acked_at`、`dismissed_via='bubble'`）
   - 文案净化同 §3.1/M3 规则：纯文本渲染，无注入执行，不展示原始路径/URL/secret 样式 token（TC-RM-15）
4. **烟花窗口 + canvas 粒子系统**（§5.3，`src/fireworks/Fireworks.tsx`，M1 窗口配置已就绪）：
   - 触发：规则勾选烟花模式或全局开关开（TC-RM-09/11）
   - 宠物位置为发射点，**绽放点固定为宠物当前所处屏幕（显示器）的中轴线上、高度为屏幕从上往下 0.3 倍处（中间偏上）**——绽放点 x = 该屏水平中心，y = 屏高 × 0.3；多显示器取宠物所在显示器计算（用户 2026-08-16 两次补充需求定案，已落笔 DESIGN §5.3 + TC-RM-09）
   - 3-5s 消散，粒子带渐变与拖尾（动漫"流光花瓣"质感）
   - canvas 粒子：~300-500 粒子、rAF 60fps、HSL 渐变 + alpha fade + 拖尾（叠加半透明）
   - 可断言部分（TC-RM-09）：fireworks 窗口显示（全屏透明置顶、无边框、无任务栏项）→ 3-5s 内自动 hide → 无重复 show、无残留帧；TC-RM-10：连续两次触发可复用（不残留上一帧、不报错）
   - **M1 遗留实测项**：fireworks 窗口透明在 M4 落地时确认（M1 时隐藏态未实测；macOS 侧按 M1 R3 经验：transparent + backgroundColor #00000000）
   - 目视验收项（不进自动回归，记录即可）：发射点位于宠物位置、粒子数 ~300-500、60fps 流畅
   - 音频：**本轮不做**（TC-RM-12 可选，M5 评估）
5. **提醒日志表**（§5.4，`reminder_logs`，M1 已建）：
   - 触发即写 `triggered_at`；点击确认写 `acked_at` + `dismissed_via='bubble'`；自动消失 `dismissed_via='auto'`（烟花路径记 `'fireworks'`）
   - 历史统计（喝水/休息次数）从 reminder_logs 聚合（TC-RM-13）
6. **托盘菜单补全**（M1 预留，tray.rs）："暂停所有提醒"菜单项（开关态，勾选/取消，TC-RM-08）

**M4 明确不做**：atlas 加载（M5）、穿透切换/拖拽/热键/右键菜单（M6）、todo 插件机制与 todo→reminders upsert（M7）、CI workflow 修改（§13）、Windows 实机验证（M8，TC-RM-16 仅代码级/文档级）、烟花音频（M5 评估）、限流豁免 /health（心跳引入时）、同桶升级放行语义（M5 前定案）。

## 需求确认

- [x] 用户已确认（确认后 status=implementing）——2026-08-16 用户确认：① M4 范围照执行；② 遗留事项并入（M3 P3 五条 + M1 fireworks 透明实测）认可；③ **coder 开工第一步：拉取远端 develop 最新代码到本地 develop_opencode 再开发**（用户明确指示，执行交付约定"coder 每次提交前必须先同步 origin/develop"）
- **2026-08-16 用户补充需求（已落笔 DESIGN §5.3 + TEST-CASES TC-RM-09，coder 禁改文档）**：① 烟花绽放点=宠物所处屏幕正中心；② **用户再次调整（2026-08-16 15:03）：绽放点改为宠物所处屏幕中轴线上、高度为屏幕从上往下 0.3 倍处（中间偏上）**——绽放点 x = 该屏水平中心，y = 屏高 × 0.3，多显示器取宠物所在屏。coder 需在 f85aa78 基础上完善实现并重新验证。
- 历史遗留事项清单（supervised-coding 扫描 task-pulsepet-m1/m2/m3 检查点汇总，默认并入本任务，见 README §4.6）：

## 遗留事项（跨任务移交）

- [ ] **M3 新移交 P3 五条（来源 task-pulsepet-m3，committer R1，2026-08-16，明确"随 M4 顺带清偿"）**：
  - ① 摘要计数偏差（token-stats "12测"实为 9、token_stats.rs "20单测"实为 18+1 ignored，后续报告注意精度）
  - ② fetchCurrentSession/token_stats_current_session 死代码（spec §4.2 要求暴露，TS 封装未消费，M4 接入或删除）
  - ③ parseStatsError 无单测（错误态 UI 关键路径，补纯函数单测）
  - ④ token_stats_opencode_path 返回 Option vs DESIGN Result 签名微偏（对齐或注明）
  - ⑤ schema-mismatch 提示"请升级 pulse-pet"文案冗余（出现两次，去重）
- [ ] **M1 轮次记录待办（来源 task-pulsepet-m1 R3/R4）**：fireworks 窗口透明实测（M1 时隐藏态未独立实测，M4 落地 fireworks 时确认透明 + 内容渲染）
- [ ] 继续移交（不并入 M4，去向注明）：限流豁免 /health 评估（心跳引入时）；同桶升级放行语义（M5 前定案）；install.ps1 BOM / classifyEvent permission.asked（M8 收尾）；Windows 实机验证（M8）

## M4 遗留事项（已清偿 / 新移交，2026-08-16 R1 双通过后更新）

- [x] **M3 P3 五条（来源 task-pulsepet-m3，2026-08-16 清偿）**：① 计数精度实跑一致；② fetchCurrentSession 前端删除、Rust command 保留注册（spec §4.2 合规）；③ parseStatsError +6 单测；④ token_stats_opencode_path → Result<Option<PathBuf>,String> 对齐 DESIGN §4.2；⑤ "请升级 pulse-pet" 仅 Rust 侧一处。tester 逐条 PASS。
- [x] **M1 fireworks 透明实测（来源 task-pulsepet-m1 R3/R4，2026-08-16 清偿）**：播放中 vs 播放后 10/16 探针区 0 像素差异（透明）+ 内容渲染 ~9.4 万差异像素。tester PASS。
- [x] **回 spec 落笔（2026-08-16 用户确认，supervised-coding）**：DESIGN §5.3 绽放点=宠物所在屏中轴+屏高×0.3（用户两次补充定案）+ 屏高取整屏物理高度（用户确认维持整屏）+ 全局烟花 OR 语义；§5.1 暂停顺延语义 + 试一试语义；§5.4 时间戳 RFC3339 本地字符串；§12 多屏实机 M8 注记。共 5 处 DESIGN（+TEST-CASES TC-RM-09 绽放点口径）。
- [ ] **M4 新移交（2026-08-16，committer R1 P2 七条不阻断）**：① cover_monitor 后回读 outer_position 竞态（仅多屏首切影响，M8 多屏实机时改直接用 monitor bounds 计算）；② Reminders.tsx ruleToForm 把 todo 降级为 custom（M7 接入时处理）；③ validate_input 允许 todo kind+interval>0（M7 upsert 强制 interval=0）；④ 播放中被打断时旧 log dismissed_via 残留 NULL（M7/M8 前可选补报）；⑤ Panel.tsx settings 占位文案"烟花全局开关 — M5/M6"陈旧；⑥ Reminders.tsx:211 .catch 静默吞开关写失败；⑦ ready 握手晚于 play 2.7s+ 时 watchdog 截断 pending 补发（触发概率极低）
- [ ] **M4 引入项（去向注明）**：多显示器烟花绽放点实机验证 + cover_monitor 竞态修复（M8）；烟花音频评估（M5）

## 验收标准（对应 TEST-CASES.md）

- **TC-RM-01 调度器整点语义**：配置每 30 分钟喝水提醒 → 到点触发（`reminder://trigger` → 前端渲染气泡）；间隔正确；未到点不触发
- **TC-RM-02 睡眠恢复不补发**：调度器显式 `MissedTickBehavior::Skip`；睡眠跨过多个 tick 唤醒后不瞬间连弹，错过不补发
- **TC-RM-03 气泡展示与自动消失**：触发 → 宠物头顶气泡（默认文案如"该喝水啦 💧"）；8s 自动消失
- **TC-RM-04 点击确认提前消失**：触发 2s 时点击宠物 → 气泡立即消失；`reminder_logs` 记 `acked_at`、`dismissed_via='bubble'`
- **TC-RM-05 同规则 3 分钟不重复**：立即再次触发 → 3 分钟内不重复；3 分钟后再触发正常
- **TC-RM-06 跨午夜窗口**：`start_time=22:00, end_time=06:00` 仅 [22:00,24:00)∪[00:00,06:00) 内触发；非跨日规则不受影响
- **TC-RM-07 规则 CRUD 与持久化**：panel 增/改/删 → 写 `reminders` 表；重启保留；删除不再触发；修改后 reload 生效无需重启
- **TC-RM-08 暂停所有提醒**：托盘"暂停所有提醒"开启 → 到期不触发；取消后恢复
- **TC-RM-09 烟花模式触发（可断言部分）**：fireworks 窗口显示（全屏透明置顶、无边框、无任务栏项）→ 3-5s 内自动 hide → 无重复 show、无残留帧
- **TC-RM-10 烟花结束后可复用**：连续触发两次 → 第二次正常重新播放，不残留、不报错
- **TC-RM-11 单条规则覆盖全局开关**：全局关 + 单条 use_fireworks=1 → 该条放烟花；其它规则仅气泡
- **TC-RM-12 烟花音频**：本轮不做（M5 评估）
- **TC-RM-13 提醒日志与历史统计**：`reminder_logs` 逐条记录（triggered_at/acked_at/dismissed_via）；喝水/休息历史次数聚合正确
- **TC-RM-14 自定义提醒文案**：custom 规则自定义文案 → 气泡显示；同样过净化
- **TC-RM-15 提醒文案净化**：文案含 `<script>`/markdown 链接/敏感字符 → 纯文本渲染无注入；不展示原始路径/URL/secret 样式 token
- **TC-RM-16 烟花窗口 Windows 兼容**：代码级/文档级（Windows 实机 M8；回退方案记录于 DESIGN §12）
- **M1 遗留实测**：fireworks 窗口透明 + 内容渲染实测（macOS，参照 M1 R3 透明窗口经验）
- **M3 遗留 P3 五条清偿验收**：②死代码删除或接入（前端无调用方则删，Rust command 按 spec 保留）；③parseStatsError 单测补齐；⑤文案去重；①④报告精度/签名对齐
- 回归基线：npm test（M3 85 项 + 新增模块单测）全通过；cargo test（M3 58 项 + 1 ignored + 新增调度器测试）全通过；npm run build / tauri build 成功

## 轮次记录

- R1: committer 审查 **APPROVED**（reviewedSha=1bfc549）。评审对象核对：三方 SHA 一致（HEAD=testedSha=1bfc549）、基线 origin/develop(068b270) 已 fetch 且 d5cc96d^=068b270（M4 三提交干净叠放 3 ahead）、改动 23 文件 3457+/44- 与 filesChanged 一致全在 pulse-pet/ 内、Cargo 仅 +tokio(time)/+chrono（Tauri 依赖图内无新下载）、无新增 npm 依赖、工作区 DESIGN/TEST-CASES 文档改动与实现一致。需求对应性：TC-RM-01~16 逐条有实现+测试+验证（调度 in-memory 倒计时/dedup 2:59✗3:00✓ 边界/跨午夜 6 断言/暂停顺延精确恢复/绽放点纯函数 x=mon 中轴 y=mon_h×0.3 三屏数值断言/OR 语义/petStore fake timers 8s 全时序）；M3 P3 五条清偿合规（②TS 死代码删除全仓 grep 无残留、Rust command 按 spec §4.2 保留；③parseStatsError 6 用例；④Result 签名对齐；⑤文案去重）；不做项零预实现。**无 P0/P1**。P2 七条（不阻断）：① cover_monitor 后回读 outer_position 竞态（仅多屏首切影响，单屏 no-op 无竞态；M8 多屏实机时改直接用 monitor bounds 计算消除窗口回读）；② Reminders.tsx ruleToForm 把 todo 降级为 custom（M7 前无 todo 规则 latent，M7 接入时处理）；③ validate_input 允许 todo kind+interval>0（M7 upsert 应强制 interval=0）；④ 播放中被打断时旧 log dismissed_via 未回报残留 NULL（watchdog 兜底同）；⑤ Panel.tsx settings 占位文案"烟花全局开关 — M5/M6"陈旧（实际已落地 reminders 页）；⑥ Reminders.tsx:211 .catch(()=>{}) 静默吞开关写失败；⑦ ready 握手晚于 play 2.7s+ 时 6.5s watchdog 可能截断 pending 补发（触发概率极低）。已核验无问题：锁序无死锁、SQL 全参数化、dismissed_via 白名单、ack/dismiss 防覆盖、事件路由门控、定时器互斥。测试质量：真实行为断言非空转；计数复核 TS 123（13 files）与 tester 精确一致、Rust 80 #[test]（79+1 ignored）与 tester 一致（M3 58+1→+21）、1bfc549 相对 f85aa78 恰 3 文件与提交说明一致；cargo/npm 复跑受限采信 tester。观察项裁定：① cover_monitor 竞态=P2 M8 修复不阻塞；② **"屏高"语义=需求边界问题→回 spec**（实现取 Monitor.size() 整显示器物理高度，实测 y=574=0.3×1912 自洽，若用户观感按可视区需 DESIGN 定公式）；③ 全局烟花 OR 语义→回 spec（全局开未勾选规则也升级，无豁免机制，panel 文案已明示）；④ 暂停顺延语义→回 spec（暂停到期顺延、恢复按顺延点不补弹）；⑤ 时间戳 RFC3339 本地字符串→回 spec（schema TEXT 未定格式）；⑥ 试一试语义→回 spec（受暂停+3min 去重、跳过窗口/倒计时、触发后推进 last_triggered_at 顺延下一自然点）；多屏实机 M8。**回 spec 建议 5 条（②③④⑤⑥）+ 多屏实机 M8 注记，其中②最可能影响用户观感（菜单栏 66px 使绽放点实际落在可视区 ~27.5% 处），建议优先向用户确认**。**交付把关：放行**（HEAD 三 SHA 一致、基线同步、无越界、证据完整；回 spec 由 supervised-coding 落笔）。
- R1: tester 验证 **PASS**（testedSha=1bfc549）。环境：macOS arm64 真实 GUI 会话，单屏物理 2940×1912（dpr2 逻辑 1470×956），理论绽放点 (1470,573.6)，被测 commit 1bfc549（HEAD 一致），origin/develop 同步 OK。自动化基线全实际复跑：npm test 123/123（13 files）、cargo test 79 passed/1 ignored、npm run build 成功（339ms）、npm run tauri build 成功（.app+.dmg）。**TC-RM-01~16 逐条**：01 调度整点 PASS（注入 last=now-29.5min → next_due 16:42:49 → 实际 16:43:39.804 触发，间隔内不二次触发，OCR 捕捉气泡）；02 睡眠恢复不补发 PASS（MissedTickBehavior::Skip 代码级 + compute_next_due 顺延单测 + 实测重启不补弹）；03 气泡 8s 自动消失 PASS（OCR 三次捕捉 + 消失 + db dismissed_via='auto' 12 条）；04 点击确认提前消失 PASS（CGEvent 点击 → 0.5s 消失，log 27 triggered_at/acked_at/dismissed_via='bubble' 三字段齐全）；05 3min 去重 PASS（真实时间路径：16:51:14.283 首触 → 16:52:14 拦截 → 16:54:14.283 二次 → 16:57:14.298 三次；单测 2:59✗/3:00✓ 边界）；06 跨午夜 PASS（规则 17 跨日 22:00-06:00 到点不触发、对照规则 18 同时到点正常触发 17:20:26.493，6 边界断言单测）；07 CRUD+持久化 PASS（UI 增/改/删实测 + 落库 + reload 即时生效（改 interval 45 后按新值 17:00:14.306 触发）+ 重启保留 + 两步删除级联）；08 暂停所有提醒 PASS（AX 托盘菜单切换 → app_state reminders.paused 持久化 → 暂停期间两规则到点均不触发 → 取消后顺延点 17:18:38.699 精确恢复，CheckMenuItem+持久化代码核验）；09 烟花可断言部分 PASS（窗口配置核验 + show→hide 3.5-4s + show/hide 配对 2/2 无重复 + 结束帧粒子清零无残留）+ **绽放点量化（用户终版口径：中轴+屏高×0.3）**：位置 A（宠物左上 (100,66)）Rust target=(735,254) 逻辑（物理 574=0.3×1912 ✓），炸裂帧质心 (1428,607) offset(-41,+34) dist=54px、y bracket 573.6（568→607）、x 收敛中轴；位置 B（宠物右下 (2500,1400)）origin 跟随宠物 ✓，炸裂帧质心 (1409,610) dist=71px → **绽放点与宠物位置无关、固定屏中轴+0.3 屏高** ✓；粒子数 320-440+流光（单测 peak）、60fps rAF 帧序列连续；10 连续两次可复用 PASS（规则 19 两次触发 log 47/51 正常重播 hide+finished，0 error，engine.reset 清场）；11 单条覆盖全局 PASS（全局关 + 规则 19 use_fireworks=1 → 5 次全 fireworks（dismissed_via='fireworks'）；规则 15/16/18 同期全气泡（'auto'）；OR 语义单测）；12 音频按范围不做（记录）；13 日志+统计 PASS（triggered_at 触发即写/acked_at 点击写/dismissed_via 全路径实测 + stats 聚合单测 hydration 2/rest 1 + panel 统计 UI 核验）；14 自定义文案 PASS（custom 规则文案 OCR 显示）；15 净化 PASS（<script>/URL/密钥 sk-…/路径 脱敏为占位符纯文本渲染、0 JS 错误、17 单测）；16 Windows 代码级 PASS（回退方案注释+DESIGN §12 记录，实机 M8）。**M1 遗留 fireworks 透明+内容渲染 PASS**：播放中 vs 播放后 diff 分布 10/16 区域 0 差异（透明不遮挡桌面）+ 粒子内容 ~9.4 万差异像素。**M3 P3 五条清偿 PASS**：① 计数精度实跑一致；② fetchCurrentSession 前端 grep 仅注释无调用、Rust command 保留注册（spec §4.2 合规）；③ parseStatsError 6 用例；④ token_stats_opencode_path Result<Option<PathBuf>,String> 与 DESIGN §4.2 对齐；⑤ "请升级 pulse-pet" 仅 Rust 侧 2 处、TokenStats.tsx 不再拼接。**确认缺陷无（P0/P1/P2 均无）**。观察项 4：① compute_play_payload cover_monitor 后立即读 outer_position 存在异步竞态（单屏实测结果正确，多屏跨屏移动坐标读取时序 M8 实机确认）；② "屏高"语义=整显示器物理高度（含菜单栏，1912×0.3=573.6 与实测一致），DESIGN 未细分可视区口径（待 supervisor 定案）；③ 托盘图标无法 CGEvent 点击（AX menu bar 2 驱动，测试工具限制非产品缺陷）；④ UI 类型下拉无法 AX 操作，kind=custom 经 db 调整完成 TC-RM-14（前端代码/校验单测覆盖）。环境恢复：进程干净、测试规则 13-19 已删、用户规则 11+log 21 保留、全局烟花开关恢复 1、pet 位置恢复 (100,-440)、paused 恢复 0、工作区仅预期文档修改。
- R1: coder 完成，commit `d5cc96d`（`[task-pulsepet-m4] R1: M4 提醒——Rust 调度器(tokio Skip/跨午夜/3min去重/暂停/todo一次性)+气泡确认回报+烟花窗口粒子系统+面板Reminders CRUD/全局烟花开关/统计+托盘暂停项；清偿M3 P3②③④⑤；运行时E2E实测`，分支 develop_opencode，提交前已 git fetch + merge origin/develop 同步）。改动：23 文件（新增 7：reminder_scheduler.rs（tokio interval+Skip、in-memory 倒计时、跨午夜窗口、3min 去重、暂停顺延、todo 一次性、13 个 Tauri command、19 单测）、fireworks/engine.ts（纯逻辑粒子引擎：上升流光+320-420 花瓣炸裂、HSL 渐变/摇曳/alpha fade、峰值 300-500、硬上限 5s、reset 复用）、engine.test.ts、lib/reminders.ts（类型/模板/净化 URL/路径/secret 脱敏/校验/触发事件解析/命令封装）、reminders.test.ts、reminder-bridge.ts（pet 窗口事件桥）、panel/Reminders.tsx（规则 CRUD、两步删除确认、全局烟花开关、模板、试一试、历史统计）；修改 16：lib.rs（调度器接线+13 命令）、tray.rs（暂停所有提醒 CheckMenuItem+持久化）、windows.rs（show/hide_fireworks）、token_stats.rs（P3-④ 签名对齐）、token-stats.ts（P3-② 删 fetchCurrentSession）、token-stats.test.ts（P3-③ +6 测）、TokenStats.tsx（P3-⑤ 文案去重）、petStore.ts/petStore.test.ts（气泡 logId+ack/auto 回报 +5 测）、PetCanvas.tsx（点击优先 ack 提醒）、Fireworks.tsx（canvas 渲染+play/ready/finished 编排）、main.tsx、Panel.tsx、global.css、Cargo.toml/Cargo.lock（+tokio(time)/chrono 依赖图内缓存无新下载））。自测证据：npm test 121/121（13 files，基线 85→+36）、cargo test 77+1 ignored（基线 58+1→+19）、npm run build 成功（327ms）、tauri build 成功（.app+.dmg）；运行时 E2E（PULSEPET_REMINDER_TICK_MS=2000 tauri dev，真实 GUI+AX/CGEvent）：TC-RM-01 到点触发（reminder://trigger 前端渲染）、TC-RM-03 8s 自动消失 dismissed_via='auto'、TC-RM-04 点击宠物 acked_at+dismissed_via='bubble'、TC-RM-05 三次触发精确 3min 门控（14:05:59→14:08:59→14:11:59）、TC-RM-07 CRUD+落库+试一试 reload 即时生效+重启保留+两步删除级联、TC-RM-08 托盘暂停拦截+恢复、TC-RM-09 fire→hide 3.59s∈[3,5] 每轮恰一次 show/hide、TC-RM-10 连续 5 轮重播无残留、TC-RM-11/13/14/15 单测+日志字段实测+净化渲染；M1 遗留 fireworks 透明实测：烟花播放中 vs 播放后探针区 0/120000 像素差异（maxDelta=0）=透明，粒子渲染 70 万差异像素。遗留/裁定点：① E2E 发现修复 window.confirm 在 wry 无对话框（改应用内两步删除确认）+ 烟花 watchdog 冗余 hide 加可见性判断；② 语义定案待回写 DESIGN：全局烟花开关取 OR（单条勾选/全局开升级，TC-RM-11 只测单向）、暂停期间到期规则倒计时顺延（恢复后不补弹）、试一试（reminders_trigger_now）受暂停+3min 去重约束但跳过窗口/倒计时、时间戳统一 RFC3339 本地字符串（schema TEXT，DESIGN 未定格式）、trigger payload 含 fireworks_global/log_id；③ TC-RM-12 音频按范围未做（M5 评估）、TC-RM-16 Windows 代码级就绪实机 M8；④ 目视项（发射点=pet 中心单测断言、60fps）不进自动回归；⑤ 新依赖 tokio(time)/chrono 原依赖图缓存内无网络请求。E2E 截图在 /tmp/m4-*.png，测试数据已从用户 db 清理。
- R1: coder 完成（补充需求轮 2，用户 2026-08-16 二次调整：绽放点从"屏幕正中心"改为"中轴线 + 屏高 0.3 倍处（中间偏上）"，supervised-coding 已落笔 DESIGN §5.3 + TEST-CASES TC-RM-09），commit `1bfc549`（`[task-pulsepet-m4] R1: 烟花绽放点定案为中轴线+屏高0.3处（用户二次补充）`，基于 f85aa78，提交前已同步 origin/develop）。改动（相对 f85aa78）：reminder_scheduler.rs 纯函数重命名 monitor_burst_point_in_window + BURST_Y_RATIO=0.3 常量（y=mon_h×0.3），compute_play_payload 兜底路径/日志/注释同步；engine.ts 仅注释措辞（target 机制零改动，本就参数化无硬编码 y）；engine.test.ts 目标值 478→286.8、测试命名同步。自测证据：npm test 123/123（13 files）、cargo test 79+1 ignored（monitor_burst_point_in_window 断言：主屏 dpr2→(735,286.8)、次屏对齐→(735,286.8)、未对齐兜底→(4410,573.6)、兜底路径同步 0.3 系数）、npm run build 成功（337ms）、tauri build 成功；运行时实测（真实 GUI，物理屏 2940×1912，理论绽放点 (1470, 573.6≈574)）：宠物右下 (700,1000) → Rust 日志 target=(735,254) logical，绽放起始帧 y 568→609 bracket 住 574、x 随炸裂圆团收敛 -39→0（seq13 起趋 0），绽放起始总偏差 ≤42px（1.4% 屏宽）；宠物左上 (240,240) → 捕获帧为弹道拱点，bbox 中心 x=1474 中轴 offset≈0、y +35→+241 为花瓣重力下坠；逻辑→物理换算自洽（254×2+菜单栏 66=574=0.3×1912）。遗留/裁定点：① 多显示器未实测（单屏），代码级链路 current_monitor→cover_monitor→monitor_burst_point_in_window（次屏对齐用例断言与屏号无关），实机并入 M8；② **"屏高"语义**：实现取 Tauri Monitor bounds=整显示器物理高度（含菜单栏，1912×0.3=574）；若用户观感应按"可视区高度"（去菜单栏/Dock）计算，需 supervisor 回写 DESIGN 明确口径（当前文档未细分）；③ 用户数据保留：验证期间用户在面板自建规则"该喝水啦 💧"（30min 无烟花）+ 开启全局烟花开关——均已保留未清理；coder 测试规则/日志/pet 位置已清除；④ 测量帧与理论点 y 负偏（-6px 弹道弧线抬升混入）与正偏（+35px 花瓣下坠）均在截帧时序噪声内。文档改动（DESIGN/TEST-CASES）未纳入 commit，待交付时由 coder 回 spec 提交。
- **回 spec 落笔（2026-08-16 用户确认开始交付，supervised-coding）**：DESIGN §5.3 绽放点=宠物所在屏中轴+屏高×0.3（用户两次补充定案）+ **屏高取整显示器物理高度（用户确认维持整屏口径）** + 全局烟花 OR 语义；§5.1 暂停顺延语义 + 试一试语义；§5.4 时间戳 RFC3339 本地字符串；§12 多屏实机 M8 注记。共 5 处 DESIGN（+TEST-CASES TC-RM-09 绽放点口径，此前已落笔）。
- **交付执行（2026-08-16 用户确认）**：Coder 回 spec 提交 `ccf8c4a`（`[task-pulsepet-m4] R1: 回 spec 文档口径`，2 files +8/-2，DESIGN.md+TEST-CASES.md）→ 同步 origin/develop（0 behind）→ SSH 推送成功（39cddf1..ccf8c4a）→ 开 PR：**https://github.com/yq3/lab/pull/4**（base develop / head develop_opencode，title `[pulse-pet] M4 提醒：调度器/气泡/烟花/配置 UI/日志 + 遗留清偿`，body 8 节：摘要/验收结论（tester PASS+committer APPROVED，SHA=1bfc549）/TC-RM 通过摘要/回归基线（npm 123/cargo 79+1/build×2）/回 spec 5+1 处/Known Issues（P2 七条 M8 计划 + 多屏 M8 + 音频 M5）/Evidence Manifest 占位）。待：Committer gh pr review 留痕 → Coder 写 evidence manifest → 汇报合入请求。
- **交付执行（2026-08-16）**：Committer 已执行 `gh pr review` 留痕——**COMMENTED**（同账号 POC 约定，Review ID `PRR_kwDOTsiHgs8AAAABJszYLw`，2026-08-16T10:03:37Z）：正文五节（① 评审对象核对：4 提交链 d5cc96d→f85aa78→1bfc549→ccf8c4a、双 SHA=1bfc549、23 文件全在 pulse-pet/、依赖 tokio(time)/chrono；② 回 spec 5+1 处逐条复核一致（§5.1 暂停顺延/试一试、§5.3 绽放点终版+整屏口径（用户确认记录一致）+OR、§5.4 RFC3339、§12 多屏 M8 注记、TC-RM-09）；③ R1 结论摘要 APPROVED 无 P0/P1；④ knownIssues 移交 P2 七条→M8 + 多屏 M8 + 音频 M5；⑤ 不自动合入声明）。manifest 占位待 coder 步骤 5 补写。PR 保持 OPEN。
- **交付执行（2026-08-16）**：Coder 已把 evidence manifest JSON 写入 PR description（`gh pr edit 4` + JSON.parse 校验通过）：12 顶层 key（taskId/milestone/headSha=1bfc549/specCommit=ccf8c4a/commits=4/verdicts（tester PASS+committer APPROVED 双 SHA）/testEvidence 7 键（npm 123/cargo 79+1/build×2/TC-RM 绽放点质心 dist 54/71px/透明 10/16 区 0 差异/P3 清偿）/acceptanceCriteria/knownIssues P2 七条+多屏 M8+音频 M5/specUpdates 5+1 处/environment/reviewers Review ID）。**交付三步全部完成，PR 待用户合入决定**：https://github.com/yq3/lab/pull/4
- **合入（2026-08-16 用户确认）**：PR #4 已合入 develop（merge commit `5bde16c`，`gh pr merge 4 --merge --delete-branch=false`，develop_opencode 分支保留）。**M4 任务完成，status=approved 终态。**（检查点随后提交推送 origin/develop）

## 最新验证意见原文

（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

### Tester R1 报告原文（2026-08-16，testVerdict=PASS）

# PulsePet M4 提醒功能 R1 验收报告（tester）

## 1. 环境
| 项 | 值 |
|---|---|
| 机器 | macOS（darwin，arm64）真实 GUI 会话 |
| 显示器 | 单屏物理 2940×1912（dpr=2，Retina；逻辑 1470×956），理论绽放点 (1470, 573.6) |
| 被测 commit | `1bfc549`（develop_opencode HEAD，M4 三次 R1 提交 d5cc96d → f85aa78 → 1bfc549 之上） |
| 同步状态 | `origin/develop`(068b270) 是 develop_opencode 祖先，同步 OK；工作区 HEAD=1bfc549 ✅ |
| 验证方式 | `PULSEPET_REMINDER_TICK_MS=2000` tauri dev（debug）+ 真实 GUI 截屏 + Vision OCR + CGEvent/AX 驱动（Swift 工具）+ 粒子质心像素分析 + SQLite 直查 |
| 测试数据 | 测试规则 13-19 均已删除；用户规则 id=11"该喝水啦 💧"、全局烟花开关、pet 位置 (100,-440) 全部恢复原值 |

## 2. 自动化基线（全部实际复跑）
| 命令 | 结果 |
|---|---|
| `npm test` | ✅ **123 passed (123)，13 files**（与预期基线一致） |
| `cargo test` | ✅ **79 passed; 0 failed; 1 ignored**（与预期基线一致） |
| `npm run build` | ✅ tsc + vite 构建成功（339ms） |
| `npm run tauri build` | ✅ release 构建 + bundle 成功（pulse-pet.app + .dmg） |

## 3. TC-RM 逐条结论
**TC-RM-01 调度器整点语义 — PASS**：规则 13（30min）注入 last=now-29.5min → 重启 → next_due=16:42:49，实际触发 16:43:39.804（误差 <1s）；触发后 next_due=+30min，间隔内 10s+ 多 tick 无二次触发；前端渲染气泡（OCR 捕捉 pet 头顶"测试30分钟"文本）。
**TC-RM-02 睡眠恢复不补发 — PASS（代码级+单测）**：spawn_scheduler 显式 MissedTickBehavior::Skip（reminder_scheduler.rs:738）；compute_next_due 对已过期 cand 顺延 now+interval 不回溯补发（:199-203，单测 next_due_never_triggered_anchors_at_created）。实测多次印证重启后已过期规则均顺延不补弹。
**TC-RM-03 气泡展示与自动消失 — PASS**：触发 → 气泡渲染（OCR 三次捕捉"测试30分钟"）；8s 后消失 + db dismissed_via='auto'（log 25/28/29/30 等 12 条）。
**TC-RM-04 点击确认提前消失 — PASS**：触发 2s 时 CGEvent 点击 pet 中心 (210,176) → 气泡立即消失（0.5s 后 OCR=0）+ db log 27 triggered_at=16:49:40.420, acked_at=16:49:43.249, dismissed_via='bubble' 三字段齐全。
**TC-RM-05 同规则 3 分钟不重复 — PASS**：真实时间路径规则 14（interval=1）首触发 16:51:14.283 → next_due 16:52:14 被拦截 → 16:54:14.283（恰 3 分钟）二次触发（log 29）→ 16:57:14.298 三次；单测 dedup_window_three_minutes_tc_rm_05 覆盖 2:59✗/3:00✓ 精确边界。
**TC-RM-06 跨午夜窗口 — PASS**：运行时规则 17（22:00-06:00 跨日）到点不触发；对照规则 18（09:00-18:00）同时到点正常触发（17:20:26.493, log 36）。边界 21:59/22:00/23:59/00:00/05:59/06:00 由 Rust 单测 window_cross_midnight_boundaries_tc_rm_06 6 断言覆盖。
**TC-RM-07 规则 CRUD 与持久化 — PASS**：增（UI 表单 AX 驱动新建"UI-New-Rule"→ db 落库规则 15）；改（UI 编辑规则 13 → label='UI-Rule-45'、interval 30→45 写库；reload 即时生效：注入 last 后编辑保存 → 按新 interval=45 在 17:00:14.306 精确触发）；删（两步确认删除规则 14 → 级联删 logs 归零 → 删除后不再触发）；重启保留（多次重启后 11/13/15 均保留）。
**TC-RM-08 暂停所有提醒 — PASS**：AX 点击托盘菜单 → Rust 日志 reminders paused=true + app_state reminders.paused=1 持久化 → 暂停期间规则 16/15 到点均不触发 → 取消暂停 → 顺延点 17:18:38.699 精确恢复触发（恢复后不瞬间补弹语义同时验证）。tray.rs 核验 CheckMenuItem+toggle 翻转+持久化+勾选同步。
**TC-RM-09 烟花触发（可断言部分）— PASS**：窗口配置核验（transparent、backgroundColor #00000000、decorations false、alwaysOnTop、skipTaskbar、maximized）；show→hide 3-5s（帧序列 fwC_15 弹道 → fwC_17 炸裂 → fwC_22 消散 ≈3.5-4s）；无重复 show（show=2/hide=2 配对）；无残留帧（结束帧 fwC_35/fwD_35 粒子清零）。**绽放点量化（用户终版口径：宠物所在屏中轴线+屏高×0.3，理论 (1470,573.6)）**：位置 A（宠物左上 (100,66)）Rust target=(735,254) 逻辑（物理 574=0.3×1912 ✅）；炸裂帧 fwC_16 bbox y∈[399,540]、fwC_17 圆团质心 (1428,607)（offset -41,+34，dist=54px）→ 绽放起始 y bracket 573.6（568→607），x 收敛中轴（-41~+3）。位置 B（宠物右下 (2500,1400)）发射点 origin=(1360,777) 跟随宠物 ✅；炸裂帧 fwD_17 bbox x 中轴 ±92px、y bracket 573.6、fwD_18 质心 (1409,610)（dist=71px）→ **绽放点与宠物位置无关，固定屏中轴+0.3 屏高** ✅。粒子数 ~300-500（engine 峰值 320-440 花瓣+流光，单测 peak 断言）；60fps（rAF 帧序列连续性证明）。
**TC-RM-10 烟花结束后可复用 — PASS**：规则 19 自动连续两次触发 17:35:53.823（log 47）→ 17:40:53.826（log 51），第二次 show 正常重播、hide+fireworks_finished 正常，0 error/panic，无残留帧。engine.reset 清场 + Fireworks.tsx stopLoop/clearRect 复用路径。
**TC-RM-11 单条规则覆盖全局开关 — PASS**：全局关（0）+ 规则 19（use_fireworks=1）→ 5 次触发全部 fireworks（log 37/40/42/46/47 dismissed_via='fireworks'）；规则 15/16/18（use_fireworks=0）同期触发全部仅气泡（dismissed_via='auto'）。OR 语义单测 usesFireworks 覆盖。
**TC-RM-12 烟花音频 — 本轮不做（记录）**：M5 评估，范围外。
**TC-RM-13 提醒日志与历史统计 — PASS**：reminder_logs 逐条（triggered_at 触发即写毫秒 RFC3339、acked_at 点击写 log 27、dismissed_via ∈ {bubble,auto,fireworks} 全路径实测）；stats 聚合（Rust 单测 logs_trigger_ack_dismiss_and_stats_tc_rm_13 断言 hydration total=2 / rest total=1 + today）；panel 历史统计 UI（今日/累计）代码核验。
**TC-RM-14 自定义提醒文案 — PASS**：custom 规则文案"UI-New-Rule"→ 触发后气泡 OCR 显示自定义文案 ✅。
**TC-RM-15 提醒文案净化 — PASS**：规则 16 文案含 `<script>alert(1)</script> https://evil.example.com sk-1234567890abcdef /usr/local/bin/x 喝水啦` → 气泡 OCR 显示 `<script>alert(1)</script>［链…`（纯文本渲染无执行、URL 脱敏为占位符）；dev 日志 0 JS 错误；URL/密钥/路径脱敏正则 + 单测覆盖（reminders.test.ts 17 用例）。
**TC-RM-16 烟花窗口 Windows 兼容 — PASS（代码级/文档级）**：Fireworks.tsx 注释 + DESIGN §12（:646）记录回退方案（不透明+近桌面深色+自适应 alpha）；Windows 实机延后 M8（§12 :651）。

**M1 遗留（fireworks 透明+内容渲染实测）— PASS**：播放中帧 vs 播放后帧 diff 分布（4×4 cell）：粒子集中在中央 cell[5]=44318/cell[6]=49814（+顶部 cell[1][2] 弹道），其余 10/16 区域 0 差异 → 透明窗口不遮挡桌面 ✅；粒子内容渲染 ~9.4 万差异像素 ✅。

**M3 遗留 P3 五条 — PASS**：① 计数精度：本报告实测 npm 123（13 files）、cargo 79+1，与 coder 摘要一致（无虚报）；② fetchCurrentSession：前端 grep 仅注释残留，无调用方（已删）；token_stats_current_session Rust command 保留注册（lib.rs:157，spec §4.2 合规）；③ parseStatsError：token-stats.test.ts 含 6 用例（已知/未知 code、冒号保留、Error/对象、空输入）；④ token_stats_opencode_path() -> Result<Option<PathBuf>, String>（token_stats.rs:479）与 DESIGN §4.2 对齐；⑤ "请升级 pulse-pet" 仅 Rust 侧 2 处（token_stats.rs:144,155）；TokenStats.tsx 不再拼接（:42 注释确认）。

## 4. 缺陷清单与观察项
**确认缺陷：无（P0/P1/P2 均无）**
观察项（非缺陷）：① compute_play_payload 中 cover_monitor 后立即读 outer_position 存在异步竞态（本机读到窗口旧 y=66 而非 set 的 0）——单屏实测结果恰好使绽放点物理位置=理论 (1470,574)，行为正确；多显示器（窗口真正跨屏移动）场景坐标读取时序建议 M8 实机确认；② "屏高"语义：实现取整显示器物理高度（含菜单栏，1912×0.3=573.6），与实测一致；DESIGN 未细分可视区口径（coder 已标注，待 supervisor 定案）；③ 托盘图标无法用 CGEvent 点击（只能经 AX menu bar 2 驱动）——环境/测试工具限制，非产品缺陷；④ UI select（类型下拉）无法 AX 操作，kind=custom 经 db 调整完成 TC-RM-14（表单选择路径由前端代码/校验单测覆盖）。

## 5. testVerdict：**PASS**
TC-RM-01~16（除 12 按范围不做）全部通过；M1 遗留透明实测通过；M3 P3 五条清偿全部通过；回归基线 4/4 通过。

## 6. 环境恢复情况
进程：pulse-pet / tauri dev / vite 全部退出（pgrep 确认干净）；数据：测试规则 13-19 已删（含级联/孤儿日志清理）；用户规则 11 + 其 log 21 保留；全局烟花开关恢复 1；pet 位置恢复 (100,-440)；paused 恢复 0；工作区仅预期状态（DESIGN.md/TEST-CASES.md 的 supervised-coding 文档修改、检查点文件未跟踪），无测试残留文件；测试工具/截图均在 /var/folders 临时目录。

## 7. testedSha
**1bfc549**（git rev-parse HEAD = 1bfc5494d6d924c6d8259256160dfbbf5badd325）✅ 与检查点一致

### Committer R1 报告原文（2026-08-16，reviewVerdict=APPROVED）

# PulsePet M4 提醒功能 R1 — Committer 审查报告

## 1. 评审对象核对
| 项 | 结论 |
|---|---|
| 三方 SHA | ✅ 一致：HEAD=`1bfc5494d6...` = 检查点 testedSha `1bfc549`；工作区无代码改动（仅 DESIGN/TEST-CASES 文档改动，属 supervised-coding 落笔、交付时回 spec 提交） |
| 分支/基线 | ✅ develop_opencode，`origin/develop`（068b270）已 fetch 且 `d5cc96d^ = 068b270`，M4 三提交干净叠在 origin/develop 之上（3 ahead），未合入任何未同步上游 |
| 提交链 | ✅ d5cc96d（主体）→ f85aa78（补充需求①）→ 1bfc549（补充需求②终版绽放点） |
| 改动文件越界 | ✅ `origin/develop...1bfc549` = 23 文件、3457+/44-，与检查点 filesChanged 完全一致；全部在 pulse-pet/ 内，未触碰 CI/其它 App |
| 依赖变更 | ✅ Cargo.toml +tokio(time)/+chrono，二者本已在 Tauri 依赖图中（Cargo.lock 仅 pulse-pet 条目 + chrono 的 wasm 侧 js-sys 声明，macOS 构建无新下载）；无新增 npm 依赖 |
| 文档口径 | ✅ 工作区 DESIGN §5.3 / TEST-CASES TC-RM-09 改动与实现一致（绽放点=宠物所在屏中轴+屏高×0.3；Rust BURST_Y_RATIO=0.3、monitor_burst_point_in_window、engine 注释同步） |

## 2. 需求对应性逐项结论（TC-RM-01~16 + 用户补充）
TC-RM-01 ✅（in-memory 倒计时 load/reload 读表后按 next_due_ms 决策、collect_due 到点触发+推进，单测 collect_due_fires_when_due_and_advances；tester 实测 16:43:39 触发）；TC-RM-02 ✅（显式 MissedTickBehavior::Skip + compute_next_due 过期顺延单测 + tester 重启实测）；TC-RM-03 ✅（petStore armBubbleTimer 8s → dismissed_via='auto'；tester OCR+db 12 条）；TC-RM-04 ✅（PetCanvas 点击优先 ackReminderBubble（仅提醒气泡返回 true，否则回落 M1 状态轮换）→ reminders_ack（WHERE dismissed_via IS NULL 防覆盖）；tester CGEvent 三字段齐全）；TC-RM-05 ✅（dedup_ok + DEDUP_WINDOW_MS；边界单测 2:59✗/3:00✓；tester 真实时间 16:51→16:54→16:57）；TC-RM-06 ✅（in_window 分支语义 [start,24:00)∪[00:00,end)，6 边界断言；tester 规则 17/18 对照实测）；TC-RM-07 ✅（upsert/delete 命令内置 reload_state；compute_next_due 锚定 db last_triggered_at（reload 不重置）单测；tester UI 实测+改 interval 即时生效+重启保留）；TC-RM-08 ✅（托盘 CheckMenuItem 初始态从 app_state 恢复、切换翻转 st.paused+持久化+set_checked 同步；暂停期间 collect_due 顺延到期倒计时不补弹；tester AX 实测 17:18:38.699 精确恢复）；TC-RM-09 ✅（窗口配置核验 + show→hide 3.5-4s + 无重复 show/hide；绽放点 monitor_burst_point_in_window 纯函数 x=mon 中轴 y=mon_h×0.3，单测 (735,286.8)/次屏对齐同值/未对齐 (4410,573.6)；engine 弹道 target 参数化、getBurstPoint()==target 断言；tester 两宠物位置质心 x 收敛中轴 y bracket 573.6 偏差≤42px（1.4%）与宠物位置无关）；TC-RM-10 ✅（engine.reset 清场 + startPlay stopLoop + tester 规则 19 两连发无残留无报错）；TC-RM-11 ✅（usesFireworks OR（use_fireworks ∥ fireworks_global），payload 携带 fireworks_global，tester 全局关+单条开 5 次全 fireworks、其余全气泡）；TC-RM-12 ✅ 按范围不做（M5 评估）无预实现；TC-RM-13 ✅（触发即写 triggered_at、ack 写 acked_at、dismiss 三 via 全路径；stats 按 kind 聚合 today/total；tester db 实测+panel UI 核验）；TC-RM-14/15 ✅（custom 模板/自定义文案 + sanitizeReminderText（URL/路径/secret 脱敏 → M3 基础净化 → React 纯文本渲染），17 单测 + tester OCR 显示脱敏占位符、0 JS 错误）；TC-RM-16 ✅（代码级/文档级，实机 M8）；M1 遗留 fireworks 透明 ✅（tester 10/16 探针区 0 差异+内容渲染）；M3 P3 五条清偿 ✅（②TS 删除无调用方 fetchCurrentSession，Rust command 按 spec §4.2 保留，全仓 grep 无残留调用；③parseStatsError +6 单测；④token_stats_opencode_path → Result<Option<PathBuf>, String> 对齐 DESIGN 无 TS 调用方无破坏；⑤Rust message 已含"请升级 pulse-pet"，前端不再拼接；①计数见 §4）。不做项零预实现 ✅（diff 无 atlas/穿透/拖拽/热键/CI/音频痕迹；todo 仅 kind 消费语义 interval=0 一次性，无 upsert 机制）。

## 3. 代码质量要点
**P0：无。P1：无。**
**P2（建议）**：1. reminder_scheduler.rs:617-629 cover_monitor 后立即回读 outer_position/outer_size 的竞态（tester 观察项①）：set_position/set_size 生效前读到旧窗口 bounds 时，多屏首次切换会算错一次绽放点（单屏 already 短路无影响，故不阻塞）。建议 M8 多屏实机时一并修：cover 后直接用 monitor bounds 代替窗口回读（窗口==显示器，目标=(mon_w/2, mon_h×0.3)/sf、原点=(pet 中心−mon 原点)/sf），彻底消除对窗口位置读数的依赖。2. Reminders.tsx:51-61,149-156 ruleToForm 把 todo 降级为 custom：对 todo 规则做快捷开关/编辑会改写 kind 并丢 source_todo_id（interval=0 也会被表单校验拒绝）。M7 前无 todo 规则存在，latent；M7 接入时需处理（或本轮加只读分支）。3. reminder_scheduler.rs:387-396 validate_input 允许 todo kind + interval>0（spec 约定 todo 恒 0 一次性）；UI 无入口创建，M7 upsert 应强制 interval=0 或收紧此处校验。4. Fireworks.tsx + fireworks_finished 播放中途被新一场打断（如全局烟花开+多规则密集触发）时，前一场 log 的 dismissed_via 未回报，残留 NULL；watchdog 兜底路径同理。数据质量瑕疵，建议 finish/startPlay 切换时对旧 logId 补报。5. Panel.tsx settings 占位文案仍写"烟花全局开关 — M5/M6"，实际已落地在 reminders 页，文案陈旧（P3 同风格小项）。6. Reminders.tsx:211 .catch(() => {}) 静默吞掉全局开关写失败；showToast setTimeout 无清理（React 18 无害）。可留待后续。7. reminder_scheduler.rs:918-934 极端场景：ready 握手晚于 play 请求 2.7s+ 时，6.5s watchdog（play 时刻起算）可能截断 pending 补发场次的中段。实际 fireworks 窗口随 App 启动即挂载，触发概率极低。
**其它已核验无问题**：锁序（db→state 嵌套单向，无反向持有）无死锁；SQL 全部参数化、dismissed_via 白名单校验；ack_log/dismiss_log 均带 dismissed_via IS NULL 防覆盖；事件路由门控（hash 含 "pet" 才注册 bridge，"panel"/"fireworks" 均不含 "pet" 子串，无误命中）；定时器 ack/auto 互斥（clearBubbleTimer）；气泡被顶替按 auto 结案。

## 4. 测试质量结论 + 计数复核
测试是真的在测该测的：Rust 侧全部纯函数真实行为断言（窗口 6 边界、顺延不回溯、去重 2:59/3:00 边界、暂停顺延+精确恢复、todo 一次性跨 reload、CRUD 往返+校验拒绝、ack 不覆盖 auto、绽放点三屏场景数值断言）；TS 侧引擎炸裂点==target 逐帧断言、峰值区间、reset 复用、大 dt 钳制，净化脱敏逐类断言，OR 四值真值表，petStore 用 fake timers 走完整 8s 时序。无走过场测试。
计数复核（静态统计 vs tester 报告）：TS 13 个测试文件共 123 个 it/test —— 与 tester "123/123 (13 files)" 精确一致 ✓；Rust 共 80 个 #[test] 标记（reminder_scheduler 21 + token_stats 19 + http_server 18 + session_state 12 + db 4 + windows 4 + runtime 2）—— 与 tester "79 passed + 1 ignored = 80" 一致 ✓（M3 基线 58+1 → +21）；1bfc549 相对 f85aa78 恰 3 文件与提交说明一致 ✓；npm run build / tauri build / cargo test / npm test 我的 bash 仅放行只读命令复跑受限，采信 tester 实际复跑证据。

## 5. tester/coder 观察项逐条裁定
① cover_monitor 后回读竞态：真实但仅多屏首切影响（单屏 no-op 无竞态）。裁定 P2，M8 多屏实机时修复（方案见 §3-P2-1），本轮不阻塞；② "屏高"语义（整显示器 vs 可视区）：需求边界问题 → 回 spec。实现取 Monitor.size()（整显示器物理高度）；若用户观感按可视区（扣菜单栏/Dock）需 DESIGN 定公式。实现自洽、实测 y=574=0.3×1912 与当前口径一致，非代码 bug；③ 全局烟花 OR 语义：回 spec 确认。实现为 OR（全局开→未勾选规则也升级放烟花，无单条豁免机制），panel 文案已明示；DESIGN §5.3 "或"字与 TC-RM-11 只测单向不冲突，但"升级"与"是否有豁免"建议 DESIGN 落笔；④ 暂停顺延语义：实现与 coder 遗留②定案一致（暂停期间到期顺延、恢复后按顺延点触发不补弹，单测+tester 实测）。回 spec 落笔 DESIGN；⑤ 时间戳格式：RFC3339 本地字符串（chrono，schema TEXT），往返单测通过。回 spec 落笔 DESIGN（schema 未定格式）；⑥ 试一试语义：受暂停+3min 去重、跳过窗口/倒计时、触发后推进 last_triggered_at 与 next_due（会顺延下一自然触发点）。语义自洽，回 spec 落笔；多显示器绽放点实机：代码级链路完整（current_monitor→cover_monitor→纯函数，次屏对齐断言与屏号无关），单屏实测通过；实机验证按计划 M8。
**回 spec 建议清单（supervised-coding 落笔）**：②③④⑤⑥ 五条 + 多屏实机 M8 注记；其中②是最可能影响用户观感的一条（菜单栏 66px 使绽放点实际落在可视区 ~27.5% 处），建议优先向用户确认。

## 6. reviewVerdict
**APPROVED**
无 P0/P1；P2 均为非阻塞建议（含 1 项 M8 修复建议）；需求边界问题（屏高语义、OR 语义、顺延/时间戳/试一试语义定案）非代码问题，不构成 NEEDS_CHANGES，随交付由 supervised-coding 回 spec 落笔。

## 7. 交付把关结论
**放行**：最终 HEAD 1bfc549 三 SHA 一致、基线已同步（0 未合并上游）、23 文件无越界、文档口径与实现一致（交付时 coder 将 DESIGN/TEST-CASES 工作区改动回 spec 提交）、证据记录完整（检查点 R1 tester 报告含全部实测证据）。无 PR 需留痕（本任务走 develop_opencode 直提流程，无关联 PR；gh pr review 仅在有 PR 且用户确认交付后执行）。合入动作不经手，由 coder 在 spec 侧执行。未收到 CASE_BUG 裁定请求，本节无裁定结论。
