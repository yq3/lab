# PulsePet v2 未完成事项清单（Open Items）

> 生成：2026-08-27（v2 M6 合入 develop 后）
> 来源：Windows 实机使用反馈（[issue #19](https://github.com/yq3/lab/issues/19) / [issue #20](https://github.com/yq3/lab/issues/20)）+ 源码级诊断（2026-08-27，诊断结论已分别留痕于两 issue）
> 性质：两项 **Windows 特有缺陷**，根因已定位、修复方案已裁定（R1-R5，见 [§三](#三修复任务清单r1r5统一实施)）。
> **状态（2026-08-27 闭环）**：R1-R5 **已修复并随 `pulse-pet-v0.2.1` 发布**——实施 commit `6f9e0be`（R1-R4）/ `9e609d6`（R5）/ `acc12b3`（本文件）/ `f2cf13e`（版本 bump 四件套），tag `pulse-pet-v0.2.1`（CI run 33071206433 双矩阵 success，安装包挂 draft Release）。测试基线全绿（`cargo test` 320+3 钉子 / `npm test` 409 / `tsc --noEmit`），committer 评审 APPROVED（P0/P1=0，三条 P3 加固已落地）。**Windows release 实机三场景验证通过（2026-08-27，v0.2.1，§四）**，#19 / #20 可闭环。
> 共同背景：与 v1 issue #9 同源——Windows 上 WebView2 环境创建异步、主线程泵消息期间页面已加载执行（GUI 子系统 + 控制台子进程交互）的时序盲区；v1 里程碑"Windows 实机验证后移"的欠账在 v2 实机使用中集中显性化。macOS 开发机均无法复现。
> 构成说明（2026-08-27 补充）：§一~§四为 issue #19/#20 专项记录（**已闭环**）；§五起为 **v2 六里程碑（M1~M6）工作流检查点遗留事项汇总**（supervised-coding 2026-08-27 归档，来源 `.opencode/workflows/task-pulsepet-v2-m1~m6.md`），清偿后回写勾选并注来源任务 ID 与日期；**§十一为 2026-08-28 新增**：宠物大小三档 + 视觉归一化特性（设计 + 实施同日完成，含 en 右键菜单裁剪与 atlas 短缓冲两处存量缺陷清偿，见 §11.5 与 `docs/v2/pet-size.md`）；**§十二为 2026-08-28 二次新增**：v2 收尾用户反馈批次 F1~F16（气泡汇总 / Token 页柱图与文案 / 例程页全宽·notify 徽标·todo 类别列·todo 烟花勾选项·日期时间控件规格·历史统计区移除 / 设置页控件形态·接入卡缩高·命名统一·宠物下拉字样·二轮微调 / Windows 托盘与任务栏图标资产；**2026-08-28 用户批准后同日全部实施**，F16 为实施后目验二轮微调，见 §12.4）；**§十三为 2026-08-28 三次新增**：新增第三 agent 接入成本审计（预研备查——约 12 处老代码必改 + agent registry 收敛机会，是否立项待决策）；**§十四为 2026-08-29 新增**：token 统计跨天会话归属缺陷（聚合粒度 session 级 → 跨天会话 token 全部归到最后活跃日；修正方案已与用户对齐——day/week/range/today 四类聚合下沉 message 级按消息时间归天，**同日实施完毕**，见 §14.5 实施记录）；**§十五为 2026-08-29 四次新增**：Windows 托盘/任务栏图标 tile 化（F15 后续——复刻 macOS dock 系统合成底观感，tile 只上 Windows 侧资产 + tray.rs 平台分叉，**同日实施完毕**，见 §十五）；**§十六为 2026-08-29 五次新增**：panel 默认高度 640→650（Token 页图表日期标签被窗口底边裁半，用户目验驱动微调，见 §十六）；**§十七为 2026-08-29 六次新增**：设置页选择宠物下拉与「宠物大小」标签间距 +10px（原 0px 挤贴，用户目验驱动微调，见 §十七）；**§十八为 2026-08-29 七次新增**：卸载应用不自动清理接入插件——README 卸载插件节 + 设置页接入管理卡各加提示（用户问询驱动，见 §十八）；**§十九为 2026-08-29 八次新增**：设置页最底部新增"版本"区块（h2 + 版本号小字，用户目验驱动，见 §十九）；**§二十为 2026-08-30 九次新增**：接入管理卡补统计源状态行 + Token 页被动读取脚注（**已实施同日**，见 §二十）；**§二十一为 2026-08-30 十次新增**：品牌名显示层 "opencode" → "OpenCode" 统一（**已实施同日**，见 §二十一）；**§二十二为 2026-08-30 十一次新增**：exec 例程含中文命令保存即闪退——R3 警告日志按字节切片越界 panic（根因已定位 + 修复方案已与用户对齐，**同日实施完毕**，见 §二十二）；**§二十三为 2026-08-30 十二次新增**：exec 例程命令含中文弯引号 → sh 引号不配对执行 failed（§二十二修复验证顺带发现——模板指令不自动同步 command 逼用户手改 + 中文 IME 引号键出弯引号；四处前端加固**同日实施完毕**，见 §二十三）；**§二十四为 2026-08-30 十三次新增**：exec 例程 GUI 启动 PATH 最小集 → 用户级工具 command not found（§二十三验证顺带发现——launchd 最小 PATH × 非交互 `sh -c` 不读 shell 配置；dev 能跑 release 必现的环境盲区；Unix PATH 增广 + hint **同日实施完毕**，见 §二十四）；**§二十五为 2026-08-30 十四次新增**：执行历史批次——分页 50→15 + 快照化三列（`label`/`command`/`executed_command`，迁移 004）+ 分页控件底部居中（方案定稿，经 reviewer subagent 两轮复核 APPROVED WITH NITS，**同日实施完毕**——完整方案、审查记录与实施记录见 `docs/v2/routine-exec.md` Part A，本文件留指针见 §二十五；同会话产物「例程模板注册表」「cwd 缺省行为备查」归档同文档 Part B / 附录）。

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

## 十九、设置页底部版本信息区块（2026-08-29，**已实施**）

> 来源：用户目验反馈（2026-08-29）——想在设置页最下面展示 PulsePet 当前版本。

**形态（用户裁定）**：与其他区块同款分节形态——`h2`「版本」加粗标题 + 另起一行小字版本号（如 `0.2.2`），复用 `panel-settings h2` + `settings-current` 既有样式（**CSS 零改动**）。**版本源**：state 初值 = `package.json` version（版本四件套 lockstep 同步），Tauri 运行时经 `getVersion()`（`@tauri-apps/api/app`，权威源 = tauri.conf.json，即真实打包版本）刷新，非 Tauri 预览/取值失败保持 package.json 回退；i18n 新键 `settings.versionTitle`（zh「版本」/en「Version」）。playwright 实测设置页 h2 序列 …接入管理 → 版本 + 小字 0.2.2。基线 tsc 0 错 / npm 447 原样。

---

## 二十、接入管理卡补统计源状态行 + Token 页被动读取脚注（2026-08-30，**已实施同日**）

> 来源：用户问询（2026-08-30）——"设置页的接入管理是事件接入管理，是否有必要加一个统计接入管理？"同日二轮追加 Token 页底部说明脚注。

**事实口径**：现有接入管理卡 = 事件链管理（hook 安装/卸载/doctor/last_event_at）；统计链无任何 UI——被动发现式读取（opencode.db / CC transcript），无安装物无卸载物，故**不存在对称的"管理"语义**；源状态三态（Ok/Missing/Failed，口径 A′）仅经 Token 页隐性呈现（Failed 横幅 hover / 硬报错文案，Missing 已随口径 A′ 静默）。

**裁定（2026-08-30 讨论定稿）**：不做独立"统计接入管理"区块，也不做控制型开关（开关读取撞 agent-registry §9-7 killswitch 粒度同款问题且无真实诉求）——两个落点：① **现有接入卡内补一行"统计源状态"**（正常 / 未检测到数据〔路径 hover〕/ 异常〔错误摘要〕/ 无统计源〔`StatsSource::None` 形态，与 §7.1 概念自洽〕）：卡语义即"该 agent 与 PulsePet 的连接健康度"，事件链 + 统计链各占一行自然对称；② **Token 页底部脚注**说明统计链被动性质并将状态查看入口导向接入卡（互为闭环）。

**实施落点**：

1. Rust `token_stats.rs`：抽 `probe_source_states()`（遍历 sources_from_agents 逐源只判三态、不跑查询聚合）。**量级利好（2026-08-30 核实）**：`open_checked`（:518）本身就是完整三态判据载体——`detect_db_path` None→Missing（含 legacy 区分）/ Some×open 或 schema 失败→Failed / 成功→Ok；CC 侧 = `cc_projects_dir()` 目录存在性——无需新写判据，只消费既有判据；
2. Rust `integrations/mod.rs`：`integrations_status` 返回体扩展（`IntegrationStatus` 加 `stats_state`/`stats_path` 字段，**复用现有命令不新开 IPC**；Ok 态会真连 db，沿用命令层既有 blocking 纪律）——在 P1 注册表分发框架内加法扩展，非改分支逻辑；
3. 前端 `Settings.tsx`：接入卡加一行状态渲染（hover 路径/错误摘要）；
4. 前端 `TokenStats.tsx`：会话列表区块后、组件根 div 收尾前加脚注，复用 `settings-current` 小字模式；i18n 新键 `token.sourceNote`（zh/en 成对），**文案逐字定稿（2026-08-30 用户逐轮裁定：紧凑版 + 追加状态查看入口句）**：
   - zh：`说明：Token 统计为被动读取——自动发现各 agent 本地产生的用量记录，无需安装，暂不支持在应用内开关或管理；某 agent 未显示数据时，可到设置 → 接入管理查看统计源状态。`
   - en：`Note: token stats are read passively — PulsePet auto-discovers each agent's local usage records. No setup is needed, and sources cannot be toggled in-app. If an agent shows no data, check its source status in Settings → Integrations.`
5. 测试：Rust 钉（每源三态 + `StatsSource::None` 形态"无统计源"）+ V2-TEST-CASES 一条用例 + i18n 键集合完备性（既有测试自动把守）。

**量级评估（2026-08-30）**：约 140~200 行净变动、3~4 个代码文件 + i18n——半天量级小任务（约为 §十八脚注的 6~8 倍、P3 的 1/4），适合作为 P4 接第三家的顺手项（届时新源判据自动进卡）。**对 agent-registry 已实施内容零影响**（2026-08-30 逐项对账）：AGENTS 表/StatsSource enum/双端互钉/N 源编排/MergeAcc/口径 A′ 判据/P1-P3 全部钉子/idle 分流/register_states 均不动；有交集的 `integrations/mod.rs` 与 `Settings.tsx` 均在 registry 建立的查表/派生框架内做加法；`StatsSource::None` 显示"无统计源"正是 registry 为"仅事件链 agent"预留形态（§7.1）的自然呈现。

**关联悬置项**：实施时与 agent-registry.md §9-6（新 agent 是否都进接入管理卡）一并拍板。

**实施记录（2026-08-30）**：已实施（工作区改动，未 commit）。① Rust `token_stats.rs` §20 探测区块：`ProbeState`（Ok/Missing/Failed/NoSource 四态）+ `probe_one`（路径注入，判据复刻 `query_source_rows` 两段式——第二段以 `open_checked` 为 Failed/Ok 判定）+ 生产壳 `probe_spec`；② Rust `integrations/mod.rs`：`StatsSourceStatus` wire 结构（camelCase：state/path/detail）+ `stats_status_of` 转换 + `IntegrationStatus.stats` 字段（4 构造点填 placeholder）+ **status_for 尾部覆盖**（install/uninstall/spawn_status 刷新路径自动携带真值，无需逐命令改）+ `integrations_status` 循环覆盖；③ 前端 `Settings.tsx` 接入卡行（`intg-message` 类复用，CSS 零改动；hover title = 路径 + 原因/错误摘要；`STATS_STATE_KEYS` 查表 + 未知值兜底 statsNone）；④ 前端 `TokenStats.tsx` 底部脚注（`settings-current` 模式）+ `integrations.ts` 类型扩展；⑤ i18n 新键 6 ×zh/en：`integrations.statsRow`（{state} 参数）/ statsOk / statsMissing / statsFailed / statsNone / `token.sourceNote`（文案逐字按前述定稿）。测试：Rust 新钉 3 枚（`s20_probe_opencode_three_states` / `s20_probe_cc_dir_presence_and_none_form` / `s20_probe_schema_error_is_failed_not_missing`——第三枚对照 s14 钉⑤同款 DROP TABLE 构造，钉「探测与 query 判据不漂移」）；V2-TEST-CASES 增 TC-INT-14；integrations.test.ts fixture 补 stats 默认值。验证：cargo test **370 passed + 3 ignored**（367 基线 + 3 新钉）/ `cargo build` 零警告 / npm test **447 passed** 原样全绿（键集合不变）/ `npx tsc --noEmit` 0 错 / `npm run build` 通过。对 agent-registry 已实施内容零影响（AGENTS 表/enum/互钉/编排/钉子均未触碰——probe 纯消费既有判据）。实机目验（TC-INT-14 步骤 3/4）：接入卡状态行与 Token 页脚注随交付自然目验。

---

## 二十一、品牌名显示 "opencode" → "OpenCode" 全显示层统一（2026-08-30，**已实施同日**）

> 来源：用户问询（2026-08-30）——接入管理卡里的 "opencode" 改为 "OpenCode"；二轮裁定"理论上所有地方都需要改"（从两键扩为全显示层）。

**事实口径（2026-08-30 两轮盘点）**：品牌名指代与**技术字面量**必须区分——后者不改：`opencode run` CLI 命令（tasks.tpl.hint 及测试断言）、`opencode.db` 数据库文件名（schemaMismatch 文案指向真实文件）、`opencode_auto` 任务字段名、agent id `"opencode"`（wire 值/注册表主键，两链锁死约定）、shortName "oc"、代码注释（历史注记按惯例不回改）。**id 层全不动，仅显示层**。

**裁定（2026-08-30 二轮）**：所有**用户可见的品牌名指代**统一 "OpenCode"。改动面三类：

1. i18n 值 5 键 ×zh/en 共 10 处：`token.agent.opencode`（Token 页 tab/徽标 title）、`integrations.opencodeDesc`（接入卡名称）、`token.error.legacyStorage`（两处品牌指代）、`token.degraded`（主源名）、`tasks.tpl.title`（模板块标题——不碰例程识别逻辑，识别走 "pulsepet 例程:" 前缀与 `opencode run` 命令串均字面量不变）；
2. Rust `token_stats.rs` legacy-storage 错误消息两处（:525/:918，用户可见——硬报错透传 + 横幅 tooltip）+ 断言两处同步（:1645/:2304 `contains("升级 OpenCode")`——断言行号为 §二十 实施后现状，原 :1567/:2226 随 §20 区块插入漂移 +76；终审观察④更正 2026-08-30）；
3. **`Panel.tsx` 状态芯片品牌化（行为变更）**：原直显 wire id（"opencode"/"claude-code"）→ 查表 `specOf(agent)` + `t(labelKey)`（OpenCode / Claude Code）；task 特例与未知 agent 原名兜底不变（agent-registry §2 兜底口径一致）。

**实施记录（2026-08-30）**：已实施（工作区改动，未 commit）。验证：npm test **447 passed（32 文件）** 原样全绿（键集合不变、无文案值断言）/ `npx tsc --noEmit` 0 错 / cargo test **367 passed + 3 ignored** 零净增全绿（纯文案替换 + 断言同步，无新钉）/ `cargo build` 零警告。en/zh 词典 zh 侧 5 处 + en 侧 5 处；残扫确认 i18n 值与组件渲染层无品牌名 "opencode" 残留（注释除外）。zh/en 品牌名同值（技术名不翻译约定，大小写统一 OpenCode）。

---

## 二十二、exec 例程含中文命令保存即闪退（R3 警告日志字节切片越界，2026-08-30，**已实施同日**）

> 来源：用户实机报告（2026-08-30）——例程页新建「执行命令」例程（OpenCode 模板拼装，命令含中文标题 + 中文指令），点「新建」App 整体闪退，**可稳定复现**；结合 `~/.pulsepet/pulsepet.log` panic 栈 + 源码定位。影响 v0.2.3 release（实测复现）；dev 构建同源码路径理论必现。

**根因（日志 + 源码双证，已定位）**：

- panic 点：`src-tauri/src/action_exec.rs:229`——R3 特殊字符**警告日志行**（`plog!("…special characters…: {:?}", &command[..command.len().min(80)])`）对命令做**按字节**截断；命令含多字节 UTF-8（中文/emoji）且第 80 字节落在字符中间时 → `str::slice_error_fail` panic；
- 触发链路：点「新建」→ `reminders_upsert` → `reminder_scheduler::normalize_input` → `ExecExecutor::validate` → plog! 截断 panic；panic 发生在 WKWebView scheme handler / Tauri IPC 回调内（栈帧 `url_scheme_handler::start_task`），跨 FFI 边界展开即 abort → **整个 App 闪退**（日志有 PANIC 块、无 exit 行）；
- 复现输入逐字吻合：`opencode run --title 'pulsepet 例程: 该喝水啦 💧' '数一下仓库有几个 md 文件'` 的第 80 字节恰落「有」（bytes 78..81）内——日志原文 `end byte index 80 is not a char boundary; it is inside '有' (bytes 78..81 of string)`；
- 讽刺点：R3 警告本来就是给「含非 ASCII 字符的命令」打日志提醒（Windows PowerShell 转义风险，**警告不阻止**，V2-DESIGN R3）——恰是它要警告的输入类（中文/emoji）必崩；
- **数据未入库**：panic 在 DB insert 之前，例程保存失败；修复后需重新新建。

**全量审计（2026-08-30，"彻底修复"依据——结论：唯一病灶一处）**：

| 检查项 | 扫描结果 |
|---|---|
| str 按字节切片 `[..N]` | 全库仅 action_exec.rs:229 对用户输入按长度切；其余切片切点均安全（`opencode_config.rs` 来自 ASCII 标记 `find()` 索引 / `todos.rs` 日期前 10 字节恒 ASCII / `transcript.rs` 换行索引 / `TailBuf` 为 `Vec<u8>` 字节操作） |
| `split_at` / 非边界索引 / 字符串精度截断 `{:.N}` | 零命中（精度格式仅用于浮点数） |
| 命令输出乱码/二进制 | `TailBuf::finish` 用 `from_utf8_lossy`（action_exec.rs:486）——替换 U+FFFD，不 panic |
| 命令含 NUL/控制字符 spawn 失败 | spawn 返回 Err → Failed outcome（Result 化，不 panic） |
| 长度校验口径 | command ≤2000 **字符**、label ≤140 **字符**（`chars().count()`），中文按字算 |
| `normalize_input` / `reminders_upsert` 链 | 全 Result 化，无 unwrap/expect |

**修复方案（2026-08-30 与用户对齐，先记录后实施）**：

1. `action_exec.rs:229` 改**按字符截断**：`command.chars().take(80).collect::<String>()`（日志语义不变）；
2. 对抗性回归测试（表驱动）：精确复现命令（原代码必崩）→ `validate_params` 返回 `Ok`；语料：4 字节 emoji 恰跨第 80 字节 / 组合音符 / 零宽连接符 / RTL / 控制符 / NUL / 恰 2000/2001 个汉字（顺带钉字符口径）→ 全部不 panic 且判定正确；
3. 运行时钉子：子进程输出非法 UTF-8 → tail lossy 回填不 panic（现有测试仅覆盖截断未覆盖编码）；
4. 源码级纪律钉（照 integrations TC-INT-08-5 模式）：exec 模块非测试代码禁 unwrap + 禁按字节切 str，防未来回归。

**裁定（2026-08-30）**：① 维持 R3「警告不阻止」语义——控制字符仍放行，spawn 失败自会记 failed + 执行历史留 `spawn failed: …`（非崩溃面，不升级为校验拒绝）；② 不采用命令处理器全局 `catch_unwind` 兜底（改动面大、与 POC 定位不符；现有防线 = panic hook 落日志 + 命令路径零 panic 纪律 + 本次 exec 对抗钉，三层已足够）。修复后各类输入归宿：中文/emoji/组合字符/RTL → 正常保存 + 日志一行 R3 警告；控制符/NUL → 保存放行，到点 spawn 失败记 failed（进程不崩）；输出乱码 → lossy 显示；超长 → 校验拒绝报错（前端可见）。

**边界诚实口径**：静态审计保证当前代码再无同类崩溃点；测试钉子保证该路径未来不被改坏；但"今后新写出的 panic"无静态手段 100% 杜绝——以三层防线 + 纪律钉兜底（catch_unwind 全局兜底不采用，理由见裁定②）。

**实施记录（2026-08-30）**：已实施（工作区改动，未 commit）。① 修复：`action_exec.rs` validate 的 R3 警告日志截断改**按字符**（`command.chars().take(80).collect::<String>()`，日志语义不变）；② 新钉 4 枚（cargo **374 passed + 3 ignored** = §二十后基线 370 + 4）：`exec_validate_unicode_straddling_byte80_no_panic`（精确复现命令 + 「78 ASCII+中」/「77 ASCII+💧」最小跨界构造 + 全多字节超长——旧代码在此必 panic，断言放行即回归钉）/ `exec_validate_unicode_corpus_no_panic`（对抗语料：预组重音 / 组合音符 / 零宽 / RTL / 制表换行 / NUL / 恰 2000 汉字放行 + 2001 汉字按字符数拒绝——顺带钉 chars 口径）/ `tail_buf_invalid_utf8_lossy`（运行时钉：非法 UTF-8 输出 lossy 不 panic + 多字节字符跨 push 拼回）/ `exec_module_panic_discipline_s22`（源码级纪律钉，照 integrations TC-INT-08-5 模式：exec 非测试代码禁 `.unwrap()`/`.expect(` + 禁病灶形态 `command[..command.len().min(` + 修复形态 `chars().take(80).collect` 必须在）。两项裁定照 §二十二记录执行：维持 R3「警告不阻止」、不采用全局 catch_unwind。验证：`cargo build` 零警告 / npm test **447 passed** 原样（无前端改动）/ `npx tsc --noEmit` 0 错。**用户实机目验（待办）**：重建复现例程（该中文命令）→ 点「新建」保存成功不闪退，日志出现 R3 警告行（预期）而非 PANIC；此前 panic 在入库前，旧尝试未落数据、无需清理。

---

## 二十三、exec 例程命令含中文弯引号 → sh 引号不配对 failed（模板 UX 缺陷链 + 加固，2026-08-30，**已实施同日**）

> 来源：用户实机报告（2026-08-30，§二十二修复验证过程顺带发现）——新建 exec 例程成功（闪退修复生效），但到点执行 failed（exit 2）。

**根因链（已定位，DB 字节级 + 日志双证）**：

1. **模板指令框输入不自动更新 command**（Tasks.tsx 指令 onChange 仅更新 `tplInstruction`，需再点一次「OpenCode 例程」按钮才重拼；`--auto` checkbox 有同步逻辑而指令没有）→ 用户填完指令后 command 仍为 `''`，只能**手动进 command 文本框改**；
2. 手改时**中文输入法的引号键产出弯引号**：用户输入环境实测按引号键出 `‘’“”`（用户同一会话消息即含 U+201C/U+201D）。字节级对账：例程 #78 存储命令 `opencode run --title 'pulsepet 例程: 该喝水啦 💧’ '统计一下当前项目有几个MD文档'` 与 `buildOpencodeCommand` 应有输出**唯一差异 = 标题收引号位（pos 41）ASCII `'` 被 `’`（U+2019）顶替**，其余字节（空格/指令引号）与模板输出逐位一致——即模板拼装函数无误， substitutions 发生在 textarea 编辑环节；
3. sh 收到不配对引号 → `unexpected EOF while looking for matching '` → exit 2 → 例程 failed（执行历史正确落库：log#63 `failed|2`，output_tail 含 sh 报错——失败呈现链路工作正常）。

**字节级证据**：`action_params` 中引号位谱 `21:'(ASCII) 41:’(U+2019) 43:' 59:'`；`label` 干净（`该喝水啦 💧` 无弯引号）；该例程为全新创建（无编辑历史路径）；`buildOpencodeCommand`/`shellQuote` 逻辑复核无误（恒产 ASCII 引号）。

**加固方案（2026-08-30 与用户对齐，四处小改动，全前端，Rust 零改动）**：

1. **指令输入自动同步进 command**：模板指令框 onChange 时，若 command 为模板拼装（含 `opencode run`，与既有 `--auto` checkbox 同款启发式）→ 自动 `buildOpencodeCommand` 重拼——常规路径消灭手改 command 的需求（根因①）；
2. **弯引号检测 + 一键修正**：command 含 `‘’“”` 时表单警示行（「命令含中文弯引号，shell 无法识别」）+「一键修正」按钮（`‘’`→`'`、`“”`→`"`，修正后仍可再编辑）；**不阻止保存**（与 R3「警告不阻止」口径一致）；
3. **模板拼装规范化**：`buildOpencodeCommand` 对任务名/指令先做弯引号→ASCII 归一再 `shellQuote`（防任务名带 IME 弯引号进入标题）；
4. i18n 新键 zh/en 成对（警示行 + 修正按钮文案，键集合完备性测试自动把守）+ `reminders.test.ts` 钉子（含弯引号输入 → 输出全 ASCII 且 `shellQuote` 转义正确）。

**口径**：Rust 不动（R3 警告已覆盖弯引号类、失败落历史行为正确）；弯引号修正仅替 `‘’“”` 四字符，不动其他全角标点（保守最小替换）；用户当前例程 #78 的即时解法 = 手改该字符为英文引号（不等新代码）。

**实施记录（2026-08-30）**：已实施（工作区改动，未 commit；Rust 零改动照口径）。① `reminders.ts`：新增 `normalizeSmartQuotes`（`‘’`→`'`、`“”`→`"`，保守最小替换）+ `hasSmartQuotes`；`buildOpencodeCommand` 对任务名/指令先归一再 `shellQuote`（拼出命令恒 ASCII 结构引号）；② `Tasks.tsx` 三处同步：模板指令框 onChange 自动重拼 command（含 `opencode run` 启发式，与既有 `--auto` checkbox 同款；消灭"填完指令手改 command"的事故入口）+ **实施中顺带扩展**：任务名 onChange 同款重拼（改名后同样无需手改，启发式与目标一致）；command 含弯引号时表单警示行（`task-danger-hint` 危险色，R3「警告不阻止」口径）+「一键修正为英文引号」按钮（仅替 `‘’“”` 四字符，修正后仍可再编辑）；③ `global.css`：`.task-smartquote-row`（flex 同行 + seg 按钮缩小）一条；④ i18n 新键 2 ×zh/en：`tasks.tpl.smartQuoteWarn` / `tasks.tpl.smartQuoteFix`（键集合完备性测试自动把守）。测试：`reminders.test.ts` 新钉 1 枚（实测病灶形态「任务名收尾 `’`」→ `shellQuote` 转义输出逐字断言 + 指令双弯引号归一 + 四字符映射/检测纯函数钉）；基线 npm test **448 passed**（447 + 1）/ `npx tsc --noEmit` 0 错 / `npm run build` 通过 / `npm run tauri build` 产物双 bundle 正常。**用户实机目验（待办）**：替换新 build 后——编辑例程 #78 手动把 `’` 敲回弯引号（复现警示）→ 警示行出现 → 点「一键修正」→ 保存试一试执行成功；或直接重建例程全程不再触碰 command 文本框（指令/任务名输入即自动同步）。

**修订（2026-08-30，用户质询驱动）**：用户问"不会是把所有单引号都机械替换吧"——复查确认 ASCII 引号从未被替换（内容 ASCII `'` 走 `shellQuote` 标准转义 `'\''`，保留内容而非替换），但暴露一处设计过度与一处文案失准，已修：① **撤销方案第 3 点（拼装内容归一）**——弯引号在单引号串内是合法字面量，`shellQuote` 包裹后内容弯引号本就无害，拼装归一属无收益的内容改写（如任务名 `他说’你好’` 会被改字面）；`buildOpencodeCommand` 回归内容原样保留，结构安全仍由恒产 ASCII 结构引号 + `shellQuote` 保证；`normalizeSmartQuotes` 仅保留给一键修正按钮（语义明示为"把弯引号当作引号"——修复误替场景；确为内容时替换后最坏是字面变化/词拼接，不比误替更坏）；② **警示文案去绝对化**：原「shell 无法识别，会导致执行失败」对内容弯引号不成立，改「若为输入法误替英文引号会导致执行失败；确为内容可忽略」+ 按钮文案「把弯引号当作引号修正」；③ 测试钉同步改写（弯引号内容原样保留逐字断言 + `shellQuote` 转义钉 + 归一/检测钉），基线 npm test **448** / tsc 0 错 / `npm run tauri build` 重新打包。

---

## 二十四、exec 例程 GUI 启动 PATH 最小集 → 用户级工具 command not found（2026-08-30，**已实施同日**）

> 来源：用户实机报告（2026-08-30，§二十三修复验证过程发现）——弯引号已修复（命令全 ASCII，R3 警告行可见完整命令），执行改报 **exit 127**：`sh: opencode: command not found`（action_logs log#64）。

**根因（已定位，环境盲区）**：

- opencode 实际位于 `~/.npm-global/bin`，PATH 在 **`~/.zshrc`** export（仅**交互式** shell 读取）；
- PulsePet release 从 Dock/Finder/`open` 启动继承 **launchd 最小 PATH**（`/usr/bin:/bin:/usr/sbin:/sbin`），exec 为非登录非交互 `sh -c`——任何 shell 配置文件都不会执行 → 用户级工具找不到；
- **判定标准 = 进程树祖先是否终端**：与 .app 安装位置无关（`/Applications` 与 bundle 同样失败）；`npm run tauri dev` 从终端启动继承终端完整 PATH，**故 TC-M4-08 首日实机验证（dev 语境）通过而 release 必现**——测试用例未覆盖 GUI 启动场景；
- 排除「登录壳 `$SHELL -l -c`」方案：`zsh -l -c` 非交互不读 `.zshrc`（本机 PATH 恰在其中），且引入 profile 副作用/慢启动。

**Windows 侧评估（不动代码，挂观察项）**：Explorer/开始菜单启动的 GUI 进程**继承注册表**用户/系统 PATH——主流安装器（Node/npm、winget、scoop）均写入注册表，`%APPDATA%\npm` 天然可见，主流场景无此问题；残余风险仅「PATH 只写在 PowerShell `$PROFILE`」的少数手动配置（spawn 为 `-NoProfile` 不读）——按 TC-M4-18 口径挂观察项，Windows 实机批次顺带验证 `npm i -g` 场景。

**修复方案（2026-08-30 与用户对齐，B+C）**：

1. **B. spawn 时 PATH 增广（主修复，`action_exec.rs`，仅 Unix）**：新增纯函数 `augmented_path(base, home)`——在现有 PATH 基础上**追加**（去重、保序）常见用户 bin 目录（`~/.npm-global/bin`、`/opt/homebrew/bin`、`/usr/local/bin`、`~/.local/bin`、`~/.opencode/bin`、`~/.cargo/bin`、`~/bin`）；spawn 前 `cmd.env("PATH", …)`。只增不删不改序——系统路径优先级不变，对已在 PATH 的命令零影响；目录清单外仍需绝对路径；
2. **C. 表单 hint（兜底说明）**：command 框下加一行小字（i18n `tasks.form.commandHint` zh/en）：GUI 启动的 App PATH 有限，清单外工具请用绝对路径或命令前 `export PATH=…`；
3. 测试：`augmented_path` 单测（HOME 展开 / 去重 / 保序，`#[cfg(unix)]` 门）+ 验证链 cargo / npm / tsc / build。

**口径**：Windows 不动代码（观察项见上）；R3 警告行为不受影响；hint 文案与 §二十三 弯引号警示并存互不干扰。

**实施记录（2026-08-30）**：已实施（工作区改动，未 commit）。① `action_exec.rs`：新增 `EXTRA_PATH_ABS`（/opt/homebrew/bin、/usr/local/bin、/home/linuxbrew/.linuxbrew/bin†）+ `EXTRA_PATH_HOME`（.npm-global/bin、.local/bin、.opencode/bin、.cargo/bin、bin）+ 纯函数 `augmented_path(base, home)`（split ':' → 追加去重 → 保序 join；空段容错）——均 `#[cfg(unix)]` 门控，Windows 编译零涉及；`exec_run_with_timeout` spawn 前读当前进程 `PATH`/`HOME` 增广后 `cmd.env("PATH", …)`（只增不删，系统优先级不变；env 读取失败静默跳过 = 行为回退原样，零 unwrap 符合 §二十二纪律钉）；② hint：i18n 新键 `tasks.form.commandHint` zh/en（command 框下 `.reminder-hint` 小字，与 §二十三弯引号警示并存互不干扰）；③ 测试：`augmented_path_appends_user_dirs_dedup_order`（保序 + HOME 展开逐字断言 / 去重 / 尾随冒号空段容错，内层 `#[cfg(unix)]` 块照既有风格）。验证：cargo test **375 passed + 3 ignored**（§二十二后基线 374 + 1）/ `cargo build` 零警告 / npm test **448 passed** 原样 / `npx tsc --noEmit` 0 错 / `npm run tauri build` 双 bundle 正常。**用户实机目验（待办）**：退出旧 App → 替换新 build → 从 Dock/Finder 启动 → 例程「试一试」执行成功（不再 127）；Token 页应出现「pulsepet 例程:」会话（spawn 的 opencode 加载 hook，宠物细粒度状态随动）——此即 TC-M4-08 在 **GUI 启动语境**下的补验。

> † 修订（2026-08-30，Committer P3-8 处置）：`EXTRA_PATH_ABS` 原枚举仅前两者，linuxbrew 路径为审查后增补（测试断言同步），见 §二十三「Committer 审查」块 P3 处置。

**备忘（Committer P3-9，2026-08-30）**：cwd 表单 label「需填写绝对路径」为 UI 建议，Rust validate 仍接受存在的相对路径（action_exec.rs 只拦「存在但非目录」）——UI 建议严于后端校验系有意口径（绝对路径为最佳实践提示，后端保留宽容），非矛盾。

**二轮微调（2026-08-30，用户目验驱动，5 项，已实施同日）**：

1. **警示文案加 `❗` 前缀**（`tasks.tpl.smartQuoteWarn` zh/en 两 value，key 不变）——与警示行 danger 红色语义呼应，更醒目；
2. **修正按钮上色**：`seg` → `seg primary`（accent 色，复用「一键填充」/「新建」同款既有样式，零新增 CSS；不用红色——红在本行是"问题"语义，修正按钮是"解决动作"）；
3. **exec 任务名上移到执行命令块最顶**（动作类型行之后、opencode 模板块之前）——拆 notify/exec 共享行：exec 独立渲染任务名行（handler 含 §二十三 自动重拼逻辑不变），notify 保持「类型 + 文案」行原位与顺序不变；
4. **exec 任务名默认值：该喝水啦 💧 → 任务名示例**——新 i18n 键 `tasks.form.nameDefault`（zh `任务名示例` / en `Example task`）；仅 exec 语境：`setActionType("exec")` 时 label 若仍为模板默认文案（复用 `allTemplateLabels()` 判定）→ 置为 nameDefault；exec 切回 notify 时若 label == nameDefault（zh/en 双语判定）→ 对称恢复 notify 模板默认文案；编辑已有例程（startEdit）不受影响；notify 表单默认文案保持「该喝水啦 💧」不变（裁定）；
5. **cwd label 补绝对路径要求**：`tasks.form.cwd` zh `工作目录（可选）` → `工作目录（可选，需填写绝对路径）` / en 同步（zh/en 成对；与 §二十四 PATH 修复呼应——绝对路径无歧义且不受系统「智能引号」影响）。

**实施记录**：见下「二轮微调实施记录」。

**Committer 审查（2026-08-30，§二十二~§二十四 + 二轮微调整体）**：**APPROVED WITH NITS**（P0/P1/P2 均无，10 条 P3 备忘）。文档↔代码一致性逐条核对一致（重点项「拼装内容归一已撤销」与代码逐字吻合）；6 枚测试钉确认为真实回归钉（3 条旧代码必 panic）；测试三件套在主会话独立复跑（cargo 375+3 / npm 448 / tsc 0）与基线一致。**P3 处置（同日）**：
- 已修 5 条：fallback 统一（`onLabelInput`/指令 onChange/`--auto` checkbox 三处 `|| "task"` 硬编码 → `trim() || t("tasks.form.namePlaceholder")`，与模板按钮同口径）；`normalizeSmartQuotes` 注释口径修正（承认内容弯引号修正后可能造成新的不配对，删「不比误替更坏」的乐观表述）；commandHint 文案跨平台中性化（去 Dock/Finder / export PATH 的 macOS 专属表述，zh/en）；`EXTRA_PATH_ABS` 补 `/home/linuxbrew/.linuxbrew/bin`（测试断言同步）；新测试去重复的 `shellQuote` 断言；
- 已修 1 条（本轮审查回应）：二轮微调块「实施记录：（待实施）」占位残留与其后实施记录矛盾；
- 备忘口径补录 1 条：cwd UI 建议严于后端校验系有意口径（见 §二十四备忘）；
- 暂缓 3 条（记录不修）：`tplSeeded` 结构化标志替代 `includes("opencode run")` 子串探测（既有既定模式，未来重构项）；自定义 label 恰等「任务名示例」切换误重置（需新增 labelDirty 态，边界极小）；纪律钉源码扫描的固有局限（字面量残留假通过 / split 位置敏感——文档已裁定接受）。

**二轮微调实施记录（2026-08-30）**：5 项全部落地（工作区改动，未 commit）。① `i18n.ts`：`smartQuoteWarn` zh/en 加 `❗` 前缀；② `Tasks.tsx` 修正按钮 `seg` → `seg primary`；③ `Tasks.tsx` 任务名行拆分——exec 独立任务名行移至动作类型行之后（模板块之前），notify 保持「类型 + 文案」行原位（模板快捷块顺序不变），输入 handler 抽为 `onLabelInput` 复用（exec 自动重拼逻辑不变，仍在 `form.kind !== "todo"` 片段内）；④ `setActionType` 对称默认值：切 exec 时 label 仍为模板默认文案（`allTemplateLabels()` 判定）→ 置 `t("tasks.form.nameDefault")`（zh 任务名示例 / en Example task）；切回 notify 时 label == nameDefault（zh/en 双语判定）→ 恢复 `t(TEMPLATE_KEYS[0])`；⑤ `tasks.form.cwd` zh/en 补绝对路径要求。**附带发现并修复**：`.task-tpl-row` 的「OpenCode 例程」填充按钮 `seg primary` 为死类——`.primary` accent 样式原本只挂在 `.task-form-actions` / `.reminder-form-actions` 容器下，M4 起填充按钮从未渲染过 accent，新增 `.task-smartquote-row` / `.task-tpl-row` 两处 `.seg.primary` 规则一并启用（hover 走 accent-ink 同款）。验证：npm test **448 passed** / `npx tsc --noEmit` 0 错 / `npm run tauri build` 双 bundle 正常。目验点：警示行 ❗ + accent 修正按钮 + 填充按钮 accent；新建 exec 例程任务名预填「任务名示例」且位于块顶，指令/任务名输入命令自动重拼；切回 notify 文案恢复「该喝水啦 💧」。

---

## 二十五、执行历史批次：分页 50→15 + 快照化三列 + 分页控件移位（2026-08-30，**已实施同日**）

> 来源：用户会话（2026-08-30）。**完整方案（背景 / 四项方案 / 口径 / 文件级实施清单 / Reviewer 审查-自审-复核记录）已整体迁至 `docs/v2/routine-exec.md` Part A**——本条目留指针防断链；审查记录中的本文件行号以迁移前为准。同会话产物「例程模板注册表（Part B，**已实施同日**）」「exec 的 cwd 缺省行为备查（附录）」与「执行上下文增补批次（Part C：cwd 快照列 + executed_command 删列 + 命令单展示，**已实施同日**）」也归档于该文档。

要点四项：① 分页 50→15 + 常量收归 `ACTION_LOG_PAGE_SIZE` 单点；② 分页控件（页码 + 上一页/下一页）移至历史块底部居中，筛选下拉不动；③ `action_logs` 迁移 004 新增 3 快照列 `label` / `command` / `executed_command`——执行历史 = 执行时点任务内容快照（ID 关联当前配置的方案被用户否决）；④ 前端全读快照：行内任务名 + 展开区「存储命令（当时配置）」「实际执行命令」双块，skipped →「—（未执行）」、旧行 →「—（未记录）」。

状态：方案经 reviewer subagent 两轮（CHANGES REQUIRED → 修订 → 复核 APPROVED WITH NITS）后用户批准，**2026-08-30 同日实施完毕**（TDD 全程先红后绿）：迁移 004 + db.rs 四处、`ACTION_LOG_PAGE_SIZE` 15 收归单点、`ActionLog` 三快照列 + `SkippedRule` 数据管线 + `command_from_params` 同源助手、前端底部分页 + 行内任务名 + 双命令块（渲染判定照口径）；**验证 cargo 377 passed + 3 ignored（+2 新钉）/ npm 448 / tsc 0**；实施记录与偏差见 routine-exec.md Part A 末；P3-6（空历史隐藏分页容器）悬置未动；用户目验待办。

---

## 二十六、Token 时序图 tooltip 三行数值右对齐（2026-08-31，**已实施同日**）

> 来源：用户会话（2026-08-31）——柱图 tooltip 悬浮行对齐原则微调（视觉打磨，无逻辑变化）。

**现状与裁定**：tooltip 三行（cache read → input → output，`TOOLTIP_ROW_ORDER` 钉序）由 `token.chart.tipRow` 单模板串渲染成**单个文本节点**（zh `"{name}：{n}（{pct}%）"` / en `"{name}: {n} ({pct}%)"`），三行整体左对齐、数字右缘参差。用户裁定：**标签列保持左对齐不动；数字列右对齐**（右缘对齐同一竖线）；**百分比不参与对齐**，紧跟数字（`（` 位置随数字列右缘自然对齐）。标题行（`…：共 …`）不参与。

**方案（4 文件，纯展示层，Rust 零涉及）**：

1. **i18n 拆键**：`token.chart.tipRow` 清退 → `token.chart.tipRowName`（zh `"{name}："` / en `"{name}: "`）+ `token.chart.tipRowPct`（zh `"（{pct}%）"` / en `" ({pct}%)"`）；数字本身不经 i18n（沿用 `toLocaleString()`）；拼接结果与旧模板逐字相同。
2. **渲染**（`TokenStats.tsx`）：三行外裹 `.chart-tip-rows` 网格容器（`display: grid; grid-template-columns: max-content ×3`），每行平铺 3 个 span（name / `.chart-tip-num` / pct），数字列 `text-align: right`——**必须共享网格列宽**，跨行右缘才能对齐（每行独立 flex 无法对齐）。
3. **空格塌缩风险（实施前审查发现）**：grid item 会被块化，CSS 空白折叠规则移除行首/行尾空格（`.chart-tip` 的 `nowrap` 继承仍是折叠型）→ en 模板中的分隔空格会消失（`input:5,947,470(2.0%)`）。对策：`.chart-tip-rows { white-space: pre }`——空格保留、分隔符逐字还原；tooltip 本就不换行，`pre` 无副作用；zh 模板全角标点不可折叠、零影响。
4. **测试**（`i18n.test.ts`）：m3Keys 清单 `tipRow` 换两新键 + 新增清退/钉值 `it`（仿 `todayUnavailable`/`noAgents`/`costOpencodeOnly` 先例）——钉 zh 全角无空格、en 半角带空格的分隔符差异，即空格塌缩的守卫钉。

**效果示例**（数字带千分位，`toLocaleString()`）：

```text
改前（整体左对齐）            改后（数字列右对齐）
cache read：297,424,454（97.9%）    cache read：297,424,454（97.9%）
input：5,947,470（2.0%）            input：       5,947,470（2.0%）
output：532,386（0.2%）             output：        532,386（0.2%）
```

**关联面核查（已确认无影响）**：`t()` 为简单 `{(\w+)}` 正则替换（全角标点透传）；`nameOf` 本地字面量表不翻译；`tipRow` 模板值无测试钉住（仅键存在性）；`token-chart.test.ts:223` 只钉顺序常量不钉渲染；`.chart-tip-row` 仅 global.css + TokenStats.tsx 两处引用；tooltip 定位逻辑不动、字符集相同（典型数据下宽度不变；极端数据下 grid 三列 max-content 之和可略超旧单行最大行宽，亚像素级——committer P3-2 修订）；mockups/a.html 为静态设计稿不动。

**实施记录（2026-08-31）**：已实施（工作区改动，未 commit）。① `i18n.ts`：`tipRow` zh/en 两行清退，`tipRowName`/`tipRowPct` zh/en 四行新增（zh `"{name}："` / `"（{pct}%）"`、en `"{name}: "` / `" ({pct}%)"`）；② `TokenStats.tsx`：tooltip 三行改 `.chart-tip-rows` 网格容器、每行 `Fragment` 平铺 name / `.chart-tip-num` / pct 三 span，导入补 `Fragment`；③ `global.css`：`.chart-tip-row` 规则替换为 `.chart-tip-rows`（grid 三列 max-content + `white-space: pre` + `color: var(--ink-soft)`）与 `.chart-tip-num`（`text-align: right`）；④ `i18n.test.ts`：m3Keys 清单 `tipRow` → 两新键 + 新增清退/钉值 `it`（en 带空格钉 = 塌缩守卫）。验证：npm test **464 passed**（基线 463 + 1 新钉，33 文件）/ `npx tsc --noEmit` 0 错；Rust 零涉及（cargo 不涉）。用户目验 = 悬停柱图三行数字右缘对齐、en 语言下冒号后/括号前空格保留。

**Committer 审查（2026-08-31，§二十六）**：**APPROVED**（P0/P1/P2 均无，5 条 P3 备忘）。核心技术点逐项复核成立——Fragment 不产 DOM 层级、9 span 平铺共享网格列宽 + `text-align: right` 跨行对齐右缘；`pre` 防块化空格折叠推理成立（模板无换行符、zh 全角标点不受影响）；zh/en 拼接与旧模板逐字相同；旧引用清退干净（`.chart-tip-row` 零残留、`tipRow` 仅剩测试负向断言）；文档↔代码逐条核对相符（含 464=463+1 与 33 测试文件数）；测试钉具真实防护力（回退任一处会红）。**P3 处置（同日）**：已修 2——P3-2 文档「总宽不变」表述软化（极端数据下 grid 列宽之和可略超旧行宽，亚像素级）；P3-5 CSS 注释补「子 span 须各自独占一行」（同行排列时隔开空格会经 `pre` 保留成匿名 grid item 破坏三列）；记录在案 3——P3-1 工作区 untracked `pulse-pet/images/`（08-20~24 素材，与本批无关）去留待用户裁定，**提交本批时须只 stage 上述 5 文件**；P3-3 en 空格钉防护面为「删空格绕过塌缩」而非「删 CSS pre」（无 CSS 测试基建，按仓库惯例接受）；P3-4 m3Keys 测试名仍冠「v2 M3」属既有「含实施细项微调键」混收惯例（不动）。

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
- [x] **§十九 设置页底部版本信息区块**：✅ 已实施 2026-08-29（同日）——`Settings.tsx` 版本分节（h2「版本」+ 小字版本号；getVersion 权威 + package.json 回退）+ i18n `settings.versionTitle` zh/en，CSS 零改动；playwright 实测；基线 tsc 0 错 / npm 447 原样；目验 = 设置页最底部见「版本 / 0.2.2」
- [x] **§二十二 exec 例程含中文命令保存即闪退（R3 警告日志字节切片越界）**：✅ 已实施 2026-08-30（同日定位 + 记录 + 实施）——`action_exec.rs` R3 警告日志截断改按字符（原按字节切，第 80 字节落多字节字符内 → panic 经 IPC 回调跨 FFI abort 闪退）+ 对抗钉 4 枚（精确复现跨界 / Unicode 语料 + 字符口径 / 输出非法 UTF-8 lossy / 源码级纪律钉）；裁定维持 R3「警告不阻止」+ 不采用 catch_unwind 全局兜底。基线 cargo **374 passed + 3 ignored**（370 + 4 新钉）/ npm 447 原样 / tsc 0 错 / `cargo build` 零警告。完整留痕：§二十二；用户实机目验 = 重建该中文命令例程保存成功、日志 R3 警告行而非 PANIC
- [x] **§二十三 exec 例程命令含中文弯引号 → sh 引号不配对 failed**：✅ 已实施 2026-08-30（同日定位 + 记录 + 实施，含用户质询驱动修订）——`reminders.ts` `normalizeSmartQuotes`/`hasSmartQuotes`（仅供一键修正按钮；**拼装内容归一已撤销**——弯引号在单引号串内是合法字面量，内容原样保留）+ `Tasks.tsx` 指令/任务名输入自动重拼模板 command（含 `opencode run` 启发式，消灭手改入口）+ 弯引号警示行与「把弯引号当作引号修正」按钮（R3 警告不阻止口径、文案去绝对化）+ i18n 2 键 zh/en + CSS 一条；Rust 零改动。基线 npm **448 passed** / tsc 0 错 / build 通过。完整留痕：§二十三（含修订注记）；用户实机目验 = 弯引号警示行出现 → 一键修正 → 试一试执行成功
- [x] **§二十四 exec 例程 GUI 启动 PATH 最小集 → command not found**：✅ 已实施 2026-08-30（同日定位 + 记录 + 实施）——`action_exec.rs` Unix 侧 `augmented_path` spawn 前向 PATH 追加常见用户 bin 目录（只增不删不改序；Windows 不动挂观察项）+ i18n `tasks.form.commandHint` zh/en 表单 hint；含「dev 能跑 release 必现」盲区根因（TC-M4-08 首日验证为 dev 语境）。基线 cargo **375 passed + 3 ignored**（+1 钉）/ npm 448 原样 / tsc 0 错 / build 通过。完整留痕：§二十四；用户实机目验 = GUI 启动后试一试执行成功 + Token 页现「pulsepet 例程:」会话（TC-M4-08 GUI 语境补验）
- [x] **§二十五 执行历史批次（分页 15 + 快照化三列 + 分页控件移位）**：✅ 已实施 2026-08-30（方案定稿 + reviewer 两轮复核 + 用户批准，同日实施，TDD 全程先红后绿）——迁移 004（action_logs +`label`/`command`/`executed_command` 三快照列，SCHEMA_VERSION=4）+ `db.rs` 四处接线 + 新钉（缺列红→绿、旧行三列 NULL）；`ACTION_LOG_PAGE_SIZE` 50→15 收归单点（局部 `PAGE_SIZE` 删除）+ 分页断言 15/15/tail-31 + 第 5 页末页边界钉；快照管线（`SkippedRule`+`action_params`、`collect_due` 两构造点、`persist_skipped` 判定时刻提取、`command_from_params` 同源助手 pub 共用、`start_exec_run` 派发时刻快照）+ 孤儿悬空可读钉 + skipped「executed 恒 None」钉；前端（底部分页居中、行内任务名、展开「存储命令（当时配置）/ 实际执行命令」双块、skipped→未执行 / 旧行→未记录、i18n 4 键 zh/en、CSS 2 类）；文档（V2-DESIGN §4.2/§4.5/§4.7/§4.8 + TC-M4-16/TC-M4-01）。基线 cargo **377 passed + 3 ignored**（375+2 新钉）/ npm **448** 原样 / tsc 0 错。完整留痕：`docs/v2/routine-exec.md` Part A（含 Reviewer 审查-自审-复核全记录与实施记录）；用户目验待办（分页居中 / 任务名 / 双命令 / 删改规则后历史不变 / skipped 与旧行占位）；P3-6 空历史分页显示悬置未动
- [x] **§二十五·Part B 例程模板注册表（routine-exec.md §3）**：✅ 已实施 2026-08-30（方案定稿 + reviewer 两轮（NITS→APPROVED）+ 用户批准，同日实施，TDD 全程）——`routine-templates.ts` 新建（shellQuote 迁入 + opencode/claude-code 两行 + templateOf/matchOf/tplHintKey，11 钉）；`reminders.ts` 导出 `ExecFormState`/`emptyExecState`/`execParamsJson`/`execFromParams`（新格式 `tpl_agent`+`tpl_flags` + 兜底四态 + 旧 `opencode_auto` 读兼容 + matchOf 反推，5 测）+ `validateExecParams` 两键预检；Rust validate 两条宽松校验（+1 钉）；`Tasks.tsx` 模板块泛化（chips 单选/共享指令框/声明式 flags/填充恒可点——空指令禁用处置经用户目验推翻恢复旧行为）+ 三联动点 `matchOf` 化 + **空指令守卫（顺带修复编辑改任务名 clobber 隐患）**；i18n 8 新键 + 4 旧键清退；V2-DESIGN §4.6 重写 + TC-M4-08 泛化 + agent-onboarding checklist 补例程模板行。基线 cargo **378+3** / npm **463** / tsc 0。完整留痕：routine-exec.md §3.7；用户目验待办
- [x] **§二十五·Part C 执行上下文增补（routine-exec.md §4）**：✅ 已实施 2026-08-30（用户目验反馈驱动：双平台确认命令串原样/目录经进程属性生效后，恒同值双展示冗余 + 执行目录不可见；方案定稿过 reviewer 审查与复核 APPROVED，同日实施，TDD 全程）——迁移 005（+cwd 快照列 / DROP executed_command 恒同值冗余列，SCHEMA_VERSION=5，m4b 改版改名 m4c）；`cwd_from_params` pub 助手（只 trim 判空存原串）+ 新钉；insert 参数位 executed→cwd、SELECT 同位换列；前端「命令（当时）」单块 +「工作目录（当时）」块（notExecuted 三元整删）；i18n −3+3；**真实 v4 库副本 migrate 演练 ok**（v4→v5、11 行全保留、id72/73 command 快照完整）。基线 cargo **379+4 ignored** / npm **463** / tsc 0。完整留痕：routine-exec.md §4.6-4.7；用户目验待办
- [x] **§二十六 Token 时序图 tooltip 三行数值右对齐**：✅ 已实施 2026-08-31（视觉打磨微批，方案核查（含空格塌缩风险前置发现）+ 用户批准，同日实施）——i18n `tipRow` 单模板串拆 `tipRowName`/`tipRowPct` 两键（en 分隔空格）+ `TokenStats.tsx` 三行改共享网格平铺 3 span（数字列 `text-align: right` 跨行对齐右缘）+ `global.css` `.chart-tip-rows`（grid + `white-space: pre` 防 grid item 块化空格折叠）；i18n 新钉 1（清退 + zh/en 分隔符钉值）。基线 npm **464**（463+1）/ tsc 0 错；Rust 零涉及。完整留痕：§二十六；用户目验 = 悬停柱图数字右缘对齐、en 空格保留
