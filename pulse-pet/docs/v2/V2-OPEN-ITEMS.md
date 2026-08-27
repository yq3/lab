# PulsePet v2 未完成事项清单（Open Items）

> 生成：2026-08-27（v2 M6 合入 develop 后）
> 来源：Windows 实机使用反馈（[issue #19](https://github.com/yq3/lab/issues/19) / [issue #20](https://github.com/yq3/lab/issues/20)）+ 源码级诊断（2026-08-27，诊断结论已分别留痕于两 issue）
> 性质：两项 **Windows 特有缺陷**，根因已定位、修复方案已裁定（R1-R5，见 [§三](#三修复任务清单r1r5统一实施)）。
> **状态（2026-08-27 闭环）**：R1-R5 **已修复并随 `pulse-pet-v0.2.1` 发布**——实施 commit `6f9e0be`（R1-R4）/ `9e609d6`（R5）/ `acc12b3`（本文件）/ `f2cf13e`（版本 bump 四件套），tag `pulse-pet-v0.2.1`（CI run 33071206433 双矩阵 success，安装包挂 draft Release）。测试基线全绿（`cargo test` 320+3 钉子 / `npm test` 409 / `tsc --noEmit`），committer 评审 APPROVED（P0/P1=0，三条 P3 加固已落地）。**Windows release 实机三场景验证通过（2026-08-27，v0.2.1，§四）**，#19 / #20 可闭环。
> 共同背景：与 v1 issue #9 同源——Windows 上 WebView2 环境创建异步、主线程泵消息期间页面已加载执行（GUI 子系统 + 控制台子进程交互）的时序盲区；v1 里程碑"Windows 实机验证后移"的欠账在 v2 实机使用中集中显性化。macOS 开发机均无法复现。

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
