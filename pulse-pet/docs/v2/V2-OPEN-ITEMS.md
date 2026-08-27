# PulsePet v2 未完成事项清单（Open Items）

> 生成：2026-08-27（v2 M6 合入 develop 后）
> 来源：Windows 实机使用反馈（[issue #19](https://github.com/yq3/lab/issues/19) / [issue #20](https://github.com/yq3/lab/issues/20)）+ 源码级诊断（2026-08-27，诊断结论已分别留痕于两 issue）
> 性质：两项 **Windows 特有缺陷**，根因已定位、修复方案已裁定（R1-R5，见 [§三](#三修复任务清单r1r5统一实施)）。
> **状态（2026-08-27 闭环）**：R1-R5 **已修复并随 `pulse-pet-v0.2.1` 发布**——实施 commit `6f9e0be`（R1-R4）/ `9e609d6`（R5）/ `acc12b3`（本文件）/ `f2cf13e`（版本 bump 四件套），tag `pulse-pet-v0.2.1`（CI run 33071206433 双矩阵 success，安装包挂 draft Release）。测试基线全绿（`cargo test` 320+3 钉子 / `npm test` 409 / `tsc --noEmit`），committer 评审 APPROVED（P0/P1=0，三条 P3 加固已落地）。**Windows release 实机三场景验证通过（2026-08-27，v0.2.1，§四）**，#19 / #20 可闭环。
> 共同背景：与 v1 issue #9 同源——Windows 上 WebView2 环境创建异步、主线程泵消息期间页面已加载执行（GUI 子系统 + 控制台子进程交互）的时序盲区；v1 里程碑"Windows 实机验证后移"的欠账在 v2 实机使用中集中显性化。macOS 开发机均无法复现。
> 构成说明（2026-08-27 补充）：§一~§四为 issue #19/#20 专项记录（**已闭环**）；§五起为 **v2 六里程碑（M1~M6）工作流检查点遗留事项汇总**（supervised-coding 2026-08-27 归档，来源 `.opencode/workflows/task-pulsepet-v2-m1~m6.md`），清偿后回写勾选并注来源任务 ID 与日期。

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

| # | 来源 | 事项 | 位置与修法建议 |
|---|---|---|---|
| 1 | v2-m2 P3-5 | AtlasData Clone derive 死代码 | atlas.rs——动 atlas.rs 时顺手删 |
| 2 | v2-m2 P3-6 | Settings notice 重复计算 | 微优化 |
| 3 | v2-m2 P3-7 | 禁用语汇四套不一致 | CSS/微打磨轮统一 |
| 4 | v2-m3 P3-1 | idle 汇报「 · 今日 X」追加段在 220px 气泡被单行省略截断不可见 | 气泡文案/CSS 打磨轮（两行或精简） |
| 5 | v2-m3 P3-5 | plugin-hook.test.ts:763 注释草稿痕迹 | 删 |
| 6 | v2-m4 P3① | logging.rs `ends_with("x"×64)` 残余竞态（并行 plog! 旧句柄 .old 尾部污染偶发） | 测试专用助手持全局 slot 锁内轮转，或删 ends_with 只留 len>= |
| 7 | v2-m4 P3② | action_exec.rs:622-635 注释块复制粘贴重复（**注**：v0.2.1 R2 已动该文件加 creation_flags，此项或已顺手消化——打磨轮核对后勾销） | 删 |
| 8 | v2-m5 P3-1 | transcript.rs:208-210 注释块重复 | 删一行 |
| 9 | v2-m5 P3-2 | transcript.rs:590-624 `assert_ne!(本地日, UTC日)` 硬假设非零时区偏移（TZ=UTC 环境会红） | 去 assert_ne 或 TZ 注入，保留 oracle 对账 |
| 10 | v2-m5 P3-3 | TokenStats.tsx:521 symmetricToggle 注释「模型/agent 共用」过时（R2 后仅模型用） | 改注释 |
| 11 | v2-m5 P3-4 | token_stats.rs:709-712 TranscriptCache 全目录解析在 Mutex 持有期执行 | 观察项：文件体量增长时改锁内判定+锁外解析 |
| 12 | v2-m6 P3-① | PetMenu clamp effect deps 仅 `[pos]`、首帧估值 130 不含 agent 分布子行——双 agent 日菜单增高 ~14px 贴下缘时底项被裁 | deps 加 todayToken 或 ResizeObserver，或估值 130→146 |
| 13 | OBS-SIGTERM | 外部 kill 不产生 `exit` 日志行、runtime token/endpoint 残留不清理（v1 既有） | 主去向=V1-OPEN-ITEMS §八维护版清单；退出钩子补 SIGTERM 路径 |

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

## 附：清偿记录

（清偿后回写：日期 + 来源任务 ID + 去向。已有示例：§6.2-5 TC-M4-18 核心面 2026-08-27 随 v0.2.1 §四场景 2 验证；§7-7 或已随 v0.2.1 R2 顺手消化，打磨轮核对）

- [x] **§8-1 文档滞后（v2-m6 P3-②）**：✅ 已清偿 2026-08-27（文档维护轮，supervised-coding 执行）——V2-DESIGN §6.0/§6.2/§6.3/§6.4 共 7 处 + V2-TEST-CASES TC-M6-04/TC-M6-06-4 共 4 处对齐"右键菜单子行"口径，修订注记引用 §3.4 后裁定；改动在工作区待入库（与 V2-OPEN-ITEMS 本文件 §五~§十 一并提交）
