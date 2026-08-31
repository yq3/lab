---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-pulsepet-v2-m6
target: pulse-pet
coderTaskId: ses_fbe1152d9ffei3GJmPfbjYj1ZD
testerTaskId: ses_fbdf7608dffeWdd2Fnsr362iZ1
committerTaskId: ses_fbdb11dd4ffePsoum1WLXjbROu
status: approved
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 8973813da5fbe23baba93a09769995314a0b2de2
reviewedSha: 8973813da5fbe23baba93a09769995314a0b2de2
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [pulse-pet/src-tauri/src/session_state.rs, pulse-pet/src-tauri/src/http_server.rs, pulse-pet/src-tauri/src/lib.rs, pulse-pet/src-tauri/src/action_exec.rs, pulse-pet/src-tauri/src/token_stats.rs, pulse-pet/src/lib/bubble-queue.ts, pulse-pet/src/lib/bubble-queue.test.ts, pulse-pet/src/lib/token-stats.ts, pulse-pet/src/lib/http-bridge.ts, pulse-pet/src/lib/http-bridge.test.ts, pulse-pet/src/lib/tool-bubble-bridge.ts, pulse-pet/src/lib/tool-bubble-bridge.test.ts, pulse-pet/src/lib/reminder-bridge.ts, pulse-pet/src/lib/reminder-bridge.test.ts, pulse-pet/src/lib/reminders.test.ts, pulse-pet/src/lib/pet-menu.ts, pulse-pet/src/lib/pet-menu.test.ts, pulse-pet/src/lib/i18n.ts, pulse-pet/src/lib/i18n.test.ts, pulse-pet/src/pet/Bubble.tsx, pulse-pet/src/pet/PetMenu.tsx, pulse-pet/src/pet/todayToken.ts, pulse-pet/src/styles/global.css]
endReason: null
createdAt: 2026-08-27T14:17:21+0800          # 创建时间（30 天清理审计用，见 README §4.5）
updatedAt: 2026-08-27T21:17:54+0800          # 每次写检查点必更新为当前时间（ISO 8601 含时区），不得沿用旧值
---

# task-pulsepet-v2-m6: PulsePet v2 M6——多 agent × 多 session 抢镜 + 气泡 agent 标识

## 任务原文

用户原文（2026-08-27）："聚焦pulse-pet项目，开始V2版本M6阶段的开发任务"

实施 **V2-DESIGN §6（已终审定稿 2026-08-23：两轮评审 NEEDS REVISION → APPROVED WITH COMMENTS 全部采纳 + 用户终审"照单定稿"）**：M6 多 agent × 多 session 抢镜，落 M2 重构后的新气泡组件。

**权威文档**：
- 设计：`pulse-pet/docs/v2/V2-DESIGN.md` §6.0~§6.7（含 §6.7 两轮评审记录与终审记录）
- 范围：`pulse-pet/docs/v2/V2-SCOPE.md` §3.6（最近活跃优先 + 气泡 agent 标识 + M4 例程协同）
- 验收用例：`pulse-pet/docs/v2/V2-TEST-CASES.md` 六、TC-M6-01~06

**核心裁定（§6.0）**：活跃窗口 **10s**（对齐 opencode 流式心跳实际节奏——插件 reaction 桶 10s 冷却 → 生成中会话约每 10s 一事件；SCOPE 示例值 5s 太严会让生成中会话掉窗）；合并算法**两层**（①窗口内有事件的 session 间按既有优先级合并；②窗口空时显示最近活跃 session 的状态——不做全量优先级合并，陈旧 error 不复活抢镜）；气泡 agent 标识**前置等宽徽标 `[oc]`/`[cc]`/`[task]`**（token 汇报/工具播报携带；提醒不加——非 agent 来源）；悬停卡追加 **agent 分布行**「oc 39M · cc 3M」（双 agent 有数据才显示）。

**范围（按 V2-DESIGN §6.1~§6.3）**：

1. **合并算法（`session_state.rs` display() 改造，§6.1）**：
   - `display(&self)` → `display(&self, now: Instant)`（注入时钟保单测）；`ACTIVITY_WINDOW_MS = 10_000`
   - 两层算法：①活跃集 = sessions 中 last_event_at >= now - 10s；②活跃集非空 → 活跃集内 max_by_key(priority)（既有优先级表不变），**同 priority 平局取 last_event_at 最新者**（活跃集按 (priority, last_event_at) 取最大、fallback 按 (last_event_at, priority) 取最大——互为镜像字典序，防 HashMap 迭代序任意决定胜者致芯片 agent 无因跳变，P2-2）；③活跃集空 → 全量 sessions 中 last_event_at 最大者（平局取 priority 高者）；④sessions 空 → Idle（v1 语义）
   - **归属与兜底**：DisplayState.agent 取胜者 SessionRecord.agent（M1 §1.5 已备）；sessions 空 → Idle 时 agent 为空、前端芯片降级；无事件时的显示切换（掉窗让位瞬间）依赖既有 1s 后台循环 notify 兜底（延迟 ≤1s）——该循环对 M6 语义不可或缺，**注释防未来被优化掉（P3-6）**
   - **改造面**：生产调用点两处适配传 `Instant::now()`——DisplayNotifier::notify 与 lib.rs get_display_state 命令（P2-3）；tick 回收/瞬态超时/优先级表零改动
2. **气泡 agent 徽标（§6.2，P2-4 载体）**：
   - `agent` 是 **BubbleItem 新增可选字段**（M2 §2.6.2 结构本无，M6 新增）——随条目顶替回队/同源合并流转（**合并键不含 agent，徽标以幸存新条目为准**，P3-4）
   - 渲染在 Bubble.tsx 前置等宽小字（`[oc] `），i18n 不翻译（技术名约定）；task 映射 [task]
   - **徽标形态与 M5 会话列表无括号 oc/cc 刻意不同**（气泡=[oc] 终端习惯、列表=oc 列徽标），勿顺手统一（P3-2）
   - 四来源：token 会话汇报（opencode [oc] / CC [cc]，Rust pulsepet://bubble payload 补 agent——M1 事件已带透传 + M5 build_cc_idle_report 补字段）；工具级播报（双 agent [oc]/[cc]，**pulsepet://tool-bubble payload 补 agent**——/state 请求已带，http_server.rs 透传链路 M3 只透传 detail 本里程碑 +agent）；定时任务结果（[task]，payload 显式 agent:"task" 字段已隐含显式化）；提醒气泡（无徽标，非 agent 来源）
   - 三桥层（http-bridge.ts / tool-bubble-bridge.ts / reminder-bridge.ts）payload 解析 agent 传入条目
3. **悬停卡 agent 分布行（§6.2，M3 HoverToday 扩展）**：
   - `token_stats_today` 返回体**在 TodayStats 结构内追加 `by_agent: Vec<{agent, total}>`**（落 TodayStats 内非顶层——M5 N-4 包装 {today, degraded} 的 today 即此结构，P3-3；有数据的 agent 降序；**total 口径 = 今日总量同口径**——in+out+cacheRead、不含 reasoning、mock 过滤，三层数值交叉断言由此成立）
   - 悬停卡在总量+三行明细下追加一行 `oc 39M · cc 3M`（**单项时不显示**——单 agent 无辨识需求）；30s 缓存口径不变
4. **i18n**：少量键（悬停分布行标签 `token.hoverAgent` 等）；徽标不翻译；zh/en 键集合一致（完备性测试守护）
5. **已知边界（设计定案，实施照办）**：solo error 经 fallback 显示至 30s 回收 = 有意行为（P1-1 钉子）；waiting-permission 掉窗让位 = 接受 + 单测钉子（P2-5，终端弹窗本身持续可见）；窗口翻转显示交替仅双 session 事件交错时发生（R1 观察项，2s 滞回预设计不实现）

**数据库：零迁移。**

**不含（§6.3/§6.6）**：显示滞回（hysteresis）、气泡尾部/颜色标识、per-session 宠物、提醒气泡徽标、5s 窗口。

**开发纪律**：分支 develop_opencode（当前 ca2b600，落后 origin/develop（d2a8786）两笔文档提交，开工先 fetch + merge origin/develop）；提交信息 `[task-pulsepet-v2-m6] R<n>`；cargo 网络用 CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false；新代码日志一律 plog!（不新增 eprintln!）；每轮验证证据必含 tauri build 成功 + 产物时间戳；commit 前同步 origin/develop。

## 验收标准（V2-TEST-CASES 六、TC-M6-01~06 + V2-DESIGN §6.4）

- **TC-M6-01 两层合并算法（单测）**：①活跃集内优先级合并（双活跃 error>working）②同 priority 平局取 last_event_at 最新者（双 agent 同 kind，镜像字典序）③掉窗让位（A error 10s 前静默 + B working 2s 前 → B，核心修复）④窗口空 fallback 最近活跃（平局 priority 高者）⑤solo error 经 fallback 显示至 30s 回收（P1-1 钉子）⑥sessions 空 → idle（agent 空、芯片降级）⑦跨 agent 同权（opencode/claude-code/task）⑧伪 session 15s 心跳时序（手头静默期例程 working 连续显示不闪变、手头事件到达即夺回）⑨waiting-permission 掉窗让位钉子（P2-5）⑩既有 v1 display 断言修订（同刻事件行为等价、跨时刻注入时钟；1s notify 循环不可被优化掉注释钉）
- **TC-M6-02 双 agent 抢镜实测（实机）**：opencode + CC 双开并行 → 宠物随两侧事件切换归属（panel 芯片 agent 同步）；一侧 error 后静默 → ≤10s 让位另一侧（v1 抢镜问题消除）
- **TC-M6-03 气泡 agent 徽标（实机 + 单测）**：①token 汇报 [oc]/[cc]、工具播报 [oc]/[cc]（tool-bubble payload 补 agent）、任务结果 [task] ②提醒气泡无徽标（回归）③载体 = BubbleItem agent 字段随顶替回队/同源合并流转，合并键不含 agent 徽标以幸存新条目为准 ④前置等宽小字不翻译、与 M5 列表形态刻意不同 ⑤单测：agent 缺省不渲染徽标
- **TC-M6-04 悬停卡 agent 分布行（实机 + 单测）**：①双 agent 分布行降序、单项不显示 ②by_agent 落 TodayStats 内、total 同口径 ③三层数值与 panel 一致（M3 交叉断言延续）、30s 缓存不变 ④单测：单源单行/双源双行/零数据省略
- **TC-M6-05 M4 例程协同（实机）**：①例程执行中手头窗内持续有事件 → 手头状态优先（working(1) 压不过 editing/testing）②例程失败 × 手头持续活跃 → error ≤10s 让位（M4 R6 精化实证）③例程失败 × 无并发（或所有其他会话更旧）→ error 显示至 30s 自然回收（solo 边界）④手头静默期例程 working 连续显示（兜底不闪变）
- **TC-M6-06 回归目验（实机）**：重启后状态与芯片正常；三事件 payload 补 agent 向后兼容（同版本锁步）；显示交替仅双 session 交错（R1 观察项）；M6 新键 i18n 完备性（token.hoverAgent 等 zh/en 一致，徽标不翻译）
- 回归基线：npm test（vitest 386 基线 + 新增）全绿；cargo test（301+3 ignored 基线 + 新增）全绿；tsc 0；npm run build / tauri build（产物时间戳）成功；既有纯函数测试不破坏（display 断言按 TC-M6-01-⑩ 修订）

## 需求确认
- [x] 用户已确认（确认后 status=implementing）——2026-08-27 14:35 用户确认：M6 范围照 V2-DESIGN §6 定稿执行（多 agent 原则问题经讨论后用户裁定维持原设计）；流程级两点默认处置生效（遗留事项按清单 + TC-M6-02/03/05 实测走 HTTP POST 直打 /state 模拟双 agent 事件流、不触 INC 禁区）
- 历史遗留事项清单：（supervised-coding 扫描 task-pulsepet-v1~m8 / v2-m1~m5 检查点汇总，默认并入本任务，见 README §4.6）

## 遗留事项（跨任务移交）
- [x] **并入本轮：TEST_BUG real_db_reconciliation_manual（来源 task-pulsepet-v2-m5，原去向"下轮 coder 顺手修"即本轮）**：src-tauri manual 冒烟测试（ignored，不在 301+3i 基线内）参考 SQL 仍 DESIGN §4.1 旧口径（GROUP BY day,project_id + 全量 session），未随 M5 `GROUP BY day,agent,model_id`+mock 过滤更新——与 M6 改动面重合（token_stats.rs），本轮 coder 顺手修——**✅ 已清偿（2026-08-27，R1 commit 8973813；tester 单独执行 ignored 测试 ok + committer 口径核对一致）**
- [ ] **M6 新移交（2026-08-27 R1 双通过后 committer 定级，去向已注明）**：P3-① PetMenu clamp effect deps 仅 [pos] 首帧估值 130 不含子行——双 agent 日菜单增高 ~14px 贴下缘时底项被裁（**打磨轮**：deps 加 todayToken 或 ResizeObserver 或估值 146）；P3-② 文档滞后：V2-DESIGN §6.2/§6.3/§6.4 与 TC-M6-04 仍写悬停卡/HoverToday（**文档维护轮**，M5 d2a8786 先例；i18n 键名 hoverAgent 名实不符不改备注查）；P3-③ TC-M6-05 完全实机组合（真实例程×并发手头流同屏）+ OBS-PANEL panel 真机点击层（**用户人工目验批次**，与 TC-M5 实机缺口同批）；P3-④ (priority,last_event_at) 完全相等胜者依 HashMap 序（纳秒分辨率不可达，**记录备查**）
- [ ] **OBS-SIGTERM（来源 R1 tester 观察项，committer 定级）**：外部 kill 不产生 exit 日志行、runtime token/endpoint 残留不清理——v1 既有行为 M6 零改动面，**去向=V1-OPEN-ITEMS §八维护版清单**（随下个 v1 文档维护点落笔）
- 继续移交（去向已注明，不并入）：v2-m2 实机目验 7 项（TC-UI-01/03/06/07/10/11/12，待用户反馈）；TC-M5 实机验收缺口 4 项（TC-M5-08/09 实机 + TC-M5-05/06 实机触发，用户人工配合 per INC-20260827-1033）；v2-m2 P3-5（atlas.rs Clone 死代码，打磨轮）/ P3-6~10（CSS/微打磨轮/UX 观察项/M8 类 i18n 扩展）；v2-m5 committer P3×4（transcript.rs 注释重复/时区断言、TokenStats.tsx 注释过时、token_stats.rs 锁内解析观察项，打磨轮）；M4 P3①②③ + Windows 观察项（打磨轮/具备硬件时）；v2-m1 遗留 A~D（实机/目验/Release publish/观察项，原去向）；after-crash 库三件套留档至 2026-09-03 到期删；tester 沙箱资产 pp-m5-dom/（63 截图，人工复核后可清）

## 轮次记录
- R1: coder 完成（2026-08-27 15:00，coderTaskId=ses_fbe1152d9ffei3GJmPfbjYj1ZD），commit `8973813`（`[task-pulsepet-v2-m6] R1: 两层合并算法 display(now)（10s 活跃窗+镜像字典序平局+fallback 最近活跃）+ 气泡 agent 徽标（BubbleItem.agent 三桥层/三事件 payload 补 agent）+ by_agent 今日分布（TodayStats+菜单 sub 行，悬停卡移除后适配落点）+ reconcile manual SQL M5 口径顺手修`），基于 d2a8786（=origin/develop 最新，开工 fetch+fast-forward，commit 前确认无新提交）；23 files +961/−100；supervised-coding 已核验 HEAD=8973813、文件清单与 diff --stat 一致、工作区仅流程文件。改动：**session_state.rs**（display(now) 两层算法 ACTIVITY_WINDOW_MS=10_000 闭区间、镜像字典序 (priority,last_event_at)/(last_event_at,priority)、既有断言注入时钟修订 + TC-M6-01 十条钉子含 solo error 5/15/25/29s→30s 回收、15s 心跳时序、waiting-permission 让位）；**http_server.rs**（notify 传 Instant::now()、DetailHook (detail,agent)、集成测试 agent 透传断言）；**lib.rs**（display_state_dto 适配、1s 循环不可优化注释钉 P3-6、pulsepet://bubble payload 补 agent 双路径、idle_hook_body emit (agent,text)）；**action_exec.rs**（task_result_payload 显式 agent:"task" 纯函数+单测）；**token_stats.rs**（TodayStats +by_agent serde default、query_today_on 填充/today_stats_dual 合并降序、5 单测含 Σby_agent==今日总量交叉断言、**顺手修 real_db_reconciliation_manual SQL M5 口径**——v2-m5 移交 TEST_BUG 清偿）；**前端**（bubble-queue BubbleItem.agent? 合并键不含 agent 注 P3-4 + bubbleAgentBadge 缺省 null；token-stats TodayStats.by_agent? + agentShortName oc/cc/task；三桥层解析 agent 缺省容错；Bubble.tsx+global.css 前置等宽徽标 11px 弱化色与 M5 列表形态刻意不同；pet-menu/todayToken/PetMenu agent 分布行双 agent 才显示；i18n token.hoverAgent zh/en）。自测：cargo test **317 passed+3 ignored**（基线 301+3i +16）、npm test **405/28 files**（基线 386 +19）、tsc 0、npm run build ✓（391ms）、tauri build 成功（app @14:58:56 / dmg 4.7M @14:59:17）、cargo 0 warnings。TDD 红→绿记录四类：掉窗让位（7 红测 left:Error right:Working→绿）、平局镜像字典序（HashMap 序任意→显式元组比较+插入序反转钉）、solo error（5/15/25/29s Error→30s Idle）、徽标缺省不渲染（13 红→绿）。**裁定点①（需求边界适配，coder 报告）**：M6 设计对象 HoverToday.tsx 已被用户 2026-08-25 裁定移除（V2-DESIGN §3.3 留档「不作实施依据」，晚于 M6 定稿 08-23）——按后裁定优先：数据层照设计全量实现（by_agent 落 TodayStats/同口径/降序/零数据省略，TC-M6-04-2/4 单测绿），**呈现层适配到现存 pet 侧快捷查看点=右键菜单「今日 token」信息项子行**（单项不显示）；i18n 键按文档定名 token.hoverAgent 保留；TC-M6-04-1 实机目验面相应从悬停卡变为右键菜单。其余裁定点：② 实机项 TC-M6-02/03（实机）/05/06 按 INC 禁区口径由 tester HTTP POST 直打 /state 模拟；③ reconcile manual 按 INC 未实际运行仅编译验证；④ 窗口边界闭区间 >= now-10s（对齐插件 10s 心跳，单测钉住）。status=testing（待 tester）
- R1: tester 验证 **PASS**（2026-08-27 15:51，testerTaskId=ses_fbdf7608dffeWdd2Fnsr362iZ1，testedSha=8973813da5fbe23baba93a09769995314a0b2de2=HEAD，验证全程无新 commit、业务代码零改动）。报告全文见「最新验证意见原文」。摘要：TC-M6-01 十条钉子源码级逐条核验（测试名+行号+断言有效性评估，含边界闭区间附加钉）；基线独立复跑全一致（cargo 317+3i/npm 405/tsc 0/build ✓，tauri build 独立重建 app @15:16:34）；TC-M6-02/05 实机（HOME 重定向沙箱 + release 二进制 + HTTP POST 直打 /state 模拟双 agent 流 + screencapture + swift Vision OCR 本地脚本）——芯片五连拍实证归属切换、error 静默 13.3s>10s 让位（t≈16.4s 回 opencode·working）、窗内新 error 立即回归；TC-M6-03 四类气泡 OCR 全捕获（[oc] 工具播报×2、[cc]、[task] 例程 echo exit=0、提醒无徽标回归、token 汇报 [oc]/[cc]）+ DOM/CSS 断言（等宽 11px 弱化色、缺省不渲染、合并键不含 agent 幸存者 [oc] queueLen=0、task 无 snooze）；TC-M6-04 裁定点①口径（右键菜单子行）三态 DOM 断言 + Σby_agent==39M 页内交叉相等（三层同口径互锁：Rust 单测/DOM harness/真实气泡追加段）；TC-M6-05 标 * 说明（task agent 不可 HTTP 注入系白名单设计——实机注入例程触发 4 次 exit=0 + 单测⑧⑨时序精确钉住）；TC-M6-06 四次重启 setup 全绿 + 旧格式兼容 3 路（空 body 400/错 token 401/多余字段 200 不炸）+ i18n 18/18。**缺陷：P0/P1/P2 均无**（TEST_BUG×2 测试侧自纠不影响交付面）。观察项 5：OBS-SIGTERM（外部 kill 无 exit 日志——v1 既有，建议后续维护版清单）、OBS-DEDUP（3 分钟去重节律，提醒实测须按 fired 时间戳对窗）、OBS-HYST（交替仅事件交错时、滞回未实现符合设计）、OBS-PANEL（panel 真机点击层未执行——鼠标合成权限超本轮工具授权，数据层三链路证明替代，建议 committer 判定是否需人工点验）、徽标间距 CSS margin 备查。环境恢复：自起进程全杀净（pgrep 复核空）、沙箱已删、用户真实 pulsepet.db mtime 11:33 未变、INC 禁区未读未写、仓库零 commit 零 diff。status=testing（待 committer 评审）
- R1: committer 审查 **APPROVED**（2026-08-27 16:02，committerTaskId=ses_fbdc9b371ffe1mp9bZ29u6rJk2，reviewedSha=8973813…=testedSha=HEAD 三方一致）。报告全文见「最新验证意见原文」摘要：基线核验五项全过（HEAD/父级 d2a8786=origin/develop/23 文件 +961−100 与 filesChanged 逐项一致/依赖零变更/提交格式合规）；逐块语义核验全过（两层算法 §6.1 逐字一致含 checked_sub/saturating 边界、十条钉子逐行号核验、P1-1/P2-2/P2-3/P2-4/P2-5/P3-2/P3-3/P3-4/P3-6 评审钉子全部落实、四来源徽标、reconcile SQL 清偿属实、plog! 纪律零 eprintln!/零 debug、不做项零预实现）；测试质量（Rust +16/TS +19 断言真实非空跑、插入序反转构造有效）；tester 证据交叉核验通过。**问题清单：P0/P1/P2 均无；P3×4**：① PetMenu clamp effect deps 仅 [pos] 首帧估值 130 不含子行——双 agent 日菜单增高 ~14px 贴下缘时底项被裁（打磨轮：deps 加 todayToken 或 ResizeObserver 或估值 146）；② [文档] V2-DESIGN §6.2/§6.3/§6.4 与 TC-M6-04 仍写悬停卡/HoverToday——M6 交付后文档维护提交同步修订（i18n 键名 hoverAgent 名实轻微不符不改备注查）；③ TC-M6-05 完全实机组合（真实例程×并发手头流同屏）未跑——算法已被单测+TC-M6-02 端到端钉住可接受，建议并入用户人工目验批次；④ (priority,last_event_at) 完全相等胜者依 HashMap 序——纳秒分辨率下不可达，记录备查。tester 观察项定级：OBS-SIGTERM→V1-OPEN-ITEMS §八维护版清单；OBS-DEDUP/OBS-HYST=记录无行动；OBS-PANEL=**判定无需强制人工点验**（M6 新增 UI 仅菜单子行 DOM 三态已验、panel 与 by_agent 零交互、数据三层互锁）建议并入既有实机目验批次不阻塞放行。**需求边界裁定**：裁定点①（分布行落点右键菜单）适配成立无需回 spec 阻断——后裁定（08-25 移除 HoverToday）优先于 M6 定稿（08-23），文档滞后属 P3 文档维护项；裁定点②（TC-M6-05 单测为主+实机抽查）成立——AGENT_WHITELIST 白名单设计属实、口径充分。**双通过达成：testVerdict=PASS + reviewVerdict=APPROVED + SHA 三方一致 → status=approved**，待用户裁定是否交付（交付=同步 origin/develop→push develop_opencode→PR base=develop→gh pr review 留痕→evidence manifest 入 PR description；另含 committer 建议的文档维护提交 P3-②）

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

### R1 tester 报告（2026-08-27 15:51，testVerdict=PASS）

# PulsePet v2 M6 验证报告（tester）

**testVerdict: PASS** | **testedSha: `8973813da5fbe23baba93a09769995314a0b2de2`**（HEAD，develop_opencode，[task-pulsepet-v2-m6] R1，基线 d2a8786；验证全程无新 commit、工作区业务代码零改动）

## 一、TC 用例结果总表

| 用例 | 结论 | 关键证据 |
|---|---|---|
| TC-M6-01 两层合并算法（单测） | ✅ PASS | 十条钉子逐条源码+测试双确认（§二），cargo 全绿 |
| TC-M6-02 双 agent 抢镜实测 | ✅ PASS | 实机芯片 OCR 五连拍：归属切换 + error 静默 >10s 让位 + 新 error 回归（§四·A） |
| TC-M6-03 气泡 agent 徽标 | ✅ PASS | 四类气泡实机 OCR 全捕获（含提醒无徽标回归）+ 单测 13 项 + DOM getComputedStyle 断言 |
| TC-M6-04 分布行（裁定点①口径） | ✅ PASS | 落右键菜单子行：三态 DOM 断言 + Σby_agent==39M 页内交叉相等 + Rust 单测 5 条 |
| TC-M6-05 M4 例程协同 | ✅ PASS* | 实机注入 interval 例程触发 4 次全程 exit=0 日志；手头压过/静默兜底时序由单测⑧⑨精确钉住（task agent 不可 HTTP 注入——白名单设计如此），标 * 为单测为主+实机抽查 |
| TC-M6-06 回归目验 | ✅ PASS | 4 次重启 setup 全绿日志；旧格式兼容 3 路 HTTP 戳测 + 三桥层缺省容错单测；i18n 18/18 含 M6 显式钉 |

## 二、TC-M6-01 十条钉子逐条核验（源码级，非空跑）

实现主体：`session_state.rs L203-250 display(now)` 两层算法——活跃集 `(priority, last_event_at)` 字典序取最大 / fallback `(last_event_at, priority)` 取最大 / 空表 Idle+空 agent，`ACTIVITY_WINDOW_MS=10_000` 闭区间。

| # | 钉子 | 测试名（cargo 实跑绿） | 行号 | 断言有效性评估 |
|---|---|---|---|---|
| ① | 双活跃 error>working | `m6_active_set_merges_by_priority` | L492 | error(-2s) 压 working(0s)，断 kind+agent |
| ② | 平局镜像字典序+插入序反转钉 | `m6_same_priority_tie_picks_latest_last_event_at` | L505 | 双构造镜像插入序，winner 恒 claude-code——若依赖 HashMap 序则反序必翻车，**有效防任意序** |
| ③ | 掉窗让位（核心修复） | `m6_stale_error_yields_to_active_working` | L523 | error@12s 前 vs working@2s 前 → working，v1 会持续 error 抢镜 |
| ④ | fallback 最近活跃（平局 priority 高者） | `m6_empty_window_falls_back_to_most_recent` | L536 | 双段：20s/15s 掉窗选更新的 working；同刻平局 success(2)>working(1) |
| ⑤ | solo error 至 30s 回收（P1-1） | `m6_solo_error_survives_via_fallback_until_reclaim` | L557 | 5/15/25/29s 四点仍 Error+agent 不丢 → tick(30s) 后 Idle+agent 空 |
| ⑥ | sessions 空→idle | `m6_empty_sessions_display_idle_with_empty_agent` | L577 | Idle + agent=""（前端降级基础） |
| ⑦ | 跨 agent 同权（oc/cc/task） | `m6_cross_agents_participate_equally` | L585 | task testing 胜窗内合并；掉窗后被 opencode 接管 |
| ⑧ | 15s 心跳时序不闪变 | `m6_task_heartbeat_fallback_stable_during_user_silence` | L607 | 心跳 11s 后掉窗 fallback 连选例程「不闪变」→ 手头事件即夺回 → 例程 working(1) 压不过 editing(4)，全链五断言 |
| ⑨ | waiting-permission 掉窗让位（P2-5） | `m6_waiting_permission_yields_when_out_of_window` | L637 | 12s 前让位 vs 8s 前不让位对照段，语义双向钉 |
| ⑩ | v1 断言时钟修订 + 1s 循环注释钉 | 既有全部旧测改传 `t/t0`（L296-482 共 14 处）；末尾注释块 L673-676 | lib.rs **L334-338 注钉原文在场**：「本循环的 notify 对 M6 语义不可或缺，不可被"优化"掉…删掉 notify（只留 tick）会让掉窗让位永不发生」；调用点 `notify()` 与 `get_display_state` 均传 `Instant::now()`（http_server.rs L72-76、lib.rs L59-64，P2-3） |

附加：边界闭区间钉 `m6_window_boundary_is_inclusive_at_10s`（恰 10s 在窗内 / +50ms 让位），对齐插件 10s 心跳节奏。**Rust 侧输出证据**：`cargo test` 显示上述 10 个 m6_* 测试逐名 `... ok`（session_state 10 + token_stats 5，见 §八命令摘录）。

## 三、基线独立复跑（与 coder 自述核对）

| 项 | coder 自述 | 本次复跑 | 一致 |
|---|---|---|---|
| cargo test | 317 passed + 3 ignored | **317 passed; 0 failed; 3 ignored**（~2.06s） | ✅ |
| npm test | 405 / 28 files | **405 passed (28)**（3.26s） | ✅ |
| tsc --noEmit | 0 | **TSC_OK** | ✅ |
| npm run build | ✓ | ✓ built in 403ms | ✅ |
| tauri build 产物 | app @14:58:56 / dmg @14:59:17 | 本 tester 独立重建：**PulsePet.app @15:16:34 / PulsePet_0.1.3_aarch64.dmg @15:16:55**（release 二进制随跑实测驱动后续章节） | ✅ |
| 遗留 TEST_BUG 清偿 | reconcile manual SQL 修 | `real_db_reconciliation_manual -- --ignored` 单独执行 **ok** | ✅ |

## 四、实机验证（release 二进制 + HOME 重定向沙箱，零触真实数据）

沙箱方式：`HOME=/var/folders/.../opencode/pp-m6/home`（经源码核实 opencode 数据目录/transcript 目录/runtime 目录均从 `$HOME` 解析）。真实库安全声明：用户 `~/Library/Application Support/com.pulsepet.app/pulsepet.db` 验证前后 mtime 均 **11:33** 未变；INC 禁区目录未读未写；自起 4 个 App 进程用毕 TERM 全退（`pgrep -x pulse-pet` 空）；沙箱已删除。

### A. TC-M6-02/05 双 agent 芯片时序（panel 第二实例唤起术 + screencapture + swift Vision OCR，非 Vision 子代理）

POST 流（token 读 `$HOME/.pulsepet/runtime/update-token`、endpoint 文件 47811，curl 直打 `/state`）：

```
oc working sesA ──► cc editing sesB ──► cc error sesB
   │(静默 13.3s)│                        │
chip: opencode·working → claude-code·editing → claude-code·error
                                             (t≈8.6s) 仍 claude-code·error【掉窗前占片】
oc working 每 1s ×7 ………► chip 回 "opencode · working"@t≈16.4s 【error 静默 13.3s>10s 窗口，≤10s+1s 循环兜底延迟让位✔】
再发 cc error（窗内）► chip 立刻回 "claude-code · error" ✔
```

OCR 摘录（shots/n_c*.png）：`opencode• working` / `claude-code • editing` / `Claude-code• errOr`(识别噪声) / t8.6s 同款 error / n_c4 `opencode• working`。芯片去重键 (kind,agent) 使换 agent 即广播（M2 P1-1 口径保持）。**核心修复（③掉窗让位）获得端到端实机实证。**

HTTP 层证据：正常事件全 200 且日志首见记号两行（`first event from agent 'claude-code'/'opencode'`）；坏输入健壮性：空 body→400、错 token→401、未知多余字段 body→200（不炸，向后兼容行为面）。

### B. TC-M6-03 四类气泡徽标实机捕获（220×220 pet 区抓帧 OCR）

| 类别 | 触发法 | OCR 画面摘录 | 判定 |
|---|---|---|---|
| 工具播报 [oc] | POST detail=`edit:M6 工具播报甲` | `［oc］正在编辑 M6 实机播报甲`（两次复现 u_d1） | ✅ |
| 工具播报 [cc] | POST detail=`bash:M6 实机播报乙回拍` | `［cc］正在跑 M6 实机播报乙…`（v_d2） | ✅ |
| 任务结果 [task] | 沙箱库注入 interval exec 例程 `echo pulsepet-m6-echo-ok` | `［task］ M6例程echo：任务…`（v_b08–b12 连续帧） | ✅ |
| 提醒无徽标（回归） | 注入 interval notify 提醒 | `M6测试提醒` 无任何方括号徽标（v_b04–b07） | ✅ |
| token 汇报 [oc]/[cc] | OC 库行 + CC transcript jsonl 刷新后 idle POST | `［oc］本期用了 3.6k input/8…`、`［cc］本期用了 6.0k input/9…` | ✅ |

附证：`action_logs` 4 行均 `status=ok exit_code=0`，日志 `exec started/finished ... exit=Some(0)` —— M4 例程触发回归实锤；气泡排队可见 critical(critical 8s)→critical(task result 8s) 顺序推进，与 §2.6 排队模型一致。

**TEST_BUG 自纠记录**：初版探针用 `detail:"test:"/"run:"` 前缀不出气泡——定位为 `parseToolDetail` 模板白名单 `read/edit/bash/search/web` **按设计丢弃**（tool-bubble-bridge.ts L31/L49 单测钉在位），改用白名单前缀后复现成功。归类 TEST_BUG，非 IMPL 缺陷。

### C. TC-M6-03/04 组件级 DOM/CSS 断言（Playwright harness：项目 Vite 直接挂生产 Bubble.tsx/PetMenu.tsx + Tauri invoke shim；**非重写组件**）

| 断言 | 结果 |
|---|---|
| 徽标前置渲染 `.pet-bubble-agent` textContent `[oc]`/`[cc]`/`[task]` | ✅ 三连过 |
| 字体形态 | `font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`、`11px`、`rgb(107,95,78)`（global.css L177-183 弱化色）✅ 与设计「前置等宽小字」一致 |
| agent 缺省不渲染 | 提醒气泡（critical+reminder 载荷）badge 不存在且 **⏱10min snooze 按钮在场**（M4 回归同时锚定）✅ |
| 合并键不含 agent（P3-4） | 同 source `tool:edit` 两连 push → 幸存者徽标 `[oc]`、queueLen=0（原地合并非排队）✅ |
| task 结果气泡无 snooze 按钮 | ✅（无 reminder 载荷路径正确） |
| 菜单分布行（双 agent） | 第 0 项 label `今日 token：39.0M`，子行 `pet-menu-sub` = `oc 36.0M · cc 3.0M`，**降序 true**，display:block、10px，title=`今日 agent 分布`（i18n 键直连）✅ |
| 单项不显示 / 零数据省略 | 子行不存在（label 正常 36.0M / 0）✅ |
| 全缺错误路径 | label `今日 token：—`（M3 三态保留）✅ |
| **Σby_agent==今日总量交叉断言**（同口径 in+out+cacheRead） | 页内复算 sum=total=39,000,000 equal=true rowsDesc=true ✅（与 Rust 单测 m6_today_by_agent_* 及 vitest todayByAgentText 形成三层同口径互锁）|

徽标形态刻意不同（P3-2）：气泡 JSX 输出带括号 `[${badge}]`（Bubble.tsx L34），菜单分布行无括号短名（pet-menu.ts L65），代码注释两侧均在位——未发现被「顺手统一」。

## 五、缺陷清单

**P0：无。P1：无。P2：无（IMPL_BUG 计数 0）。**

自检发现的测试侧问题（均已当场修正重跑，不影响交付面）：
- TEST_BUG-A：工具播报探针初用白名单外 tpl 前缀（见 §四·B）
- TEST_BUG-B：截图坐标两次解析偏移/竞态导致早期帧落空（修正为双窗口就绪门闩 + findwin2 精确解析后全中）

## 六、观察项（不改判分）

1. **OBS-SIGTERM**：外部 kill 不产生 `exit` 日志行、runtime token/endpoint 残留不清理（退出钩子仅覆盖常规退出路径）——v1 时代既有行为，M6 零改动面，建议纳入后续维护版清单。
2. **OBS-DEDUP 节律**：interval 规则受「同规则 3 分钟不重复」（TC-RM-05 既定）影响，60s 周期规则实际展示节律 ≈每 4min；后续做提醒类实测须按 fired 时间戳对窗而非假定整分钟。
3. **OBS-HYST**：TC-M6-06-3 观察项成立——显示交替仅在双 session 事件交错时观察到（本次为事件流直接驱动的预期交错），2s 滞回预设计未实现，符合 R1 设计原样。
4. **OBS-PANEL 数值面**：panel Token 页三层交叉（菜单 sub vs panel 表格 vs idle 追加段）的**真机点击层**未执行（需鼠标合成权限，超本轮工具授权），以数据层三条链路证明替代：同一 `TodayStats.by_agent` 结构在 Rust 单测（Σ==total）、DOM harness（页内复算相等）、真实 App 气泡追加段（`今日 k` 段）三个消费端各自验对。建议 committer 判定是否需要在具备辅助权限的环境补一次人工点验。
5. 徽标文字流后间距由 CSS margin-right 提供（textContent 无尾随空格），实机截图中视觉间距正常，非缺陷记录备查。

## 七、环境恢复声明

- 自起进程：probe/main×3 App 实例、harness node、playwright-cli browser —— **全部关闭**（pgrep 复核为空）。
- 测试数据：全部位于 `/var/folders/9k/.../opencode/pp-m6/`（home 沙箱已删；bin/scripts/log/89 张截图留存于系统临时目录供复核，到期自动清理或可手动清除）。用户真实 `pulsepet.db`、`~/.pulsepet`、`~/.local/share/opencode`、`~/.claude` **零触碰**（禁区未读未写；real-db 仅存在性 stat 对账）。
- 仓库：无任何 commit/stash/checkout；`git status` 仅含任务开始前已存在的流程文件变更与 `pulse-pet/images/` 未跟踪项；业务代码与测试文件 diff 为零。

## 八、关键命令/输出备查摘录

```
test result: ok. 317 passed; 0 failed; 3 ignored            # cargo test
Test Files 28 passed (28) / Tests 405 passed (405)          # npm test
TSC_OK / ✓ built in 403ms                                   # tsc + vite build
test session_state::tests::m6_stale_error_yields_to_active_working ... ok   （十条逐名绿）
test token_stats::tests::m6_today_by_agent_dual_source_two_rows_desc ... ok
2026-08-27 15:24:02 [pulsepet] first event from agent 'claude-code' ...
2026-08-27 15:28:22 [pulsepet] reminder fired: #2 label="M6测试提醒" log=3
2026-08-27 15:28:22 [pulsepet] exec finished: task #1 log#3 status=ok exit=Some(0)
POST /state: empty→400 | wrong-token→401 | extra-field→200 | normal→200×N
OCR: ［oc］正在编辑 M6 实机播报甲 | ［cc］正在跑… | ［task］ M6例程echo：任务… | M6测试提醒(无徽标)
DOM: oc/[cc]/[task] badge ff=ui-monospace fs=11px | reminder badgeGone=true
DOM: subText="oc 36.0M · cc 3.0M" descSorted=true | crossCheck {sumByAgent:39000000,total:39000000,equal:true}
```

**结论：verdict = PASS。** coder R1 的两层合并算法、徽标链路、by_agent 分布与 i18n 完备性实现与 V2-DESIGN §6 / TC-M6-01~06 一致，遗留 TEST_BUG 清偿属实，可进入 committer 审核。

### R1 committer 报告（2026-08-27 16:02，reviewVerdict=APPROVED）

# PulsePet v2 M6 R1 审查报告（Committer）

**审查基线核验**：HEAD=8973813da5fbe23baba93a09769995314a0b2de2 ✓（与检查点 testedSha 一致）；提交父级 d2a8786 = origin/develop 最新 ✓（开工同步属实）；工作区业务代码零 diff（仅流程文件）✓；23 文件 +961/−100 与检查点 filesChanged、coder 自述逐项一致 ✓；无依赖变更（Cargo.toml/package.json/lock 均未动）✓；提交信息 `[task-pulsepet-v2-m6] R1` 格式合规 ✓。

## 一、逐块语义核验（设计对照）

| 审查面 | 结论 |
|---|---|
| session_state.rs 两层算法 | ✓ L203-250：活跃集 `(priority,last_event_at)` 字典序最大 / fallback `(last_event_at,priority)` / 空表 Idle+空 agent；闭区间 `>=`；`checked_sub` 防 Instant 下界、未来时刻按活跃（saturating）——与 §6.1 逐字一致 |
| 十条钉子 | ✓ 逐条源码核验：①L492 ②L505（含插入序反转钉）③L523 ④L536（fallback 平局 priority）⑤L557（5/15/25/29s→30s 回收）⑥L577 ⑦L585 ⑧L607 ⑨L637 ⑩既有断言 14 处时钟注入修订；另有边界闭区间附加钉（恰 10s 在窗/+50ms 掉窗） |
| P1-1/P2-2/P2-5 | ✓ solo error 有意行为、镜像字典序、waiting-permission 双向对照段全部钉住 |
| P2-3 两调用点 | ✓ http_server.rs notify（L72-76）与 lib.rs display_state_dto（L59-64）均传 `Instant::now()`，无遗漏调用点（编译期强制） |
| P3-6 注释钉 | ✓ lib.rs L334-338 原文在场：「本循环的 notify 对 M6 语义不可或缺，不可被"优化"掉…删掉 notify（只留 tick）会让掉窗让位永不发生」 |
| 气泡 agent 徽标四来源 | ✓ token 汇报双路径（opencode 经 idle_hook_body emit `(agent,text)`、CC 硬编码 "claude-code"）、tool-bubble `(detail,agent)` 透传、task-result `task_result_payload` 显式 agent:"task"；提醒无徽标 |
| P2-4 载体 | ✓ BubbleItem.agent? 可选字段；mergeable 键 = source+level+10s 窗，**不含 agent**（bubble-queue.ts L91-97）；幸存者=新条目（L136 spread item）、回队条目 agent 保留（L156-158）——P3-4 语义精确 |
| P3-3 by_agent | ✓ 落 TodayStats 内 + `#[serde(default)]`；query_today_on 填 opencode 行、today_stats_dual 合并降序（total 平局按 agent 名稳定序）；degraded 路径 CC-only 单行；Σ==今日总量交叉断言（in+out+cacheRead 同口径） |
| reconcile SQL 清偿 | ✓ 与 M5 实现（query_by_day L363-376 `GROUP BY day,agent,model_id`+mock 过滤）口径一致；session 级同加 mock 过滤；TEST_BUG 清偿属实 |
| P3-2 形态刻意不同 | ✓ 气泡 `[{badge}]` 带括号等宽 11px 弱化色 vs 分布行无括号短名；两侧注释钉在位，未被顺手统一 |
| i18n | ✓ token.hoverAgent zh/en 双键 + 显式钉 + 既有完备性测试；徽标不翻译 |
| plog!/debug 纪律 | ✓ Rust diff 零新增 eprintln!；前端零新增 console.log（3 处为既有代码）；无 dbg!/debugger |
| 不做项零预实现 | ✓ 滞回/尾部标识/per-session 宠物/提醒徽标/5s 窗口均未实现 |

## 二、测试质量

- **Rust +16**（317+3i）：10 个 m6_* + task_result_payload + 时钟注入修订——全部断言 kind+agent 双维，非空跑；平局测试的插入序反转构造有效防 HashMap 迭代序依赖。
- **TS +19**（405/28 files）：合并幸存者 agent、顶替回队保留、badge 映射/缺省 null、三桥层解析容错、菜单 sub 行三态、i18n 双键——逐条断言真实行为，无走过场。
- tester 报告与代码交叉核验：测试名/行号/断言与我源码阅读**全部一致**；基线独立复跑与 coder 自述一致；tester P0/P1/P2 零缺陷结论与我的独立审查结论一致。

## 三、问题清单

**P0/P1/P2：无。**

**P3（不阻塞，均定去向）：**

1. **[P3] PetMenu 菜单高度增长无重算**——`PetMenu.tsx` L40-52 实测 clamp 的 effect deps 仅 `[pos]`，首帧估值 130（L37）不含子行：双 agent 日数据 resolve 后菜单增高约 14px，但 clamp 按 loading 态高度（130）计算，菜单贴近窗口下缘时最底项约 14px 被 220px 窗口裁切。修法：effect deps 加入 todayToken（子行出现后重算）或 ResizeObserver；或首帧估值 130→146。→ 打磨轮。
2. **[P3·文档] V2-DESIGN §6.2/§6.3/§6.4 与 TC-M6-04 步骤面仍写「悬停卡/HoverToday.tsx」**——非代码问题，M6 交付后文档维护提交同步修订（M5 d2a8786 先例），交叉引用 §3.4 修订。i18n 键名 `token.hoverAgent` 保留「hover」字样名实轻微不符——不改（churn 不值得），备注查。
3. **[P3·观察] TC-M6-05 完全实机组合未跑**——真实例程 × 并发手头 HTTP 流同屏组合缺实机实证；task 芯片显示面仅由单测推断（[task] 气泡已实机 OCR 捕获）。算法纯函数已被单测精确钉住 + TC-M6-02 同算法端到端实证，可接受；建议并入用户人工目验批次（与 TC-M5 实机缺口同批）。
4. **[P3·理论边界] 活跃集 (priority,last_event_at) 完全相等时胜者依 HashMap 迭代序**——生产 Instant::now() 纳秒分辨率下不可达，设计未定义第三级 tie-break，记录备查，无需处理。
5. **tester 观察项定级**：OBS-SIGTERM=v1 既有 → V1-OPEN-ITEMS §八 维护版清单；OBS-DEDUP=既定行为（TC-RM-05）→ 后续提醒实测按 fired 时间戳对窗，记录；OBS-HYST=符合设计（R1 观察项）→ 无行动；**OBS-PANEL=判定无需强制人工点验**（M6 新增 UI 仅菜单子行，DOM harness 三态已验证；panel 与 by_agent 零交互；点击直达为 M3 既有行为零改动；数据三层互锁已证明）——建议顺手并入既有实机目验批次，不阻塞放行；徽标间距=CSS margin-right 4px 视觉正常 → 备查。

## 四、需求边界裁定

- **裁定点①：适配成立，无需回 spec 阻断**。后裁定（2026-08-25 移除 HoverToday，§3.4 留档「不作实施依据」）优先于 M6 定稿（08-23）——数据层照设计全量实现（by_agent 落 TodayStats/同口径/降序/单双项语义），呈现层落到现存活入口（右键菜单信息项子行，TC-M3-11 面）。§6.2/§6.3 表述滞后属**文档维护项（P3），去向 = M6 交付后文档维护提交**。
- **裁定点②：成立**。`AGENT_WHITELIST=["opencode","claude-code"]`（http_server.rs L41，未知 agent 400）确认 task 不可 HTTP 注入系白名单设计属实；「单测为主（⑧⑨精确时序钉）+ 实机抽查（例程 4 次 exit=0、[task] 气泡 OCR）+ TC-M6-02 同算法端到端实证」口径充分，tester 标 * 恰当。

## 五、Tester 证据交叉核验结论

**通过**。十条钉子测试名/行号/断言与源码一致；numstat 复核 +961/−100 与 23 文件清单精确吻合；基线数字双方独立复跑一致；reconcile SQL 与 M5 实现口径一致；TEST_BUG×2 确属测试侧自纠；环境恢复声明完整（真实 db mtime 未变、INC 禁区零触碰、零 commit）。

---

**reviewVerdict: APPROVED** | **reviewedSha: 8973813da5fbe23baba93a09769995314a0b2de2**

## 六、交付步骤清单（放行）

1. **检查点更新**：reviewVerdict=APPROVED、reviewedSha=8973813da5fbe23baba93a09769995314a0b2de2、committerTaskId、updatedAt、endReason=正常闭环。
2. **文档维护提交**（可独立于交付）：V2-DESIGN §6.2/§6.3/§6.4 + TC-M6-04 措辞对齐「右键菜单子行」口径（P3-2 项）。
3. **PR 留痕**：当前无 M6 开放 PR（#17 为已合并的 M5 PR）；用户确认交付、PR 开出后（develop_opencode→develop，M4/M5 先例），执行 `gh pr review --approve` 落审查结论。**合入动作不经手。**
4. **遗留更新**：OBS-SIGTERM → V1-OPEN-ITEMS §八；OBS-PANEL 与 TC-M6-05 实机组合 → 用户人工目验批次清单。

R1 一次通过，无修复轮次需求。
- **用户交付裁定（2026-08-27 16:04）**：确认交付（"先交付吧"——纯交付链，文档维护 P3-② 不在本轮随行）。交付链启动：① coder（复用会话）同步 origin/develop→push develop_opencode→gh pr create（base=develop）；② committer（复用会话）gh pr review 留痕；③ coder 把 evidence manifest JSON 写入 PR description；④ 汇报合入请求（不自动合入）
- **交付① coder push+PR（2026-08-27 16:08）**：fetch 确认 origin/develop=d2a8786 无新提交；push 成功 `ca2b600..8973813 develop_opencode`（用户侧放行）；**PR #18** 已创建（https://github.com/yq3/lab/pull/18，base=develop / head=develop_opencode，1 commit=8973813，23 files +961/−100，body 六节齐备含 EVIDENCE_MANIFEST_PLACEHOLDER 占位）。待：② committer gh pr review 留痕 → ③ coder evidence manifest 入 PR description
- **交付②中断与恢复（2026-08-27 16:20）**：首次调用 committer（复用 R1 会话 ses_fbdc9b371ffe1mp9bZ29u6rJk2）执行 gh pr review 留痕时陷入死循环，用户取消——**旧会话作废，PR #18 留痕尚未执行**（reviews 状态未知，新会话须先核验）。按恢复协议新开 committer 会话（返回后覆盖 committerTaskId），指示其从检查点文件恢复上下文
- **交付② committer PR 评审留痕（2026-08-27 16:23，新会话 committerTaskId=ses_fbdb11dd4ffePsoum1WLXjbROu，旧死循环会话 id 已覆盖）**：防死循环纪律三步全一次成功——前置核验四项过（base/head/OPEN、1 commit 8973813 双 SHA 三方一致、23 文件 +961/−100 精确吻合、reviews=[] 确认死循环会话未落痕无重复风险）；`gh pr review 18 --comment` 提交五节正文（①评审对象核对 ②R1 审查结论 APPROVED ③tester 证据交叉核验 ④knownIssues 移交 P3×4+OBS 定级 ⑤交付声明 COMMENT 留痕+self-approve 限制注记）；复核恰 1 条——**Review ID `PRR_kwDOTsiHgs8AAAABLFR9Qg`，state=COMMENTED，submittedAt 2026-08-27T08:23:17Z（北京 16:23:17）**，正文首行「Committer 终审（task-pulsepet-v2-m6）— reviewVerdict=APPROVED」正确落痕无重复。未 merge/未改 PR body/未推分支。待：③ coder evidence manifest 入 PR description
- **交付③ evidence manifest（2026-08-27 16:25）**：一次读取 body（59 行占位符在末尾）→ 本地构造 JSON（deliveredAt=2026-08-27T16:24:34+0800 实时取值）→ **diff 校验 removed 仅占位符 1 行、原六节零丢失**（59→96 行）→ `gh pr edit 18 --body-file` 一次提交 → 复核 7 个 ## 节（原六节+Evidence Manifest）在位、PLACEHOLDER 消失。manifest 全字段：双 SHA=8973813…、base=develop@d2a8786、testVerdict=PASS、reviewVerdict=APPROVED、committerReview（PRR_kwDOTsiHgs8AAAABLFR9Qg COMMENTED）、evidence 五项（cargo 317+3i/npm 405/tsc 0/build/runtime 三项实机 OCR）、openItems 五项。**交付链三步完成（PR #18 OPEN 待用户 merge）**
- **交付④ PR 合入（2026-08-27 16:29，用户指示"先合入PR吧"）**：`gh pr merge 18 --merge --delete-branch=false`（沿用 #16/#17 merge commit 惯例）→ **MERGED** @2026-08-27T08:28:56Z，merge commit `f9e471f`；fetch 确认 origin/develop d2a8786→f9e471f（8973813 入 develop）。**task-pulsepet-v2-m6 全流程闭环**（R1 实现→测试 PASS→终审 APPROVED→交付三步→合入，R1 一次通过无修复轮）；本地 develop_opencode 未动，检查点等工作区流程文件待后续文档维护点入库。**v2 六个里程碑（M1~M6）全部收官，v2 主体完成**

### 遗留事项清偿/移交汇总（交付回写，2026-08-27 16:29）
- **本轮清偿**：TEST_BUG real_db_reconciliation_manual（v2-m5 移交，R1 顺手修，tester ignored 单测 ok + committer 口径核对一致）；M6 主体全部交付（两层算法/徽标/by_agent/i18n，双通过 + PR #18 合入）
- **本轮新移交**：P3×4（① PetMenu clamp 高度→打磨轮；② 文档滞后 §6.2/6.3/6.4+TC-M6-04→文档维护轮；③ TC-M6-05 实机组合+OBS-PANEL→用户人工目验批次；④ 理论 tie-break→备查）；OBS-SIGTERM→V1-OPEN-ITEMS §八（随下个 v1 文档维护点落笔）；OBS-DEDUP/OBS-HYST=记录无行动
- **继续移交（历史）**：v2-m2 实机目验 7 项（待用户反馈）；TC-M5 实机验收缺口 4 项（用户人工配合 per INC-20260827-1033）；v2-m2 P3-5/P3-6~10；v2-m5 committer P3×4（打磨轮）；M4 P3①②③+Windows 观察项；v2-m1 遗留 A~D；after-crash 库留档至 2026-09-03；pp-m5-dom/ 63 截图（人工复核后可清）
- **遗留清单文档化（2026-08-27 21:10，用户指示，supervised-coding 执行）**：新建 `pulse-pet/docs/v2/V2-OPEN-ITEMS.md`——v2 六里程碑检查点遗留全量汇总（六类：用户目验/实机批次、条件触发、打磨轮 13 项、文档维护、发布与清理、记录备查）；后续任务以此清单 + 检查点为移交基准。另注：v0.2.0 之后用户自行 bump v0.2.1（tag f2cf13e，Draft 待核对）已入清单五节
- **⚠️ 覆盖事故与恢复（2026-08-27 21:12 更正上条记录）**：21:05 写入 V2-OPEN-ITEMS.md 时**误覆盖了用户并行创建的同名文件**（acc12b3 新建 + 94622dd 闭环——issue #19/#20 Windows 缺陷诊断/R1-R5 修复/v0.2.1 实机三场景验证记录，16:29~21:05 期间用户另一线工作产物）。根因：会话开始时该文件不存在，间隔近 5 小时后写入前未复查存在性（期间已注意到 v0.2.1 tag 异常却未联想到其他文件变动）。用户自行从 git 恢复原文件（21:11）→ supervised-coding 改为**按原结构追加**：原文一~四节（#19/#20 专项）一字不动，引言加构成说明一行，追加五~十节（六里程碑遗留六类汇总 + 附清偿记录），git diff +126 行纯追加零删除；内容融合两处：TC-M4-18 核心面标注已随 v0.2.1 场景 2 验证、v0.2.0 Release 标注被 v0.2.1 取代待裁定。教训入册：**写入既有路径前必先检查存在性 + 读原文**（即使会话早期它不存在，长会话期间用户可能有并行操作）
- **文档维护轮执行（2026-08-27 21:18，用户指示，supervised-coding 落笔）**：清偿 M6 P3-②（V2-OPEN-ITEMS §8-1）——V2-DESIGN 7 处（§6.0 裁定表悬停卡行加前向注记〔原文不动〕、§6.2 标题改「今日 agent 分布行」+节首修订注记+末段按实际落点改写、§6.3 表 HoverToday 行改 pet-menu/PetMenu/todayToken 三文件+i18n 行键名保留注、§6.4 单测表「前端」行+实机验收 3 改菜单子行两层口径）+ V2-TEST-CASES 4 处（TC-M6-04 标题+修订注记+步骤+预期 1/3、TC-M6-06-4 措辞）；§6.7 评审/终审记录历史留档未动；i18n 键名 token.hoverAgent 按裁定保留。V2-OPEN-ITEMS §8-1 已勾销+清偿记录回写。三文件改动（DESIGN +18 行内/OPEN-ITEMS +128/TEST-CASES ±10）在工作区待入库
