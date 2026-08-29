# PulsePet v2 未完成事项清单（Open Items）

> 生成：2026-08-27（v2 M6 合入 develop 后）
> 来源：Windows 实机使用反馈（[issue #19](https://github.com/yq3/lab/issues/19) / [issue #20](https://github.com/yq3/lab/issues/20)）+ 源码级诊断（2026-08-27，诊断结论已分别留痕于两 issue）
> 性质：两项 **Windows 特有缺陷**，根因已定位、修复方案已裁定（R1-R5，见 [§三](#三修复任务清单r1r5统一实施)）。
> **状态（2026-08-27 闭环）**：R1-R5 **已修复并随 `pulse-pet-v0.2.1` 发布**——实施 commit `6f9e0be`（R1-R4）/ `9e609d6`（R5）/ `acc12b3`（本文件）/ `f2cf13e`（版本 bump 四件套），tag `pulse-pet-v0.2.1`（CI run 33071206433 双矩阵 success，安装包挂 draft Release）。测试基线全绿（`cargo test` 320+3 钉子 / `npm test` 409 / `tsc --noEmit`），committer 评审 APPROVED（P0/P1=0，三条 P3 加固已落地）。**Windows release 实机三场景验证通过（2026-08-27，v0.2.1，§四）**，#19 / #20 可闭环。
> 共同背景：与 v1 issue #9 同源——Windows 上 WebView2 环境创建异步、主线程泵消息期间页面已加载执行（GUI 子系统 + 控制台子进程交互）的时序盲区；v1 里程碑"Windows 实机验证后移"的欠账在 v2 实机使用中集中显性化。macOS 开发机均无法复现。
> 构成说明（2026-08-27 补充）：§一~§四为 issue #19/#20 专项记录（**已闭环**）；§五起为 **v2 六里程碑（M1~M6）工作流检查点遗留事项汇总**（supervised-coding 2026-08-27 归档，来源 `.opencode/workflows/task-pulsepet-v2-m1~m6.md`），清偿后回写勾选并注来源任务 ID 与日期；**§十一为 2026-08-28 新增**：宠物大小三档 + 视觉归一化特性（设计 + 实施同日完成，含 en 右键菜单裁剪与 atlas 短缓冲两处存量缺陷清偿，见 §11.5 与 `docs/v2/pet-size.md`）；**§十二为 2026-08-28 二次新增**：v2 收尾用户反馈批次 F1~F16（气泡汇总 / Token 页柱图与文案 / 例程页全宽·notify 徽标·todo 类别列·todo 烟花勾选项·日期时间控件规格·历史统计区移除 / 设置页控件形态·接入卡缩高·命名统一·宠物下拉字样·二轮微调 / Windows 托盘与任务栏图标资产；**2026-08-28 用户批准后同日全部实施**，F16 为实施后目验二轮微调，见 §12.4）；**§十三为 2026-08-28 三次新增**：新增第三 agent 接入成本审计（预研备查——约 12 处老代码必改 + agent registry 收敛机会，是否立项待决策）；**§十四为 2026-08-29 新增**：token 统计跨天会话归属缺陷（聚合粒度 session 级 → 跨天会话 token 全部归到最后活跃日；修正方案已与用户对齐——day/week/range/today 四类聚合下沉 message 级按消息时间归天，**同日实施完毕**，见 §14.5 实施记录）；**§十五为 2026-08-29 四次新增**：Windows 托盘/任务栏图标 tile 化（F15 后续——复刻 macOS dock 系统合成底观感，tile 只上 Windows 侧资产 + tray.rs 平台分叉，**同日实施完毕**，见 §十五）；**§十六为 2026-08-29 五次新增**：panel 默认高度 640→650（Token 页图表日期标签被窗口底边裁半，用户目验驱动微调，见 §十六）；**§十七为 2026-08-29 六次新增**：设置页选择宠物下拉与「宠物大小」标签间距 +10px（原 0px 挤贴，用户目验驱动微调，见 §十七）；**§十八为 2026-08-29 七次新增**：卸载应用不自动清理接入插件——README 卸载插件节 + 设置页接入管理卡各加提示（用户问询驱动，见 §十八）。

---

## 一、issue #19：doctor 的 node 探测与面板焦点事件自激励死循环

> 状态：**已修复（R1-R4，commit 6f9e0be）+ Windows 实机验证通过（2026-08-27，v0.2.1）**；诊断评论见 [#19](https://github.com/yq3/lab/issues/19#issuecomment-5437033400)。
> 定级：设置 tab 无法正常驻留（日志风暴 ~4-5 轮/s，每轮 2 行 plog + 一次 node spawn），无数据损坏。

### 1.1 症状（2026-08-27 用户报告）

Windows release 构建打开控制面板切到设置 tab，`pulsepet.log` 疯狂滚动输出 `integrations status opencode/claude-code` 两行状态日志，无终止。

### 1.2 根因（源码级证据链）

日志节奏是关键线索：每轮两条相隔 ~200ms（= node probe 耗时），下一轮在上轮完成后 ~35ms 立即开始——不是定时轮询，是**每次调用完成后立即自我续期**的循环：

1. 切到设置 tab → `panel://tab`（或 focus）触发 `loadIntegrations()`（`Settings.tsx` focus/tab 双触发监听）；
2. Rust doctor **每次调用现测 node**（`integrations/mod.rs` `detect_node()`，V2-DESIGN §1.4.1 明确"不缓存"）→ `Command::new("node").output()`；
3. 已核对 Rust std 源码：Windows `Command` 默认 `flags: 0`，`output()` **不会**自动加 `CREATE_NO_WINDOW`；release 构建是 GUI 子系统（`main.rs` `windows_subsystem = "windows"`）→ 控制台子进程 node.exe 闪现控制台窗口，扰动前台焦点；
4. probe 结束（~190ms）→ 控制台销毁 → 面板重获焦点 → WebView2 派发 `tauri://focus` → Settings 的 `onFocusChanged(focused=true)` 再次触发 `loadIntegrations()` → 回到 2。

### 1.3 三个特征（与实测全部吻合）

| 特征 | 解释 |
|---|---|
| Windows 独有 | macOS 上 spawn node 不扰动 WKWebView 焦点（#9 同款盲区） |
| 设置 tab 独有 | 只有 doctor 每次调用 spawn 子进程 + plog；Token 页的 focus 刷新无子进程燃料，循环无法维持 |
| dev 构建复现不了 | Windows dev 下父进程是控制台子系统，子进程共享控制台不闪窗；只有 release 触发——CI 级静态兼容检查也扫不出 |

### 1.4 顺带审计：同类隐患（同一根因类别，v2 M4 引入）

| 位置 | 问题 |
|---|---|
| `action_exec.rs` `build_shell_command` | spawn `powershell` 无 `creation_flags` → release 上**每次定时任务执行**闪控制台窗 + 抢焦点 |
| `action_exec.rs` `kill_process_tree` | `taskkill`（abort 路径）同样裸 spawn |

---

## 二、issue #20：启动时宠物在屏幕左上角闪现后才移到上次位置

> 状态：**已修复（R5，commit 9e609d6）+ Windows 实机验证通过（2026-08-27，v0.2.1）**。
> 定级：视觉体验缺陷，无功能影响。

### 2.1 症状（2026-08-27 用户报告）

Windows release 构建启动 App：宠物先在**屏幕左上角**闪现一个大图标，随后跳到上次保存的位置正常显示。macOS 无此现象。

### 2.2 根因

1. `tauri.conf.json` pet 窗口 `"visible": true` 且未配置 x/y → Windows 上 tao 以 `CW_USEDEFAULT` 放置（≈左上角）并在创建时**立即显示**；
2. issue #9 已实证的 Windows 时序特性：WebView2 环境创建异步，主线程在 `build()` 内部泵消息期间**页面已加载执行**——setup 闭包尚未跑到位置恢复，前端已把宠物画在默认位置；
3. `build()` 返回后 `lib.rs` setup 才执行 `restore_pet_position` → 窗口移动 → 视觉上"闪现后跳位"。

macOS 的 WKWebView 不在创建等待期派发内容加载（内容首帧晚于 setup），故无此现象。

"大"的观感：大概率是高分屏 DPI 过渡期的一帧未修正渲染（或位置突兀带来的感知放大）；隐藏-恢复-显示方案（R5）无论哪种成因都一并消除。

---

## 三、修复任务清单（R1-R5，统一实施）

| # | 层级 | 改动 | 作用 | 对应 |
|---|---|---|---|---|
| R1 | Rust 根因 | `detect_node()` Windows 下加 `creation_flags(0x0800_0000)`（CREATE_NO_WINDOW） | 消灭控制台闪现 → 焦点不再被扰动 → #19 循环断根 | #19 |
| R2 | Rust 同类清扫 | `build_shell_command`（tokio Command 同名 API）+ `taskkill` 加同样 flag | 定时任务执行/abort 不再闪窗抢焦点 | #19 §1.4 |
| R3 | 前端加固 | Settings 的 focus 触发 doctor 刷新加冷却（~3s，纯函数 + vitest） | 防未来任何焦点抖动再次自激励 | #19 |
| R4 | Rust 钉子 | 仿 `order_nails` / `spawn_blocking` 结构钉子先例，`include_str!` 断言 `creation_flags` 存在 | 防回归（项目既有风格） | #19 |
| R5 | 时序 | `tauri.conf.json` pet 窗口改 `"visible": false`；`lib.rs` setup 中 `restore_pet_position` 之后**无条件** `win.show()` + plog 标记 | 启动先移位后显示，消除左上角闪现；无条件 show 防"无保存位置时永不显示"回归 | #20 |

R5 配套钉子（并入 R4 实施）：`order_nails` 新增断言 conf 里 pet `visible: false`、lib.rs 中 restore 先于 show。

实施注意：
- R1-R4 为一组（#19），R5 独立（#20），可分开提交/闭环；
- R2 的 `CREATE_NO_WINDOW` 只抑制控制台宿主窗口，不影响子进程启动 GUI 程序；
- R3 冷却只作用于 focus 触发路径，mount / `panel://tab` 触发不受限（保持"重开面板即刷新"语义）。

## 四、验证口径与结果

**测试基线**（实施后全绿）：`cargo test` + `npm test` + `npx tsc --noEmit`。

**Windows release 实机**（2026-08-27 用户复测，PulsePet v0.2.1——三项全部通过，闭环）：

| # | 场景 | 预期 | 结果 |
|---|---|---|---|
| 1 | 打开面板切到设置 tab | 日志只出 2 行 doctor 状态（进 tab 一次），无循环滚动 | ✅ 通过 |
| 2 | 定时任务（exec 型）到点执行 | 无控制台窗口闪现、无焦点被抢 | ✅ 通过 |
| 3 | 启动 App（有/无保存位置各一次） | 宠物直接出现在上次位置，无左上角闪现；无保存位置时仍正常显示 | ✅ 通过 |

---

## 五、用户人工目验 / 实机批次（待用户操作或反馈）

### 5.1 v2-m2 UI 实机目验 7 项（待用户反馈）

来源：task-pulsepet-v2-m2 R2 产物（2026-08-24 09:14 构建），经 v2-m3/m4/m5/m6 连续移交，无反馈。日常使用顺带目验即可，发现问题随下轮修复。

| # | 用例 | 内容 |
|---|---|---|
| 1 | TC-UI-01 | 主题三档（浅/深/跟随系统）切换 |
| 2 | TC-UI-03 | 面板壳两段布局 + 状态芯片实时更新 |
| 3 | TC-UI-06 | 双 agent 同 kind 切换时芯片 agent 跟随 |
| 4 | TC-UI-07 | 功能管理禁用 Todo 全链路（tab 消失 + 停派生 + 数据保留） |
| 5 | TC-UI-10 | 气泡排队实机（优先级抢占 / dwell 合并 / 并发上限） |
| 6 | TC-UI-11 | 气泡与右键菜单视觉 |
| 7 | TC-UI-12 | 四 tab 对照样例 a/b-cool 目验 + 深色可读性 |

### 5.2 v2-m5 实机验收缺口 4 项（用户人工配合）

来源：task-pulsepet-v2-m5 R2 tester（2026-08-27）。**安全前提（INC-20260827-1033 教训）**：操作 `~/.local/share/opencode` 与 `~/.claude` 前**务必完全退出 opencode**；agent 永不代执行。

| # | 用例 | 步骤 | 预期 |
|---|---|---|---|
| 1 | TC-M5-08 | 退出 opencode 与 CC 后临时改名 `~/.claude/projects` → 打开 Token 页 | 安静回退 opencode-only，无错误横幅无 degraded 字段 |
| 2 | TC-M5-09 | 退出 opencode 后临时改名 opencode.db（CC 有数据）→ Token 页 → 恢复 | CC-only 数据 + 「opencode 源不可用」细横幅（仅 panel）；恢复后消失；双缺走既有错误路径 |
| 3 | TC-M5-05 | 真实 Claude Code 干活一个会话至 Stop | `[cc] 本次会话消耗 token Xk · 今日 T` 汇报气泡（§十二 F1 改单总量口径，2026-08-28） |
| 4 | TC-M5-06 | 真实 CC 会话中触发编辑/命令工具 | `[cc] 正在编辑 X` / `[cc] 正在跑 X` 工具级气泡 |

### 5.3 v2-m6 实机目验 2 项（并入用户目验批次）

来源：task-pulsepet-v2-m6 R1 committer P3-③ 定级（2026-08-27，与 5.2 同批顺带）。

| # | 事项 | 说明 |
|---|---|---|
| 1 | TC-M6-05 完全实机组合 | 真实例程执行 × 手头会话（opencode/CC）并发同屏：手头优先 / 例程失败 ≤10s 让位 / 无并发时 error 30s 自然回收 / 手头静默期例程兜底显示。算法已被单测十条钉子 + TC-M6-02 端到端实证，此处为真实场景顺带确认 |
| 2 | OBS-PANEL panel 点击层 | panel Token 页与右键菜单「今日 token」子行 / idle 气泡追加段三层数值同窗一致性点验（数据层三层互锁已证，点击层顺带） |

### 5.4 v0.1.3 收尾用户目视验收（v1 线未了结项，经 v2-m1~m6 移交）

来源：V1-OPEN-ITEMS §8.5.4-3。TC-EV-27/DONE-04 姿态目视（thinking ≥4s、结束 ≤10s 回 idle）、DONE-05 面板数值比对、DONE-06 烟花+气泡叠加目视、TC-APP-14 下拉刷新 GUI；另有 §9.6-1 真实会话双场景验证（App 停运即时性）。0.2.x 线行为同源，日常使用顺带确认即可。

---

## 六、条件触发类（等硬件 / 等约定扩展）

### 6.1 多屏实机（需外接显示器）

来源：V1-OPEN-ITEMS 一（TC-APP-10 拔屏回退 / TC-APP-11 跨屏拖拽 / 多显示器烟花绽放点与跨屏 / 拖拽钳制真实鼠标行为 / A9 实机确认）。v2 侧无新增多屏改动面，维持"具备硬件时顺带核对"。

### 6.2 Windows 实机剩余批次（需 Windows 设备；#19/#20 已闭环不计入）

| # | 事项 | 来源 | 状态 |
|---|---|---|---|
| 1 | TC-SEC-05 token 文件位置（`%LOCALAPPDATA%\pulsepet\runtime\`） | v1 线 | 待验 |
| 2 | TC-TK-02 opencode.db schema canary 实机 | v1 线 | 待验 |
| 3 | TC-SP-10 webp 运行时解码（CI 编译侧已验，v0.1.2 实机粗验过） | v1 线 | 大体已验，顺带 |
| 4 | TC-INT-13 CC hooks Windows 形态（install.ps1 / cmd 包装） | v2-m1 | 待验 |
| 5 | TC-M4-18 定时任务 Windows 分支 | v2-m4 | **核心面已随 v0.2.1 §四场景 2 验证**（exec 到点执行无闪窗无抢焦点）；剩余面（超时 kill/taskkill 分支等）顺带核对 |

### 6.3 i18n 约定扩展时顺带（v2-m2 P3-10）

Rust 命令错误串未 i18n（与代码库既有模式一致）——待 i18n 约定扩展（v1 M8 类）时一并考虑。

---

## 七、打磨轮清单（代码级 P3，非阻断）

> **状态（2026-08-27 闭环）**：13 项**全部清偿**（task-pulsepet-v2-polish，2026-08-27）——12 项代码落地 + #13 落文档（V1-OPEN-ITEMS §8.6）。逐项落点：
> #1 删 derive（atlas.rs）；#2 composeActionNotice 单次计算（Settings.tsx）；#3 禁用语汇统一（ink-faint 字色 + 输入类 surface-2 底 + cursor wait=加载/not-allowed=锁定 二分，global.css）；#4 气泡改 `width:max-content + max-width:208 + max-height:70px` 三行截断（line-clamp/-webkit-box 与 absolute shrink-to-fit 不兼容，playwright 实测定案；文案钉字不动），CSS 钉子 bubble-clamp.test.ts + DOM 实测佐证；#5 删草稿注释；#6 测试专用助手 `init_at_exclusive` 持全局 slot 锁内「预写+轮转+换柄」，ends_with 强断言保留（global.css 外的 rust 侧 8 轮稳定绿）；#7 核对结论：原 622-635 区域已是 v0.2.1 改写后内容（无重复），但 dispatch_exec 函数体内 R5 注释块（"fire 决策即时持久化"）逐字重复两遍——删一份；#8 删重复行；#9 去 assert_ne（oracle 对账保留；TZ 注入因 chrono Local/SQLite localtime 平台缓存行为不稳而弃）；#10 改注释；#11 方案 α 落地（增量偏移解析 + 锁外解析 + in-flight 让路 + file_id 防重写拼接，七枚 alpha 钉子测试）；#12 ResizeObserver（实测重算，子行注入 h 132→147 y 86→71 自动上移）；#13 → V1-OPEN-ITEMS §8.6。测试基线：cargo test 327 passed + 3 ignored / npm test 418 / tsc 0 错 / build 通过。

| # | 来源 | 事项 | 位置与修法建议 | 状态 |
|---|---|---|---|---|
| 1 | v2-m2 P3-5 | AtlasData Clone derive 死代码 | atlas.rs——动 atlas.rs 时顺手删 | ✅ task-pulsepet-v2-polish 2026-08-27 |
| 2 | v2-m2 P3-6 | Settings notice 重复计算 | 微优化 | ✅ 同上 |
| 3 | v2-m2 P3-7 | 禁用语汇四套不一致 | CSS/微打磨轮统一 | ✅ 同上 |
| 4 | v2-m3 P3-1 | idle 汇报「 · 今日 X」追加段在 220px 气泡被单行省略截断不可见 | 气泡文案/CSS 打磨轮（两行或精简） | ✅ 同上（CSS 三行截断，文案钉字不动） |
| 5 | v2-m3 P3-5 | plugin-hook.test.ts:763 注释草稿痕迹 | 删 | ✅ 同上 |
| 6 | v2-m4 P3① | logging.rs `ends_with("x"×64)` 残余竞态（并行 plog! 旧句柄 .old 尾部污染偶发） | 测试专用助手持全局 slot 锁内轮转，或删 ends_with 只留 len>= | ✅ 同上（选前者，强断言保留） |
| 7 | v2-m4 P3② | action_exec.rs:622-635 注释块复制粘贴重复（**注**：v0.2.1 R2 已动该文件加 creation_flags，此项或已顺手消化——打磨轮核对后勾销） | 删 | ✅ 同上（核对：原区域已消化，删 dispatch_exec 体内 R5 重复注释块） |
| 8 | v2-m5 P3-1 | transcript.rs:208-210 注释块重复 | 删一行 | ✅ 同上 |
| 9 | v2-m5 P3-2 | transcript.rs:590-624 `assert_ne!(本地日, UTC日)` 硬假设非零时区偏移（TZ=UTC 环境会红） | 去 assert_ne 或 TZ 注入，保留 oracle 对账 | ✅ 同上（选去 assert_ne） |
| 10 | v2-m5 P3-3 | TokenStats.tsx:521 symmetricToggle 注释「模型/agent 共用」过时（R2 后仅模型用） | 改注释 | ✅ 同上 |
| 11 | v2-m5 P3-4 | token_stats.rs:709-712 TranscriptCache 全目录解析在 Mutex 持有期执行 | 观察项：文件体量增长时改锁内判定+锁外解析 | ✅ 同上（方案 α：增量偏移 + 锁外解析） |
| 12 | v2-m6 P3-① | PetMenu clamp effect deps 仅 `[pos]`、首帧估值 130 不含 agent 分布子行——双 agent 日菜单增高 ~14px 贴下缘时底项被裁 | deps 加 todayToken 或 ResizeObserver，或估值 130→146 | ✅ 同上（选 ResizeObserver） |
| 13 | OBS-SIGTERM | 外部 kill 不产生 `exit` 日志行、runtime token/endpoint 残留不清理（v1 既有） | 主去向=V1-OPEN-ITEMS §八维护版清单；退出钩子补 SIGTERM 路径 | ✅ 同上（只落文档：V1-OPEN-ITEMS §8.6） |

---

## 八、文档维护轮

| # | 来源 | 事项 | 说明 |
|---|---|---|---|
| 1 | v2-m6 P3-② | V2-DESIGN §6.2/§6.3/§6.4 与 TC-M6-04 步骤面仍写「悬停卡 / HoverToday.tsx」 | **✅ 已清偿（2026-08-27 21:20，文档维护轮）**：V2-DESIGN 7 处（§6.0 表行前向注记/§6.2 标题+注记+末段改写/§6.3 两行/§6.4 两处）+ V2-TEST-CASES TC-M6-04 标题注记+步骤预期 3 处 + TC-M6-06-4 措辞——对齐"右键菜单「今日 token」信息项子行"口径；i18n 键名 `token.hoverAgent` 按裁定保留不改；§6.7 评审记录历史留档未动。改动待入库 |

---

## 九、发布与清理（待用户决定 / 时间触发）

| # | 事项 | 状态与说明 |
|---|---|---|
| 1 | v0.1.3 Release publish | Draft（2026-08-22 起），publish 与否待用户指示（v2-m1 C 项移交） |
| 2 | v0.2.0 Release 处置 | Draft（tag a6ad68d）——**已被 v0.2.1 取代**（#19/#20 修复），publish 或丢弃待用户裁定 |
| 3 | v0.2.1 Release publish | Draft（tag f2cf13e，CI 双矩阵 success，**Windows 实机三场景已验 §四**）——publish 就绪，待用户指示 |
| 4 | after-crash 库三件套清理 | `opencode.db.after-crash.db` 等留档至 **2026-09-03**，到期确认无用后删除（INC-20260827-1033，报告存 `.opencode/incidents/`） |
| 5 | pp-m5-dom/ 测试截图 63 张 | 系统临时目录 `/var/folders/.../opencode/pp-m5-dom/`，供人工复核 M5 DOM 测试后可清 |

---

## 十、记录备查类（无行动 / 观察项）

| # | 来源 | 事项 | 定级 |
|---|---|---|---|
| 1 | v2-m3 P3-2 | 合成事件测试工具限制（悬停/菜单依赖小步移动合成） | 非产品缺陷，记录 |
| 2 | v2-m4 P3-③ | 定时任务理论双记账边界（reload µs 窗 + 补跑窗尾 + 队列满三巧合叠加） | 概率趋零，不修 |
| 3 | v2-m6 P3-④ | 活跃集 (priority, last_event_at) 完全相等时胜者依 HashMap 迭代序 | Instant 纳秒分辨率下不可达，备查 |
| 4 | v2-m6 OBS-DEDUP | interval 规则受「同规则 3 分钟不重复」影响，短周期规则实际节律 ≈4min | 既定行为（TC-RM-05）；提醒类实测须按 fired 时间戳对窗 |
| 5 | v2-m6 OBS-HYST | 双 session 事件交错时显示状态周期性交替 | 设计已知（V2-DESIGN §6.5 R1）；实测烦扰再加 2s 滞回（预设计不实现）——**用户日常使用反馈触发** |
| 6 | v2-m2 P3-8/9 | 插件开关失败静默 + panel://tab 冷启动 ~100ms 竞态 | UX 观察项，记录不修 |
| 7 | v2-m1 E | TC-INT-04 事件乱序覆盖（设计记录）/ TC-INT-06 慢 POST 事件丢弃（风险接受）/ CC hooks 配置读取时机未实证（保守假设会话启动缓存） | 观察项 |
| 8 | v2-m1 D | V1-OPEN-ITEMS §六 观察项归档 | 同源 v1 线，默认不动 |

---

## 十一、宠物大小三档 + 视觉归一化（2026-08-28 设计定稿，**已实施**）

> 来源：用户需求"允许用户设置宠物大小（大/中/小三档）"+ 实测发现 petdex 导入素材与内置宠物视觉大小悬殊（idle 高度比 1.8×，根因是素材"填帧率"差异而非渲染缺陷）。
> 状态：**✅ 已实施（2026-08-28 同日完成）**——完整设计与实施偏差记录见 `docs/v2/pet-size.md`（防裁剪上限从"全表 content 包围盒"修正为"帧尺寸"、idle 度量从"行条带"修正为"逐帧原点并集"，锚定比率与残差结论不变；附带清偿 en 菜单裁剪 §11.5 与 atlas 短缓冲越界隐患两处存量缺陷）。测试基线：`cargo test` 346 passed+3 ignored / `npm test` 433 / `tsc` 0 错 / build 通过；dev 冒烟（large 档窗口实测 280×280、时序日志正确）+ tester 复核 PASS（db 档位 4 场景 + 静态核验）+ committer 审查 **APPROVED**（P2-1/P3-1/2/3/5/6 六项当日修复；复核再 APPROVED + 复核新提 A/B 两条 P3 亦落地——兜底测试改跑真实短缓冲形态、pet-size.md 占位路径措辞对齐，2026-08-28；P3-4/7~11 记录备查）。用户目验项 = pet-size.md §6 TC-SZ-01~09（日常使用顺带）。

### 11.1 起因：素材"填帧率"差异实测（2026-08-28）

四素材 sheet 均为标准 1536×1872（单帧 192×208）、同一缩放路径渲染，差异全在画师对帧面积的占用（PIL alpha 包围盒实测；192×208 是"舞台"，用多少是画师的事——codex/petdex 生态普遍满帧，内置素材刻意留白）：

| 素材 | idle 帧内容占比 | 220 画布 idle 视觉高（现状） |
|---|---|---|
| blinking-kitty（内置） | 宽 46% × 高 52% | ~114 px |
| wagging-doggy（内置） | 宽 50% × 高 54% | ~118 px |
| kun-like（petdex） | 宽 62% × 高 95% | ~210 px |
| line-puppy（petdex） | 宽 81% × 高 95% | ~210 px |

调研佐证：v1 调研报告（`docs/v1/desktop-pet-research.md`）覆盖的 7 个开源同类产品均无"用户可调宠物大小"设置，本特性为差异化功能，无生态行为冲突。

### 11.2 决策记录（用户拍板 2026-08-28）

| 项 | 决定 |
|---|---|
| 档位 | **184 / 220 / 280 逻辑像素**（小/中/大）；默认 medium=220（老用户无感）；持久化 `app_state` 新键 `pet.size`（"small"/"medium"/"large"，缺省 medium） |
| 归一化 | **常开无开关**。锚定**内置猫现状**：目标 idle 高 = `canvas × 108/208`（≈52%），全帧最大内容包围盒做防裁剪上限（安全网，实测四素材均不触发）。决策演进：初始方案 A（idle 目标 0.73×canvas）会把内置猫放大 1.2× 且留 1.2× 残差，用户裁定改为"内置现状就是中档、petdex 靠过来"——内置零变化、残差归零 |
| 入口 | 仅 panel 设置页「宠物」区三档分段控件（复用 `theme-seg` 样式结构）；宠物右键菜单**不加**项（避免与 §七-12 已修的菜单贴边风险再叠加）。切换即时生效（Rust `set_size` + `pet://size` 广播），无需重启，与主题/穿透体验一致 |
| 插值 | atlas 模式 `ctx.imageSmoothingEnabled = false`（nearest 像素锐化；归一化后内置猫大档放大 ~1.35×，平滑插值会糊）；占位 PNG 路径零改动 |
| 行为变化 | **内置宠物视觉不变**；仅 petdex/codex 导入素材缩小到与内置一致（中档 idle 210→114）。发布说明需注明 |

归一化公式（**实施修订版**，详见 pet-size.md §3.4 两处修正：防裁剪上限弃用全表 content 包围盒——奔跑行动画使其 ≈ 整张 sheet 无区分度；改用帧尺寸本身，数学上等价"每帧不裁"且不依赖度量）：

```
s = min(canvas × (108/208) / idle.h, canvas / frameW, canvas / frameH)
```

- `idle` = idle 行**逐帧原点并集**（Rust `frame_union_at_origin(row 0)`，帧内局部坐标）；
- 绘制 = 帧居中（帧内相对位置保持 → 帧间无抖动、奔跑帧帧内位移不破坏）；
- `idle` 缺失（全透明 sheet / 占位 PNG 路径）→ 回退现行 `computeFrameRect`（min 适配，行为同今天）。

数值验算（idle 视觉高度 px；三档等比，无任何素材触上限 → 零裁剪风险）：

| 素材 | s（中档） | 小 184 | 中 220 | 大 280 |
|---|---|---|---|---|
| blinking-kitty | 1.0577（= 现状缩放比，视觉零变化） | 95.5 | **114.2（与今天一致）** | 145.4 |
| wagging-doggy | 1.0203 | 95.5 | 114.2（较 today −3.6%，无感） | 145.4 |
| kun-like / line-puppy | 0.5769 | 95.5 | 114.2（自 210 靠拢） | 145.4 |
| **idle 残差** | — | **0** | **0** | **0** |

### 11.3 改动面摘要（Rust ~300 行 / 前端 ~350 行 / 文档 ~150 行）

Rust：

| # | 文件 | 改动 |
|---|---|---|
| 1 | `pet_size.rs`（新，照 `theme.rs` 同构） | `KEY_SIZE="pet.size"` / `SIZE_EVENT="pet://size"` / `SIZES={184,220,280}`；parse-read-write + `pet_get_size`/`pet_set_size` 命令（写库 → 应用窗口 → 广播 `{size, logical}`）+ mock runtime 测试（**窗口应用分支容忍无 pet 窗**） |
| 2 | `windows.rs` | `apply_pet_size(app, logical)`：`set_size(LogicalSize)` + **内容中心锚定**（位置补偿 ±Δ/2 × dpr 物理像素，切档不"右下生长"）+ 按所在显示器复用 `clamp_position` 防越屏 |
| 3 | `lib.rs` setup | 窗口创建循环（:397）之后、`restore_pet_position`（:412）**之前**应用档位——时序铁律 **set_size → restore → show**（restore 读 outer_size 做 clamp，#9/#20 语义不变）；`invoke_handler` 注册两命令 |
| 4 | `atlas.rs` | 加载 RGBA 时计算 idle 行（row 0）**逐帧原点并集**（alpha>0，防御式访问）；`AtlasMetaDto` 增 `idle` 嵌套字段 `{x,y,w,h}`（全透明 null）+ 纯函数单测；resolve 兜底短缓冲保持不补全（committer P2-1：补全会劣化降级路径，见 pet-size.md §5） |

前端：

| # | 文件 | 改动 |
|---|---|---|
| 5 | `lib/pet-scale.ts`（新） | 归一化纯函数（帧上限公式，§11.2 修订版）+ 四素材实测 bbox 钉子单测（idle 收敛一致、帧上限生效、缺省回退路径） |
| 6 | `lib/size-bridge.ts`（新，照 `interaction.ts` 同构） | fetch/set invoke 封装 + payload 解析 + `initSizeBridge`（查询 + 订阅 → store；pet/panel 双路由初始化）；`PET_SIZES` 常量与 Rust `SIZES` 注释互钉双端一致 |
| 7 | `petStore.ts` | `size: PetSize`（默认 medium）+ `setSize` |
| 8 | `PetCanvas.tsx` | `CSS_SIZE` 常量（:9）→ 档位驱动（渲染 effect deps `[size]`，重建即重设 canvas/监听器——实施改此方案，替代原"sizeRef + 主动 resize"设计，rAF 依赖读取模式不变）；`drawAtlas` 改归一化缩放 + 每帧设 `imageSmoothingEnabled=false`（仅 atlas 路径，占位路径显式保持平滑） |
| 9 | `global.css` | `.pet-root`/`.pet-canvas`（:121-129）220px → `--pet-size` CSS 变量（Pet.tsx 从 store 注入）；`.pet-bubble`（:138）`max-width: 208px` → `calc(100% − 12px)` |
| 10 | `PetMenu.tsx` | clamp 的 windowSize（:37-47）写死 220 → `PET_SIZES[size]` |
| 11 | `Settings.tsx` | 「宠物」区下拉后加三档分段控件（`theme-seg` 结构复刻）；onSize 乐观更新 + 失败回滚（照 `onLanguage` 模式） |
| 12 | `i18n.ts` | 新键 `settings.size` / `settings.sizeSmall` / `settings.sizeMedium` / `settings.sizeLarge`（zh/en 成对，字典完备性测试自动兜底）；Rust 侧无新文案 |

联动确认**无需改动**：位置记忆（存左上角 + clamp 兜底）、fireworks（动态读 pet bounds）、MiniCat、拖拽阈值（4px 常量）、跨 dpr（LogicalSize + TC-SP-03 链路）、TC-01「不可 resize」语义（`resizable:false` 不变，档位是显式设置非自由缩放）、热键/托盘。

### 11.4 小档（184）适配核验（2026-08-28，SF 系统字体 @12px 实测）

| 项 | 结论 |
|---|---|
| panel 设置页 | 独立 900×640 窗口，与宠物档位无关，永远完整 |
| 气泡 | 改 `calc(100% − 12px)` 后小档 max 172px：zh 提醒样例 170px **完整**；token 汇报 224px 在中档 208 上限下本就省略，小档多省 2~4 字符——优雅降级，气泡框/尖角/snooze 按钮不受影响 |
| 右键菜单（zh） | 实测外宽 176px（min-width 168 + padding/border 12），184 − 176 − 2×2 = **4px 余量，完整显示**（184 取值依据即在此） |
| 右键菜单高度 | 双 agent 子行最高 ~146px，184 余 34px ✓（§七-12 ResizeObserver 已修，风险不叠加） |

### 11.5 附带存量缺陷：en 右键菜单今日已裁剪（随本特性一并修复）

实测（SF@12px 逐项量宽）：`menu.togglePass` en 文案 "Toggle interaction mode (pass-through: on)" 菜单项 258px、外宽 **266px** > 中档 220 窗口——**en 语言下右键菜单今天已被右裁 ~46px**（M8 i18n 漏检），184 小档将裁 82px。修复两件（并入实施清单）：

1. **en 文案缩短**（主修复）：`"Pass-through: {state}"`（外宽 ~120px，任何档位完整）；zh 文案不动（实测 176px 安全）；
2. **防御 CSS**（保险丝）：`.pet-menu` 加 `max-width: calc(100% − 4px)`、菜单项加 `overflow: hidden + text-overflow: ellipsis`——未来任何语言/文案/档位组合最坏只省略文案，不再裁布局。

### 11.6 实施顺序与验收要点

顺序（每步独立可验证）：① Rust `pet_size.rs` + lib.rs 接线（`cargo test`）→ ② 前端档位化（bridge/store/CSS/菜单/气泡，`npm test`）→ ③ Settings 分段控件 + i18n（`npm run build`）→ ④ atlas 度量 + DTO（`cargo test`）→ ⑤ 归一化 + nearest（`npm test`）→ ⑥ 文档（`docs/v2/pet-size.md` + AGENTS.md）+ `npm run tauri dev` 全链路手验。

验收要点：档位切换即时生效 + 重启恢复 + 默认 medium；四素材同档 idle 高度一致（残差 0）；奔跑/挥手帧无裁剪；184 档 zh/en 菜单与气泡完整（en 修复后）；非法 `pet.size` 值拒绝且不破坏已存值；贴屏边缘切档 clamp 不越界；set_size → restore → show 时序钉子（order_nails 风格）；发布说明注明"导入素材视觉缩小到与内置一致"。

工作量：~800 行，1~1.5 天。

---

## 十二、v2 收尾用户反馈批次（2026-08-28，F1~F16；**全部已实施**）

> 来源：用户日常使用反馈（2026-08-28，15 项——会话气泡汇总 1 + Token 页 3 + 面板布局 1 + 设置页 4：控件形态 / 接入卡缩高 / 命名统一 / 宠物下拉字样 + 例程页 5：notify 徽标 / todo 类别列 / todo 烟花勾选项 / 日期时间控件规格 / 历史统计区移除 + Windows 平台 1：托盘/任务栏图标猫太小），根因均已源码定位，方案已与用户对齐（含多项裁定，见各行）。F16 为同日实施后目验的二轮微调（5 点，见行内）。
> **状态（2026-08-28 实施）**：用户批准后同日全部实施（F4 先行、F1~F3/F5~F15 随后），逐项落点见 §12.4；基线 `cargo test` 346 passed+3 ignored / `npm test` 439 / `npx tsc --noEmit` 0 错 / `npm run build` 通过。用户目验项见 §12.3 第三条（日常使用顺带）；F15 任务栏 exe 图标需 Windows release 实机。

### 12.1 清单

| # | 事项 | 根因（源码级） | 修复方案（已裁定） | 改动面 |
|---|---|---|---|---|
| F1 ✅ | 会话结束气泡显示 input/output 明细，只要一个汇总总量 | Rust `i18n.rs:110` `token_report`（zh「本期用了 X input / Y output / $cost」，opencode 路径）+ `:129` `cc_token_report`（CC 路径无 cost 段）；目标口径 = 面板 KPI `sumRows`（`token-stats.ts:284`）：**total = in + out + cache_read，reasoning 不计** | 两模板改单总量参数（zh「本次会话消耗 token {total}」措辞基准，en 对应改写）；**cost 段一并去掉**（2026-08-28 裁定）；「· 今日 T」追加段保留（口径相同，`token_report_today` 不动） | `i18n.rs` 两函数 + `token_stats.rs:603` `format_session_report` / `:921` CC 调用处 + 测试断言 ~15 处（`token_stats.rs:1378/1435/1692/1888`、`i18n.rs:409-461`、`lib.rs:583-715`）；文档联动：V2-DESIGN §3.2/§5.4、V2-TEST-CASES TC-M3-09-1 / TC-M5-05、本文件 §5.2-3 预期文案（TC-TK-10 属 v1 线留档） |
| F2 ✅ | 柱图三问：今日单柱过宽 / 日期标签不与柱中心对齐 / 近 7 天零值日缺柱 | ① `token-chart.ts:94` barW = slot×0.6，n=1 时 ≈362px；② `TokenStats.tsx:583-598` 仅渲染首尾标签且首标签左对齐 x=PAD（单柱时柱居中、标签在左缘）；③ `computeStackedBars` 无查询窗口概念、只聚合有数据的日 → 零值日无柱 | ① barW 加上限 cap（~56px，终值实施目测定）；② n≤7 改 per-bar 居中标签（textAnchor=middle、x=柱中心），n>7 维持首尾两枚；③ `StackedBarOptions` 增查询窗口（`resolveQueryRange` 的 fromMs/toMs 已有），**仅 day 维度 ≤7 天窗口逐日补零柱**（今日=1 柱、7d 恒 7 柱；周维度与 >7 天跨度不补——2026-08-28 裁定） | `token-chart.ts` + `TokenStats.tsx:227/:583` + `token-chart.test.ts` 新钉子（补零 / 柱宽上限 / 标签中心 x）；`bars.length===0` 空态分支对 day+≤7d 不再可达（仅 week / 30d / custom） |
| F3 ✅ | 「费用仅统计 opencode（Claude Code 无可靠费用数据）」标注语去掉 | `TokenStats.tsx:344-346` 消费点 + i18n 键 `token.costOpencodeOnly`（`i18n.ts:78` zh / `:434` en）+ `global.css:761` `.token-kpi-note` | 四处连删；`i18n.test.ts:134-160` 存在性断言改**清退断言**（仿 `token.kpi.totalSub` 先例） | 4 文件 |
| F4 | 「Token 时序」标题 12px 比正文 13px 还小；各 tab 区块标题字号不一（设置页 h2 13px、其余 tab h3 12px） | `global.css:810-816` `.token-section h3 { font-size:12px }`（Token/例程/待办页所有 section 标题）+ `:483-489` `.panel-settings h2 { font-size:13px }`（设置页） | 四 tab 区块标题统一 **14px**（2026-08-28 裁定并扩围至设置页 h2；层级已核验：h1 17 > 区块标题 14 > 正文 13） | ✅ **已实施（2026-08-28）**：CSS 两处（h3 12→14px、设置页 h2 13→14px）；基线 npm test 433 / tsc 0 错 |
| F5 ✅ | 面板全屏放大后例程页内容钉在 860px 偏左、不随窗口横向扩展 | `global.css:1103-1105` `.reminders { max-width:860px }`（唯一被钉宽的 tab，其余 tab 均全宽自适应） | 删该规则，与 Token/设置页一致全宽 | CSS 一处 |
| F6 ✅ | 设置页控件形态统一：大小/主题三档改下拉、交互/工具播报改卡片行开关 | 大小（`Settings.tsx:416-438`）与主题（`:486-508`）用 `theme-seg` 分段控件，与语言/宠物选择的下拉形态不一致；交互（`:440-455`）与工具播报（`:457-469`）用 `settings-check` 裸复选框，与功能管理 todo 插件卡片行形态不一致，且分属两个 h2 区 | ① 大小/主题 → 照语言形态：`settings-pet-label` label + 原生 `select`（复用 `.panel-settings select` 既有样式）；option 文案复用现有键（sizeSmall/Medium/Large、themeAuto/Light/Dark）；busy 禁用 / 失败横幅 / 乐观回滚语义全保留；大小下拉留在「宠物」区内，主题 hint 小字保留。② 交互/工具播报 → 照 todo 插件开关卡片行（`intg-list` + `intg-row`，右侧 `reminder-check compact` 复选框带「已启用/已停用」）；**两行合并为一个 h2 区**（2026-08-28 裁定，区名实施时定，如「交互与播报」）；穿透热键提示小字留在卡片行下方 | `Settings.tsx` + `global.css`（`.theme-seg` 成死代码一并清退：`:430` dark 变体 + `:450-479`）+ i18n 新区名键（zh/en 成对）；状态文案复用 `todo.plugin.enabled/disabled` 还是新增 `settings.state*` 实施时定；**无 Rust 改动** |
| F7 ✅ | 设置页-接入管理卡片偏高，稍微缩小 | `.intg-row` padding 12px×2（`global.css:592`）+ 每卡固定 4 行（head 行按钮 28px 撑底 + path + message + note）≈ 114px/卡；`.intg-note`「修改前自动备份」（`:668`，i18n `integrations.backupNote`）两卡重复同样文案 | ① padding 12→8px、`.intg-path` margin 6→4、notice/error 行距微收；② **备份提示去重**（2026-08-28 裁定）：删每卡 `.intg-note` 行，提升为接入管理区底部一处提示——每卡共省 ~33px | `Settings.tsx`（删 `:584` 每卡 note + 区底加一处）+ `global.css` 微调；i18n 键复用不新增；**无 Rust 改动**；联动：`.intg-row` 共用类——功能管理插件行与 F6 卡片行同向变紧凑（方向一致，无冲突） |
| F8 ✅ | 接入管理两卡命名不一（「opencode 插件」vs「Claude Code hooks」） | i18n `integrations.opencodeDesc`（`i18n.ts:354` zh「opencode 插件」/ `:707` en "opencode plugin"）与 `integrations.claudeDesc`（`:355` / `:708`「Claude Code hooks」）术语混用；且「插件」一词已被功能管理区（PulsePet 内置插件）占用，跨区撞名 | **按宿主名**（2026-08-28 裁定）：两卡名只写「opencode」/「Claude Code」，zh/en 同值（产品名不翻译，符合既有 i18n 约定）；Rust doctor 文案（`intg_*` 模板）核对无「插件/hooks」术语，不受影响；README/设计文档术语不动（仅 UI 文案） | `i18n.ts` 两键 zh/en 共 4 处值改写；无组件、无 Rust 改动 |
| F9 ✅ | 宠物下拉框去掉「内置小猫」「内置小狗」字样 | 字样烧在内置素材元数据：`src-tauri/assets/blinking-kitty/pet.json` `displayName: "blinking-kitty（内置小猫）"`、`wagging-doggy/pet.json` 同款；下拉 option = `displayName + （来源）`（`Settings.tsx:381`）→ 现显示「blinking-kitty（内置小猫）（内置）」双重标注 | 两份 pet.json 的 `displayName` 去掉「（内置小猫）/（内置小狗）」后缀 → 下拉显示「blinking-kitty（内置）」「wagging-doggy（内置）」，来源标注（内置）保留（分组信息不丢）；`description` 字段不动（不在下拉展示）；codex/petdex 素材 displayName 来自各自 pet.json，不受影响 | 仅两份 assets 数据文件（`include_bytes!` 编译期内嵌，改后需重编译生效）；测试核验：cargo 侧 displayName 断言均为 `contains(id)`（`atlas.rs:1243/1255/1418/1421`）不受影响、无需改测试；前端无相关断言 |
| F10 ✅ | notify 型例程动作徽标 💧 → 🔔 | `reminders.ts:374` `actionBadge`（notify → 💧 / exec → ⚡ / todo → 📋）驱动例程列表行首列与执行历史筛选下拉（`Tasks.tsx:853`）；`Tasks.tsx:903` 历史行另有同款硬编码——notify 型（新建例程默认）全显水滴，与「提醒」语义不贴 | notify 分支 💧 → **🔔**（2026-08-28 裁定，与 ⚡/📋 区分度最佳）；`Tasks.tsx:903` 硬编码统一改走 `actionBadge`（消重复）；**类别徽标 `kindEmoji` 的 hydration=💧 保留**（「💧 喝水」是类别语义，与动作徽标独立）；文案里的 💧（「该喝水啦 💧」模板/placeholder）不动 | `reminders.ts` 一处 + `Tasks.tsx:903` + `reminders.test.ts:476` 钉子断言改 🔔 + 注释口径三处（`reminders.ts:371`/`Tasks.tsx:41`/`global.css:1393`）+ 文档两处（V2-DESIGN §4.7、V2-TEST-CASES 的「💧 notify」字样）同步；无 Rust 改动 |
| F11 ✅ | todo 派生行在例程页也显示类别「待办」 | `Tasks.tsx:467-469` 条件排除：`{r.kind !== "todo" && (<span className="reminder-kind">…)}`——todo 派生行无类别列（其余行显示 💧 喝水 / ☕ 休息 / ⭐ 自定义） | 删除该条件，todo 行统一渲染类别列「📋 待办」，与其他行格式一致；`kindLabel`/`kindEmoji`/i18n 键 `reminders.kind.todo`（zh「待办」/ en "Todo"）**全部现成零新增**；目验点：todo 行首列动作徽标已是 📋，类别列再 📋 相邻略重复，如嫌冗余可类别列只显文字「待办」（实施时目验定） | `Tasks.tsx` 一处条件；核对无组件测试钉住该行为；文档口径（V2-DESIGN §4.7 列表描述）顺带补注「todo 行含类别列」；无 Rust 改动 |
| F12 ✅ | todo 派生行例程列表的「烟花」勾选项去掉 | `Tasks.tsx:508-517`：`{r.kind === "todo" && (<label …「烟花」…>)}`——仅 todo 派生行渲染（普通例程行本就无），是 TC-RM-11「单条烟花覆盖」在 todo 行的快捷入口；且该入口属半截入口——Todo 页无烟花字段、todo 编辑表单全锁定（仅提示+按钮），todoHint 自述「改动会随任务下次保存被覆盖」 | 删除该渲染块，todo 行与普通行一致只留「启用」开关；**数据语义不变**（`use_fireworks` 字段与 `usesFireworks` OR 判定照旧，全局烟花总开关仍覆盖 todo 行）；i18n 死键清退（`reminders.fireworks` / `reminders.fireworksOverride` 仅此一处消费，zh/en 4 处，核对 i18n.test 键清单断言）；**附带发现存量缺陷**：todoHint 文案「此处仅可调整文案、启用与烟花」与现状不符（todo 编辑态实际无任何可调字段）——顺带修正或删提示，实施时定 | `Tasks.tsx` 一处 + `i18n.ts` 两键清退 + 文档联动（TC-RM-11 / V2-DESIGN §4.7 列表描述同步）；无 Rust 改动 |
| F13 ✅ | 「一次」调度分支的日期时间控件大小怪异 | `global.css:1250-1254` 统一控件基线选择器（32px 高 / 2px token 边框 / 统一 padding 与字号）列了 text/number/time/date/select，**漏 `input[type="datetime-local"]`**（全仓唯一消费点 `Tasks.tsx:734` once 分支）→ 走浏览器默认样式（macOS WKWebView 上明显超 32px、无 token 边框、默认 padding/字号），与旁边基线控件并排大小突兀，连带整列观感拥挤 | 选择器列表补 `input[type="datetime-local"]` 一项——高度/padding/边框/字号/底色全走 32px 控件基线；补齐后 label 上、控件下的堆叠形态与表单其他字段完全一致，**无需横排改造**（用户初判为 label 与控件挤同列，根因核验后定位在控件规格缺失） | `global.css` 一处选择器；无组件、无 i18n、无 Rust 改动；无测试钉住 |
| F14 ✅ | 例程页底部「历史统计」区移除（无意义信息） | `Tasks.tsx:930-947` 统计区 ← `reminders.ts:596` `fetchReminderStats` ← Rust `reminders_stats` 命令，按 kind 显示「今日 N 次 / 累计 N 次」。评估定论（2026-08-28 用户认同）：**无行动价值**（知道被提醒几次不指导任何决策，行级「上次 X」+ 调度摘要已够）；与行级信息冗余；v1 M4 提醒记账遗留（TC-RM-13），与 v2 例程页身份错位（有诊断价值的执行历史已覆盖 exec，统计区反而只含 notify 三类）；i18n 标题还暴露内部表名「历史统计（reminder_logs）」 | **整区移除 + 链路清退**：删统计区与 stats state/调用；`fetchReminderStats`/`ReminderStat` 类型删；Rust `reminders_stats` 命令 + `lib.rs` 注册 + 查询与测试删；i18n `reminders.stats.*` 四键清退（zh/en 8 处，核对 i18n.test 键清单断言）；**记账写日志保留**（`reminder_logs` 写入不动——排障/未来功能燃料，只删查询与展示） | `Tasks.tsx` + `reminders.ts` + Rust（命令/注册/测试）+ `i18n.ts` + 文档联动（TC-RM-13 口径作废同步）；提醒触发日志照常落库，验收含此项 |
| F15 ✅ | Windows 任务栏与托盘的猫图标太小 | 托盘 = `tray.rs:101` 硬编码 `icons/32x32.png`（Windows 100% DPI 下缩到 16px 显示，125%/150% 也仅 20/24px）；任务栏 = exe 图标 `icon.ico`（pet 窗口 `skipTaskbar:true`，任务栏按钮是 panel 窗口/exe 图标，典型显示 20-24px）；**macOS 无感原因**：retina 菜单栏按 32 物理像素 1:1 显示同一资产——Windows 视觉尺寸直接减半，故为 Windows 特有观感。美术层面（视觉子代理分析 + alpha 实测）：① 大尺寸版留白多——512 版猫横向仅占 60-70%（bbox 70%×82%），各尺寸裁切不一；② 细线条像素画小尺寸存在感弱。系统显示尺寸（16-24px）不可改，唯一杠杆 = 同样像素里猫占得更满更清晰 | **重制图标资产（代码零改动）**：源图按猫轮廓紧裁切放大至 ~95% 满幅 → `tauri icon` 一键重生成全套（32/64/128/128@2x/512/ico/icns），ico 内 16/24/32 档随之收紧；若 16px 下细节仍糊再补手绘像素版 16/24 档（二期可选）；macOS 菜单栏/dock 同向变大一点（正向副作用，目验不溢出）。**桌面宠物本体零影响**——atlas 素材（`assets/blinking-kitty|wagging-doggy/`）与 `icons/` 相互独立，渲染链路（PetCanvas + pet.size 档位）不交叉 | 仅 `src-tauri/icons/` 资产文件；无代码/i18n/Rust 改动；验收：dev 重编译即验托盘图，**任务栏 exe 图标需 Windows release 实机**（随打包生效，走 CI——同 #19/#20 验证路径）；预期为「变满变清晰」而非物理变大（系统尺寸限制） |
| F16 ✅ | 设置页二轮微调（F6/F7 实施后目验反馈，5 点）：①「交互与播报」→「交互管理」；② 交互管理两卡长文案不全加粗（冒号前名称加粗、后段常规体）；③ 外观区删「界面主题」label，themeHint 上移至 label 位；④ 宠物区「当前渲染：…」信息行删；⑤ 大小 label「大小」→「宠物大小」。**二轮续（2 点）**：⑥ 交互卡粗体名独占一行、描述另起一行（原同行横排改两行）；⑦ 设置页非加粗小字字号统一（原 label 13 / hint 12 / desc 13 混排） | 均为 F6/F7 新形态的文案与字重打磨：①③⑤ i18n 值/键位；② 原 `intg-name` 整段 700 字重承载长句；④ `settings.current`/`fellBack` 唯一消费点；⑥⑦ `intg-desc` 同行横排 + 三档字号并存 | ① `sectionInteraction` 改值（en 同步 Interaction & Broadcast → Interaction，对齐「接入管理=Integrations」命名式）；② i18n 拆 `passThrough`/`toolBroadcast` 为粗体名 + `*Desc` 常规体两键；③ `themeLabel` 键清退、hint `<p>` 移至 select 上方；④ 「当前渲染」块删 + `settings.current`/`fellBack` 清退（回退可见性由 notice 横幅 + 下拉占位项承担）；⑤ `settings.size` 改值（zh 宠物大小 / en Pet size）；⑥ 描述移出 `intg-row-head` 为块级 `<p class="intg-desc">`；⑦ 小字统一 **12px**（`settings-pet-label` 13→12、`intg-desc` 13→12；`settings-current`/`hotkey-hint`/`intg-path`/`message`/`state-label` 原本 12px 不动；警示横幅 `settings-notice`/`error` 13px 属警示语义保留；`reminder-check` 13px 为例程页共用控件伴随文字不动）+ 死类 `.settings-check` 清退；**三轮**：备份提示文案「修改前自动备份」→「修改前自动备份至同目录」（en 同步）+ 位置从区底移至「接入管理」标题下（照功能管理 hint 位形态） | `i18n.ts` zh/en + `Settings.tsx` + `global.css`（新增 .intg-desc、字号统一、死类清退）+ `i18n.test.ts`（F6 测试扩为二轮版：清退 current/fellBack/themeLabel + 拆分键齐备 + 区名/大小钉值）；无 Rust 改动；基线 npm 439 / tsc 0 错 |

### 12.2 已知边缘点（随需求自然产生，验收按此预期）

| # | 点 | 说明 |
|---|---|---|
| 1 | 两种时间轴语义并存 | ≤7 天补零后为「日历等宽」；>7 天仍按有数据的日等分（缺日坍缩相邻，现状行为）。30 天补零其实也可读（柱宽 ≈12px），如嫌割裂可后续扩到 ≤30 天补、custom 不补 |
| 2 | 空态语义变化 | 7d 全零显示 7 根零高柱而非「暂无数据」文案（今日同理 1 根）；模型全不勾的 noModels 空态不受影响（`effectiveSelected.size===0` 分支先行） |
| 3 | 气泡两段数字可能高度重复 | 当天仅一个会话时「本次 …X · 今日 X」两段几乎相同（既有追加段设计如此，改汇总后更明显）；reasoning 不计入与 KPI 一致，属有意口径 |
| 4 | CC 行 cost「—」失去解释文案 | F3 去标注后会话列表/详情 CC 行 cost「—」无来源说明，影响极小（接受） |

### 12.3 实施与验收

- 顺序：F4 / F5 / F3 / F6~F13、F15（CSS + 前端/数据/图标资产微改）→ F14（前端 + Rust 命令链路清退）→ F2（纯函数 + 组件）→ F1（Rust + 文档联动面最大，含 V2-DESIGN / V2-TEST-CASES / 本文件 §5.2-3 口径同步）。**F4 已于 2026-08-28 率先实施**（扩围含设置页 h2）。
- 基线：`cargo test` + `npm test` + `npx tsc --noEmit` 全绿；F1 另跑 dev 冒烟看真实气泡文案；F2 实测今日单柱宽度与标签居中；F6 目验四控件与语言/插件行视觉一致且切换/失败/回滚行为不变；F9 dev 冒烟看下拉两行字样；F10/F11 目验例程列表与历史行徽标/类别列；F12 目验 todo 行仅剩启用开关、全局烟花开时 todo 到期仍有烟花（OR 语义钉子 `reminders.test.ts:171-174` 不动）。
- 用户目验：今日单柱收窄 + 日期居中、7d 恒 7 柱（含零柱）、气泡只显总量、全屏例程页横向扩展、设置页控件形态统一、接入卡紧凑且备份提示仅区底一处、接入卡命名按宿主名、宠物下拉无「内置小猫/小狗」字样、notify 例程行/历史行徽标为 🔔、todo 派生行显「待办」类别、todo 派生行无烟花勾选项、「一次」分支日期时间控件与其他控件同高同边框、例程页无历史统计区且提醒日志照常落库、桌面宠物大小不变前提下 Windows 托盘/任务栏猫视觉占比显著提升（release 实机）。

### 12.4 实施记录（2026-08-28）

> 用户批准后同日实施完毕（顺序微改 → F2 → F1 → 图标 → 文档同步）。基线：`cargo test` 346 passed + 3 ignored / `npm test` 439（+6 新钉子与清退测试）/ `npx tsc --noEmit` 0 错 / `npm run build` 通过。

| # | 实施落点 |
|---|---|
| F1 | `i18n.rs` `token_report`/`cc_token_report` 收敛为单总量模板（zh「本次会话消耗 token {total}」/ en "This session used {total} tokens"）；`token_stats.rs` `format_session_report` / `build_cc_idle_report` 改 in+out+cache_read；`format_cost_usd` 清退（气泡侧唯一消费方消失）；断言更新 token_stats.rs ×4 / i18n.rs ×3（含新增无 $ 钉子）/ lib.rs ×5 |
| F2 | `token-chart.ts`：`expectedLabels` 补零（≤7 生效）+ `MAX_BAR_W=56` 柱宽上限；`token-stats.ts` 新增 `dayLabelsBetween`（DST 安全）；`TokenStats.tsx` day 维度接线 + 标签 n≤7 per-bar 居中（textAnchor=middle）/ n>7 维持首尾；`token-chart.test.ts` +4 钉子 |
| F3 | `TokenStats.tsx` 注释行删 + `i18n.ts` 键清退（zh/en）+ `global.css` `.token-kpi-note` 清退 + `i18n.test.ts` 改清退断言 |
| F5 | `global.css` `.reminders` max-width 删 |
| F6 | `Settings.tsx`：大小/主题改下拉（label+select，busy/错误/回滚语义保留）；交互+工具播报合并「交互与播报」区（intg-row 卡片行 ×2 + 已启用/已停用）；`theme-seg` CSS 全清退（5 处 comma 选择器剥离，token-seg 保留）；i18n：`settings.interaction`/`sectionPet` 清退、`sectionInteraction`/`themeLabel` 新增（+清退断言测试） |
| F7 | `.intg-row` padding 12→8、path margin 6→4、error/notice 4→2；`.intg-note` 规则清退；每卡备份提示 → 接入管理区底一处（`settings-current`） |
| F8 | i18n `integrations.opencodeDesc/claudeDesc` zh/en 四值改宿主名「opencode」/「Claude Code」 |
| F9 | 两份 pet.json `displayName` 去后缀（cargo 断言 `contains(id)` 不受影响，随批A 基线验证） |
| F10 | `actionBadge` notify 💧→🔔；历史行经新共享助手 `execBadge`（审查 P3-1 落实——actionBadge 与 Tasks 历史行共用，历史行无 kind 字段故不能直接复用 actionBadge）+ `reminders.test.ts` 断言（含 execBadge 钉子）+ 注释三处（reminders.ts/Tasks.tsx/global.css） |
| F11 | `Tasks.tsx` 类别列条件排除删除（kindEmoji/kindLabel/`reminders.kind.todo` 全现成） |
| F12 | todo 行烟花勾选块删；i18n `reminders.fireworks`/`fireworksOverride` 清退（zh/en）；todoHint 过时文案修正（编辑态无任何可调字段）；`usesFireworks` OR 语义与 `reminders.test.ts:171-174` 钉子不动 |
| F14 | 前端：stats state/拉取/统计区 + `fetchReminderStats`/`ReminderStat` 清退 + i18n stats 四键清退；Rust：`ReminderStat`/`stats()`/`reminders_stats` 命令 + lib.rs 注册 + 测试 stats 断言删（logs 记账路径保留，测试改名 `logs_trigger_ack_dismiss_paths`） |
| F15 | 源图 alpha 紧裁 → 96% 满幅 1024（NEAREST 保像素风）→ `tauri icon` 重生成全套（32/64/128/128@2x/512/ico/icns/Square*）；32 版猫 bbox 实测 **81.2%×100%**（严格 alpha 阈值；视觉复核 ~90%×95%，旧版 75%×87.5%/70%×82.8% 显著提升；审查 P3-9 校准原"94%×100%"记录——该数为布局盒含居中留白的口径），轮廓/眼睛可辨、无裁切溢出（双独立复核一致）；android/ios 移动端目录清退；**桌面宠物本体零影响**（atlas 与 icons 独立） |
| F16 | `i18n.ts`：sectionInteraction 改值「交互管理」/ en "Interaction"、size 改值「宠物大小」/ "Pet size"、themeLabel·current·fellBack 清退、passThrough/toolBroadcast 拆名+描述四键；`Settings.tsx`：卡片行加 intg-desc、themeHint 上移、「当前渲染」块删；`global.css` 增 `.intg-desc`；`i18n.test.ts` F6 测试扩为二轮版（npm 439 全绿）；**二轮续**：intg-desc 改块级两行结构（名称行下独立 <p>）、小字统一 12px（settings-pet-label/intg-desc 13→12）、死类 `.settings-check` 清退 |

文档同步（随实施完成）：V2-DESIGN §3.2（M3 idle 汇报段 F1 修订注记）/ §5.4（CC 汇报文案两处）/ §4.7（列表描述 F10/F11/F12/F14 注记）；V2-TEST-CASES TC-M3-09-1 / TC-M5-05 / §4.7 列表（TC-M4-04）；本文件 §5.2-3（TC-M5-05 预期）。v1 线 TC-RM-11/TC-RM-13 历史验收记录不回改（docs/v1 留档原貌约定）。

**审查轮（2026-08-28，tester + committer 双审后「应修尽修」）**：tester 全项 PASS（0 P1/P2 + 4 P3）；committer **APPROVED with comments**（无 P1；P2-1 + P3×10）。同批清偿：**P2-1** `chartDayLabels` deps 追加 rows（跨午夜驻留 Refresh 后标签窗口跟随前进，防 7d 8 柱/今日 2 柱陈旧窗口）+ **P3-1** 提取共享助手 `execBadge`（actionBadge 与历史行共用，消 F10 偏差）+ **P3-2** reminders.ts 文件头陈旧注释（ReminderStat 移除留痕）+ **P3-3/P3-4** README:268 / V2-SCOPE:54 旧气泡文案改单总量口径 + **P3-5** `dayLabelsBetween` 直测 ×3（两端含/跨月/倒置空表）+ **P3-6** themeLabel 恒真断言移除（HEAD 无此键，F6 增 F16 删同批净零，注释说明）+ **P3-7** `should_report` 口径差注释钉住（判定宽于显示有意为之，防误改 TC-TK-12 静默语义）+ **P3-8** Settings 尾部缩进修正 + themeHint 转 `<label htmlFor>`（a11y）+ **P3-9** §12.4 F15 占比数字按实测校准（81.2%×100%，三源口径注记）+ **P3-10** §12.1 F1 文档联动列去 TC-TK-10（v1 线）。清偿后基线复跑见 §12.3。

---

## 十三、新增第三 agent 接入成本审计（2026-08-28，预研备查）

> 起因：用户问「新接入一个 agent（类似 opencode）是纯新增还是要改老代码」。全量扫描结论：**不是纯新增——约 12 处老代码必改**。分层抽象总体良好（状态机 / agent tab / 气泡链路均数据驱动零改动），但 agent 注册点**散落各层、各持一份微型注册表互不引用**（Rust 3 份：AGENT_WHITELIST / AGENT_* 常量 / ID_* 常量；TS 1 份：token-stats 常量 + switch；另有 i18n 键）。本节为预研记录备查；registry 收敛重构是否立项待用户决策。

### 13.1 零改动面（已数据驱动）

- 状态机 `session_state.rs`（复合键 `agent:sessionId`，agent 纯字符串透传，优先级合并只看 kind）
- Token 页 agent tab / 模型 chips（`token-chart.ts:164` `agentsWithRows` 从 rows 动态导出——第三家有数据自动出 tab）
- 气泡 `[徽标]` 渲染（payload.agent 透传 + 前端短名映射）、右键菜单 by_agent 分布行、工具级气泡（detail 协议 agent 无关，新插件发 detail 即得）
- `POST /state` 契约（`http_server.rs:279-299` 只做白名单字符串校验，body 协议 agent 无关）
- 例程功能（绑定 opencode CLI，与第三 agent 正交）；`action_exec.rs` 的 `task` 伪 agent 与 HTTP agent 不冲突（新 agent id 不能叫 "task"）

### 13.2 纯新增面（照现有模式写新文件/函数，不动老代码）

- 事件源 hook 脚本（照 `claude-code-hook.js` 模式抄，POST 协议现成）
- 统计提取模块（`transcript.rs` 等价物）+ `cc_to_token_row` 式行转换 + `build_cc_idle_report` 式 idle 汇报
- `integrations/` 第三套 install/uninstall/config_state/canonical 函数 + `BUNDLED_*_HOOK` 脚本文件
- 前端 `src/lib/adapters/<new>.ts`——**注意：`AgentAdapter` 接口是装饰性抽象，主链路无人 import（归一化实际在插件脚本侧），新增 adapter 无运行时效果**

### 13.3 必改老代码清单（~12 处硬编码分支）

| # | 层 | 位置 | 现状 |
|---|---|---|---|
| 1 | Rust 事件入口 | `http_server.rs:41` `AGENT_WHITELIST` | 唯一明示注册点（注释注明「新增 agent 时同步」） |
| 2 | Rust idle 分流 | `lib.rs:109` `idle_hook_body` match | 硬编码 `"opencode"`/`"claude-code"` 两臂 + 分支内字面量 |
| 3 | Rust 统计编排 | `token_stats.rs` `query_stats_dual`/`today_stats_dual` + `token_stats_query`/`token_stats_today` 命令 | **双源硬编码**（`opencode_data_dir()` + cc cache 两源写死）；degraded 语义只建模「opencode 错 × CC 有数据」，第三源进来需重推 N 源容错 |
| 4 | Rust 接入管理 | `integrations/mod.rs` `status_for` | `if id == ID_OPENCODE … else 当作 CC` 二元——第三 id **会错误落进 CC 探测分支** |
| 5 | Rust 接入管理 | `mod.rs` `integrations_status` | 硬编码 `vec![两行]`——设置页只显示两个接入 |
| 6 | Rust 接入管理 | `mod.rs` `integrations_install`/`integrations_uninstall` | id 守卫只认两 id + match 二元分发，无 trait 无注册表 |
| 7 | 前端徽标 | `token-stats.ts:47` `agentShortName` switch | oc/cc/task/原名——气泡徽标、菜单分布行、会话徽标三处共用的单一映射点 |
| 8 | 前端徽标 | **`TokenStats.tsx:83` `agentBadgeOf`** | **else 一律→"oc"——第三 agent 会被错标 oc，唯一「静默错误」级耦合**（其余处 fallback 显示原名，只是丑不算错） |
| 9 | 前端展示规则 | `TokenStats.tsx:90` `agentLabel`、`:467/:502` cost「—」per-agent 规则 | 各自二元判断（新无费用 agent 需扩） |
| 10 | 前端接入 UI | `Settings.tsx:545` nameKey 三元、`integrations.ts:33` `IntegrationId` 联合类型 | 第三接入显示错名 / 类型不含 |
| 11 | i18n | `token.agent.*`、`integrations.*Desc`、`token.costOpencodeOnly`、`token.degraded` | ×zh/en 双份（键集合一致性测试强制同步）；注：`costOpencodeOnly` 随 F3 删除、`token.degraded` 措辞随 F1/N 源化重写——届时自然减负 |
| 12 | 测试面 | `lib.rs:571-722` idle 分流单测、`token_stats.rs:1747-2040` 双源/degraded/by_agent 用例、前端 `token-chart.test.ts` 等 | 改白名单/编排后会红，需同步 |

### 13.4 收敛机会（若确定接第三家再做）

Rust 定义 `AgentSpec { id, short_name, bundled_hook, install/uninstall/status, idle_report, stats_source }` 数组——AGENT_WHITELIST、integrations 三命令 match、`status_for` 分支、`idle_hook_body` 分流、双源编排全部数据驱动（degraded 改「N 源中主源错误 × 其余有数据」）；前端建单一 `AGENTS` 注册表 `{id, short, i18nLabelKey, hasCost}` 供 `agentShortName`/`agentBadgeOf`/`agentLabel`/Settings nameKey/cost 列消费。收敛后新增 agent = **一个 hook 脚本 + 一套函数 + 一行注册 + i18n 键**，回归纯新增形态。**是否立项待用户决策；未收敛前按 §13.3 清单照做亦可。**

---

## 十四、token 统计跨天会话归属缺陷：聚合粒度 session 级（2026-08-29，**已实施同日**）

> 来源：用户日常使用疑问（2026-08-29）——「跨天会话在第二天有新对话内容时，统计的 token 是整个会话的还是第二天的？」源码级诊断确认：**是整个会话的累计值**。用户判定该行为与「按天统计」预期不符（方案设计问题），修正方案已对齐并获两项裁定（见 §14.2）。
> 状态：**✅ 已实施（2026-08-29 同日完成）**——三项实施微决策经用户确认（message 行筛选 / CC 桶 model 归属 / ts 缺失兜底，见 §14.5）；基线 `cargo test` **366 passed + 3 ignored**（+9 新钉）/ `npm test` 447（前端零改动原样通过 = IPC 契约不变验证）/ `npx tsc --noEmit` 0 错 / `cargo build` 零警告；本机真实库只读对账通过（by day message 级 vs 参考 SQL：30d 67 行 / $12.2916 双侧零误差）。

### 14.1 问题与根因（源码级证据链）

**症状**：一个会话跨天使用（第一天聊了一部分、第二天继续），第二天的「今日 token」= **整个会话的累计值（含第一天）**；且第一天的统计**完全丢失**该会话的贡献。

**根因：两个数据源的聚合粒度都是 session 行**（累计值 + 单点时间 `time_updated`），没有按 message 时间切片：

| 源 | 证据 |
|---|---|
| opencode（SQLite） | `session` 表 `tokens_*`/`cost` 为**会话累计值**（逐 message 增量写入更新该行，TC-TK-11 实测留痕 `token_stats.rs:17-26`）；今日聚合 `query_today_on`（`token_stats.rs:514`）与 day/week/range 共用的 `query_grouped`（`:357`）均 `WHERE time_updated ∈ 窗口` 后 `SUM(tokens_*)` 整行——跨天会话第二天有新对话 → `time_updated` 推进到今天 → 整行进今天 |
| Claude Code（transcript） | 每个会话 jsonl 聚合为一行 `CcSessionRow`（`transcript.rs:258` finalize 全部 assistant usage 求和）；`today_stats_dual`（`token_stats.rs:847`）与 `cc_group_rows`（`:684`）同样只看 `time_updated` 是否落在窗口，命中整行进桶 |

**衍生影响（同一根因）**：

1. **第一天贡献消失**：day 维度按 `strftime(time_updated)` 分组（`token_stats.rs:329`），整个会话 token 全部归到**最后活跃那天**；
2. **窗口漏计**：7d/30d/自定义窗口若不含最后活跃日，该会话**完全不计入**；
3. 气泡「本期会话」数字同理是全会话累计（`format_session_report`）——但该处语义本就是「本会话共消耗」，**不属于缺陷**（保持不动）。

### 14.2 数据源核实与决策记录（2026-08-29）

**两个源都有 message 级明细可用**（本机真实数据只读核实）：

- opencode.db `message` 表：`data` JSON 含 `$.tokens`（input/output/reasoning/cache.read/cache.write）、`$.cost`、`$.modelID`、`$.providerID`，每条带 `time_created`（毫秒）；mock 过滤与模型归并可全部在 message 级完成，**无需 JOIN session**；
- CC jsonl：每条 assistant 行自带 `timestamp` + `usage` 五维；现有去重键（`message.id` → uuid 兜底，S3 末条覆盖）已具备，按行 timestamp 归天即可；
- **一致性实测**（2026-08-29，本机真实库抽样 5 个会话）：message 求和与 session 累计值**逐字段完全一致**（input/output/cache_read/cost 全对上）→ message 级聚合与现有口径等价，只是粒度更细，可安全替换。

**用户裁定（2026-08-29）**：

| 项 | 决定 |
|---|---|
| 旧版 opencode 无 message 表 / data 缺 tokens 结构 | **严格报错** `schema-mismatch`（提示升级 pulse-pet），与现有 session 列缺失处理一致，不静默口径漂移；现有 opencode 1.18.x 均有 message 表，实际影响极小 |
| range 视图（自定义跨度按模型聚合） | **一并下沉** message 级（窗口不含最后活跃日时按天只计窗口内消息），与 day/week/today 口径统一 |

### 14.3 修正方案（定稿）

**原则**：day/week/range/today 四类聚合下沉到 message 级，按**消息产生时间**归天；by-session 视图保持会话累计不变（该语义本来正确）。

**1. opencode 源（`token_stats.rs`）**

- 新增 `MESSAGE_REQUIRED_COLUMNS`（id/session_id/time_created/data）+ `check_message_schema`；`open_checked` 同时校验 session、message 两表，message 缺失 → `schema-mismatch`（§14.2 裁定）；
- `query_grouped`（day/week/range 共用）改：`FROM message`，`strftime(m.time_created/1000,'unixepoch','localtime')` 归天，分组 `day, model_id, agent`；
- `query_today_on` 改：`WHERE time_created >= 今日0点 AND <= now`；
- 5 维 tokens/cost 用 `COALESCE(json_extract(data,'$.tokens.X'),0)` 提取（`json_valid` 守卫，损坏 data → 0 保留行，沿 MOCK_FILTER_SQL 同款守卫先例）；mock 过滤用 `$.providerID`、model 归并用 **message 级 `$.modelID`**（会话中途换模型也能分对，较现状 session.model 更准）；
- **不动**：`query_by_session`、`query_current_session`、气泡链路（`should_report`/`format_session_report`）。

**2. CC 源（`transcript.rs`）**

- `SessionState.usage_by_key` 值扩展为 `(usage5, 该行 timestamp)`（去重语义不变：同 message.id 末条覆盖、只计一次）；finalize 按 `local_day_label(ts)` 分桶，`CcSessionRow` 新增 `by_day` 明细；
- `today_stats_dual` / `cc_group_rows`：today/day/week/range 改按分桶明细聚合（替换「整行进最后活跃日桶」）；session 视图与 `last_assistant_ts` 护栏不变；
- 增量解析路径（CacheEntry 方案 α append）同步携带 timestamp。

**3. 不变项（契约与口径）**

- Tauri IPC 契约（命令名/参数/返回体）、`TokenRow`/`TodayStats` 形状、前端代码**全部零改动**（day 标签口径变准而已）；
- 口径不变：reasoning 不计、CC cost=0、mock 过滤、气泡「本期会话」= 会话累计、前端 30s 缓存；
- 性能：message 表个人量级（几万行）窗口全扫毫秒级，只读库不建索引。

### 14.4 实施清单与验收

- Rust 测试新增跨天夹具：opencode 同一 session 两条 message 不同天 → 两天各得各的；昨日 message 不进 today；7d 窗口不含最后活跃日仍收到前几天量；mock 过滤（message 级 providerID）/ 损坏 JSON 守卫 / message 表缺失报 schema-mismatch；
- CC 测试：单 jsonl 跨天两行 assistant → `by_day` 两桶，去重不重复计；现有 `query_by_day_*` 等夹具从 session 行改为 session+message 双插；
- 前端测试零改动；文档联动：V2-DESIGN §3.2/§5.3 口径修订（day 归属 = 消息产生时间）+ V2-TEST-CASES TC-TK-06/07、TC-M3 增补跨天用例；
- 验收基线：`cargo test` + `npm test` + `npx tsc --noEmit` 全绿；本机真实库跑修正后聚合 SQL 与现网今日数值对比复核。
- 工作量预估：Rust ~200 行 + 测试 ~150 行，半天内。

### 14.5 实施记录（2026-08-29）

> 实施前两项校准 + 三项微决策（用户确认按默认）+ 实施偏差留痕。

**实施校准（相对 §14.1/§14.3 文字）**：

1. §14.1 所写 `today_stats_dual`（token_stats.rs:847）已被 registry-P3（2026-08-29 早间合入）泛化为 N 源编排——实施落点为 `today_source_stats` CC 分支（原 :905-935）与 `query_source_rows` CC 分支 + `cc_group_rows`，编排层/MergeAcc/三态判据零改动（**agent-registry 架构未受影响，改动全部收敛于单源实现内部**，见 agent-registry.md 文末补充说明）；
2. 真实 message 表另有 `time_updated` 列（白名单按定稿只校验 id/session_id/time_created/data）；`$.tokens` 内层为 `{input, output, reasoning, cache: {read, write}}`（cache 嵌套，实施前真实库核实）；
3. §14.4 文档联动所指「V2-TEST-CASES TC-TK-06/07」——TC-TK-06/07 属 docs/v1 冻结线（AGENTS.md 约定不回改），实际落地为 V2-TEST-CASES **TC-M3-18** 并以「v1 TC-TK-06/07 语义扩展」括注承接（文档维护轮惯例，committer P3-3 澄清）。

**微决策（默认方案获用户认可 2026-08-29）**：

| # | 决策 | 落点 |
|---|---|---|
| 1 | message 行筛选 = `json_valid(data) AND $.tokens IS NOT NULL`（实测 assistant 行 100% 带 tokens / user 行 0% 带——等价只取 assistant 行，防 user 行零值组污染图表；损坏 data 沿 json_valid 守卫先例不炸不入聚合） | `MESSAGE_ROW_FILTER_SQL`（CASE WHEN 形态保证求值序） |
| 2 | CC by_day 桶的 model 归属保持**会话级**（末条 assistant 的 model，同今天）——只改时间归属不改模型归属（§14.3 CC 条目未要求 message 级 model；opencode 侧则为 message 级 `$.modelID`，较定稿更准） | `cc_group_rows` 聚合键用 `r.model_id` |
| 3 | CC assistant 行缺 timestamp（真实数据不出现）→ 兜底归会话 `time_updated` 日；两者皆无 → 不进 by_day（仍计会话总量） | `finalize_state` 分桶 |

**实施落点**：

- **transcript.rs**：`usage_by_key` 值 `Usage5` → `(Usage5, Option<i64> ts)`（行 ts 在 feed_lines 顶部解析一次复用，顺带消原 assistant 分支的二次 timestamp 解析）；`finalize_state` 按 `local_day_label(ts)` 分桶（BTreeMap 升序确定性）产出 `CcSessionRow.by_day: Vec<CcDayUsage {day, first_ts, 五维}>`；增量路径（方案 α）随值类型扩展自动继承（`alpha_incremental_matches_full_reparse` 逐字段对账自动覆盖 by_day，无需新增增量测试）。
- **token_stats.rs（CC 消费端）**：`cc_group_rows` 签名改收 `&[CcSessionRow]`，day/week/range 改遍历 by_day 桶（窗口过滤在桶级 `first_ts`——custom 窗口双侧按天对齐故精确；preset 窗口 to=now 下桶内消息时刻不可能晚于已落盘解析时刻、同样精确〔tester P3-2 措辞校准：非笼统"按天对齐"〕；**去掉整行 time_updated 预过滤** = 窗口漏计修复）；today CC 分支改按桶 `day == local_day_label(today_start)` 累加；session 视图与 `build_cc_idle_report` 不动。
- **token_stats.rs（opencode 源）**：`MESSAGE_REQUIRED_COLUMNS` + `check_message_schema`（与 session 校验共用 `check_table_columns` 助手）入 `open_checked`；`query_grouped` 改 `FROM message` / `time_created` 过滤归天 / 五维+cost 走 `COALESCE(json_extract(data,'$.…'),0)`；`query_today_on` 同款；三个包装函数 day/week 表达式换 `time_created`。`query_by_session`/`query_current_session`/气泡链路（`should_report`/`format_session_report`）零改动。
- **测试**：夹具 `make_db` 全局补建 message 表 + `insert_message(_model)`/`message_data` 助手（data JSON 照真实形态含嵌套 cache）；既有 grouped/today/dual 系用例改「session+message 双插」或转 message 夹具；新钉 9 枚（token_stats.rs 6〔其中 CC 消费钉 1〕+ transcript.rs 3，清单见 TC-M3-18）；`real_db_reconciliation_manual` 参考 SQL 同步 message 级。

**验证**：cargo 366 passed + 3 ignored / npm 447 原样 / tsc 0 错 / build 零警告；真实库对账 by day 67 行 $12.2916 vs 参考 SQL 零误差、by session 299 行零误差；真实双源冒烟 day 35 行（message 级跨天拆分天数自然多于原 session 级）、today/degraded 正常。**用户目验**（日常使用顺带）：跨天会话次日的「今日 token」不再包含前一日用量；Token 页 day 视图跨天会话逐日拆柱。

**tester 验证轮（2026-08-29）**：**PASS（0 P1 / 0 P2）**——基线 4 项 / TC-M3-18 钉子 9/9 真钉核对 / 白盒 7 项（`effective_ts.unwrap` 安全性、BTreeMap 确定性、week 标签同日不变性含跨年 oracle 实测、CASE 求值序、增量等价、DST 退化路径）/ 真实库只读 4 项（对账零误差、degraded=None、message≤session 三维、mock 零泄漏）；不动项经 diff hunk 核对确认零改动。2 项 P3 当日清偿：**P3-1** `CcDayUsage.first_ts` 取 HashMap 迭代首遇值（值级不确定，未来同日多 ts 夹具会 flake）→ 改取桶内最早消息时刻 + 新钉 `s14_same_day_bucket_first_ts_is_earliest`；**P3-2** 「前端窗口按天对齐」注释表述过宽（仅 custom 双侧成立）→ 措辞收窄（custom 天对齐精确；preset to=now 下桶内时刻不可能晚于解析时刻，同样精确），代码注释 + V2-DESIGN §5.3 + 本节三处同步。清偿后基线 cargo **367 passed + 3 ignored**。**复测轮（同日，task_id 回调）**：2 项 P3 清偿质量合格（min 逻辑/新钉真实/三处文档到位/回归面干净，`alpha` 增量对账在 min 语义下确定性等价）；复测新提 **P3-3**（`first_ts` 字段级文档残留「首条」与笼统「按天对齐」措辞，全仓唯一未收窄处）——当场顺手清偿（transcript.rs:74），最终基线 cargo 367+3 / build 零警告不变。

**committer 审查轮（2026-08-29）**：**APPROVED（0 P1 / 0 P2）**——语义正确性与 §14.3 定稿/三微决策逐条核对一致（含四视图桶级过滤一致性、老行为→新行为逐情形推演无丢量、增量整结构体对账覆盖 by_day、TranscriptCache 纯内存态无跨版本序列化风险）；不动项逐 hunk 核对全零触碰（by-session/气泡链路/N 源编排/IPC 契约与前端）；npm 447 原样 + 形状未动 = 契约不变充分证据。P3×5：**P3-1**（by_day 字段文档「总量=桶和」缺例外括注）/**P3-2**（§14.5「9 枚」括号枚举 6+1+3 表面矛盾）/**P3-3**（§14.4「TC-TK-06/07」计划措辞歧义）三项纯文档当场清偿；**P3-4**（旧库无 message 表时气泡链路 `.ok()?` 吞错静默消失——属「严格报错」裁定接受的边界，面板有升级提示，与 session 白名单吞错同型；如需完备后续可加 plog 留痕）/**P3-5**（进程内 TranscriptCache 缓存 CC 日标签，运行中热切换系统时区会短暂双源不一致、重启自愈；不建议为此改缓存结构）两项**记录备查不改**。交付结论：**可安全合入 develop**；提交边界提醒——工作区另有仓级 `.opencode/` 编排文件改动与 `images/` 未跟踪目录，与本轮 pulse-pet 6 文件须分开提交。

---

## 十五、Windows 托盘/任务栏图标 tile 化（F15 后续，2026-08-29，**已实施**）

> 来源：F15 实施后用户 Windows 实机复验反馈——猫占比提升后仍嫌小，想要 Mac dock 栏的观感（"猫大小合适 + 底色圆角方块"）。

**根因定位**：Mac dock 的"底"不是图标资产的一部分——macOS 26 对 App 图标自动合成 Liquid Glass 圆角底（浅灰玻璃质感），Windows 任务栏/托盘**无此机制**、按像素原样显示。唯一杠杆 = 把 tile 直接画进 **Windows 侧**图标资产。

**实测口径（2026-08-29 dock 截屏逐像素取样）**：系统 tile = 浅灰垂直渐变 `#e1e1e1`(顶)→`#c0c0c0`(底) + 玻璃描边 rim ~1.2% 宽（顶 `#f2f3f5`/侧 `#e2e4e7`/底 `#d2d4d6`，顶亮底暗 = 立体感来源）+ 圆角 ~22%；图标画布以 ~97.5% 贴入 tile（猫深色轮廓 bbox = tile 的 67%×79%，与源图轮廓 bbox 69%×81% 换算一致 → 即"画布原样贴入"而非"猫居中缩小"）。

**决策记录（与用户逐轮对齐）**：
1. **tile 只上 Windows 侧资产**（`icon.ico` + `Square*Logo` 全套 + `StoreLogo` + 托盘专用 `tray-tile.png`）；macOS/Linux 侧（`icon.icns`/`icon.png`/`32x32.png`/`64x64.png`/`128x128*`）**零改动**——icns 若换 tile，macOS 系统合成底会"方块套方块"。
2. **底色裁定**：初版出两档粉色预览（耳粉 `#f4a8b8` / 玫瑰 `#e0719f`），用户均不满意并指出 Mac 实际观感是**浅灰**而非粉 → 改为按 dock 实测取色复刻（取色截图存 `images/`，复刻 vs 实拍对比图逐像素核对：猫 bbox 67%×79% 双向一致）。
3. **托盘也换 tile**（用户选定"任务栏 + 托盘都换"；已知代价：16~24px 下猫占比稀释，粉/灰底整块醒目度补偿），macOS 菜单栏保持紧裁猫 → `tray.rs` `#[cfg(windows)]` 资产分叉（唯一代码改动）。
4. 底板 4x 超采样抗锯齿（圆角/描边平滑），像素猫最后 NEAREST 贴上保锐利。

**实施落点**：`src-tauri/icons/` 11 文件更新（ico + Square* 9 + StoreLogo）+ `tray-tile.png` 新增（32px，PIL LANCZOS）；`tray.rs:106` 附近 cfg 分叉。生成链路：PIL 脚本合成 1024 master（脚本口径见本节"实测口径"，参数化可重出）→ `tauri icon` 输出临时目录 → 只拷 Windows 侧回 `icons/`（android/ios 产物弃置）。

**验证**：基线 cargo 367 passed + 3 ignored / npm 447 / tsc 0 错 / build 通过；macOS 侧资产零改动（菜单栏托盘/dock 观感不变，git status 核对无触碰）。**Windows 目验口径**：托盘 tile 可 Windows dev/release 目验；**任务栏 exe 图标需 release 打包后目验**（走 CI tag 流程，同 F15 口径）。

---

## 十六、panel 默认高度 640→650（2026-08-29，**已实施**）

> 来源：用户目验反馈（2026-08-29）——打开 Token 页，时序柱状图底部的年月日标签只显示一半（被窗口底边裁切）。

**根因**：panel 默认高 640（`tauri.conf.json` 唯一来源，无持久化/程序改高），Token 页内容总高 ≈702px 可滚动；日期标签文字顶部恰在逻辑 y≈635.5，仅露出 ~4.5px。**裁定**：用户只要标签行完整（不追求整页无滚动），640→650 后标签底距窗口底 5.5px（截屏像素实测），页面其余部分保持可滚动。验证链：退出旧实例 → `tauri build` → 启动 + `open -n` 二次实例唤起 panel（TC-APP-02 捷径）→ `screencapture -R` 截窗 → 亮色文字行像素核对。基线 tsc 0 错 / npm 447 原样（纯配置改动，Rust 不涉及）。

---

## 十七、设置页选择宠物下拉间距 +10px（2026-08-29，**已实施**）

> 来源：用户目验反馈（2026-08-29）——设置页「宠物大小」上方的选择宠物下拉框间距太挤。

**根因**：`select#pet-select` 与下方「宠物大小」label 之间间距 0（其他下拉后跟 h2 区块标题自带 26px 上边距，唯此处 select 直贴 label）。**改法**：一条兄弟选择器规则 `.panel-settings select + .settings-pet-label { margin-top: 10px }`（`global.css`，全页仅命中此一处，零 TSX 改动；量级经用户裁定 12→10）。验证：vite dev + playwright 截设置页，`getBoundingClientRect` 实测 gap=10px。基线 tsc 0 错 / npm 447 原样。

---

## 十八、卸载应用不自动清理接入插件：文档 + 设置页提示（2026-08-29，**已实施**）

> 来源：用户问询（2026-08-29）——"卸载应用时会自动卸载已安装的插件吗？"

**事实口径**：接入插件全装在用户主目录（opencode `~/.config/opencode/plugins/` + `opencode.json(c)` 条目；CC `~/.pulsepet/hooks/` + `~/.claude/settings.json` 条目），App 卸载（macOS 拖废纸篓 / Windows 卸载器）只删 App 自身文件、**不碰用户目录** → 插件残留。残留无害已核实：hook 上报全链路 try/catch 静默（指数退避），agent 功能零影响，仅孤儿文件。**裁定**：选方案 1（文档提示；Windows 卸载器清理不做、App 内 status 提示对"App 已被卸"场景无从谈起）。

**实施落点**：① README「卸载插件」节 blockquote 提示（**四轮定稿**：与设置页同步升级为"接入说明"三点版——备份 / 重开会话生效〔注明插件随会话进程加载不热重载〕 / 卸载顺序 + 残留无害）；② 设置页接入管理卡列表下方单条脚注，**三轮改版（同日用户逐轮裁定）**：初版单句 → 二轮并入备份提示合一句 → 三轮定稿为"接入说明"三行编号格式（`integrations.notes` 键承载，zh/en 同改；backupNote/uninstallHint 两旧键清退；备份 / 会话生效时机〔opencode/CC 均在会话进程启动时加载插件，卸载后已运行中的会话保持原样——当日实机排查证实的反直觉行为〕 / 卸载顺序三点；CSS `settings-notes` pre-line 按行渲染）；playwright 渲染实测 4 行 76.75px。基线 tsc 0 错 / npm 447 原样。

---

## 附：清偿记录

（清偿后回写：日期 + 来源任务 ID + 去向。已有示例：§6.2-5 TC-M4-18 核心面 2026-08-27 随 v0.2.1 §四场景 2 验证；§7-7 或已随 v0.2.1 R2 顺手消化，打磨轮核对）

- [x] **§8-1 文档滞后（v2-m6 P3-②）**：✅ 已清偿 2026-08-27（文档维护轮，supervised-coding 执行）——V2-DESIGN §6.0/§6.2/§6.3/§6.4 共 7 处 + V2-TEST-CASES TC-M6-04/TC-M6-06-4 共 4 处对齐"右键菜单子行"口径，修订注记引用 §3.4 后裁定；改动在工作区待入库（与 V2-OPEN-ITEMS 本文件 §五~§十 一并提交）
- [x] **§十一 宠物大小三档 + 视觉归一化**：✅ 已实施 2026-08-28（同日设计 + 实施）——Rust `pet_size.rs`/`windows.rs::apply_pet_size`/`atlas.rs` idle 度量 + 前端 `pet-scale.ts`/`size-bridge.ts`/档位化渲染/设置页分段控件；公式两处实施修订（帧上限替代全表 bbox，见 pet-size.md §3.4）；附带清偿 §11.5 en 菜单裁剪（文案缩短 + 防御 CSS）与 atlas 兜底短缓冲越界隐患（防御式访问，保持短以维持占位猫降级——committer P2-1 裁定）；基线 cargo 346 passed+3 ignored / npm 433 / tsc 0 错；dev 冒烟通过（large 档窗口 280×280 实测）+ committer 审查 APPROVED（六项审查意见当日落地）。完整留痕：`docs/v2/pet-size.md`；用户目验 TC-SZ-01~09 日常顺带
- [x] **§十二 v2 收尾用户反馈批次 F1~F15**：✅ 已实施 2026-08-28（用户批准后同日）——F4 标题字号（先行）+ F1 气泡单总量 / F2 柱图三改（补零+柱宽上限+标签居中）/ F3 费用标注 / F5 例程页全宽 / F6 设置页控件形态统一（下拉+卡片行，theme-seg 清退）/ F7 接入卡缩高+备份提示去重 / F8 接入命名按宿主名 / F9 宠物下拉字样 / F10 notify 徽标 🔔 / F11 todo 类别列 / F12 todo 烟花勾选项（含 todoHint 修正）/ F13 datetime-local 控件基线 / F14 历史统计区移除（含 Rust `reminders_stats` 命令清退）/ F15 图标资产重制（紧裁 96% 满幅 + `tauri icon` 全套）。基线 cargo 346+3 ignored / npm 439 / tsc 0 错 / build 通过；逐项落点见 §12.4。用户目验项见 §12.3；F15 任务栏图标需 Windows release 实机。改动在工作区待入库
- [x] **§十四 token 统计跨天会话归属缺陷**：✅ 已实施 2026-08-29（方案定稿同日）——opencode 源四类聚合下沉 message 级（`MESSAGE_ROW_FILTER_SQL`/`MESSAGE_MODEL_ID_SQL`/`check_message_schema` + `query_grouped`/`query_today_on` 改 `FROM message` 按 `time_created` 归天）+ CC 源 by_day 分桶（`usage_by_key` 值携 ts → `CcSessionRow.by_day` → `cc_group_rows`/today 桶级聚合）；by-session 视图与气泡会话累计语义、agent-registry N 源编排架构均不动。基线 cargo 366 passed+3 ignored（+9 钉）/ npm 447 原样 / tsc 0 错；真实库对账零误差。完整留痕：§14.5；用户目验 = 跨天会话次日「今日 token」不再含前一日用量、day 视图逐日拆柱
- [x] **§十五 Windows 托盘/任务栏图标 tile 化**：✅ 已实施 2026-08-29（F15 后续，同日）——Windows 侧资产换"灰底玻璃 tile + 猫"（`icon.ico`/`Square*Logo` 9 件/`StoreLogo` 更新 + `tray-tile.png` 新增）+ `tray.rs` cfg 平台分叉（唯一代码改动）；macOS/Linux 侧资产零改动。底色经 dock 实测取色复刻（粉稿两版被否 → 浅灰玻璃），猫 bbox 与 dock 逐像素对齐（67%×79%）。基线 cargo 367+3 / npm 447 / tsc 0 错 / build 通过；Windows 任务栏 exe 图标待 release 实机（同 F15 口径）。完整留痕：§十五
- [x] **§十六 panel 默认高度 640→650**：✅ 已实施 2026-08-29（同日）——`tauri.conf.json` panel `height` 650，Token 页柱图日期标签完整可见（标签底距窗口底 5.5px，截屏像素实测）；页面其余保持滚动。基线 tsc 0 错 / npm 447 原样；目验 = 打开 Token 页标签不裁半
- [x] **§十七 设置页选择宠物下拉间距 +10px**：✅ 已实施 2026-08-29（同日）——`global.css` 兄弟选择器一条（`select + .settings-pet-label` margin-top 10px，全页唯一命中），playwright 实测 gap=10px；基线 tsc 0 错 / npm 447 原样；目验 = 设置页宠物区两下拉不再挤贴
- [x] **§十八 卸载应用不自动清理接入插件提示**：✅ 已实施 2026-08-29（同日）——README「卸载插件」节 blockquote + 设置页接入管理卡"接入说明"三行编号脚注（`integrations.notes` zh/en；备份 / 会话生效时机 / 卸载顺序；`settings-notes` pre-line 渲染；经三轮用户逐轮裁定），playwright 渲染实测；基线 tsc 0 错 / npm 447 原样；目验 = 设置页接入卡下方见三行接入说明
