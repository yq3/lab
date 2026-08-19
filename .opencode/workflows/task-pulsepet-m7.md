---
taskId: task-pulsepet-m7
target: pulse-pet
coderTaskId: ses_ff06c8318ffeAnxMQyft4iPTam
testerTaskId: ses_ff026fea3ffe5fGkfkxrp3uBbi
committerTaskId: ses_feffea28cffeE07dRMMlmIisas
status: approved
round: 1
maxRounds: 3
testVerdict: PASS
reviewVerdict: APPROVED
testedSha: 5a35019
reviewedSha: 5a35019
filesChanged: [src-tauri/migrations/002-m7-todo.sql, src-tauri/src/todos.rs, src-tauri/src/plugins.rs, src/lib/todos.ts, src/lib/todos.test.ts, src/lib/todo-bridge.ts, src/panel/plugins/Todo.tsx, src-tauri/src/db.rs, src-tauri/src/reminder_scheduler.rs, src-tauri/src/atlas.rs, src-tauri/src/lib.rs, src-tauri/Cargo.toml, src/lib/reminders.ts, src/lib/reminders.test.ts, src/lib/reminder-bridge.ts, src/pet/petStore.ts, src/pet/petStore.test.ts, src/pet/PetCanvas.tsx, src/panel/Reminders.tsx, src/panel/Panel.tsx, src/panel/Settings.tsx, src/lib/interaction.ts, src/lib/interaction.test.ts, src/main.tsx, src/styles/global.css]
endReason: null
createdAt: 2026-08-17T19:51:32+0800
updatedAt: 2026-08-19T09:55:45+0800
---

# task-pulsepet-m7: M7 Todo 插件 + 插件机制骨架

## 任务原文

（DESIGN §10 M7 + §8 Todo 插件机制 + §5.4 todo 派生提醒约定；验收标准对应 TEST-CASES TC-TD-01~09）

**M7 范围（DESIGN §10 M7，1 周）：**

1. **插件 manifest + 权限面（声明级，v1 无运行时复检、无沙箱、所有插件皆内置）**：`~/.pulsepet/plugins/todo/plugin.json`，内容含 `id: "built-in-todo"` / `name: "Todo"` / `version: "0.1.0"` / `manifestVersion: 1` / `permissions: ["schedule", "notify", "ui:panel-tab", "todo:*"]` / `configSchema` / `panelTab: { "title": "Todo", "icon": "check-square" }`；`plugins` 表登记该插件元数据；控制面板出现 Todo tab（TC-TD-01 / TC-TD-09）。
2. **todo CRUD（Rust 侧命令 + 前端 Todo tab UI）**：todos/todo_tags 读写，字段含 title/notes/priority(0-3)/due_date/remind_before_minutes/completed_at/sort_order/created_at/updated_at；tag 增删即时反映到 `todo_tags`（todo 删除时级联删 tags）；列表按 `sort_order` 排序显示、修改后顺序立即更新；UI 与库一致（TC-TD-02）。
3. **派生提醒（B16 定案通道，DESIGN §8.3/§5.4）**：todo 写入/修改时，若 `due_date` 带时间且 `remind_before_minutes > 0`，Rust 侧 todo command 同步 upsert 一行 `reminders`：`kind='todo'`、`source_todo_id=<todo.id>`、`interval_minutes=0`、`start_time = due_date - remind_before_minutes`；调度器统一消费，不另查 todos 表。`remind_before_minutes = 0` 时不派生（reminders 表不出现该行，完全无提醒，不提前也不到点）——随后若修改 due_date 且 >0 才 upsert 派生（TC-TD-03 / TC-TD-08）。
4. **到点提醒**：宠物气泡显示"还有 X 分钟要完成「任务名」"（TC-TD-03）。
5. **todo 完成联动**：完成一个任务 → 宠物播放 `waving` 动画 + 气泡"干得漂亮 🎉"；`completed_at` 写入；派生 reminder 级联删除/不再触发（TC-TD-04 / TC-TD-07 删除路径）。
6. **今日全清庆祝**：完成今日全部任务（最后一个完成时）→ 气泡显示今日完成数（"今日完成 N 项"）；"今日"按用户本地时区自然日（00:00 起）按 `completed_at` 统计（与 token 聚合 localtime 语义一致）；jumping 二级庆祝 v1 不做强制（TC-TD-05）。
7. **非周期只触发一次**：`kind='todo'` 仅触发一次；调度器根据 `reminders.last_triggered_at` 与当前时间判断不再重发（**唯一防重来源**）；`todos.remind_last_triggered_at` 保留字段 v1 不写入不读取（TC-TD-06）。
8. **删除/完成级联清理**：删除带派生提醒的 todo 或完成 todo，对应 `reminders` 行被级联删除；`reminder_logs` 历史保留（TC-TD-07）。

**M7 范围内遗留清偿（来源 M4 P2 ②③，todo 接入时处理）：**

- M4 P2 ②：Reminders.tsx ruleToForm 不再把 todo 降级为 custom——todo 规则快捷开关/编辑不得改写 kind、不得丢 source_todo_id（interval=0 也要被表单接受）。
- M4 P2 ③：reminder_scheduler.rs validate_input 收紧——todo kind 强制 interval=0（spec 约定 todo 恒 0 一次性；核实现有 `max = if kind=="todo" {0} else {1}` 逻辑是否已覆盖 upsert 入口，未覆盖则补齐）。

**M7 范围内遗留清偿（用户 2026-08-17 确认"能并入都并入"，全部并入）：**

- M4 P2 ④：播放中被打断时旧 log dismissed_via 残留 NULL 补报（M7/M8 前可选，本轮并入——完成联动/fireworks 打断路径顺带处理）。
- M5 P2 ⑤：list_pets_in 逐项全量解码慢 → 改头部尺寸校验（M7/M8，本轮并入）。
- M5 P2 ⑥：decode_sheet 无解压炸弹防护 → image::io::Reader limits 加固（M7/M8，本轮并入）。
- M6 P2 ②：Settings.tsx onPassThrough 成功清 error 连带清 atlas 错误横幅（M7/M8，本轮并入）。

**范围外（继续移交，不在本任务处理）：** M4 P2 ① cover_monitor 竞态（M8 多屏实机）、⑥ .catch 静默吞（后续）、⑦ watchdog 截断（概率极低）；M6 P2 ③ resolve_restore_target monitors[0]（M8 评估）；限流豁免 /health（心跳引入时）；install.ps1 BOM / classifyEvent permission.asked（M8）；Windows 实机验证（M8）；多显示器烟花绽放点实机 + 跨屏烟花评估（M8）；多屏实机 TC-APP-10/11（M8）；M5 P2 ⑦ 不可达分支（可不动）；M5 观察项①②③（可不动/环境容差/设计结果）；M6 观察项（合成输入噪声，多屏 M8 待验）。

## 需求确认

- [x] 用户已确认（确认后 status=implementing）——2026-08-17 19:54 用户确认：M7 范围照执行；**遗留事项"能并入都并入"**——M4 P2 ②③ + 可选并入四项（M4 P2 ④、M5 P2 ⑤⑥、M6 P2 ②）全部并入本任务；无范围调整
- 历史遗留事项清单（supervised-coding 扫描 task-pulsepet-m1~m6 检查点汇总，默认并入本任务，见 README §4.6）：
  - **并入本任务（M4 P2 ②③，标注 M7）**：Reminders.tsx ruleToForm todo 降级 custom；validate_input todo kind+interval>0 收紧。均随 todo 接入时处理。
  - **并入本任务（M4 P2 ④，用户确认并入）**：播放中被打断时旧 log dismissed_via 残留 NULL 补报。
  - **并入本任务（M5 P2 ⑤⑥，用户确认并入）**：list_pets_in 逐项全量解码慢（改头部尺寸校验）；decode_sheet 解压炸弹防护（image::io::Reader limits 加固）。
  - **并入本任务（M6 P2 ②，用户确认并入）**：Settings.tsx onPassThrough 成功清 error 连带清 atlas 错误横幅。
  - **不并入（去向注明）**：M4 P2 ①（M8）、M6 P2 ③（M8）、限流豁免 /health（心跳引入时）、install.ps1 BOM / classifyEvent（M8）、Windows 实机（M8）、多显示器烟花绽放点实机 + 跨屏烟花（M8）、多屏实机 TC-APP-10/11（M8）、M5 P2 ⑦（可不动）、M5 观察项三条（可不动）、M6 观察项（M8）。

## 遗留事项（跨任务移交）

- [x] **M4 P2 ②③ 清偿（来源 task-pulsepet-m4 committer R1，2026-08-17 本任务清偿）**：Reminders.tsx ruleToForm todo 不降级（类型/间隔/时刻锁定，仅开放文案/启用/烟花）；validate_input todo kind 强制 interval=0 覆盖 insert/update/upsert 三入口。tester PASS + committer APPROVED。
- [x] **M4 P2 ④ 清偿（来源 task-pulsepet-m4，2026-08-17 本任务清偿）**：播放中被打断旧 log dismissed_via NULL 补报（superseded 顶替 + watchdog 6.5s 补报，dismiss 只动 NULL 行；结果级全库 0 条 NULL）。tester PASS + committer APPROVED。
- [x] **M5 P2 ⑤⑥ 清偿（来源 task-pulsepet-m5 committer R1，2026-08-17 本任务清偿）**：list_pets_in 头部探测（probe_pet_dir/sheet_dimensions 只读尺寸不解码像素，实测含炸弹素材下拉秒开）；decode_sheet image::io::Limits 加固（16384²/512MB，构造 30000×30000 声明 PNG 实测拒载回退不 OOM）。tester PASS + committer APPROVED。
- [x] **M6 P2 ② 清偿（来源 task-pulsepet-m6 committer R1，2026-08-17 本任务清偿）**：Settings.tsx 穿透错误独立 state（成功只清穿透错误，不连带清 atlas 错误横幅）。tester PASS + committer APPROVED。
- [ ] **M7 新移交（2026-08-17，committer R1 P2×4 不阻断，去向注明）**：① 002 迁移非事务化（db.rs migrate execute_batch 逐条 autocommit，崩溃可致启动失败）——**M8 收尾**（包 BEGIN/COMMIT 一行）；② 重武装边界补单测 + spec 备注（due 变化但 start 分钟级未变时不重发）——**随 M8 或顺带**；③ 暂停×todo 一次性到期语义未定义（paused 只顺延 interval>0，todo 恢复后下一 tick 补触发，与 M4"暂停不补弹"定案有张力）——**回 spec 确认**（supervised-coding 落笔）；④ TS/Rust 校验口径差补测试（notes 长度 2000、2026-02-31 由 Rust 拒绝契约）——**随 M8 或顺带**。
- [x] **M7 回 spec 已落笔（2026-08-17 22:06 用户确认三条，supervised-coding 已 edit 落笔 DESIGN.md）**：① §8.1 manifest 示例 permissions 补 `todo:*`（4 项，标注"M7 定案：含 todo:*，与 TC-TD-01 一致"）；② §5.4 reminder_logs DDL 后加 M7 定案注释（002 迁移后无 FK、所有 kind 历史 log 一律保留、悬空引用由 insert_log 唯一写入保证、stats INNER JOIN 数字无影响）；③ §5.4 todo 派生提醒约定段追加"重武装（M7 定案）：start_time 变化清 last_triggered_at 重发；due 变化但 start 分钟级未变不重发"+"暂停×todo（M7 定案）：一次性提醒暂停期间不补发错过场次、恢复后下个 tick 触发一次"。改动待交付流程 coder 回 spec 提交（coder 禁改文档，仅提交）。
（新任务开工时 supervised-coding 读历史检查点的本节 + 轮次记录中"移交/待办"条目；未了结事项默认并入新任务处理并更新相应测试用例；处理完毕回写勾选并注来源任务 ID，继续移交的注明去向）

## 轮次记录

- R1: coder 完成，commit `5a35019`（`[task-pulsepet-m7] R1: M7 Todo 插件 + 插件机制骨架——内置 built-in-todo manifest/权限面、todos CRUD+tags+sort_order、B16 派生提醒(kind='todo' 单次/start=due-before/due 变化重武装)、完成联动 waving+气泡、今日全清统计、删除/完成级联(reminder_logs 历史保留)；清偿 M4 P2②③④ + M5 P2⑤⑥ + M6 P2②`，分支 develop_opencode，提交前已 fetch + merge origin/develop=160d087）。改动：25 文件 +2924/-94（新增 7：migrations/002-m7-todo.sql（reminders.todo_due_at 列 + reminder_logs 去 FK 级联重建保历史）、todos.rs（todo CRUD/完成/重排 + B16 派生提醒 upsert 同步/删除/重武装 + 今日全清统计 + todo://completed 事件 + 15 单测 + mock runtime 集成测试）、plugins.rs（内置 manifest 物化 ~/.pulsepet/plugins/todo/plugin.json + plugins 表登记 + plugins_list 命令 + 3 单测）、todos.ts（类型/校验/due 形态互转/文案/事件解析/celebrationText/命令封装）、todos.test.ts（20 用例）、todo-bridge.ts（pet 窗口 todo://completed 桥）、panel/plugins/Todo.tsx（Todo tab UI 列表/表单/tags/↑↓重排/完成勾选/manifest 信息栏）；修改 18：db.rs（SCHEMA_VERSION=2 分步迁移 + 2 迁移测试）、reminder_scheduler.rs（todo_due_at 字段/parse_due_like_ms/绝对时刻 next_due+到点判定/TriggerPayload.todo_due_ms/validate_input todo 恒 0 M4 P2③/fw_active_log 顶替+watchdog 补报 M4 P2④/reload_from_app 泛化 + 5 新测试）、atlas.rs（decode_sheet 加 image Limits M5 P2⑥ + sheet_dimensions/probe_pet_dir 头部探测 M5 P2⑤ + list_pets_in 不再全量解码 + 3 新测试）、lib.rs（注册 plugins/todos + 6 命令）、Cargo.toml（dev-deps + tauri(test) mock runtime）、reminders.ts（ruleToForm 导出 todo 不降级 M4 P2②/todo_due_ms）、reminders.test.ts（+3）、reminder-bridge.ts（todoReminderText"还有 X 分钟"文案）、petStore.ts（celebration 状态 startCelebration until 自过期）+petStore.test.ts（+3）、PetCanvas.tsx（庆祝期覆盖 success 行=waving）、Reminders.tsx（todo 派生规则编辑不降级，仅开放文案/启用/烟花）、Panel.tsx（Todo tab 接入）、Settings.tsx（穿透错误独立状态 M6 P2②）、interaction.ts+.test.ts（normalizeTab 白名单加 todo）、main.tsx/global.css（initTodoBridge 接线/样式））。自测证据：npm test 204/204（19 files，基线 184→+20）、cargo test 140+1 ignored（基线 115+1→+25）、tsc --noEmit exit 0、npm run build 成功（355ms）、cargo build 0 warnings、tauri build 成功（.app+.dmg）；运行时 E2E（macOS 真实 GUI + AX + OCR）：TC-TD-01 manifest 生成+plugins 表登记+Todo tab 出现；TC-TD-02 CRUD+tags 落库+重启回显；TC-TD-03 due=20:52/before=1 派生行 20:51 触发气泡 OCR「还有1分钟要完成「M7E2E冒烟」」；TC-TD-04/05 完成→completed_at 写入+派生行删除+气泡「今日完成1项」（all_today_done 变体；"干得漂亮 🎉" 普通变体单测覆盖）；TC-TD-06 触发过派生行重启 5 tick 0 refire；TC-TD-07/08 cargo 单测覆盖+运行时完成删行实证。遗留/裁定点：① 需求边界（备注级）：DESIGN §8.1 manifest permissions 示例 3 项 vs 任务书/TC-TD-01 要求 4 项含 todo:*——按任务书实现，与 TEST-CASES 一致无需回 spec；② 02 迁移抹 reminder_logs FK（无引用重建保历史，代码层 insert_log 唯一写入，可接受裁定）；③ 编辑 todo 派生规则时 label 下次保存被 todo title 覆盖（B16 source of truth 自然结果，提示文案已说明）；④ waving 视觉无实机确认（像素 diff 间接证据+映射纯函数 M5 已测）；⑤ remind_last_triggered_at 保留列零引用已实现；⑥ 移交 tester 手测项：Todo 表单 date/time picker AX 无法操作部分（本次经 db+文本字段路径覆盖）。测试数据清理：测试 todo/tags/派生 reminders/logs 全删、用户数据与备份 diff 完全一致、进程杀净、唯一保留差异 user_version 1→2（预期迁移）。

- R1: tester 验证 **PASS**（testedSha=5a35019）。环境：macOS arm64 真实 GUI 会话单屏 dpr=2，release 构建二进制，HEAD=5a35019 与提交链核对一致，工作区仅检查点未跟踪。用户数据基线备份 baseline.db（user_version=2、app_state 7 项、plugins 1 行、reminders 2 条、logs 7 条、todos 1 行）。⚠️ 验证开始发现 coder 清理遗漏：todos 残留 1 行「Hello」（21:08 创建，按基线保留未删，观察项）。自动化基线 5 项全实际复跑与 coder 自述一致：npm test 204/204（19 files）、cargo test 140+1 ignored、tsc --noEmit exit 0、npm run build 成功（357ms）、tauri build 成功（.app+.dmg）。**TC-TD 逐条 9/9 PASS**：01 插件清单与注册 PASS（plugin.json 逐字段核对 4 权限+panelTab、plugins 表登记 built-in-todo|Todo|0.1.0|1|1、panel OCR「Token / 提醒 / Todo M7 / 设置」+ manifest 信息栏含权限）；02 CRUD PASS（UI 新建/编辑/删除、字段逐列核对、tag 增删即时、priority 0-3 双端校验、sort_order 重排 UI 立即更新、重启回显 3 任务、删除级联 tags 实测 FK=ON）；03 到点提醒 PASS（派生行 id=34：kind='todo'/interval=0/start=21:30=due 21:35−5min/source_todo_id=3/todo_due_at；气泡 OCR 两次实捕「还有3分钟要完成「M7CRUD-任务A」」「还有0分钟要完成「M7TC06-单次」」与剩余分钟 round 一致；调度器统一消费不查 todos）；04 完成联动 PASS（completed_at=2026-08-17T21:34:50.276+08:00 写入、派生行级联删、气泡「干得漂亮 🎉」OCR 6 帧、waving 12 帧 diff 0.6%~6.1% 非静止+代码级映射）；05 今日全清 PASS（完成今日第 3 个→「今日完成3项」OCR 8 帧、N 与 db 一致、重启后统计保持）；06 非周期单次 PASS（触发后 3 tick 0 重复+重启 2.5 分钟 0 refire；remind_last_triggered_at 全仓 grep 零写入零逻辑读取）；07 级联清理 PASS（两步删除带已触发派生行→reminders 级联删+reminder_logs id=70 保留 dismissed_via='auto' 完好）；08 remind=0 不派生 PASS（due 纯日期无行、db 注入带时间 remind=0 编辑保存仍无行、改 0→1 upsert 派生行 id=35 出现）；09 权限面声明 PASS（全仓无运行时复检、无沙箱、无第三方安装入口）。**遗留清偿 6/6 PASS**：M4 P2②（ruleToForm 保留 kind/interval、UI 编辑 todo 规则类型 select「待办（派生）」disabled+提示文案）；M4 P2③（validate_input todo 强制 0 覆盖 insert/update/upsert 三入口+派生路径硬编码 0+单测）；M4 P2④（superseded 顶替补报+watchdog 6.5s 补报+dismiss 只动 NULL 行；结果级全库 0 条 NULL dismissed_via；顶替实测两次「试一试」连点未命中 UI 操作失败未产生两场重叠）；M5 P2⑤（probe_pet_dir/sheet_dimensions 只读头部不解码、list_pets_in 改 probe、含炸弹素材下拉秒开无卡顿）；M5 P2⑥（sheet_limits 16384²/512MB；构造 30000×30000 声明 PNG 实测：下拉显示「bomb-pet — 素材损坏/非标准，不可选」+ notice「读头部尺寸失败：Image size exceeds limit，已回退内置占位 blinking-kitty」，无卡顿无 OOM）；M6 P2②（passThroughError 独立 state，成功只清穿透错误不碰 atlas 横幅）。**回归抽查**：提醒「试一试」气泡 OCR+8s auto 消失、烟花路径 dismissed_via='fireworks'、atlas 正常+损坏回退、pet 单击轮换/拖拽/右键菜单/完成联动互不破坏。**缺陷：P0/P1 均无**。观察项 5（非阻断）：① coder 测试残留 todos「Hello」行（清理未净）；② WebKit date/time 空值渲染为今天/12:30（本地化行为，value 实为空）；③ WebKit date/time 键盘输入不可预测（走系统 picker 无碍，TC-TD-02/03 date/time 经 db 注入+表单回显等效链路覆盖）；④ M4 P2④ 顶替实测未完成（UI 连点失败，代码级+结果级充分）；⑤「还有 X 分钟」X=round 取整已过期钳 0，两次实测一致语义合理。**环境恢复**：db .dump 与 baseline 完全一致（sqlite_sequence 序列值已恢复、reminders id=11 last_triggered_at 恢复 21:10:17.604、app_state 7 项原值、fireworks_global=1、pet.position=(2500,454)）；测试 todos/tags/派生行/logs 全删、bomb-pet 素材已删；进程杀净；保留项=plugins 登记行/plugin.json/user_version=2（预期迁移）。

- R1: committer 审查 **APPROVED**（reviewedSha=5a35019，双通过达成）。评审对象核对：HEAD=5a35019=testedSha、单 commit 父=160d087=origin/develop、25 文件全在 pulse-pet/ 内无越界、依赖仅 dev-dependency tauri(test)（Cargo.lock 零变化）、DESIGN/TEST-CASES/AGENTS 未改动。需求对应性 8/8 + 遗留清偿 6/6 + 不做项零预实现（http_server/windows/hotkeys/tray/session_state/token_stats/runtime 均不在 diff；cover_monitor 未动；jumping 仅预留注释；plugins_root Windows 分支为跨平台路径正确性所需）。特殊裁定点复核：002 迁移分步正确（ALTER 加列→无 FK 重建保数据→DROP→RENAME、v1→v2 数据保留单测、SCHEMA_VERSION=2 一致、幂等单测；去 FK 后 reminder_logs 唯一代码写入路径=insert_log 引用完整性代码层保证）；todo_due_at/parse_due_like_ms 语义（纯日期=当日 00:00、带时间=本地 epoch ms、到点=绝对时刻 next_due、round+钳 0 与 OCR 实测一致、remind=0 不派生+due 变化重武装清 last_triggered_at）；防重唯一来源 reminders.last_triggered_at（remind_last_triggered_at 全仓仅 SELECT 透传列零写入）；级联事务性（autocommit 顺序执行半途概率极低→P3）；权限面声明级（无运行时复检/沙箱/第三方安装入口）；todo://completed 链路（桥路由门控、celebration {id,until} 自过期、显示层覆盖 success 行 raw 状态不丢、ackReminderBubble 非提醒返回 false 交回轮换、拖拽/右键未触碰）。测试质量：计数复核一致（Rust 140+1=+25=todos 12+plugins 3+scheduler 5+atlas 3+db 2、TS 204=+20=todos.test 14+reminders.test 3+petStore.test 3；⚠️ 检查点 coder 报告行文归属有误"todos.rs 15 单测"实为 11+1、"todos.test.ts 20 用例"实为 14，总数一致属记录性误差 P3）；断言以 db 状态级为主真实有效；mock runtime 集成测试真实调用 command+managed state+reload 副作用断言非走过场。**问题清单：P0/P1 均无**。P2×4（不阻断，去向注明）：① db.rs migrate+002 迁移非事务化（execute_batch 逐条 autocommit，崩溃可致启动失败）——M8 收尾（修复成本一行包 BEGIN/COMMIT）；② 覆盖缺口：重武装边界无测试（due 变化但 start 分钟级未变时不重发，语义合理但 spec 措辞"due 变化重武装"）——补一条单测钉住边界 + spec 备注；③ 覆盖缺口：暂停×todo 一次性到期未定义（paused 分支只顺延 interval>0，todo 恢复后下一 tick 补触发，与 M4"暂停不补弹"定案有张力）——回 spec 确认或加注释+测试；④ 覆盖缺口：TS/Rust 校验口径差无测试（TS 不查 notes 长度 2000、TS 正则放过 2026-02-31 而 Rust chrono 拒绝）——补 TS 校验或固定"由 Rust 拒绝"契约测试。P3×7（记录级）：① reminder_scheduler.rs:532 注释过时"级联清 reminder_logs 由 schema CASCADE 保证"（002 后不成立，改"历史保留（孤儿行不入 stats）"）；② todos.rs CRUD/complete 未包事务（派生同步失败半落概率极低）；③ delete_todo 不检查 n==0、todo_reorder 不校验 id 完整性；④ plugins::ensure_builtin_plugins 失败阻断 App 启动（lib.rs ?，建议降级 eprintln+继续）；⑤ Todo.tsx notes 无 maxLength、showToast 多 toast 竞态；⑥ 检查点 coder 报告测试归属行文误差；⑦ tester 观察项 5 条已记录无新动作。**需求边界问题（建议 supervised-coding 回 spec，非阻断）**：① DESIGN §8.1 manifest 示例 permissions 3 项缺 todo:*（实现/TC-TD-01 为 4 项，建议顺手补）；② DESIGN §5.4 reminder_logs DDL 仍写 REFERENCES reminders(id) ON DELETE CASCADE（002 后实际无 FK，且级联去除是全局的——所有 kind 历史 log 一律保留，建议 DESIGN 注明）；③ 重武装与暂停语义两处建议 DESIGN 落一句备注。**最终判定：APPROVED**（需求 8/8、遗留 6/6、裁定点全复核通过、无隐藏缺陷）。交付把关：放行（待用户确认交付后执行留痕）。

- **交付执行①（2026-08-17 22:09 用户确认交付）**：Coder 完成——回 spec 提交 `17aa817`（`[task-pulsepet-m7] R1: 回 spec 文档口径`，仅 DESIGN.md +5/-2，三处落笔逐字核验与检查点一致）→ 同步 origin/develop（0 behind）→ SSH 推送成功（94be5db..17aa817）→ 开 PR：**https://github.com/yq3/lab/pull/7**（base=develop / head=develop_opencode / OPEN，2 commits：5a35019 + 17aa817，26 文件 +2929/-96；body 8 节：摘要/验收结论（双 SHA=5a35019）/TC-TD 通过摘要/回归基线/回 spec 3 处/Known Issues（P2×4 去向+ P3 记录级 + M8 实机项）/用户数据与环境恢复/Evidence Manifest 占位）。待：Committer gh pr review 留痕 → Coder 补写 manifest → 汇报合入请求。

- **交付执行②（2026-08-17 22:12）**：Committer 已执行 `gh pr review 7 --comment` 留痕——**COMMENTED**（同账号 POC 约定，Review ID `PRR_kwDOTsiHgs8AAAABJy2rpA`，submittedAt 2026-08-17T14:12:13Z UTC）：正文五节（① 评审对象核对：2 commits 提交链 5a35019→17aa817、双 SHA=5a35019、26 文件（25 业务+1 回 spec）全在 pulse-pet/、依赖仅 dev-dependency tauri(test) Cargo.lock 零变化、migration 002 合规；② 回 spec 复核：17aa817 仅 DESIGN.md 三处 +5/-2 逐字一致；③ R1 结论摘要：APPROVED 无 P0/P1、需求 8/8、遗留清偿 6/6、裁定点全复核通过、测试质量 npm 204/cargo 140+1 与 tester 一致；④ knownIssues 移交：P2×4 去向（迁移非事务化 M8、重武装边界补测随 M8、暂停×todo 已回 spec 定案、TS/Rust 校验口径差随 M8）+ P3 记录级×7 + M8 实机项 + tester 观察项（Hello 残留等）；⑤ 交付声明：COMMENTED 留痕、不自动合入、Evidence Manifest 待 coder 补写）。提交前确认 reviews=[] 无先前评审，提交后二次核验仅 1 条无重复。PR 保持 OPEN。manifest 占位待 coder 步骤③补写。

- **交付执行③（2026-08-17 22:16）**：Coder 已把 Evidence Manifest JSON 写入 PR #7 description（占位替换，14 顶层 key：taskId/pr/milestone/headSha(5a35019)/specCommit(17aa817)/commits 2 链/verdicts（PASS+APPROVED 双 SHA+reviewer COMMENTED PRR_kwDOTsiHgs8AAAABJy2rpA）/testEvidence（npm 204、cargo 140+1、tsc、build×2、migration v1→v2、E2E 证据、dependencies）/acceptanceCriteria（TC-TD-01~09 逐条 PASS）/specUpdates 3 处/legacyCleared 6 项/knownIssues（P2×4+P3×7+M8 实机项）/userDataNote（diff 一致+Hello 残留行保留）/timestamp）。核验：占位段消失（PLACEHOLDER=0）、前 8 节正文逐字节一致、JSON 完整可回析（14 keys）、无乱码。**交付三步全部完成**：① 回 spec 17aa817 + push + PR #7 ② committer gh pr review（PRR_kwDOTsiHgs8AAAABJy2rpA COMMENTED）③ manifest 落 PR description。PR #7 保持 OPEN，**等待用户合入决定（不自动合入）**。

- **合入（2026-08-19 09:55 用户确认）**：`gh pr merge 7 --merge` 成功——**MERGED**（merge commit `9a963c121110e27017508e44b64a80c4ab150ec7`，mergedAt 2026-08-19T01:55:09Z）；本地 develop_opencode 已 fetch + fast-forward 至 9a963c1=origin/develop。M7 任务收官（status=approved，testedSha=reviewedSha=5a35019，PR 留痕 COMMENTED + manifest 齐备）。遗留事项已回写：M4 P2②③④、M5 P2⑤⑥、M6 P2② 勾选清偿；P2×4 去向注明（迁移非事务化→M8、重武装边界补测→随 M8、暂停×todo 已回 spec 定案、TS/Rust 校验口径差→随 M8）；回 spec 三条已落笔提交。

（R1 起逐轮记录 coder/tester/committer 结果）

## 最新验证意见原文

（tester/committer 报告逐字保留——恢复时给 coder 的修复依据）
