# PulsePet v2 未完成事项清单（Open Items）

> 生成：2026-08-27（v2 M6 合入 develop 后）
> 来源：Windows 实机使用反馈（[issue #19](https://github.com/yq3/lab/issues/19) / [issue #20](https://github.com/yq3/lab/issues/20)）+ 源码级诊断（2026-08-27，诊断结论已分别留痕于两 issue）
> 性质：两项 **Windows 特有缺陷**，根因已定位、修复方案已裁定（R1-R5，见 [§三](#三修复任务清单r1r5统一实施)）。
> **状态（2026-08-27 闭环）**：R1-R5 **已修复并随 `pulse-pet-v0.2.1` 发布**——实施 commit `6f9e0be`（R1-R4）/ `9e609d6`（R5）/ `acc12b3`（本文件）/ `f2cf13e`（版本 bump 四件套），tag `pulse-pet-v0.2.1`（CI run 33071206433 双矩阵 success，安装包挂 draft Release）。测试基线全绿（`cargo test` 320+3 钉子 / `npm test` 409 / `tsc --noEmit`），committer 评审 APPROVED（P0/P1=0，三条 P3 加固已落地）。**Windows release 实机三场景验证通过（2026-08-27，v0.2.1，§四）**，#19 / #20 可闭环。
> 共同背景：与 v1 issue #9 同源——Windows 上 WebView2 环境创建异步、主线程泵消息期间页面已加载执行（GUI 子系统 + 控制台子进程交互）的时序盲区；v1 里程碑"Windows 实机验证后移"的欠账在 v2 实机使用中集中显性化。macOS 开发机均无法复现。
> 构成说明（2026-08-27 补充）：§一~§四为 issue #19/#20 专项记录（**已闭环**）；§五起为 **v2 六里程碑（M1~M6）工作流检查点遗留事项汇总**（supervised-coding 2026-08-27 归档，来源 `.opencode/workflows/task-pulsepet-v2-m1~m6.md`），清偿后回写勾选并注来源任务 ID 与日期；**§十一为 2026-08-28 新增**：宠物大小三档 + 视觉归一化特性（设计 + 实施同日完成，含 en 右键菜单裁剪与 atlas 短缓冲两处存量缺陷清偿，见 §11.5 与 `docs/v2/pet-size.md`）。

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
| 3 | TC-M5-05 | 真实 Claude Code 干活一个会话至 Stop | `[cc] 本期用了 Xk input / Yk output · 今日 T` 汇报气泡（无 cost 段） |
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

## 附：清偿记录

（清偿后回写：日期 + 来源任务 ID + 去向。已有示例：§6.2-5 TC-M4-18 核心面 2026-08-27 随 v0.2.1 §四场景 2 验证；§7-7 或已随 v0.2.1 R2 顺手消化，打磨轮核对）

- [x] **§8-1 文档滞后（v2-m6 P3-②）**：✅ 已清偿 2026-08-27（文档维护轮，supervised-coding 执行）——V2-DESIGN §6.0/§6.2/§6.3/§6.4 共 7 处 + V2-TEST-CASES TC-M6-04/TC-M6-06-4 共 4 处对齐"右键菜单子行"口径，修订注记引用 §3.4 后裁定；改动在工作区待入库（与 V2-OPEN-ITEMS 本文件 §五~§十 一并提交）
- [x] **§十一 宠物大小三档 + 视觉归一化**：✅ 已实施 2026-08-28（同日设计 + 实施）——Rust `pet_size.rs`/`windows.rs::apply_pet_size`/`atlas.rs` idle 度量 + 前端 `pet-scale.ts`/`size-bridge.ts`/档位化渲染/设置页分段控件；公式两处实施修订（帧上限替代全表 bbox，见 pet-size.md §3.4）；附带清偿 §11.5 en 菜单裁剪（文案缩短 + 防御 CSS）与 atlas 兜底短缓冲越界隐患（防御式访问，保持短以维持占位猫降级——committer P2-1 裁定）；基线 cargo 346 passed+3 ignored / npm 433 / tsc 0 错；dev 冒烟通过（large 档窗口 280×280 实测）+ committer 审查 APPROVED（六项审查意见当日落地）。完整留痕：`docs/v2/pet-size.md`；用户目验 TC-SZ-01~09 日常顺带
