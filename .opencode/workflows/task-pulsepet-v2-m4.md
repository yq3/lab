---
# 全部字段必填：未产生/未知的值写 null 或 []，禁止删除或省略任何字段（D33 完整性铁律）
taskId: task-pulsepet-v2-m4
target: pulse-pet
coderTaskId: ses_fc7318cdbffeTnHwAfnBTQpShw
testerTaskId: ses_fc69fe5abffegUuJH6i9bI9jhO
committerTaskId: ses_fc2033415ffet4PQG0eKsT8iRI
status: approved
round: 5
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: d71571683f1aca9e61caa215ebcf0d96278b3713
reviewedSha: d71571683f1aca9e61caa215ebcf0d96278b3713
# 以上 SHA = coder 最近一轮本地 commit（[taskId] R<n>）后的 HEAD；修复轮 commit 后 reviewedSha 置空待重审
filesChanged: [pulse-pet/src-tauri/Cargo.toml, pulse-pet/src-tauri/Cargo.lock, pulse-pet/src-tauri/migrations/003-m4-tasks.sql, pulse-pet/src-tauri/src/action_exec.rs, pulse-pet/src-tauri/src/db.rs, pulse-pet/src-tauri/src/i18n.rs, pulse-pet/src-tauri/src/lib.rs, pulse-pet/src-tauri/src/logging.rs, pulse-pet/src-tauri/src/reminder_scheduler.rs, pulse-pet/src/lib/i18n.ts, pulse-pet/src/lib/i18n.test.ts, pulse-pet/src/lib/interaction.ts, pulse-pet/src/lib/interaction.test.ts, pulse-pet/src/lib/reminder-bridge.ts, pulse-pet/src/lib/reminders.ts, pulse-pet/src/lib/reminders.test.ts, pulse-pet/src/panel/Panel.tsx, pulse-pet/src/panel/Reminders.tsx, pulse-pet/src/panel/Tasks.tsx, pulse-pet/src/panel/TokenStats.tsx, pulse-pet/src/panel/registry.ts, pulse-pet/src/panel/registry.test.ts, pulse-pet/src/pet/Bubble.tsx, pulse-pet/src/pet/petStore.ts, pulse-pet/src/pet/petStore.test.ts, pulse-pet/src/pet/todayToken.ts, pulse-pet/src/styles/global.css]
endReason: null
createdAt: 2026-08-25T19:58:37+0800          # 创建时间（30 天清理审计用，见 README §4.5）
updatedAt: 2026-08-26T21:43:02+0800          # 每次写检查点必更新为当前时间（ISO 8601 含时区），不得沿用旧值
---

# task-pulsepet-v2-m4: PulsePet v2 M4——定时任务（动作泛化 notify / exec）

## 任务原文

用户原文（2026-08-25）："聚焦pulse-pet项目，开始V2版本M4阶段的开发任务"

实施 **V2-DESIGN §4（已终审定稿 2026-08-23，§4.14 评审 P1×3/P2×7/P3×9 全部采纳）**：M4 定时任务（动作泛化），落 M2 设计系统之上。

**权威文档**：
- 设计：`pulse-pet/docs/v2/V2-DESIGN.md` §4.0~§4.14（Spike S1~S4 事实基线 + §4.0 裁定汇总）
- 范围：`pulse-pet/docs/v2/V2-SCOPE.md` §3.4（三功能定位表 + 设计输入 §5.8）
- 验收用例：`pulse-pet/docs/v2/V2-TEST-CASES.md` 四、TC-M4-01~18

**范围（按 V2-DESIGN §4.1~§4.10）**：

1. **数据模型（迁移 003，SCHEMA_VERSION=3）**：`reminders` 表 +7 列——`action_type`（'notify' 默认 / 'exec'）、`action_params`（JSON 载荷，exec = `{command, cwd?, timeout_minutes?, opencode_auto?}`）、`schedule_kind`（'interval' 默认 / 'daily' / 'once'）、`schedule_at`（daily→"HH:MM"；once→"YYYY-MM-DDTHH:MM"；interval→NULL）、`schedule_weekdays`（JSON "[1,3,5]"，1=周一…7=周日，仅 daily 消费，NULL/空=每天；weekly 并入 daily 过滤）、`snooze_until`（RFC3339，触发时清空）、`last_skipped_at`（与 last_triggered_at 分离，防 skipped 写入使 3min dedup 拒绝手动补跑）；新表 `action_logs`（id/reminder_id 悬空允许/action_type 冗余快照/status 'running'|'ok'|'failed'|'skipped'/summary/output_tail ≤2KB/exit_code/started_at/finished_at/scheduled_at）。存储约定（P2-6）：daily/once 行 interval_minutes 恒 0（validate 强制），既有 `interval_minutes > 0` 分派点全改按 `schedule_kind == "interval"` 分派；kind 切换时 validate 重置无关字段（interval 行清 schedule_at/weekdays；daily/once 行清 start_time/end_time 窗口）；once 的 schedule_at 过去时刻 validate 拒绝。todo 派生行（kind='todo'）不迁移。v1 存量行自动获默认值，零行为变化。加列+新表全可事务化（A1 约定）。
2. **调度扩展（reminder_scheduler.rs）**：`compute_next_due` 按 schedule_kind 分派（纯函数扩展）——interval 既有逻辑不变（错过不补）；daily=下一个匹配日的 HH:MM（当日已过则次日跳过不匹配日）；once=schedule_at 绝对时刻、触发/跳过后 i64::MAX 终态。补跑宽限窗 `CATCHUP_WINDOW_MS = 15min`（notify/exec 同窗、daily/once 两 kind——用户单一口径裁定，偏离 SCOPE 字面已标注；interval 维持 v1 不补）：窗内正常触发（last_triggered_at 记实际时刻）；超窗 skipped——exec 写 action_logs(status='skipped', summary='错过补跑窗（15 分钟）', scheduled_at=原定) + 推进 next_due，notify 不落库不弹。**skipped 记账闭环（N1/P3-2）**：两来源（超窗/暂停）均写 last_skipped_at + 推进 next_due + 清空未过期 snooze_until（P3-5）；`collect_due` 返回 `(fired, skipped)` 由调用方落库。**reload 错过检测（P2-5）**：App 关闭/CRUD reload 重建 next_due 时 daily/once 检测「schedule_at 已过且 max(last_triggered, last_skipped) 早于该时刻」→ 同补跑窗判定（今早跑了没重启可对账）。暂停期间（对齐 SCOPE 字面）：daily/once 到期不顺延不触发即记 skipped（exec 落库/notify 不落）、记后推进 next_due、恢复后不补跑（完全冻结）；interval 类维持 v1 顺延。**snooze（仅 notify——exec 结果气泡无 reminder 载荷永不显示按钮）**：气泡按钮「稍后 10 分钟」→ `reminders_snooze(log_id)`——语义=重发本次（P1-1）：snooze_until = now+10min 写表 + 当前 log 结案 dismissed_via='snooze' + 内存 next_due 直接置为 snooze_until（优先于常规计算，非 max）；重发触发时清空 snooze_until 按 kind 常规推进（interval 锚点链后移 10min；daily 下个匹配日；once MAX 重发即终态）；已知边界：snooze 过期后重启静默丢弃（notify 无害，接受）。**跳过本次**：内存 next_due 即时推进（interval→+interval；daily→下个匹配日；once→MAX），不触发不记录；snooze_until 未过期则一并清空（N2，写表+内存同清）。
3. **ActionExecutor（新模块 action_exec.rs）**：`ActionOutcome{status: Ok|Failed|Skipped, summary, output_tail?, exit_code?}` + trait `validate(&Value) -> Result<(), String>` + `async run(&Value, RunCtx) -> ActionOutcome`；NotifyExecutor 薄壳（触发即 ok，编排走既有 reminder://trigger）；ExecExecutor——validate：command 非空 ≤2000 字符、cwd 可选（存在则须为目录）、timeout_minutes 1–120 缺省 10、opencode_auto bool 仅校验不改命令；run：`sh -c`（Unix）/ `powershell -NoProfile -Command`（Windows，同构实现实机挂观察项）、cwd 生效、**进程组 kill**（Unix setsid + kill −pgid；Windows taskkill /T /F——Cargo 新增 libc 依赖、tokio features +process）、输出 stdout+stderr 合并攒 buffer 超 2KB 保尾部（截尾标记 `…(已截断)`）、超时杀进程组→Failed「超时（N 分钟）被终止」output_tail 保留、async tokio 进程 + 独立 spawn 任务（调度器 tick 不等待）+ RunCtx 携 action_log_id 完成回写 + 完成先从登记表移除/Exit 只处置登记表句柄（N7 防竞写）。分派注册表 action_type → Box<dyn ActionExecutor>。「试一试」对 exec 行=真实执行一次（force_fire_one 接分派，受暂停/去重约束）。
4. **exec 执行链**：tick 判定到期（补跑窗内）→ 并发满 2 进内存等待队列（RemindersState.pending_execs，不写 running；空位出现 channel 通知出队 spawn）→ insert action_logs(running) → 通用层伪 session `apply_event("task:<log_id>", Working)` + `DisplayNotifier::notify`（agent=常量 "task"，Rust 内部直连不经 HTTP 白名单；不更新 AgentActivity、不触发 idle_hook；M2 芯片 agent=="task" 显示「定时任务」panel.agentTask）→ spawn 执行（期间每 15s 重 apply Working + notify 心跳保鲜防 30s idle 回收，P2-9）→ 完成/超时 → update action_logs → 终态 apply（exit 0→Success；非 0/超时→Error，30s 自然回收）+ notify → 结果气泡 `emit_to("pet","pulsepet://task-result",{text, logId, status})`（**独立事件 P1-3**，不复用被 M2 冻结为 info 级的 pulsepet://bubble；桥层 critical 入队 source="task:<log_id>"；无 reminder 载荷——点宠物即消、不写 reminder_logs、无 snooze 按钮）→ text = 任务名 + summary（lib.rs 拼接，summary 存 i18n 模板键按当前语言渲染 P3-3）。agent 层免费（spawn 的 opencode run 加载 pulse-pet-hook.js 细粒度状态正常上报，真实 session key 平等参与优先级合并；已知双 emit P3-7 接受）。`RunEvent::Exit` 处置（P1-2）：遍历运行句柄 kill 进程组 + action_logs 补写 failed（「App 退出中断」）；启动时 running 态幂等清理（崩溃残留 R5）。例程会话进 opencode.db，`--title "pulsepet 例程: <任务名>"` 在 Token 页可辨识（来源标注留 M5）。
5. **opencode 一等模板（UI 辅助，执行层不感知）**：表单动作类型选「执行命令」出现「opencode 例程」快捷块一键填充——command = `opencode run --title "pulsepet 例程: <任务名>" [--auto] "<指令>"`、cwd、timeout 10；--auto 由 checkbox「自动放行权限（危险）」控制（默认不勾，勾选危险色警示）；模板仅填表辅助，产物与手写无差异；不用 --dir（cwd 字段即工作目录）。
6. **UI 合并「定时任务」tab + snooze 按钮**：核心 tab「提醒」→「定时任务」（panel.tab.tasks，位置不变；panel://tab 兼容旧值 reminders 映射直达）；Reminders.tsx → Tasks.tsx 改名重构——一张列表（动作徽标 💧/⚡ title 说明 + 名称 + 调度摘要「每 30 分钟 · 09:00-18:00」/「每天 09:00」/「周三、五 09:00」/「一次 · 08-25 21:00」+ 启用开关 + 行操作 编辑/试一试/跳过本次/删除两步确认；todo 派生行保持 M2 展示）；表单完整重做按 action_type 条件显隐（notify：kind/文案/调度/烟花；exec：任务名/模板块/command 等宽多行/cwd/超时/调度/--auto 随模板）；Rust validate 权威 + 前端同规则预检（v1 模式）；执行历史区（列表下方折叠面板，action_logs 倒序 分页 50 条/页 `action_logs_list(reminder_id?)`，行=时间/徽标/summary/状态色点 ok 绿·failed 红·skipped 灰·running 蓝，展开 output_tail 等宽 + scheduled_at 与 started_at 差）；snooze 按钮（M2 气泡扩展——critical 且 reminder 载荷时右侧小按钮 hover 浮现，点击 invoke reminders_snooze 气泡即消；点宠物仍=确认）。新命令：reminders_snooze / tasks_skip_once / action_logs_list。
7. **i18n**：`tasks.*` 命名空间（表单/徽标/摘要/历史/模板/snooze）+ `panel.tab.tasks` + `panel.agentTask`（芯片「定时任务」）+ summary 模板键（ok/failed(N)/timeout/skipped/退出中断——存模板键展示按当前语言渲染）+ `reminders.*` 存量保留；zh/en 键集合一致（完备性测试守护）。

**不含（§4.1/§4.13）**：webhook/平台自动化等未来动作类型、对话入口、M2 气泡排队重做（消费 M2 critical）、todo 派生行迁移、notify 型写 action_logs、补跑窗按动作分长、独立 tab（不合并）、调度器多线程重写。Windows 实机验证挂观察项（TC-M4-18，macOS 先行、分支同构实现）。

**开发纪律**：分支 develop_opencode（当前 HEAD=e7291c3 领先 origin/develop（53e447f）仅流程检查点提交，开工先 fetch + merge origin/develop 确认无新提交）；提交信息 `[task-pulsepet-v2-m4] R<n>`；cargo 网络用 CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP2=false；新代码日志一律 plog!；每轮验证证据必含 tauri build 成功 + 产物时间戳；依赖变更：tokio features +process、新增 libc（tauri 依赖树既有 crate）；迁移走 migrations/003 + SCHEMA_VERSION=3（编译期断言）。

## 验收标准（V2-TEST-CASES 四、TC-M4-01~18 + V2-DESIGN §4.11）

- **TC-M4-01 迁移 003 与 v1 兼容（单测+实机）**：幂等（2→3 执行/3 跳过，事务化 A1）；SCHEMA_VERSION=3 编译断言；+7 列 + action_logs 表；v1 存量行默认值 + 行为零变化（原提醒可见可编辑、interval 窗口/去重/暂停顺延/烟花叠加 TC-RM 回归）；action_params JSON 解析失败 validate 拒绝
- **TC-M4-02 合并 tab（实机）**：改名「定时任务」位置不变 + panel://tab 旧值兼容；一张列表（徽标/摘要/开关/行操作四件套 + todo 派生行 M2 展示）；表单条件显隐 + validate 权威前端预检；notify 新建三调度触发与 v1 等价
- **TC-M4-03 调度纯函数（单测）**：daily（当日未到/已过/跳过不匹配星期/NULL=每天）；once（未来/已触发已跳过→MAX/过去 validate 拒绝）；补跑窗边界 14m59s 触发/15m01s skipped；snooze 重发语义（优先置非 max；once 重发后 MAX/daily 下匹配日/interval 链顺延——P1-1 回归钉子）+ 触发清空；reload 错过检测（跨过 schedule_at 窗内补跑/超窗 skipped；last_triggered 已晚不误报）；interval 分支 v1 断言全量保留
- **TC-M4-04 collect_due 与 skipped 闭环（单测）**：到期窗内触发；超窗 skipped（exec 落库/notify 不落/均不弹）；N1 闭环（两来源写 last_skipped_at + 推进 + dedup 不拒手动补跑 + 暂停每 tick 只记一次 + reload 不重复 + once skipped 重启仍 MAX + (fired, skipped) 返回落库）；N2 跳过清空未过期 snooze_until（写表+内存）；暂停分支（interval 顺延回归/daily-once 记 skipped 且恢复不补）；并发上限 2（第 3 个入 pending_execs 不写 running；完成 channel 通知出队）
- **TC-M4-05 定点触发（实机）**：daily 1 分钟后到点执行；once 触发后列表完结；星期过滤今天+1 → 下周才触发
- **TC-M4-06 exec 执行链（实机）**：echo ok 秒级成功+气泡「任务完成」；exit 3 failed(3)；sleep 600 超时 1 分钟进程组被杀（ps 无残留）+failed+output_tail 保留；输出洪水截尾 ≤2KB（`…(已截断)`）内存不膨胀；sh -c + cwd 生效 + 独立 spawn 不阻塞 tick
- **TC-M4-07 validate 规则（单测）**：command 非空 ≤2000；cwd 可选须目录；timeout 1–120 缺省 10；opencode_auto bool；kind 切换重置无关字段（含清窗口防 in_window 卡住误 skipped）；once 过去拒绝；JSON 失败拒绝
- **TC-M4-08 opencode 模板（实机）**：拼 command 逐字（--title/--auto 可选默认不勾危险色/--dir 不用）；模板仅填表辅助；真实例程（数 md 文件）→ 宠物细粒度状态随 agent 层变化（R9 首日验证）→ 终态+气泡+Token 页「pulsepet 例程:」会话（--title 是否被自动摘要覆盖=实测回填）
- **TC-M4-09 权限行为（实机 S1 复验）**：不带 --auto 触发权限任务不卡死（警告行进 output_tail 自动拒绝按拒绝结果继续/失败）；带 --auto 放行
- **TC-M4-10 宠物状态两层（单测+实机）**：通用层 working/success/error（30s 回收）；伪 session task:<log_id>（内部直连不经白名单；apply+notify 成对断言；不更新 AgentActivity/idle_hook mock 零调用）；心跳 15s（注入时钟：正常不回收/延迟>15s 回收可观察）；agent 层优先级合并（task working(1)/success(2) 低于 editing(4)/testing(5)；error(7) 抢镜一次接受；双 emit 记录级）；芯片「定时任务」
- **TC-M4-11 结果气泡边界（实机）**：pulsepet://task-result 独立事件 critical 入队 source=task:<log_id>；无 reminder 载荷（点宠物即消/不写 reminder_logs/无 snooze 按钮）；text=任务名+summary 按语言渲染
- **TC-M4-12 补跑与暂停（实机）**：睡眠醒后 15min 内补跑一次/超窗 skipped 记录；App 关闭跨过 schedule_at 重启同口径（reload 检测）；暂停到期记 skipped 恢复不补；interval 睡眠/暂停维持 v1（TC-RM-02 回归）；notify/exec 同窗（用户单一口径）；观察项 R1 连环补跑记录级
- **TC-M4-13 snooze（实机+单测）**：hover 按钮→点击 invoke（气泡即消/log 结案 snooze/snooze_until 写表+next_due 置为）；10min 内重启重发仍有效（过期重启丢弃=已知边界记录级）；重发清空按 kind 推进（once 完结/daily 下匹配日/interval 顺延）；点宠物仍=确认（via='bubble'）；仅 notify；暂停交互（interval 被顺延吞没/daily-once 记 skipped）
- **TC-M4-14 跳过本次（实机+单测）**：daily 跳过本周期不触发下匹配日正常；once→MAX 完结；UI 可见不触发不记录；snooze 未过期一并清空（写表+内存）；已知边界 once 跳过+补跑窗内重启会补跑（接受记录）
- **TC-M4-15 退出处置与崩溃清理（实机+单测）**：Exit 遍历句柄 kill 进程组（ps 断言无残留）+ 补写 failed「App 退出中断」；完成先移除登记表/Exit 只处置登记表（防竞写单测钉住）；启动 running 幂等清理；崩溃孤儿残留已知边界记录级
- **TC-M4-16 执行历史区（单测+实机）**：倒序分页 50/页可过滤；行四件套+状态色点；展开 output_tail 等宽 + 补跑延迟可见；规则删除历史保留（悬空 id + 冗余快照）；tempdir 增删查全链路单测
- **TC-M4-17 双语与深浅主题（实机）**：tasks.* + panel.tab.tasks + panel.agentTask zh/en 完备；summary 模板键双语渲染；新元素全落 M2 token
- **TC-M4-18 Windows 分支（实机挂观察项）**：powershell 执行/taskkill 杀树/特殊字符警告（R3）；macOS 先行不阻塞收尾
- **并入项（M3 移交 P2）**：面板 Token 页数据 App 启动时刻定格修复——仿 Settings.tsx:164 `tauri://focus` 双触发（面板可见时刷新 TokenStats），长运行 App 首开面板 TC-M3-11「无缝衔接」/TC-M3-12 交叉断言成立；含相应验证（实机：长运行后首开面板数据为打开时刻近实时值）
- **并入项（M3 移交 P3-4 顺手清理）**：todayToken.ts resetTodayCache 死导出删除（悬停卡移除后无调用方，2 行；含相关测试同步）
- 回归基线：npm test（vitest 351 基线 + 新增）全绿；cargo test（236+1 ignored 基线 + 新增，含迁移/调度/action_exec/伪 session/集成 tempdir）全绿；npm run build / tauri build（产物时间戳）成功；TC-RM 提醒回归 + 既有纯函数测试不破坏

## 需求确认
- [x] 用户已确认（确认后 status=implementing）——2026-08-25 20:02 用户确认：① M4 范围照 V2-DESIGN §4 定稿执行（含两项并入修复：M3 P2 面板数据定格 tauri://focus 双触发 + M3 P3-4 resetTodayCache 死导出清理）；② 其余遗留事项维持原去向移交；③ M2 目验 7 项本轮无反馈继续移交；无范围调整
- 历史遗留事项清单：（supervised-coding 扫描 task-pulsepet-v2-m1/m2/m3 检查点汇总，默认并入本任务，见 README §4.6）

## 遗留事项（跨任务移交）

- [x] ~~**并入本任务——M3 P2 面板数据定格（来源 task-pulsepet-v2-m3，committer 定级去向=M4 面板改动轮）**~~：TokenStats.tsx load 仅挂载执行 + panel visible:false 隐藏创建即挂载 → 长运行 App 首开面板数据为启动时刻快照；修复=仿 Settings tauri://focus 双触发（已写入验收标准并入项）——**已清偿**：R1 双触发接线 + R3 补 range.toMs 挂载定格（load 重算窗口），tester R3 实机双向复现验证通过
- [x] ~~**并入本任务——M3 P3-4 resetTodayCache 死导出（来源 task-pulsepet-v2-m3，可选清理顺手清）**~~：todayToken.ts:19 悬停卡移除后无调用方，2 行删除 + 测试同步（已写入验收标准并入项）——**已清偿**：R1 删除，tester R1 grep 零命中验证
- [ ] **v2-m2 实机目验 7 项（来源 task-pulsepet-v2-m2 经 v2-m3 移交，去向=用户反馈）**：TC-UI-01 主题三档 / TC-UI-03 面板壳+芯片 / TC-UI-06 双 agent 芯片跟随 / TC-UI-07 功能管理禁用 Todo 全链路 / TC-UI-10 气泡排队实机 / TC-UI-11 气泡与右键菜单视觉 / TC-UI-12 四 tab 对照样例目验——**本轮继续待用户反馈**（发现问题随本轮修复；无反馈继续移交）
- [ ] **v2-m2 P3-5（经 v2-m3 移交，去向=M5 或打磨轮——动 atlas.rs 时顺手清）**：atlas.rs AtlasData Clone derive 死代码——M4 不动 atlas.rs，继续移交
- [ ] **v2-m2 P3-6~10（去向注明，不并入）**：P3-6 notice 重复计算 + P3-7 禁用语汇四套不一致（CSS/微打磨轮）；P3-8 插件开关失败静默 + P3-9 panel://tab 冷启动竞态（UX 观察项）；P3-10 Rust 命令错误串未 i18n（M8 类约定扩展时）
- [ ] **v2-m1 遗留（去向已注明，不并入）**：A 实机验证类（多屏/Windows，具备硬件时——M4 的 TC-M4-18 Windows 同批）；B v0.1.3 收尾用户目视验收（待用户反馈）；C v0.1.3 Release publish（待用户指示）；D 观察项（默认不动）
- [ ] **M3 P3-1/2/5（去向已注明，不并入）**：P3-1 idle 汇报追加段 220px 气泡单行截断（气泡文案/CSS 打磨轮）；P3-2 合成事件测试工具限制（记录）；P3-5 plugin-hook.test.ts:763 注释草稿痕迹（打磨轮）
- [x] ~~M3 P3-3 V2-DESIGN §3.8 陈旧措辞~~（已随 v2-m3 回 spec 提交 562879a 清偿，PR #15 已合入）
- [ ] **M4 新移交（2026-08-26 终审 committer 定级，PR #16 已合入）**：
  - **P3① logging.rs ends_with("x"×64) 残余竞态**（并行 plog! 在 write 与 set_file 间写旧句柄 → .old 尾部污染偶发；19 轮全绿统计倾向改善未完全证明）——**去向=打磨轮**（建议测试专用助手持全局 slot 锁内轮转，或删 ends_with 只留 len>=）
  - **P3② action_exec.rs:622-635 注释块复制粘贴重复**（外观）——**去向=打磨轮顺手清**
  - **P3③ 理论双记账边界**（reload 命中 µs 窗口 + 补跑窗尾 + 队列满三巧合叠加 → 下 tick 记 skipped 且排队条目仍执行，概率趋零）——**记录级，不修**
  - **Windows 实机**（TC-M4-18：powershell/taskkill 分支同构实现已落地，实机验证挂观察项——与 TC-INT-13/TC-M4-18 同批，具备硬件时）
  - M2 目验 7 项继续待用户反馈（见上）
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录
- R1（第 1 次调用，2026-08-25 20:03 用户确认后调用）：**网络中断，Task 被取消**。用户 20:48 提示从 opencode.db 找回 task_id：`ses_fc7318cdbffeTnHwAfnBTQpShw`（"v2 M4 R1 实施 (@Coder subagent)"，20:04 创建、活动约 37 分钟），已写入 frontmatter。中断现场（supervised-coding 查证）：develop_opencode HEAD=e7291c3 **未 commit**；半成品改动 = Rust 侧已开工——`M pulse-pet/src-tauri/Cargo.toml + Cargo.lock`（依赖）、`M db.rs`（+120 迁移接线）、`M i18n.rs`（+106）、`M lib.rs`（+23）、`M reminder_scheduler.rs`（+1124 大改）、`?? migrations/003-m4-tasks.sql`、`?? src/action_exec.rs`（新文件未跟踪）；前端 src/ 未开始；7 文件 +1254/−142。处置：**续接该会话继续 R1**（恢复语义按 .opencode/README.md §4.3）。
- R1: coder 完成（网络中断后同会话续接），commit `b5321bf`（`[task-pulsepet-v2-m4] R1: v2 M4 定时任务（动作泛化 notify/exec）——迁移 003 + 调度 daily/once/补跑窗/snooze/skipped 闭环 + ActionExecutor 执行链 + 合并 Tasks tab + snooze 按钮 + 执行历史`，commit 前 fetch 确认 origin/develop=53e447f 无新提交；supervised-coding 已核验 HEAD=b5321bf、25 files +5386/−712、工作区干净仅流程文件）。改动七块全量——**中断前段（Rust）**：003-m4-tasks.sql（+7 列+action_logs 悬空 id+冗余快照）；db.rs（M4_SQL 接线+SCHEMA_VERSION=3+MIGRATIONS 追加+4 测试：幂等/列默认值/半途回滚/表数）；action_exec.rs 新 1246 行（trait validate+async run→ActionOutcome、Notify/Exec 实现、分派注册表、RunningTasks 登记表 N7、伪 session task_apply apply+notify 成对/不污染 AgentActivity、15s 心跳、并发 2/pending_execs/出队、TailBuf 2KB 尾部、Unix setsid/kill(−pgid) 组杀+Windows taskkill 分支、cleanup_running_logs R5、abort_all_on_exit P1-2）；reminder_scheduler.rs +1859（compute_next_due 按 kind+snooze 优先 P1-1；CATCHUP_WINDOW_MS=15min；collect_due→(fired,skipped)；暂停按 kind（interval 顺延/daily-once 记 skipped+清 snooze P3-5）；skip_once N2 写表+内存同清；normalize_input（kind 切换重置 P2-6/daily-once interval 恒 0/once 过去拒绝/exec JSON+注册表校验）；mark_skipped/mark_triggered 清 snooze；action_logs 增删查分页；新命令 reminders_snooze/tasks_skip_once/action_logs_list；spawn_scheduler select 完成通知出队）；i18n.rs（render_task_summary 模板键双语渲染+task_result_text）；lib.rs（启动 running 幂等清理+RunningTasks manage 窗口创建前 issue #9+命令注册+RunEvent::Exit→abort_all_on_exit）；Cargo（tokio +process/macros/sync+libc）。**恢复段（前端）**：i18n.ts（tasks.* 60+ 键 zh/en+panel.tab.tasks+panel.agentTask+task.summary.*）；reminders.ts（ReminderRule+7/ReminderInput+5/validateReminderInput M4 分支/actionBadge/scheduleSummary/buildOpencodeCommand/shellQuote/renderTaskSummary/parseWeekdays/snooze/skip/fetchActionLogs）；reminder-bridge.ts（snooze 结案+task-result 监听→critical 入队 source=task:\<logId\> 无 reminder 载荷）；petStore（snoozeReminderBubble via='snooze'+2 测试含 exec 结果气泡永不 snooze）；Bubble.tsx（critical 且 reminder 载荷 snooze 按钮 hover 浮现）；Tasks.tsx 新 930 行删 Reminders.tsx 489（一张列表徽标+摘要+开关+四件套+todo 派生行 M2；条件表单 notify 三分支/exec 模板块+command 等宽+cwd+超时；历史折叠面板倒序 50/页+过滤+色点+展开 output_tail+补跑延迟）；registry/Panel（tab id reminders→tasks+normalizeTabId 旧值映射+芯片 agent=="task"→panel.agentTask N4）；interaction（PanelTab+tasks+normalizeTab 映射）；**并入修复①**TokenStats.tsx tauri://focus 双触发；**并入修复②**todayToken.ts resetTodayCache 删除；global.css（snooze/task-badge/模板/command 等宽/星期行/历史区 250 行）。自测证据：npm test **368 passed/27 files**（基线 351+17）；cargo test **274 passed+1 ignored**（基线 236+38）；tsc exit 0；npm run build ✓；tauri build 成功（PulsePet.app @21:24:48/dmg 4.6M @21:25:08）；cargo check 0 warning。裁定点 5 条：① running 色点固定蓝 #4a7fb5（M2 无蓝 token，两主题固定色值）② dispatch_exec 测试进程清理 ③ exec 行 use_fireworks 清 false+表单无烟花/时间窗（Rust normalize 双保险）④ 前端 cwd 宽松放行（Rust 权威拦截，键 cwdNotDir 留报错透传）⑤ 实机类用例留 tester。无需求边界问题。
- R1 补充轮（2026-08-25 22:10 用户目验 R1 产物后提出 5 点 UI 改动）：① tab 中文显示名「定时任务」→「例程」、「Todo」→「待办」（英文 coder 定，建议 Routines/Todo）；② 「新建」按钮从单独一行移至「新建提醒」表单块右下角；③ 「新建」按钮换合适的非默认色；④ 表单标题「新建提醒」→「新建例程」；⑤ 表单动作类型按钮去图标（提醒去 💧、执行命令去 ⚡；列表行徽标保留）。**验收口径变化已由 supervised-coding 落笔**（2026-08-25 22:15）：V2-DESIGN §4.7 修订注记 1 处 + V2-TEST-CASES TC-M4-02 预期 1/3 + TC-M4-17 预期（含 TC-UI-07/12 波及面注记）。status: testing → implementing（补充轮），round 不变，testedSha 保持 null 待新 HEAD。
- R1 补充轮: coder 完成（同会话续接），commit `067a2d3`（`[task-pulsepet-v2-m4] R1: 补充——tab 改名例程/待办 + 新建按钮右下角换色 + 表单去图标（用户 2026-08-25 5 点 UI 裁定）`，commit 前 fetch 无新提交；supervised-coding 已核验 HEAD=067a2d3、7 files +100/−16）。改动：i18n.ts（zh：tab.tasks→例程/tab.todo→待办/newTitle→新建例程/editTitle→编辑例程/tasks.rules.title→例程（{n}）/empty 同步；en：Routines/Todo/New routine 等）；Tasks.tsx（分段按钮去 💧/⚡ 仅表单内**列表徽标保留**；动作行类名→task-form-actions）；registry.ts+Panel.tsx（新 PLUGIN_TAB_LABEL_KEYS 覆盖机制——built-in-todo→panel.tab.todo，manifest title 双语单值不改走前端 i18n 覆盖，无覆盖插件 tab 原样直显约定不变）；global.css（.task-form-actions 右下角 flex-end + 主按钮 accent 色系——浅色蜜橘 #d96c2c/深色青 #62c6c0 与激活 tab/KPI 首卡同族非默认 ink 色 + hover accent-ink 加深；.reminder-form-actions 原样零波及）；i18n.test.ts +1（改名键防回退钉子）；registry.test.ts +2（覆盖机制钉子）。自测：npm test **371 passed/27 files**（368+3）；tsc 0；npm run build ✓；tauri build 成功（PulsePet.app @22:25:16/dmg @22:25:36）；Rust 零 diff 未跑 cargo。**待验对象更新为 067a2d3**（提交链 b5321bf→067a2d3）。裁定点 3 条待用户：① **panel.agentTask 芯片「定时任务」未动**（与新 tab 名「例程」不一致——语义自洽但可统一，交用户裁定）② 联动文案取舍（rules.title/empty 改例程，stats/toast 未动）③ Todo 改名走覆盖机制 6 行（非改 manifest）。
- R1 补充轮 2（2026-08-25 22:30 用户裁定 2 点）：① 状态芯片 `panel.agentTask`「定时任务」→「例程」（en 建议 Routine）；② 「新建」按钮再上移——不占单独动作行，**与表单最后一行字段同行对齐**（上一轮仅 flex-end 仍独占动作行，用户指出不符合"非单独一行"意图）。**验收口径变化已由 supervised-coding 落笔**（2026-08-25 22:34）：V2-DESIGN §4.7 二次修订注记（⑤⑥）+ V2-TEST-CASES TC-M4-02 预期 3（同行对齐）/TC-M4-10 预期 5（芯片例程）/TC-M4-17（芯片口径）。status: testing → implementing（补充轮 2），round 不变。
- R1 补充轮 2: coder 完成（同会话续接），commit `bef21cc`（`[task-pulsepet-v2-m4] R1: 补充——芯片文案例程 + 新建按钮并入表单末行（用户 2026-08-25 二次裁定）`，commit 前 fetch 无新提交；supervised-coding 已核验 HEAD=bef21cc、4 files +74/−30）。改动：i18n.ts（panel.agentTask zh 例程/en Routine 单数对齐芯片语境与 tab Routines 刻意区分）；Tasks.tsx（按钮组抽 formActions 变量**删独立动作行**，按分支互斥并入实际渲染末行字段行右端——once/interval+exec→调度行、interval+notify→时间窗行、daily→星期行，四注入点条件互斥恰渲染一次；todo 编辑态锁定表单无字段行→按钮组 flex-column 右下角 margin-left:auto）；global.css（.task-form-actions 行内形态 inline-flex+margin-left:auto+align-self:flex-end 底缘与 32px 输入框对齐、.task-weekdays 下 center 覆盖、独子项场景 flex 右对齐；accent 主按钮保持；.reminder-form-actions 零波及）；i18n.test.ts +1（agentTask 例程/Routine 防回退钉子）。自测：npm test **372 passed/27 files**（371+1）；tsc 0；npm run build ✓；tauri build 成功（PulsePet.app @22:40:17/dmg @22:40:38）；Rust 零 diff 未跑 cargo；DOM 自查 grep task-form-actions 定义 1+注入 4、非 todo 分支无独立动作行。**待验对象更新为 bef21cc**（提交链 b5321bf→067a2d3→bef21cc）。裁定点 3 条：① todo 编辑态分支按钮组右下角近似（唯一渲染行不与提示语争行）② cross-midnight 提示在窗口行下方（非字段行未视为违反）③ en Routine 单数 vs tab Routines 复数刻意区分。
- R1: tester 验证 **FAIL**（testedSha=bef21cc，testerTaskId=ses_fc69fe5abffegUuJH6i9bI9jhO；**16 PASS / 1 FAIL / 2 PENDING-USER / 1 SKIPPED**）。独立复跑基线全一致（vitest 372/27、cargo 274+1i、tsc 0、产物时间戳逐秒吻合）。PASS 亮点：TC-M4-02（tab 例程/待办+按钮同行对齐+蜜橘橙实机确认）、05（daily 准点/once 完结/星期过滤下周）、06（exec 全链：60.0s 整杀组 ps 无残留/洪水 2054B 截尾/cwd 生效）、08（**--title 未被自动摘要覆盖，R8 可行性成立**，132 md 真实例程）、09（auto-rejecting 不卡死实机复验）、10（芯片「例程 · working」修订口径）、12（补跑三径：reload 窗内补跑/超窗 skipped/暂停冻结恢复不补）、13（snooze 持久化重启重发实机；按钮点击降级单测覆盖）、14（跳过+已知边界复现×2）、16（历史区+悬空保留）、01/03/04/07 单测真实性核验、并入② grep 零命中。**FAIL 项：TC-M4-15-1（P2 IMPL_BUG）**——abort_all_on_exit 先 kill 后写库（WHERE status='running'），被杀进程唤醒的 async 完成回调 finish_action_log_with **无 status 守卫**抢先写入通用 task.summary.failed，「App 退出中断」interrupted summary 落空（实机 1/1 复现）；建议：abort 先 UPDATE 再 kill 或完成回写加 running 守卫 + 真实进程集成钉子。**PENDING-USER×2**（显示器 00:10 自动锁屏阻断非缺陷）：TC-M4-17 en/深色主题目验、并入① 长运行首开面板近实时实机——解锁后补验。P3 观察项：critical 未抢占 ambient 单次现象（疑 webview 事件延迟，记录级）。环境已恢复（进程杀净/测试 21 规则+33 logs 清理/app_state 默认/opencode.db 只读/106 截图临时目录留档）。**处置：status=fixing→implementing，round 1→2，reviewedSha 置空，Tester 报告原文交 Coder 修复**。
- R2: coder 修复完成（同会话续接），commit `5259d43`（`[task-pulsepet-v2-m4] R2: 修复退出处置 summary 竞态（abort 先写库后 kill + 完成回写 status 守卫 + 真实进程集成钉子）`，commit 前 fetch 无新提交；supervised-coding 已核验 HEAD=5259d43、2 files +173/−4 纯 Rust）。改动：reminder_scheduler.rs（finish_action_log_with 加 `WHERE id=? AND status='running'` 守卫 + 新测试 finish_action_log_with_guarded_by_running_status：ok 结案后迟到 failed 不覆盖+interrupted 后通用 failed 不覆盖）；action_exec.rs（abort_all_on_exit **调序：先写库（interrupted，WHERE status='running'）→ 后 kill_process_tree** + 新测试 abort_exit_race_real_process_keeps_interrupted_summary——**真实进程集成钉子**：run_task 真实 sleep 597 进程+真实 async runtime 执行中调 abort_all_on_exit，join 完成回调走完断言终态 task.summary.interrupted）。竞态消除机制：两写入方以行状态为单调屏障——abort 先占行（status 离开 running），完成回调守卫 UPDATE 落 0 行；反向自然完成先落库由 abort 侧同款守卫兜底（真跑完任务保留真实 summary 语义正确）；与 N7 登记表语义自洽（完成先移除登记表；abort drain 后 remove no-op）。**钉子反证（TDD）**：临时回退修复→钉子以预期理由失败（left task.summary.failed/right interrupted，与实机缺陷形态逐字一致）→恢复全绿。自测：cargo test **276 passed+1 ignored**（274+2）；npm test/tsc 未跑（前端零改动说明合理）；tauri build 成功（PulsePet.app @19:14:43/dmg @19:15:03/二进制 19:15:03）。裁定点 2 条：① 双保险方案（调序+双侧守卫——仅守卫不调序时 kill 唤醒回调极快 abort UPDATE 可能晚到行停留通用 failed 缺陷仍在，调序后 interrupted 必然先占行，任意交错序收敛正确终态）② docs 修订未入 commit（归交付阶段统一提交）。**待验对象更新为 5259d43**（提交链 b5321bf→067a2d3→bef21cc→5259d43）。
- R2: tester 焦点复验 **FAIL**（testedSha=5259d43，同会话；**焦点 1 PASS / 焦点 2-① 全过 / 焦点 2-② 新 P2 缺陷**）。独立复跑基线一致（cargo 276+1i、vitest 372/27、产物 19:14:43/19:15:03 逐秒吻合）。**焦点 1（上轮唯一 FAIL 竞态）已修复并实机钉住**：sleep 600 运行中退出 App → ps 无残留 + summary=task.summary.interrupted（2/2 实机，含 en 切换重启自然触发样本）；双钉子真实性核验（真实进程+真实 runtime 三方竞态 / SQL 守卫语义）+ TDD 反证逻辑必然性成立；反向语义抽查（echo 自然完成后退出 → ok 保留不被 interrupted 覆盖）✓。**焦点 2-①（en+深色目验）全部通过**：Routines/Todo/Settings、New routine、Create 与时间窗行同底缘对齐（OCR y 0.213/0.215）、分段无 emoji、蜜橘橙/深色青 accent、芯片 Routine · working、snooze ⏱10min hover 浮现、en summary 字典逐字、深色可读性；验后恢复 zh/light。**焦点 2-② 首开近实时 PASS**（8.5min 后首开 KPI 163.8M vs sqlite 推算 160.8M 误差<0.1%，启动快照应 13.3M 确非快照）；**但二次打开/Refresh FAIL——新发现 P2（IMPL_BUG）**：TokenStats.tsx range useMemo 依赖不含 now → toMs 挂载定格；面板 hide/show 不重挂载 → 活跃会话 time_updated 越过定格 toMs 后被 `time_updated <= toMs` 整体排除且 Refresh/重开不可追回（双向复现 100%：KPI 69.0M vs DB 166M+，deepseek 107M 消失；重启首开恢复 107.2M 再关开又消失）。修复建议：load() 内重算 toMs（range 依赖注入 now）或查询 toMs 加秒级余量。环境已恢复（语言/主题 zh/light、测试数据清理、opencode.db 只读）。**处置：status=fixing→implementing，round 2→3（最后一轮），reviewedSha 置空，报告原文交 Coder 修复**。
- R3: coder 修复完成（同会话续接），commit `8d9b323`（`[task-pulsepet-v2-m4] R3: 修复 Token 页 range.toMs 挂载定格（load 时重算窗口，二次打开活跃会话可追回）`，commit 前 fetch 无新提交；supervised-coding 已核验 HEAD=8d9b323、3 files +69/−14 纯前端）。改动：token-stats.ts（新纯函数 resolveQueryRange(preset, fromStr, toStr, now)——preset→rangeForPreset toMs=调用时刻 now 可注入；custom→用户指定整天边界与调用时刻无关**自定义区间语义原样保留**）；TokenStats.tsx（**删挂载定格的 range useMemo（缺陷根源）**，load 内每次 resolveQueryRange(..., new Date()) 重算——挂载/focus 双触发/Refresh 三路径统一走 load，toMs 均为当前时刻；useCallback 依赖同步；清退 rangeForPreset/localDay* 旧 import）；token-stats.test.ts +3 钉子（TDD 先红：resolveQueryRange is not a function→实现全绿）：① preset 后一次调用 toMs 前进（T0 10:00→T1 18:30 from 锚定不变）② custom now 前进 8.5h 结果全等整天边界 ③ custom 倒填 min/max 归位。自测：npm test **375 passed/27 files**（372+3）；tsc 0；npm run build ✓；tauri build 成功（PulsePet.app @19:54:38/dmg @19:54:59/二进制 19:54:59）；Rust 零 diff 未跑 cargo。裁定点 3 条：① 未采纳秒级余量方案（治标，余量耗尽仍丢会话；load 重算彻底消除）② range useMemo 整体移除（唯一消费方是 load，窗口语义单点收敛 resolveQueryRange）③ focus 刷新 effect 与窗口重算正交叠加（focus 管何时刷/resolveQueryRange 管窗口对不对）。**待验对象更新为 8d9b323**（提交链 b5321bf→067a2d3→bef21cc→5259d43→8d9b323）。
- R3: tester 焦点复验 **PASS**（testedSha=8d9b323，同会话）。独立复跑基线一致（npm 375/27、cargo 276+1i、tsc 0、产物 19:54:38/59 逐秒吻合）。**R2 唯一 FAIL（toMs 定格）已修复并实机双向复现验证**：① 长运行 90s 首开 KPI 204.2M vs DB 实时 201.5M（13s 增量吻合近实时）；② 关开面板 205.6M **上涨不消失**（R2 缺陷形态骤降 69.0M 未再出现）；③ 多轮关开×2 持续上涨；④ 跨 70s Refresh 207.4M vs DB 204.3M（3s 差）追回正常；⑤ 会话级在场核对 deepseek 129.6M 完整在场；custom 区间语义不回归（整天边界对账吻合、关开不漂移）。三钉子真实性核验（toMs 前进/custom 全等/倒填归位——与缺陷语义严格对应）+ 代码机制核验（resolveQueryRange 纯函数+删 range useMemo+load 内重算三路径统一）。回归抽查：首开近实时不回归/今日 preset 正常/focus 与窗口重算正交。无新缺陷。环境已恢复（zh/light/测试数据清理/opencode.db 只读）。**testVerdict=PASS——M4 全部验收项闭环**（R1 16 PASS 含 2 项 PENDING 已在 R2 补验 + R2 焦点修复 + R3 焦点修复）。status→reviewing，调 Committer。
- R3: committer 审查 **NEEDS_CHANGES**（reviewedSha=8d9b323，committerTaskId=ses_fc2033415ffet4PQG0eKsT8iRI；**P0/P1 无**）。评审对象核对全过（提交链 5 提交逐吻合、净 28 files 全在 pulse-pet/ 内、依赖 libc/tokio 既有 crate、迁移事务化+编译断言）；需求对应性 7 块+2 并入+2 轮裁定全 ✅（不含项零预实现）；代码质量（SQL 参数化/锁纪律/竞态双保险与 N7 自洽/plog! 零新增/删除残余零命中/伪 session 结构性隔离）；测试质量（三轮 tester 采信 + 静态计数交叉核 cargo 236→276=+40 / vitest 351→375=+24 严格吻合 + 断言真实性抽查 + 既有测试零削弱）。**问题清单：P2-1（阻断，新发现）并发上限 2 为竞态软上限，批量分派可超发**——上限判定读 RunningTasks.len() 但登记表条目在 spawn 任务首个 poll 才异步插入，run_tick 同步循环与 drain 无 await 循环中多次 dispatch 读 len 均不含刚分发任务，第 3 个不保证入 pending_execs（多线程 runtime 下竞态；触发场景真实：多条 daily 同 HH:MM、睡眠后连环补跑 ≥3）；违反 §4.5「并发满 2 进等待队列」+ TC-M4-04-5 批量场景；现有单测仅覆盖预置 2 句柄顺序分派。**建议：槽位预留同步化**——RemindersState 维护 active_execs: usize（dispatch/drain 与 collect_due 同锁序列化）：dispatch 锁内 active>=2→入队否则 active+=1→start_exec_run；完成回调锁内 active-=1；改动约 15 行 + 补 1 条批量钉子（单 tick 3 due exec→2 运行+1 排队无第三行 running）。**P3×4 记录级**：① pending 队列 stale 规则删除后仍会执行（reload 不清队列，建议 drain 校验或记录）② Tasks.tsx:491-495 双分支同文案死逻辑 ③ action_exec.rs:313-332 正常退出路径孙进程持管道 → reader 300ms 超时弃 → output_tail 丢 None（低概率）④ tester R2 报告 en 引文转述误差（实现无错）。无需求边界问题。**处置：status=fixing→implementing、round 3→4（超 maxRounds=3 需用户批准，M1 先例）、reviewedSha 置空待重审**。
- R4 启动（2026-08-26 20:26 用户批准突破 maxRounds 继续 R4，M1 先例）：committer P2-1 修复轮。status=fixing→implementing（round 3→4，maxRounds 保持 3 记录原始上限）、reviewedSha 置空、committer 报告 P2-1 原文交 Coder。修复验收口径（committer §8.2）：单 tick 3 个 due exec → 2 运行 + 1 排队不写 running；drain 超发场景同步钉住；既有 375/276 基线不回归。
- R4: coder 修复完成（同会话续接），commit `76e23d2`（`[task-pulsepet-v2-m4] R4: 修复并发上限 2 竞态软上限（槽位预留同步化 active_execs + 批量钉子）`，commit 前 fetch 无新提交；supervised-coding 已核验 HEAD=76e23d2、2 files +253/−48 纯 Rust）。改动：reminder_scheduler.rs（RemindersState +active_execs: usize 槽位预留计数 doc 注明生命周期与 reload-不重置理由；既有 dispatch_exec_queues_third_beyond_limit 适配新判定源预置 active_execs=2+锁内递减语义+**新增「出队即占槽」断言**+补规则进 st.rules 匹配真实形态；**新批量钉子 batch_dispatch_three_due_execs_two_run_one_pending**+**stale 丢弃钉子 drain_drops_stale_rule_snapshots**）；action_exec.rs（dispatch_exec 重写：判定+自增在 sched 锁内一次完成 enum Decision::Started/Queued——spawn 未插登记表不影响后续判定；启动失败锁内归还槽位防泄漏；drain_pending_execs 重写：锁内 active>=MAX→停、pop 后 **P3-1 stale 校验**（规则不在 st.rules→丢弃不执行不占槽继续取下一个）、占槽与出队原子配对；start_exec_run 签名改 ->bool；run_task 完成回调 notify_slot_free 前锁内 active_execs-=1 递减先于通知）。同步化机制：计数全程同一把锁内变更与 collect_due 串行——批量分派与并发 dispatch 序列化第 3 个必入队；锁临界区无 await 无嵌套 db 锁（start_exec_run 锁外调用）；RunningTasks 职责收缩回纯句柄登记表（N7 语义不变）。自测：cargo test **278 passed+1 ignored**（276+2）；**钉子 TDD 反证**：临时移除同步自增→批量钉子以预期理由失败（恰占 2 槽 left:0/right:2——旧形态 3 个全超发 active=0 pending=0）→恢复全绿，grep TEMP-REVERT 零残留；适配过程：首跑既有单测 FAILED（P3-1 stale 校验咬住空规则表）→修正测试设置匹配 run_tick 真实形态→全绿；npm test/tsc 未跑（前端零改动）；tauri build 成功（PulsePet.app @20:32:16/dmg @20:32:36/二进制 20:32:36）。裁定点 3 条：① **P3-1 已顺手修复**（drain 出队按 id 校验规则仍在 st.rules，stale 快照丢弃不执行不占槽不写 running，独立钉子三断言；边界：规则禁用未删除仍在内存表→排队条目照常执行，与 v1 enabled 语义一致）② reload 不重置 active_execs 不清 pending_execs（有意为之 doc 注明：在飞完成回调仍递减，重置破坏记账致超发；队列残留 stale 校验兜底）③ 其余 P3×3 按指示记录不修。**待验对象更新为 76e23d2**（提交链 b5321bf→067a2d3→bef21cc→5259d43→8d9b323→76e23d2）。
- R4: tester 焦点复验 **FAIL**（testedSha=76e23d2，同会话；**P2-1 修复本体 PASS / 新 P2 业务缺陷 + 2 P3**）。独立复跑：npm 375/27 ✓；**cargo 278+1 但 ~15% flaky**（277+1——logging.rs 轮转断言见缺陷 2）。**P2-1 修复验证通过**：单测面——批量钉子（2 槽/1 排队/2 running 断言直击旧缺陷形态）+ stale 三断言 + 既有测试适配加强（新增「出队即占槽」断言）+ TDD 反证因果必然；实机面完整闭环——3 条 once 同分钟 sleep 25：20:38:44 两 start（槽 0→2）→第 3 个 log「exec queue full (2), pending (queue 1)」→20:39:09 完成回调出队 → 补跑 → 终态 3 行全 ok，**触发瞬间 running=2/total=2/max running=2，无第三行并行 running** ✓。**新发现 P2（业务）——排队中规则 reload 后重复 fire → 双重执行**：3 条 once 排队期间 UI 删除另一规则触发 reload → 内存重算排队规则 #69 next_due（once 无 handled 标记 → 回退过去时刻）→ 下个 tick 再次 fire → 队列重复条目（queue 2）→ drain 两次 → **#55/#56 同时 running（sleep 60 执行两遍）**；根因：排队不写 handled 标记 + reload 重算绕过内存状态；触发条件：并发 ≥3 排队期间任何 CRUD（真实中等概率）；**修复建议：collect_due fire 前按 id 查 pending_execs 去重，或 reload 时对 pending 中规则 next_due 置 MAX/打标记**；注意并发上限 2 本身未破（max running=2），破的是「同一规则重复执行」语义。**P3×2**：① TEST_BUG logging.rs:230 轮转断言 flaky（~15%，全局日志句柄与并行测试竞争，R4 真实进程钉子增加 plog! 流量加剧；非业务缺陷但使 cargo test 非确定性）② 观察项——钉子测试尾部 kill 清理与登记表插入竞态 → cargo test 偶发泄漏 sleep 30 孤儿（本轮 4 个已清理）。环境已恢复（测试规则 64-69 删/action_logs 0/reminder_logs 133 基线/zh+light/opencode.db 只读）。**处置：status=fixing→implementing、round 4→5（超 maxRounds 需用户再批准）、reviewedSha 置空待重审**。
- R5 启动（2026-08-26 20:50 用户批准突破 maxRounds 继续 R5）：tester R4 新 P2（排队中规则 reload 重复 fire → 双重执行）修复轮。status=fixing→implementing（round 4→5，maxRounds 保持 3 记录原始上限）、reviewedSha 保持 null、tester R4 报告原文交 Coder。修复建议：collect_due fire 前按 id 查 pending_execs 去重，或 reload 时对 pending 中规则 next_due 置 MAX/打标记；P3 flaky（logging 轮转 + 测试孤儿泄漏）待用户答复是否一并修（预告时问询）。
- R5 补充（2026-08-26 20:53 用户答复「一起修」）：**P3 flaky 两项一并修**——① logging.rs:230 轮转断言 ~15% flaky（全局日志句柄并行竞争，R4 真实进程钉子加剧；修复方向：轮转断言容忍并行写入或串行化测试）② 钉子测试尾部清理与登记表插入竞态泄漏 sleep 孤儿（修复方向：测试清理等待 spawn poll 或 kill 前同步）。
- R5: coder 修复完成（同会话续接），commit `d715716`（`[task-pulsepet-v2-m4] R5: 修复排队中 reload 双重执行 + logging 轮转 flaky + 测试孤儿清理`，commit 前 fetch 无新提交；supervised-coding 已核验 HEAD=d715716、3 files +248/−12 纯 Rust）。改动：**P2 主修复（两层闭合）**——① reminder_scheduler.rs run_tick 分派循环加**排队中去重**（exec 分派前按 id 查 pending_execs，已排队=本周期已认领→跳过分派+补 mark_triggered 落库防 collect_due fire 与 dispatch 落库之间的 reload 毫秒窗口；run_tick/persist_skipped 泛型化 mock 可直调）+ **新钉子 queued_rule_reload_does_not_refire_or_duplicate**；② action_exec.rs dispatch_exec 入口**无条件 mark_triggered 落库**（含排队分支——此前仅 start_exec_run 落库排队条目 handled 只在内存 reload 即丢失；落库在 sched 锁外锁序 db/sched 不嵌套与 reload_state 反序安全；start_exec_run 内二次 mark 保留幂等无害）——排队条目的「本周期已认领」持久化，任意后续 reload 不再复活到过去时刻。**P3-1 logging flaky**：轮转断言容忍并行写入（.old 改 >=ROTATE_BYTES+1 + ends_with("x"×64) 内容校验；新文件改**首行含 banner** 断言比原 len<1024 更精确免疫竞争）。**P3-2 孤儿**：dispatch_exec_queues_third_beyond_limit 清理段补「等登记就绪」循环 + batch/drain 钉子 sleep 缩至 45s（漏杀自愈）。自测：cargo test **279 passed+1 ignored**（278+1）；**P2 钉子 TDD 反证**：临时移除两处修复→钉子以实机缺陷形态红（once #3 reload 后不复活 left: 过去/right: MAX）→恢复全绿；**flaky 稳定性：连续 10 轮全量 cargo test 全绿**（修复前 ~15% 失败率清零）；**孤儿：第 7-10 轮每轮后 ps 断言 0 孤儿**；npm test/tsc 未跑（前端零改动）；tauri build 成功（PulsePet.app @21:03:32/dmg @21:03:53/二进制 21:03:53）。裁定点 3 条：① 钉子构造口径（3 条 once 用 insert 未来+UPDATE 置过去模拟真实到期，reload 后断言 MAX；at 留未来则 reload 返回 at 本身正确非缺陷）② 对照规则口径（disabled daily created=insert 时刻→常规值次日 HH:MM 断言重算一致，比「仍过去时刻」贴合 insert 语义；reload 错过检测过去时刻路径已有既有测试 daily_reload_missed_window_returns_past_due 覆盖未削弱）③ 孤儿防御双保险（清理等待循环+测试 sleep ≤45s 自愈；等待超时 5s 仍 drain 空极端视为测试基础设施故障非业务面）。**待验对象更新为 d715716**（提交链 7 提交至 d715716）。
- R5: tester 焦点复验 **PASS**（testedSha=d715716，同会话）。独立复跑：cargo 279+1i 首跑 ✓ + **独立 9 轮连续全绿**（R4 ~15% flaky 清零）+ **8 轮重跑后 ps 零孤儿** + npm 375/27 ✓ + 产物 21:03:32/53 吻合。**P2 修复验证（复现 R4 铁证路径）**：单测面——新钉子 queued_rule_reload_does_not_refire_or_duplicate 断言链完整（tick1 恰 2 槽+1 排队/对照 daily 常规值/reload 后 3 条 once 全 MAX 不复活/队列无重复条目/db 3 条 handled 全落库）+ TDD 反证因果必然（left 过去/right MAX 与 R4 实机缺陷形态逐字一致）+ 既有 reload 错过检测不削弱；**实机面——排队期间删规则 reload 后排队规则单次执行**（74/75 running + 76 pending → 删除触发 reload → 出队 76 单次 log#62，action_logs 76 恰 1 行、grep started 计数 1、无 queue 2 无并行 running；对比 R4 #69 双重执行形态消失）；reload 其它语义抽查（disabled daily 对照/collect_due/reload 本体零改动）。**P3 两项验证**：flaky 9 轮全绿 + 新断言未削弱（.old >=ROTATE_BYTES+1 + ends_with x×64 + 新文件首行 banner 免疫并行尾部追加）；孤儿 8 轮 ps 零残留（等登记就绪循环 + sleep ≤45s 自愈双保险）。回归抽查全过（R4 批量两轮实机复现/R2 竞态双钉子/TC-M4-04/TC-M4-06 抽样）。无新缺陷。环境已恢复（规则 70-77 删/action_logs 0/reminder_logs 133 基线/zh+light/opencode.db 只读）。**testVerdict=PASS——M4 全部验收闭环**（R1 主体 + R2 退出竞态 + R3 Token 定格 + R4 并发上限 + R5 排队 reload）。status→reviewing，调 Committer 重审。
- R5（终审）: committer 重审 **APPROVED**（reviewedSha=d715716=testedSha=HEAD，**双通过达成**，同会话）。R4 P2-1 处置核对（active_execs 同锁序列化符合建议/批量钉子直击缺陷形态/既有测试加强属实/TDD 反证必然/实机 2 running+1 pending 达成）+ R5 新 P2 核审（双层闭合语义正确：mark_triggered 落库「本周期已认领」持久化 + run_tick 去重覆盖 µs 窗口；锁序 db→sched 不嵌套无死锁环；钉子断言链完整 left 过去/right MAX 与实机缺陷形态逐字一致；实机复现路径闭环）+ P3 两项核审（logging 断言方向正确但 **ends_with("x"×64) 残余竞态窗口**——19 轮全绿在 p≈15% 下无命中概率 ≈4.5% 统计倾向改善不能完全证明，P3 记录建议打磨轮锁内轮转；孤儿双保险成立）+ tester 证据链采信（R4 FAIL→R5 PASS 同会话/9 轮稳定/ps 零孤儿/计数交叉核 276→278→279=+3 钉子严格吻合）+ 上轮 P3×4 处置确认（P3-1 已修/P3-2、3 记录/P3-4 无需处理）。**P3（终态记录级）**：① 检查点 filesChanged 缺 logging.rs（已补）② action_exec.rs:622-635 注释复制粘贴重复（外观）③ logging ends_with 残余竞态（打磨轮）④ 理论双记账边界（µs 窗口+补跑窗尾+队列满三巧合叠加概率趋零）。无需求边界问题。**P0/P1/P2 全无——M4 双通过闭环**（testVerdict PASS + reviewVerdict APPROVED，reviewedSha=testedSha=HEAD=d715716）。交付步骤清单 5 步已列（检查点回写→coder 回 spec 提交+push+开 PR→committer gh pr review 留痕→coder 补 manifest→汇报合入请求不自动合入）。
- **交付启动（2026-08-26 21:28 用户确认"交付"）**：三步执行——① coder 回 spec 提交（docs/v2 两文件全部修订）+ 同步 origin/develop + SSH 推送 develop_opencode + 开 PR（base=develop，留 manifest 占位）；② committer gh pr review 留痕；③ coder 补写 evidence manifest 进 PR description。不自动合入。
- **交付执行①（2026-08-26 21:32）**：Coder 完成——回 spec 提交 `d51ba9c`（`[task-pulsepet-v2-m4] R1: 回 spec 文档口径（用户 2026-08-25 两轮 UI 裁定：tab 例程/待办 + 芯片例程 + 按钮末行对齐 + 去图标）`，仅 V2-DESIGN.md + V2-TEST-CASES.md 两文件 +7/−5，逐字核验与检查点口径一致；.opencode/ 与 images/ 未进提交）→ fetch origin/develop=e7291c3 无新提交 → SSH 推送成功（562879a..d51ba9c）→ 开 PR：**https://github.com/yq3/lab/pull/16**（base develop / head develop_opencode，8 commits：b5321bf→067a2d3→bef21cc→5259d43→8d9b323→76e23d2→d715716→d51ba9c；正文六节齐备 + EVIDENCE_MANIFEST_PLACEHOLDER 占位）。待：② committer gh pr review → ③ manifest 补写。
- **交付执行②（2026-08-26 21:37）**：Committer 已执行 `gh pr review 16 --comment` 留痕——**COMMENTED**（同账号 POC 约定，Review ID `PRR_kwDOTsiHgs8AAAABK9_flQ`，submittedAt 2026-08-26T13:36:41Z UTC）：正文五节（① 评审对象核对：8 提交链、双 SHA=d715716、回 spec d51ba9c 纯文档逐字复核一致；② 重审结论摘要 APPROVED；③ tester R4/R5 证据摘要；④ knownIssues 移交：P3×4 + Windows 观察项 + M2 目验 7 项待用户；⑤ 交付声明：COMMENTED 留痕、不自动合入、manifest 待补写后复核）。前置核验全过（base/head/OPEN/8 commits SHA 链吻合/双 SHA 在代码链内/本地 HEAD=d51ba9c 与 origin 同步）、提交后二次核验恰 1 条无重复（正文 2017 字符首尾逐字一致）。PR #16 保持 OPEN。待：③ coder 补写 manifest。
- **交付执行③（2026-08-26 21:39）**：Coder 已把 Evidence Manifest JSON 写入 PR #16 description（`gh pr edit --body-file`，正文 3552→10016 字节 +6464B；13 顶层键：taskId/pr=16/milestone/headSha(d715716 双 SHA)/specCommit(d51ba9c)/commits(8 链)/verdicts(tester PASS 全轮轨迹 R1 16PASS+1FAIL+2PENDING→R2 补验→R3/R4/R5 闭环 + committer APPROVED + reviewer COMMENTED PRR_kwDOTsiHgs8AAAABK9_flQ)/testEvidence(npm 375/27、cargo 279+1i 9 轮稳定、tsc 0、产物 21:03:32/53、ps 零孤儿、4 处 TDD 反证、6 条实机闭环)/acceptanceCriteria/specUpdates/knownIssues/environment+timestamp）。核验五项全过：① 占位符零残留 ② 前六节正文 startswith 逐字节一致 ③ manifest JSON 可解析（13 键）④ Review 留痕仍在 count=1 ⑤ PR 保持 OPEN。**交付三步全部完成，PR #16 OPEN 等待用户合入决定（不自动合入）**。
- **合入（2026-08-26 21:41 用户确认"合入"）**：`gh pr merge 16 --merge --delete-branch=false` 成功——**MERGED**（merge commit `a6c98c5902e0818cdc7949c7245c2a6730981166`，mergedAt 2026-08-26T13:41:45Z UTC）；origin/develop 已更新至 a6c98c5。**M4 任务收官**（status=approved 终态，testedSha=reviewedSha=d715716，PR 留痕 COMMENTED + manifest 齐备）。遗留事项回写（见「遗留事项」小节）：本轮清偿——并入 2 项（M3 P2 面板定格 + P3-4 resetTodayCache）、两轮 UI 裁定、R2~R5 修复闭环；新移交——P3×4（logging ends_with 残余竞态→打磨轮、注释重复→打磨轮、理论双记账边界→记录、filesChanged 已补）、Windows 实机（TC-M4-18 观察项）、M2 目验 7 项（继续待用户）；维持原去向——v2-m2 P3-5（atlas.rs M5/打磨轮）、P3-6~10、v2-m1 A/B/C/D。检查点文件随收官提交至 develop。
（R1 起逐轮记录 coder/tester/committer 结果）

## 最新验证意见原文
（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）

### Committer R5 重审终审报告（2026-08-26，reviewVerdict=APPROVED）

# PulsePet v2 M4 Committer 重审终审报告（reviewedSha = d715716）

## 1. 评审对象核对表

| 项 | 核验结果 |
|---|---|
| 提交链（7） | b5321bf（25f +5386/−712）→ 067a2d3（7f +100/−16）→ bef21cc（4f +74/−30）→ 5259d43（2f +173/−4）→ 8d9b323（3f +69/−14）→ **76e23d2**（2f +253/−48 纯 Rust）→ **d715716**（3f +248/−12 纯 Rust）——逐提交 stat 与检查点声明吻合 ✓ |
| 分支领先 | develop_opencode = d715716 相对 origin/develop（e7291c3）恰 7 个 M4 提交领先，无混入 ✓ |
| R4/R5 范围 | 仅 action_exec.rs / reminder_scheduler.rs / logging.rs 三文件（R4 两文件、R5 三文件），前端零改动、Cargo 零改动、迁移零改动——修复轮范围收敛 ✓ |
| 工作区 | 仅 docs 两文件（22:15/22:34 口径修订，与检查点注记逐字一致，diff 与上轮核验相同未变）+ 流程文件 + images/ 历史截图 ✓ |
| testedSha | d71571683f1aca9e61caa215ebcf0d96278b3713 = HEAD ✓ |
| TEMP-REVERT 残留 | grep 零命中（R4/R5 的 TDD 反证临时回退已清）✓ |

## 2. 上轮 P2-1 处置核对（R4）——**已闭环，方向与建议一致**

- **机制**：`RemindersState.active_execs` 槽位预留——判定+自增在 sched 锁内一次完成（与 collect_due 同锁序列化），恰好是我上轮建议的「同锁序列化同步计数器」方案；dispatch 启动失败锁内归还、run_task 完成锁内递减先于通道通知、drain 锁内 `active>=MAX` 停——增/减/判定三路径全部同一把锁内原子配对 ✓
- **批量钉子** `batch_dispatch_three_due_execs_two_run_one_pending`：3 条 exec 同步循环分派 → 断言 `active==2` + `pending==[id=3]` + running 行恰 2 + 满员 drain 不出队——直击旧缺陷形态（登记表异步插入延迟→超发）✓
- **既有测试适配**：dispatch_exec_queues_third_beyond_limit 预置 active=2 + 规则进 st.rules（匹配 run_tick 真实形态）+ **新增「出队即占槽」断言**——断言加强非削弱属实 ✓
- **TDD 反证**：移除同步自增 → 钉子以「恰占 2 槽 left:0/right:2」失败（旧形态 3 超发），逻辑必然 ✓
- **实机闭环**（tester R4）：3 条 once 同分钟 → 恰 2 running + 1 pending 不写 running + 完成出队补跑 + max running=2——上轮验收口径实机达成 ✓
- **R4 裁定点复核**：① stale 顺手修（drain 锁内按 id 校验 st.rules，丢弃不占槽，钉子三断言）② reload 不重置 active/pending（doc 注明理由：在飞完成回调仍递减，重置破坏记账；stale 校验兜底）——自洽成立 ✓

## 3. R5 新 P2 修复核审（排队 reload 双重执行）——**双层闭合，语义正确**

- **层① dispatch_exec 入口无条件 mark_triggered 落库**（含排队分支）：「本周期已认领」持久化——排队条目 reload 后不再复活（once→MAX/daily→下个匹配日）；start_exec_run 内二次 mark 保留（出队执行时刻刷新锚点，幂等无害）✓
- **层② run_tick 分派前按 id 查 pending 去重**：覆盖 collect_due fire 与 dispatch 落库之间的 µs 级 reload 窗口——已排队跳过分派 + 补 mark_triggered（此后任意 reload 不再复活）✓
- **锁序**：dispatch 的 db 写与 sched 锁互不嵌套（db 单独段 → sched 决策段 → 锁外 start_exec_run）；reload_state 的 db→sched 嵌套方向无反向路径 → 无死锁环 ✓；persist_skipped/run_tick 泛型化（mock 可直调）与既有模式一致 ✓
- **钉子** `queued_rule_reload_does_not_refire_or_duplicate`：3 条 once（insert 未来+UPDATE 置过去模拟真实到期——过 validate 的合法路径）+ disabled daily 对照；断言链完整（恰 2 槽+1 排队 / 对照 daily 常规值 / reload 后 once 全 MAX / 队列无重复条目 / db handled 全落库）；TDD 反证 left 过去/right MAX 与 R4 实机缺陷形态逐字一致 ✓；既有 `daily_reload_missed_window_returns_past_due` 未削弱（reload 错过检测路径零改动）✓
- **实机闭环**（tester R5）：R4 铁证路径复跑——排队期间删除规则触发 reload → 排队规则出队**单次**执行（log 恰 1 行、started 计数 1、无 queue 2、无并行 running）；R4 缺陷形态（#69 双重执行）未再出现 ✓
- **R5 裁定点复核**：① 钉子构造口径合法（insert 需未来时刻过 validate，UPDATE 置过去模拟到期）② 对照 daily 常规值口径（created=insert 时刻 → 次日 HH:MM）贴合 insert 语义 ③ 孤儿双保险（等登记就绪循环 + sleep ≤45s 自愈）——全部成立 ✓

## 4. P3 两项修复核审

- **logging 轮转 flaky**：断言方向正确——`.old.len() >= ROTATE_BYTES+1`（免疫尾部追加）与新文件「首行含 banner」（追加只落尾部）两条**可证免疫**；但 **`old.ends_with("x"×64)` 仍与旧断言同一竞态窗口**：并行 plog! 在 `std::fs::write` 与 `set_file` 之间写入旧句柄 → .old 尾部被污染 → ends_with 失败（R4 实测的 176B 正是该窗口）。19 轮全绿（coder 10 + tester 9）在 R4 估算 p≈15% 下无命中概率 ≈4.5%——统计上倾向改善但不能完全证明消除。属测试基建级、非业务面，**P3 记录**（建议打磨轮：测试专用助手持全局 slot 锁内轮转，或删 ends_with 只留 len>=）。
- **孤儿清理**：等登记就绪循环（drain 前确认登记表）+ sleep 缩至 45s 自愈（漏杀 45s 自灭）——双保险机制成立；tester 8 轮重跑 ps 零残留 ✓

## 5. Tester 证据链与计数交叉核

| 项 | 核验 |
|---|---|
| R4 FAIL → R5 PASS 采信 | R4 报告实机铁证（#69 双重执行 + running=2 上限未破的根因链）+ R5 报告复现路径闭环——两轮报告同会话、环境恢复声明完整，采信 ✓ |
| 独立复跑数字 | R5：cargo 279+1i 首跑 + 独立 9 轮连续全绿 + 8 轮 ps 零孤儿 + npm 375/27 + 产物 21:03:32/53 逐秒吻合 ✓ |
| 静态计数交叉核 | 276→278 = R4 +2（批量钉子+stale 钉子）→ 279 = R5 +1（queued_rule 钉子）——committer 独立核对与轮次声明严格吻合；R4 +253/−48、R5 +248/−12 与 stat 一致 ✓ |
| 钉子真实性 | 批量/stale/queued_rule 三钉子断言直击各自缺陷形态、TDD 反证声明均经因果链核验（逻辑必然非走过场）✓ |

## 6. 上轮 P3×4 处置确认

- P3-1（pending stale）→ R4 已顺手修（drain 校验 + 钉子）✓
- P3-2（Tasks.tsx 双分支死逻辑）/ P3-3（output_tail 低概率丢失）→ 记录不修——均为外观/低概率边缘，合理 ✓
- P3-4（tester R2 报告 en 引文转述误差）→ 无需处理 ✓

## 7. 问题清单（终态）

**P0：无。P1：无。P2：无**（上轮 P2-1 经 R4 闭环、R4 新 P2 经 R5 闭环，均实机+钉子+TDD 三重钉住）。

**P3（记录级，不阻断）**：
1. 检查点 filesChanged 缺 `pulse-pet/src-tauri/src/logging.rs`（R5 触及）——检查点回写时补；
2. action_exec.rs:622-635 R5 注释块复制粘贴重复（外观）；
3. logging ends_with("x"×64) 残余竞态（§4 分析，测试基建级，打磨轮建议锁内轮转）；
4. 理论双记账边界：reload 命中 collect_due→dispatch 的 µs 窗口 + 规则于补跑窗尾 1 分钟触发 + 队列仍满三巧合叠加 → 下 tick 记 skipped 且排队条目仍执行（概率趋零，记录级）。

## 8. 需求边界问题

**无**。设计/验收与实现行为自洽；R4/R5 均为实现缺陷修复，未触及 spec 口径。

## 9. 结论

**reviewVerdict: APPROVED**
**reviewedSha: d71571683f1aca9e61caa215ebcf0d96278b3713**

**双通过确认**：reviewedSha = testedSha = HEAD = d715716 ✓（testVerdict=PASS @ R5 + reviewVerdict=APPROVED，M4 全部验收项闭环：R1 主体 + R2 退出竞态 + R3 Token 定格 + R4 并发上限 + R5 排队 reload）。

## 10. 交付步骤清单（待用户确认交付后执行）

1. **检查点回写**（supervised-coding/committer）：status=approved、reviewVerdict=APPROVED、reviewedSha=d715716、filesChanged 补 logging.rs、本报告归档「最新验证意见原文」+ R5 终审轮次行；
2. **coder 回 spec 提交**：docs/v2 两文件（V2-DESIGN §4.7 两轮用户裁定注记 + V2-TEST-CASES TC-M4-02/10/17 修订，工作区已就绪且与检查点注记逐字一致，逐字核验后提交）→ fetch 同步 origin/develop → SSH 推送 develop_opencode → 开 PR（base=develop，正文含验收结论/提交链/测试证据/回 spec 说明/Known Issues，末尾 evidence manifest 占位）；
3. **Committer 交付留痕**：`gh pr review --comment` 五节（① 评审对象核对：7+1 提交链、双 SHA=d715716、回 spec 提交纯文档；② 重审结论摘要 APPROVED；③ tester R4/R5 证据摘要；④ knownIssues 移交：P3×4 记录 + Windows 实机观察项 + M2 目验 7 项继续待用户；⑤ 交付声明：COMMENTED 留痕、不自动合入）；留痕前核验 evidence manifest 双 SHA 与 HEAD=d715716 一致，不满足不放行；
4. **coder 补写 evidence manifest** JSON 进 PR description（双 SHA=d715716、verdicts、testEvidence：npm 375/27 + cargo 279+1i + 9 轮稳定 + 实机闭环证据、acceptanceCriteria、knownIssues、specUpdates）；
5. **汇报合入请求**（不自动合入，等用户指示；合入动作不经手）。

### Tester R5 焦点复验报告（2026-08-26，testVerdict=PASS）

# PulsePet v2 M4 R5 焦点复验报告（Tester）

## 1. 环境与被测对象核验

| 项 | 结果 |
|---|---|
| HEAD（testedSha） | `d71571683f1aca9e61caa215ebcf0d96278b3713` |
| 提交链 | b5321bf→…→76e23d2→**d715716** ✓（3 files +248/−12 纯 Rust） |
| 产物时间戳 | .app @**21:03:32** / dmg @**21:03:53** / 二进制 21:03:53——与 coder 声称一致 |
| 工作区 | src 零改动（仅测试前已有 docs 修订+流程文件） |

## 2. 独立复跑基线表（含多轮稳定性）

| 基线 | coder 声称 | 独立复跑 | 结论 |
|---|---|---|---|
| cargo test（首跑） | 279+1 ignored | **279 passed + 1 ignored**（含新钉子 ok） | ✓ |
| **稳定性多轮** | 连续 10 轮全绿 | **独立 9 轮连续全绿**（首跑 + 8 轮重跑，全部 279+1；R4 时 ~15% flaky 清零） | ✓ |
| 孤儿 | 第 7-10 轮后 0 孤儿 | **8 轮重跑后 `ps` 断言零测试孤儿**（sleep 45/20/30/2 全无） | ✓ |
| npm test | 375/27（前端零改动） | **375 passed / 27 files** | ✓ |

## 3. P2 修复验证（排队 reload 双重执行）

### 3.1 单测面（钉子真实性）
`queued_rule_reload_does_not_refire_or_duplicate`（reminder_scheduler.rs:3429）：
- 构造口径：3 条 once exec 用 insert 未来 + UPDATE 置过去模拟真实到期（过 validate 未来校验的合法路径）+ 1 条 disabled daily 对照 ✓
- 断言链：tick1 恰 2 槽 + 1 排队 → 对照 daily 常规值（次日 09:00，非 MAX）→ **reload 后 3 条 once next_due 全 MAX（不复活）** + daily 重算一致 → tick2 **队列无重复条目**（仍原第 3 条）→ db 3 条 handled 全落库（last_triggered_at is_some）✓
- **TDD 反证因果必然性**：临时移除两处修复（dispatch mark_triggered + run_tick 去重）→ 排队条目 handled 仅在内存 → reload 重建后 next_due 回过去 → 断言 `due == i64::MAX` 必失败（left 过去/right MAX，与 R4 实机缺陷形态逐字一致）✓ 逻辑必然成立
- **既有 reload 错过检测不削弱**：`daily_reload_missed_window_returns_past_due` 等全量通过 ✓

### 3.2 实机面（复现 R4 铁证路径）
3 条 once exec 同分钟触发（sleep 25 与 sleep 60 两轮）：
```
第一轮（无 reload 对照组）：70/71 running + 72 pending → 完成出队 → 72 单次执行（log#59）
第二轮（排队期间 reload 组）：74/75 running + 76 pending（21:10:27）
  → 排队期间 UI 删除 r5b-probe → reminders_delete → reload（21:10:46）
  → 21:11:27 74/75 完成 → 76 出队启动（log#62）——单次
断言：action_logs 中 76 恰 1 行；grep "started: task #76" 计数 1；
     无 "pending (queue 2)"、无第二次 started、无同 reminder_id 并行 running ✓
```
**对比 R4 缺陷形态（#69 双重执行 #55/#56 同时 running）——本轮 reload 后排队规则正常单次执行** ✓✓ 终态 3 行全 ok，last_triggered 落库（76 @21:11:27 出队时刻）✓

### 3.3 reload 其它正常语义抽查
- disabled daily 对照：钉子断言重算结果一致（非排队规则不受排队保护波及）✓
- 正常 daily 补跑判定：`daily_reload_missed_window_returns_past_due` 等既有测试未削弱（全量通过）；实机路径 R3/R4 已验证（本轮代码仅动 run_tick 分派循环与 dispatch 落库，collect_due/reload 本体零改动）✓

## 4. P3 两项验证

### 4.1 flaky（logging 轮转）
- **独立 9 轮连续全量 cargo test 全绿**——R4 实测 ~15% 失败率清零 ✓
- 新断言有效性核验：`.old >= ROTATE_BYTES+1`（轮转确实发生、量不缩水）+ `ends_with("x"×64)`（内容尾部保留）+"新文件首行含 banner"（重开语义，比原 `len<1024` 更精确且免疫并行尾部追加）——**断言未削弱，免疫竞争的机制成立** ✓

### 4.2 孤儿
- 8 轮重跑后 `ps -eo pid,command` 断言：**零测试孤儿**（sleep 45/20/30 等全无）——R4 泄漏 4 个 sleep 30 的场景未再出现 ✓
- 机制核验：`dispatch_exec_queues_third_beyond_limit` 清理段补「等登记就绪」循环（drain 前确认登记表非空）+ 批量/drain 钉子 sleep 缩至 45s（漏杀 45s 自愈）——双保险 ✓

## 5. 回归抽查

| 项 | 结论 |
|---|---|
| R4 批量分派（2 running + 1 排队 + 出队补跑、max=2） | ✓ 本轮实机两轮完整复现（70/71/72、74/75/76 均恰 2 running、排队、出队补跑、无超发） |
| R2 竞态双钉子（abort interrupted / finish 守卫） | ✓ 全量跑通过 |
| TC-M4-04 序列化分派（dispatch_exec_queues_third_beyond_limit） | ✓ 通过 |
| TC-M4-06 exec 链（本轮抽样：sleep 命令执行/完成/悬空 id） | ✓ 正常（echo/exit3/超时杀组代码零改动，前轮已验证） |
| npm/tsc | ✓ 375/27 |

## 6. 缺陷清单

| 级别 | 结论 |
|---|---|
| P2（R4 报告：排队 reload 双重执行） | **已修复**——实机复现路径（排队期间删规则 reload）后排队规则单次执行，无重复 fire/无双行 running；钉子 + 9 轮稳定全绿 |
| P3 flaky（logging 轮转） | **已修复**——9 轮全绿，断言免疫竞争且未削弱 |
| P3 测试孤儿 | **已修复**——8 轮后 ps 零残留 |

无新发现缺陷。

## 7. 环境恢复声明

- 进程：PulsePet 已退出（测试前未运行）；无孤儿（sleep 全清）；
- pulsepet.db：测试规则（70-77）已删、action_logs **0**、reminder_logs **133**（基线）、#39 保留（use_fireworks=1）、app_state 默认（**zh/light**/paused=0）；
- opencode.db：全程 `-readonly`；
- 仓库工作区：零测试残留；/tmp 无残留。

## 8. 结论

**testVerdict: PASS**

- P2（排队 reload 双重执行）实机复现路径闭环：排队期间 reload 后单次执行、无重复 fire；钉子断言完整、TDD 反证逻辑必然；reload 正常语义不回归；
- P3 两项（logging flaky + 测试孤儿）独立 9 轮全绿验证修复，断言未削弱；
- 回归全绿（R4 批量/R2 竞态/TC-M4-04/TC-M4-06 抽样），基线 279+1 / 375+27；
- M4 全部验收闭环（R1 主体 + R2 退出竞态 + R3 Token 定格 + R4 并发上限 + R5 排队 reload）。

**testedSha: `d71571683f1aca9e61caa215ebcf0d96278b3713`**

### Tester R4 焦点复验报告（2026-08-26，testVerdict=FAIL）

# PulsePet v2 M4 R4 焦点复验报告（Tester）

## 1. 环境与被测对象核验

| 项 | 结果 |
|---|---|
| HEAD（testedSha） | `76e23d221c0396c0565eeaa047e076d955dc06b5` |
| 提交链 | b5321bf→…→8d9b323→**76e23d2** ✓（2 files +253/−48 纯 Rust） |
| 产物时间戳 | .app @**20:32:16** / dmg @**20:32:36** / 二进制 20:32:36——与 coder 声称一致 |
| 工作区 | src 零改动（仅测试前已有 docs 修订+流程文件） |

## 2. 独立复跑基线表

| 基线 | coder 声称 | 独立复跑 | 结论 |
|---|---|---|---|
| cargo test | 278 passed + 1 ignored | **278+1 但 flaky**：多次重跑中 ~15% 概率 277+1（详见 §5 缺陷 2） | ⚠ 见缺陷清单 |
| npm test | 375 / 27（前端零改动） | **375 passed / 27 files** | ✓ |

## 3. 批量分派修复验证（committer P2-1）

### 3.1 单测面（钉子真实性）
- `batch_dispatch_three_due_execs_two_run_one_pending`：3 条 exec 规则同步循环 dispatch（run_tick 形态）→ 断言 `active_execs==2`（恰占 2 槽）、`pending==1`（id=3）、**action_logs running 行恰 2**、满员 drain 不出队不新增 running——断言具体，直击旧实现缺陷形态（登记表插入延迟 → 3 次全读 0 → 超发）✓
- `drain_drops_stale_rule_snapshots`：stale(id=999 不在内存) + live(id=7) 排队 → drain 后三断言：队列排空 / active_execs==1（仅 live 占槽）/ running 行 count=1 且 only_id=7（stale 未执行）✓
- 既有 `dispatch_exec_queues_third_beyond_limit` 适配：预置 active_execs=2 + 规则进 st.rules（匹配 run_tick 真实形态）+ **新增「出队即占槽（计数回满）」断言**——**断言加强而非削弱** ✓
- **TDD 反证因果必然性**：旧实现 3 次 dispatch 读 `RunningTasks.len()` 全为 0 → 3 个全 start_exec_run → 3 行 running → 钉子断言（2 槽/1 排队/2 running）必然失败（left:0/right:2 形态）；新实现 active_execs 锁内同步自增 → 第 3 个判定 `2>=2` 必入队 ✓ 逻辑必然成立

### 3.2 实机面（完整闭环铁证）
构造 3 条 once exec 同分钟（sleep 25）触发：
```
20:38:44.619 exec started: task #64 log#50      ← 第 1 个（占槽 0→1）
20:38:44.621 exec started: task #65 log#51      ← 第 2 个（占槽 1→2）
20:38:44.621 exec queue full (2), task #66 pending (queue 1)   ← 第 3 个必入队 ✓
20:39:09.645 exec finished: task #65 → exec dequeued: task #66  ← 完成回调触发出队
20:39:09.647 exec started: task #66 log#52      ← 出队补跑
20:39:34.672 exec finished: task #66
```
- 触发瞬间轮询：**running=2、total=2、max running=2**——恰 2 行 running、第 3 个不写 ✓（旧实现此处 3 全超发）
- 全程无第三行并行 running；终态 3 行全 ok；scheduled_at 溯源 20:38:00 ✓
- **P2-1 验收口径（单 tick 3 due → 2 运行 + 1 排队不写 running）实机达成** ✓

### 3.3 stale 语义
单测钉子三断言全过 ✓；实机复现未完成（UI 行配对错位删了运行中的 #68 而非排队的 #69——见 §5 缺陷 1 的触发链）——**stale 以单测+代码核验为准**（drain 锁内按 id 校验 st.rules，stale 丢弃不占槽继续取下一个，逻辑与钉子一致）。

## 4. 回归抽查

- **TC-M4-04 序列化分派**：`dispatch_exec_queues_third_beyond_limit` 适配后全过 ✓
- **TC-M4-06 exec 全链**：本轮批量实机覆盖（sleep 25/60 正常执行、完成回写、悬空 id 保留——被删规则 #68 的 in-flight 完成写库 ok）；echo/exit 3/超时杀组为上轮已验证项（代码零改动）✓
- **R2 竞态双钉子**：`abort_exit_race_real_process_keeps_interrupted_summary` + `finish_action_log_with_guarded_by_running_status` 每次全跑均过 ✓

## 5. 缺陷清单

| 级别 | 位置 | 描述 |
|---|---|---|
| **P2（新发现，业务）** | `reminder_scheduler.rs` collect_due / reload 交互 | **排队中规则 reload 后重复 fire → 双重执行**。实机铁证：3 条 once 同分钟触发，第 3 条（#69）排队；排队期间 UI 删除另一规则触发 reload → 内存重算 #69 next_due（once 无 handled 标记 → 回退到 20:43 过去时刻）→ 下个 tick 再次 fire → **队列出现同规则重复条目（queue 2）** → drain 出队两次 → **#55/#56 同时 running（sleep 60 执行两遍）**。根因：排队不写 handled 标记 + reload 重算绕过内存状态。触发条件：并发 ≥3 排队期间任何 CRUD（含开关任意规则）——真实中等概率。**修复建议**：collect_due fire 前按 id 查 pending_execs 去重，或 reload 时对 pending 中规则 next_due 置 MAX/打标记。注意：并发上限 2 本身未破（max running=2），破的是「同一规则重复执行」语义 |
| **P3（新发现，测试级 TEST_BUG）** | `logging.rs:230` 轮转断言 | **flaky**：多次全量跑 ~15% 概率 `init_write_rotate_and_panic_hook` 失败（left 1048753 vs right 1048577——轮转 .old 被并行测试的 plog! 额外写入 ~176B）。根因：全局日志句柄与并行测试竞争（R4 新增真实进程钉子增加 plog! 流量加剧触发）。非业务缺陷，但使 cargo test 非确定性（coder 声称 278+1 单跑成立） |
| **P3（观察项）** | 测试清理时序 | 钉子测试尾部 kill 清理与登记表插入存在竞态窗口（spawn 未 poll 时 drain 空）→ **cargo test 偶发泄漏 sleep 30 孤儿**（本轮实测 4 个，已人工清理） |

## 6. 环境恢复声明

- 进程：PulsePet 已退出（测试前未运行）；**4 个测试孤儿 sleep 30 已清理**；opencode 主进程未动；
- pulsepet.db：测试规则（64-69）已删、action_logs **0**、reminder_logs **133**（基线）、#39 保留（use_fireworks=1）、app_state 默认（zh/light/paused=0）；
- opencode.db：全程 `-readonly`；
- 仓库工作区：零测试残留；/tmp 无残留。

## 7. 结论

**testVerdict: FAIL**

- **P2-1 修复本体 PASS**：批量分派实机闭环完整（恰 2 running + 排队 + 出队补跑 + max=2）、单测钉子真实、TDD 反证逻辑必然、既有测试适配加强；
- **但实机场景暴露新 P2 业务缺陷**（排队中 reload → 双重执行，实机铁证）+ 新 P3 测试 flaky（logging 轮转 + 测试孤儿泄漏）——需 coder 修复排队 reload 语义后重测（建议：collect_due 按 pending id 去重或 reload 保护 pending 规则）。

**testedSha: `76e23d221c0396c0565eeaa047e076d955dc06b5`**

### Committer R1 审查报告（2026-08-26，reviewVerdict=NEEDS_CHANGES）

# PulsePet v2 M4 Committer 审查报告（reviewedSha 候选 = 8d9b323）

## 1. 评审对象核对表

| 项 | 核验结果 |
|---|---|
| 提交链 | b5321bf（25 files +5386/−712）→ 067a2d3（7 files +100/−16）→ bef21cc（4 files +74/−30）→ 5259d43（2 files +173/−4 纯 Rust）→ 8d9b323（3 files +69/−14 纯前端）——与检查点各轮声明逐提交吻合 ✓ |
| 净 diff 边界 | e7291c3→8d9b323 = 28 files +5761/−735，全部在 pulse-pet/ 内，无越界 ✓（53e447f→8d9b323 仅多 .opencode/workflows/task-pulsepet-v2-m3.md = M3 流程文档提交，非 M4 代码）|
| 分支领先 | develop_opencode（8d9b323）相对 origin/develop（e7291c3）恰 5 个 M4 提交领先，无混入 ✓；origin/develop_opencode=562879a，ahead 7 = 53e447f+e7291c3+M4×5 ✓ |
| 依赖变更 | tokio features +process/macros/sync + libc——Cargo.lock 显示 libc/signal-hook-registry/tokio-macros 均为 tauri 依赖树既有 crate，无新引入 ✓ |
| 迁移 | 003-m4-tasks.sql +7 列 + action_logs 表；SCHEMA_VERSION=3；MIGRATIONS 追加 + 编译期断言 `const _: () = assert!` ✓；加列+新表无重建、可事务化（A1）✓ |
| filesChanged | 检查点 26 文件 = 25（b5321bf）+ i18n.test.ts（067a2d3）链内全覆盖 ✓ |
| testedSha | 8d9b323b80daa4bf911c027617fa1b176dd7ecbc = HEAD ✓ |
| 工作区 | 仅 docs 两文件（22:15/22:34 口径修订，与检查点注记逐字一致，归交付阶段统一提交）+ 流程文件；pulse-pet/images/ 为 08-20~24 历史截图（M4 前遗留，非测试残留）✓ |

## 2. 需求对应性（七块 + 并入项 + 两轮用户裁定）

| 块 | 结论 |
|---|---|
| 1 迁移 003 | ✓ 幂等/半途回滚/列默认值/表数 4 测试；v1 存量行默认 notify/interval；todo 派生行不迁移；action_params JSON 失败拒绝 |
| 2 调度扩展 | ✓ compute_next_due 按 kind 分派 + snooze 优先（P1-1）；15min 补跑窗同窗；skipped 闭环 N1（last_skipped_at 分离/推进/once 重启仍 MAX/手动补跑不被 dedup 拒）；暂停按 kind 分派（interval 顺延 / daily-once 记 skipped+清 snooze P3-5，恢复不补）；reload 错过检测 P2-5（prev_daily_occurrence + floor=created 防新建即补跑）；snooze 重发语义全 kind；跳过本次 N2 写表+内存同清 |
| 3 ActionExecutor | ✓ trait validate+async run；Exec 校验全规则（2000 字符/1-120/timeout 缺省 10/cwd 须目录）；Unix setsid+kill(−pgid) 组杀 / Windows taskkill 分支同构；TailBuf 2KB 截尾；分派注册表；试一试 = 真实执行 |
| 4 exec 执行链 | ✓ insert running → 伪 session Working+notify → spawn（15s 心跳 P2-9）→ 完成回写（N7 先移除登记表）→ 终态 apply → task-result 独立事件（P1-3）→ channel 出队；Exit 处置 P1-2（R2 先写后杀+双侧守卫）；启动清理 R5 |
| 5 opencode 模板 | ✓ buildOpencodeCommand 逐字（--title 前缀 / 可选 --auto / 无 --dir）；仅填表辅助；实机验证 --title 不被覆盖 |
| 6 UI | ✓ tab 改名/旧值映射直达；一张列表四件套+徽标+摘要；条件表单；历史折叠面板倒序 50/页+过滤+色点+展开 output_tail+补跑延迟；snooze 按钮 hover 浮现（critical 且 reminder 载荷）|
| 7 i18n | ✓ tasks.* zh/en 键集合一致（完备性测试守护）；summary 模板键按当前语言渲染（Rust/TS 两层同口径）；panel.tab.tasks/panel.agentTask |
| 并入① focus 双触发 | ✓ TokenStats.tsx:132-151 onFocusChanged→load（仿 Settings）|
| 并入② resetTodayCache | ✓ 全仓 grep 零命中，2 行已删 |
| 用户 5 点裁定 | ✓ ① tab 例程/待办 ② 右下角 ③ accent 色（--accent 蜜橘/青，hover accent-ink）④ 新建例程 ⑤ 分段去图标列表徽标保留 |
| 用户 2 点二次裁定 | ✓ ⑤ agentTask 例程/Routine ⑥ 按钮并入末行字段行右端（四注入点互斥恰渲染一次；todo 编辑态 margin-left:auto 右下角）|
| 「不含」项 | ✓ 零预实现：executor_for 未知类型 None（无 webhook）；notify 不写 action_logs；todo 不迁移；补跑窗单一口径；无独立 tab；调度器未多线程重写 |

## 3. 代码质量

- **SQL 参数化**：全 params! 绑定；list_action_logs 的 where/LIMIT/OFFSET 均为常量或数值，无注入面 ✓
- **线程/锁纪律**：registry/sched/db 锁全部短临界区、无锁跨 await ✓；RunningTasks 在窗口创建循环前 manage（issue #9）✓；伪 session 直连 apply_event 不经 HTTP 白名单，idle_hook 在 http_server 层结构性不可达、AgentActivity 不被触碰（测试断言）✓
- **竞态双保险（R2）**：abort 先写库（WHERE status='running'）后杀组 + 完成回写同款守卫——两写入方以行状态为单调屏障，任意交错序收敛正确终态（含反向：自然完成不被 interrupted 覆盖），与 N7 登记表语义自洽 ✓
- **plog! 纪律**：M4 diff 内零新增 eprintln!/println!（token_stats.rs 的 println! 为 M3 既有测试代码）✓
- **删除残余**：Reminders.tsx 已删（仅文档注释提及）、resetTodayCache 零命中、interaction.ts 旧 tab 引用已改 ✓
- **spawn_blocking/async**：tokio 进程 + async 读取；无阻塞调用进 async 上下文（Windows taskkill 为退出/超时路径短暂同步调用，可接受）✓
- **跨层一致性**：zh/en 字典 Rust/TS 两层逐字一致（interrupted 均为「App 退出中断」/「Interrupted on app exit」）✓

## 4. 测试质量

- **三轮 tester 独立复跑采信**：vitest 375/27、cargo 276+1i、tsc 0、产物时间戳逐秒吻合 ✓
- **静态计数交叉核（committer 独立复核）**：cargo 236→276 = +40 = db.rs 3 + action_exec.rs 17（含 R2 竞态钉子）+ reminder_scheduler.rs 19（含 R2 守卫钉子）+ i18n.rs 1 ✓；vitest 351→375 = +24 = i18n 2 + registry 5 + interaction 1 + token-stats 3 + petStore 2 + reminders 11 ✓——与 tester 数字严格吻合
- **断言真实性抽查**：M4 调度纯函数（daily/once/snooze 重发/reload 检测/补跑窗 14m59s/15m01s 边界）、skipped 闭环（once 重启 MAX、手动补跑不被拒）、暂停分支、并发队列（真进程断言+清理）、竞态双钉子（真实 sleep 597 进程+真实 runtime 三方竞态 / SQL 守卫语义）、toMs 三钉子（TDD 先红）——断言具体可执行，非走过场 ✓
- **既有测试零削弱**：314→375 计数链成立；interval v1 断言全量保留 ✓
- **i18n 完备性**：键集合一致测试自动覆盖新键 ✓

## 5. 问题清单

**P0：无。P1：无。**

**P2-1（阻断，新发现）并发上限 2 为竞态软上限，批量分派可超发**
- `action_exec.rs:609-669`（dispatch_exec / drain_pending_execs）+ `reminder_scheduler.rs:1636-1638`（run_tick 同步循环批量分派）
- 机制：上限判定读 `RunningTasks.len()`，但登记表条目在 spawn 任务**首个 poll**（exec_run_with_timeout 的 cmd.spawn 之后）才异步插入——run_tick 的同步循环与 drain 的无 await 循环中，多次 dispatch 读到的 len 均未含刚分发的任务，第 3 个到期任务不保证进 pending_execs；多线程 runtime 下为竞态（时而过界、时而入队）。触发场景真实：多条 daily 例程同 HH:MM、睡眠后连环补跑 ≥3。
- 违反：设计 §4.5「并发满 2 进等待队列」+ 验收 TC-M4-04-5「第 3 个到期 exec 任务进内存等待队列（不写 running 行）」在批量场景不成立。现有单测仅覆盖预置 2 句柄的顺序分派形态，未钉批量场景。
- 修改建议：槽位预留同步化——在 RemindersState 内维护 `active_execs: usize`（dispatch/drain 与 collect_due 同锁序列化）：dispatch 锁内 `active >= 2 → 入队，否则 active+=1 → start_exec_run`；run_task 完成回调（notify_slot_free 前）锁内 `active-=1`。改动约 15 行，另补 1 条批量钉子（单 tick 3 个 due exec → 断言第 3 个在 pending 且无第三行 running）。

**P3（记录级，不阻断）**
1. pending_execs 队列中任务在规则删除后仍会执行一次（stale 规则快照；reload 不清队列）——建议 drain 时按 id 校验规则仍存在，或记录边界；
2. `Tasks.tsx:491-495` last_triggered/last_skipped 双分支渲染相同文案（死逻辑，无害）；
3. `action_exec.rs:313-332` 正常退出路径若后台孙进程持有管道，reader 300ms 超时被弃 → Arc::try_unwrap 失败 → output_tail 丢为 None（低概率边界；超时路径组杀无此问题）；
4. tester R2 报告 en 字典引文「App exited unexpectedly」与实现「Interrupted on app exit」措辞不符——两层实现一致，属报告转述误差，代码无错。

## 6. 需求边界问题

**无**。设计/验收标准与实现行为在语义层自洽；P2-1 是实现层面的并发时序缺陷（设计明确要求上限 2、代码意图也是实现它），非 spec 矛盾，不转 supervised-coding 回 spec。

## 7. 结论

**reviewVerdict: NEEDS_CHANGES**
**reviewedSha: 8d9b323b80daa4bf911c027617fa1b176dd7ecbc**

理由：P2-1 是 M4 自身验收项（TC-M4-04-5）在批量分派场景的行为级违背，属并发/时序类实现缺陷，触发场景真实（多条例程同点到期），且无后续里程碑自然承接（M5 不动调度器）。修复量小、风险低，建议开 R4 修复轮：P2-1 修复 + 批量钉子测试；P3×4 记录移交（1 条建议随 R4 顺手核验，其余留打磨轮）。

## 8. 处置建议（供 supervised-coding）

1. status=fixing→implementing、round 3→4（超 maxRounds，需流程确认）、reviewedSha 置空、本报告 P2-1 原文交 Coder；
2. 修复验收口径：单 tick 3 个 due exec → 2 运行 + 1 排队不写 running；drain 超发场景同步钉住；既有 375/276 基线不回归；
3. P2-1 修复后 tester 焦点复验 → 回 Committer 重审（届时核对 evidence 双 SHA 与 HEAD 一致）；APPROVED 后按交付流程执行 gh pr review 留痕（docs 口径修订 + 流程文件随交付统一提交）。

### Tester R3 焦点复验报告（2026-08-26，testVerdict=PASS）

# PulsePet v2 M4 R3 焦点复验报告（Tester）

## 1. 环境与被测对象核验

| 项 | 结果 |
|---|---|
| HEAD（testedSha） | `8d9b323b80daa4bf911c027617fa1b176dd7ecbc` |
| 提交链 | b5321bf→067a2d3→bef21cc→5259d43→**8d9b323** ✓（19:54:5x 提交，3 files +69/−14 纯前端） |
| 产物时间戳 | .app @**19:54:38** / dmg @**19:54:59** / 二进制 19:54:59——与 coder 声称逐秒一致 |
| 工作区 | src 零改动（仅测试前已有的 docs 修订+流程文件） |
| 屏幕 | 已解锁，GUI 全程可用 |

## 2. 独立复跑基线表

| 基线 | coder 声称 | 独立复跑 | 结论 |
|---|---|---|---|
| npm test | 375 passed / 27 files | **375 passed / 27 files**（3.28s） | ✓ |
| cargo test | 276+1 ignored（Rust 零改动） | **276 passed + 1 ignored** | ✓ |
| tsc --noEmit | 0 错误 | **TSC_OK** | ✓ |

## 3. 缺陷场景复现验证（核心）

复现 R2 双向复现路径，**全部通过**：

| 步骤 | 面板 KPI（总量/cache read） | DB 同窗口对账（-readonly） | 判定 |
|---|---|---|---|
| ① 长运行 90s 后首开（20:03:39） | 204.2M / 200.7M | 20:03:52 实时 cache_read 201.5M（13s 增量 0.8M ≈ 61k/s 活跃会话速率） | ✓ 近实时吻合（秒级增量内） |
| ② **关开面板**（20:03:5x） | **205.6M / 202.1M（上涨 +1.4M）** | — | ✓ **deepseek 活跃会话未消失**（R2 缺陷形态=骤降至 69.0M，未再出现） |
| ③ 多轮关开 ×2（20:04:0x） | 206.0M（持续上涨） | — | ✓ |
| ④ 跨 70s 后 **Refresh**（20:05:42） | **207.4M / ≈203.9M** | 20:05:45 实时 204.3M（3s 差） | ✓ 跨分钟追回正常 |
| ⑤ 会话级在场核对 | — | deepseek-v4-flash **129.6M** 完整在场（+glm 74.7M+glm-4.6v） | ✓ 上轮整体消失的会话全程在场 |

**custom 区间语义不回归**：切自定义（08-26~08-26 整天）→ 面板 209.2M/cache 205.7M vs DB 整天边界（0点~23:59:59.999）205.6M ✓ 吻合；关开后面板值仅随数据增长（窗口边界固定，非漂移）✓。

## 4. 钉子真实性核验（token-stats.test.ts +3）

1. **preset toMs 前进**：T0(10:00)→T1(18:30) 两次调用，断言 `second.toMs > first.toMs` + `fromMs` 锚定不变 + 7d 同语义——直接对应"活跃会话越过定格 toMs 不落窗外"的缺陷语义 ✓
2. **custom 全等**：now 前进 8.5h 后 `a.toEqual(b)`（整天边界与调用时刻无关）——对应"自定义区间语义原样保留" ✓
3. **custom 倒填归位**：from>to 时 min/max 归位断言 ✓

**代码机制核验**：`resolveQueryRange(preset, fromStr, toStr, now=new Date())` 纯函数 + TokenStats 删除挂载定格 range useMemo（缺陷根源）+ `load()` 内每次重算（useCallback 依赖 [preset, fromStr, toStr, dimension] 同步）——挂载/focus 双触发/Refresh 三路径统一走 load，toMs 均为调用时刻 ✓ 与"挂载定格→重算前进"语义严格对应。

## 5. 回归抽查

- **首开近实时不回归** ✓（步骤① 204.2M 对账吻合，R2 已 PASS 场景保持）
- **今日 preset 默认视图** ✓（全程今日视图正常，KPI/时序/模型行齐全）
- focus 双触发与窗口重算正交 ✓（关开触发 focus→load→重算，实测多轮均正常）

## 6. 缺陷清单

| 级别 | 结论 |
|---|---|
| P2（R2 报告：range.toMs 挂载定格） | **已修复**——实机双向复现路径 5 步全过，活跃会话全程在场、Refresh 可追回、custom 语义保留 |

无新发现缺陷。

## 7. 环境恢复声明

- 进程：PulsePet 已退出（测试前未运行）；无孤儿进程（sleep/opencode run 零残留）；
- pulsepet.db：仅存 #39 该喝水啦（use_fireworks=1）；action_logs **0**；reminder_logs **133**（基线）；app_state 全默认（ui.language=**zh** / ui.theme=**light** / paused=0 / fireworks_global=0 / toolBroadcast=true / pet.position 未动）；
- opencode.db：全程 `-readonly` 只读；
- 仓库工作区：零测试残留（截图 8 张存于 /var/folders/.../m4-test/）；/tmp 无残留。

## 8. 结论

**testVerdict: PASS**

- R2 唯一 FAIL（Token 页 range.toMs 定格）已修复并通过实机双向复现验证（首开近实时、多轮关开+Refresh 活跃会话全程在场、custom 语义不回归）；
- 三枚新钉子断言具体、与缺陷语义严格对应；
- 基线全绿（npm 375/27、cargo 276+1、tsc 0），Rust 零改动确认；
- M4 全部验收项（R1 15 PASS + R2 焦点修复 + R3 焦点修复）闭环。

**testedSha: `8d9b323b80daa4bf911c027617fa1b176dd7ecbc`**

### Tester R2 焦点复验报告（2026-08-26，testVerdict=FAIL）

# PulsePet v2 M4 R2 焦点复验报告（Tester）

## 1. 环境与被测对象核验

| 项 | 结果 |
|---|---|
| HEAD（testedSha） | `5259d4307f70e1d25e29ee1af5b3d6c7e6845df7` |
| 提交链 | b5321bf→067a2d3→bef21cc→**5259d43** ✓（19:15:15 提交，2 files +173/−4 纯 Rust） |
| 产物时间戳 | .app @**19:14:43** / dmg @**19:15:03** / 二进制 19:15:03——与 coder 声称逐秒一致 |
| 工作区 | src 零改动（仅测试前已有的 docs 修订+流程文件） |
| 屏幕状态 | 已解锁（上轮锁屏已解除），本轮 GUI 全程可用 |

## 2. 独立复跑基线表

| 基线 | coder 声称 | 独立复跑 | 结论 |
|---|---|---|---|
| cargo test | 276 passed + 1 ignored | **276 passed + 1 ignored**（2.04s，两个新钉子单独确认 ok） | ✓ |
| npm test | 372 / 27（前端零改动） | **372 passed / 27 files** | ✓ |

## 3. 焦点 1：TC-M4-15-1 竞态修复（上轮唯一 FAIL）

### 3.1 实机退出处置（本轮核心钉住）
创建 `sleep 600`（timeout 10min）exec 规则 → 自然触发运行中（log#34 running，pid 11917）→ 正常退出 App：

```
APP_QUIT；NO_SLEEP_RESIDUAL（ps 断言进程组被杀无残留）
34|62|failed|task.summary.interrupted|19:19:36.403|19:20:03.061
日志：exit → "exit: killing 1 running task process group(s)" → exec finished status=failed
```
- ① `ps` 无残留 ✓；② status=failed + summary=**task.summary.interrupted**（「App 退出中断」，按语言渲染）——**上轮缺陷形态（通用 failed 覆盖）未再出现** ✓
- 附带第二次实机样本：en 切换重启时自然触发的 #36 同样定格 interrupted ✓（2/2 实机）

### 3.2 新钉子真实性核验
- `abort_exit_race_real_process_keeps_interrupted_summary`（action_exec.rs）：真实 `sleep 597` 进程 + 真实 async `run_task` 完成回调 + `abort_all_on_exit` 三方竞态，断言 status=failed + summary=SUMMARY_INTERRUPTED——**真实进程/真实 runtime，非 mock 空转** ✓
- `finish_action_log_with_guarded_by_running_status`（reminder_scheduler.rs）：钉 SQL 语义——ok 结案后迟到 failed 被拦（旧值全保留断言）、interrupted 不被通用 failed 覆盖 ✓
- **TDD 反证逻辑必然性核验**：旧实现（先 kill 后写 + 无守卫）下——kill 唤醒完成回调 → 无守卫 finish 抢先写通用 failed → abort 的 `WHERE status='running'` 落空 → 终态 failed ≠ 钉子断言 interrupted → **钉子必然失败（left failed/right interrupted，与上轮实机缺陷形态逐字一致）**；新实现（先写后 kill + 双侧守卫）→ interrupted 先占行 → 完成回调 0 行更新 → interrupted 必然胜出——任意交错序收敛正确 ✓ 因果关系成立

### 3.3 反向语义抽查
`echo natural-ok` 自然完成（log#35 ok）→ 立即退出 App → **ok 保留**（abort 的 running 守卫不覆盖终态行）✓——真跑完任务保留真实 summary，守卫兜底方向正确。

**焦点 1 结论：PASS**

## 4. 焦点 2：PENDING-USER 补验

### 4.1 TC-M4-17 en + 深色主题目验（全部通过）
| 目验项 | 证据 |
|---|---|
| tabs | **Routines / Todo / Settings** + 标题「PulsePet · Control Panel」✓ |
| 表单 | **New routine** 标题、**Create 按钮与 Start/End 时间窗行同行底缘对齐**（OCR 0.213/0.215 同 y + Vision）✓ |
| 分段按钮 | Notify / Run command **无 emoji**（Vision）✓；列表行 💧/⚡ 徽标保留 ✓ |
| accent 色 | Create 蜜橘橙（浅色）/ **青色 #62c6c0 系**（深色）非默认色（Vision）✓ |
| 芯片 | exec 执行期「**Routine · working**」✓ |
| snooze | 提醒气泡 hover 浮现「**⏱ 10min**」按钮（Vision+OCR 双确认；注意 hover 需落在气泡中心区域并停留 ~2s）✓ |
| summary 渲染 | en 字典逐字：Task finished / Failed (exit code N) / App exited unexpectedly（i18n.rs:283-292 + zh 实机链路已验证）✓ |
| 深色主题 | 深灰底/白标题/浅灰正文对比度可读、Create 青色 accent、分段按钮激活态清晰（Vision 逐项）✓；**验后已恢复 zh/light** ✓ |

### 4.2 并入① Token 面板定格（首开 PASS / **二次打开 FAIL——新发现 P2 缺陷**）
- **首开近实时 ✓**：App 长运行 8.5 分钟后首开 Token 页 → KPI 163.8M / cache read 160.8M；sqlite 只读对账（session 表 time_updated 口径，扣 90s 增量推算打开时点 ≈160.8M，**误差 <0.1%**）；对照启动快照应为 13.3M——**确非快照** ✓
- **tauri://focus 二次打开 FAIL（新缺陷）**：关开面板 + Refresh 后 KPI 稳定 **69.0M**（deepseek 活跃会话 107M 从 KPI/时序**整体消失**），DB 实时 166M+；重启后首开恢复（107.2M ✓）→ 再关开又消失（**双向复现 100%**）

**缺陷机制（P2, IMPL_BUG）**：`TokenStats.tsx` 的 `range`（useMemo 依赖 preset/fromStr/toStr，**不含 now**）在组件挂载时定格 `toMs`；面板窗口 hide/show **不重挂载组件** → toMs 永不前进；用户使用 opencode 期间（活跃会话 time_updated 持续推进，打开面板的动作本身即触发写入）一旦写入越过定格 toMs → 该会话被 `time_updated <= toMs` **整体排除**，此后任何 Refresh/重开（load 复用定格 range）**均无法追回**。修复建议：`load()` 内重算 toMs（range 依赖注入 now），或查询 toMs 加秒级余量。属 M4 并入项交付（focus→load 已接线但刷新不完整）。

## 5. 缺陷清单

| 级别 | 位置 | 描述 |
|---|---|---|
| **P2（新发现）** | `src/panel/TokenStats.tsx` range useMemo（~line 100） | Token 页二次打开/Refresh 后活跃会话（time_updated 越过定格 toMs）整体缺席且不可追回——焦点 2-② 二次打开场景不满足用例预期；首开场景正常 |
| ~~P2（上轮）~~ | action_exec.rs abort | **已修复**（实机 2/2 interrupted + 反向 ok 保留 + 双钉子真实） |

## 6. 环境恢复声明
- 进程：PulsePet 已退出（测试前未运行）；测试 exec 孤儿（sleep 600×1）已清理；
- pulsepet.db：测试规则（62/63）已删、action_logs 16→**0**、reminder_logs 137→**133**（基线）、#39 该喝水啦 use_fireworks=1 保留、app_state 全部默认（**ui.language=zh / ui.theme=light 已恢复**、paused=0、pet.position 未动）；
- opencode.db：全程 `-readonly` 只读；
- 仓库工作区：零测试残留（截图/工具全在 `/var/folders/.../m4-test/`，164 张证据）；
- /tmp 无残留。

## 7. 结论

**testVerdict: FAIL**

- 焦点 1（上轮唯一 FAIL）**已修复并通过**：实机 2/2 interrupted、ps 无残留、反向语义正确、钉子真实且 TDD 反证逻辑必然。
- 焦点 2-①（en/深色目验）**全部通过**。
- 焦点 2-② 首开近实时 **PASS**；但「二次打开再刷新」暴露**新 P2 缺陷**（Token 页 range.toMs 定格 + 活跃会话整体缺席不可追回）——需 coder 修复后重测该场景。

**testedSha: `5259d4307f70e1d25e29ee1af5b3d6c7e6845df7`**

### Tester R1 报告（2026-08-26，testVerdict=FAIL）

# PulsePet v2 M4 R1 验收测试报告（Tester）

## 1. 环境与被测对象核验

| 项 | 结果 |
|---|---|
| HEAD（testedSha） | `bef21cccd9c0d7d594678584fcd2578373608b22` |
| 提交链 | b5321bf → 067a2d3 → bef21cc ✓（`git log` 核验，bef21cc 提交于 22:40:49） |
| 产物时间戳 | PulsePet.app @ **22:40:17** / dmg @ **22:40:38** / 二进制 @ 22:40:38 —— 与 coder 声称**逐秒一致**；构建完成于 bef21cc 提交前 11s，工作区 src 零改动 → 产物即 HEAD 源码所建 |
| DB 状态 | pulsepet.db user_version=3（迁移已完成）、+7 列 + action_logs 表齐、v1 存量行（#39 该喝水啦 💧）保留 |
| 环境警示 | **显示器于 00:10 自动锁屏**（长时间等待中系统休眠），后续 GUI 类操作中断——影响项已降级/挂 PENDING-USER |

## 2. 独立复跑基线（与 coder 声称对比，全部一致）

| 基线 | coder 声称 | 独立复跑 | 结论 |
|---|---|---|---|
| `npm test` | 372 passed / 27 files | **372 passed / 27 files**（3.25s） | ✓ |
| `cargo test` | 274 passed + 1 ignored | **274 passed + 1 ignored**（2.06s） | ✓ |
| `npx tsc --noEmit` | 0 错误 | **0 错误** | ✓ |
| `npm run build` | ✓ | ✓（396ms） | ✓ |
| 产物时间戳 | .app 22:40:17 / dmg 22:40:38 | 一致（未重跑 tauri build，以 HEAD 同树验证） | ✓ |

## 3. 逐 TC 结论表

| 用例 | 结论 | 证据 |
|---|---|---|
| TC-M4-01 迁移与 v1 兼容 | **PASS** | 幂等/半途回滚/列默认值单测真实（db.rs `migration_is_idempotent` 等）；v1 行 #39 全程可编辑可触发（气泡/记账/烟花）；action_params JSON 失败拒绝（reminder_scheduler.rs:3258 断言） |
| TC-M4-02 合并 tab | **PASS** | 实机：tab「例程」「待办」✓、表单标题「新建例程」✓、分段按钮「提醒/执行命令」无 emoji ✓、**「新建」按钮与最后一行字段（时间窗行/调度行）同行右对齐** + 蜜橘橙非默认色（Vision+OCR 双重确认）✓、列表四件套+💧/⚡徽标+调度摘要 ✓ |
| TC-M4-03 调度纯函数 | **PASS** | 单测真实性抽查：daily/once 分派、snooze 优先非 max、reload 错过检测、`catchup_window_boundary_14m59s_fires_15m01s_skips`、interval v1 断言保留——断言全部具体可执行 |
| TC-M4-04 collect_due 闭环 | **PASS** | `once_skipped_writes_last_skipped_and_stays_max_across_reload`、`paused_daily_once_records_skipped_and_resumes_without_catchup`、`dispatch_exec_queues_third_beyond_limit`（真进程断言+清理） |
| TC-M4-05 定点触发 | **PASS** | 实机：daily 23:05:42 准点 ✓；once 23:06:42 触发+完结（不再触发）✓；weekday=[3]（周三）今天周二不触发，列表摘要「周三 23:07 从未触发」✓ |
| TC-M4-06 exec 执行链 | **PASS** | 实机全链：`echo ok`→ok/exit0/output"ok"+气泡「Exec-echo-ok：任务完成」；`exit 3`→failed(3)；`sleep 600`+1min 超时→**60.0s 整杀组，`ps` 无残留**+summary timeout:1；`yes` 洪水→output_tail **2054B**+`…(已截断)`；cwd=/tmp→pwd 输出 /private/tmp ✓；独立 spawn 不阻塞 tick ✓ |
| TC-M4-07 validate | **PASS** | `normalize_resets_unrelated_fields_on_kind_switch`（清窗口防误 skipped）、once 过去拒绝、weekdays JSON 拒绝、exec JSON 失败拒绝、timeout 1–120 缺省 10（action_params 落库核实 `{"command":"echo ok","timeout_minutes":10}`） |
| TC-M4-08 opencode 模板 | **PASS** | 模板命令逐字拼装（--title/--auto/无 --dir）DB 落库核实；真实例程（`opencode run --title "pulsepet 例程: md计数" --auto`）→ agent 真实执行（find 数出 **132 个 md**、11k tokens/3 msgs）；**opencode.db 会话标题「pulsepet 例程: md计数」完整保留（--title 未被自动摘要覆盖，R8 可行性成立）**；cwd 生效 |
| TC-M4-09 权限行为 | **PASS** | 无 --auto：output_tail 含 `permission requested: external_directory (/tmp/*); auto-rejecting` → 拒绝后 agent 继续、任务正常结束（**不卡死**）✓；带 --auto：写入放行（Wrote file successfully，文件真实落盘）✓ |
| TC-M4-10 宠物状态两层 | **PASS** | 实机：exec 执行期状态芯片显示**「例程 · working」**（修订后口径）✓；apply+notify 成对 mock 断言、不污染 AgentActivity、心跳 15s 注入时钟单测（`heartbeat_interval_keeps_session_alive_between_recycles`）、agent 优先级合并单测 ✓ |
| TC-M4-11 结果气泡边界 | **PASS** | 实机：气泡 text=任务名+summary 双语渲染 ✓；exec 触发**不写 reminder_logs** ✓（全链核实）；无 snooze 按钮（单测 `snoozeReminderBubble exec 返回 false` + 视觉无按钮）✓；点宠物即消——GUI 锁未实机，由 M2 ack 单测覆盖（降级说明） |
| TC-M4-12 补跑与暂停 | **PASS** | 实机三径：①App 关闭跨 23:03 重启 → 23:09:17 **窗内补跑**（reload 错过检测）✓；②App 关闭跨 00:36 重启（17min 超窗）→ **skipped**（`task.summary.missed`+scheduled_at 溯源）✓；③暂停期 daily 到期 → exec 落 skipped（`task.summary.paused`）/notify 不落库、last_skipped_at 写、每 tick 一次、**恢复不补跑** ✓；notify/exec 同窗 ✓；连环补跑观察项（23:09:17 双规则同 tick 补跑正常，记录级） |
| TC-M4-13 snooze | **PASS**（部分降级） | 实机：气泡 hover **浮现「⏱ 10min」按钮**（Vision 确认）✓；**snooze_until 持久化 + 重启重发**：DB 注入 00:13:03 → 重启 → 00:13:05.4 重发、snooze_until 清空、interval 锚点推进 ✓；按钮点击 invoke 因锁屏未实机（命令级单测 `reminders_snooze_command_writes_until_and_closes_log` 覆盖写表+结案+next_due）——**降级说明** |
| TC-M4-14 跳过本次 | **PASS** | 实机：UI「跳过本次」toast「已跳过本周期」✓；once-skip3 跳过 → 23:22 到期**未触发**（无 log 无记账）✓；daily 跳过 + 重启后重触发 = **TC-M4-14-4 已知边界实机复现**（跳过未持久化，记录级）；once 重启补跑边界同复现 ×2（记录级） |
| TC-M4-15 退出处置 | **FAIL** ⚠ | ①Exit 遍历句柄**杀进程组无残留**（ps 断言）+ running→failed 补写 ✓，**但 summary 竞态被覆盖为 `task.summary.failed` 而非「App 退出中断」**（见缺陷 P2）②完成先移除登记表单测 ✓ ③启动幂等清理**实机** ✓（崩溃 kill -9 → 重启「startup cleaned 1 stale running action log」→ failed+stale）；崩溃孤儿残留实机复现（记录级） |
| TC-M4-16 执行历史区 | **PASS** | 实机：倒序 5 条/分页「第1/1页·共5条」、行四件套、**状态色点绿/红**（Vision）、⚡徽标、展开「输出尾部（≤2KB）」等宽 output_tail ✓；tempdir 单测 `action_logs_crud_pagination_and_orphan_survival`（61 行/50 页/悬空保留/快照）✓ |
| TC-M4-17 双语与主题 | **PENDING-USER** | zh 实机全过（例程/待办/新建例程/芯片例程/summary 双语渲染）；en 与深色主题被锁屏阻断；i18n zh/en 键集合完备性单测 ✓ + en 字典核实（Routines/Todo/Routine 单数） |
| TC-M4-18 Windows | **SKIPPED**（挂观察项，不判失败） | 代码级：powershell -NoProfile 分支 + taskkill /T /F 存在（action_exec.rs） |
| 并入① Token 面板定格 | **PENDING-USER** | 代码级 ✓：TokenStats.tsx:145 `onFocusChanged → load()` 双触发接线在（仿 Settings）；长运行首开面板近实时值实机验证被锁屏阻断 |
| 并入② resetTodayCache | **PASS** | `grep resetTodayCache` 全仓**零命中**（src/ 无死导出） |

**回归抽查**：TC-RM 去重（3min 窗多次实机拦截 ✓）、烟花叠加（该喝水啦 use_fireworks=1 触发 fireworks 窗口 ✓）、interval 窗口纯函数（单测 ✓）、M2 tab 注册表（待办 tab 显示 ✓，禁用插件 tab 消失由 registry.test.ts 覆盖）、气泡排队 critical 抢占 ambient（4/5 次实机成功 + 队列顶替单测完备）。

## 4. 缺陷清单

| 级别 | 位置 | 描述 | 建议 |
|---|---|---|---|
| **P2 (IMPL_BUG)** | `action_exec.rs:561 abort_all_on_exit` + `reminder_scheduler.rs:1214 finish_action_log_with` | **TC-M4-15-1「App 退出中断」summary 竞态**：abort 先 `kill_process_tree` 后写库（`WHERE status='running'`），被杀进程唤醒 async 完成回调（`finish_action_log_with` **无 status 守卫**）抢先写入通用 `task.summary.failed`，abort 的 interrupted 写入落空。实机 1/1 次复现（00:15:50 退出后 DB 为 failed 而非 interrupted）。单测 `abort_all_on_exit_kills_and_writes_failed` 为 mock 环境无真实 runtime 竞态，未钉住 | abort 先 UPDATE 日志再杀进程组（写库在 kill 前），或将完成回写加 `WHERE status='running'` 守卫且 abort 优先；补一个真实进程的集成钉子 |
| **P3 (观察项)** | 气泡队列（petStore/bubble-queue） | 23:21:20 提醒气泡（critical）未抢占 ambient 工具气泡的单次现象（当时显示「正在跑cd」，其余 4 次抢占均正常；队列逻辑单测完备）——疑为 webview 事件投递延迟，无法在代码层复现 | 记录级，后续如再出现再深挖 |

## 5. 观察项（记录级）

1. 连环补跑：23:09:17 单 tick 双规则补跑（once-skip-test + reload-catchup-test）正常，无并发问题；
2. TC-M4-14-4 已知边界实机复现 ×2：once/daily 跳过后在补跑窗内重启 → reload 重新触发（#53/#54/#55 均被重启重新武装）；
3. 崩溃孤儿进程残留（TC-M4-15-3）：kill -9 后 `sleep 300` 存活（已人工清理），重启幂等清理正常；
4. tick 相位随重启漂移（:18/:33/:42 等）——interval 首 tick 跳过 + MissedTickBehavior::Skip 设计内行为；
5. `reminders.created_at` 依赖应用写入 RFC3339（DB 默认值格式不可解析 → floor=now 兜底）：仅影响手工 SQL 注入行，真实创建路径无影响（非缺陷）；
6. 测试产生的 3 个真实 opencode 会话（md计数/权限测试/权限测试2）留在用户 opencode.db——属正常会话且该库全程只读，不清理。

## 6. 环境恢复声明

- **进程**：PulsePet 已退出（测试前未运行）；无残留子进程（含测试 exec 进程全部杀净）；
- **pulsepet.db**：测试规则 21 条全删；action_logs 33→**0**；reminder_logs 151→**133**（测试前基线）；#39 该喝水啦 `use_fireworks` 恢复 **1**；app_state 全部默认值（paused=0 / fireworks_global=0 / toolBroadcast=true / pet.position=2430,1134 未动 / ui.language=zh / theme=light）；
- **opencode.db**：全程 `sqlite3 -readonly` 只读，零写入；
- **仓库工作区**：零测试残留（测试工具/截图/脚本全部位于 `/var/folders/.../opencode/m4-test/`，106 张证据截图留档）；git 工作区仅测试前已有的 docs 修订与流程文件；
- **/tmp**：`oc-noauto-test2`、日志等测试产物已清；
- **显示器锁屏**：00:10 系统自动锁屏，需用户解锁（Touch ID/密码）。

## 7. 结论

**testVerdict: FAIL**

- 单一失败项：**TC-M4-15-1**（P2 竞态——退出处置的「App 退出中断」summary 不稳定达成，实机被通用 failed 覆盖），需 coder 修复后重测；
- 两项 **PENDING-USER**（TC-M4-17 en/主题视觉、并入① Token 面板实机）——显示器锁屏阻断，非实现缺陷，解锁后补验即可；
- 其余 15 项 PASS + 2 项记录级已知边界。

**testedSha: `bef21cccd9c0d7d594678584fcd2578373608b22`**
