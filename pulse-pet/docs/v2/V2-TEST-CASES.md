# PulsePet v2 测试用例

> 依据：`V2-DESIGN.md`（v2 技术方案，M1~M6 已全部定稿）、`V2-SCOPE.md`（v2 范围与裁定）；v1 `DESIGN.md` / `TEST-CASES.md` 为既有基线与回归参照。
> 用途：v2 各里程碑（M1-M6）与各里程碑 Done 标准的验收依据。用例编号按模块前缀，可在里程碑结束时逐条勾验。
> 约定：本文件只覆盖 v2 新增 / 变更面；v1 既有用例（TC-APP / TC-EV / TC-TK / …）仍为全量回归基线，各里程碑收尾时按附二对照回归，不在此重复。
> 口径：单测类用例的「预期」即测试断言（`npm test` / `cargo test`）；实机类用例需真机操作目验；标注「观察项 / 已知边界」者为记录级（验收不判失败）。

## 编号约定

| 前缀 | 模块 | 对应里程碑 |
|---|---|---|
| TC-INT | Claude Code 事件接入 + 接入管理（安装器 / doctor / 复合 session key） | M1 |
| TC-UI | 前端 UI 基础（设计系统 / 主题 / 面板壳 / tab 注册表 / 气泡排队） | M2 |
| TC-M3 | Token 看板增强 + 三层今日查看 + 工具级气泡 | M3 |
| TC-M4 | 定时任务（notify / exec 泛化 + 合并 tab + snooze + 执行历史） | M4 |
| TC-M5 | Token by agent（CC transcript 解析 + 统一视图 + CC 汇报） | M5 |
| TC-M6 | 多 agent × 多 session 抢镜 + 气泡 agent 标识 | M6 |

---

## 一、TC-INT Claude Code 事件接入与接入管理（M1）

### TC-INT-01 CC hook 事件归一化全集（单测）

- **前置**：`claude-code-hook.js` 纯函数单测（`src/lib/claude-code-hook.test.ts`，无需真实 CC）。
- **步骤**：按 V2-DESIGN §1.3.1 映射表逐事件构造 hook input JSON 驱动 classify。
- **预期**：

| CC 事件 | PulsePet kind |
|---|---|
| `SessionStart` | idle（`--resume` 时复位旧 session 残留状态） |
| `UserPromptSubmit` | thinking |
| `PreToolUse` + tool_name ∈ {Edit, Write, MultiEdit, NotebookEdit} | editing |
| `PreToolUse` + Bash 且 command 命中测试正则 | testing |
| `PreToolUse` + Bash 普通命令 / Read / Grep 等其余工具 | working |
| `PostToolUse` | working（瞬态复位主信号） |
| `PostToolUseFailure` | error |
| `PermissionRequest` | waiting-permission（单向展示） |
| `Stop` | idle（与 openpets(success) / clawd(attention) 的分歧已记录在案） |
| `StopFailure` | error |

  1. 测试命令判定复用 opencode 插件 `TEST_CMD_RE` 同款正则常量，两处定义**逐字一致**（`cargo test` / `go test` 经 "test" 子串天然覆盖）；
  2. `Notification` / `SubagentStart` / `SubagentStop` / `SessionEnd` / `PreCompact` / `PostCompact` 等事件**不注册**——安装条目（§1.4.2 共 8 事件键）与脚本分类均不出现。

### TC-INT-02 CC hook 行为契约（单测）

- **前置**：同 TC-INT-01。
- **步骤/预期**：
  1. stdin payload >64KB → 拒收；
  2. hook input 缺 `session_id` → 事件**丢弃**（不落 `default`——较 opencode 侧仅流式心跳类缺号丢弃更严，全事件丢弃）；
  3. killswitch 文件（`~/.pulsepet/runtime/hooks-disabled`）存在 → 整体跳过不 POST；
  4. endpoint / token 文件 ENOENT → 快速通道立即 exit 0（不 POST、无重试无退避——一次性进程不存在退避睡眠载体）；
  5. POST body 恰为 `{sessionId, kind, agent:"claude-code"}`；POST 超时 1s；
  6. 全部异常路径 catch-all → exit 0 不抛错；无 stderr 输出（除非 `PULSEPET_HOOK_DEBUG=1`，且错误文案净化路径）；
  7. **不做客户端节流**（M1 裁定；App 侧 30 req/s 限流 + 幂等状态覆盖兜底）。

### TC-INT-03 一键安装 claude-code（实机，macOS）

- **前置**：`~/.claude/settings.json` 存在（或不存在），含用户自有 hooks 条目（含 matcher 组形态）与 `env` 等其它键。
- **步骤**：设置页「接入管理」→ claude-code 行点击「安装」。
- **预期**：
  1. `settings.json` 的 `hooks` 下出现 8 个事件键（SessionStart / UserPromptSubmit / PreToolUse / PostToolUse / PostToolUseFailure / PermissionRequest / Stop / StopFailure），各追加一组 canonical **matcher 组条目**（事件数组元素为 `{hooks:[...]}` 组、外层省略 matcher=全捕——**2026-08-24 勘误**：初版"数组直接元素"形态被 CC zod 拒绝、整文件跳过），组内 command 条目：`type:"command"`、command 内嵌 `--pulse-pet-managed`、`timeout:3`、`async:true`、`asyncRewake:false`；安装后新开 CC 会话**无 Settings Error**；
  2. command 为 Unix shell 包装形态（killswitch 前置 → hook 文件存在且 node 在 PATH 则 `exec node` → 兜底 drain stdin + exit 0，V2-DESIGN §1.4.2）；
  3. 用户已有条目（含 matcher 组内）原样保留；`env` 等未知键保留；**键序不变**（serde_json preserve_order）；
  4. 写前备份 `settings.json.pulsepet-backup-<ISO>.json`（mode 0600）产生，且旧备份被清理**仅保留最近 1 份**；写入为原子写（`<pid>.tmp` → rename）；
  5. `~/.pulsepet/hooks/claude-code-hook.js` 落点正确，md5 与 App 内嵌副本一致（doctor `hookFile.matchesBundled = true`）；
  6. **安装后须新开 CC 会话验证生效**（hooks 配置读取时机未实证，保守假设会话启动缓存）。

### TC-INT-04 真实 CC 会话状态闭环（实机）

- **前置**：CC 接入已安装，新开 CC 会话，App 运行中。
- **步骤**：依次真实操作：发消息 → 让 agent 编辑文件 → 跑 `npm test` → 跑普通命令（如 `ls`）→ 制造权限弹窗并在终端审批 → 结束本轮。
- **预期**：宠物状态依次为 thinking → editing → testing → working → **waiting-permission（review 姿态）→ 终端审批通过后经 PostToolUse → working 自愈**（单向展示语义完整闭环）→ Stop → idle。
- **追加**：（PostToolUseFailure / StopFailure 目视可选——制造工具失败 / 中断场景各一次，预期 error，单测已钉住映射）。
- **观察项（R8 事件乱序覆盖）**：PreToolUse(editing) 的 POST 可能晚于 PostToolUse(working) 到达（一次性进程 ~100ms 冷启动窗口），宠物短暂停留旧瞬态后自愈——记录不修。

### TC-INT-05 双 agent 并行会话（实机）

- **前置**：opencode 与 Claude Code 各开一个会话。
- **步骤**：交替触发事件：opencode 会话 editing → CC 会话 error → opencode 会话 idle → CC 会话 working。
- **预期**：
  1. 互不串状态（状态机 key 为复合键 `agent:sessionId`，`opencode:ses_*` 与 `claude-code:<UUID>` 天然隔离）；
  2. 优先级合并表现与 v1 一致（error > waiting-permission > testing > editing > thinking > working > idle）——CC 报 error 时宠物显示 error；
  3. 同名 session id 撞车理论不可行（`ses_*` vs UUID），单测钉住（R6）。

### TC-INT-06 零阻塞实证（实机）

- **步骤**：
  1. 退出 PulsePet App → 在 CC 里正常干活（连续多轮对话 + 工具调用）；
  2. CC 未运行时启动 App；
  3. 顺带核对慢 POST 场景（R1：`timeout:3` 与 `async:true` 组合语义，观察事件是否丢失 / CC 是否有等待卡顿）；
  4. 创建 `~/.pulsepet/runtime/hooks-disabled` → CC 里触发若干事件 → 删除该文件 → 再触发（M1 验收第 6 条：killswitch 对 CC 接入实机生效）；
  5. 构造不含 node 的 PATH（临时改 shell 环境 / 移走 node）→ CC 里触发事件 → 恢复 PATH（M1 P2-2：node 缺席路径的行为验证；**执行提示（复审 P3-N1）**：hook 进程 PATH 取决于 CC 启动环境，非交互 shell 启动的 CC 可能不继承改动——实测先用 doctor `nodeAvailable` 或 `PULSEPET_HOOK_DEBUG=1` 确认 hook 进程实际 PATH 已构造到位再触发）。
- **预期**：
  1. CC 侧完全无卡顿、无报错入 transcript（issue #12「阻塞宿主」的 CC 侧复验：async + timeout + shell 包装缺席短路 + ENOENT 快速通道四重防护）；
  2. App 启动无异常；
  3. 慢 POST 场景的结论记录在案（事件丢失与否），风险接受或据实调整；
  4. killswitch 存在期间：shell 包装首段短路（不 exec node）→ CC 侧静默无报错、App 侧无 POST；删除后下一个事件立即恢复（无需重启 CC——逐事件探测文件存在性）；
  5. node 缺席时：shell 包装的 `command -v node` 检查失败 → 走兜底 drain + exit 0，CC 侧**无 `node: command not found` 报错、退出码 0**（P2-2 修订的静默契约行为验证；对照：若无此检查，`exec node` 失败时 sh 以 127 退出并打 stderr）。

### TC-INT-07 卸载 / 幂等 / stale（实机）

- **前置**：claude-code 已安装；settings.json 中另有用户自有 hooks 条目。
- **步骤**：
  1. 「接入管理」点击「卸载」；
  2. 再次「安装」→ 再「卸载」（验证幂等）；
  3. 手动改写一条 pulse-pet 条目的 command（构造 stale）→ 查看 doctor → 一键「重新安装」；
  4. 手动复制一条 pulse-pet 条目（构造多条特征条目）→ 查看 doctor。
- **预期**：
  1. 卸载后 8 事件键下 pulse-pet 特征条目全部移除（**含 matcher 组内递归移除**）、用户条目保留；事件数组空则删事件键、`hooks` 对象空则删 `hooks` 键；hooks 脚本文件删除；doctor 显示未安装；
  2. 二次卸载 no-op；重装幂等（每个事件键下 pulse-pet 特征条目数恰为 1 且 command 与 canonical 串完全一致 → installed；**用户条目 + canonical 条目共存同样判 installed**——P1-1 修订口径）；
  3. stale 态（command 形态不一致）→ doctor 显示「需更新」；重装 = 移除旧条目 + 落新脚本 + 写 canonical 条目，修复为 installed；
  4. 多个 pulse-pet 特征条目 → stale；
  5. 卸载提示文案含「建议新开 CC 会话」（Windows 字面路径无逐事件自愈，§1.4.4）。

### TC-INT-08 安装器防御路径（单测，tempdir 注入）

- **前置**：Rust `integrations.rs` 单测。
- **步骤/预期**：
  1. settings.json JSON 解析失败 / 顶层非对象 / `hooks` 值非对象 → 报 error **不落笔**（原文件字节不变）；
  2. 文件不存在 → 视为 `{}` 新建（安装成功）；
  3. settings 路径为符号链接 → 拒绝操作并报错；
  4. opencode JSONC 合并移植用例 = `opencode-config.test.ts` 全量平移：注释保留 / 尾逗号保留 / 空 plugin 段 / 非法输入保守返回原文并报 doctor error（§1.4.5）；
  5. **线程与 panic 纪律（issue #9 复核面）**：`integrations_status` / `integrations_install` / `integrations_uninstall` 三命令为 `async fn`，node 探测（spawn ~50-200ms）与安装文件 I/O 经 `spawn_blocking`（不放主线程——Windows 消息泵所在，阻塞即 UI 冻结）；命令路径零 panic（全部 `Result<T,String>` 返回 + `plog!`，无 `unwrap()/expect()`）；`AgentActivity` 等 managed state 在**窗口创建循环之前** `app.manage()`（非「命令首次调用时惰性 manage」——代码结构核对项）。

### TC-INT-09 doctor 状态与接入管理 UI（实机）

- **步骤**：打开设置页「接入管理」区，构造各状态核对。
- **预期**：
  1. 两接入各一行：状态点四态（已安装 / 未安装 / 需更新 / 错误）+ 关键路径 + doctor message + 动作按钮（安装 / 重新安装 / 卸载）；安装中按钮 disabled + spinner；
  2. `version` 显示 App 版本（脚本随 App 发布）；`nodeAvailable` 现测不缓存（每次 doctor spawn `node --version`，~50ms）：node 在 PATH →「node 已就绪」，缺席 →「未检测到 node（CC 接入需要）」；
  3. `lastEventAt` 活性：「事件正常 / 最近无事件」，新鲜度阈值 **10 分钟**（超阈显示 noEvent）；数据来自 App 内存 AgentActivity，无需落盘；
  4. 刷新时机：进入设置页 + `tauri://focus` 双触发（复用 v0.1.3 四-1 模式）；
  5. 双语 zh/en 切换即时；`integrations.*` 键 zh/en 集合一致（字典完备性测试守护）。

### TC-INT-10 agent 白名单与状态机复合 key（单测）

- **前置**：Rust `http_server.rs` / `session_state.rs` 单测。
- **步骤/预期**：
  1. POST /state `agent` 为白名单外值（如 `claude`）→ 400（防 typo 幽灵 session）；`opencode` / `claude-code` 合法；
  2. 两合法 agent 各自以复合 key `agent:sessionId` 落状态机；**同 sessionId 不同 agent 互不覆盖**；
  3. `DisplayState` 返回归属 agent（归属来自 `SessionRecord.agent` 字段而非反解析 key）；
  4. AgentActivity 更新 per-agent 最近事件时刻（`lastEventAt` 数据源）；
  5. 既有 http_server 集成用例的 `"agent":"a"` 值同步修订为合法值（不因白名单落地而红）。

### TC-INT-11 idle hook 分流（单测）

- **步骤/预期**：`make_idle_hook(agent, session_id)` 仅 `agent=="opencode"` 走 token 汇报（查 opencode.db）；claude-code 的 idle 事件**不触发任何 opencode.db 查询**（mock 断言零查询）；opencode idle 汇报不回归（v1 TC-TK-10 保持绿）。

### TC-INT-12 opencode 接入 Rust 化对等（单测 + 实机）

- **步骤**：
  1. App 内「接入管理」安装 / 卸载 opencode 插件；
  2. 与 `install.sh` / `install.ps1` 产物对账。
- **预期**：
  1. 脚本落点 / 配置查找顺序（`opencode.json` → `.jsonc` → 新建 `.json`）与 v1 install.sh 完全一致；
  2. App 内嵌 `include_str!` 与 install.sh 从同一源文件拷贝，产物 md5 天然一致（doctor 对账基准 = 内嵌串）；
  3. JSONC 文本合并保注释 / 尾逗号 / 未知键（v1 TC-EV-01 语义不回归）；备份 + 原子写对两接入统一适用；
  4. `install.sh/ps1` 维持 opencode-only 不扩展 CC（M1 裁定；CC 安装唯一通道 = App 内「接入管理」）。

### TC-INT-13 Windows 形态（实机，挂观察项）

- **前置**：Windows 环境。
- **步骤**：安装 claude-code 接入 → 检查条目 → 删除 hooks 脚本文件 → 触发事件。
- **预期**：
  1. command 为跨 shell 字面路径形态：`node "C:\Users\<name>\.pulsepet\hooks\claude-code-hook.js" --pulse-pet-managed`，条目追加 `"shell": "powershell"`；
  2. hooks 目录为 `%LOCALAPPDATA%\pulsepet\hooks\`（与 runtime / plugins 平级）；
  3. killswitch 不依赖 shell 包装，脚本自身启动即查 `hooks-disabled`，同样生效；
  4. 脚本缺席时 `node <missing>` 向 CC stderr 报一次错（已知边界，openpets 等价行为，doctor 钉住缺席态；实机验证挂观察项，与 V1-OPEN-ITEMS 一.2 同批）。

---

## 二、TC-UI 前端 UI 基础（M2）

### TC-UI-01 主题三档切换（实机）

- **步骤**：
  1. 设置页「外观」三选一分段控件：跟随系统（默认）/ 浅色 / 深色，依次切换；
  2. 「跟随系统」下修改系统外观；
  3. 切深色后重启 App；
  4. 切换主题期间观察宠物气泡与右键菜单。
- **预期**：
  1. panel 全控件即时跟随（浅色 = 暖纸 + 蜜橘；深色 = 冷炭 + 项圈青，对照权威样例 `mockups/a.html` / `b-cool.html`）；
  2. 手动选择 > 系统偏好；「跟随系统」时监听 `prefers-color-scheme` 即时联动；
  3. 重启后选择保留（`app_state` 键 `ui.theme`，缺省 auto）；
  4. **气泡 / 右键菜单不随主题变**（「宠物世界物件」固定暖白 `--pet-world-*`，两主题同值）；
  5. pet 窗 body 背景保持 transparent；
  6. 已知边界：深色用户冷加载面板先闪一帧浅色（FOUC）——接受（R9），不计失败。

### TC-UI-02 主题解析与持久化（单测）

- **前置**：`resolveTheme` 纯函数 + Rust `ui_get_theme` / `ui_set_theme` 单测。
- **步骤/预期**：
  1. `resolveTheme(preference, systemDark)`：auto + 系统深 → dark；auto + 系统浅 → light；light / dark 手动值覆盖系统偏好；
  2. `ui_get_theme` 缺省返回 `"auto"`；非法值拒绝 / 回退；
  3. `ui_set_theme` 持久化到 `app_state` 且写后 `ui://theme` 事件广播断言（仅 panel 窗消费，Rust 无主题消费面）。

### TC-UI-03 面板壳与 agent 状态芯片（实机）

- **步骤**：打开控制面板，驱动任一 agent 会话产生状态变化。
- **预期**：
  1. 顶栏 = 「PulsePet · 控制面板」标题 + agent 状态芯片**两段布局**（2026-08-24 修订：mini 猫移除，原三段布局作废）；tab 栏在顶栏正下方（2px 底线，激活 tab 带 accent 色硬阴影上浮效果）；
  2. 状态芯片 `● {agent} · {kind}`，等宽字体，随 `pulsepet://state` 实时更新；agent / kind 字面量不翻译（i18n 约定），aria-label 走 `panel.statusAria`；
  3. 面板初开即正确（`get_display_state` 返回 `{kind, agent}`——M1 前置拉前至 M2 生效）；
  4. sessions 全空 → idle 且 agent 为空时芯片优雅降级（不显示错误值）。

### TC-UI-04 atlas_sheet_png 命令（单测）

> **作废（2026-08-24 修订）**：用户裁定移除顶栏 mini 猫，`atlas_sheet_png` 命令为唯一消费方，一并回收删除——本用例不再执行。原文留档：

- **步骤/预期**：返回非空 PNG dataURL；结果随 AtlasState 缓存（重复调用不重编码）；atlas 热替换（换宠物）时缓存失效重建；命令为 `async fn` + `spawn_blocking`（1536×1872 重编码 ~50-200ms 不占主线程，issue #9 纪律）。

### TC-UI-05 mini 猫状态镜像与降级（实机）

> **作废（2026-08-24 修订）**：用户裁定移除顶栏 mini 猫（连带 MiniCat.tsx），本用例不再执行。原文留档：

- **步骤**：驱动 agent 状态变化（working / error 等）→ 换宠物（atlas 热替换）→ 构造 atlas 损坏回退。
- **预期**：
  1. mini 猫（24×26 canvas，`image-rendering: pixelated`）用当前 atlas 真实帧镜像状态：working → running 行跑动帧、error → failed 行等；帧行映射复用 `sprite.ts`，**120ms 固定步进**（不复用帧时长表节拍），rAF 节流；
  2. atlas 热替换后 mini 猫同步换装；
  3. atlas 损坏 / 加载失败时渲染占位方块，不崩、优雅降级。

### TC-UI-06 (kind, agent) 去重拉前（实机 + 单测）

- **前置**：双 agent 场景（opencode + claude-code；或单测注入）。
- **步骤**：让宠物长时间停留同一 kind（如整日 idle），期间切换另一 agent 会话产生**同 kind** 事件。
- **预期**：状态芯片的 agent 正确跟随（`DisplayNotifier` 去重键已改为 `(kind, agent)`——同 kind 换 agent 仍发事件；不拉前的后果是芯片 agent 值永久停留，此为 P1-1 修订的验收钉子）。

### TC-UI-07 tab 注册表与 feature flag（实机）

- **步骤**：
  1. 查看默认 tab 集；
  2. 设置页「功能管理」区关闭 Todo 插件（此时正停留在 Todo tab）；
  3. 等待某条 todo 派生提醒的到期时刻；
  4. 重新启用 Todo；
  5. `panel://tab` 直达已禁用的 tab（宠物右键菜单 → 设置路径再验证）。
- **预期**：
  1. 核心三 tab（Token / 提醒 / 设置）静态注册、顺序渲染，**不可关闭、不出现在「功能管理」区**；插件 tab（今日 = Todo）按 name 排序插在提醒与设置之间；「功能管理」区列**每个插件一行（含已停用——2026-08-24 修订）**；
  2. 禁用 Todo → tab 立即消失；正查看时**立即自动切到首个可用 tab**；
  3. 禁用期间 todo 派生提醒**不再触发**（到期无气泡 / 无烟花）；提醒列表中 todo 派生行仍可见但显示「已停用（插件关闭）」徽标（可见但惰性——数据不删，用户不疑惑「我的 todo 提醒去哪了」）；
  4. 重启用后全恢复（tab 回来 + 派生提醒恢复触发 + 徽标消失），DB 数据全程无损（无任何 DELETE）；
  5. `panel://tab` 直达禁用 tab → 回退到首个可用 tab。

### TC-UI-08 禁用语义数据面（单测）

- **前置**：Rust `plugins_set_enabled` / `reminder_scheduler` 单测（tempdir DB）。
- **步骤/预期**：
  1. 禁用 todo 插件 → 调度器专用 `load_active_rules` 过滤 `kind='todo'` 且源插件 `enabled=0` 的行；`reminders_list` 照旧走 `load_rules` 全量返回（列表可见性依据）；
  2. 重启用 → 派生行恢复参与调度；
  3. `plugins_set_enabled` 写 `plugins.enabled` 列后触发提醒调度器 reload（禁用停派生的执行面）。

### TC-UI-09 气泡排队模型（单测，`bubble-queue.test.ts` 全覆盖）

- **前置**：`src/lib/bubble-queue.ts` 纯函数，全部可注入 `now` 虚拟时钟直测。
- **步骤/预期**（对照 V2-DESIGN §2.6.1 六条规则）：
  1. **顶替回队**：critical 到达时 info 显示中 → info 立即被顶回**队首**（不丢失、不结案）；同级新条目按 FIFO 排队；
  2. **同源合并 10s**：同 `source` + 同级别 10s 内新条目**原地替换**旧条目——显示中的替换后文案刷新 + dwell 重计时，队列中的同样替换；**已离场过期的不复活**（新条目独立入队）；
  3. **队列上限与驱逐**：上限 3 指 queue 数组长度（不含 current）；入队 / 回队超限**仅驱逐 ambient（自队尾优先——2026-08-24 修订，原「ambient → info 顺序」与下句矛盾）**；critical / info 永不被驱逐（queue 全为 critical/info 时允许临时超 3）；被顶替回队的 ambient 遇满队驱逐即丢弃（ambient 可丢语义，critical 无漏账风险）；
  4. **分级 dwell**：critical 8s（或点宠物确认）、info 6s、ambient 4s；`expireCurrent` 到期离场；
  5. **悬停层冻结**：`setHoverPaused(true)` 后 dwell 冻结、队列不推进；恢复后续走剩余 dwell；
  6. **净化护栏与记账**：sanitizeBubbleText 净化后为空 → 按 auto 结案；只有最终离开显示（dwell 到期 / 确认）才回报 dismissed_via，被顶回队期间不结案；**critical 不会被 info / ambient 顶**（只有同级 critical 间 FIFO / 合并轮换）；
  7. **已知边界**（记录级）：critical 尚在队列未显示时 App 退出 → 该 reminder_log 的 dismissed_via 永久 NULL（与 v1 同窗，无回归）。

### TC-UI-10 气泡排队实机（实机）

- **步骤**：
  1. 提醒气泡（critical）显示中触发一次会话结束 token 汇报（info）；
  2. token 汇报显示中触发一条提醒；
  3. 10s 内连续结束两个会话（同 source="token-report"）；
  4. 提醒显示中点击宠物；
  5. 完成一个 todo（烟花 + 庆祝）。
- **预期**：
  1. token 汇报**不顶替**提醒（critical 优先），排队随后显示；
  2. 提醒**立即顶替**汇报，汇报回队首、提醒结束后重现（剩余 dwell 续走）；
  3. 同源合并：仅一条汇报（文案刷新、dwell 重计时），不产生第二条；
  4. 提醒气泡立即消失，`reminder_logs` 记 `acked_at` + `dismissed_via='bubble'`（v1 记账语义不变）；
  5. todo 完成庆祝 = info 级 source="celebration" + waving 动画保留；烟花叠加编排原样保留（`planReminderActions`：气泡无条件 + 烟花**额外** invoke，v0.1.3「特效只叠加」原则不变）。

### TC-UI-11 气泡与右键菜单视觉（实机）

- **步骤**：触发各级气泡 + 打开宠物右键菜单，在浅色 / 深色主题下分别目验。
- **预期**：
  1. 气泡：暖白底 + 2px 墨边 + `2px 2px 0` 硬阴影 + 像素尖角；critical 级左侧 4px 蜜橘色条；单行省略（净化约束不变）；
  2. 右键菜单：同语言翻新（暖白 + 2px 墨边 + 硬阴影 + 直角项），**行为零改动**（clamp / 关闭逻辑保留，v1 TC-WIN-03/04 不回归）；
  3. 两者均不随主题切换（`--pet-world-*` 固定色组）。

### TC-UI-12 设计系统落地与硬编码色清零（实机 + grep）

- **步骤**：
  1. 四个 tab 页（Token / 提醒 / Todo / 设置）逐页对照样例目验；
  2. 深色主题下核对卡片 / 表格 / 输入控件 / 滚动条 / hover / disabled 态可读性；
  3. grep 色值字面量（`#[0-9a-fA-F]{3,8}` / `rgba(`）做硬编码色清单。
- **预期**：
  1. 全部落新 token（像素语言四规则抽验：2px 实线边框、位移式硬阴影、直角为主、数字等宽字体；字号阶 10/11/12/13/17/22 无 14/15/16/20 混用）；
  2. 深色下无白底刺眼 / 低对比不可读控件（R7 目验面）；
  3. 未列入 token 表的色值字面量即清理对象，清零核对（例外：pet 窗气泡 / 菜单走 `--pet-world-*`、fireworks 无文案）——R8 准绳。

### TC-UI-13 测试迁移与既有套件不红（单测）

- **步骤/预期**：
  1. 既有 `bubble.ts` 纯函数测试（sanitizeBubbleText / 时长常量）与插件侧 `plugin-hook.test.ts` 的 pickBubble 用例**不动且全绿**（P3-1 归属修正）；
  2. `token-chart` 等纯函数套件不红（V2-SCOPE「不破坏」边界）；
  3. `petStore.test.ts` 单槽位断言（顶替即丢 / 8s 恒定）**有意改写**为排队语义（顶替回队 / 分级 dwell）——V2-SCOPE「不破坏」不含 petStore 行为测试，取代清单已在 V2-DESIGN §2.6.4 明示；
  4. i18n 字典完备性：新键（`settings.theme*` / `plugins.manage*` / `panel.statusAria`）zh/en 键集合一致。

### TC-UI-14 tab 注册表纯函数（单测）

- **前置**：`useTabs()` / `registry.ts` 纯逻辑单测（mock `plugins_list` 返回）。
- **步骤/预期**：
  1. 核心三 tab 静态注册且顺序固定（token / reminders / settings）；插件 tab 按 name 排序插在 reminders 与 settings 之间；
  2. 禁用过滤：`enabled=0` 的插件 tab 不出现在注册表；
  3. 回退：当前 tab 被禁用 → 解析结果回退到首个可用 tab；
  4. **`panel_tab` 键读取（P3-③ 回归陷阱钉子）**：PluginInfo 序列化键为 `panel_tab`（无 serde rename），前端读 `panel_tab` 字段消费 manifest 的 panelTab——mock 数据含 `panel_tab` 时正确生成 tab、读错键（如 `panelTab`）时插件 tab 缺失（用例两种键各构造一次钉住正确键名）。

---

## 三、TC-M3 Token 看板增强 + 工具级气泡（M3）

### TC-M3-01 数据层字段扩展（单测）

- **前置**：Rust `token_stats.rs` 单测（tempdir 构造 opencode.db）。
- **步骤/预期**：
  1. `TokenRow` 增 3 字段：`model_id`（`json_extract(model,'$.id')`；NULL / JSON 损坏 → None）、`project_name`（JOIN `project.worktree` → Rust 侧 `Path::file_name` 取 basename；`"/"`（global）或 JOIN 未命中 → None）、`title`（by-session 独有；聚合行 None）；
  2. model 列 NULL → None（前端「未知模型」合并，防御性回退）；带后缀 id（如 `deepseek-v4-flash@max`）按原样归并；
  3. grouped（day/week）行含 model_id 且**不含 project_id**（`GROUP BY day_expr, model_id`）；range 维同口径（GROUP BY model_id）；
  4. `SESSION_REQUIRED_COLUMNS` 白名单 + `model` + `title`：构造缺列库 → 既有 schema-mismatch 错误码路径，不崩溃不查错列（v1 TC-TK-13 语义扩展）。

### TC-M3-02 mock 模型过滤口径（单测）

- **步骤/预期**：`providerID='mock'` 的行（如 `probe-model`）在**全部查询**（by-session / day / week / range / `query_current_session` idle 汇报链路 / `token_stats_today`）中均被过滤——mock 行不出现、统计零影响、口径统一防漂移（S4 裁定）。

### TC-M3-03 token_stats_today 命令（单测）

- **步骤/预期**：
  1. from = 本地今天 0 点（chrono::Local，注入固定时刻验证边界）、to = now；返回 `{input, output, cache_read, cost}`；
  2. 复用 no-database / legacy-storage / schema-mismatch 全套错误处理原样透传；
  3. 命令为 `async fn` + `spawn_blocking`（沿 M1 线程纪律）；
  4. 三层快捷查看（TC-M3-09/10/11）共享此命令，单一数据源。

### TC-M3-18 跨天会话按消息时间归天〔**§14 增补 2026-08-29**，单测〕

> 来源：V2-OPEN-ITEMS §十四（token 统计跨天会话归属缺陷）；day/week/range/today 四类聚合下沉 message 级（v1 TC-TK-06/07 语义扩展——day 归属从「会话 time_updated」改为「消息产生时间」）。Rust 侧已落地钉子：`s14_cross_day_session_attributed_by_message_day` / `s14_window_excluding_last_active_day_counts_earlier_days` / `s14_message_row_filter_user_and_corrupt_rows` / `s14_mid_session_model_switch_splits_groups` / `s14_message_table_missing_is_schema_mismatch` / `s14_cc_cross_day_session_buckets_by_message_day`（token_stats.rs）+ `s14_by_day_buckets_cross_day_session` / `s14_dedup_precedes_day_bucketing` / `s14_missing_ts_falls_back_to_session_time_updated` / `s14_same_day_bucket_first_ts_is_earliest`（transcript.rs；末枚为 tester P3-1 加固钉）。

- **步骤/预期**：
  1. **opencode 跨天拆分**：同一 session 两条 message 分属两天 → by-day 两天各自聚合、today 只计今天的 message、by-session 仍为会话累计（首日贡献不再消失）；
  2. **窗口漏计修复**：7d 窗口不含最后活跃日 → 窗口内天数的 message 照常计入（day 与 range 同口径）；
  3. **message 行筛选**：user 行（无 `$.tokens`，实测 0% 带）不产生零值聚合组；损坏 data 不炸查询不入聚合（json_valid 守卫）；mock 过滤在 message 级 `$.providerID` 生效；
  4. **message 级模型归并**：同 session 中途换模型 → 按 `$.modelID` 分两组（原 session.model 末值归一组）；
  5. **schema 严格报错**：message 表缺失 / 缺列 → schema-mismatch（「请升级 pulse-pet」），query/today/current/idle 全链路拦截；
  6. **CC 侧对称**：单 jsonl 跨天两行 assistant → `by_day` 两桶；同 message.id 跨天去重末条胜且只计末条那天；ts 缺失兜底归会话 time_updated 日；session time_updated 出窗但有窗内桶仍计入；session 视图与 `last_assistant_ts` 护栏不变。

### TC-M3-04 今日 preset 与面板默认（单测 + 实机）

- **步骤**：`rangeForPreset` 纯函数单测（注入固定时刻）+ 打开面板 Token 页 → 切 7d / 30d / 自定义 range。
- **预期**：
  1. 默认选中**今日**（原默认 7d 变更）；分段控件首位为「今日」；
  2. 单测断言：`rangeForPreset("today")` 注入固定时刻 → from = 该时刻本地今天 0 点、to = now（含跨午夜前后的边界用例）；
  3. 切 7d / 30d / 自定义行为不回归（v1 TC-TK-08）；时间边界含当天。

### TC-M3-05 堆叠柱状图（单测 + 实机）

- **前置**：`computeStackedBars` 纯函数单测 + 面板目验。
- **步骤/预期**：
  1. 柱内三段**自底向上 output → input → cache read**（SCOPE D 裁定；reasoning 不参与任何汇总口径）；
  2. 悬浮 HTML tooltip：日期 + 三项数值 + 占比 + 总量；三项数值行**自上而下 cache read → input → output**（用户 2026-08-25 裁定修订；柱内堆叠顺序仍为自底向上 output → input → cache read，两者独立）；图例三项仅说明**不可交互**（与模型筛选语义隔离）；
  3. 色值 = M2 `--chart-output/input/cache` token，深浅主题下三段色均可读（token 化）；
  4. 单测：三段顺序 / 勾选模型剔除后重新聚合 / selectedModels 空集 → 空态文案不渲染柱 / 空行输入；**不传 `agentFilter` 时行为 = 不过滤**（等价全量——M5 预留参数位钉子 N12）；
  5. `computeBars` / `pieSlices` 及其测试已删除，无残余消费（grep 确认）；
  6. range 维度无柱图：隐藏柱图与筛选区，仅 KPI + 会话列表（现状语义不变）。

### TC-M3-06 模型筛选（实机）

- **步骤**：Token 页查看柱图上方模型 chip → 取消勾选某模型 → 全部取消。
- **预期**：
  1. chip 来源 = 当前跨度聚合行 distinct model_id，按总量降序排列，默认全勾；
  2. 取消勾选**仅柱图变化**（剔除该模型数据后重新聚合），KPI 卡 / 会话列表不联动（SCOPE E：口径各自独立）；
  3. probe-model 不出现在 chip 列表（SQL 层已过滤，TC-M3-02）；
  4. 空集 → 空态文案；
  5. 筛选 chip 行为**可容纳多组筛选的容器**结构（`filter-row` 内模型组为第一组；M5 时 agent 组插入同容器——agent 筛选 UI 预留位，本里程碑不渲染空组不留空位）。

### TC-M3-07 KPI 首卡与 reasoning 口径（单测 + 实机）

- **步骤**：`sumRows` 单测断言 + 查看 KPI 卡片，与 by-session 明细对账。
- **预期**：
  1. 首卡「总量」= input + output + cache_read（**reasoning 不计入任何汇总口径**——用户裁定，与 GLM 官方展示同口径；数据层 tokens_reasoning 独立存在，v1 会话详情露出不变）；
  2. 卡片顺序：**总量 / cache read / input / output** 四卡布局（用户 2026-08-25 裁定修订：cost 卡移除，cache read 升独立第二卡，首卡无「含 cache read X」副行小字）；
  3. 单测断言：`sumRows` 注入含非零 reasoning 的行数据 → total = in + out + cache_read（reasoning 字段存在但不参与任何汇总字段）。

### TC-M3-08 砍饼图与会话列表改造（实机）

- **步骤**：打开 Token 页查看会话列表 → 展开一条会话详情。
- **预期**：
  1. `ProjectPie` 组件、双栏布局（`.token-columns`）消失，会话列表升为全宽；项目维度经 project_name 映射在会话列表体现（饼图信息量趋零的裁定落实）；
  2. 首列 = **会话标题**（过长 flex 省略；`title` 属性 tooltip = 完整标题 + session id + 本地时间）；`New session - 时间戳` 回退行按原样显示；title NULL → session id 前 8 位；
  3. 项目列 = 可读项目名（basename，如 `lab`）；`global`（`/`）→ 回退标签 `token.project.global`；JOIN 未命中 → `token.project.unknown`（替代 v1 哈希不可读问题）；
  4. 展开详情追加「模型」行（model_id；None →「未知模型」）；input/output/reasoning/cache 分布详情不回归；
  5. 排序 = token 总量降序（前端 `sortedSessions` 重排保留；Rust ORDER BY time_updated DESC 为传输序——两行为均维持现状）。

### TC-M3-09 被动层：idle 汇报追加今日累计（单测 + 实机）

- **前置**：Rust 单测（`make_idle_hook` 追加段拼接，注入时钟 / 注入今日聚合错误）+ opencode 会话有 ≥1 条 token 记录的实机场景。
- **步骤**：单测断言追加段逻辑 → 实机结束会话（session idle）观察汇报气泡。
- **预期**：
  1. 气泡末尾追加「 · 今日 {format_tokens_k(total)}」；total = in + out + cache_read（reasoning 不计；mock 过滤）——单测注入固定时刻断言拼接文案逐字符合（zh 与既有汇报措辞钉住一致，i18n 模板键 `token_report_today`；**§十二 F1 修订 2026-08-28**：本期段改「本次会话消耗 token {total}」单总量口径，断言已随改）；
  2. 本期数字逻辑不变（60s 新鲜度护栏沿用）；今日聚合与本期查询同连接一次完成；
  3. **失败省略分支（单测）**：注入今日聚合错误（如跨午夜边界竞态）→ 静默省略追加段、本期数字照常显示（实机不可稳定构造，以单测钉住——P2-6）；
  4. **仅 opencode**（M1 idle 分流内实现；CC 会话 idle 无追加——M5 前无 CC 数据）。

### TC-M3-10 主动层：悬停宠物今日汇总卡（实机）〔**作废留档 2026-08-25 用户裁定：悬停卡实际体感差，本功能点已移除**——HoverToday 组件及接线删除；不执行本用例；30s 缓存与 token_stats_today 由 TC-M3-11 右键菜单独享〕

- **步骤**：
  1. 非穿透态悬停宠物 <500ms 移开 → 再悬停 ≥500ms → 移开；
  2. 悬停显示期间触发一条提醒气泡；
  3. 悬停显示中右键宠物；菜单打开中再悬停 500ms；
  4. 悬停显示中按热键切穿透；
  5. 穿透模式下尝试悬停 / 右键；
  6. 刚过午夜（全零数据）悬停；无 opencode 库时悬停。
- **预期**（作废前原貌，仅留档）：
  1. 进入 500ms 防抖（不足 500ms 移开不显示）；到点显示悬停层卡片：总量大字 + input / output / cacheRead 三行（等宽字体），落点固定（宠物上方贴顶居中，与气泡同位）；**移开即消**（离开即时，非防抖）；
  2. 显示期间队列推进暂停、当前气泡 dwell 冻结（`setHoverPaused(true)`）；卡片**视觉替换**当前气泡位置（底层 current 不销毁）；移开后恢复显示并续走剩余 dwell；
  3. 与右键菜单**互斥（后开者胜）**：悬停中右键 → 菜单打开 + 卡片隐藏 + **冻结解除**（菜单打开即 `setHoverPaused(false)`，队列恢复推进）；菜单打开中悬停到点不显示（pointer 已被菜单捕获）；
  4. **穿透切换兜底（N14）**：切穿透瞬间（webview 收不到后续 pointer 事件）→ 取消 500ms 计时器 + 隐藏卡片 + 解除冻结（订阅既有 `pulsepet://pass-through` 广播）；切回非穿透不自动恢复；
  5. 穿透模式下悬停与右键均不可达（已知限制——仅被动层与面板可用，不改穿透语义）；
  6. 全零数据照常显示卡片数字为 0（诚实呈现，不伪装错误态）；错误态（no-database 等）显示一行「暂无数据」，不闪错误码；
  7. 数据经 pet 桥层 30s 缓存（防高频悬停打查询；与右键菜单共享缓存）。
- **移除后补充验收**：悬停宠物（含长时间悬停）无任何卡片浮现；右键菜单「今日 token」与面板不受影响（TC-M3-11/12）。

### TC-M3-11 入口层：右键菜单「今日 token」（单测 + 实机）

- **步骤**：`buildPetMenuItems` 单测（注入三态 TodayTokenState）+ 数据加载中 / 就绪 / 无库三态分别实机打开宠物右键菜单 → 点击「今日 token」项。
- **预期**：
  1. 菜单第 0 项为信息项「今日 token：…」（loading）/「今日 token：42M」（ok）/「今日 token：—」（无库 / 错误）三态；数值由既有 `formatTokens` 生成（与 idle 追加段 `format_tokens_k` 同口径）；
  2. 点击 → `openPanel("token")` 打开面板 Token tab（默认即今日，无缝衔接详情）；
  3. 信息项与行为项间有分隔线样式区分；菜单共 4 项，clamp 逻辑按 menuH 估值 130 调整后不越屏；
  4. 菜单打开时 invoke `token_stats_today`（与悬停卡共享 30s 缓存）；
  5. 单测断言（N1 同步）：`buildPetMenuItems(passThrough, todayToken, lang?)` 注入三态 → label 分别为 `…` / `42M` / `—`；菜单恰 4 项、第 0 项 id 为 `today-token`；`PetMenuAction` 联合类型含 `"today-token"`。

### TC-M3-12 口径交叉断言（实机）〔2026-08-25 修订：三层→两层（悬停卡移除）〕

- **步骤**：会话静止窗口内分别读取面板今日 KPI 总量、右键菜单显示值。
- **预期**：两处数值相等——口径一致（同 0 点起点 + mock 过滤 + reasoning 不计）；活跃会话持续写入下的秒级差异属正常（N2 时序限定）。

### TC-M3-13 工具级气泡：插件侧提取与节流（单测）

- **前置**：`plugin-hook.test.ts` 增补 `extractDetailParam` + detail 桶用例。
- **步骤/预期**：
  1. 各工具族 param 提取：read / edit → file path 取 basename；bash → **先剥离行首连续 `KEY=value` 赋值段，再取首词；首词含 `/` 或 `\` 时取 basename**（绝对路径命令 `/opt/homebrew/bin/npm test` → `npm`；env 赋值命令 `FOO=secret npm test` → `npm`——P1-4 净化强化钉子）；search → pattern 净化后原样 ≤40 字符（含 `/` / `\` 取末段）；web → URL 取 hostname；无参 / 提取失败 → 不携带 detail；
  2. detail 携带仅 `tool.execute.before`（`tool.execute.after` / `command.execute.before` 不携带）；args 来源 = `output?.args`；
  3. detail 走**独立 detail 桶**（全局单桶、20s，与 speech 桶同参数非复用）：冷却期内状态事件照发、detail 省略；状态事件被 reaction 桶吞掉时 detail 桶**不消耗**；detail 不影响状态节流桶；冷却消耗在 reaction 放行后（网络成败不回滚）；
  4. detail = `"<tplId>:<param>"`（tpl ∈ read/edit/bash/search/web 白名单）；绝不携带路径原文 / 参数原文 / URL 全文（TC-SEC 净化口径）。

### TC-M3-14 工具级气泡：App 侧解析与入队（单测）

- **前置**：`tool-bubble-bridge.ts` 单测 + Rust `tool_broadcast` 单测。
- **步骤/预期**：
  1. detail 按**首个** `:` 切分（param 可含 `:`——macOS 文件名 / grep pattern 均合法）；tpl 不在白名单或 param 为空 / 纯空白 → 丢弃（不发气泡事件）；
  2. param 再净化：单行、≤40 字符、去控制字符（格式级兜底；路径剥除责任在插件提取层，R8 记录边界）；
  3. 通过 → `pushBubble({level:"ambient", source:"tool:<tplId>"})`（dwell 由级派生 4s；可顶可丢按 M2 ambient 语义）；文案经 i18n `toolb.<tplId>` 渲染（语言随 App 即时）；
  4. Rust 侧：收到含非空 detail 的状态事件 → `emit_to("pet", "pulsepet://tool-bubble", {detail})` 定向透传（不做解析、不判开关）；
  5. `tool_broadcast_get` 缺省 true / 非法值回退；`tool_broadcast_set` 持久化（app_state `bubble.toolBroadcast`）+ `emit_to("pet")` 广播断言；开关关闭 → 桥层静默（判定只读 store 位，零 IPC 热路径）。

### TC-M3-15 工具级气泡实机 + ambient 排队补验（实机）

- **步骤**：
  1. opencode 会话中让 agent 编辑文件 / 跑命令 / 搜索 / 访问 URL；
  2. 连续触发多次工具调用（20s 内）；
  3. 提醒（critical）显示中触发工具播报；
  4. 连续不同工具产生多条 ambient。
- **预期**：
  1. 气泡「正在编辑 X.md」「正在跑 npm」等 ambient 级，4s 自动消失；**不含任何路径 / 参数 / URL 原文**（TC-SEC 口径目验）；
  2. 20s 内同类播报仅一条（插件 detail 桶节流）；
  3. critical 显示中工具播报**排队不顶替**（承接 M2 §2.10 遗留的 ambient 排队实机补验）；
  4. 多条 ambient 触发队列上限驱逐可观察（ambient 可丢）。

### TC-M3-16 工具播报开关（实机 + 单测）

- **步骤**：设置页「宠物与播报」区切换开关 → 立即触发工具调用 → 重启 App 核对。
- **预期**：
  1. 开关位于「宠物与播报」区（与「点击穿透」同区 `settings-check` 形态；**不在**「功能管理」区——该区语义 = 插件启停）；
  2. 默认开；关闭后**立即静默**（无需重启：panel set → `pulsepet://tool-broadcast` 广播 → pet 桥 store 即时更新；panel 开关初始显示值经 get 初始化）；
  3. 持久化重启保留；
  4. 插件照发 detail 不动（App 侧过滤实现，SCOPE 倾向落实）。

### TC-M3-17 M3 新键 i18n 完备性（单测）

- **步骤/预期**：M3 新键 zh/en 字典键集合一致（完备性测试守护）——含 `token.preset.today` / `token.kpi.total` / `token.col.model` / `token.project.global` / `token.project.unknown` / `menu.todayToken` / `toolb.read` / `toolb.edit` / `toolb.bash` / `toolb.search` / `toolb.web` / `settings.toolBroadcast*` / `settings.sectionPet*`（§3.9 完整清单；实施时按实际模板微调增补的细项键同样纳入断言）。〔2026-08-25 修订：`token.todayUnavailable` 随悬停卡移除清退，不再列入断言（清退断言钉住防回归）〕

---

## 四、TC-M4 定时任务（M4）

### TC-M4-01 迁移 003 与 v1 兼容（单测 + 实机）

- **前置**：tempdir DB 集成测试 + v1 存量数据实机。
- **步骤/预期**：
  1. 迁移 003 幂等（版本 2→3 执行 / 3 跳过；SQL + 版本提升包在同一事务，A1 约定）；`SCHEMA_VERSION = 3` 编译期断言不红；
  2. `reminders` 表 +7 列（action_type / action_params / schedule_kind / schedule_at / schedule_weekdays / snooze_until / last_skipped_at）+ `action_logs` 新表；
  3. v1 存量行自动获得默认值（action_type='notify' / schedule_kind='interval'），**v1 行为零变化**：升级后原提醒原样可见可编辑、interval 窗口 / 去重 / 暂停顺延 / 烟花叠加行为与 v1 等价（TC-RM 回归）；
  4. `action_params` JSON 解析失败 → validate 拒绝保存（存量行不可能有，新写路径全过 validate）。

### TC-M4-02 合并「定时任务」tab（实机）
- **步骤**：打开合并后的「定时任务」tab，查看列表与新建表单。

- **预期**：
  1. 核心 tab「提醒」改名「例程」（2026-08-25 R1 后用户裁定修订：原「定时任务」再改「例程」，en 建议 Routines 实施定；`panel.tab.tasks` 键不变仅改 i18n 值），位置不变；`panel://tab` 兼容旧值 `reminders` 映射直达；「Todo」tab 中文显示名同步改「待办」（en 保持 Todo，同裁定）；
  2. 一张列表：每行动作徽标（🔔 notify / ⚡ exec，title 说明——§十二 F10 修订 💧→🔔）+ 类别列（§十二 F11：todo 派生行同渲染「📋 待办」）+ 名称 + 调度摘要（「每 30 分钟 · 09:00-18:00」/「每天 09:00」/「周三、五 09:00」/「一次 · 08-25 21:00」）+ 启用开关 + 行操作（编辑 / 试一试 / 跳过本次 / 删除两步确认）；todo 派生行保持 M2 展示（可见惰性 + 徽标；§十二 F12：行内烟花勾选项移除；§十二 F14：页底历史统计区移除）；
  3. 表单按 `action_type` 条件显隐字段（notify：kind / 文案 / 调度 / 烟花；exec：任务名 / opencode 模板块 / command / cwd / 超时 / 调度）；表单标题「新建例程」（原「新建提醒」，同裁定修订）；「新建」按钮**与表单最后一行字段同行右对齐**（2026-08-25 二次修订：不在单独动作行，随上一行字段内容对齐）且为非默认色；动作类型分段按钮无 emoji 图标（「提醒」不带 💧、「执行命令」不带 ⚡——列表行徽标保留）；Rust `validate` 为权威、前端同规则预检（v1 模式）；
  4. notify 新建（interval / daily / once 三种调度）触发行为与 v1 提醒等价（气泡 / 烟花 / 记账）。

### TC-M4-03 调度纯函数（单测）

- **前置**：`compute_next_due` 按 schedule_kind 分派，注入时钟。
- **步骤/预期**：
  1. daily：当日时刻未到 → 今日 HH:MM；已过 → 次日匹配日；`schedule_weekdays` 不含今天 → 跳到下个匹配日；NULL / 空 = 每天（weekly 并入 daily 的 weekdays 过滤，3 枚举语义不减）；
  2. once：未来时刻 → schedule_at；已触发 / 已跳过 → `i64::MAX` 终态；`schedule_at` 为过去时刻 → validate 拒绝（防创建即意外执行）；
  3. 补跑窗边界（`CATCHUP_WINDOW_MS = 15min`）：now − next_due = 14m59s → 正常触发；15m01s → skipped；
  4. **snooze 重发语义（P1-1）**：`snooze_until` 未过期时**优先于**常规计算（直接置为，非 max——触发后常规 next_due 已是未来，max 会吞掉 snooze）；重发触发时清空 snooze_until 并按 kind 常规推进：once → MAX（重发即终态）、daily → 下个匹配日、interval → 锚点顺延链整体后移 10min；
  5. reload 错过检测：App 关闭跨过 schedule_at 且 `last_triggered_at` 早于该时刻 → 同补跑窗判定（窗内补跑 / 超窗 skipped）；`last_triggered_at` 已晚于 schedule_at → 不误报；
  6. interval 分支 v1 断言全量保留（回归）。

### TC-M4-04 collect_due 与 skipped 记账闭环（单测）

- **步骤/预期**：
  1. daily / once 到期且在补跑窗内 → 触发；超窗 → skipped：exec 型写 `action_logs(status='skipped', summary='错过补跑窗（15 分钟）', scheduled_at=原定时刻)`，notify 型不落库（错过无害）、均不触发气泡 / 烟花；
  2. **skipped 记账闭环（N1/P3-2）**：两来源（超窗 / 暂停）的 skipped 均写 `last_skipped_at`（与 last_triggered_at 分离——防「醒来 3 分钟内点试一试手动补跑」被 dedup 拒绝）+ 推进 next_due（daily → 下个匹配日；once → MAX）；暂停期每 tick 只记一次；skipped 后 CRUD reload 不重复判定；once skipped 后重启仍 MAX；`collect_due` 返回 `(fired, skipped)` 由调用方落库；
  3. **跳过本次清空未过期 snooze_until（N2）**：防 reload 因 snooze 优先级复活被跳过的重发（写表 + 内存同清）；
  4. 暂停分支（对齐 SCOPE 字面「不跑不补、记 skipped」）：interval 类维持 v1 顺延；daily/once 到期**不顺延、不触发**，记 skipped（exec 落 action_logs；notify 不落库）且记后推进 next_due、同款清空未过期 snooze_until；恢复后不补跑（暂停 = 完全冻结）；
  5. 并发上限 2：第 3 个到期 exec 任务进内存等待队列（`pending_execs`，**不写 running 行**）；完成回调经 channel 通知调度器出队 spawn（排队中无进程无 running 行——App 退出时自然消失无残留）。

### TC-M4-05 daily / once / 星期过滤定点触发（实机）

- **步骤**：
  1. 建 daily 任务设 1 分钟后的 HH:MM（如 now+1min）；
  2. 建 once 任务「明晚 9 点」类（近未来时刻）；
  3. 建 daily 任务星期过滤设为今天 +1 的星期。
- **预期**：
  1. daily 到点执行（不早不晚）；
  2. once 触发后列表显示已完结（next_due = MAX，不再触发）；
  3. 星期过滤任务本周不触发、下个匹配日才触发。

### TC-M4-06 exec 执行链（实机）

- **步骤**：依次创建并触发：`echo ok`（秒级）→ `exit 3` → `sleep 600` 且超时设 1 分钟 → `yes` 输出洪水循环。
- **预期**：
  1. `echo ok` → 历史 status=ok + 结果气泡「任务完成」（text = 任务名 + summary）；
  2. `exit 3` → failed，summary 含退出码 3；
  3. `sleep 600` 超时 → **进程组被终止**（Unix `setsid` + kill −pgid；`ps` 断言无残留子进程）+ status=failed（超时被终止）+ output_tail 保留已捕获部分；
  4. 输出洪水 → stdout+stderr 合并尾部截取 ≤2KB（截尾标记 `…(已截断)`），进程内存不膨胀；
  5. Unix 经 `sh -c`、cwd 生效（可配，缺省当前目录）；执行跑独立 spawn 任务（调度器 tick 不等待，并行任务互不阻塞）。

### TC-M4-07 validate 规则（单测）

- **步骤/预期**：command 非空且 ≤2000 字符；cwd 可选（存在则必须为目录）；timeout_minutes 1–120（缺省 10）；`opencode_auto` 为 bool（仅校验，不改变命令）；kind 切换时重置无关字段（interval 行清 schedule_at / weekdays；daily/once 行清 start_time / end_time 窗口——防遗留窗口卡住 in_window 判定导致误 skipped）；once 过去时刻拒绝；`action_params` JSON 解析失败拒绝。

### TC-M4-08 opencode 一等模板（实机）

- **步骤**：表单动作类型选「执行命令」→ 点「opencode 例程」模板快捷块 → 填任务名与指令 → 保存并触发。
- **预期**：
  1. 拼出的 command = `opencode run --title "pulsepet 例程: <任务名>" [--auto] "<指令>"`（`--auto` 由 checkbox 控制，默认不勾、勾选时危险色警示）；cwd 字段独立（不用 `--dir`）；timeout 缺省 10 分钟；
  2. 模板仅填表辅助：用户改 command 后与手写命令无差异（执行层不感知 opencode）；
  3. 真实例程（如「数一下仓库有几个 md 文件」）执行 → 宠物细粒度状态随 agent 层变化（spawn 的 `opencode run` 加载 pulse-pet-hook.js，thinking / editing / testing 正常上报，R9 首日验证）→ 结束 success / failed + 气泡 + **Token 页出现「pulsepet 例程:」标题会话**（`--title` 是否被自动摘要覆盖 = 本用例实测回填，M5 例程徽标 R8 的可行性前提）。

### TC-M4-09 权限行为（实机，S1 复验）

- **步骤**：
  1. 模板不带 `--auto` 跑一个会触发权限请求的任务（如写文件）；
  2. 带 `--auto` 跑同一任务。
- **预期**：
  1. **不卡死**：`opencode run` 打印 `permission requested: …; auto-rejecting` 警告行（进 output_tail）→ 自动拒绝 → agent 按拒绝结果继续执行或失败，任务正常结束（S1 spike 结论复验）；
  2. 带 `--auto` → 权限自动放行（`reply:"once"`），任务放行执行。

### TC-M4-10 宠物状态两层（单测 + 实机）

- **步骤/预期**：
  1. 通用层：任务执行中 → 宠物 working；退出码 0 → success；非 0 / 超时 → error（30s 后自然回收）；
  2. 伪 session 定义：session key = `task:<log_id>`（agent = 常量 `"task"`，Rust 内部直连 `apply_event` 不经 HTTP 白名单）；每次 apply 后**必须调 `DisplayNotifier::notify`**（单测断言 apply+notify 成对）；**不更新 AgentActivity、不触发 idle_hook**（mock 断言零调用）；
  3. 心跳 15s：执行期间每 15s 重 apply Working + notify（防 30s idle 回收；注入时钟单测：正常心跳不回收、心跳延迟 >15s 时回收可观察）；
  4. agent 层免费：例程会话的真实细粒度状态与伪 session 平等参与优先级合并（task 的 working(1)/success(2) 天然低于手头 editing(4)/testing(5)；error(7) 抢镜一次可接受）；已知双 emit（例程结束真实会话 Success 与伪 session Success 同优先级先后到达，芯片在 opencode/task 间闪一次——接受，记录级）；
  5. 状态芯片任务执行期显示「例程」（`panel.agentTask`，2026-08-25 用户裁定修订：原「定时任务」同步「例程」，en 建议 Routine 实施定）。

### TC-M4-11 结果气泡与伪 session 边界（实机）

- **步骤**：触发 exec 任务完成 → 观察气泡 → 点击宠物。
- **预期**：
  1. 结果气泡经独立事件 `pulsepet://task-result` → 桥层按 M2 **critical** 入队（source=`"task:<log_id>"`；不复用 `pulsepet://bubble`——其已被 M2 冻结为 info 级 token-report 映射）；
  2. **无 reminder 载荷**：点宠物即消、不写 reminder_logs、不显示 snooze 按钮（M2 snooze 按钮条件 = critical 且有 reminder 载荷，天然不满足）；M6 起带 `[task]` 徽标；
  3. text = 任务名 + summary（lib.rs 拼接；summary 用 i18n 模板键按当前语言渲染）。

### TC-M4-12 补跑与暂停（实机）

- **步骤**：
  1. daily 任务设在系统即将睡眠的窗口（合盖 10+ 分钟）；
  2. App 关闭状态下跨过 schedule_at 后再启动 App；
  3. 托盘「暂停所有提醒」开启，等 daily/once 任务到期 → 取消暂停。
- **预期**：
  1. 醒后 **15 分钟内**补跑一次（last_triggered_at 记实际触发时刻）；醒后超窗 → 列表 / 历史出现 skipped 记录（exec 型），不补跑；
  2. App 关闭跨过 schedule_at → 重启后同口径判定（reload 错过检测——「今早跑了没」重启后可对账）；
  3. 暂停期间到期 → 不跑不补、记 skipped（exec 型）；恢复后不补跑（完全冻结）；interval 类提醒睡眠 / 暂停维持 v1 语义（不补弹，TC-RM-02 回归）；
  4. notify / exec 同窗 15 分钟（用户单一口径裁定，偏离 SCOPE「仅任务补跑」字面已标注）。
- **观察项（R1 连环补跑）**：睡眠跨过多个 daily/once 任务时刻时，醒后窗口内的连环补跑表现（并发上限 2 排队 + 单错过点）记录在案——记录级，验收不判失败。

### TC-M4-13 snooze（实机 + 单测）

- **步骤**：
  1. 触发一条 notify 提醒 → 气泡 hover 出现「稍后 10 分钟」按钮 → 点击；
  2. 10 分钟内重启 App → 等待；
  3. once 型提醒 snooze 一次 → 等重发；
  4. 观察点宠物确认路径。
- **预期**：
  1. 点击 → invoke `reminders_snooze(log_id)`：气泡即消、当前 log 结案 `dismissed_via='snooze'`、`snooze_until = now+10min` 写表（持久化）+ 内存 next_due 置为 snooze_until；
  2. **10 分钟窗口内重启 → 重发仍有效**（snooze_until 持久化；已知边界：snooze 过期后重启则静默丢弃，notify 无害，记录级）；
  3. 重发触发时清空 snooze_until 并按 kind 推进：once 重发后完结（MAX）；daily 回下个匹配日；interval 链顺延；
  4. 点宠物仍 = 确认（`dismissed_via='bubble'`，两动作并存）；**snooze 仅 notify**——exec 结果 / 任务结果气泡永不显示 snooze 按钮（无 reminder 载荷）；
  5. 重发距点击 10min > 3min 去重窗，天然无冲突；暂停期内 snooze_until 到点 → interval 类被暂停顺延吞没、daily/once 类按暂停语义记 skipped。

### TC-M4-14 跳过本次（实机 + 单测）

- **步骤**：daily 任务行操作「跳过本次」→ 等本周期 → once 任务「跳过一次」→ 对 snooze 未过期规则跳过。
- **预期**：
  1. 跳过后本周期不触发、下个匹配日正常（daily）；once → MAX（列表完结）；
  2. 操作本身在 UI 可见、不触发不记录（不写 action_logs / reminder_logs）；
  3. 若该规则 snooze_until 未过期 → 一并清空（写表 + 内存同清，防 reload 复活）；
  4. 已知边界（记录级）：once 跳过后在补跑窗内重启 App → reload 检测会补跑（跳过标记未持久化，接受）。

### TC-M4-15 退出处置与崩溃残留清理（实机 + 单测）

- **步骤**：
  1. `sleep` 型任务运行中正常退出 App → `ps` 查子进程；
  2. 强杀 App（模拟崩溃）后重启，查 action_logs。
- **预期**：
  1. `RunEvent::Exit` 遍历运行句柄 → kill 进程组（`ps` 断言无残留）+ action_logs 补写 failed（summary =「App 退出中断」i18n 模板键按语言渲染）；
  2. 完成回写先从登记表移除、Exit 只处置仍在登记表的句柄（防完成与退出竞写同一行——单测钉住）；
  3. 启动时 running 态幂等清理（崩溃残留 status → failed）；崩溃路径孤儿进程残留为已知边界（记录级）。

### TC-M4-16 执行历史区（单测 + 实机）

- **步骤**：tempdir DB 集成单测（action_logs 增删查）+ 产生多次运行（ok / failed / skipped / 超时）→ 打开历史区 → 展开一行。
- **预期**：
  1. action_logs 倒序、分页 50 条/页（`action_logs_list(reminder_id?)` 可按规则过滤）；
  2. 每行：时间 / 动作类型徽标 / summary / 状态色点（ok 绿 · failed 红 · skipped 灰 · running 蓝）；
  3. 行展开：output_tail（等宽、2KB 内）+ scheduled_at 与 started_at 差（补跑延迟可见）；
  4. 规则删除后历史保留（悬空 reminder_id 允许，action_type 冗余快照可读）；
  5. 单测（tempdir DB）：action_logs 增删查全链路 + 悬空 reminder_id 行保留（§4.11 集成行——与 TC-M4-15 的启动清理单测互补）。

### TC-M4-17 双语与深浅主题（实机）

- **步骤**：zh/en 切换 + 深 / 浅主题下目验新表单 / 徽标 / 调度摘要 / 历史区 / snooze 按钮 / 状态芯片。
- **预期**：`tasks.*` + `panel.tab.tasks` + `panel.agentTask` 键 zh/en 集合一致（完备性测试）；summary 模板键（ok / failed(N) / timeout / skipped / 退出中断）按当前语言渲染；新元素全落 M2 token。zh 下 tab 显示「例程」/「待办」、状态芯片显示「例程」（2026-08-25 R1 后用户裁定修订，en 建议 Routines / Todo / Routine 实施定；修订波及面：TC-UI-07/TC-UI-12 的「Todo」tab 显示名同口径，M2 用例留档不改）。

### TC-M4-18 Windows 分支（实机，挂观察项）

- **前置**：Windows 环境（macOS 先行开发，实机验证挂观察项——与 TC-INT-13 同批，§4.0 工期口径）。
- **步骤**：Windows 上依次触发 exec 任务（正常 / 超时 / 特殊字符命令）→ 检查执行与历史。
- **预期**：
  1. exec 经 `powershell -NoProfile -Command <command>` 执行、cwd 生效（pwsh 不保证存在故用 powershell）；
  2. 超时 → `taskkill /T /F` 杀进程树（`tasklist` 断言无残留）+ action_logs 补写 failed(timeout)；
  3. 含引号 / 特殊字符的命令 → validate 阶段字符白名单外警告提示（不阻止）+ 执行结果正确性观察（R3）；
  4. 记录级：观察项，验收不判失败（Windows 实机具备前不阻塞 M4 收尾）。

---

## 五、TC-M5 Token by agent（M5）

### TC-M5-01 transcript 解析（单测，tempdir 注入）

- **前置**：Rust `transcript.rs` 纯函数单测，构造 `~/.claude/projects/<munged-cwd>/<sessionId>.jsonl` fixture。
- **步骤/预期**：
  1. **message.id 去重（S3 回归钉子）**：同一 message.id 多次写行（thinking/text 两类事件行、usage 相同，如 6 行 assistant）→ 去重后仅 3 条 SUM；**按行序取最后一条**（勿按 timestamp——尾行可能无 ts）；id 缺失行按行级顶层 uuid 兜底去重、两者皆缺独立计入；
  2. 五维映射：`input_tokens`→input、`output_tokens`→output、`cache_creation_input_tokens`→cache_write、`cache_read_input_tokens`→cache_read、`output_tokens_details.thinking_tokens`→reasoning；
  3. 坏行 / 空文件 / 非 JSON 行跳过不崩（防御式解析，未知行类型跳过、usage 缺字段按 0）；
  4. **时间戳取自首 / 末条含 timestamp 的事件行（P1-1 钉子）**：mode / last-prompt / file-history-snapshot 等非事件行无 ts，首末行均在其中也不影响；UTC ISO8601 → epoch ms 本地口径转换（跨日边界注入时区断言）；
  5. **week 标签复刻 SQLite `%Y-W%W` 语义**（周一起始日历年周号，**勿用 chrono `iso_week()`**——ISO 年周跨年分叉会致双源同周拆柱）：2026-12-28 / 2027-01-01 / 2027-01-04 跨年对齐断言（P2-4）；
  6. title = 首条 `type=="user"` 且 content 为 string 的行截断（`chars().take(60)`，中文按字符不按字节）；无 → sessionId 前 8 位；
  7. project = **首条含非空 cwd 的行**的 cwd → basename（fixture 含无 cwd 的 snapshot 行稀释，P2-6）；全无 cwd → None（回退标签）；
  8. **last_assistant_ts** = 末条 assistant 行 timestamp（护栏专用字段——分组 / 过滤用 time_updated、护栏只看 assistant 行，两口径分离）；
  9. `memory/` 子目录排除；`~/.claude/projects` 目录不存在 → CC 源整体缺席静默（空结果，不报错不提示）。

### TC-M5-02 缓存与索引（单测）

- **步骤/预期**：
  1. `TranscriptCache`（`Arc<Mutex<...>>`，窗口创建循环之前 manage——issue #9 铁律）：按 `(mtime, size)` 缓存解析结果，未变文件不重解析；变了重解析；CC 原子写（tmp+rename 落位新文件 mtime）→ 缓存自动失效；
  2. `HashMap<String, PathBuf>` sessionId 索引：idle hook 只有 (agent, session_id) 可定位文件（无法从事件推导 munged 目录）；缓存缺失时（首查 / idle 先于查询）由 scan 补建；
  3. 无常驻 watcher（查询驱动懒解析，与 opencode.db 即开即查同模式）。

### TC-M5-03 双源查询与统一视图（实机）

- **前置**：本机有真实 CC 会话存量 + opencode.db。
- **步骤**：打开 Token 页今日 / 7d。
- **预期**：
  1. 出现 CC 会话行：标题 = 首条用户 prompt 截断 + `cc` agent 微列徽标（i18n title 提示全名）+ cost 列显示 `—`（CC 侧 cost 省略——第三方 API key 下单价表永远不准，诚实优于假精确）；
  2. KPI 总量含 CC 用量（grouped 行 SUM 自动全 agent 合计）；费用口径「仅 opencode」标注可见（M4 移除 cost KPI 卡后以 KPI 区注释小字承载——2026-08-27 措辞对齐实际形态）；
  3. day/week 聚合增 agent 维度（opencode SQL `GROUP BY day, agent, model_id` + CC 内存聚合合并，两源 concat）；range 维 `agent × model_id`；
  4. 模型 chip 来源 distinct(model_id) 自动含 CC 模型，双源同模型（如 deepseek 系）自然归并（模型维度跨 agent 合法）；
  5. CC 行与 opencode 行时间倒序统一排序；`token_stats_query` / `token_stats_today` 为 `async fn` + `spawn_blocking`（主线程不承 IO，IPC 契约不变）；
  6. **三层交叉断言双源复验（M5 验收第 1 条）**：会话静止窗口内，悬停卡总量 = 面板今日 KPI 总量 = 右键菜单显示值——三者均含 CC 双源合计（口径 = 同 0 点起点 + mock 过滤 + reasoning 不计）；degraded 态下悬停 / 菜单静默显示 CC-only 数值（不呈现横幅）。
- **观察项**：R2——MB 级长会话 transcript 首次全量解析延迟体感（文件级缓存后仅首次）；R7——TZ 显式设置环境下双源同日拆柱症状观察（SQLite `localtime` 与 chrono `Local` 口径分叉，症状易发现）。均记录级，验收不判失败。

### TC-M5-04 agent 筛选（实机）

> 口径修订（2026-08-27，用户反馈 R1 偏差）：agent 筛选由「复选框第二组」改为「标题右侧 tab 单选 + 模型复选框联动收窄」——用户意图是两级筛选（先 agent 维度、再模型维度），R1 两组复选框并排属需求偏差。

- **步骤**：Token 页「Token 时序」标题右侧 agent tab（全部 / opencode / claude-code）切换 → 观察柱图与下方模型复选框联动。
- **预期**：
  1. agent tab 为分段单选控件（Settings 主题三档 `theme-seg` 同款交互，`role="radiogroup"` + `seg active`），置于「Token 时序（按日/按周）」标题（`<h3>`）右侧同一行；选项 = **「全部」（恒显，默认选中）** + 仅有数据的 agent（无数据不渲染；仅一个 agent 有数据时「全部」仍并列恒显，语义稳定不跳动）；
  2. 选中「全部」→ 柱图 = 双源混合全量（等价原「默认全勾」语义），模型复选框列出所有 agent 的模型并集；选中具体 agent → **柱图剔除其它 agent 数据**，模型复选框**收窄为该 agent 有数据的模型**；切换 tab 时模型勾选**重置为全选**（不保留跨 tab 隐性勾选状态）；
  3. 作用域仅柱图（M3 E 口径延续）：KPI / 会话列表不随 tab 切换变化；`computeStackedBars` 的 `agentFilter` 参数位填实现（M3 N12 钉子扩展：具体 agent = 单元素集 / 「全部」= 不传或全量集）；
  4. agent 空集空态随单选交互不可达（始终恰有一项选中），原 noAgents 空态移除或降为防御分支；模型空集空态口径不变（复用 M3）。

### TC-M5-05 CC 会话汇报气泡（实机 + 单测）

- **步骤**：真实 CC 会话干活后结束（Stop 事件）→ 观察气泡。
- **预期**：
  1. 气泡「本次会话消耗 token Xk · 今日 T」（**§十二 F1 修订 2026-08-28**：单总量口径 in+out+cache_read，原「Xk input / Yk output」无 cost 双模板收敛，与 opencode 同模板）；今日段 = `token_stats_today` 双源合计；经 `pulsepet://bubble` info 级 source="token-report"（与 opencode 汇报同源同级，M2 同源合并 10s 窗口自然防双发刷屏）；
  2. 新鲜度护栏：**末条 assistant 行** timestamp（last_assistant_ts）距 idle 事件 <60s（对齐 opencode 口径；实测末条 system 行可晚于末条 assistant 3 分钟——护栏若用 time_updated 会误判）；文件缺席 / 无 assistant 行 / 全零 / 陈旧 → 静默跳过（TC-TK-12 口径）；
  3. 注入 success 状态：apply_event 复合键 `claude-code:{sessionId}` + notify；idle 分支 http 线程仅派发、解析在后台线程（不阻塞派发）；
  4. opencode 会话汇报无回归（双发时同源合并）；
  5. 竞态诚实口径（P2-3）：护栏只防陈旧不防尾行未 flush（Stop 先于尾行落盘时欠计最后一条 message——接受，对齐 R3「截至上次快照」；可选 1-2s 延迟复查增强按实测决定）；
  6. 单测：`build_cc_idle_report`（护栏消费 last_assistant_ts / 全零静默 / 无 cost 段文案）。

### TC-M5-06 CC 工具级气泡（实机 + 单测）

- **步骤**：CC 会话中编辑文件 / 跑命令 → 观察气泡；关闭工具播报开关再试。
- **预期**：
  1. M3 协议（`detail="tplId:param"`）照抄接入：「正在编辑 X」「正在跑 npm」等与 opencode 同模板同 ambient 行为；
  2. 单测：`extractDetailParam` CC 工具族五类平移（Edit/Write/MultiEdit/NotebookEdit → edit basename；Bash → 剥 KEY=value + 首词 basename；Read → read；Grep/Glob → search；WebFetch/WebSearch → web hostname）；
  3. 一次性进程**不做文件级节流**（M1 先例延续）——App 侧 10s 同源合并即节流；App 侧合并键 `tool:<tpl>` 跨 agent 共桶（双 agent 同工具 10s 内一条，R6 接受）；
  4. 开关对双 agent 统一生效；CC hook 随 App 重装更新（无手动重装负担）；
  5. **R8 边界复核**：CC 播报同样不含任何路径 / 参数 / URL 原文（TC-SEC 口径目验）——App 侧 param 再净化为格式级兜底，路径剥除责任由 CC hook 的 param 提取层继承（照抄 M3 规则即继承同等责任，M3 §3.12 R8 预留的复核点）。

### TC-M5-07 例程 ⚡ 徽标（实机，前提回填）

- **前置**：TC-M4-08 已实测确认 `--title "pulsepet 例程: …"` 保留（R8 可行性前提；若失效 → 备选「spawn 时间窗 + cwd 粗匹配」，实施时二选一）。
- **步骤**：M4 定时任务跑一次 opencode run → 打开 Token 页。
- **预期**：新会话标题前带 ⚡ 图标（`title.startsWith("pulsepet 例程:")` 匹配；title 属性「定时任务例程」）；零 schema 改动实现。

### TC-M5-08 CC 缺席回退（实机）

> 安全修订（2026-08-27，INC-20260827-1033 事故整改）：原步骤「临时改名 / 删除 `~/.claude/projects`」属破坏性 live rename——`~/.claude` 与 `~/.local/share/opencode` 同为 agent 运行时依赖目录，**agent（tester/coder）禁触这两个目录的改名 / 删除 / 写入**。改名与恢复由**用户人工执行**（或后续引入沙箱 HOME 方案），agent 仅在安全窗口内做观察断言。

> 口径 A′ 注记（2026-08-29，agent-registry P3 / §6.4）：CC Missing（目录不在）不触发横幅、opencode Ok 正常展示——与本用例预期一致，**行为不变**。

- **步骤**：**用户人工**临时改名 `~/.claude/projects`（模拟 CC 未安装）→ 告知 agent → agent 打开 Token 页观察断言 → **用户人工**恢复原状。agent 全程不执行任何针对该目录的文件系统变更命令。
- **预期**：安静回退 opencode-only——无错误横幅、无 degraded 字段（`rows` 原样 + `degraded=None`，**单源场景行为与 M3 单测钉住的原样一致**——N-4 兼容口径回归）。

### TC-M5-09 双源容错 degraded（实机 + 单测）

> 安全修订（2026-08-27，INC-20260827-1033 事故整改）：`~/.local/share/opencode/opencode.db` **同时是正在运行的 opencode 自身（含 tester/coder/supervised-coding 全部会话）的实时存储**——R2 测试轮 tester 按原步骤执行 `mv opencode.db` 导致全部会话崩溃 + 约 72s 会话数据永久丢失（实证）。**agent 禁触该文件的改名 / 删除 / 写入**；改名与恢复由**用户人工执行**（完全退出 opencode 后操作更安全），agent 仅在安全窗口内做观察断言；单测路径（预期 5）不涉及真实文件操作，不受影响。

> 口径 A′ 修订（2026-08-29，agent-registry P3 / §6.4）：源状态三态化 **Ok / Missing / Failed**——degraded 横幅收窄为「**主源 opencode Failed（在但坏）× 其余有数据**」；**Missing（未装/未用）不再触发横幅**（CC-only 用户从此干净）；全部源无数据且无一源 Ok → 硬报错，文案 N 源中性化。

- **步骤**：
  1. **用户人工**临时改名 opencode.db（模拟 opencode **Missing**，CC 有数据）→ 告知 agent → agent 打开 Token 页 / 右键菜单观察；
  2. **用户人工**恢复 opencode.db；
  3. 双源全缺（两库都缺席，同样用户人工操作）；
  4. （可选，Failed 实机验证）**用户人工**将 opencode.db 内容替换为垃圾字节（模拟「在但坏」；同样完全退出 opencode 后操作、agent 禁触）→ 观察 → 恢复。
- **预期**：
  1. Token 页 **CC-only 数据静默正常展示——无横幅、无 degraded 字段**（`degraded=None`）【口径 A′ 行为变更：原「opencode 源不可用」横幅取消】；
  2. **pet 三层（悬停卡 / 菜单 / 追加段）静默显示 CC-only 数值**（宠物不打扰原则，不变）；
  3. 恢复后正常（双源齐全）；
  4. 双源全缺 → 硬报错路径（M3「无库 → —」语义保留给全缺态；**文案 N 源中性化**，`token.error.noDatabase` 新措辞以实施落稿为准，如「未检测到任何 agent 用量数据」）；
  5. 单测（全部 tempdir / 隔离路径构造，禁触真实目录）：oc **Missing**（无 db）× CC 有数据 → `Ok(CC-only) + degraded=None`【变更：原 Some】；oc **Failed**（伪造 schema 错 / db 文件在但打不开、损坏）× CC 有数据 → `Ok(CC-only) + degraded=Some`；CC 缺席 → rows 原样 + None（M3 回归）；oc Missing / oc Failed × CC **Ok-0行**（目录在、无 transcript）→ **空态「暂无数据」**【变更：原 Err】；双源全缺 → 既有错误码透传（不变，文案中性化）。

### TC-M5-10 主题与双语目验（实机）

- **步骤**：深 / 浅主题 + zh/en 下目验新增元素。
- **预期**：agent tab（标题右侧分段单选，含「全部」项）/ 模型复选框联动收窄 / cc 徽标 / ⚡ / 费用区注释小字 / cost `—` / degraded 横幅全走 M2 token；新键（`token.agent.*`（含 `token.agent.all`）/ `token.costOpencodeOnly` / `token.taskBadge` / CC 汇报模板）zh/en 集合一致。

---

## 六、TC-M6 多 agent × 多 session 抢镜（M6）

### TC-M6-01 两层合并算法（单测）

- **前置**：`session_state.rs` `display(now)` 纯函数，注入时钟；`ACTIVITY_WINDOW_MS = 10_000`。
- **步骤/预期**：
  1. **活跃集内优先级合并**：双 session 均在 10s 窗内，error vs working → error（正在发生的 error 本就该被看见）；
  2. **同 priority 平局取 last_event_at 最新者**（双 agent 同 kind 场景——防 HashMap 迭代序任意决定胜者、芯片 agent 无因跳变；活跃集按 (priority, last_event_at) 取最大、fallback 按 (last_event_at, priority) 取最大，互为镜像字典序）；
  3. **掉窗让位（核心修复）**：会话 A error（10s 前事件后静默）+ 会话 B working（2s 前事件）→ 显示 B 的 working（v1 中 error 持续抢镜至回收）；
  4. **窗口空 fallback**：全量 sessions 中 last_event_at 最大者（平局取 priority 高者）；
  5. **solo error 钉子（P1-1）**：唯一会话（或所有其他会话均更旧）error → fallback 仍选中，显示至 30s 回收（有意行为——失败应被看见，与 v1 无回归无改善）；
  6. sessions 空 → idle（agent 为空，前端芯片降级）；
  7. **跨 agent 同权**：opencode / claude-code / task 伪 session 平等参与；
  8. **伪 session 15s 心跳时序**：心跳间隙例程掉窗但 fallback 连选 → 手头静默期间（含 >10s 长间隙）例程 working **连续显示不闪变**；手头事件到达即夺回——整体呈随手头事件节律的周期性交替；
  9. **waiting-permission 掉窗让位钉子（P2-5）**：权限请求 >10s 未审批且手头会话活跃 → review 姿态让位（接受 + 记录：终端弹窗本身持续可见，10s 已覆盖「刚发生」最重要时段）；
  10. 既有 v1 display 断言修订：同刻事件下行为等价，跨时刻用例改注入时钟；无事件时的掉窗让位依赖既有 1s 后台 notify 循环兜底（延迟 ≤1s，循环不可被优化掉）。

### TC-M6-02 双 agent 抢镜实测（实机）

- **步骤**：opencode + CC 双开并行干活 → 一侧制造 error 后停止操作。
- **预期**：
  1. 宠物随两侧事件切换归属（panel 芯片 agent 同步变化）；
  2. error 侧静默后 **≤10s 让位**另一侧活跃状态（v1「不关心的 session 报错长时间抢镜」问题消除）。

### TC-M6-03 气泡 agent 徽标（实机 + 单测）

- **步骤**：双 agent 各触发一次会话结束汇报 / 工具播报；触发一条提醒；跑一次定时任务。
- **预期**：
  1. token 汇报（opencode / CC）→ 前置 `[oc]` / `[cc]`；工具播报（双 agent）→ `[oc]` / `[cc]`（`pulsepet://tool-bubble` payload 补 agent——`/state` 请求已带，Rust 透传）；任务结果 → `[task]`（payload 显式 `agent:"task"`）；
  2. **提醒气泡无徽标**（非 agent 来源，回归项）；
  3. 载体 = `BubbleItem` 新增可选 `agent` 字段，随顶替回队 / 同源合并流转；**合并键不含 agent，徽标以幸存新条目为准**；
  4. 渲染为前置等宽小字（`[oc] `），i18n 不翻译；徽标形态（气泡 `[oc]`）与 M5 会话列表（无括号 `oc` 列徽标）**刻意不同**，勿顺手统一；
  5. 单测：agent 缺省不渲染徽标（提醒气泡回归）。

### TC-M6-04 今日 agent 分布行（实机 + 单测）〔**修订 2026-08-27：呈现面由悬停卡改为右键菜单「今日 token」信息项子行**——HoverToday 已随 M3 2026-08-25 用户裁定移除（V2-DESIGN §3.4 留档），M6 实施按后裁定优先；数据层（by_agent/口径）不变，步骤与预期按菜单子行口径执行〕

- **步骤**：双 agent 均有今日用量时右键宠物查看「今日 token」信息项；单 agent 日右键。
- **预期**：
  1. 右键菜单「今日 token」信息项在数值下追加分布行子行 `oc 39M · cc 3M`（有数据的 agent 降序）；**单项时不显示**（单 agent 无辨识需求）；
  2. `by_agent` 落在 TodayStats 结构内（随 `{today, degraded}` 包装返回）；total 口径 = 今日总量同口径（in+out+cacheRead、不含 reasoning、mock 过滤）——三层数值交叉断言由此成立；
  3. 数值与 panel 一致（M3 交叉断言延续，两层口径〔悬停卡移除后三层降两层〕）；30s 缓存口径不变；
  4. 单测：today by_agent 分组（单源单行 / 双源双行 / 零数据省略）。

### TC-M6-05 M4 例程协同（实机）

- **步骤**：例程执行中分别维持 / 停止手头会话操作；例程失败场景同法。
- **预期**：
  1. 例程执行中**手头会话窗内持续有事件** → 手头状态优先（例程 working(1) 压不过 editing/testing）；
  2. 例程失败 × 手头持续活跃 → error **≤10s 让位**（M4 R6「失败抢镜 30s」的精化实证）；
  3. 例程失败 × 无并发会话（或所有其他会话最后事件均早于 error）→ error 显示至 30s 自然回收（solo 边界，有意行为——fallback 最近活跃语义实证点）；
  4. 手头静默期例程 working 连续显示（兜底语义，不因 15s 心跳 > 10s 窗口而闪变）。

### TC-M6-06 回归目验（实机）

- **步骤**：重启 App；主题 / 双语切换；长时观察。
- **预期**：
  1. 重启后状态与芯片正常；
  2. 三事件 payload 补 agent 字段对旧解析向后兼容（前端旧解析只读既有字段；同版本锁步发布，无跨版本运行场景）；
  3. 窗口翻转带来的显示状态交替仅发生在双 session 事件交错时（事件驱动天然限频；实测烦扰再加 2s 滞回——预设计不实现，R1 观察项）；
  4. M6 新键 i18n 完备性：`token.hoverAgent` 等分布行标签键 zh/en 集合一致（键名按定稿保留〔名实注记见 V2-DESIGN §6.2 修订注记〕；徽标 `[oc]`/`[cc]`/`[task]` 不翻译——技术名约定）。

---

## 附一：v2 设计评审项 → 测试用例对照表

> 覆盖 V2-DESIGN 各章评审记录中的 P1 / 关键 P2 / N 项落点，防实施时遗漏。

| 评审项（V2-DESIGN） | 用例 |
|---|---|
| M1 P1-1 幂等判定重写（用户条目共存 → installed） | TC-INT-07 |
| M1 P2-2 node 缺席静默（command 加 `command -v node`） | TC-INT-03（形态）/ TC-INT-06（行为） |
| M1 P2-3 AgentActivity（lastEventAt 数据源） | TC-INT-09 / TC-INT-10 |
| M1 R8 一次性进程事件乱序覆盖 | TC-INT-04（观察项） |
| M1 #9 复核（manage 时序 / async 命令 / 零 panic） | TC-INT-08（M1 面：integrations 命令 + AgentActivity manage）；纪律同款断言另见 TC-UI-04 / TC-M3-03 |
| M2 P1-1 (kind, agent) 去重 + get_display_state 拉前 | TC-UI-03 / TC-UI-06 |
| M2 P1-2 token 表与样例一致性（表为唯一实施清单） | TC-UI-12 |
| M2 P2-1 队列上限与驱逐规则 | TC-UI-09 |
| M2 P2-2 禁用过滤位置（load_active_rules）+ 已停用徽标 | TC-UI-07 / TC-UI-08 |
| M2 P2-4 todo-bridge 迁移（celebration） | TC-UI-10 |
| M3 P1-1 穿透模式 ②③ 均不可达修正 | TC-M3-10 |
| M3 P1-2 agent 筛选预留位落实 | TC-M3-06 / TC-M5-04 |
| M3 P1-3 工具播报开关跨窗口机制 | TC-M3-16 |
| M3 P1-4 bash 净化强化（env 赋值 / 绝对路径） | TC-M3-13 |
| M3 N14 悬停卡穿透切换兜底 | TC-M3-10 |
| M3 N1 菜单 4 项构建 | TC-M3-11 |
| M3 N12 agentFilter 不传 = 全量（预留位钉子） | TC-M3-05 / TC-M5-04 |
| M3 P2-5 三层口径交叉断言 | TC-M3-12 |
| M4 P1-1 snooze 重发语义（优先置位非 max） | TC-M4-03 / TC-M4-13 |
| M4 P1-2 退出处置（kill 进程组 + 补写 failed） | TC-M4-15 |
| M4 P1-3 task-result 独立事件（critical、无 reminder 载荷） | TC-M4-11 |
| M4 N1 / P3-2 skipped 记账闭环（last_skipped_at 独立列） | TC-M4-04 / TC-M4-12 |
| M4 N2 跳过本次清空 snooze_until | TC-M4-14 |
| M4 N3 snooze 过期重启静默丢弃（已知边界） | TC-M4-13 |
| M4 P2-5 reload 错过检测 | TC-M4-03 / TC-M4-12 |
| M5 P1-1 时间戳取自含 ts 事件行 | TC-M5-01 |
| M5 P2-4 week 标签复刻 %W | TC-M5-01 |
| M5 C1/N-4 双源容错 degraded 包装 | TC-M5-08 / TC-M5-09 |
| M5 N-1 last_assistant_ts 护栏专用字段 | TC-M5-05 |
| M5 N-5 TranscriptCache Arc<Mutex> manage 时序 | TC-M5-02 |
| M6 P1-1 solo error 30s 有意行为 | TC-M6-01 / TC-M6-05 |
| M6 P2-2 平局镜像字典序 | TC-M6-01 |
| M6 P2-5 waiting-permission 掉窗让位（接受 + 钉子） | TC-M6-01 |

## 附二：v1 用例回归基线（按里程碑收尾时对照）

> v2 各里程碑改动面触及的 v1 既有用例；其余 v1 用例按 TC-DONE-01 全量回归节奏执行。

| 里程碑 | 必须回归的 v1 用例 | 说明 |
|---|---|---|
| M1 | TC-EV 全量（事件链路 / 鉴权 / 限流 / killswitch / token 文件）；TC-TK-10~12（idle 汇报）；TC-SEC-01~06；TC-CI-03（install.sh 手动通道保留 opencode-only） | `/state` 契约不变；`agent` 从校验升级为白名单消费 |
| M2 | TC-APP-04/05/06/14（托盘 / 热键 / 设置页）；TC-RM-03/04/09/17（气泡确认 / 烟花叠加编排）；TC-SP-02/03/11（渲染 / 换装）；TC-TD-01~08（todo 插件，含禁用 → 重启用恢复） | petStore 排队改造的记账语义不变面 |
| M3 | TC-TK 全量（含 06 对账 ≤0.01 USD）；TC-EV-20/21（气泡净化约束）；TC-RM-15 | Token 页信息架构变更但数据口径对账延续 |
| M4 | TC-RM 全量（v1 提醒行为等价：01/02/05/06/07/08/13）；TC-TD-03/06/08（todo 派生行不迁移） | 迁移 003 后 v1 行为零变化 |
| M5 | TC-TK-05/06（只读并发 / 对账——CC 行 cost `—` 不参与对账）；TC-EV-08/09（runtime 文件不动） | 双源合并不改 opencode 只读语义 |
| M6 | TC-EV-16/17（多 session 优先级合并 / 回收——**断言按 M6 两层算法修订**）；TC-EV-22（长时一致性） | display 从全量 max 改为窗口两层，v1 断言需同步修订非原样回归 |

---

## 附三：评审记录（2026-08-24，reviewer subagent）

> 评审对象：本文件初稿（75 条用例）。评审基准：`V2-DESIGN.md`（M1~M6 定稿）、`V2-SCOPE.md`、v1 `TEST-CASES.md`——四文件通读逐条核对；未读源码（v2 未实施，属实施前验收用例评审）。
> **verdict：APPROVED WITH COMMENTS**（无 P1；P2×9 / P3×7 / 澄清×4）。
> 处置结论：**全部采纳**——P2×9、P3×7 均已修订正文；澄清×4 裁定采纳（见各条）。

### 总体评价（摘要）

数值常量与语义转译逐项核对无误（dwell 8/6/4s、补跑窗 14m59s/15m01s 边界、snooze 重发语义、M6 平局镜像字典序、solo error 有意行为、迁移 003 +7 列、week 复刻 %W 三组跨年日期等）；附二所引 v1 用例编号全部存在且语义匹配；体例与 v1 一致。短板集中在覆盖承接完备性——设计单测表少量条目仅实机承接或未承接，附一两行映射偏差。

### 问题清单与处置

**P2-1（已修，→ TC-INT-06）**：M1 实机验收第 6 条「killswitch 对 CC 接入生效」无用例承接——TC-INT-02 预期 3 是脚本级单测、TC-INT-13 预期 3 是 Windows 形态，macOS 上 shell 包装前置检查的端到端实机验证缺失。修法：TC-INT-06 追加创建 / 删除 killswitch 步骤。

**P2-2（已修，→ TC-INT-08 + 附一）**：附一「M1 #9 复核」映射不实——TC-UI-04（atlas_sheet_png）/ TC-M3-03（token_stats_today）只证明纪律在 M2/M3 被遵守，M1 面的 integrations.rs 三命令（async fn + spawn_blocking + 零 panic）与 AgentActivity manage 时序无断言可拦截。修法：TC-INT-08 增补纪律断言；附一该行改为指向 TC-INT-08（M1 面）。

**P2-3（已修，→ TC-INT-06 + 附一）**：附一「M1 P2-2 node 缺席静默」两处指向（TC-INT-02 / TC-INT-13）均未测「hook 文件存在但 node 不在 PATH → 兜底静默」路径（TC-INT-13 测的是脚本缺席）。修法：TC-INT-06 追加 PATH 移除 node 步骤；附一改指 TC-INT-03 / TC-INT-06。

**P2-4（已修，→ 新增 TC-UI-14）**：M2 §2.10 单测表「registry 逻辑（禁用过滤/回退/插件插位/panel_tab 键读取）」无前端纯函数单测；panel_tab 键读取是设计 P3-③ 标注的回归陷阱点。修法：新增 TC-UI-14（useTabs 纯逻辑全覆盖）。

**P2-5（已修，→ 新增 TC-M3-17）**：M3 §3.11 单测表「i18n 新键 zh/en 完备性」整章缺失（M3 新键量六章之最：toolb.* 五键 + token.* 新键 + settings.* 两族）。修法：新增 TC-M3-17。

**P2-6（已修，→ TC-M3-09）**：设计单测表「idle 追加段格式与失败省略」仅实机承接，且「失败省略」分支实机不可稳定构造（跨午夜竞态）。修法：TC-M3-09 改「单测 + 实机」，注入时钟 / 错误断言追加段格式与失败省略。

**P2-7（已修，→ TC-M3-04 / 07 / 11）**：token-stats.ts（today 0 点边界 / sumRows total）与 pet-menu（4 项构建 / 三态 label / 点击直达 id）仅实机承接，边界值需注入时钟的纯函数断言。修法：三条用例标注「单测 + 实机」并补单测断言。

**P2-8（已修，→ 新增 TC-M4-18）**：M4 Windows 分支（powershell / taskkill / 参数转义）实机验证挂观察项但无用例条目（M1 有 TC-INT-13 先例）。修法：新增 TC-M4-18（记录级观察项）。

**P2-9（已修，→ TC-M5-03）**：M5 验收第 1 条「M3 三层交叉断言双源复验」无用例（TC-M6-04 属 M6 用例，M5 收尾时不可用）。修法：TC-M5-03 追加三层交叉断言预期项。

**P3（记录级，均已修）**：
1. 附一「M4 N1/N3-2」编号不存在（last_skipped_at 是第三轮 P3-2）→ 已改「M4 N1 / P3-2」；
2. M4 R1 连环补跑观察项 → TC-M4-12 追加；
3. M5 R2（大 transcript 首查延迟）/ R7（TZ 分叉）观察项 → TC-M5-03 追加；
4. M3 R8「M5 复核 App 侧 param 再净化边界」→ TC-M5-06 显式复述；
5. M6 新键（token.hoverAgent 等）i18n 完备性 → TC-M6-06 追加；
6. M4 action_logs 增删查单测（tempdir）→ TC-M4-16 标注含单测；
7. 附一补录已承接的 N 项映射（M3 N1 / M3 N12 / M4 N3 / M5 N-5）。

### 澄清项（作者裁定）

1. 附一 M1 #9 行属遗漏而非有意分层——采纳 P2-2 修法 (a)，M1 面纪律由 M1 用例钉住；
2. killswitch 实机验收系设计 §1.10 明确条目，应补（P2-1）；
3. M4 Windows 观察项缺席非有意（硬件未具备），补条目保持与 TC-INT-13 体例一致（P2-8）；
4. M5 三层交叉断言不能依赖 M6 用例（M5 收尾时不存在），在 TC-M5-03 独立承接（P2-9）。

### 修订汇总（2026-08-24，按评审意见）

用例数 75 → 78（+TC-UI-14 / TC-M3-17 / TC-M4-18）；TC-INT-06 补 killswitch + node 缺席两步；TC-INT-08 补线程与 panic 纪律断言；TC-M3-04 / 07 / 09 / 11 改「单测 + 实机」并补断言；TC-M4-12 补 R1 观察项、TC-M4-16 标注含单测；TC-M5-03 补三层交叉断言 + R2/R7 观察项；TC-M5-06 补 R8 边界复核；TC-M6-06 补 i18n 完备性；附一修两行映射 + 改一处编号 + 补四行 N 项。

### 复审记录（2026-08-24 第二轮，同 reviewer 续会话）

> 复核 16 项处置：**全部正确落实**（逐项证据见会话记录）；附三评审记录忠实完整；未声明修订的用例与修订前逐字一致、无夹带改动；正文引用与附一 33 行映射均无偏差。新发现仅 1 条 P3-N1（TC-INT-06 步骤 5 的 PATH 构造执行提示，非文档缺陷）——已顺手补入该步骤括注。
> **verdict：APPROVED**——「建议将该文件作为 v2 实施前验收基线定稿」。

#### 终审记录（2026-08-24，用户）

- **评审流程闭环**：两轮（APPROVED WITH COMMENTS → 修订 → APPROVED）；P2×9 / P3×7 / 澄清×4 全部采纳落实，P3-N1 执行提示已补——照单定稿。
- **V2-TEST-CASES.md 定稿**（78 条用例）：作为 v2 M1~M6 各里程碑实施与收尾的验收基线；各里程碑 Done 验收时按章勾验，附二回归基线随收尾对照执行。后续里程碑实施中的勘误以「修订」标注追加，不回改已定稿章节。
